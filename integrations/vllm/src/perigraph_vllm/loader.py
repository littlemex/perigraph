"""The model half, digested by the process that loads the weights, during this load.

vLLM loads weights in its worker processes, not in the API server, so the only collector that may write a model part
as `loaded_by_us` (SPEC section 9) is one running inside the worker's loader. vLLM has a public seam for exactly that:
`register_model_loader`. This module registers a loader named `perigraph`; a server started with
`--load-format perigraph` loads through it, and nothing in vLLM is patched.

The loader is vLLM's `DefaultModelLoader` with two additions:

* it records the weight files `_prepare_weights` hands to the weight iterator, opening each one before the load reads
  it and keeping the file descriptor, so the digest taken afterwards is over the same inode the load read;
* after the load it reads the precision off the parameters and buffers of the module it returns, never off the
  configuration (`auto` is a question, not a precision).

What it does not cover, said here because a model half that hides it would be a confident wrong identity:

* the tokenizer, the chat template and `generation_config.json` are read by the API server process, not by this
  loader, so they are not in `checkpoint`. The label says so;
* LoRA adapters loaded per request bypass the loader. The stamp describes the base model only;
* other load formats (GGUF, bitsandbytes, tensorizer, sharded state) use other loaders and get no stamp.

**One private touchpoint.** `_prepare_weights` is the only place the file list exists, and it is underscore-prefixed.
`check_supported()` pins its signature; on any other shape the loader still loads (it is the default loader) and
writes a stamp that says why it has no model half, rather than guessing. LoRA, tensor and pipeline parallelism get
no model half (see README.md).
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import logging
import json
import os
import socket
import time
from importlib import metadata
from pathlib import Path, PurePosixPath

#: The vLLM versions whose `_prepare_weights` this module was read against. Outside the list nothing is claimed.
TESTED_VLLM = ("0.27.1",)

#: Distributions whose versions make up `runtime`. Declared, as SPEC section 9 requires: a list that misses a library
#: that matters produces a confident wrong identity, and the list is the place to look when that is suspected.
#: The collector's own packages are not here: the record names its collector and version already, and putting them in
#: `runtime` would give every release of this plug-in a new model identity for the same weights.
RUNTIME_DISTRIBUTIONS = ("vllm", "torch", "transformers", "safetensors", "triton", "flashinfer-python")

#: `_prepare_weights` only accepts these, and raises on any other value, so the loader hands its parent a copy of the
#: load config that says `auto`. Read off vllm 0.27.1 default_loader.py.
_PARENT_LOAD_FORMAT = "auto"

_log = logging.getLogger("perigraph_vllm")

_EXPECTED_PARAMS = ("self", "model_name_or_path", "subfolder", "revision", "fall_back_to_pt", "allow_patterns_overrides")

#: What the loaded engine is configured to produce, from vLLM's `model_config.runner_type`, fixed at load.
#: Only `generate`: the middleware records chat completions only, and a pooling runner can be an embedder as well as a
#: classifier, so mapping it would be a guess.
ANSWER_MODES = {"generate": "generated_text"}
LOAD_FORMAT = "perigraph"
START_ENV = "PERIGRAPH_VLLM_START"


def stamp_dir() -> Path:
    """Where stamps and records go. One directory per server, shared by its processes; never inside the model."""
    d = os.environ.get("PERIGRAPH_VLLM_DIR", "")
    if not d:
        raise RuntimeError("PERIGRAPH_VLLM_DIR is not set: perigraph-vllm has nowhere to write, and a stamp nobody can "
                           "find is the same as no stamp")
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


def check_supported(default_loader_cls) -> str:
    """Empty when this vLLM is one the loader was read against, otherwise why not."""
    try:
        version = metadata.version("vllm")
    except metadata.PackageNotFoundError:
        return "vllm is not installed as a distribution, so its version cannot be checked"
    if version not in TESTED_VLLM:
        return f"vllm {version} is not one of {TESTED_VLLM}, the versions _prepare_weights was read against"
    params = tuple(inspect.signature(default_loader_cls._prepare_weights).parameters)
    if params != _EXPECTED_PARAMS:
        return f"DefaultModelLoader._prepare_weights takes {params}, not {_EXPECTED_PARAMS}"
    return ""


def _fence(st: os.stat_result) -> tuple[int, int, int, int, int]:
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


class ReadSet:
    """The weight files a load asked for, each opened before the load reads it.

    Appended per call: `_prepare_weights` runs for `download_model` and once per weight source.
    """

    def __init__(self) -> None:
        self.root: Path | None = None
        self.files: dict[str, tuple[int, tuple, str]] = {}  # rel path -> (fd, fence, absolute path)
        self.problems: list[str] = []

    def add(self, folder: str, paths: list[str]) -> None:
        root = Path(folder)
        if self.root is None:
            self.root = root
        elif root != self.root:
            self.problems.append("weights came from more than one folder, so there is no single artifact root")
            return
        for p in paths:
            rel = PurePosixPath(Path(p).relative_to(root).as_posix()).as_posix()
            if rel in self.files:
                continue
            fd = os.open(p, os.O_RDONLY)
            self.files[rel] = (fd, _fence(os.fstat(fd)), p)

    def digest(self) -> tuple[list[tuple[str, str]], str]:
        """(path, sha256) pairs hashed through the pinned descriptors, or an empty list and why not."""
        out = []
        why = ""
        for rel, (fd, before, path) in sorted(self.files.items()):
            try:
                now = _fence(os.stat(path))
            except OSError as e:
                why = why or f"{rel} could not be stat'ed after the load ({type(e).__name__})"
                continue
            if now != before:
                why = why or f"{rel} is not the inode the load opened (device, inode, size or times changed)"
                continue
            h = hashlib.sha256()
            off = 0
            while True:
                chunk = os.pread(fd, 1 << 22, off)
                if not chunk:
                    break
                h.update(chunk)
                off += len(chunk)
            if _fence(os.fstat(fd)) != before:
                why = why or f"{rel} changed while it was being hashed"
                continue
            out.append((rel, h.hexdigest()))
        return ([] if why else out), why

    def close(self) -> None:
        for fd, _, _ in self.files.values():
            try:
                os.close(fd)
            except OSError:
                pass
        self.files.clear()


def quantisation_of(module) -> str:
    """The quantisation scheme read off the loaded module: the classes of the layers' quantisation methods, with
    vLLM's unquantised methods counting as none. Read off what was built, not off the configuration that asked."""
    names = set()
    for m in module.modules():
        q = getattr(m, "quant_method", None)
        if q is not None:
            n = type(q).__name__
            if not n.startswith("Unquantized"):
                names.add(n)
    return ",".join(sorted(names)) or "none"


