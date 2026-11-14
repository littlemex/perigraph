# perigraph, version 3

perigraph is a record attached to one model call. It says what surrounded the model (the harness parts), what answered
(the model parts), how each fact reached the record, and which facts the record cannot see. Its purpose is to let a
receiver refuse a claim about accuracy or cost that the record cannot support.

## 0. Conventions

### 0.1 Requirement keywords

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT
RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 (RFC 2119, RFC 8174)
when, and only when, they appear in all capitals, as shown here. Lowercase "may", "must" and "is refused" are prose and
carry no requirement of their own.

### 0.2 What is normative, and what governs when sources disagree

Sections 0 to 10, 12 and 13 are normative, except paragraphs that begin **Rationale** or **Example**, which are
informative. Section 11 is informative. Documents under `spec/bindings/` are normative for the binding they name.

Where two sources disagree, they rank as follows, and the lower-ranked one is the defect:

1. `spec/vocabularies.json`, including the digest definitions in `digest` (`request_template_serialisation` among them) and
   `model_parts.rationale`;
2. `spec/fixtures/` and `conformance/cases/`;
3. the JSON Schemas under `spec/schema/`, which are generated from `spec/vocabularies.json` and checked against it;
4. this document.

The ranking exists because a prose copy of a list is how two implementations drift, and the files are what every
implementation reads.

### 0.3 Roles

A role is a set of obligations. One program may hold several roles, and conformance is claimed per role.

| role | what it does |
|---|---|
| **requester** | authors the request to the model. Blame value `sender` in `absence_reasons.blames` means the requester |
| **collector** | produces records. Its name and version are `perigraph.collector` and `perigraph.collector_version`; the name SHOULD be one its author controls, such as a repository path or a domain, because comparisons that are collector-local key on it |
| **stamper** | a collector in the process that loaded the model, and the only role that may originate a model part as `loaded_by_us` (section 9); a forwarder relays it |
| **forwarder** | a router or gateway that relays a stamper's model half without producing it (section 9) |
| **owner** | whoever makes a `pushed_by_owner` declaration about a part the request does not carry |
| **trainer** | writes a lineage document about an artifact it produced (section 10) |
| **receiver** | reads records and decides what they may support |

### 0.4 Terms

- **run**: one model call, one request and the answer to it. A record describes one run.
- **conversation**: a sequence of runs that share a context, so that one run's cache state depends on the runs before it.
- **arm**: a set of runs a receiver treats as one configuration under one name, for example one routing choice.
- **verdict**: a published claim about accuracy or cost drawn from records, for example "arm A is accurate enough" or
  "arm A is cheaper than arm B".
- **missingness**: which facts were absent from the records an arm's decisions were made on.
- **identifying part**: a part that keys the harness identity (section 2).
- **item**: the per-run text a requester places into a request template's holes, as opposed to the fixed strings
  around them.

### 0.5 What a receiver does with a record

A receiver uses only these four actions, and the requirements below say which applies:

| action | meaning |
|---|---|
| **reject** | the attributes do not parse as a record of a version the receiver implements. Nothing is stored |
| **store** | keep the record. A receiver MUST store every record it does not reject |
| **refuse a verdict** | publish no claim from this record, while still storing it |
| **refuse a comparison** | publish no claim that rests on comparing these two records or arms |

The outcome of asking for a verdict or a comparison is one of `admitted`, `refused` or `unknown`. `unknown` is the
outcome of a rule that widens a verdict (sections 1.1a and 3.2): it is never `admitted`, and a receiver publishes no
claim on it.

## 1. The record

A record describes **one run**. It carries the collector's name and version, the collector's manifest, the collector's
terminal status, the harness parts held and absent (sections 1.0 to 1.2), and the model half (section 9). A record that
holds no part at all, with every part absent, is still a record.

### 1.0 The parts

Closed. A receiver MUST reject a record that names a part outside this list. **Rationale**: a part nobody named is a part
that can change without anybody's record saying so. Of the named parts, only `instruction` and `request_template` key
the harness identity in practice, and `request_template` only beside another identifying part (section 2), so naming a part
is what makes its change recordable, not what makes it identifying.

| part | what it is | usual sourcing |
|---|---|---|
| `instruction` | the system prompt, as text | `in_the_request` |
| `request_template` | the fixed text the requester wraps around each item in the other messages, as the requester declares it in the request | `in_the_request` |
| `tool_schemas` | which tools were offered, and their declared shapes | `in_the_request` |
| `tool_extension` | what those tools actually do, as functions | `not_observable` |
| `tool_trace` | the calls that actually happened | `in_the_request`, after the fact |
| `loop` | the scaffold: how calls are sequenced, what ends the run | `pushed_by_owner` |
| `turn_budget` | how many turns it may take | `pushed_by_owner` |
| `retry_policy` | what it retries and how often | `pushed_by_owner` |
| `readout` | how the final answer is taken out of the reply | `in_the_request` |
| `decoding` | temperature, top-p, and whether output is grammar-constrained | `in_the_request` |
| `context_partitioning` | how many contexts exist and what crosses between them | `pushed_by_owner` |

