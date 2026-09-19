# Contributing

## The thing this project wants most

**A third implementation, by somebody who is not the author of the first two.**

Writing the second implementation found five sentences in the spec that read two ways, one of them fatal to
interoperability — and **four of the five were invisible from inside the first implementation**, whose tests all passed
before and after the fixes. See [docs/ambiguities.md](docs/ambiguities.md).

Both existing implementations share one author, so they share whatever that author assumed without noticing. If you
write a sender in another language and it disagrees with `spec/fixtures/identity.json`, **the disagreement is the
contribution** — open an issue with what you read the spec to mean. A sentence two people read differently is a spec
defect even when one reading is "obviously" right.

## Changing the protocol

`spec/vocabularies.json` is normative. `SPEC.md` is prose that must not drift from it, and a test enforces that: every
closed-vocabulary value and every receiver obligation has to appear in the prose. Adding one without writing the
sentence fails.

Read [SPEC.md section 7](SPEC.md) before proposing a change. **Adding a receiver obligation is a breaking change** — a
receiver that does not implement it stops being conformant while still claiming the same version.

Three copies of the JSON exist (`spec/`, `src/perigraph/`, `typescript/`) so that each package ships it, and CI fails if
they differ. Change the one in `spec/` and copy it.

## Changing an implementation

- **Every invariant is tested by breaking it.** A test that passes against a deliberately broken implementation is not
  evidence. If you add a rule, revert it locally and confirm a test fails.
- **Do not canonicalise a `model_visible` payload.** Section 2.4 says why, and a mutation that lowercased the
  instruction once passed every test in the suite — so the test that catches it varies only case and whitespace.
- **The injection must never break the call it describes.** A shim that can is a shim nobody leaves installed, and then
  there is no record at all. Every failure path degrades the record and lets the call through.
- **No runtime dependencies.** A shim runs in a sender's process; a tracer is an optional extra.

## Running everything

```bash
# Python
pip install -e ".[dev]" && python -m pytest tests/ -q

# TypeScript
cd typescript && npm install && npm test

# The check neither implementation can pass by agreeing with itself
cd typescript && npm run build && cd .. && PYTHONPATH=src python tools/cross_check.py
```

## Style

Prose in comments and commit messages explains **why**, not what. A comment that restates the code is debt; a comment
recording a non-obvious reason, a measured number, or an alternative that was tried and was wrong is the kind worth its
lines.
