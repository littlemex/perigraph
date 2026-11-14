# Conformance

The same cases, checked by the same runner, for every implementation in every language. The runner never imports the implementation it checks. It talks to a small adapter the implementation provides, over standard input and output, so a new implementation needs about fifty lines of glue and no change to the suite.

```bash
pip install jsonschema
python tools/conform.py --adapter "python conformance/adapters/python_adapter.py"
```

```bash
(cd typescript && npm install && npm run build)
python tools/conform.py --adapter "node conformance/adapters/typescript_adapter.mjs"
```

```bash
python tools/conform.py --adapter "go -C go run ./cmd/conform"
```

The run ends with one line per implementation, for example `perigraph (Go): roles collector, stamper; 23 of 23 cases pass`, and exits non-zero if any case fails. `--json FILE` also writes the results with the requirement identifiers each case checks, and `--role` restricts the run to some of the roles the adapter declares.

## What is checked

Conformance is claimed per role (SPEC section 8). The runner checks each role the adapter declares:

| role | cases | what must hold |
|---|---|---|
| collector | every body in `spec/fixtures/identity.json`, and every case in `spec/fixtures/canonical_value.json` | the fixture's harness identity and instruction digest, and where the case names them the `request_template` and `generation_controls` digest or absence and the unlisted member names; a record that validates against `spec/schema/record.schema.json`; a model half; `tool_extension` absent as `not_observable`; for each canonical case, the canonical text, or a failure where the fixture says it fails |
| stamper | every case in `spec/fixtures/model_identity.json` | the fixture's checkpoint, precision and runtime digests and both identities; every map in `refused_precision` refused |
| receiver | every case in `cases/receiver.json`, and every case in `cases/arm.json` | the expected outcome: `rejected`, or `stored` with a verdict over that record alone that is `admitted` or `refused`; for an arm case, the outcome of one verdict over its records as one arm, `admitted`, `refused` or `unknown` |

Each receiver case also says whether the record schema alone rejects it. The runner checks that claim too, so a schema that drifts from the prose fails the suite. Four cases are rejected only by recomputing a digest or an identity, which a schema cannot do.

The fixture cases are the part of conformance that a second implementation cannot pass by agreeing with itself (SPEC section 8). The receiver cases cover single records, and the arm cases cover the obligations over records grouped as one arm that the wire record carries: one harness identity, uniformity of the parts in `uniform_within_arm`, and uniformity of the unlisted member names. Each arm case has at least three records, so that an implementation comparing only adjacent records, or only against the first, fails one. They do not cover the obligations about comparing two arms, which need data about runs that the version 4 wire record does not carry (SPEC section 6.1), nor the lineage rules of section 10. Which requirements have no portable case yet is printed by:

```bash
python tools/requirements.py --report
```

## The adapter contract

The adapter is a long-running process. It reads one JSON object per line on standard input and writes exactly one JSON object per line on standard output, in order, echoing the request's `id`. It writes nothing else to standard output. Diagnostics go to standard error.

| request `op` | other request fields | reply |
|---|---|---|
| `describe` | none | `name` (free text) and `roles`, a list drawn from `collector`, `stamper`, `receiver` |
| `collect` | `body`: the request body as a JSON value | `attributes`: the record's attributes as one JSON object, using the implementation's collector name and version of its choice |
| `stamp` | `files` (path to file contents as a UTF-8 string; the file's sha256 is over those bytes), `precision`, `runtime`, `answer_mode` | `checkpoint_digest`, `precision_digest`, `runtime_digest`, `model_identity`, `artifact_identity`, and optionally `attributes` for a record carrying the stamp; or `refused` with a message when the inputs cannot be stamped |
| `receive` | `attributes`: one record's attributes | `outcome`: `rejected` or `stored`; when stored, `verdict`: `admitted` or `refused`; optionally `why` |
| `canonical` | `json`: JSON text, as a string, which the adapter parses itself | `canonical`: the text `digest.canonical_value_serialisation` gives; or `fails` with a message when the definition fails it |
| `admit_arm` | `records`: a list of records' attributes, grouped as one arm | `outcome`: `rejected` if any record is, otherwise `admitted`, `refused` or `unknown` for one verdict over them; optionally `why` |

Framing: each line is UTF-8 JSON ended by LF, and the adapter flushes after every reply, because the runner waits for one reply before sending the next request. `id` is an integer, echoed unchanged. A request the adapter cannot handle gets `{"id": …, "error": "…"}`, and the adapter keeps running. The `canonical` op takes text rather than a value so that an implementation parses it with its own reader, which is where a lone surrogate escape or an out-of-range number is lost or kept. The runner sends `describe` first, runs every case in one process, and closes standard input at the end, after which the adapter exits with status 0. Cases are independent: a verdict depends on the one record in the request and on nothing stored earlier. The runner, not the adapter, validates records against the schema.

Attribute values are JSON strings, numbers or booleans, as they would be on a span. `admitted` and `refused` are the outcomes of SPEC section 0.5. No receiver case in version 4 expects `unknown`, because no single-record rule widens a verdict; arm cases do. A `receive` reply of `stored` means the receiver kept the record. `verdict` answers whether a verdict could be drawn from this record by itself, under every `must_refuse` obligation that a single record can trigger and none of the `must_not_refuse` ones.

The adapters for the three implementations in this repository are short and are the reference for writing one: `conformance/adapters/python_adapter.py`, `conformance/adapters/typescript_adapter.mjs` and `go/cmd/conform/main.go`.

## Adding a case

Receiver cases live in `cases/receiver.json`. Each one names the requirements it checks by identifier from `spec/requirements.json`. A case that cites an identifier that does not exist fails `tools/requirements.py --check`. A requirement whose sentence is reworded gets a new identifier, so a case cannot silently go on checking a sentence that has changed. Every reference implementation must pass a new case before it is merged, and a case they disagree on is a defect in SPEC.md or in one of them, which is the point of adding it.