def tensor_precision(module, quantisation: str) -> dict[str, str]:
    """`dtype.<name>` element counts over every parameter and buffer, the quantisation scheme, and the device."""
    counts: dict[str, int] = {}
    devices: set[str] = set()
    for t in list(module.parameters()) + list(module.buffers()):
        name = str(t.dtype).replace("torch.", "")
        counts[f"dtype.{name}"] = counts.get(f"dtype.{name}", 0) + t.numel()
        devices.add(t.device.type)
    if not counts:
        raise ValueError("the loaded module has no parameters or buffers")
    if len(devices) != 1:
        raise ValueError(f"parameters sit on {sorted(devices)}; one device per model is what this part can say")
    return {**{k: str(v) for k, v in counts.items()}, "quantisation": quantisation or "none", "device": devices.pop()}


def runtime_versions() -> dict[str, str]:
    out = {}
    for d in RUNTIME_DISTRIBUTIONS:
        try:
            out[d] = metadata.version(d)
        except metadata.PackageNotFoundError:
            continue
    return out


def build_stamp(read_set: ReadSet, module, vllm_config, unsupported: str) -> dict:
    """The stamp one process writes after one load. Every field is computed here or the half is absent with a reason."""
    from perigraph.model import checkpoint_digest, precision_digest, runtime_digest

    rank, world = _rank_and_world(vllm_config)
    stamp = {"format": 1, "pid": os.getpid(), "loaded_at_ns": time.time_ns(), "rank": rank, "world_size": world,
             "start_id": os.environ.get(START_ENV, "")}
    if unsupported:
        stamp["absent"] = unsupported
        return stamp
    if not hasattr(vllm_config, "lora_config"):
        stamp["absent"] = "this vLLM's config has no lora_config, so whether adapters are on cannot be checked"
        return stamp
    if vllm_config.lora_config is not None:
        # An answer through an adapter is not an answer from these weights, and adapters bypass this loader.
        stamp["absent"] = "LoRA is enabled, and adapters loaded per request are not in this stamp"
        return stamp
    mode = ANSWER_MODES.get(str(getattr(getattr(vllm_config, "model_config", None), "runner_type", "")))
    if mode is None:
        stamp["absent"] = "the engine's runner type is not one this loader maps to an answer mode"
        return stamp
    stamp["answer_mode"] = mode
    entries, why = read_set.digest()
    if why or read_set.problems:
        stamp["absent"] = why or read_set.problems[0]
        return stamp
    try:
        fields = tensor_precision(module, quantisation_of(module))
        stamp["checkpoint"] = checkpoint_digest(entries)
        stamp["checkpoint_files"] = len(entries)
        stamp["precision"] = precision_digest(fields)
        stamp["precision_label"] = ",".join(f"{k}={v}" for k, v in sorted(fields.items()))
        versions = runtime_versions()
        stamp["runtime"] = runtime_digest(versions)
        stamp["runtime_label"] = ",".join(f"{k}=={v}" for k, v in sorted(versions.items()))
    except Exception as e:  # a stamp that cannot be computed is an absence, never a failed load
        stamp = {k: stamp[k] for k in ("format", "pid", "loaded_at_ns", "rank", "world_size", "start_id")}
        stamp["absent"] = f"{type(e).__name__}: {e}"
    return stamp


