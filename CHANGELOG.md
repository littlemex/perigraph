# Changelog

Versions here are the **package** version. The **protocol** version is `spec_version` in
`spec/vocabularies.json`, and [SPEC.md section 7](SPEC.md) says what forces it to change.

## Unreleased

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

Also: `spec/fixtures/identity.json`, the golden identities every implementation must reproduce, including one
non-ASCII case that exists solely to catch an encoding disagreement.

### Implementations

- Python sender and receiver.
- TypeScript sender.
- `tools/cross_check.py`, run in CI: the only check neither implementation can pass by agreeing with itself.
