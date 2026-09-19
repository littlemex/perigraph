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

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from perigraph import collect, wire  # noqa: E402

CASES = json.loads((ROOT / "spec" / "fixtures" / "identity.json").read_text(encoding="utf-8"))["cases"]

NODE_SCRIPT = """
import { fromRequest } from "%(dist)s/src/collect.js";
import { toAttributes } from "%(dist)s/src/wire.js";
const cases = %(cases)s;
console.log(JSON.stringify(cases.map((c) => toAttributes(fromRequest(c, { collector: "x", version: "1" })))));
"""


def typescript_attributes(bodies: list[dict]) -> list[dict]:
    dist = ROOT / "typescript" / "dist"
    if not dist.exists():
        raise SystemExit("typescript/dist is missing: run `npm run build` in typescript/ first")
    script = NODE_SCRIPT % {"dist": dist.as_posix(), "cases": json.dumps(bodies)}
    out = subprocess.run([  # noqa: S603
        "node", "--input-type=module", "-e", script], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise SystemExit(f"the TypeScript sender failed:\n{out.stderr}")
    return json.loads(out.stdout)


def main() -> int:
    bodies = [c["body"] for c in CASES]
    ts = typescript_attributes(bodies)
    failures: list[str] = []
    parsed_agreements: list[str] = []

    for case, ts_attrs in zip(CASES, ts):
        py_attrs = wire.to_attributes(collect.from_request(case["body"], collector="x", version="1"))
        name = case["name"]

        py_id, ts_id = py_attrs.get("perigraph.identity"), ts_attrs.get("perigraph.identity")
        if py_id != ts_id:
            failures.append(f"{name}: identity {py_id} against {ts_id}")
        elif py_id is not None and py_id != case["identity"]:
            failures.append(f"{name}: both senders agree on {py_id} and the fixture says {case['identity']}")

        for key in sorted(set(py_attrs) | set(ts_attrs)):
            if not key.endswith(".digest"):
                continue
            boundary = py_attrs.get(key.replace(".digest", ".boundary"))
            same = py_attrs.get(key) == ts_attrs.get(key)
            if boundary == "model_visible" and not same:
                failures.append(f"{name}: {key} is model_visible and differs")
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

    print(f"checked {len(CASES)} bodies across two independent senders")
    for f in failures:
        print(f"FAIL {f}")
    if not failures:
        print("identities and every model_visible digest agree; parsed digests differ as the spec says they may")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
