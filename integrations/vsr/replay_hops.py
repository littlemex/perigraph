"""Turn vLLM Semantic Router replay records into hop rows, with no change to the router.

The router's own `router_replay` plugin keeps, for every primary dispatch, the sha256 and length of the exact bytes
it sent to the backend (`route_diagnostics.prepared_dispatch`). That digest, compared with the one the backend's
collector took over the bytes it received, shows both hops held the same request -- or that something between them
changed it. The router states no identity, so the row has none.

    python replay_hops.py replay-*.json > vsr-hops.jsonl

Each input file is one record from `GET /api/v1/observability/replays/{id}` (or a JSON list of them). Records with
no `prepared_dispatch` (a cache hit, a Looper attempt, a fallback attempt) become rows with no digest, which a
receiver refuses to bind: the router's single-dispatch receipt does not describe them.
"""
from __future__ import annotations

import json
import sys


def hop_row(rec: dict) -> dict:
    pd = (rec.get("route_diagnostics") or {}).get("prepared_dispatch") or {}
    return {"format": 1, "hop": "vsr", "request_id": rec.get("request_id", ""), "attempt": rec.get("id", ""),
            "body_sha256": pd.get("sha256", ""), "body_bytes": pd.get("byte_length")}


def main(argv: list[str]) -> int:
    for path in argv:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for rec in data if isinstance(data, list) else [data]:
            print(json.dumps(hop_row(rec), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
