"""perigraph records from a stock vLLM server, through vLLM's public plug-in seams and nothing else.

* `vllm.general_plugins` entry `perigraph` -> `register()`: registers the `perigraph` model loader in every process.
* `--load-format perigraph`: the workers load through it and stamp the model half (`loader.py`).
* `--middleware perigraph_vllm.Middleware`: the API server records the harness half per request (`middleware.py`).
"""
__version__ = "0.1.0"


def __getattr__(name):
    if name == "Middleware":
        from perigraph_vllm.middleware import Middleware
        return Middleware
    raise AttributeError(name)
