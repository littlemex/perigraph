# Binding: OpenAI Chat Completions request bodies

Normative for a collector that reads a request body in the OpenAI Chat Completions shape (SPEC section 0.2). It says which field each part is read from. How a part is digested, and what an unreadable field becomes, is in SPEC sections 1.2 and 2.2; this document does not restate those rules.

## Field to part

| part | read from | boundary | identifying |
|---|---|---|---|
| `instruction` | the `content` of every message whose `role` is `system`, joined with U+000A in message order (SPEC 2.2) | `model_visible` | yes |
| `request_template` | the top-level member `perigraph_template`, verified against `messages` (below) | `model_visible` | only beside an identifying part outside `refines_only`, here `instruction` (SPEC 2) |
| `tool_schemas` | `tools`: for each entry, the function's `name` and `parameters`. The serialisation and the order of entries are the collector's own, because a `parsed` digest is collector-local (SPEC 2.3) | `parsed` | no |
| `generation_controls` | `chat_template_kwargs`, `reasoning_effort`, `reasoning`, `thinking`, `enable_thinking`, `max_tokens`, `max_completion_tokens`, `stop`, `response_format`, `tool_choice`, `parallel_tool_calls`, `chat_template`, `add_generation_prompt`, `continue_final_message`, `guided_json`, `guided_regex`, `guided_choice`, `guided_grammar`, `structured_outputs`, `min_tokens`, `stop_token_ids`: each when present and not `null` | `canonical_value` | only beside an identifying part outside `refines_only`, here `instruction` (SPEC 2) |
| `decoding` | `temperature`, `top_p`, `top_k`, `min_p`, `presence_penalty`, `frequency_penalty`, `repetition_penalty`, `logit_bias`, `n`, `logprobs`, `top_logprobs`: each when present and not `null` | `canonical_value` | no |
| `readout`, `loop`, `turn_budget`, `retry_policy`, `context_partitioning` | nothing: a request body has no field for them. The owner may declare them (`pushed_by_owner`) | -- | absent, `not_provided`, unless declared |
| `tool_extension` | nothing: what a tool does is not in any request | -- | absent, `not_observable` |
| `tool_trace` | nothing. Earlier `tool_calls` and `tool` messages in `messages` are not read as a trace | -- | absent, `not_provided` |
| recorded nowhere | `model`, `seed`, `stream`, `stream_options`, `user`, `metadata`, `store`, `service_tier` | -- | -- |

This table restates `bindings.openai_chat_completions.members` in `spec/vocabularies.json`, which governs (SPEC 0.2). A
member the table does not name is **unlisted**: the first `unlisted_names.max` names matching `unlisted_names.pattern`,
in ascending order, are written in `perigraph.request.unlisted`, and every other unlisted member is counted in
`perigraph.request.unlisted_omitted` (SPEC section 6). The list is frozen per `spec_version`, because adding a member to
a part changes what that part's digest is over. It is the members of each kind the authors identified in the OpenAI
Chat Completions reference and in vLLM's chat completion request, plus the top-level reasoning switches of other
servers; a member of either kind outside it is unlisted, so its presence is recorded and its value is not.

**Each canonical part's payload** is the JSON object of its members present and not `null`, under their request names,
serialised by `digest.canonical_value_serialisation`; its label lists the member names, sorted and joined with U+002C,
and no value. Names are compared exactly, by code unit, and are not aliased: `max_tokens` and `max_completion_tokens`
are two members, and `stop: "x"` is not `["x"]`. Whether they mean the same is the server's decision, and splitting is
the safe direction. A member whose value cannot be serialised makes its part `extraction_failed` and leaves the other
parts alone.

**What kind of member goes where.** A member that selects what the engine renders into the prompt, excludes outputs by
their form, or bounds the output's length is a generation control, even where an engine enforces it on the scores. A
member that reshapes or reports the distribution a token is drawn from, or says how many completions are drawn, is
decoding. `seed` selects a draw from the distribution the other members define and changes none of them; it is
recorded nowhere. Where a member fits two kinds, the list governs.

The collector's manifest is `instruction,request_template,tool_schemas,generation_controls,decoding`. The four model parts are absent with reason `not_observable`, because a request body says nothing about what answered (SPEC section 6).

**Example.** A body with a system message `Answer in one word.`, a user message, `"temperature": 0` and `"max_tokens": 8` gives a held `instruction` with the `model_visible` digest of `Answer in one word.`, a held `generation_controls` labelled `max_tokens` with the digest of `{"max_tokens":8}`, a held `decoding` labelled `temperature` with the digest of `{"temperature":0}`, `tool_schemas` and `readout` absent with reason `not_provided`, `perigraph.request.unlisted` empty, and a harness identity computed over the instruction and the generation controls. `spec/examples/request-adapter.json` is a complete record of this kind.

## The request template

The requester MAY add a top-level member `perigraph_template` to the body to declare which text of its non-system
messages is fixed and where the item goes. A collector reads it as follows; the requester has no conformance class of
its own (SPEC section 8), so every rule is stated as what the collector does.

```json
{"messages": [{"role": "system", "content": "Answer with one word."},
              {"role": "user", "content": "Headline: Stocks rise"}],
 "perigraph_template": {"messages": [{"role": "system"},
                                     {"role": "user", "fixed": ["Headline: ", ""]}]}}
```

