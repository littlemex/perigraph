# vLLM Semantic Router: no collector, one adapter

The router needs no perigraph code. Its own `router_replay` plugin keeps, for every primary dispatch, the sha256 and the length of the exact bytes it sent to the backend (`route_diagnostics.prepared_dispatch`). A collector at the backend, such as `integrations/vllm`, digests the bytes it received. When the two digests are equal, the backend's record describes the request the router sent; when they differ, something between them changed it.

`replay_hops.py` turns replay records into hop rows for a receiver that joins by request id, such as `tierbook bind`:

```bash
python replay_hops.py replay-*.json > vsr-hops.jsonl
```

Each input is one record from the router's `GET /api/v1/observability/replays/{id}`. The router serves that API on `127.0.0.1:8080` inside its pod, so it is read from inside the pod, for example with `kubectl exec`.

| the router does | consequence for a record |
|---|---|
| rewrites `max_tokens` to `max_completion_tokens` | the backend's `generation_controls` digest, and so its harness identity, differs from a direct request with the same text. The backend reads both members as the same limit |
| adds or replaces a system message (a decision's `system_prompt` plugin) | the backend's `instruction` digest is over the text the router sent, which is the text the model read |
| rejects request members it does not know, including `perigraph_template` | a request that sends a template through the router gets HTTP 400. Send none on routes through the router; `request_template` is then `not_provided` |
| keeps no `prepared_dispatch` for cache hits, Looper calls and fallback attempts | the hop row has no digest, and a receiver refuses to bind it |
| keeps replay records in memory by default | they are lost when its configuration reloads; read them before changing the configuration |

Configuration used for the check (router at upstream commit `8396cbbe`, image `ghcr.io/vllm-project/semantic-router/vllm-sr:8396cbbec54dc4a4d83cdc249c197f2b73579071`):

```yaml
plugins:
  - type: router_replay
    configuration:
      enabled: true
      prompt_capture: none
```