**Rationale: why `request_template` is a part.** On one byte-identical checkpoint with no system message, wrapping
each item as `<instruction>\n\nHeadline: <item>` instead of sending the item alone moved measured accuracy by 4.58
points (95% interval 2.38 to 6.79), and appending an irrelevant block of about 150 tokens to the user message moved it
from 0.898 to 0.858. Version 2 read nothing from the user message, so neither change reached any part. Reading the whole
user message would make every item its own harness; the template names the text that stays fixed and leaves out the
item. Without a system message neither run has a harness identity in either version (section 2); what the part changes
is that the wrapper is recorded, and that two runs under one system message with different wrappers, a case not yet
measured, get two identities.

**Rationale: why `readout` and `decoding` are parts rather than details.** A mis-set readout convention has been measured to put
**1,822 of 2,364** answers on one option, every one well formed -- a record that did not name the readout would report
that as the model's behaviour. And the sampler settings decide whether the same input can give the same output at all.

**Rationale: why the four pushed parts are here despite being unverifiable.** A request body has no place to put them, so their
absence is the **sender's** rather than the collector's, and saying which is the whole point of section 1.2. Recording an
unverifiable claim and marking it unverifiable is worth more than omitting it: `context_partitioning` in particular
carries a published 39.2% saving (section 5), and the other ten parts cannot express it.

### 1.1 The two refusals are about different objects

> **Toward the sender, permissive. About itself, exact.**

A collector MUST NOT withhold a record because parts are missing. **Rationale**: a collector that refuses a partial record
produces no record, and **a run that emitted nothing is indistinguishable from a run that emitted a perfect record of
nothing**.

A collector MUST set `perigraph.status` to one of these:

| status | when |
|---|---|
| `complete` | the collector finished reading everything it reads |
| `aborted` | the collector stopped before finishing for a reason outside itself, for example because the run was cancelled |
| `collector_failed` | the collector stopped because of an error of its own |

Every failure path of a collector, including an exception raised inside it, MUST still emit a record with status
`collector_failed`, because **a collector cannot record its own absence**.

A receiver MUST refuse a verdict over a record whose status is not `complete`, and MUST store it.

**An absent record is never a clean one.** A record can also be lost after it is emitted: a bounded queue drops it, an
exporter samples it away. A collector that can lose records SHOULD report how many it lost, and a receiver MUST read a loss
nobody reported as **unknown, never as zero**. Version 3 defines no attribute that carries the count (section 6.1). Otherwise fewer records than runs reads as a population with nothing
wrong in it.

### 1.1a How a fact reached the record

Closed, and the five are **not interchangeable**: they differ in what the fact may support.

| sourcing | what it means | may key an identity |
|---|---|---|
| `in_the_request` | the bytes are held. It *is* what was sent: verifiable and contemporaneous | **yes** |
| `loaded_by_us` | the collector runs in the process that loaded the model and digested what it loaded, during this load. Only a model part can have it (section 9) | the **model** identity only |
| `pulled_by_us` | fetched, so verifiable and **not contemporaneous** | no |
| `pushed_by_owner` | a declaration the receiver cannot check | no |
| `not_observable` | no mode reaches it | no |

**A `pulled_by_us` part MUST carry its read lag in seconds, and a part with any other sourcing MUST NOT carry one.** The lag is a non-negative number: the time from the moment the collector read the fact to the moment it received the request, or zero if it read the fact after receiving the request. We read at one moment and the
request ran at another, and everything that changed in between is invisible: **a lag nobody wrote down is a lag nobody
can bound**, and an unbounded lag cannot support a per-request claim. A lag on a part from the request is meaningless,
because bytes in the request have no lag by definition, and a lag on a pushed claim is the owner's word rather than a
measurement.

**A `pushed_by_owner` part can only subtract confidence.** A session that caches a tool list at connect time and runs
after the owner's signed change window used the old shapes while the record says the new ones -- undetectably, because
the absence of observation is what admits the channel in the first place. So a receiver MAY let a pushed fact **widen** a verdict to
`unknown` and MUST NOT let one narrow it.

The rule is not limited to parts. **A receiver MAY let any claim it cannot check, whether a pushed part or a declaration that
travels beside the record, trigger a refusal, and MUST NOT let one lift a refusal.** A forwarded model stamp is the one
exception, and section 12.1 states the trust it requires.

### 1.2 Every absence names whose it is

A collector MUST emit each of the eleven parts and each of the four model parts as held or as absent. A receiver reads a part
that a record does not mention as unknown, and stores the record (`receiver_obligations.must_not_refuse`).

Every absence MUST carry one of the reasons below, and the reason MUST name whose absence it is. **Rationale**: the case this
exists for is not a shim that crashes; it is **a shim
that loses the ability to read a part after an SDK renames a field, and writes the same absence it writes when the
sender genuinely sent none.** Every consumer then behaves exactly as designed while the regression is invisible.

