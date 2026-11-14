#!/usr/bin/env python3
"""Keep spec/requirements.json in step with the requirement sentences in SPEC.md and spec/bindings/*.md.

    python tools/requirements.py           rewrite spec/requirements.json from SPEC.md
    python tools/requirements.py --check   exit 1 if the registry and SPEC.md disagree

A requirement is a sentence of SPEC.md or of a binding containing a BCP 14 keyword in capitals (section 0.1). Each gets an identifier
that never changes and is never reused: an edited sentence keeps its identifier only when its text is unchanged, so a
reworded requirement is a new requirement and the old identifier is retired rather than silently re-pointed. That is
deliberate: a conformance case that cites an identifier was written against a sentence, and a different sentence under
the same name is how a case comes to test something nobody wrote.

`roles` is read from the subject before each keyword; where the sentence is passive the generator writes `any`, and
an entry edited by hand with `"roles_by_hand": true` keeps its roles for as long as its text is unchanged. `cases` lists the conformance cases that cite the identifier, so the
registry also says which requirements no portable case checks yet -- printed by --report.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = ROOT / "SPEC.md"
OUT = ROOT / "spec" / "requirements.json"
CASES = ROOT / "conformance" / "cases"
KEYWORD = re.compile(r"\b(MUST NOT|MUST|SHALL NOT|SHALL|SHOULD NOT|SHOULD|NOT RECOMMENDED|RECOMMENDED|MAY|REQUIRED|OPTIONAL)\b")
ROLES = ("stamper", "forwarder", "collector", "sender", "receiver", "implementation", "proposal")
LEVEL = {"MUST": "MUST", "MUST NOT": "MUST", "SHALL": "MUST", "SHALL NOT": "MUST", "REQUIRED": "MUST",
         "SHOULD": "SHOULD", "SHOULD NOT": "SHOULD", "RECOMMENDED": "SHOULD", "NOT RECOMMENDED": "SHOULD",
         "MAY": "MAY", "OPTIONAL": "MAY"}


def blocks(text: str):
    """Yield (section, block) for every paragraph, list item and table row outside code fences."""
    section = ""
    para: list[str] = []
    fence = False

    def flush():
        if para:
            yield section, " ".join(para)
            para.clear()

    for line in text.splitlines():
        if line.startswith("```"):
            fence = not fence
            yield from flush()
            continue
        if fence:
            continue
        head = re.match(r"^#{2,4}\s+(\d+(?:\.\d+)?[a-z]?)\b", line)
        if head or line.startswith("#"):
            yield from flush()
            if head:
                section = head.group(1)
            continue
        if not line.strip():
            yield from flush()
            continue
        if line.startswith("|") or re.match(r"^\s*(?:[-*]|\d+\.)\s", line):
            yield from flush()
            if line.startswith("|"):
                for cell in line.strip().strip("|").split("|"):
                    if cell.strip():
                        yield section, cell.strip()
                continue
        para.append(re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line).strip() if not para else line.strip())
    yield from flush()


def sentences(block: str):
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z*`(])", block):
        s = s.strip()
        if s:
            yield s


def normative(text: str, where: str = "") -> list[tuple[str, str]]:
    out = []
    for section, block in blocks(text):
        if section == "0.1" and not where:
            continue
        section = where or section
        for s in sentences(block):
            if KEYWORD.search(s):
                out.append((section, s))
    return out


def roles_of(sentence: str) -> list[str]:
    """The roles a sentence binds: for each keyword, the nearest role named before it in the sentence."""
    out: list[str] = []
    low = sentence.lower()
    for m in KEYWORD.finditer(sentence):
        head = low[:m.start()]
        hits = [(head.rfind(r), r) for r in ROLES if r in head]
        r = max(hits)[1] if hits else "any"
        if r not in out:
            out.append(r)
    return out


STRENGTH = {"MUST": 0, "SHOULD": 1, "MAY": 2}


def cited() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if CASES.is_dir():
        for f in sorted(CASES.glob("*.json")):
            for case in json.loads(f.read_text(encoding="utf-8"))["cases"]:
                for rid in case.get("requirements", []):
                    out.setdefault(rid, []).append(f"{f.stem}/{case['id']}")
    return out


def build() -> dict:
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"requirements": [], "retired": []}
    by_text = {r["text"]: r for r in old["requirements"]}
    used = {r["id"] for r in old["requirements"]} | set(old.get("retired", []))
    next_n = 1 + max([int(i.split("-")[1]) for i in used] or [0])
    cites = cited()
    reqs = []
    seen = set()
    found = normative(SPEC.read_text(encoding="utf-8"))
    for binding in sorted((ROOT / "spec" / "bindings").glob("*.md")):
        found += normative(binding.read_text(encoding="utf-8"), f"bindings/{binding.stem}")
    for section, text in found:
        if text in seen:
            continue
        seen.add(text)
        prev = by_text.get(text)
        if prev:
            rid = prev["id"]
        else:
            rid = f"PG-{next_n:03d}"
            next_n += 1
        level = min((LEVEL[m.group(1)] for m in KEYWORD.finditer(text)), key=STRENGTH.__getitem__)
        entry = {"id": rid, "section": section, "level": level, "roles": roles_of(text), "text": text,
                 "cases": cites.get(rid, [])}
        if prev and prev.get("roles_by_hand"):
            entry["roles"], entry["roles_by_hand"] = prev["roles"], True
        reqs.append(entry)
    live = {r["id"] for r in reqs}
    retired = sorted(set(old.get("retired", [])) | {r["id"] for r in old["requirements"] if r["id"] not in live})
    return {"note": ("Every sentence of SPEC.md that carries a BCP 14 keyword, with an identifier that is never reused. "
                     "Generated by tools/requirements.py; edit SPEC.md, not this file. `cases` names the conformance "
                     "cases citing the requirement; an empty list means no portable case checks it yet."),
            "requirements": reqs, "retired": retired}


def main() -> int:
    reg = build()
    text = json.dumps(reg, indent=2, ensure_ascii=False) + "\n"
    dangling = sorted(set(cited()) - {r["id"] for r in reg["requirements"]})
    if dangling:
        print(f"conformance cases cite requirements that do not exist: {dangling}")
        return 1
    if "--report" in sys.argv:
        bare = [r for r in reg["requirements"] if not r["cases"]]
        print(f"{len(reg['requirements'])} requirements, {len(bare)} with no conformance case")
        for r in bare:
            print(f"  {r['id']} {r['section']:>5} {','.join(r['roles']):<20} {r['text'][:100]}")
        return 0
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("spec/requirements.json is not in step with SPEC.md: run tools/requirements.py")
            return 1
        print(f"{len(reg['requirements'])} requirements in step with SPEC.md")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(reg['requirements'])} requirements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
