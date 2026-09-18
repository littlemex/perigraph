# perigraph, version 1

Normative. Where this document and `spec/vocabularies.json` disagree, **the JSON is correct** — it is what both sides
read, and a prose copy of a list is how two sides drift.

A **sender** produces records. A **receiver** consumes them. An implementation may be either or both, and conformance is
claimed separately for each.

## 1. The record

A record describes **one run**, and carries four things: the parts held, the parts absent, the collector's own manifest,
and the collector's terminal status. Nothing else is required, and a record missing every part is still a record.

### 1.1 The two refusals are about different objects

> **Toward the sender, permissive. About itself, exact.**

A sender MUST NOT refuse to emit a record because parts are missing. A collector that refuses a partial record produces
no record, and **a run that emitted nothing is indistinguishable from a run that emitted a perfect record of nothing** —
the absence of a record is the one thing nobody can notice.

A sender MUST report its own terminal status truthfully. `complete`, `aborted`, `collector_failed`. A collector that
crashed MUST still emit a record, with status `collector_failed`, because **a collector cannot record its own absence.**

A receiver MUST refuse a verdict over a record whose status is not `complete`, and MUST NOT refuse to store it.

### 1.2 Every absence names whose it is

A single undifferentiated hole is not conformant. The case this exists for is not a shim that crashes; it is **a shim
that loses the ability to read a part after an SDK renames a field, and writes the same absence it writes when the
sender genuinely sent none.** Every consumer then behaves exactly as designed while the regression is invisible.

`not_provided` and `redacted` blame the **sender**. `not_reachable` and `extraction_failed` blame the **collector**.
`not_observable` blames **nobody** and is structural.

An absence that blames the collector MUST carry a detail: a measurement failure nobody described is one nobody can fix.
An absence that does not blame the collector MUST NOT carry one: there is no moment for us to describe.

### 1.3 The manifest, and what a contradiction is

The manifest states what the collector claims it can reach **here**. It MUST be static per collector version: a manifest
that adapted to what it happened to find could never contradict a record, and contradicting one is the only thing it is
for.

**A contradiction is the manifest claiming a part that the record then reports `not_reachable`, or says nothing about at
all.** It is NOT the sender's silence — a manifest claims *"I can reach this if it is there"*, not *"this will be
there"*, and reading the difference as a contradiction blames the collector for a request that simply carried nothing.

`extraction_failed` is **consistent** with the claim: the capability exists and failed on this input.

A receiver MUST refuse a verdict over a record with a contradiction, because no absence in such a record can be read at
face value.

## 2. Identity

A record's identity is a digest over its identifying parts, sorted by part name. A part is identifying only when **all
three** hold:

1. its sourcing is `in_the_request` — the bytes are held, so the fact *is* what was sent;
2. its boundary is `model_visible` — it is the text the model read, not a protocol value;
3. its part name is not in `never_identifying`.

A record with no identifying part **has no identity**. This is not an error in the record: parts that identify nothing
are still facts worth keeping. It is an error to ask such a record for an identity, and a receiver MUST refuse a verdict
over one, because an identity constant across every possible harness groups things that have nothing in common.

### 2.1 The three boundaries, and why the middle one is the trap

| boundary | keying an identity on it |
|---|---|
| `transport` | **splits runs that were identical** — two client versions serialise differently and decode to the same text |
| `parsed` | **merges runs that were not** — two strings that canonicalise to one value can behave differently embedded verbatim in a prompt |
| `model_visible` | correct |

The two mistakes run in **opposite directions**, so neither is fixed by being careful. A digest MUST declare its
boundary.

### 2.2 Canonicalisation

A sender MUST NOT canonicalise a `model_visible` payload before digesting it. A model reads a string, not a meaning, and
one sentence's wording moved measured accuracy by 12.04 points.

A sender MAY canonicalise a `parsed` payload. **The difference is who reads them:** a machine reading a sampler setting
cannot tell two spellings apart.

A sender MUST NOT digest a payload after transmission. That hashes something other than what was sent.

## 3. Evidence about tools

`tool_extension` — what a tool actually does — is `not_observable`. A tool's implementation can change behind an
unchanged schema and nothing in the request differs.

