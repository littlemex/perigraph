"""The harness half, read from the exact bytes the server received, and the record that joins it to the model half.

Loaded with `vllm serve ... --middleware perigraph_vllm.Middleware`. A pure ASGI class, not `BaseHTTPMiddleware`:
the body is read once from `receive`, digested, and replayed to vLLM unchanged, and the response is passed through
frame by frame, so streaming and client disconnects behave exactly as without it. It reads, it never rewrites.

What one record holds, written as one JSON line to `$PERIGRAPH_VLLM_DIR/records-<host>-<pid>.jsonl`:

| field | what it is |
|---|---|
| `record_id` | minted here, one per request this server received; the only value put on the response (`x-perigraph-record`) |
| `request_id`, `trace_id` | the `x-request-id` header and the trace id of `traceparent`, as received, for joining with other hops |
| `body_sha256`, `body_bytes` | over the bytes as received. Never a join key (two requests may send the same body); a check across hops |
| `status`, `complete` | the response status this server sent, and whether the last body frame was sent (a stream cut after the 200 is not complete) |
| `attributes` | the perigraph record (`perigraph.to_attributes`): harness half from the body, model half relayed from the stamps |

The identities are not put in response headers by default. A harness identity is a confirmation oracle for any
system text a router injected (SPEC 12.2), and the model identity fingerprints the runtime; set
`PERIGRAPH_VLLM_IDENTITY_HEADERS=1` only when every caller is inside the trust domain.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import socket
import threading
import time
import uuid
from pathlib import Path

from perigraph_vllm import __version__
from perigraph_vllm.loader import START_ENV, stamp_dir

COLLECTOR = "github.com/littlemex/perigraph/integrations/vllm"
PATHS = ("/v1/chat/completions",)
RECORD_HEADER = b"x-perigraph-record"
#: While the model half is missing, the stamp directory is read again at most this often, not on every request.
RESCAN_SECONDS = 5.0


def _trace_id(traceparent: str) -> str:
    parts = traceparent.split("-")
    if len(parts) >= 4 and len(parts[1]) == 32:
        return parts[1]
    return ""


def model_half(directory: Path, start_id: str, started_ns: int):
    """The model half this server's workers stamped during this start, relayed verbatim, or why there is none.

    A stamp counts only if it carries this start's marker and was loaded after this process started: a stamp left in
    the directory by an earlier start describes a load that is not the one answering. Every rank 0..n-1 must have
    stamped exactly once, and all stamps must agree.
    """
    from perigraph.model import Model, ModelAbsence, loaded
    from perigraph.vocab import MODEL_PARTS

    def absent(why: str) -> Model:
        return Model(absences=tuple(ModelAbsence(kind=k, reason="extraction_failed", detail=why) for k in MODEL_PARTS),
                     reaches=MODEL_PARTS)

    stamps = []
    for p in sorted(directory.glob("model-*.json")):
        try:
            with open(p, encoding="utf-8") as f:
                s = json.load(f)
            if not isinstance(s, dict):
                continue
            ours = s.get("start_id") == start_id and int(s.get("loaded_at_ns", 0)) >= started_ns
        except (OSError, ValueError, TypeError):
            continue
        if ours:
            stamps.append(s)
    if not stamps:
        return absent("no worker has stamped during this start"), False
    world = int(stamps[0].get("world_size", 1))
    try:
        world = int(world)
        ranks = sorted(int(s.get("rank", -1)) for s in stamps)
    except (ValueError, TypeError):
        return absent("a stamp's rank or world size is not a number"), True
    if ranks != list(range(world)):
        return absent(f"stamps from ranks {ranks}, expected one from each of 0..{world - 1}"), False
    for s in stamps:
        if "absent" in s:
            return absent(f"a worker could not stamp: {s['absent']}"), True
    keys = ("checkpoint", "precision", "runtime", "answer_mode")
    try:
        if len({tuple(s[k] for k in keys) for s in stamps}) != 1:
            return absent("the workers' stamps disagree (with tensor or pipeline parallelism each holds a shard)"), True
        s = stamps[0]
        labels = {"checkpoint": f"{s['checkpoint_files']} weight files read by the loader; tokenizer, chat template "
                                f"and generation_config not included",
                  "precision": s["precision_label"], "runtime": s["runtime_label"]}
        return loaded(checkpoint=s["checkpoint"], precision=s["precision"], runtime=s["runtime"],
                      answer_mode=s["answer_mode"], labels=labels), True
    except (KeyError, ValueError, TypeError) as e:
        return absent(f"a stamp is malformed ({type(e).__name__})"), True


def _absent_model(why: str):
    from perigraph.model import Model, ModelAbsence
    from perigraph.vocab import MODEL_PARTS
    return Model(absences=tuple(ModelAbsence(kind=k, reason="extraction_failed", detail=why[:200]) for k in MODEL_PARTS),
                 reaches=MODEL_PARTS)


class Middleware:
    def __init__(self, app):
        from perigraph_vllm import plugin

        self.app = app
        self.dir = stamp_dir()
        self.start_id = os.environ.get(START_ENV, "")
        self.started_ns = plugin.STARTED_NS
        self.identity_headers = os.environ.get("PERIGRAPH_VLLM_IDENTITY_HEADERS") == "1"
        self._model = None  # cached once final: a model half, or an absence that will not change in this start
        self._next_scan = 0.0
        self._pending = None
        self.out = self.dir / f"records-{socket.gethostname()}-{os.getpid()}.jsonl"
        self._fd = None
        self._lock = threading.Lock()

    def _model_half(self):
        if self._model is not None:
            return self._model
        now = time.monotonic()
        if self._pending is None or now >= self._next_scan:
            self._next_scan = now + RESCAN_SECONDS
            m, final = model_half(self.dir, self.start_id, self.started_ns)
            if final:
                self._model = m
            self._pending = m
        return self._pending

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") != "POST" or scope.get("path") not in PATHS:
            await self.app(scope, receive, send)
            return
        chunks = []
        more = True
        while more:
            msg = await receive()
            if msg["type"] == "http.disconnect":
                # Nothing to replay: the client left before the body arrived. vLLM sees the same disconnect.
                async def gone():
                    return msg
                await self.app(scope, gone, send)
                return
            chunks.append(msg.get("body", b""))
            more = msg.get("more_body", False)
        body = b"".join(chunks)
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        row = {"format": 1, "record_id": uuid.uuid4().hex, "received_at": time.time(),
               "request_id": headers.get("x-request-id", ""), "trace_id": _trace_id(headers.get("traceparent", "")),
               "path": scope["path"], "body_sha256": hashlib.sha256(body).hexdigest(), "body_bytes": len(body)}
        self._record(body, row)
        state = {"status": None, "complete": False}

        async def wrapped_send(msg):
            if msg["type"] == "http.response.start":
                state["status"] = msg.get("status")
                extra = [(RECORD_HEADER, row["record_id"].encode())]
                if self.identity_headers:
                    attrs = row.get("attributes", {})
                    for k in ("perigraph.harness_identity", "perigraph.model_identity", "perigraph.artifact_identity"):
                        if k in attrs:
                            extra.append((("x-" + k.replace(".", "-").replace("_", "-")).encode(), str(attrs[k]).encode()))
                msg = dict(msg)
                msg["headers"] = list(msg.get("headers", [])) + extra
            await send(msg)
            if msg["type"] == "http.response.body" and not msg.get("more_body", False):
                state["complete"] = True

        try:
            await self.app(scope, replay, wrapped_send)
        finally:
            row["status"] = state["status"]
            row["complete"] = state["complete"]
            await asyncio.to_thread(self._write, row)

    def _record(self, body: bytes, row: dict) -> None:
        """Never raises: a record that cannot be made is written as a row that says why, and the request proceeds.
        The two halves fail separately, so a bad stamp never costs the harness half."""
        try:
            from perigraph import from_request, to_attributes
            try:
                parsed = json.loads(body)
            except ValueError:
                parsed = body.decode("utf-8", "replace")  # from_request names a non-object body as extraction_failed
            record = from_request(parsed, collector=COLLECTOR, version=__version__)
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
            return
        harness_only = record
        try:
            record = dataclasses.replace(record, model=self._model_half())
        except Exception as e:
            row["model_error"] = f"{type(e).__name__}: {e}"
            record = dataclasses.replace(record, model=_absent_model(row["model_error"]))
        for candidate in (record, harness_only):
            try:
                row["attributes"] = to_attributes(candidate)
                return
            except Exception as e:
                row["model_error"] = f"{type(e).__name__}: {e}"
        row.pop("attributes", None)
        row["error"] = row.pop("model_error")

    def _write(self, row: dict) -> None:
        line = (json.dumps(row, sort_keys=True) + "\n").encode("utf-8")
        with self._lock:
            if self._fd is None:
                self._fd = os.open(self.out, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            os.write(self._fd, line)