`not_provided` and `redacted` blame the **requester** (blame value `sender`). `not_reachable` and `extraction_failed` blame the **collector**.
`not_observable` blames **nobody** and is structural.

An absence that blames the collector MUST carry a detail: a measurement failure nobody described is one nobody can fix.
An absence that does not blame the collector MUST NOT carry one: there is no moment for us to describe.

**A request the collector cannot parse is an absence it names, not a record it withholds** (section 1.1). The rules in
the rest of this paragraph and the next are for a request in the OpenAI Chat Completions shape; `spec/bindings/openai-chat-completions.md`
maps its fields to parts, and other request shapes need their own binding. When the body
is not valid JSON, or is JSON that is not an object, a collector MUST give every manifest part read from the request body
as `extraction_failed`. When a field a part is read from is present but not of the JSON type the collector expects -- for
example `messages` or `tools` that is not an array, an entry of either that is not an object, a message whose `role` is
missing or is not a string, or a `response_format` that is not an object -- every manifest part read from the top-level
field holding the defect is `extraction_failed`, even if the entries it needs are readable, because the unreadable entry
might have been one of them. A system message's `content` is narrower: it fails `instruction` only (section 2.2). A
top-level field that is missing or `null` is not this case: the request carries none, which is what a client that
serialises an unset optional field as `null` means. Parts read from anywhere else are unaffected. Each such absence
carries a detail naming the body or the field, the entry's index where there is one, and the JSON type found, or
`missing`, or, for a body that is not JSON, that it did not parse; it never quotes the value. The record's status is `complete`, never `collector_failed` for this cause: that status is for a
collector that did not finish, and this one finished and named what it could not read.

**An empty request field is a missing one.** For a request template the test is applied only after the template has
passed every check of its binding, so an empty template the request contradicts is still `extraction_failed`. An `instruction` that is empty after removing leading and trailing white
space, a `tools` array with no entries, a `response_format` object with no members and a request template none of whose
fixed strings contain a character that is not white space are each treated as not sent; a part is `not_provided` only when
everything it is read from is missing or empty. The white-space removal is for this
test only: a non-empty instruction is digested as section 2.2 says. The rule covers these four and nothing else; an
empty `precision` value is `extraction_failed` (section 9). A `response_format` is read by both `readout` and
`decoding`: it says how the answer is taken out, and it constrains the grammar of the output. **White space**, here and
in section 9, is the Unicode `White_Space` property: U+0009-U+000D, U+0020, U+0085, U+00A0, U+1680, U+2000-U+200A,
U+2028, U+2029, U+202F, U+205F and U+3000, listed in `white_space.code_points`. It is named because the default
trim of each language tried strips a different set (U+001F and U+FEFF among the differences), and this test decides
whether a part exists.

### 1.3 The manifest, and what a contradiction is

The manifest (`perigraph.collector_reaches`, and `perigraph.model_reaches` for the model half) states what the collector
claims it can reach **here**. The manifest MUST be static per collector version. **Rationale**: a manifest that adapted to what it
happened to find could never contradict a record, and contradicting one is the only thing it is for.

**A contradiction is the manifest claiming a part that the record then reports `not_reachable`, or says nothing about at
all.** It is NOT the sender's silence — a manifest claims *"I can reach this if it is there"*, not *"this will be
there"*, and reading the difference as a contradiction blames the collector for a request that simply carried nothing.

`extraction_failed` is **consistent** with the claim: the capability exists and failed on this input.

A receiver MUST refuse a verdict over a record with a contradiction in either manifest, because no absence in such a
record can be read at face value.

## 2. Identity

A record's **harness identity** (`perigraph.harness_identity`, called `perigraph.identity` in version 1 and computed
exactly as before) is a digest over its identifying parts, sorted by part name. Section 9 adds a model identity and an
artifact identity beside it; "identity" alone in sections 2 to 6 means the harness identity. A part is identifying only when **all
three** hold:

1. its sourcing is `in_the_request` — the bytes are held, so the fact *is* what was sent;
2. its boundary is `model_visible` — the text the requester supplied for the model to read, as opposed to a protocol value.
   It is the text before any chat template the server applies and before any prompt a provider adds, which the requester
   does not hold;
3. its part name is not in `never_identifying`.

A record **has no identity** when any of these holds:

- it has no identifying part;
- every identifying part it has is in `refines_only`. Such a part names text whose division from the item is the
  requester's declaration, which nobody can check. Beside another identifying part it can only split runs that part
  would join; alone it would give an identity to runs version 2 gave none, on the requester's word, and section 1.1a
  forbids an unverifiable claim to lift a refusal;
- a part in `must_be_known_for_identity` is neither held, in any sourcing, nor absent with the reason in
  `known_when_absent_as`, which is `not_provided`. A part the collector failed to read, could not reach, withheld as
  `redacted`, or did not mention might have been there, and an identity computed without it would join runs that differ
  in it. A part held with another sourcing satisfies this and keys nothing, which gives the identity a record without
  it would have; a receiver MAY refuse on it as on any claim it cannot check (section 1.1a).

