"""Unit tests without vLLM or torch: the loader against a stand-in DefaultModelLoader, the middleware against a
stand-in ASGI app. The real-machine check (a stock vLLM 0.27.1 started with the plug-in) is in README.md."""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import pathlib
from pathlib import Path

import pytest

from perigraph_vllm import loader as L
from perigraph_vllm import middleware as M


class FakeDtype:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return f"torch.{self.name}"


class FakeTensor:
    def __init__(self, dtype, n, device="cuda"):
        self.dtype, self._n = FakeDtype(dtype), n
        self.device = type("D", (), {"type": device})()

    def numel(self):
        return self._n


class FakeModule:
    def __init__(self, params, buffers=()):
        self._p, self._b = list(params), list(buffers)

    def parameters(self):
        return iter(self._p)

    def buffers(self):
        return iter(self._b)

    def modules(self):
        return iter([self] + list(getattr(self, "children_", [])))


class LoadConfig:
    def __init__(self, load_format):
        self.load_format = load_format


def fake_default_loader(folder: Path, files: list[Path], seen: dict):
    class DefaultModelLoader:
        def __init__(self, load_config):
            seen["parent_format"] = load_config.load_format
            self.load_config = load_config

        def _prepare_weights(self, model_name_or_path, subfolder, revision, fall_back_to_pt,
                             allow_patterns_overrides):
            return str(folder), [str(f) for f in files], True

        def load_model(self, vllm_config, model_config, prefix=""):
            self._prepare_weights("m", None, None, True, None)
            if seen.get("swap"):
                seen["swap"]()
            m = FakeModule([FakeTensor("bfloat16", 10), FakeTensor("float32", 2)])
            if seen.get("quant"):
                m.quant_method = type(seen["quant"], (), {})()
            return m
    return DefaultModelLoader


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PERIGRAPH_VLLM_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("PERIGRAPH_VLLM_START", "e1")
    monkeypatch.setattr(L.metadata, "version", lambda d: {"vllm": "0.27.1"}.get(d, "1.0"))
    art = tmp_path / "art"
    art.mkdir()
    files = []
    for name, data in (("model-00001.safetensors", b"aa"), ("model-00002.safetensors", b"bbb")):
        (art / name).write_bytes(data)
        files.append(art / name)
    (art / "unread.bin").write_bytes(b"decoy")
    return tmp_path, art, files


def vllm_config(runner="generate", world=1, lora=None, has_lora=True):
    ns = lambda **kw: type("NS", (), kw)()  # noqa: E731
    kw = dict(model_config=ns(runner_type=runner), parallel_config=ns(world_size=world))
    if has_lora:
        kw["lora_config"] = lora
    return ns(**kw)


def load_once(art, files, seen, cfg=None):
    cls = L.make_loader_class(fake_default_loader(art, files, seen))
    cls(LoadConfig("perigraph")).load_model(cfg or vllm_config(), None)
    out = Path(os.environ["PERIGRAPH_VLLM_DIR"])
    return [json.loads(p.read_text()) for p in sorted(out.glob("model-*.json"))]


def test_parent_sees_auto_and_stamp_covers_only_the_files_read(env):
    _, art, files = env
    seen = {}
    [stamp] = load_once(art, files, seen)
    assert seen["parent_format"] == "auto"
    from perigraph.model import checkpoint_digest
    want = checkpoint_digest([(f.name, hashlib.sha256(f.read_bytes()).hexdigest()) for f in files])
    assert stamp["checkpoint"] == want and stamp["checkpoint_files"] == 2 and stamp["start_id"] == "e1"
    assert stamp["answer_mode"] == "generated_text" and "perigraph" not in stamp["runtime_label"]
    assert "dtype.bfloat16=10" in stamp["precision_label"] and "quantisation=none" in stamp["precision_label"]


def test_a_decoy_file_does_not_change_the_checkpoint(env):
    _, art, files = env
    [a] = load_once(art, files, {})
    (art / "unread.bin").write_bytes(b"changed decoy")
    for p in Path(os.environ["PERIGRAPH_VLLM_DIR"]).glob("model-*.json"):
        p.unlink()
    [b] = load_once(art, files, {})
    assert a["checkpoint"] == b["checkpoint"]


def test_a_file_replaced_during_the_load_withdraws_the_stamp(env):
    _, art, files = env

    def swap():
        tmp = art / "x.tmp"
        tmp.write_bytes(b"other")
        os.replace(tmp, files[0])
    [stamp] = load_once(art, files, {"swap": swap})
    assert "checkpoint" not in stamp and "not the inode the load opened" in stamp["absent"]


