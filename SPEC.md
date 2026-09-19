# perigraph, version 1

Normative. Where this document and `spec/vocabularies.json` disagree, **the JSON is correct** — it is what both sides
read, and a prose copy of a list is how two sides drift.

A **sender** produces records. A **receiver** consumes them. An implementation may be either or both, and conformance is
claimed separately for each.

## 1. The record

A record describes **one run**, and carries four things: the parts held, the parts absent, the collector's own manifest,
and the collector's terminal status. Nothing else is required, and a record missing every part is still a record.

### 1.0 The parts

Closed. **A part nobody named is a part that can change without the identity changing**, which is the defect the whole
vocabulary exists to close, so a value outside this list is refused rather than accepted with a warning.

| part | what it is | usual sourcing |
|---|---|---|
| `instruction` | the system prompt, as text | `in_the_request` |
| `tool_schemas` | which tools were offered, and their declared shapes | `in_the_request` |
| `tool_extension` | what those tools actually do, as functions | `not_observable` |
| `tool_trace` | the calls that actually happened | `in_the_request`, after the fact |
| `loop` | the scaffold: how calls are sequenced, what ends the run | `pushed_by_owner` |
| `turn_budget` | how many turns it may take | `pushed_by_owner` |
| `retry_policy` | what it retries and how often | `pushed_by_owner` |
| `readout` | how the final answer is taken out of the reply | `in_the_request` |
| `decoding` | temperature, top-p, and whether output is grammar-constrained | `in_the_request` |
| `context_partitioning` | how many contexts exist and what crosses between them | `pushed_by_owner` |

**Why `readout` and `decoding` are parts rather than details.** A mis-set readout convention has been measured to put
**1,822 of 2,364** answers on one option, every one well formed -- a record that did not name the readout would report
that as the model's behaviour. And the sampler settings decide whether the same input can give the same output at all.

**Why the four pushed parts are here despite being unverifiable.** A request body has no place to put them, so their
absence is the **sender's** rather than the collector's, and saying which is the whole point of section 1.2. Recording an
unverifiable claim and marking it unverifiable is worth more than omitting it: `context_partitioning` in particular
carries a published 39.2% saving (section 5), and the other nine parts cannot express it.

### 1.1 The two refusals are about different objects

> **Toward the sender, permissive. About itself, exact.**

A sender MUST NOT refuse to emit a record because parts are missing. A collector that refuses a partial record produces
no record, and **a run that emitted nothing is indistinguishable from a run that emitted a perfect record of nothing** —
the absence of a record is the one thing nobody can notice.

A sender MUST report its own terminal status truthfully. `complete`, `aborted`, `collector_failed`. A collector that
crashed MUST still emit a record, with status `collector_failed`, because **a collector cannot record its own absence.**

A receiver MUST refuse a verdict over a record whose status is not `complete`, and MUST NOT refuse to store it.

### 1.1a How a fact reached the record

Closed, and the four are **not interchangeable**: they differ in what the fact may support.

| sourcing | what it means | may key an identity |
|---|---|---|
| `in_the_request` | the bytes are held. It *is* what was sent: verifiable and contemporaneous | **yes** |
| `pulled_by_us` | fetched, so verifiable and **not contemporaneous** | no |
| `pushed_by_owner` | a declaration the receiver cannot check | no |
| `not_observable` | no mode reaches it | no |

**A `pulled_by_us` part MUST carry its read lag in seconds, and no other sourcing may.** We read at one moment and the
request ran at another, and everything that changed in between is invisible: **a lag nobody wrote down is a lag nobody
can bound**, and an unbounded lag cannot support a per-request claim. A lag on a part from the request is meaningless,
because bytes in the request have no lag by definition, and a lag on a pushed claim is the owner's word rather than a
measurement.

**A `pushed_by_owner` part can only subtract confidence.** A session that caches a tool list at connect time and runs
after the owner's signed change window used the old shapes while the record says the new ones -- undetectably, because
the absence of observation is what admits the channel in the first place. So a pushed fact may **widen** a verdict to
unknown and may never narrow one.

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

### 2.2 How the identity is computed

Every field here was added **because a second implementation could not interoperate without it.** None of it was in
version 1 as first written, and the identity agreed across the two reference senders only because the second author had
read the first's source.

| | |
|---|---|
| algorithm | `sha256` |
| encoding | `utf-8` -- see below, this is the one that fails silently |
| identity length | the first **24** characters of the lowercase hex |
| serialisation | for each identifying part, **sorted by part name ascending**, append the utf-8 bytes of `<part_name>=<content_digest>;`. Digest the concatenation. |

**The encoding is the entry that would have been silently wrong.** An implementation choosing UTF-16 produces a
different identity for every non-ASCII instruction **while passing every test it wrote for itself**, because a test
suite written in English never exercises the difference. `spec/fixtures/identity.json` therefore contains an instruction
in Japanese, and it is the only case in that set which can fail for this reason. An implementation that does not run the
fixtures has not checked this.

