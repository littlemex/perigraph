# Changelog

Versions here are the **package** version. The **protocol** version is `spec_version` in
`spec/vocabularies.json`, and [SPEC.md section 7](SPEC.md) says what forces it to change.

## Unreleased

No change to `spec_version` (still 2) and no change to any identity or fixture. The package versions are unchanged.

### Specification

- **Conventions** (SPEC 0): BCP 14 keywords, what is normative and which source governs when two disagree, roles
  (requester, collector, stamper, forwarder, owner, trainer, receiver), terms, and the four things a receiver does with
  a record.
- **Security and privacy considerations** (SPEC 12) and **extensibility** (SPEC 13): the proposal path for a new value,
  and the reserved `perigraph.ext.<vendor>.` prefix, which never keys an identity and is never grounds for rejection.
- **Wire-level rejections stated in one place** (SPEC 6): out-of-vocabulary values, a part both held and absent, a read
  lag or a detail where it is forbidden or missing, and an identity that is not the one derived from the parts. The
  reference receivers already rejected each of these; the text now says so.
- **Conformance per role** (SPEC 8), and the policy in SPEC 7 marked provisional, with the questions a formal versioning
  and compatibility policy has to settle listed in SPEC 7.1.
- `perigraph.model_reaches` and `perigraph.ext.<vendor>.<key>` added to `attributes` in `spec/vocabularies.json`. The
  first was already emitted; the second is a reserved pattern. Both are additions a receiver may ignore (SPEC 7).
- Bindings under `spec/bindings/`: OpenAI Chat Completions request bodies, OpenTelemetry spans, JSON Lines files.

### Machine-readable specification and conformance

- JSON Schemas for a record, a lineage document and the vocabulary file, generated from `spec/vocabularies.json`
  (`tools/gen_schema.py`).
- `spec/requirements.json`: every requirement sentence with an identifier that is never reused
  (`tools/requirements.py`).
- `tools/conform.py`, a conformance runner that checks any implementation through a line-oriented adapter, with
  receiver cases in `conformance/cases/receiver.json` and adapters for the Python, TypeScript and Go implementations.
- Example records and a lineage chain in `spec/examples/`, each validated in CI.

### Fixed

- The Python and TypeScript receivers rejected a manifest that named a part twice. SPEC 6 says a repeated name counts
  once; both now read the manifest as a set.

## 0.2.1

### A third sender, and the sentences it read differently

A Go sender (`go/`) was written by a different model family (OpenAI GPT-6 Sol) from `SPEC.md` and
`spec/vocabularies.json` alone, without the Python or TypeScript source or the fixtures, and revised only from compiler,
test and conformance output. It reproduced every fixture. Comparing it with the reference senders on inputs the
fixtures did not cover found the disagreements below, each found by an independent implementation and each now a rule
with a fixture where a fixture can hold it:

- **A system message whose content is not a string** (an array of parts, a number, `null`, missing) makes `instruction`
  `extraction_failed` (SPEC 2.2). The two reference senders rendered the same array as two different strings and so
  gave one request two harness identities.
- **A request the collector cannot parse** (a body that is not an object; `messages`, `tools` or an entry of either of
  the wrong JSON type; a `response_format` that is not an object) is named as `extraction_failed` parts with a detail,
  and the status is derived from the parts as for any record (SPEC 1.2). Both reference collectors threw on such a
  body, which their wrappers turned into `collector_failed`.
- **A message whose `role` is missing or not a string** might have been a system message, so it fails the parts read
  from `messages` (SPEC 1.2). The Go sender did this; the reference senders skipped the message.
- **A top-level field sent as `null`** is one the request does not carry (SPEC 1.2). The Go sender read `tools: null`
  as the wrong type; the reference senders read it as none sent, but kept `temperature: null` as a setting.
- **An empty value is none sent** (SPEC 1.2): an instruction of white space only, an empty `tools` array and an empty
  `response_format` are `not_provided`. The reference senders did this for the first two; the Go sender held all three.
- **White space is the Unicode `White_Space` property** (SPEC 1.2, 9). Python's `str.strip()` and JavaScript's
  `trim()` strip different sets, and the test decides whether a part exists.
- **A `response_format` is read by `decoding` as well as `readout`** (SPEC 1.2), since it constrains the grammar of the
  output. The Go sender did this; the reference senders did not.
- **The manifest is a set** (SPEC 6): order carries no meaning, and a sender should not repeat a name.
- **A collector that cannot observe the model says so** (SPEC 6, 9): it emits the four model parts as `not_observable`,
  as absences or as labelled parts with no digest. A record with no model half does not conform but is not refused; it
  is read as unknown, now also an entry in `receiver_obligations.must_not_refuse`. Both reference senders now emit the
  four absences.
