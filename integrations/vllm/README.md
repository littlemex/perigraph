# perigraph-vllm

perigraph records from a stock vLLM server, through vLLM's public plug-in seams. Nothing in vLLM is patched.

| record half | where it is collected | vLLM seam | sourcing |
|---|---|---|---|
| model: `checkpoint`, `precision`, `runtime`, `answer_mode` | each worker, inside its model loader, during the load | `vllm.general_plugins` entry point and `register_model_loader`, selected with `--load-format perigraph` | `loaded_by_us` |
| harness: `instruction`, `request_template`, `tool_schemas`, `generation_controls`, `decoding` | the API server, from the bytes it received | `--middleware perigraph_vllm.Middleware` | `in_the_request` |

The two halves meet in one record per request, written as one JSON line. The response carries one opaque header, `x-perigraph-record`, so a caller can name the record without learning what is in it.

## Install and run

```bash
git clone https://github.com/littlemex/perigraph && cd perigraph
pip install . ./integrations/vllm
export PERIGRAPH_VLLM_DIR=/var/lib/perigraph
vllm serve Qwen/Qwen3.5-0.8B --load-format perigraph --middleware perigraph_vllm.Middleware
```

`PERIGRAPH_VLLM_DIR` must be writable by every process of the server. Each worker writes `model-<host>-<pid>-<load>.json` after its load, and each API server process appends to `records-<host>-<pid>.jsonl`. A record carries a model half only when every worker of this start (ranks 0 to the world size minus one) stamped after this API server process started, and the stamps agree.

## What one record line holds

| field | meaning |
|---|---|
| `record_id` | minted per request received; the value of the `x-perigraph-record` response header |
| `request_id` | the `x-request-id` request header as received |
| `trace_id` | the trace id of the `traceparent` request header as received |
| `body_sha256`, `body_bytes` | over the request body as received. A check that two hops saw the same bytes, never a join key, since two requests can send the same body |
| `status`, `complete` | the response status, and whether the last body frame was sent; a stream cut after a 200 is not complete |
| `attributes` | the perigraph record, flattened with `perigraph.to_attributes` |
| `error` | present instead of `attributes` when no record could be made; the request is unaffected |

## What the model half covers, and what it does not

The model half is computed by a subclass of vLLM's `DefaultModelLoader`. It opens each weight file the loader is given before the load reads it, keeps the descriptor, and after the load hashes the file through that descriptor, refusing if the path no longer names the same inode, size and times. Precision is read off the parameters and buffers of the loaded module.

| not covered | why | what the record says |
|---|---|---|
| tokenizer, chat template, `generation_config.json` | the API server reads them, not the loader | the `checkpoint` label says they are not included |
| what the server applies on its own: `--chat-template`, `--default-chat-template-kwargs`, `--override-generation-config`, the sampling defaults vLLM reads from `generation_config.json` | they are not in the request and not read by the loader | nothing. Two servers that differ only here get equal identities, which merges runs that were not the same (SPEC 2.1) |
| LoRA | adapters load per request and bypass the loader | the model half is absent, with the reason, whenever LoRA is enabled |
| tensor or pipeline parallelism | each worker holds a shard, so the workers' stamps disagree | the model half is absent, with the reason. Untested on more than one GPU |
| more than one API server process (`--api-server-count` above 1) | a stamp counts only if loaded after the API process that reads it started, and a process started after the load rejects it | the model half is absent in that process. Untested |
| other load formats (GGUF, bitsandbytes, tensorizer) | they use other loaders | no stamp |
| a vLLM version other than the tested ones, or a changed `_prepare_weights` signature | the file list comes from that one underscore-prefixed method | the model half is absent, with the reason |
| non-safetensors weights | pickle checkpoints are not stamped | the model half is absent, with the reason |

## Privacy

Only the record id goes on the response. A harness identity lets anyone who knows a candidate instruction confirm it was used, including system text a router added, and a model identity fingerprints the runtime (SPEC section 12.2). Set `PERIGRAPH_VLLM_IDENTITY_HEADERS=1` to also return `x-perigraph-harness-identity`, `x-perigraph-model-identity` and `x-perigraph-artifact-identity` when every caller is inside the trust domain. The request body never leaves the process; only its digests are written.

## Checked on a real server

On one NVIDIA L40S, with vLLM 0.27.1 and `Qwen/Qwen3.5-0.8B`, the plug-in installed with `pip install --target` beside an existing vLLM and put on `PYTHONPATH` (not yet from a built image):

| check | result |
|---|---|
| the entry point loads in the API server and the engine process, and `--load-format perigraph` selects the loader | both processes logged the registration; one stamp was written |
| the checkpoint digest | equal to one computed independently over the sha256 of the one weight file |
| the same 20 prompts at temperature 0 with `--load-format auto` and no middleware | 20 of 20 answers identical |
| a restart | the same model identity, new record ids |
| through vLLM Semantic Router `8396cbbe` (stock image), second run after the review fixes | 40 of 40 router `prepared_dispatch.sha256` equal to this middleware's `body_sha256`; `x-request-id` reached vLLM, and all 20 routed callers received `x-perigraph-record` |
| `tierbook bind` over the records | 60 calls bound, each pinned to the vLLM attempt named by its `x-perigraph-record`; refusals fired for a deleted record, an edited digest, a duplicated attempt and two harnesses in one arm |

## Tests

```bash
PYTHONPATH=src:../../src python -m pytest tests -q
```

The unit tests run without vLLM or torch, against stand-ins for the loader and the ASGI app.
