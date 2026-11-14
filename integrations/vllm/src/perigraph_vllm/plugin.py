"""The `vllm.general_plugins` entry point. vLLM calls it in every process it starts, possibly more than once."""
from __future__ import annotations

import os
import socket
import time

from perigraph_vllm.loader import START_ENV

_registered = False
#: When this process first ran the plug-in. In the API server that is before any worker loads, so a stamp loaded
#: earlier than this is from another start, whatever its start marker says.
STARTED_NS = 0


def register() -> None:
    """Mark this server start and register the `perigraph` loader. Idempotent, and silent when vLLM is absent.

    The start marker is set in the first process (the API server) before it spawns the engine and the workers, which
    inherit it; a worker's stamp carries it, so the middleware can tell this start's stamps from an earlier start's.
    """
    global _registered, STARTED_NS
    if not STARTED_NS:
        STARTED_NS = time.time_ns()
    os.environ.setdefault(START_ENV, f"{socket.gethostname()}-{os.getpid()}-{STARTED_NS}")
    if _registered:
        return
    try:
        from vllm.model_executor.model_loader import register_model_loader
        from vllm.model_executor.model_loader.default_loader import DefaultModelLoader
    except ImportError:
        return
    from perigraph_vllm.loader import LOAD_FORMAT, make_loader_class

    register_model_loader(LOAD_FORMAT)(make_loader_class(DefaultModelLoader))
    _registered = True