def _rank_and_world(vllm_config) -> tuple[int, int]:
    """This worker's rank among the processes holding the model, and how many there are."""
    world = int(getattr(getattr(vllm_config, "parallel_config", None), "world_size", 1) or 1)
    rank = 0
    try:
        import torch.distributed as dist
        if dist.is_available() and dist.is_initialized():
            rank = dist.get_rank()
    except ImportError:
        pass
    return rank, world


def write_stamp(stamp: dict) -> Path:
    path = stamp_dir() / f"model-{socket.gethostname()}-{stamp['pid']}-{stamp['loaded_at_ns']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(stamp, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)
    return path


def make_loader_class(default_loader_cls):
    """Build the subclass against the DefaultModelLoader actually installed (kept out of import time so this module
    imports without vLLM, for tests and for the API server process)."""
    unsupported = check_supported(default_loader_cls)

    class PerigraphModelLoader(default_loader_cls):
        def __init__(self, load_config):
            stamp_dir()  # fail before a load that takes minutes, not after it
            parent = copy.copy(load_config)
            parent.load_format = _PARENT_LOAD_FORMAT
            super().__init__(parent)
            self._perigraph_reads = ReadSet()

        def _prepare_weights(self, *args, **kwargs):
            result = super()._prepare_weights(*args, **kwargs)
            if unsupported:
                return result
            try:
                folder, files, use_safetensors = result
                self._perigraph_reads.add(folder, list(files))
                if not use_safetensors:
                    self._perigraph_reads.problems.append("weights are not safetensors; pickle checkpoints get no stamp")
            except Exception as e:  # instrumentation never changes what the parent returns
                self._perigraph_reads.problems.append(f"the weight list could not be read ({type(e).__name__})")
            return result

        def load_model(self, vllm_config, model_config, prefix: str = ""):
            model = super().load_model(vllm_config, model_config, prefix=prefix)
            try:
                write_stamp(build_stamp(self._perigraph_reads, model, vllm_config, unsupported))
            except Exception:  # a load that succeeded is never failed by its stamp
                _log.exception("perigraph: no stamp was written for this load")
            finally:
                self._perigraph_reads.close()
            return model

    PerigraphModelLoader.__name__ = "PerigraphModelLoader"
    return PerigraphModelLoader
