# perigraph, version 2

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

**An absent record is never a clean one.** A record can also be lost after it is emitted: a bounded queue drops it, an
exporter samples it away. A sender that can lose records SHOULD report how many it lost, and a receiver reads a loss
nobody reported as **unknown, never as zero**. Otherwise fewer records than runs reads as a population with nothing
wrong in it.

### 1.1a How a fact reached the record

Closed, and the four are **not interchangeable**: they differ in what the fact may support.

| sourcing | what it means | may key an identity |
|---|---|---|
| `in_the_request` | the bytes are held. It *is* what was sent: verifiable and contemporaneous | **yes** |
| `loaded_by_us` | the collector runs in the process that loaded the model and digested what it loaded, during this load. Only a model part can have it (section 9) | the **model** identity only |
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

The rule is not limited to parts. **Any claim a receiver cannot check, whether a pushed part or a declaration that
travels beside the record, may trigger a refusal and may never lift one.**

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

A record's **harness identity** (`perigraph.harness_identity`, called `perigraph.identity` in version 1 and computed
exactly as before) is a digest over its identifying parts, sorted by part name. Section 9 adds a model identity and an
artifact identity beside it; "identity" alone in sections 2 to 6 means the harness identity. A part is identifying only when **all
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

**A digest names content, never a description of it.** A digest that cites a file is over the file's bytes as stored,
which pins a list of ids and their contents together. Two digests are compared as whole strings. A truncated digest, or
a digest over a summary of the content, can agree while the content differs.

### 2.5 What the harness identity cannot tell apart, and what now does

The harness identity is over the harness, not the weights. Two precisions of one checkpoint, bf16 and int8 for example,
served under one model name share every harness part, and an answer read from option scores shares a `readout` with one
parsed out of generated text. Version 1 said a receiver needing either distinction had to rely on a version string the
sender composed. Version 2 says it in the protocol instead: section 9's `precision` and `answer_mode` key the **model
identity**, so the two cases above are two model identities over one harness identity.

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

**Two arms grouped under one name that carry more than one model identity, or some with one and some without, MUST NOT
be given one verdict.** A retrain from the same script and seed agreed with its predecessor on 93.4% of labels; pooled,
the rate describes neither.

**A claim bound to a model identity MUST NOT be applied to records that do not carry that model identity.** A
certificate over answers from a model that no longer exists is a certificate over a different model.

**Two model identities from different collectors or collector versions MUST NOT be compared.** `precision` and
`runtime` are each collector's rendering, so the same model can digest differently in two of them. Compare the
artifact identity instead, which is over file bytes anybody holding the files computes alike.

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

`perigraph.harness_identity`, `perigraph.model_identity` and `perigraph.artifact_identity` MUST each be **omitted** when the record has none. An empty string compares equal to another empty
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

**Version 2** is breaking on four counts: four entries in `must_refuse`, a new sourcing value that may key an identity,
the attribute `perigraph.identity` renamed `perigraph.harness_identity`, and the model half, which a version-1 reader
would drop -- and a dropped model absence is a hole nobody knows exists. The harness identity's computation and the
version-1 identity fixtures are unchanged, so a version-1 identity value carries over as the harness identity.

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

**Every implementation MUST reproduce `spec/fixtures/identity.json` and `spec/fixtures/model_identity.json`.** It is the only part of conformance that a second
implementation cannot pass by agreeing with itself.

**Neither is conformant on the strength of this document alone.** There is one implementation, so the spec has not yet
been tested as a spec — the first genuine test of it is a second implementation disagreeing about what a sentence here
means.

## 9. What answered: the model parts

A record may carry a **model half**: the parts of what answered, as opposed to what surrounded it. It is written by a
collector **in the process that loaded the model**, and stamped on every answer, because only that process holds the
bytes. A request never carries weights, so a model part is never `in_the_request`, and a harness part is never
`loaded_by_us`.

