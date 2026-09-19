# perigraph

**περί** (around) + **γραφή** (record) — a record of what surrounded the model.

A protocol for carrying the harness: the instruction, the tools offered, the loop, the turn budget, the retry
policy, how the answer was read out, the decoding settings, and how contexts were partitioned. It exists because
**the thing around the model moves accuracy more than the choice of model moves cost**, and one of the two had a
name in the record.

The measurement this was built from: same model, same 1,187 items, one sentence of the instruction changed.

| condition | accuracy |
|---|---|
| `Answer with the option letter only. Do not explain.` | **0.6243** |
| the same question, asked to explain | **0.7447** |
| per-item agreement between them | 0.7346 — **one item in four flips** |

**Twelve points from one sentence.** The best cost saving from routing between models in the same study was
withdrawn, because it was a saving over 90 shared items against that project's own floor of 150 for reporting a
comparison at all.

## What it is not

**Not a logging format, and not an evaluation framework.** It carries the facts a claim about accuracy or cost
needs in order to be checkable, and it is deliberately unopinionated about what you then claim.

**Not a standard.** It is a spec with two implementations by one author, published in the hope that the shape is
right. The `spec/` directory is normative; this README is not.

Writing the second implementation found **five sentences that read two ways**, one of them fatal to interoperability:
the identity's serialisation was never specified, so two conformant senders would have produced two identities for one
run. All five are fixed and pinned by fixtures. See [docs/ambiguities.md](docs/ambiguities.md) -- four of the five were
invisible from inside the first implementation, whose tests all passed before and after.

## The design in one table

Four pieces are borrowed. Eight specifications were read first, and **none of them carries a per-part content
digest** — every one identifies by name and version, which is the failure this project measured twice.

| Role | Borrowed from |
|---|---|
| Attribute names, carriage, zero-code injection | OpenTelemetry GenAI semantic conventions |
| Naming a subject by a content digest | in-toto |
| Separating "who said this" from "is this true" | SCITT (RFC 9943) |
| Saying what a record does **not** cover | C2PA 2.1 |
| **Added**: a per-part content digest, labelled with the boundary it is over | nothing surveyed had one |
| **Added**: a per-part sourcing mode | nothing surveyed had one |

## The three rules everything else follows from

**1. Toward the sender, permissive. About itself, exact.**

Any part may be absent, in any combination, and the record is still valid — a collector that refuses a partial
record produces no record, and a run that emitted nothing is indistinguishable from a run that emitted a perfect
record of nothing. But the record must say whether the collector finished, and **a collector that failed must not
be able to present its failure as the sender's silence.** So every absence names whose it is:

| reason | blames |
|---|---|
| `not_provided` | the sender sent nothing |
| `not_reachable` | this collector, here, cannot see a thing that may well be there |
| `extraction_failed` | it was there and we failed |
| `redacted` | deliberately withheld |
| `not_observable` | nobody can see it |

The case this exists for is not the crude one. It is a shim losing the ability to read a part after an SDK renames
a field, and writing the same absence it writes when the sender genuinely sent none: every consumer then behaves
exactly as designed while the regression is invisible. **A closed vocabulary constrains spelling, not truth** — so
the collector also publishes what it claims it can reach, and a claim the record contradicts is an alarm rather
than a fact.

**2. Only what the model provably read can identify a run.**

A `tools` array, a `response_format` and the sampler settings are **protocol values**. The provider renders them
into the prompt however it likes, or not at all, and the sender does not hold that rendering. So they are recorded
and cannot key an identity, and **a harness read from a request body is identified by its instruction and nothing
else.**

Canonicalising is forbidden for the instruction and allowed for the values beside it. **The difference is who
reads them:** a model reads a string, not a meaning, and whitespace in an inlined tool definition can change
behaviour — while a machine reading a sampler setting cannot tell two spellings apart.

**3. Evidence can refuse a comparison and can never authorise one.**

Two runs' tool traces diverging on the same occasion — the tool, the trace prefix before the call, the arguments,
the credentials class, the attempt number — is evidence of divergent recorded execution. It is never proof of a
different tool. And agreement says nothing at all, because the occasions neither run exercised are unobserved
either way.

This one-sidedness is what makes the remaining hole safe: two serialisations of the same logical arguments compare
unequal, so a real difference is **missed**. A rule that could authorise would turn that miss into a false licence.

## Status

| | |
|---|---|
| `spec/vocabularies.json` | normative, version 1 |
| `SPEC.md` | the prose that goes with it |
| Python sender and receiver | implemented, 37 tests |
| TypeScript sender | implemented, 29 tests |
| `spec/fixtures/identity.json` | golden identities both implementations reproduce, including a non-ASCII one |
| Riding on a tracer's auto-instrumentation | not implemented -- one explicit `wrap` at the client boundary for now |
| A third implementation, by somebody else | none. **That is the remaining test** -- see [CONTRIBUTING.md](CONTRIBUTING.md) |

CI runs both suites on four Python versions and two Node versions, proves the spec ships **inside** each built package,
checks that the three copies of the normative JSON are byte-identical, and runs `tools/cross_check.py` -- **the only
check neither implementation can pass by agreeing with itself.**

## Relationship to the projects it came out of

Three records, and none of them holds another's:

| | holds the record of |
|---|---|
| a gateway | **the money.** What was charged. Its own documents say it does not assert quality |
| `perigraph` | **the surroundings.** What was around the model, and what the record cannot see |
| an evidence ledger | **the claim.** Whether what is recorded can support what is being said |

Keeping them apart is not tidiness. If the money ledger held the quality judgement, a judgement that changed later
would change a charge that must not; if the evidence ledger held the money, every "cannot decide" would stop a
charge that should not be stopped.

## Licence

Apache-2.0.
