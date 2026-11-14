# Proposal 0001: the `request_template` part

## What changed while every existing name stayed the same

R17a of the tierbook distillation study answered 1,200 certification items of a three-label headline task with one byte-identical student checkpoint under several harnesses, recording a perigraph version 2 record for each:

| harness | the request | accuracy | harness identity |
|---|---|---|---|
| H0 | user message: the headline | 0.8983 | none |
| H1 | system message: the instruction; user message: the headline | 0.8608 | `d6c151cf…` |
| H2 | user message: `<the same instruction>\n\nHeadline: <the headline>` | 0.8525 (H0 minus 4.58 points, 95% interval 2.38 to 6.79) | none |
| cache suffix | an irrelevant block of about 1,500 tokens appended in the user message | 0.898 to 0.858 | unchanged |

Every part stayed the same across H0 and H2, and across the cache-suffix change (whose baseline is H0), because version 2 reads nothing from a message whose role is not `system`. The same would hold for two harnesses that share a system message and differ in the text they wrap around each item: one identity, pooled. That case is not measured; R17a's measured cases have no system message, so under this proposal they are recorded and still have no harness identity.

## The change to spec/vocabularies.json

- `spec_version` 2 to 3.
- `parts.values` gains `request_template`, after `instruction`.
- New `refines_only`, with the value `request_template`: a part that may refine an identity another identifying part establishes and may never establish one.
- New `must_be_known_for_identity`, with `instruction` and `request_template`, and `known_when_absent_as: "not_provided"`: a record in which one of these parts is absent for another reason, or not mentioned, has no harness identity.
- `digest.request_template_serialisation`, the exact bytes; a top-level `white_space` with `code_points`, the set SPEC 1.2 already named; amended `boundaries.rationale.model_visible` and `digest.model_visible_payload`.
- `attributes.record.perigraph.harness_identity`, note updated.
- `receiver_obligations.must_refuse` gains the arm rule of [proposal 0002](0002-one-harness-identity-per-arm.md).

The SPEC sentences are in sections 1.0 (the part and why), 1.2 (eleven parts; an empty template is not sent), 2 (when a record has no identity), 2.1 and 2.2 (the digest is over model-visible strings framed with the entry count, the roles and the lengths), 2.5 (what the identity still cannot tell apart), 7 (version 3), and 12.2 and 12.4. The OpenAI Chat Completions binding has a new section, "The request template", with the request member, the checks, the emptiness test, the withdrawal and the forwarding duty. `tools/gen_schema.py` and `tools/requirements.py` regenerate `spec/schema/` and `spec/requirements.json`.

The request carries the template beside `messages`:

```json
{"messages": [{"role": "system", "content": "Answer with one word."},
              {"role": "user", "content": "Headline: Stocks rise"}],
 "perigraph_template": {"messages": [{"role": "system"},
                                     {"role": "user", "fixed": ["Headline: ", ""]}]}}
```

## Cases a non-conforming implementation fails

`spec/fixtures/identity.json` gains 32 cases, each naming the `request_template` digest or absence reason:

| case | rules out |
|---|---|
| an instruction and a wrapper, against the same request without a template | a collector that ignores the template, or lets it change a request that declares none |
| the instruction in the user message with no system message | a template that establishes an identity by itself |
| `["", ""]`, and untemplated entries only | a template that fixes nothing being held |
| the same string before and after the hole | a serialisation that drops empty strings |
| `["A", "B"]` against `["AB"]` over `AB` | a digest over the content instead of the fixed strings |
| Japanese and an astral-plane character | lengths in UTF-16 units |
| system messages before and after the user message | a serialisation that ignores where the untemplated entries sit |
| braces in a fixed string | a placeholder grammar |
| a newline and U+2028 in a hole, content ending in a newline | a line-anchored match |
| U+FEFF and U+001F | a language's own trim instead of the White_Space set |
| an assistant message with tool calls, as an untemplated entry | requiring every message to be templated |
| a contradicted template; overlapping `ab` and `bc` over `abc`; a system entry with fixed strings; an empty interior string; an extra member; a role with a trailing space; a wrong entry count; no `messages`; content that is an array | accepting a template the request does not verify, or falling back to the instruction-only identity |
| a `null` template | treating `null` as a malformed template |
| an empty template with a wrong entry count | applying the emptiness test before the checks |
| `fixed` empty or `null` | accepting a templated entry with no fixed text |
| `["a", "b", "c"]` over `a1b2c`; `["a", "b", "b", "c"]` over the same | an untested interior search |
| `[" ", ""]` | testing emptiness with `== ""` instead of the White_Space set |

`conformance/cases/receiver.json` gains ten cases: both parts held (admitted); a template alone (refused, no identity); an identity stated over a template alone (rejected); the instruction-only identity stated beside a failed template, and beside a held one (both rejected); a failed template, a redacted one, one neither held nor absent, and one beside an unreadable instruction (all refused); a template declared by its owner beside an instruction (admitted, with the instruction's identity). The Python and TypeScript implementations pass all of them. The Go implementation, which has no receiver role, passes every fixture.

A lone surrogate is tested in the Python and TypeScript suites and not in the shared fixtures: Go's JSON reader replaces one with U+FFFD before a collector sees it, and the binding says such a collector is not conformant for that body.

## What a receiver does with it

The part may key the harness identity only beside another identifying part, in this binding `instruction` (`refines_only`): which text is fixed and which is the item is the requester's declaration, which nobody can check, and an identity resting on it alone would lift the refusal of a record with no identity on the requester's word (SPEC 1.1a). Beside an instruction it can only split. A template that the request contradicts makes the part `extraction_failed`, and by `read_for_identity` the record then has no harness identity, so a declaration can subtract and never add. A receiver derives the identity from the parts under these rules, and a stated identity that differs is a ground for rejection (SPEC 6), which already existed.

Alternatives weighed:

- an owner-declared template digest, or a manifest file beside the harness whose digest is a part: `pushed_by_owner` can never key an identity, so H0 and H2 would stay unseparated and the shared-system-message case would still pool;
- vendor extension attributes with a permission to refuse: no version change, but no receiver would have to act on them, and each implementation would invent its own;
- reading the whole non-system text: unique per item, so no two runs share an identity;
- inferring the template from many records: a statistical guess, not a fact about one run;
- a template with named placeholders and slot values: scanning, escaping and rescanning rules that two implementations read differently, and the item copied into the record.

What it does not fix: fixed text the requester placed inside a hole; requesters who send no template; a template that grows with a conversation (each turn count is its own identity, and the arm rule then refuses the arm); the Chat Completions fields the binding still does not read; other request shapes.

## Whether it is breaking

Yes. It adds a part, which a version 2 receiver rejects (SPEC 1.0), and a value that may key an identity, which SPEC 7 lists as breaking; hence `spec_version` 3. The harness identity of a record with no `request_template` held is computed as in version 2, so every version 2 identity fixture is unchanged and a request that declares no template has the same identity under both versions. A version 2 receiver rejects every version 3 record; how mixed populations are read is left to the planned versioning policy (SPEC 7.1).
