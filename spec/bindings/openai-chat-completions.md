# Binding: OpenAI Chat Completions request bodies

Normative for a collector that reads a request body in the OpenAI Chat Completions shape (SPEC section 0.2). It says which field each part is read from. How a part is digested, and what an unreadable field becomes, is in SPEC sections 1.2 and 2.2; this document does not restate those rules.

## Field to part

| part | read from | boundary | identifying |
|---|---|---|---|
| `instruction` | the `content` of every message whose `role` is `system`, joined with U+000A in message order (SPEC 2.2) | `model_visible` | yes |
| `tool_schemas` | `tools`: for each entry, the function's `name` and `parameters`, ordered by their rendering | `parsed` | no |
| `readout` | `response_format` | `parsed` | no |
| `decoding` | `temperature`, `top_p`, `top_k` and `seed` when present and not `null`, in that order, then `response_format` | `parsed` | no |
| `loop`, `turn_budget`, `retry_policy`, `context_partitioning` | nothing: a request body has no field for them | -- | absent, `not_provided` |
| `tool_extension` | nothing: what a tool does is not in any request | -- | absent, `not_observable` |
| `tool_trace` | nothing: at request time no call has happened | -- | absent, `not_provided` |

The collector's manifest is `instruction,tool_schemas,readout,decoding`. The four model parts are absent with reason `not_observable`, because a request body says nothing about what answered (SPEC section 6).

**Example.** A body with a system message `Answer in one word.`, a user message and `"temperature": 0` gives a held `instruction` with the `model_visible` digest of `Answer in one word.`, a held `decoding` labelled `temperature`, `tool_schemas` and `readout` absent with reason `not_provided`, and a harness identity computed over the instruction alone. `spec/examples/request-adapter.json` is a complete record of this kind.

## Fields this binding does not read

A version 2 collector reads only the fields above. Every other field of the request is outside the record, and a receiver MUST NOT read the record as saying anything about it. In particular:

| field | what that means for a record |
|---|---|
| messages with `role` `developer` | not part of `instruction`. Two requests differing only in a developer message have the same harness identity. |
| `tool_choice`, `parallel_tool_calls` | not part of `tool_schemas` or `decoding` |
| `stop`, `max_tokens`, `max_completion_tokens`, `n`, `logit_bias`, `presence_penalty`, `frequency_penalty`, `reasoning_effort` | not part of `decoding` |
| `model` | not part of any part. A provider's model name may label the `checkpoint` part as `not_observable` (SPEC section 6), and it never keys anything. |

Reading any of these would change the digest of a part some existing record already carries, so each one is a change of version under SPEC section 7, and none is made in version 2. They are on the roadmap in the README.

## Other request shapes

A request in any other shape, such as the Anthropic Messages API or the OpenAI Responses API, needs its own binding: which field each part is read from, and its boundary. Until one exists, a collector reading such a request is not conformant for it, and SHOULD say so by giving every part it cannot map the absence `not_reachable` with a detail naming the request shape.
