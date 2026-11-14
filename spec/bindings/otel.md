# Binding: OpenTelemetry spans

Normative for a collector that carries a record as attributes on an OpenTelemetry span, and for a receiver that reads one from a span (SPEC section 0.2). The record's attributes are the ones of SPEC section 6, unchanged: a span is a carrier, and nothing in this binding adds a field.

## Which span

A collector SHOULD put the record on the span that represents the model call it describes: in OpenTelemetry's GenAI conventions the inference span, and in OpenInference the `LLM` span. One span carries at most one record. A record on a parent span describes nothing in particular, because the parent may cover several calls with different harnesses.

## Losses on the way

A span can lose attributes on the way to the receiver, and a lost attribute is a lost statement. The cases that matter:

| how it is lost | what the receiver sees |
|---|---|
| the SDK's attribute count limit (128 by default) is reached and later attributes are dropped | a span with a non-zero dropped attribute count, and a record with some keys missing |
| a value is truncated by an attribute length limit | a digest or identity of the wrong length |
| the span is not sampled, or the exporter drops it | no record at all |

A full record of version 2 has about 60 attributes, and an instrumented model-call span often carries 20 to 40 more of its own. A collector SHOULD raise the span's attribute count limit, or put the record on a span of its own linked to the model-call span, when the two together could pass the limit.

A receiver reading a record from a span MUST refuse a verdict over it when the span reports a non-zero dropped attribute count. **Rationale**: a dropped absence turns a hole the sender declared into silence, and a dropped manifest turns a contradiction into nothing, so no remaining attribute can be read at face value. The record is still stored, as for any other refusal (SPEC section 0.5). A truncated digest or identity fails the receiver's checks and the record is rejected (SPEC section 6). A span that never arrived is a lost record, which SPEC section 1.1 says a receiver reads as `unknown`.

## Relation to the GenAI and OpenInference attributes

Informative. Surveyed at semantic-conventions-genai commit `e6658f1` (2026-11-06) and OpenInference commit `715e299` (2026-11-11). Neither convention has a per-part content digest or a per-part sourcing mode, which are the two things a perigraph record adds, so the attributes below sit next to a record rather than inside it, and none of them is read by a receiver as part of the record.

| perigraph part | nearest GenAI attributes | nearest OpenInference attributes | how they differ |
|---|---|---|---|
| `instruction` | system instructions and input messages, when content capture is on | `llm.input_messages` | those carry the content, or nothing when capture is off. perigraph carries a digest of the exact bytes, never the content, and says where the bytes came from |
| `tool_schemas` | tool definitions | `llm.tools` | the same: content against a `parsed` digest |
| `decoding` | `gen_ai.request.temperature`, `gen_ai.request.top_p` and the other request parameters | `llm.invocation_parameters` | those are the values; perigraph keeps a digest and a label, and never keys an identity on them |
| `checkpoint` | `gen_ai.request.model`, `gen_ai.response.model` | `llm.model_name` | a model name is a label the owner controls. perigraph's `checkpoint` is the digest of the files a process loaded, and a name is only ever its label |

A span that carries both is fine and is the expected case. A receiver that compares runs reads the perigraph record for what was the same, and the other attributes for what was said.