In the OpenAI Chat Completions binding only `instruction` and `request_template` can be identifying, so a request with
no system message whose content is a string has no harness identity whatever template it declares, and a receiver
refuses a verdict over its record (below). This is the cost of keying only on bytes the requester holds. This is not an error in the record: parts that identify nothing
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

A `request_template` digest is `model_visible`: it is over text the requester supplied for the model to read, raw,
framed by `digest.request_template_serialisation`, which adds the entry count, each entry's role and the lengths. Because
the requester decides where the holes are, it can split runs whose model input was identical -- `["A", "B"]` and
`["AB"]` over the content `AB`, or the same messages with and without a template -- and because it counts every
message, untemplated ones included, any change in the number or the roles of the messages splits it too, including
the trailing assistant and tool messages of a tool loop, which are a run's outcome. Both are the safe direction. It never
joins two runs whose fixed strings differ, except that two templates fixing only white space are both treated as not
sent (section 1.2).

### 2.2 How the identity is computed

**Rationale**: every field here was added because a second implementation could not interoperate without it.

| | |
|---|---|
| algorithm | `sha256` |
| encoding | `utf-8` -- see below, this is the one that fails silently |
| identity length | the first **24** characters of the lowercase hex |
| serialisation | for each identifying part, **sorted by part name ascending**, append the utf-8 bytes of `<part_name>=<content_digest>;`. Digest the concatenation. |

**Rationale: the encoding is the entry that would have been silently wrong.** An implementation choosing UTF-16 produces a
different identity for every non-ASCII instruction **while passing every test it wrote for itself**, because a test
suite written in English never exercises the difference. `spec/fixtures/identity.json` therefore contains an instruction
in Japanese, and it is the only case in that set which can fail for this reason. An implementation that does not run the
fixtures has not checked this.

**Where several system messages are present**, a collector MUST join their contents with a single U+000A in the order they
appear. This is not a collector's choice, because the instruction digest keys the identity and two collectors
choosing differently would give two identities for one request.

**A system message whose `content` is not a JSON string makes the whole `instruction` part `extraction_failed`**, even
when other system messages have string content. This covers an array of content parts, any other non-string JSON value
including `null`, and a message with no `content` at all. The detail names the first such message by its index in
`messages` and the JSON type found, or `missing`, and never quotes the content. The text a model reads from an array of
parts is decided by a chat template the request does not carry, so no rendering of the array is the model-visible bytes.

### 2.3 A `parsed` digest is collector-local

**A `parsed` digest is comparable only against another digest from the same collector at the same version.** A receiver
MUST refuse a comparison across collectors or versions.

**Rationale**: this is stated rather than legislated because there is nothing neutral to legislate. Two reference senders disagree:
Python's `repr` renders `0.0` as `0.0` and JavaScript's `JSON.stringify` renders it as `0`, and picking either is
picking one language's conventions for everybody.

Nothing that matters is lost, because a `parsed` digest can never key an identity. What was at risk before the rule
existed is somebody comparing two and **concluding the harnesses differed** -- precisely the false positive this
protocol exists to prevent.

### 2.4 Canonicalisation

A collector MUST NOT canonicalise a `model_visible` payload before digesting it. A model reads a string, not a meaning, and
one sentence's wording moved measured accuracy by 12.04 points.

A collector MAY canonicalise a `parsed` payload. **The difference is who reads them:** a machine reading a sampler setting
cannot tell two spellings apart.

A collector MUST NOT digest a payload after transmission. That hashes something other than what was sent.

**A digest names content, never a description of it.** A digest that cites a file is over the file's bytes as stored,
which pins a list of ids and their contents together. Two digests are compared as whole strings. A digest over a summary of the content can agree while the content differs,
and so can a truncated content digest. The identities are the one exception: each is the first 24 hex characters of a
sha256, which is 96 bits. That is enough to make an accidental collision negligible and is not a commitment against an
adversary who chooses the content (section 12.2).

### 2.5 What the harness identity cannot tell apart, and what now does

The harness identity is over the harness, not the weights. Two precisions of one checkpoint, bf16 and int8 for example,
served under one model name share every harness part, and an answer read from option scores shares a `readout` with one
parsed out of generated text. Version 1 said a receiver needing either distinction had to rely on a version string the
sender composed. Version 2 says it in the protocol instead: section 9's `precision` and `answer_mode` key the **model
identity**, so the two cases above are two model identities over one harness identity.

Version 2's harness identity also could not tell two user-message wrappers apart under one system message. Version 3
does when the requester declares the wrapper as a `request_template`. It still cannot tell apart what the requester puts
inside a hole: fixed text concatenated into the item before the template is applied is read as item. And a request with
no system message has no harness identity in any version, so the same instruction in the user message against no
instruction at all is two refused records, not two identities.

**Where several messages carry a template**, the serialisation is defined in `digest.request_template_serialisation`:
the number of entries, then each entry's role and fixed strings, every string length-prefixed in utf-8 bytes in decimal
with no leading zeros. It is not a collector's choice, for the reason the join above is not.