An entry with `fixed` is **templated**: its strings are the fixed text, and the gaps between consecutive strings are
the holes the item went into. An entry with only `role` is **untemplated**: the message's content is not read, whatever
it is, and its role and position still enter the digest. A system message's entry is untemplated (check 5), because its
text is the `instruction` part and is not counted twice.

**Reading.** The collector MUST apply these checks, and any that fails makes `request_template` `extraction_failed`, with
a detail that names a failed check and the index of the entry, fixed string or message, and never quotes a string (SPEC
12.3). Which failure the detail names when several fail is the collector's choice; the outcome is the same:

1. `perigraph_template` is an object whose only member is `messages`;
2. its `messages` is an array; the request's `messages` is an array of the same length;
3. each entry is an object whose members are `role` and, optionally, `fixed`;
4. each entry's `role` is a string equal, code point for code point, to the `role` of the message at the same index;
5. an entry whose role is `system` has no `fixed`;
6. each `fixed` is a non-empty array of strings, and no string other than the first and the last is empty, because
   two adjacent holes are one hole;
7. the message of each templated entry has a `content` that is a string;
8. every string read in checks 4 to 7 is a sequence of Unicode scalar values: a lone surrogate fails, and a collector
   whose JSON reader replaces one silently cannot make this check and is not conformant for such a body;
9. each templated message's `content`, as utf-8 bytes, can be written as `s0 h1 s1 ... hn sn`, where `s0` to `sn` are
   its fixed strings and each `h` is any byte string, the empty one included. Taking the first occurrence of each interior
   string at or after the end of the previous one decides this exactly: `content` starts with `s0`, the interior strings
   are found in order, and `content` ends with `sn` at or after the end of the last one found. With one string, `content`
   equals it. A search over bytes, over code points and over UTF-16 units agrees on well-formed strings.

A `perigraph_template` that is missing or `null` is not sent, and so is one that passes every check and whose fixed strings
contain no character that is not white space (SPEC 1.2); the emptiness test is applied only after every check has
passed, so an empty template that does not match the request still fails. Either is `not_provided`. Otherwise the part is held, with
the digest of `digest.request_template_serialisation` over the entries, and no label carries template text.

This binding sets no size limit. A collector that will not read a template because of its size records it as
`extraction_failed`, which withdraws the identity: the safe direction.

No string is normalised, trimmed or changed in line endings. Member names repeated within `perigraph_template` or within
a templated message are outside this binding: JSON leaves their meaning undefined, and the collector reads the body as
its JSON reader decoded it.

**What it names.** The fixed strings, the first anchored at the start of the content, the last at its end and the
others found in order between them, together with the number and the roles of the messages. It does not name what is in the holes,
so text the requester fixed but placed in a hole -- an instruction concatenated into the item, a suffix appended to the
item before it was placed -- is read as item. A request with no system message has no harness identity whatever its
template says (SPEC section 2).

**A template that does not verify withdraws the identity.** `request_template` is in `must_be_known_for_identity`, so a record in
which it is `extraction_failed` has no harness identity even when `instruction` is held. A declaration that the request
contradicts can only subtract. The absence blames the collector, as for any field the collector cannot read (SPEC 1.2):
from inside the collector a wrong template and a misread `messages` look the same.

**Forwarding.** A collector that sends the body on MUST remove `perigraph_template` first, unless it is configured to
send to a hop that reads the template, and MUST leave every other member's decoded value unchanged. A collector that only observes a body, and an in-process collector that never forwards one, removes nothing.
A collector after a hop that removed the template records `not_provided`, so its records and the upstream collector's
have different harness identities, which is the safe direction. A requester that sends a template where no collector
removes it sends an unknown member to the provider, which some providers reject.

## What this binding reads and does not read

A version 4 collector reads only the members above. Every other member is named or counted as unlisted, and the record says nothing about its value. These are outside the record, although the binding recognises the member they belong to:

| field | what that means for a record |
|---|---|
| messages with `role` `developer` | not part of `instruction`. Two requests differing only in a developer message have the same harness identity, unless a request template names its text. |
| the `content` of messages whose role is not `system`, except the fixed strings a request template names; any message's `name`, and earlier `tool_calls` and `tool` messages | not part of any part. Without a template, changes to the conversation do not change the harness identity; with one, a change to the fixed strings or to the number or roles of the messages does |
| a tool's `description` and `strict` | not part of `tool_schemas` |
| `model` | not part of any part. A provider's model name may label the `checkpoint` part as `not_observable` (SPEC section 6), and it never keys anything. A switch carried in the model name, such as a `-thinking` suffix, is not seen |

A switch carried anywhere else -- an HTTP header, a query parameter, a server's launch flag or default template arguments -- is not in the body and is not seen either (SPEC 2.5). Two values under one unlisted member name are not told apart; reading such a member is a change of version under SPEC section 7.

## Other request shapes

A request in any other shape, such as the Anthropic Messages API or the OpenAI Responses API, needs its own binding: which field each part is read from, and its boundary. Until one exists, a collector reading such a request is not conformant for it, and SHOULD say so by giving every part it cannot map the absence `not_reachable` with a detail naming the request shape.
