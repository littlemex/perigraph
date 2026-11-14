#!/usr/bin/env python3
"""Conformance adapter for the Python reference implementation (contract: conformance/README.md).

Reads the installed `perigraph` package, or the repository's src/ when run from a clone without installing it.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from perigraph import collect, wire, model as pm  # noqa: E402
from perigraph.vocab import Unidentified  # noqa: E402


def describe(_req):
    return {"name": "perigraph (Python reference)", "roles": ["collector", "stamper", "receiver"]}


def collect_(req):
    return {"attributes": wire.to_attributes(collect.from_request(req["body"], collector="conformance", version="1"))}


def stamp(req):
    try:
        ck = pm.checkpoint_digest([(p, hashlib.sha256(t.encode("utf-8")).hexdigest()) for p, t in req["files"].items()])
        pr = pm.precision_digest(req["precision"])
        rt = pm.runtime_digest(req["runtime"])
        m = pm.loaded(checkpoint=ck, precision=pr, runtime=rt, answer_mode=req["answer_mode"])
    except Unidentified as e:
        return {"refused": str(e)}
    rec = dataclasses.replace(collect.from_request({}, collector="conformance", version="1"), model=m)
    return {"checkpoint_digest": ck, "precision_digest": pr, "runtime_digest": rt, "model_identity": m.model_identity,
            "artifact_identity": m.artifact_identity, "attributes": wire.to_attributes(rec)}


def receive(req):
    try:
        r = wire.from_attributes(req["attributes"])
    except (Unidentified, KeyError, TypeError, ValueError) as e:
        return {"outcome": "rejected", "why": str(e)}
    return {"outcome": "stored", "verdict": "admitted" if r.admissible_to_a_verdict() else "refused"}


OPS = {"describe": describe, "collect": collect_, "stamp": stamp, "receive": receive}

for line in sys.stdin:
    req = json.loads(line)
    reply = OPS[req["op"]](req)
    print(json.dumps({"id": req["id"], **reply}, ensure_ascii=False), flush=True)