## 3. Evidence about tools

`tool_extension` — what a tool actually does — is `not_observable`. A collector MUST record it as an absence with reason
`not_observable`, not as a part with that sourcing, so that the harness half has one encoding for it. A tool's implementation can change behind an
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

The refusals in sections 1 to 3 are about one record. These are about two. Several of them read facts that the version 3
wire record does not carry (section 6.1); a receiver applies them to the data it holds about the arms.

**A receiver MUST refuse a comparison of two arms whose decisions were missing different facts.** Missingness is not a nuisance term: a
fact that was absent for one arm and present for the other **changed which candidate was tried**, so part of the
difference between them was caused by the gap rather than chosen by the policy. The delta is then an artefact correlated
with whichever arm was collected worse, and adaptive escalation makes it worse still by loading the harder items into the
later tiers.

**An arm that recorded no missingness is not an arm with no gaps.** Reading it as one attributes everything to the
policy, and the arm collected worse is the one most likely to have recorded nothing. Two arms that both recorded nothing
may be compared, because refusing them would refuse every record written before the field existed.

**Recording a fallback does not license the comparison.** Recording puts the fact in the log, and the log is not where a
verdict reads admission from.

**A receiver MUST refuse a comparison of two conversations of different turn counts as two prices for the same work.** The cache discount
attaches to the shape of a request rather than to its text -- identical content measured a 0% cache rate as one long
message and 99.9% as a growing conversation -- so most of the difference between a one-turn arm and a five-turn arm is
the turn count. A routing decision changes the shape of every turn after the one it moved, which is why a routing verdict
is exactly the claim that needs this refusal.

**A receiver MUST refuse a statement of what an alternative would have cost when either side's `context_partitioning` is
unrecorded.** That is **undefined rather than uncertain**, and the difference decides the remedy: an unmeasured quantity
can be measured later from the same record, and an undefined one cannot, because the record does not contain the
question.

**Records grouped as one arm MUST NOT be given one verdict when the distinct harness identities derived from them number
more than one, or number one while some record has none.** The identities are the ones a receiver derives (section 6),
not the ones a record states. One checkpoint answered 0.8983 with no instruction, 0.8608 with an instruction as the
system message and 0.8525 with the same instruction in the user message; pooled, the rate describes none of them. Of
those three runs only the second has a harness identity, so they are refused here as {one identity, some without};
two identities under one name is the case two wrappers under one system message would give. A receiver that gives a
verdict over the records of one identity within the arm MUST say how many records of the arm it left out. The rule
refuses every arm whose records were collected on both sides of a hop that removes a template (binding), and every arm
of conversations whose template grows with the turn count; both are the safe direction.

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

A receiver MUST reject attributes whose `perigraph.spec_version` it does not implement, rather than parsing what it
recognises. A dropped field here is a **dropped absence**, which turns a hole the sender declared into a hole nobody
knows exists.

A receiver MUST reject attributes that do not form a record of this version. That is the case exactly when:

- `perigraph.spec_version`, `perigraph.collector`, `perigraph.collector_version`, `perigraph.collector_reaches` or
  `perigraph.status` is missing, or a defined attribute has a value of the wrong JSON type;
- a part, model part, sourcing, boundary, absence reason, status or answer mode is outside the vocabulary, including a
  name in a manifest;
- one part is both held and absent, or an attribute of a part is present without that part's `sourcing` or `reason`;
- a harness part is `loaded_by_us`, a model part is `in_the_request`, or a part whose sourcing is `not_observable`
  carries a digest;
- a read lag or a detail is present where sections 1.1a and 1.2 forbid one, or missing where they require one, or a
  boundary is present without a digest or missing with one;
- a digest is not 64, or an identity not 24, lowercase hexadecimal characters, or an `answer_mode` digest is not the
  digest of its label;
- an identity is present and is not the one derived from the parts the attributes carry, including when the parts derive
  none (section 2).

A receiver derives each identity from the parts. An identity attribute is a check on that derivation, and a record that
omits one its parts derive is read with the derived value. **Rationale**: an identity is a derived value, and one that disagrees with its parts is a sender
that hashed something else -- reading it as given keys a comparison on bytes nobody can name. Keys under
`perigraph.ext.` are never grounds for rejection (section 13.2). `conformance/cases/receiver.json` has a case for each
ground. A receiver MUST NOT trim white space from a wire value before these checks.

`perigraph.collector_reaches` is a comma-separated list of part names, and **an empty manifest is the empty string**.
Part names contain no commas -- they come from a closed vocabulary -- so the separator is unambiguous, but a reader
MUST drop empty entries: splitting `""` on `","` yields a single empty string in every language tried, which is a
manifest claiming a part named empty-string, and that refuses the whole record.

**The list is a set.** A collector MAY emit the names in any order and SHOULD NOT repeat one; a receiver MUST count a
repeated name once and MUST compare two manifests as sets. `perigraph.model_reaches` is the same form for the model half.