- **A dtype named `auto`, or with an empty name, is unresolved** (SPEC 9), as an `auto` or empty value already was.

Also: SPEC 7 states that a change which only withdraws an identity is not breaking, and SPEC 8 that a fixture governs
where it and the text disagree. `perigraph.part.<name>.label` is stated in the normative JSON to be never compared and
ignorable. A sender conforms by satisfying sections 1, 2, 5, 6 and 9. Nine request bodies were added to
`spec/fixtures/identity.json` and a `refused_precision` list to `spec/fixtures/model_identity.json`.
`tools/cross_check.py` runs the Go sender too. The Go sender's first draft retyped the vocabularies and dropped
rationale text, so its tests compare the embedded file's sha256 with the spec's copy.

**`spec_version` stays 2** under the withdraw-only rule in SPEC 7. These inputs had a harness or model identity from
both reference senders and now have none: a system message with numeric content; a system message with no `content`;
a request with a message whose `role` is missing or not a string; and a `precision` with a dtype named `auto` or with an
empty name. An instruction whose only characters are U+001C-U+001F or U+FEFF now has an identity that one reference
sender gave it and the other did not. No receiver refusal is added.

## 0.2.0

### Protocol, `spec_version` 2

The model is now part of what a record identifies. Every addition cites a moment in a distillation record where the
answers moved while every name stayed the same.

- **A model half, written by the process that loaded the model**: four closed model parts, `checkpoint` (every file
  read from the artifact), `precision` (read off the loaded parameters), `runtime` (packages resolved in-process) and
  `answer_mode` (`generated_text`, `option_scores`, `classifier_output`), and a new sourcing `loaded_by_us`, the only
  one that may key a model identity.
- **Two new identities**: `perigraph.model_identity` over all four model parts, collector-local; and
  `perigraph.artifact_identity` over the checkpoint alone, comparable across collectors. `perigraph.identity` is renamed
  `perigraph.harness_identity`; its computation and fixtures are unchanged.
- **Lineage documents**: a trainer-written, subtract-only record of how an artifact came to be (parent, method, the
  item sets it trained on or consulted, its training signal), read as absent when its subject is not the artifact
  observed, and walked through its parents.
- **Four receiver obligations**: refuse a model identity built on a part not `loaded_by_us`; one verdict over an arm
  carrying several model identities or a mix of with and without; a claim bound to a model identity applied to records
  without it; and a comparison of model identities across collectors.
- **Section 2.5 is replaced**: bf16 against int8, and option scores against generated text, are now two model identities.
- New fixtures `spec/fixtures/model_identity.json`, reproduced by both reference implementations.

## 0.1.x

### Protocol, `spec_version` 1

Five additions, all of them forced by writing a second implementation from the spec rather than from the first
implementation's source. See [docs/ambiguities.md](docs/ambiguities.md).

- **The identity's serialisation, encoding, length and join are now specified.** They were not, and two conformant
  senders would have produced two identities for one run. This is the one that would have killed interoperability.
- **`utf-8` is stated.** An implementation choosing UTF-16 would have produced a different identity for every
  non-ASCII instruction while passing every test it wrote for itself.
- **A `parsed` digest is declared collector-local**, with a receiver obligation to refuse the cross-collector
  comparison. The two reference senders legitimately disagree on one, and there is nothing neutral to legislate.
- **An empty manifest is the empty string on the wire**, and a reader must drop empty entries.
- **Section 7 says what a breaking change is.** It did not exist, which makes a protocol's compatibility rules
  whatever two implementations each assumed.

Three clarifications that change no vocabulary and no obligation:

- **An absent record is never a clean one.** A sender that can lose records should report how many, and a loss nobody
  reported is unknown, not zero.
- **Any claim a receiver cannot check may only subtract**, whether it is a pushed part or a declaration beside the
  record.
- **A digest names content**: a file is cited by its bytes, and digests are compared whole, never truncated.
  Section 2.5 says what the identity cannot tell apart: two precisions of one checkpoint, or an answer read from
  probabilities versus one parsed from generated text.

Also: `spec/fixtures/identity.json`, the golden identities every implementation must reproduce, including one
non-ASCII case that exists solely to catch an encoding disagreement.

### Implementations

- Python sender and receiver.
- TypeScript sender.
- `tools/cross_check.py`, run in CI: the only check neither implementation can pass by agreeing with itself.