`tool_trace` — the calls that actually happened — is bytes the sender holds, and **MUST NOT key an identity anyway.** A
per-run outcome is unique per run, so keying on it makes every pair of runs incomparable.

### 3.1 Occasion, not arguments

Two calls are comparable only when their **occasion** matches: the tool, the digest of the trace **before** the call, the
arguments digest, the credentials class, and the attempt number.

Matching on arguments alone is not conformant, and each of these is disqualifying on its own:

- it fires against a **single run** — write a key, then read it: equal arguments, unequal responses, one tool behaving
  correctly;
- it fires on **essentially every networked tool**, because request ids and timestamps sit in response bodies, so an
  always-firing rule means no harness with a real tool can ever be compared;
- its conclusion is **false even where firing is right** — a clock or a moved index makes the environments differ
  without the tool changing.

A response digest SHOULD be over the response **as rendered to the model**, which is a stable projection rather than the
raw body.

### 3.2 A divergence licenses less than it looks like

A divergence on the same occasion is evidence of **divergent recorded execution**, never proof of a different tool.

| the tool's declared contract | licence |
|---|---|
| `declared_deterministic` | **refuse** the comparison — a promise was broken |
| `known_to_vary` | **unknown** — widen the verdict |
| `unstated` | **unknown** — nobody promised anything, so nothing is contradicted |

`known_to_vary` and `unstated` license the same thing and are separate values: collapsing them lets a silence be
reported as a declared property of the tool.

**Agreement licenses nothing.** The occasions neither run exercised are unobserved either way, so this mechanism can
refuse a comparison and can never authorise one. That is what makes its known hole safe: two serialisations of the same
logical arguments compare unequal, so a real difference is *missed* — and a rule that could authorise would turn that
miss into a false licence.

## 4. Cost, and why it is here at all

Cost is in scope because **the cache discount attaches to the shape of a request rather than to its text**: identical
content measured a 0% cache rate as one long message and 99.9% as a growing conversation. A harness record that could
not express that would let a cache effect be reported as whatever the arms were supposed to differ in.

A price card bills **four** legs: `fresh_in`, `cached_in`, `cache_write`, `generation`. `cached_in` and `cache_write` are
all-or-nothing: recording one without the other leaves the fresh remainder wrong by exactly the leg omitted. **An
unrecorded split is not a zero cache rate.**

Cost belongs to a **conversation**, not a request: whether a turn's input is billed as a cache read depends on the turn
before it, so the cheapest turn in a sequence is cheap because an earlier one paid. The first turn of a context MUST NOT
report a cache read — nothing was in the context before it.

`context_partitioning` records how many contexts existed and what crossed between them. **Counting contexts is not
enough**: `briefs_and_results` keeps both caches warm and `whole_history` re-bills the entire prefix as fresh input in
the second context, and they differ in sign. Without it, "what would this have cost otherwise" is **undefined rather
than uncertain** — the record does not contain the question, so no amount of measuring recovers it.

## 5. The wire form

Flat, scalar, prefixed `perigraph.`, so it rides on a span any tracer already emits. Keys are in
`attributes` in the JSON.

Keys are indexed by **part name**, never by position: an integer index reorders when a collector learns to read one more
part, and every historical record then means something different.

`perigraph.identity` MUST be **omitted** when the record has none. An empty string compares equal to another empty
string, which would group every unidentifiable run together — the failure the identity rules exist to prevent,
reintroduced by the transport.

A receiver MUST refuse attributes whose `perigraph.spec_version` it does not implement, rather than parsing what it
recognises. A dropped field here is a **dropped absence**, which turns a hole the sender declared into a hole nobody
knows exists.

## 6. Conformance

**A sender conforms** when it emits records satisfying sections 1, 2 and 5, and when its vocabularies match
`spec/vocabularies.json` exactly.

**A receiver conforms** when it implements every refusal in `receiver_obligations.must_refuse` and none of the ones in
`must_not_refuse`.

**Neither is conformant on the strength of this document alone.** There is one implementation, so the spec has not yet
been tested as a spec — the first genuine test of it is a second implementation disagreeing about what a sentence here
means.
