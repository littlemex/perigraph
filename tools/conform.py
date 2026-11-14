#!/usr/bin/env python3
"""Run the perigraph conformance suite against any implementation, through a small adapter it provides.

    python tools/conform.py --adapter "python conformance/adapters/python_adapter.py"
    python tools/conform.py --adapter "node conformance/adapters/typescript_adapter.mjs" --role receiver

The adapter is a process that reads one JSON request per line on stdin and writes one JSON response per line on stdout
(conformance/README.md gives the contract). The runner never imports the implementation, so an implementation in any
language is checked by the same cases and the same code.

What is checked, per role (SPEC section 8):

* collector: every body in spec/fixtures/identity.json gives the fixture's harness identity and instruction digest, the
  record validates against spec/schema/record.schema.json, and it carries a model half and the tool_extension absence;
* stamper: every case in spec/fixtures/model_identity.json gives the fixture's digests and identities, and every map in
  refused_precision is refused;
* receiver: every case in conformance/cases/receiver.json gets the expected outcome and verdict.

Schema validation needs the `jsonschema` package. Without it the runner stops rather than reporting a pass it did not
check; `--no-schema` skips those checks and says so in the summary.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shlex
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
P = "perigraph."
_V = json.loads((ROOT / "spec" / "vocabularies.json").read_text(encoding="utf-8"))
MODEL_PARTS = _V["model_parts"]["values"]
PARTS = _V["parts"]["values"]


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


class Adapter:
    def __init__(self, command: str, cwd: pathlib.Path):
        self.proc = subprocess.Popen(shlex.split(command), cwd=cwd, stdin=subprocess.PIPE,  # noqa: S603
                                     stdout=subprocess.PIPE, text=True, encoding="utf-8")
        self.n = 0

    def ask(self, op: str, **fields) -> dict:
        self.n += 1
        self.proc.stdin.write(json.dumps({"id": self.n, "op": op, **fields}, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise SystemExit(f"the adapter exited while answering {op!r} (exit code {self.proc.poll()})")
        reply = json.loads(line)
        if reply.get("id") != self.n:
            raise SystemExit(f"the adapter answered request {reply.get('id')} when asked {self.n}")
        return reply

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait(timeout=30)


def validator(enabled: bool):
    if not enabled:
        return None
    try:
        import jsonschema
    except ImportError:
        raise SystemExit("schema checks need the jsonschema package (pip install jsonschema), or pass --no-schema "
                         "to skip them and have the summary say so")
    schema = load("spec/schema/record.schema.json")
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def schema_errors(v, attrs: dict) -> list[str]:
    if v is None:
        return []
    return [f"schema: {'/'.join(map(str, e.path)) or '(record)'}: {e.message[:160]}" for e in v.iter_errors(attrs)]


def check_collector(a: Adapter, v) -> list[tuple[str, list[str], list[str]]]:
    out = []
    for case in load("spec/fixtures/identity.json")["cases"]:
        r = a.ask("collect", body=case["body"])
        errs: list[str] = []
        attrs = r.get("attributes")
        if not isinstance(attrs, dict):
            out.append((f"collector/{case['name']}", ["PG-044"], [f"no attributes: {r.get('error', r)}"]))
            continue
        errs += schema_errors(v, attrs)
        for key, want in ((P + "harness_identity", case["identity"]), (P + "part.instruction.digest", case["instruction_digest"])):
            got = attrs.get(key)
            if got != want:
                errs.append(f"{key} is {got!r}, the fixture says {want!r}")
        for part in PARTS:
            if P + f"part.{part}.sourcing" not in attrs and P + f"absent.{part}.reason" not in attrs:
                errs.append(f"part {part} is neither held nor absent (every part is required, SPEC 1.2)")
        for part in MODEL_PARTS:
            if P + f"model.{part}.sourcing" not in attrs and P + f"model_absent.{part}.reason" not in attrs:
                errs.append(f"model part {part} is neither a part nor an absence (a model half is required)")
        if attrs.get(P + "absent.tool_extension.reason") != "not_observable":
            errs.append("tool_extension is not recorded as an absence with reason not_observable")
        out.append((f"collector/{case['name']}", ["PG-044"], errs))
    return out


def check_stamper(a: Adapter, v) -> list[tuple[str, list[str], list[str]]]:
    out = []
    fixture = load("spec/fixtures/model_identity.json")
    for case in fixture["cases"]:
        r = a.ask("stamp", files=case["files"], precision=case["precision"], runtime=case["runtime"],
                  answer_mode=case["answer_mode"])
        errs = []
        if "refused" in r:
            errs.append(f"refused a fixture case: {r['refused']}")
        else:
            for key in ("checkpoint_digest", "precision_digest", "runtime_digest", "model_identity", "artifact_identity"):
                if r.get(key) != case[key]:
                    errs.append(f"{key} is {r.get(key)!r}, the fixture says {case[key]!r}")
            if isinstance(r.get("attributes"), dict):
                errs += schema_errors(v, r["attributes"])
        out.append((f"stamper/{case['name']}", ["PG-044"], errs))
    for i, precision in enumerate(fixture["refused_precision"]["cases"]):
        good = fixture["cases"][0]
        r = a.ask("stamp", files=good["files"], precision=precision, runtime=good["runtime"], answer_mode=good["answer_mode"])
        errs = [] if "refused" in r else [f"accepted the unresolved precision {precision}"]
        out.append((f"stamper/refused-precision-{i}", ["PG-044"], errs))
    return out


def check_receiver(a: Adapter, v) -> list[tuple[str, list[str], list[str]]]:
    out = []
    for case in load("conformance/cases/receiver.json")["cases"]:
        r = a.ask("receive", attributes=case["attributes"])
        want = case["expect"]
        got = {"outcome": r.get("outcome")}
        if "verdict" in want:
            got["verdict"] = r.get("verdict")
        errs = [] if got == want else [f"got {got}, expected {want}" + (f" ({r['why']})" if r.get("why") else "")]
        if v is not None:
            shape_ok = not schema_errors(v, case["attributes"])
            if want["outcome"] == "stored" and not shape_ok:
                errs.append("SPEC stores this record and the schema rejects it: the schema and the prose disagree")
            if want["outcome"] == "rejected" and shape_ok != (case.get("schema") == "accepts"):
                errs.append(f"the case says the schema {case.get('schema')} it, and the schema "
                            f"{'accepts' if shape_ok else 'rejects'} it")
        out.append((f"receiver/{case['id']}", case["requirements"], errs))
    return out


CHECKS = {"collector": check_collector, "stamper": check_stamper, "receiver": check_receiver}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--adapter", required=True, help="command that starts the implementation's adapter")
    ap.add_argument("--role", action="append", choices=sorted(CHECKS), help="roles to check (default: all it declares)")
    ap.add_argument("--no-schema", action="store_true", help="skip schema validation, and say so in the summary")
    ap.add_argument("--json", metavar="FILE", help="also write the results as JSON")
    args = ap.parse_args()
    v = validator(not args.no_schema)
    a = Adapter(args.adapter, ROOT)
    desc = a.ask("describe")
    declared = desc.get("roles", [])
    roles = args.role or declared
    undeclared = sorted(set(roles) - set(declared))
    if undeclared:
        raise SystemExit(f"{desc.get('name', 'the adapter')} does not declare the roles {undeclared}")
    results = []
    for role in roles:
        results += CHECKS[role](a, v)
    a.close()
    failed = [r for r in results if r[2]]
    for name, reqs, errs in results:
        print(f"{'FAIL' if errs else 'pass'}  {name}  [{', '.join(reqs)}]")
        for e in errs:
            print(f"        {e}")
    note = "" if v is not None else " (schema checks SKIPPED)"
    print(f"\n{desc.get('name', 'adapter')}: roles {', '.join(roles)}; {len(results) - len(failed)} of {len(results)} "
          f"cases pass{note}")
    if args.json:
        pathlib.Path(args.json).write_text(json.dumps(
            {"implementation": desc, "roles": roles, "schema_checked": v is not None,
             "results": [{"case": n, "requirements": r, "failures": e} for n, r, e in results]}, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
