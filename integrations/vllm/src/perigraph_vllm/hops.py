"""Turn this plug-in's record lines into hop rows for a receiver that joins by request id (`tierbook bind`).

    python -m perigraph_vllm.hops $PERIGRAPH_VLLM_DIR/records-*.jsonl > vllm-hops.jsonl

A hop row carries only opaque strings: the request id, the digest of the bytes received, and the three identities
when the record has them. A record line with no record (`error`) still becomes a row, with no identities, so a
receiver sees the request and that nothing was stated about it.
"""
from __future__ import annotations

import json
import sys

KEYS = {"harness": "perigraph.harness_identity", "model": "perigraph.model_identity",
        "artifact": "perigraph.artifact_identity"}


def hop_row(line: dict, hop: str = "vllm") -> dict:
    a = line.get("attributes") or {}
    row = {"format": 1, "hop": hop, "request_id": line.get("request_id", ""), "trace_id": line.get("trace_id", ""),
           "attempt": line.get("record_id", ""), "body_sha256": line.get("body_sha256", ""),
           "status": line.get("status"), "complete": line.get("complete")}
    for k, attr in KEYS.items():
        if a.get(attr):
            row[k] = str(a[attr])
    return row


def main(argv: list[str]) -> int:
    for path in argv:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                if raw.strip():
                    print(json.dumps(hop_row(json.loads(raw)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