**Where several system messages are present**, join their contents with a single U+000A in the order they appear. This
is normative rather than a collector's choice, because the instruction digest keys the identity and two collectors
choosing differently would give two identities for one request.

### 2.3 A `parsed` digest is collector-local

**A `parsed` digest is comparable only against another digest from the same collector at the same version.** A receiver
MUST refuse a comparison across collectors or versions.

This is stated rather than legislated because there is nothing neutral to legislate. The two reference senders disagree:
Python's `repr` renders `0.0` as `0.0` and JavaScript's `JSON.stringify` renders it as `0`, and picking either is
picking one language's conventions for everybody.

Nothing that matters is lost, because a `parsed` digest can never key an identity. What was at risk before the rule
existed is somebody comparing two and **concluding the harnesses differed** -- precisely the false positive this
protocol exists to prevent.

### 2.4 Canonicalisation

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

## 4. What a receiver may compare

The refusals in sections 1 to 3 are about one record. These are about two, and each exists because a published number
needed withdrawing.

**Two arms whose decisions were missing different facts MUST NOT be compared.** Missingness is not a nuisance term: a
fact that was absent for one arm and present for the other **changed which candidate was tried**, so part of the
difference between them was caused by the gap rather than chosen by the policy. The delta is then an artefact correlated
with whichever arm was collected worse, and adaptive escalation makes it worse still by loading the harder items into the
later tiers.

**An arm that recorded no missingness is not an arm with no gaps.** Reading it as one attributes everything to the
policy, and the arm collected worse is the one most likely to have recorded nothing. Two arms that both recorded nothing
may be compared, because refusing them would refuse every record written before the field existed.

**Recording a fallback does not license the comparison.** Recording puts the fact in the log, and the log is not where a
verdict reads admission from.

**Two conversations of different turn counts MUST NOT be compared as two prices for the same work.** The cache discount
attaches to the shape of a request rather than to its text -- identical content measured a 0% cache rate as one long
message and 99.9% as a growing conversation -- so most of the difference between a one-turn arm and a five-turn arm is
the turn count. A routing decision changes the shape of every turn after the one it moved, which is why a routing verdict
is exactly the claim that needs this refusal.

**A statement of what an alternative would have cost is refused when either side's `context_partitioning` is
unrecorded.** That is **undefined rather than uncertain**, and the difference decides the remedy: an unmeasured quantity
can be measured later from the same record, and an undefined one cannot, because the record does not contain the
question.

## 5. Cost, and why it is here at all

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

## 6. The wire form

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

`perigraph.collector_reaches` is a comma-separated list of part names, and **an empty manifest is the empty string**.
Part names contain no commas -- they come from a closed vocabulary -- so the separator is unambiguous, but a reader
MUST drop empty entries: splitting `""` on `","` yields a single empty string in every language tried, which is a
manifest claiming a part named empty-string, and that refuses the whole record.

## 7. Versioning

**`spec_version` is a single integer and there is no minor version.** A protocol whose compatibility rules are
negotiable is a protocol two implementations disagree about quietly, and this one has already been through that once.

**These are breaking, and each requires a new `spec_version`:**

- removing or renaming a value in any closed vocabulary;
- changing what a value **means**, including which values may key an identity;
- changing anything in section 2.2 -- the algorithm, the encoding, the length, the serialisation, or the join;
- adding an entry to `receiver_obligations.must_refuse`, because a receiver that does not implement it is no longer
  conformant while still claiming the same version.

**These are not breaking:**

- adding a value to a closed vocabulary **whose meaning is a refusal a receiver already performs**;
- adding an optional attribute a receiver may ignore without dropping an absence;
- any change to a `note` or a `rationale`.

**A receiver meeting an unknown version refuses the record** (section 6). It does not downgrade, and it does not parse
what it recognises: the fields it would drop are the ones that say what the record cannot see.

**A sender MUST NOT emit two versions from one collector version.** If it can produce either, it is two collectors and
its manifest must say which one ran.

## 8. Conformance

**A sender conforms** when it emits records satisfying sections 1, 2 and 5, and when its vocabularies match
`spec/vocabularies.json` exactly.

**A receiver conforms** when it implements every refusal in `receiver_obligations.must_refuse` and none of the ones in
`must_not_refuse`. A receiver for which an obligation is **unreachable** -- it never performs the comparison the
obligation is about -- may say so instead of implementing it, and MUST be able to **demonstrate** the unreachability.
Asserting it is a loophole; one of the two reference receivers does this for the `parsed`-digest comparison and proves
it by showing that the only comparison it performs reads identifying parts, which are `model_visible` by construction.

**Every implementation MUST reproduce `spec/fixtures/identity.json`.** It is the only part of conformance that a second
implementation cannot pass by agreeing with itself.

**Neither is conformant on the strength of this document alone.** There is one implementation, so the spec has not yet
been tested as a spec — the first genuine test of it is a second implementation disagreeing about what a sentence here
means.