| model part | what it is | content digested | needed because |
|---|---|---|---|
| `checkpoint` | every file the process read from the model artifact: parameters, adapters, tokenizer, chat template, configuration | for each file, sorted by the utf-8 bytes of its POSIX path relative to the artifact root, `<path>` TAB `<sha256 of the file>` LF; a path with a tab or a newline is refused | a retrain with the same script and seed agreed on 93.4% of labels under one name |
| `precision` | the numeric transform in force once loading finished, read off the loaded parameters | `dtype.<name>=<count>`, `quantisation=<scheme or none>`, `device=<type>`, one per line, sorted; `auto` is unresolved and is `extraction_failed` | dynamic int8 at load left the stored bytes unchanged and agreed on 33-40% |
| `runtime` | the code computing the answer | `<distribution>==<version>` for each package the collector declares it reads, resolved in-process, sorted | a rebuilt image lost packages; 97 of 100 answers agreed |
| `answer_mode` | where the answer is taken from | one of `generated_text`, `option_scores`, `classifier_output` | a student trained on option scores generated "1111" |

**Two identities.** The **model identity** is the section 2.2 serialisation over all four model parts, each
`loaded_by_us` with a digest; with any one missing there is no model identity, since one without `precision` would let
the int8 model wear the bf16 identity. It is **collector-local**, as a `parsed` digest is (section 2.3). The **artifact
identity** is the same serialisation over `checkpoint` alone, and compares across collectors: it is what a trainer can
compute when it saves a model, and what a lineage document (section 10) names.

**What may key them.** Only `loaded_by_us`. A digest cached from an earlier load is `pulled_by_us`, with a lag equal to
its age. A router or gateway that forwards a backend's stamp verbatim keeps its sourcing; one that reads the stamp back
over a separate request has `pulled_by_us`, and the stamp it read may be another replica's.

**Absence.** A model half uses the same absence reasons and blame rules as the harness half. A model behind a
provider's API has every model part `not_observable` and no model identity. That record stays admissible: a receiver
MUST NOT refuse it for having no model identity, and its claims are simply not bound to model bytes.

**What it cannot see.** A sender that digests the wrong files, or declares a runtime list that misses a library that
matters, produces a confident wrong identity; a closed vocabulary constrains spelling, not truth. Re-serialising
identical tensors changes the checkpoint digest, which errs in the safe direction. Batch-dependent or nondeterministic
kernels are not separated by any identity here.

## 10. Lineage: how a tuned model came to be

A **lineage document** is written by the trainer about one artifact, outside any record. It is never identifying --
two trainings that produced the same bytes are the same model -- and always pushed, so section 1.1a applies: it may
trigger a refusal and may never lift one.

| field | form |
|---|---|
| `spec_version` | `2` |
| `subject` | the artifact identity this document is about |
| `parent` | the parent's artifact identity, or `none` for a `pretrained` artifact |
| `method` | one of `pretrained`, `sft`, `distillation`, `rl`, `merge`, `reserialisation` |
| `sets` | `{role, digest}` with role `trained_on` or `consulted` and the sha256 of the set's manifest file |
| `signal` | for `distillation` and `rl`, required: one `{artifact_identity | digest | label: value}`; a label is unverifiable and never matches |
| `trainer` | a label |

A lineage whose `subject` is not the artifact observed is read as absent. A receiver checking whether a model was trained
on some items walks the `parent` chain: a quantised or merged child lists no sets of its own while its parent may have
trained on the very items in question. A missing ancestor, or a cited set nobody can open, is **unknown, never clean**.
There is no `excluded` role, because by the rule above it could only ever lift a refusal.

## 11. Switching (not normative)

perigraph identifies what ran and refuses claims that do not follow from the record. It does not switch, and it does not
say what to switch to: routers do. In the deployment it was designed with, Prismyra stamps its own answers with all four
model parts; a vLLM backend is stamped by middleware in its own process (a wrapper that hashed a directory before launch
is `pulled_by_us` and keys nothing); vLLM Semantic Router and the stratoclave gateway forward a backend's stamp verbatim
and add their own decision as a label; a model behind a provider's API is `not_observable`. A receiver such as tierbook
composes nothing from these attributes: it is handed opaque version strings that the emitters compose, recommended as
`perigraph/2/model/<model identity>` for what answered and `perigraph/2/artifact/<artifact identity>` for what a trainer
produced, and its own conformance test binds its refusals to `receiver_obligations`.

