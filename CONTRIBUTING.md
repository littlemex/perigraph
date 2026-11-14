# Contributing

## The thing this project wants most

**An implementation by a person who is not the author of the specification.**

Writing the second implementation found five sentences in the spec that read two ways, one of them fatal to
interoperability — and **four of the five were invisible from inside the first implementation**, whose tests all passed
before and after the fixes. See [docs/ambiguities.md](docs/ambiguities.md).

The Python and TypeScript implementations share one author, and the Go one was written by a language model from the
documents alone (IMPLEMENTATIONS.md). None was written by an independent person. If you write one and it disagrees with
a fixture or a conformance case, **the disagreement is the contribution** — open an issue with what you read the spec to
mean. A sentence two people read differently is a spec defect even when one reading is "obviously" right.

Check yours with the conformance runner through a small adapter ([conformance/README.md](conformance/README.md)).

## Changing the protocol

`spec/vocabularies.json` is normative. `SPEC.md` is prose that must not drift from it, and a test enforces that: every
closed-vocabulary value and every receiver obligation has to appear in the prose. Adding one without writing the
sentence fails.

Read [SPEC.md section 7](SPEC.md) before proposing a change, and use
[docs/proposals/0000-template.md](docs/proposals/0000-template.md) for a new value (SPEC section 13.1). **Adding a
receiver obligation is a breaking change** — a receiver that does not implement it stops being conformant while still
claiming the same version. How changes are decided is in [GOVERNANCE.md](GOVERNANCE.md).

Four copies of the JSON exist (`spec/`, `src/perigraph/`, `typescript/`, `go/spec/`) so that each package ships it, and
CI fails if they differ. Change the one in `spec/` and copy it. The schemas in `spec/schema/` and the registry
`spec/requirements.json` are generated: after editing the vocabulary or SPEC.md, run `python tools/gen_schema.py` and
`python tools/requirements.py`.

## Changing an implementation

- **Every invariant is tested by breaking it.** A test that passes against a deliberately broken implementation is not
  evidence. If you add a rule, revert it locally and confirm a test fails.
- **Do not canonicalise a `model_visible` payload.** Section 2.4 says why, and a mutation that lowercased the
  instruction once passed every test in the suite — so the test that catches it varies only case and whitespace.
- **The injection must never break the call it describes.** A shim that can is a shim nobody leaves installed, and then
  there is no record at all. Every failure path degrades the record and lets the call through.
- **No runtime dependencies.** A shim runs in a sender's process; a tracer is an optional extra.

## Running everything

Python:

```bash
pip install -e ".[dev]" && python -m pytest tests/ -q
```

TypeScript, on Node 22 or later:

```bash
(cd typescript && npm install && npm test)
```

Go 1.22 or later:

```bash
(cd go && go vet ./... && go test ./...)
```

The conformance suite against all three, and the cross-check that compares the three senders on the same bodies:

```bash
python tools/conform.py --adapter "python conformance/adapters/python_adapter.py"
python tools/conform.py --adapter "node conformance/adapters/typescript_adapter.mjs"
python tools/conform.py --adapter "go -C go run ./cmd/conform"
PYTHONPATH=src python tools/cross_check.py
```

The generated files:

```bash
python tools/gen_schema.py --check && python tools/requirements.py --check
```

## Style

Prose in comments and commit messages explains **why**, not what. A comment that restates the code is debt; a comment
recording a non-obvious reason, a measured number, or an alternative that was tried and was wrong is the kind worth its
lines.