**A collector that cannot observe the model says so.** A collector outside the process that loaded the model, with no
stamp to forward or read back (section 9) -- a request adapter, or a router or gateway in front of an unstamped backend
-- MUST emit each of the four model parts either as absent with reason `not_observable`
(`perigraph.model_absent.<part>.reason`) or, where it has a name for that part (a provider's model name names
`checkpoint` and no other part), as a part with sourcing `not_observable`, that name as its label, and no digest. The
form is chosen per part. Such a collector MUST NOT emit a model or artifact identity. The two forms say the same thing: neither keys
an identity, and a receiver treats them alike. A record with no model half at all does not conform (section 9) but is
not refused: it is a hole nobody named (section 1.2), indistinguishable from the record of a collector that loaded the
model and lost the stamp; a receiver reads it as unknown, not as `not_observable`, and MUST NOT refuse the record for
it.

### 6.1 What the version 3 wire record does not carry

Some requirements in sections 1, 4 and 5 read facts that have no attribute in version 3. A receiver applies those
requirements to the data it holds about the runs, and a record alone cannot show that it did:

| fact | read by |
|---|---|
| how many records the collector lost | section 1.1 |
| turn count and conversation membership | section 4 (turn counts) and section 5 |
| billed legs | section 5 |
| context crossings (`context_crossings`) | section 4 (cost of an alternative) and section 5 |
| occasion fields and a tool's declared determinism | section 3 |
| missingness of an arm's decisions | section 4 (missing facts) |

Carrying these on the wire is on the roadmap.

## 7. Versioning

This section states the policy as it stands. A formal versioning and compatibility policy for the interface is planned
and not yet in place; the questions it must settle are listed in section 7.1.

**`spec_version` is a single integer and there is no minor version.** A protocol whose compatibility rules are
negotiable is a protocol two implementations disagree about quietly, and this one has already been through that once.

**These are breaking, and each requires a new `spec_version`:**

- removing or renaming a value in any closed vocabulary;
- changing what a value **means**, including which values may key an identity;
- changing anything in section 2.2 -- the algorithm, the encoding, the length, the serialisation, or the join --
  except a change that only withdraws an identity (below);
- adding an entry to `receiver_obligations.must_refuse`, because a receiver that does not implement it is no longer
  conformant while still claiming the same version.

**These are not breaking:**

- adding a value to a closed vocabulary **whose meaning is a refusal a receiver already performs**. A receiver holding
  the older vocabulary rejects a record that uses the new value, which loses that record but never misreads it; how such
  a value reaches receivers is one of the questions of section 7.1;
- adding an optional attribute a receiver may ignore without dropping an absence;
- any change to a `note` or a `rationale`, except the digest definitions in `digest` and `model_parts.rationale`,
  which are section 2.2 and section 9 restated.

**A change that only withdraws an identity is not breaking**: after it, every input has either no identity or the
identity a sender built from this repository already gave it, and no sender's identity for an input changes to a
different one. A sender that gave none where another gave one may therefore come to give that one. An earlier and a
later record of the same input then differ only in that one has no identity, which a receiver reports as unidentified
and never reads as a difference. The changelog MUST list the inputs withdrawn. This exception holds only while every
known sender is built from this repository.

**A receiver meeting an unknown version rejects the record** (section 6). It does not downgrade, and it does not parse
what it recognises: the fields it would drop are the ones that say what the record cannot see.

**Version 3** is breaking on three counts: a new part, `request_template`, which a version 2 receiver rejects
(section 1.0); a new value that may key an identity, with the rules `refines_only` and `must_be_known_for_identity` that bound
it; and a new entry in `must_refuse`, one harness identity per arm (section 4). The harness identity of a record with no
`request_template` held is computed exactly as in version 2, so every version 2 identity fixture carries over and a
request that declares no template has the same harness identity in both versions from a collector that reads the
template member. A collector that cannot reach `request_template` gives no record an identity unless it can see that
the request carries no template. A version 2 receiver rejects every version 3 record by its `spec_version`, including
those; how populations that mix the two are read is a question of section 7.1. Lineage documents are unchanged except
for their `spec_version`, and a version 3 reader rejects a lineage document of version 2 as it rejects a record.

**Version 2** is breaking on four counts: four entries in `must_refuse`, a new sourcing value that may key an identity,
the attribute `perigraph.identity` renamed `perigraph.harness_identity`, and the model half, which a version-1 reader
would drop -- and a dropped model absence is a hole nobody knows exists. The harness identity's computation and the
version-1 identity fixtures are unchanged, so a version-1 identity value carries over as the harness identity.

**A collector MUST NOT emit two versions from one collector version.** If it can produce either, it is two collectors, and
its `perigraph.collector` or `perigraph.collector_version` MUST say which one ran.

### 7.1 Planned: the versioning and compatibility policy

Not yet in place. When written, it has to settle at least:

- how the wire `spec_version` relates to revisions of this text, of `spec/vocabularies.json`, of the schemas, the fixtures
  and the conformance cases, including a clarification that changes output under the same integer;
