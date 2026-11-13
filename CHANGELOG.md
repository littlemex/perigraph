# Changelog

Versions here are the **package** version. The **protocol** version is `spec_version` in
`spec/vocabularies.json`, and [SPEC.md section 7](SPEC.md) says what forces it to change.

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
