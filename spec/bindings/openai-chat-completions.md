# Binding: OpenAI Chat Completions request bodies

Normative for a collector that reads a request body in the OpenAI Chat Completions shape (SPEC section 0.2). It says which field each part is read from. How a part is digested, and what an unreadable field becomes, is in SPEC sections 1.2 and 2.2; this document does not restate those rules.

## Field to part

| part | read from | boundary | identifying |
|---|---|---|---|
| `instruction` | the `content` of every message whose `role` is `system`, joined with U+000A in message order (SPEC 2.2) | `model_visible` | yes |
| `request_template` | the top-level member `perigraph_template`, verified against `messages` (below) | `model_visible` | only beside another identifying part, here `instruction` (SPEC 2, `refines_only`) |
| `tool_schemas` | `tools`: for each entry, the function's `name` and `parameters`. The serialisation and the order of entries are the collector's own, because a `parsed` digest is collector-local (SPEC 2.3) | `parsed` | no |
| `readout` | `response_format` | `parsed` | no |
| `decoding` | `temperature`, `top_p`, `top_k` and `seed` when present and not `null`, in that order, then `response_format` | `parsed` | no |
| `loop`, `turn_budget`, `retry_policy`, `context_partitioning` | nothing: a request body has no field for them | -- | absent, `not_provided` |
| `tool_extension` | nothing: what a tool does is not in any request | -- | absent, `not_observable` |
| `tool_trace` | nothing. Earlier `tool_calls` and `tool` messages in `messages` are not read as a trace in version 3 | -- | absent, `not_provided` |

The collector's manifest is `instruction,request_template,tool_schemas,readout,decoding`. The four model parts are absent with reason `not_observable`, because a request body says nothing about what answered (SPEC section 6).

**Example.** A body with a system message `Answer in one word.`, a user message and `"temperature": 0` gives a held `instruction` with the `model_visible` digest of `Answer in one word.`, a held `decoding` labelled `temperature`, `tool_schemas` and `readout` absent with reason `not_provided`, and a harness identity computed over the instruction alone. `spec/examples/request-adapter.json` is a complete record of this kind.

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

## Fields this binding does not read

A version 3 collector reads only the fields above. Every other field of the request is outside the record, and a receiver MUST NOT read the record as saying anything about it. In particular:

| field | what that means for a record |
|---|---|
| messages with `role` `developer` | not part of `instruction`. Two requests differing only in a developer message have the same harness identity, unless a request template names its text. |
| `tool_choice`, `parallel_tool_calls` | not part of `tool_schemas` or `decoding` |
| `stop`, `max_tokens`, `max_completion_tokens`, `n`, `logit_bias`, `presence_penalty`, `frequency_penalty`, `reasoning_effort` | not part of `decoding` |
| the `content` of messages whose role is not `system`, except the fixed strings a request template names; any message's `name`, and earlier `tool_calls` and `tool` messages | not part of any part. Without a template, changes to the conversation do not change the harness identity; with one, a change to the fixed strings or to the number or roles of the messages does |
| a tool's `description` and `strict` | not part of `tool_schemas` |
| `model` | not part of any part. A provider's model name may label the `checkpoint` part as `not_observable` (SPEC section 6), and it never keys anything. |

Reading any of these would change the digest of a part some existing record already carries, so each one is a change of version under SPEC section 7, and none is made in version 3. They are on the roadmap in the README.

## Other request shapes

A request in any other shape, such as the Anthropic Messages API or the OpenAI Responses API, needs its own binding: which field each part is read from, and its boundary. Until one exists, a collector reading such a request is not conformant for it, and SHOULD say so by giving every part it cannot map the absence `not_reachable` with a detail naming the request shape.