- how a value added to a closed vocabulary reaches a receiver that holds an older file, and when the receiver rejects;
- the identity-withdrawal exception above, which today relies on every known sender being built from this repository;
- populations that mix versions, receivers that implement several, and a forwarder relaying a newer stamp than it knows;
- whether the lineage document is versioned independently of the record;
- stability levels and deprecation for vocabularies and attributes, and how an extension (section 13) graduates.

## 8. Conformance

Conformance is claimed per role (section 0.3). The requirements are listed with identifiers in `spec/requirements.json`,
and `conformance/` holds cases and a runner any implementation can drive (`conformance/README.md`).

**A collector conforms** when the records it emits satisfy sections 1, 2, 3, 5, 6, 7 and 9, and when its vocabularies
match `spec/vocabularies.json` exactly. **A stamper** additionally satisfies section 9's rules for `loaded_by_us`, and
**a forwarder** section 9's rules for relaying a stamp.

**A receiver conforms** when it implements every refusal in `receiver_obligations.must_refuse` and none of the ones in
`must_not_refuse`, and also the receiver requirements stated elsewhere in this document: rejecting an unknown
`spec_version` and an out-of-vocabulary value (sections 1.0 and 6), dropping empty manifest entries (section 6), the
placement of read lags and details (sections 1.1a and 1.2), and, if it reads lineage documents, section 10. A receiver for which an obligation is **unreachable** -- it never performs the comparison the
obligation is about -- MAY say so instead of implementing it, and MUST then **demonstrate** the unreachability in the material that claims conformance.
Asserting it is a loophole. **Example**: a receiver that only ever compares harness identities can demonstrate that the
`parsed`-digest obligation is unreachable for it, because identifying parts are `model_visible` by construction.

**A collector MUST reproduce `spec/fixtures/identity.json`, and a stamper MUST reproduce `spec/fixtures/model_identity.json`.** It is the only part of conformance that a second
implementation cannot pass by agreeing with itself.

**No implementation is conformant on the strength of this document alone.** The sections say what is required; the fixtures and
`spec/vocabularies.json` are how that is checked, and where a fixture or `spec/vocabularies.json` and this text disagree
the file governs and the text is the defect. No implementation has yet been written by an independent person (`IMPLEMENTATIONS.md`).

## 9. What answered: the model parts

A collector MUST emit a **model half** on every record: each of the four model parts below, as a part or as a named
absence; together they are what answered, as opposed to what surrounded it. Its parts are digested only by a collector
**in the process that loaded the model**, which stamps them on every answer, because only that process holds the bytes;
a collector anywhere else forwards that stamp, reads it back, or reports the four parts `not_observable` (section 6). A
request never carries weights, so a model part is never `in_the_request`, and a harness part is never `loaded_by_us`.

| model part | what it is | content digested | needed because |
|---|---|---|---|
| `checkpoint` | every file the process read from the model artifact: parameters, adapters, tokenizer, chat template, configuration | for each file, sorted by the utf-8 bytes of its POSIX path relative to the artifact root, `<path>` TAB `<sha256 of the file's contents>` LF. The path is the path within the artifact, not the target of a symlink; the sha256 is over the bytes the path resolves to. A collector MUST give `extraction_failed` for a path containing a tab or a newline | a retrain with the same script and seed agreed on 93.4% of labels under one name |
| `precision` | the numeric transform in force once loading finished, read off the loaded parameters | `dtype.<name>=<count>`, `quantisation=<scheme or none>`, `device=<type>`, one per line, sorted; a dtype name, a `quantisation` value or a `device` value that, after removing leading and trailing white space (section 1.2) and comparing ASCII letters without case, is empty or equals `auto` is unresolved and makes the whole part `extraction_failed` (this normalisation is for the test only; values are digested as read) | dynamic int8 at load left the stored bytes unchanged and agreed on 33-40% |
| `runtime` | the code computing the answer | `<distribution>==<version>` for each package the collector declares it reads, resolved in-process, sorted | a rebuilt image lost packages; 97 of 100 answers agreed |
| `answer_mode` | where the answer is taken from: how the loaded process is configured to produce answers, fixed when the model is loaded | one of `generated_text`, `option_scores`, `classifier_output` | a student trained on option scores generated "1111" |

**Two identities.** The **model identity** is the section 2.2 serialisation over all four model parts, each
`loaded_by_us` with a digest; with any one missing there is no model identity, since one without `precision` would let
the int8 model wear the bf16 identity. It is **collector-local**, as a `parsed` digest is (section 2.3). The **artifact
identity** is the same serialisation over `checkpoint` alone, and compares across collectors. A trainer computes it at
save time over the files the served model will read, which excludes files only training uses, such as optimiser state;
a lineage document (section 10) names it.

