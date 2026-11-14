# perigraph

**περί** (around) + **γραφή** (record): a record of what surrounded a model, and of what answered.

perigraph is an open specification for one record attached to one model call. The record says which parts of the harness surrounded the model (the instruction, the tools, the loop, the decoding settings and the rest) and which model answered (its files, its precision, its runtime and how its answer is read). Each part the collector can read is identified by a digest of its exact content, and every part says how that fact reached the record. Each part that is missing says whose fault the gap is. The record exists so that a receiver can refuse a claim about accuracy or cost when the records behind the claim cannot show that the runs being compared were what the claim says they were.

[Project page](https://littlemex.github.io/perigraph/) · [Specification](SPEC.md) · [Conformance](conformance/README.md) · [Implementations](IMPLEMENTATIONS.md)

| | |
|---|---|
| specification | `spec_version` 2, provisional: a formal versioning and compatibility policy is planned and not yet in place ([Versioning](#versioning)) |
| normative files | [`SPEC.md`](SPEC.md), [`spec/vocabularies.json`](spec/vocabularies.json), [`spec/bindings/`](spec/bindings), with generated JSON Schemas in [`spec/schema/`](spec/schema) |
| conformance | [`tools/conform.py`](tools/conform.py) with fixtures and receiver cases, runnable against an implementation in any language |
| implementations | Python, TypeScript and Go in this repository. None yet by a person other than the specification's author |

## The problem

A comparison between two runs is only as good as the evidence that each side was what its name says. Names are the usual evidence: a model name, a prompt version, a package tag. In one distillation study, recorded in [tierbook's verification record](https://github.com/littlemex/tierbook/blob/497d5cd5ba7acf219ac90dde5648c20514f02deb/docs/verify/v0.5.0-distillation-loop.md), each of the following changed the answers while every name stayed the same:

| what happened | what stayed the same | what changed |
|---|---|---|
| a model was re-trained from the same recipe and seed | the model name, the recipe | its labels agreed with the earlier model's on 93.4% of items |
| the same weights were quantised to int8 when loaded | the stored files, the model name | its answers agreed with the unquantised run's on 33 to 40% of items |
| a model trained to answer by comparing option scores was asked to generate text instead | the model, the files | it produced `1111` instead of a label |
| the serving image was rebuilt and lost some packages | the model name, the checkpoint | 97 of 100 answers agreed with the earlier ones |

A fifth case came from the version string itself. In [Prismyra](https://github.com/littlemex/Prismyra/commit/84cf43dd77164ac3a23c8442b8d378a19eb59d14), a fallback model's version was derived from its whole serving specification, so deploying a router, which writes into that specification, made the unchanged model a different arm by its version string.

Each case either made two different things look the same or made the same thing look different. A record that names things cannot catch either. A record that digests the content of each part catches the first kind, and it catches the second only when the digest covers the text the requester supplied for the model, and nothing else. That second condition is most of what this specification is about.

## What a record looks like

A record is a set of flat attributes under the prefix `perigraph.`, so it can ride on a span that a tracer already emits, on a log line, or in a file. This is part of the record of a request with a system instruction and `"temperature": 0`, from a collector that sees only the request:

```json
{
  "perigraph.spec_version": 2,
  "perigraph.collector": "quickstart",
  "perigraph.collector_version": "1",
  "perigraph.collector_reaches": "instruction,tool_schemas,readout,decoding",
  "perigraph.status": "complete",
  "perigraph.harness_identity": "c8f8edc45e222f663d8d70ac",
  "perigraph.part.instruction.sourcing": "in_the_request",
  "perigraph.part.instruction.digest": "bc08b15e1d666817a85deb76df71182f5b17ee4ea314f8635a98fe14b17b4ad3",
  "perigraph.part.instruction.boundary": "model_visible",
  "perigraph.part.decoding.sourcing": "in_the_request",
  "perigraph.part.decoding.digest": "67a865a25ffe9dea5db8a7e6cdcfc6375a53544a1f3eb82d501424112a02845a",
  "perigraph.part.decoding.boundary": "parsed",
  "perigraph.part.decoding.label": "temperature",
  "perigraph.absent.tool_schemas.reason": "not_provided",
  "perigraph.absent.tool_extension.reason": "not_observable",
  "perigraph.model_absent.checkpoint.reason": "not_observable"
}
```

The full record has every part and every model part, each one either held or absent with a reason. Complete records are in [`spec/examples/`](spec/examples), among them one [stamped by the process that loaded the model](spec/examples/stamped.json), one for a [model behind a provider's API](spec/examples/provider-api.json), and one with a [contradiction](spec/examples/contradiction.json).

## How it is designed, and why

Each decision below is stated with the failure it prevents and the alternatives that were weighed. The specification section that makes it normative is linked.

### 1. Identify each part by a digest of its content, not by its name

A name is a label its owner controls: a prompt can stay `v3` while its text changes, and a model name can stay the same across a re-training. So each part carries the sha256 of its exact content, and the harness identity is computed from those digests ([SPEC 2.2](SPEC.md#22-how-the-identity-is-computed)). Names are kept as labels for a reader and never key anything.

Alternatives weighed: a name and version per component, which is what every convention surveyed carries and which the incidents above defeat; one digest over the whole prompt, as OpenLLMetry's `traceloop.prompt.version_hash` does, which says that something changed but not which part, and so cannot tell a changed tool list from a changed instruction.

### 2. Every digest says which boundary it is over, and only text the model reads can key the harness identity

The same request can be digested at three places: the bytes on the wire, the values after parsing, or the text the model reads. A `tools` array or a sampler setting is in the request, but the provider renders it into the prompt however it likes, so its digest does not prove what the model saw. Each digest therefore names its boundary (`transport`, `parsed` or `model_visible`), and only a `model_visible` digest can key the harness identity ([SPEC 2.1](SPEC.md#21-the-three-boundaries-and-why-the-middle-one-is-the-trap)). For a request in the OpenAI Chat Completions shape this means the identity is the instruction's alone. That is a real limit, and the record says so rather than claiming more ([`spec/bindings/openai-chat-completions.md`](spec/bindings/openai-chat-completions.md)).

The `model_visible` text is hashed raw, without canonicalising case, white space or Unicode form, because a model reads a string and not its meaning; `parsed` values may be canonicalised because a machine reads them ([SPEC 2.4](SPEC.md#24-canonicalisation)). Alternatives weighed: digesting everything and keying on all of it, which gives an identity that changes when a gateway re-serialises JSON and stays the same when the provider changes how it renders tools; canonical JSON for everything, which makes two instructions that differ only in white space look identical even though such differences change model behaviour.

### 3. Every fact says how it reached the record, and a claim nobody can check can only subtract

A part was in the request, loaded by the collector itself, pulled from somewhere else at some earlier moment, pushed by its owner as a declaration, or not observable at all. The record says which, per part (`sourcing`, [SPEC 1.1a](SPEC.md#11a-how-a-fact-reached-the-record)). A pulled fact carries its read lag in seconds, because it was read at a different moment from the request. A pushed fact may make a receiver refuse a verdict and may never make it accept one, because nobody downstream can check it. A relayed model stamp is the one exception, and SPEC 12.1 states the trust it requires.

Alternatives weighed: trusting declared metadata as other conventions do, which lets an owner's statement stand in for an observation; refusing pushed facts outright, which throws away the only source for parts a request cannot carry, such as an agent's retry policy.

### 4. Every absence names whose fault it is, and the collector states in advance what it can reach

A missing value is ambiguous. It can mean that the requester sent nothing, that the collector failed to read it, or that nobody could ever see it. The dangerous case is a collector that loses the ability to read a part after a client library renames a field, and then writes the same absence it writes when the requester really sent nothing. So every absence carries a reason that blames the requester, the collector, or nobody ([SPEC 1.2](SPEC.md#12-every-absence-names-whose-it-is)). A collector-blamed absence must carry a detail. The collector also publishes a manifest of the parts it claims it can reach, so a record that contradicts its own manifest is an alarm and not a hole ([SPEC 1.3](SPEC.md#13-the-manifest-and-what-a-contradiction-is)).

Alternatives weighed: omitting missing fields, or setting them to null, which cannot tell a regression from an empty request; a free-text reason, which no receiver can act on.

### 5. Permissive toward the sender, exact about itself

A record missing any number of parts is still a valid record, because a collector that withheld a partial record would produce no record, and a record withheld is indistinguishable from a perfect record of nothing. But the record must say whether the collector finished. Every failure path, including an exception inside the collector, still emits a record, with status `collector_failed` ([SPEC 1.1](SPEC.md#11-the-two-refusals-are-about-different-objects)). Such a record is kept as a log and supports no verdict.

Alternative weighed: validating strictly and rejecting incomplete records, which converts every partial observation into silence.

### 6. What answered is identified only by the process that loaded it

The four model parts are the checkpoint files, the precision in force after loading, the runtime packages and the answer mode. Each one corresponds to one of the incidents above. Only a collector in the process that loaded the model holds those bytes, so only its digests (`loaded_by_us`) can key a model identity ([SPEC 9](SPEC.md#9-what-answered-the-model-parts)). A router or gateway forwards that stamp or says the model is `not_observable`. A model behind a provider's API has no model identity and stays admissible: claims about it are not bound to model bytes, and the record says so. A second identity, the artifact identity, covers the checkpoint alone and can be computed by anybody holding the same set of files, including a trainer at save time.

Alternatives weighed: the model name, or a provider's model identifier, which is a label (incidents 1 and 4); a digest of the stored files alone, which cannot tell bf16 from int8 of the same files (incident 2).

### 7. A tuned model's history is a separate document, and it can only subtract

How a model came to be (its parent, its method, the item sets it was trained on, the source of its training signal) is written by its trainer in a lineage document about one artifact identity, outside any record ([SPEC 10](SPEC.md#10-lineage-how-a-tuned-model-came-to-be)). It never keys an identity, because two trainings that produced the same bytes are the same model. Its use is a refusal: a set named as trained on makes a verdict on that set suspect. A missing lineage, or a chain with a missing ancestor, is read as unknown and never as clean.

Alternative weighed: lineage fields inside every record, which would make the server that holds the bytes vouch for a history it does not hold.

### 8. Flat scalar attributes, keyed by part name

The wire form is flat `perigraph.*` keys with string or number values (an extension may also use booleans) ([SPEC 6](SPEC.md#6-the-wire-form)), because it has to ride on a span that any tracer already emits. Keys use part names and never positions: a positional index changes meaning when a collector learns to read one more part. An identity that does not exist is omitted, never written as an empty string, because two empty strings compare equal and would group every unidentifiable run together. Bindings say how the record travels on [OpenTelemetry spans](spec/bindings/otel.md), in [JSON Lines files](spec/bindings/jsonl.md), and how it is read from an [OpenAI Chat Completions request](spec/bindings/openai-chat-completions.md).

Alternative weighed: a nested JSON document, which needs a serialiser on both ends and puts the record's shape into the transport, where every change to the shape breaks compatibility.

### 9. Conformance is stated as refusals

A receiver conforms by refusing what the records cannot support, for example a verdict over a record whose collector did not finish, a comparison of two arms whose decisions were missing different facts, or a comparison of two model identities produced by different collectors. The list is closed and machine-readable (`receiver_obligations` in [`spec/vocabularies.json`](spec/vocabularies.json)). Equally closed is what a receiver must not refuse, such as a record missing parts or a model behind an API, so a receiver cannot become conformant by refusing everything ([SPEC 8](SPEC.md#8-conformance)).

Alternative weighed: listing capabilities a receiver supports, which says what it can do and not what it will not let through.

## Relation to OpenTelemetry GenAI, OpenInference and OpenLLMetry

perigraph is not a telemetry convention and does not compete with one. It adds two things that none of the three conventions carries: a content digest per part, labelled with the boundary it is over, and a sourcing mode per part. The other attributes of a span describe what was said; the perigraph record on the same span says whether two runs were the same.

| convention | surveyed at | what it carries that perigraph does not | what it does not carry |
|---|---|---|---|
| OpenTelemetry GenAI semantic conventions | [`e6658f1`](https://github.com/open-telemetry/semantic-conventions-genai/tree/e6658f1), 2026-11-06; every attribute is at `development` stability | request parameters, messages when content capture is on, `gen_ai.evaluation.result` | a content digest per part, a sourcing mode per part |
| OpenInference | [`715e299`](https://github.com/Arize-ai/openinference/tree/715e299), 2026-11-11 | a `DECISION` span kind, `llm.cost.*` in USD, `evaluation.*` | a content digest per part, a sourcing mode per part |
| OpenLLMetry | [`e3d651a`](https://github.com/traceloop/openllmetry/tree/e3d651a), 2026-11-05 | `traceloop.prompt.version_hash`, one digest over a whole prompt version | a digest per part, a sourcing mode per part |

[`spec/bindings/otel.md`](spec/bindings/otel.md) maps four parts (instruction, tool_schemas, decoding and checkpoint) to the nearest attributes of the first two and says how a span's attribute limits can drop part of a record.

## Quickstart

None of the three packages is published to a registry yet, so each quickstart runs from a clone. Each one records the same request and prints the same harness identity, `c8f8edc45e222f663d8d70ac`.

```bash
git clone https://github.com/littlemex/perigraph.git
cd perigraph
```

### Python 3.10 or later

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install .
python examples/quickstart.py
```

[`examples/quickstart.py`](examples/quickstart.py) builds a record from a request body with `collect.from_request`, flattens it with `wire.to_attributes`, and reads it back as a receiver with `wire.from_attributes`. The output ends with:

```text
harness identity: c8f8edc45e222f663d8d70ac
verdict: admitted
```

### TypeScript, Node 22 or later

```bash
cd typescript
npm install
npm run build
node examples/quickstart.mjs
```

[`typescript/examples/quickstart.mjs`](typescript/examples/quickstart.mjs) does the same with `fromRequest`, `toAttributes` and `fromAttributes`, and ends with the same two lines.

### Go 1.22 or later

```bash
cd go
go run ./examples/quickstart
```

[`go/examples/quickstart/main.go`](go/examples/quickstart/main.go) builds the record with `FromRequestValue` and prints it with `ToAttributes`. The Go implementation implements the collector and stamper roles only, so it ends with the identity line and no verdict.

## Conformance

The conformance runner checks any implementation, in any language, through a small adapter that the implementation provides. The adapter reads one JSON request per line and answers one JSON line each, and the runner never imports the implementation. The contract and the three reference adapters are in [`conformance/README.md`](conformance/README.md).

```bash
pip install jsonschema
python tools/conform.py --adapter "python conformance/adapters/python_adapter.py"
```

| role | what is checked |
|---|---|
| collector | every body in [`spec/fixtures/identity.json`](spec/fixtures/identity.json) gives the fixture's identity and instruction digest, and a record that validates against [`spec/schema/record.schema.json`](spec/schema/record.schema.json) |
| stamper | every case in [`spec/fixtures/model_identity.json`](spec/fixtures/model_identity.json) gives the fixture's digests and identities, and unresolved precisions are refused |
| receiver | every case in [`conformance/cases/receiver.json`](conformance/cases/receiver.json) is rejected, or stored with the expected verdict |

Every requirement sentence in the specification has an identifier in [`spec/requirements.json`](spec/requirements.json), and each receiver case names the requirements it checks. `python tools/requirements.py --report` lists the requirements that no portable case checks yet. Chief among them are the obligations about comparing two records, which rest on facts the version 2 wire record does not carry ([SPEC 6.1](SPEC.md#61-what-the-version-2-wire-record-does-not-carry)).

## Implementations

| implementation | roles | written by |
|---|---|---|
| Python, [`src/perigraph/`](src/perigraph) | collector, stamper, receiver | the specification's author |
| TypeScript, [`typescript/`](typescript) | collector, stamper, receiver | the specification's author |
| Go, [`go/`](go) | collector, stamper | OpenAI GPT-6 Sol, from `SPEC.md` and `spec/vocabularies.json`, without the other implementations' sources, and revised against compiler, test and conformance output, which includes fixture results |

All three pass the conformance runner in CI, and `tools/cross_check.py` compares the three senders' output on the same bodies. **An implementation written by a person other than the specification's author is still wanted.** It is the one test none of these can be, since an implementation shares the blind spots of whatever its author read. [`IMPLEMENTATIONS.md`](IMPLEMENTATIONS.md) says how to list yours.

## Versioning

The specification is at `spec_version` 2, a single integer with no minor version. Today's policy is in [SPEC section 7](SPEC.md#7-versioning). Removing or renaming a vocabulary value, changing what a value means or how an identity is computed, and adding a receiver obligation are each breaking and need a new `spec_version`. Adding a value whose meaning is a refusal a receiver already performs, and adding an optional attribute a receiver may ignore, are not. A change that only withdraws an identity is not breaking: after it, an input has either no identity or the one it had before, and never a different one. That exception holds only while every known sender is built from this repository. A receiver that meets a `spec_version` it does not implement rejects the record.

**A formal versioning and compatibility policy for the interface is planned and not yet in place.** [SPEC section 7.1](SPEC.md#71-planned-the-versioning-and-compatibility-policy) lists the questions it has to settle. Until it exists, version 2 should be treated as provisional.

## What it does not cover

- **Whether a claim is true.** A record says what surrounded a run and what answered it, and a conforming receiver refuses the comparisons the records cannot support. Neither judges accuracy, and it does not decide which model should answer ([SPEC 11](SPEC.md#11-switching-not-normative)).
- **Authenticity.** Version 2 records are not signed. A receiver trusts the collector for every digest it did not compute, and trusts a forwarder for every stamp it relays ([SPEC 12.1](SPEC.md#121-trust)).
- **Secrecy.** A digest is not a redaction. Short or predictable content, such as an instruction drawn from a few templates or a runtime package list, can be recovered by guessing ([SPEC 12.2](SPEC.md#122-what-a-digest-does-not-hide)).
- **What a provider renders.** For a request read from its body, only the instruction keys the identity, because the request does not carry how tools and settings were rendered into the prompt ([SPEC 2](SPEC.md#2-identity)).
- **Nondeterminism.** Batch-dependent kernels and other run-to-run variation are not separated by any identity here ([SPEC 9](SPEC.md#9-what-answered-the-model-parts)).
- **Comparisons across records, checked portably.** The comparison obligations need data about runs that the version 2 record does not carry ([SPEC 6.1](SPEC.md#61-what-the-version-2-wire-record-does-not-carry)), so no portable conformance case checks them yet.

## Roadmap

Planned and not started. None of these has a date.

| item | why it is needed |
|---|---|
| a formal versioning and compatibility policy | today's rules (SPEC 7) leave open how vocabularies evolve, mixed-version populations and stability levels (SPEC 7.1) |
| signed records, stamps and lineage documents | a forwarder can alter or forge a stamp today (SPEC 12.1) |
| keyed or salted digests | predictable content can be recovered from its digest (SPEC 12.2) |
| a carrier for a stamp between a stamper and a forwarder, and attribution of a relayed stamp | model identities from forwarders are comparable only within one deployment today (SPEC 9) |
| attributes for the facts the comparison obligations read, and conformance cases for them | lost-record counts, turn counts and missingness have no attribute in version 2 (SPEC 6.1) |
| bindings for more request shapes, such as the Anthropic Messages API | a collector reading another shape is not conformant for it today ([binding](spec/bindings/openai-chat-completions.md)) |
| reading `developer` messages, `tool_choice` and the remaining Chat Completions fields | each would change existing digests, so each is a version change |
| a two-record operation in the conformance adapter, with cases for the comparison obligations a pair of records can trigger | the suite checks single records only today |
| a refusal for an arm whose records carry more than one harness identity | adding a refusal is a version change (SPEC 7) |
| an attribute naming the stamper behind a relayed model stamp | a forwarder's own collector name is what the collector-local comparison keys on today (SPEC 9) |
| a registry for vendor names under `perigraph.ext.` | a vendor name is self-chosen today (SPEC 13.2) |
| more than one maintainer | decisions are made by one person today ([GOVERNANCE.md](GOVERNANCE.md)) |
| packages on PyPI, npm and a tagged Go module | the quickstarts run from a clone |
| an implementation by an independent person | see [Implementations](#implementations) |

## Contributing

Disagreements with a fixture or a conformance case are the most valuable contribution, and new values start as proposals with a measured case ([SPEC 13.1](SPEC.md#131-proposing-a-new-value), [`docs/proposals/0000-template.md`](docs/proposals/0000-template.md)). [CONTRIBUTING.md](CONTRIBUTING.md) has the commands that run every suite, [GOVERNANCE.md](GOVERNANCE.md) says how changes are decided, and [SECURITY.md](SECURITY.md) says how to report a vulnerability.

## Licence

Apache-2.0.
