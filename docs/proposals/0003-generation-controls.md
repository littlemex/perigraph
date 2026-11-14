# Proposal 0003: the `generation_controls` part, the `canonical_value` boundary, and agreement within an arm

## What changed while every existing name stayed the same

R17b of the tierbook distillation study sent its first-turn request bodies to an OpenAI-compatible server and computed a perigraph version 3 record for each, with no model needed:

| harness | the request body | what the caller did with the reply | version 3 harness identity |
|---|---|---|---|
| H0, base | a 77-intent routing system message, a templated user message, `temperature` 0, `max_tokens` 32, `chat_template_kwargs` `{"enable_thinking": false}`, `logprobs` true | read the answer by the rule `bk77-exact-v1` | `6c22e7b8d0b63ca1f9281949` |
| H3, reasoning before the answer | the same, with `max_tokens` 256 and `enable_thinking` true | the same rule | `6c22e7b8d0b63ca1f9281949` |
| H4 | the body of H3 | a different rule, the first label in the reply | `6c22e7b8d0b63ca1f9281949` |
| H6 | the body of H3 | the H3 rule, and one retry with a corrective user turn when the answer is not a label | `6c22e7b8d0b63ca1f9281949` |

The teacher's body shared the identity too. Every version 3 part digest was the same across H0 and H3, because the collector read only `temperature`, `top_p`, `top_k`, `seed` and `response_format`, and `decoding` was a `parsed` part that never keyed the identity. H4 and H6 differ from H3 only in what the caller does, which no request carries; version 3 had no way to say so for the readout, and a declared retry policy could not stop the three from being pooled.

**Not measured:** any accuracy difference caused by these members. The one adjacent measurement, R17a's reasoning-before-the-answer arm against base on 1,200 items of another task, did not move (0.0 points, 95% interval -0.42 to 0.42). No measurement of any kind exists for `stop`, the top-level reasoning switches or `max_completion_tokens`; they are included because they are the same kind as the two observed members, so that the key cannot be evaded by spelling one engine's switch another way. The case is therefore a collision, as for `request_template` in proposal 0001, and not a measured move.

## The change to spec/vocabularies.json

- `spec_version` 3 to 4.
- `parts.values` gains `generation_controls`, before `decoding`.
- `boundaries.values` gains `canonical_value`; `boundaries.may_key_identity` is replaced by `keying_boundary`, a map from each part that may key the harness identity to the one boundary at which it may: `instruction` and `request_template` at `model_visible`, `generation_controls` at `canonical_value`.
- `refines_only` gains `generation_controls`, with the ground stated beside `request_template`'s: the value is the same whatever messages are sent, so alone it would give every prompt sent with the same settings one identity.
- `must_be_known_for_identity` gains `generation_controls`, and a part in it is known only when held `in_the_request` at its keying boundary or absent as `not_provided`.
- New `uniform_within_arm`: `readout`, `retry_policy`, `loop`, `turn_budget`, `context_partitioning`, `decoding`.
- New `bindings.openai_chat_completions.members`, the closed list of top-level request members the binding recognises and the parts each is read into, and `unlisted_names`, the pattern and bound for names written in `perigraph.request.unlisted`.
- `digest.canonical_value_serialisation`; `digest.parsed_digests_are_collector_local` says a `canonical_value` digest compares across collectors.
- `attributes.record` gains `perigraph.request.unlisted` and `perigraph.request.unlisted_omitted`.
- `receiver_obligations.must_refuse` gains two entries and rewords the one about identifying boundaries.

The SPEC sentences are in sections 0.2 (normative references, what is valid JSON), 1.0, 1.2, 2, 2.1, 2.3, 2.4, 2.5, 4, 6, 7, 8, 11 and 12.3. The OpenAI Chat Completions binding states the member list, what kind of member goes where, and what the binding does not see.

## Cases a non-conforming implementation fails

- `spec/fixtures/canonical_value.json`, 44 cases from JSON text: the ECMAScript number layout (`1e-7`, `0.000001`, `5e-324`, `256.0`), the unsafe integers, `1e400`, the strings other serialisers escape (`<>&/`, U+2028), NFC against NFD, lone surrogates in a string and in a member name, RFC 8785's sorting example and a key order where UTF-16 and code-point order disagree, a repeated member name, and `__proto__` and `constructor`.
- `spec/fixtures/identity.json`, 19 new cases: R17b's H0 and H3, H3 respelled (reordered, `256.0`), `max_tokens` against `max_completion_tokens`, `{}` against absent, controls without a system message, an unsafe integer in a control and in a sampler setting, the stated `1` and `1.0` merge, `stop` as a string and as an array, members named like JavaScript object properties.
- `conformance/cases/receiver.json`, 15 new single-record cases: a version 3 record rejected, the rejection grounds of the unlisted attributes, an identity that omits the controls, controls alone, pushed, at the wrong boundary or unserialisable, and `tool_schemas` at `canonical_value` keying nothing.
- `conformance/cases/arm.json`, 15 cases over at least three records each, through the adapter op `admit_arm`: one identity, declarations that differ last or in the middle, a declaration beside none, differing sampler settings, an unknown state, differing unlisted members, and an empty arm.

The Python, TypeScript and Go implementations pass them (Go as collector and stamper).

## What a receiver does with it

`generation_controls` keys the harness identity beside an instruction and never establishes one. The pushed parts and `decoding` never key the identity; a receiver refuses one verdict over an arm whose records hold one of them with different digests, or hold it beside `not_provided`, and reports `unknown` where a record's state is unknown. Every rule here can cause a refusal and none lifts one: an arm whose records all say nothing about a part is admitted exactly as an arm whose records all say the same thing.

## Whether it is breaking

Yes, on five counts listed in SPEC 7, and a version 3 receiver rejects every version 4 record. The harness identity of a record whose request carries no generation control is the version 3 value. The identity of a record whose `request_template` is declared by its owner rather than read from the request is withdrawn.