**What may key them.** Only `loaded_by_us`, written by a stamper. A digest cached from an earlier load is `pulled_by_us`, with a lag equal to
its age. A forwarder that relays a stamper's model half verbatim keeps its sourcing; one that reads the stamp back over a
separate request has `pulled_by_us`, and the stamp it read may be another replica's. A receiver cannot check a relayed
stamp, so accepting one is a statement of trust in the forwarder (section 12.1). Version 2 defines no carrier for the
stamp between a stamper and a forwarder, and the forwarder's record carries the forwarder's own `perigraph.collector`
and version, so the collector-local comparison of model identities (section 4) holds only within one deployment whose
stampers and forwarders agree on what they relay. Attributing a relayed stamp to its stamper is on the roadmap.

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

A receiver that reads lineage MUST read an incomplete chain as `unknown`, never as clean, and SHOULD refuse a verdict on a
set when any document in the chain lists that set as `trained_on`. Version 2
lineage has a single `parent`, so a `merge` of several parents cannot list them all; such a document names one parent,
and a receiver MUST read the merge's other ancestry as missing, which is `unknown`. `spec/schema/lineage.schema.json`
gives the document's shape.

## 11. Switching (not normative)

perigraph identifies what ran and refuses claims that do not follow from the record. It does not switch, and it does not
say what to switch to: routers do. In the deployment it was designed with, Prismyra stamps its own answers with all four
model parts; a vLLM backend is stamped by middleware in its own process (a wrapper that hashed a directory before launch
is `pulled_by_us` and keys nothing); vLLM Semantic Router and the stratoclave gateway forward a backend's stamp verbatim
and add their own decision as a label; a model behind a provider's API is `not_observable`. A receiver such as tierbook
composes nothing from these attributes: it is handed opaque version strings that the emitters compose, recommended as
`perigraph/2/model/<model identity>` for what answered and `perigraph/2/artifact/<artifact identity>` for what a trainer
produced, and its own conformance test binds its refusals to `receiver_obligations`.

## 12. Security and privacy considerations

### 12.1 Trust

A receiver trusts the collector for every digest it did not compute itself. "Verifiable" in section 1.1a means
verifiable by the collector, which held the bytes. Version 3 records and stamps are not authenticated: nothing in a
record proves who wrote it, and an intermediary can alter or forge one. A receiver that accepts a relayed model stamp
(section 9) is trusting the forwarder and every hop before it. Authentication belongs around a record rather than
inside it; `SECURITY.md` names the shape (SCITT, RFC 9943).

### 12.2 What a digest does not hide

A digest is not a redaction. A sha256 of short or predictable content can be reversed by guessing:

- an instruction drawn from a small set of templates can be identified by digesting each candidate, and so can a
  request template;
- `answer_mode`, `precision` and `runtime` take few values, and a `runtime` digest can confirm that a known vulnerable
  package version is running;
- a set digest in a lineage document can confirm that a known dataset was used.

The identities are 96-bit truncations chosen as grouping keys (section 2.4). They make accidental collision negligible
and do not resist a party who chooses content to collide.

### 12.3 What a collector MUST NOT write

- A `detail` MUST NOT quote request content, credentials, tokens or URLs carrying secrets. Section 1.2 already requires
  details about unreadable fields to name the field and its type without quoting the value; this applies to every
  detail, including the text of an exception.
- A `label` is free text for a reader. A collector MUST NOT put request content or secrets in one.
- A collector MUST NOT digest altered content and present the digest as `model_visible`. Content withheld on purpose is
  an absence with reason `redacted`, which carries no digest.

### 12.4 What a receiver handles

- A harness identity correlates runs across tenants and deployments that used the same instruction and, from version 3,
  the same request template, which is a finer key. A receiver that
  stores records from several tenants SHOULD treat identities and lineage as data that links them, with the same access
  control as the runs themselves.
- A receiver SHOULD bound the number of attributes and the length of strings it accepts. A record of version 3 with every
  part and every model part present has about 63 `perigraph.*` attributes.

### 12.5 Out of scope for version 3

Keyed or salted digests, signed stamps and signed lineage documents. They are on the roadmap in `README.md`.

## 13. Extensibility

### 13.1 Proposing a new value

The closed vocabularies are closed because a value nobody named is a change nobody records. A proposal to add a part,
model part, sourcing value, absence reason, answer mode or attribute uses `docs/proposals/0000-template.md` and MUST
include:

- a measured case in which the thing changed while every existing name stayed the same;
- the diff to `spec/vocabularies.json`;
- fixtures or conformance cases that a conforming implementation passes and a non-conforming one fails;
- what a receiver does with it, and whether it may key an identity.

Whether an addition is breaking is decided by section 7.

### 13.2 Vendor extensions

The prefix `perigraph.ext.<vendor>.` is reserved for attributes outside this specification, where `<vendor>` is a name
the extension's author controls, such as a project name, written with the characters `a-z`, `0-9`, `_` and `-` only. Such an attribute:

- never keys an identity, and a receiver MUST NOT compare it as if it did;
- never lifts a refusal (section 1.1a);
- MUST be ignorable: a receiver MUST NOT reject a record because it carries one.

A `perigraph.*` attribute outside `perigraph.ext.` that this version does not define is not an extension. How a receiver
treats one is part of the planned versioning policy (section 7.1).
