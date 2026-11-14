#!/usr/bin/env python3
"""Compare the two reference senders on the same request bodies, and fail on any disagreement that matters.

**This is the job that earns its place in CI.** Both implementations' own test suites passed before and after the five
spec fixes, because a test written against an implementation cannot find a sentence that implementation happened to
interpret one way. Only running them against each other finds it.

What "matters" is defined rather than guessed: a `model_visible` digest and the identity MUST agree, and a `parsed`
digest is collector-local by spec and is expected to differ. So this script fails if the identities diverge, and also
fails if the `parsed` digests ever start agreeing by accident -- because then the collector-local rule has become a
sentence nobody is testing, and the next person to read it will believe it is enforced.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from perigraph import collect, wire  # noqa: E402

CASES = json.loads((ROOT / "spec" / "fixtures" / "identity.json").read_text(encoding="utf-8"))["cases"]
MODEL_CASES = json.loads((ROOT / "spec" / "fixtures" / "model_identity.json").read_text(encoding="utf-8"))["cases"]

NODE_SCRIPT = """
import { fromRequest } from "%(dist)s/src/collect.js";
import { toAttributes } from "%(dist)s/src/wire.js";
// Parsed from JSON text, as a collector receives a body: an object literal would read "__proto__" as the prototype.
const cases = JSON.parse(%(cases)s);
console.log(JSON.stringify(cases.map((c) => toAttributes(fromRequest(c, { collector: "x", version: "1" })))));
"""


def typescript_attributes(bodies: list[dict]) -> list[dict]:
    dist = ROOT / "typescript" / "dist"
    if not dist.exists():
        raise SystemExit("typescript/dist is missing: run `npm run build` in typescript/ first")
    script = NODE_SCRIPT % {"dist": dist.as_posix(), "cases": json.dumps(json.dumps(bodies))}
    out = subprocess.run([  # noqa: S603
        "node", "--input-type=module", "-e", script], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise SystemExit(f"the TypeScript sender failed:\n{out.stderr}")
    return json.loads(out.stdout)


MODEL_SCRIPT = """
import { createHash } from "node:crypto";
import { checkpointDigest, precisionDigest, runtimeDigest, loaded } from "%(dist)s/src/model.js";
const cases = %(cases)s;
console.log(JSON.stringify(cases.map((c) => {
  const m = loaded({ checkpoint: checkpointDigest(Object.entries(c.files).map(([p, t]) => [p, createHash("sha256").update(Buffer.from(t, "utf8")).digest("hex")])), precision: precisionDigest(c.precision),
                     runtime: runtimeDigest(c.runtime), answerMode: c.answer_mode });
  return { model: m.modelIdentity, artifact: m.artifactIdentity };
})));
"""


def model_failures() -> list[str]:
    """The model identity is defined by bytes, not by a collector, so the two senders must agree on every case.

    Run on the helpers rather than on a loader, because the helpers are the only place the two could disagree."""
    from perigraph import model as pm

    dist = ROOT / "typescript" / "dist"
    script = MODEL_SCRIPT % {"dist": dist.as_posix(), "cases": json.dumps(MODEL_CASES)}
    out = subprocess.run([  # noqa: S603
        "node", "--input-type=module", "-e", script], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise SystemExit(f"the TypeScript model helpers failed:\n{out.stderr}")
    failures = []
    for case, ts in zip(MODEL_CASES, json.loads(out.stdout)):
        m = pm.loaded(checkpoint=pm.checkpoint_digest([(p, hashlib.sha256(t.encode("utf-8")).hexdigest())
                                                           for p, t in case["files"].items()]),
                      precision=pm.precision_digest(case["precision"]), runtime=pm.runtime_digest(case["runtime"]),
                      answer_mode=case["answer_mode"])
        for key, py, want in (("model", m.model_identity, case["model_identity"]),
                              ("artifact", m.artifact_identity, case["artifact_identity"])):
            if py != ts[key]:
                failures.append(f"{case['name']}: {key} identity {py} against {ts[key]}")
            elif py != want:
                failures.append(f"{case['name']}: both senders agree on {key} {py} and the fixture says {want}")
    return failures


def go_failures() -> list[str]:
    """The Go sender, written from SPEC.md alone by a different model family. It must reproduce every identity and every
    `model_visible` digest, and give the same absence reason for every part both collectors claim. Free text (details,
    labels) and each collector's own manifest are its own and are not compared, except that a manifest is read as a set."""
    out = subprocess.run(["go", "run", "./cmd/crosscheck",  # noqa: S603, S607
                          str(ROOT / "spec" / "fixtures" / "identity.json"),
                          str(ROOT / "spec" / "fixtures" / "model_identity.json")],
                         cwd=ROOT / "go", capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise SystemExit(f"the Go sender failed:\n{out.stderr}")
    got = json.loads(out.stdout)
    failures = []
    for case, ga in zip(CASES, got["attrs"]):
        pa = wire.to_attributes(collect.from_request(case["body"], collector="x", version="1"))
        name = case["name"]
        if ga.get("perigraph.harness_identity") != case["identity"]:
            failures.append(f"{name}: Go identity {ga.get('perigraph.harness_identity')} and the fixture says "
                            f"{case['identity']}")
        for key in pa:
            if key.endswith(".digest") and pa.get(key.replace(".digest", ".boundary")) in ("model_visible",
                                                                                          "canonical_value") \
                    and pa[key] != ga.get(key):
                failures.append(f"{name}: {key} is {pa.get(key.replace('.digest', '.boundary'))} and Go differs")
        for key in ("perigraph.request.unlisted", "perigraph.request.unlisted_omitted"):
            if pa.get(key) != ga.get(key):
                failures.append(f"{name}: {key} is {pa.get(key)!r} against Go's {ga.get(key)!r}")
        both = set(pa["perigraph.collector_reaches"].split(",")) & set(
            p for p in str(ga.get("perigraph.collector_reaches", "")).split(",") if p)
        for part in sorted(both):
            for k in (f"perigraph.absent.{part}.reason", f"perigraph.part.{part}.sourcing"):
                if pa.get(k) != ga.get(k):
                    failures.append(f"{name}: {k} is {pa.get(k)!r} against Go's {ga.get(k)!r}")
        for part in ("checkpoint", "precision", "runtime", "answer_mode"):
            k = f"perigraph.model_absent.{part}.reason"
            if pa.get(k) != ga.get(k):
                failures.append(f"{name}: {k} is {pa.get(k)!r} against Go's {ga.get(k)!r}")
    for case, gm in zip(MODEL_CASES, got["models"]):
        for key, gk in (("checkpoint_digest", "checkpoint_digest"), ("precision_digest", "precision_digest"),
                        ("runtime_digest", "runtime_digest"), ("model_identity", "model"),
                        ("artifact_identity", "artifact")):
            if case[key] != gm.get(gk):
                failures.append(f"{case['name']}: {key} is {case[key]} and Go says {gm.get(gk)}")
    refused = json.loads((ROOT / "spec" / "fixtures" / "model_identity.json").read_text(encoding="utf-8"))
    for precision, ok in zip(refused["refused_precision"]["cases"], got["refused_precision"]):
        if not ok:
            failures.append(f"Go accepted the unresolved precision {precision}")
    return failures


def main() -> int:
    bodies = [c["body"] for c in CASES]
    ts = typescript_attributes(bodies)
    failures: list[str] = []
    parsed_agreements: list[str] = []

    for case, ts_attrs in zip(CASES, ts):
        py_attrs = wire.to_attributes(collect.from_request(case["body"], collector="x", version="1"))
        name = case["name"]

        py_id, ts_id = py_attrs.get("perigraph.harness_identity"), ts_attrs.get("perigraph.harness_identity")
        if py_id != ts_id:
            failures.append(f"{name}: identity {py_id} against {ts_id}")
        elif py_id is not None and py_id != case["identity"]:
            failures.append(f"{name}: both senders agree on {py_id} and the fixture says {case['identity']}")

        for key in sorted(set(py_attrs) | set(ts_attrs)):
            if not key.endswith(".digest"):
                continue
            boundary = py_attrs.get(key.replace(".digest", ".boundary"))
            same = py_attrs.get(key) == ts_attrs.get(key)
            if boundary in ("model_visible", "canonical_value") and not same:
                failures.append(f"{name}: {key} is {boundary} and differs")
            if boundary == "parsed" and same:
                parsed_agreements.append(f"{name}: {key}")

        for key in sorted(set(py_attrs) | set(ts_attrs)):
            if key.endswith(".digest") or key == "perigraph.collector":
                continue
            if py_attrs.get(key) != ts_attrs.get(key):
                failures.append(f"{name}: {key} is {py_attrs.get(key)!r} against {ts_attrs.get(key)!r}")

    if parsed_agreements and len(parsed_agreements) == sum(
        1 for c in CASES for k in wire.to_attributes(collect.from_request(c["body"], collector="x", version="1"))
        if k.endswith(".digest")
        and wire.to_attributes(collect.from_request(c["body"], collector="x", version="1")).get(
            k.replace(".digest", ".boundary")) == "parsed"
    ):
        failures.append(
            "every parsed digest now agrees across the two senders. That may look like good news and it means the "
            "collector-local rule in SPEC.md section 2.3 is no longer exercised by anything: either the rule should be "
            "tightened into a normative serialisation, or a case that does differ belongs in the fixtures")

    failures.extend(model_failures())
    failures.extend(go_failures())
    print(f"checked {len(CASES)} bodies and {len(MODEL_CASES)} model cases across three senders")
    for f in failures:
        print(f"FAIL {f}")
    if not failures:
        print("identities, every model_visible and canonical_value digest and the unlisted members agree; parsed digests "
              "differ as the spec says they may")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