def test_an_untested_vllm_claims_nothing(env, monkeypatch):
    _, art, files = env
    monkeypatch.setattr(L.metadata, "version", lambda d: "9.9.9")
    [stamp] = load_once(art, files, {})
    assert "checkpoint" not in stamp and "9.9.9" in stamp["absent"]


def test_signature_pin_matches_the_stand_in():
    params = tuple(inspect.signature(fake_default_loader(Path("."), [], {})._prepare_weights).parameters)
    assert params == L._EXPECTED_PARAMS


def test_mixed_devices_are_an_absence():
    with pytest.raises(ValueError):
        L.tensor_precision(FakeModule([FakeTensor("bfloat16", 1, "cuda"), FakeTensor("bfloat16", 1, "cpu")]), "none")


# --- middleware ------------------------------------------------------------------------------------------------------

def run_app(mw, body: bytes, headers=()):
    sent = []
    got = {}

    async def app(scope, receive, send):
        msg = await receive()
        got["body"] = msg["body"]
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b"{}", "more_body": False})

    mw.app = app
    pieces = [body[: len(body) // 2], body[len(body) // 2:]]  # the body arrives in two frames
    queue = [{"type": "http.request", "body": p, "more_body": i < len(pieces) - 1} for i, p in enumerate(pieces)]

    async def receive():
        return queue.pop(0)

    async def send(m):
        sent.append(m)

    scope = {"type": "http", "method": "POST", "path": "/v1/chat/completions",
             "headers": [(k.encode(), v.encode()) for k, v in headers]}
    asyncio.run(mw(scope, receive, send))
    return got, sent


BODY = {"model": "m", "messages": [{"role": "system", "content": "Answer briefly."},
                                   {"role": "user", "content": "hi"}], "temperature": 0}


def test_middleware_replays_the_body_unchanged_and_records_it(env):
    tmp, art, files = env
    load_once(art, files, {})
    raw = json.dumps(BODY).encode()
    mw = M.Middleware(None)
    got, sent = run_app(mw, raw, headers=[("x-request-id", "r1"),
                                          ("traceparent", "00-" + "a" * 32 + "-" + "b" * 16 + "-01")])
    assert got["body"] == raw
    hdrs = dict(sent[0]["headers"])
    assert set(hdrs) == {b"content-type", M.RECORD_HEADER}
    [row] = [json.loads(line) for line in mw.out.read_text().splitlines()]
    assert row["body_sha256"] == hashlib.sha256(raw).hexdigest() and row["request_id"] == "r1"
    assert row["trace_id"] == "a" * 32 and row["status"] == 200
    assert hdrs[M.RECORD_HEADER].decode() == row["record_id"]
    a = row["attributes"]
    from perigraph import from_request
    assert a["perigraph.harness_identity"] == from_request(BODY, collector="x", version="1").identity
    assert "perigraph.model_identity" in a and "perigraph.artifact_identity" in a


def test_stamps_from_an_earlier_start_are_not_relayed(env, monkeypatch):
    tmp, art, files = env
    load_once(art, files, {})
    monkeypatch.setenv("PERIGRAPH_VLLM_START", "e2")
    mw = M.Middleware(None)
    run_app(mw, json.dumps(BODY).encode())
    [row] = [json.loads(line) for line in mw.out.read_text().splitlines()]
    assert "perigraph.model_identity" not in row["attributes"]
    assert "no worker has stamped during this start" in json.dumps(row["attributes"])


def test_two_ranks_must_both_stamp(env, monkeypatch):
    tmp, art, files = env
    load_once(art, files, {}, vllm_config(world=2))
    mw = M.Middleware(None)
    run_app(mw, json.dumps(BODY).encode())
    [row] = [json.loads(line) for line in mw.out.read_text().splitlines()]
    assert "perigraph.model_identity" not in row["attributes"]


def test_a_body_that_is_not_json_still_reaches_vllm(env):
    mw = M.Middleware(None)
    got, sent = run_app(mw, b"not json")
    assert got["body"] == b"not json" and sent[0]["status"] == 200
    [row] = [json.loads(line) for line in mw.out.read_text().splitlines()]
    assert "perigraph.harness_identity" not in row.get("attributes", {})


def test_other_paths_are_untouched(env):
    mw = M.Middleware(None)
    called = {}

    async def app(scope, receive, send):
        called["yes"] = True
    mw.app = app
    asyncio.run(mw({"type": "http", "method": "GET", "path": "/health", "headers": []}, None, None))
    assert called and not mw.out.exists()


def test_hop_rows_carry_only_strings_and_say_nothing_when_there_is_no_record():
    from perigraph_vllm.hops import hop_row
    line = {"record_id": "a", "request_id": "q", "trace_id": "t", "body_sha256": "s", "status": 200, "complete": True,
            "attributes": {"perigraph.harness_identity": "H", "perigraph.model_identity": "M"}}
    assert hop_row(line) == {"format": 1, "hop": "vllm", "request_id": "q", "trace_id": "t", "attempt": "a",
                             "body_sha256": "s", "status": 200, "complete": True, "harness": "H", "model": "M"}
    assert "harness" not in hop_row({"request_id": "q", "error": "x"})


def test_quantisation_is_read_off_the_module_not_the_configuration(env):
    _, art, files = env
    [stamp] = load_once(art, files, {"quant": "Fp8LinearMethod"})
    assert "quantisation=Fp8LinearMethod" in stamp["precision_label"]


def test_lora_withdraws_the_model_half(env):
    _, art, files = env
    [stamp] = load_once(art, files, {}, vllm_config(lora=object()))
    assert "checkpoint" not in stamp and "LoRA" in stamp["absent"]


def test_a_stamp_from_before_this_process_started_is_not_relayed(env, monkeypatch):
    _, art, files = env
    load_once(art, files, {})
    from perigraph_vllm import plugin
    monkeypatch.setattr(plugin, "STARTED_NS", 2**62)
    mw = M.Middleware(None)
    run_app(mw, json.dumps(BODY).encode())
    [row] = [json.loads(line) for line in mw.out.read_text().splitlines()]
    assert "perigraph.model_identity" not in row["attributes"] and row["complete"] is True


def test_a_malformed_stamp_costs_the_model_half_only(env):
    tmp, art, files = env
    load_once(art, files, {})
    for p in pathlib.Path(os.environ["PERIGRAPH_VLLM_DIR"]).glob("model-*.json"):
        s = json.loads(p.read_text()); s.pop("checkpoint_files"); p.write_text(json.dumps(s))
    mw = M.Middleware(None)
    run_app(mw, json.dumps(BODY).encode())
    [row] = [json.loads(line) for line in mw.out.read_text().splitlines()]
    assert "perigraph.harness_identity" in row["attributes"] and "perigraph.model_identity" not in row["attributes"]


def test_a_stream_cut_after_the_status_is_not_complete(env):
    mw = M.Middleware(None)

    async def app(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"data: x", "more_body": True})
        raise ConnectionError("client went away")
    mw.app = app
    queue = [{"type": "http.request", "body": json.dumps(BODY).encode(), "more_body": False}]

    async def receive():
        return queue.pop(0)

    async def send(m):
        pass
    with pytest.raises(ConnectionError):
        asyncio.run(mw({"type": "http", "method": "POST", "path": "/v1/chat/completions", "headers": []}, receive, send))
    [row] = [json.loads(line) for line in mw.out.read_text().splitlines()]
    assert row["status"] == 200 and row["complete"] is False


def test_a_config_without_lora_config_fails_closed(env):
    _, art, files = env
    [stamp] = load_once(art, files, {}, vllm_config(has_lora=False))
    assert "checkpoint" not in stamp and "lora_config" in stamp["absent"]


def test_a_pooling_runner_gets_no_answer_mode(env):
    _, art, files = env
    [stamp] = load_once(art, files, {}, vllm_config(runner="pooling"))
    assert "checkpoint" not in stamp and "runner type" in stamp["absent"]


def test_junk_in_the_stamp_directory_is_skipped(env):
    tmp, art, files = env
    load_once(art, files, {})
    d = pathlib.Path(os.environ["PERIGRAPH_VLLM_DIR"])
    (d / "model-junk-1.json").write_text("[1, 2]")
    (d / "model-junk-2.json").write_text(json.dumps({"start_id": "e1", "loaded_at_ns": "soon"}))
    mw = M.Middleware(None)
    run_app(mw, json.dumps(BODY).encode())
    [row] = [json.loads(line) for line in mw.out.read_text().splitlines()]
    assert "perigraph.model_identity" in row["attributes"]
