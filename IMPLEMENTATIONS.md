# Implementations

Every implementation listed here passes `tools/conform.py` for the roles shown, in this repository's CI. Who wrote each one, and from what, is stated because an implementation shares the blind spots of whatever its author read: two implementations by one author can agree on a sentence that a third reader takes the other way.

| implementation | roles | written by | written from | conformance |
|---|---|---|---|---|
| Python, `src/perigraph/` | collector, stamper, receiver | the specification's author | the specification, which it was developed alongside | `python tools/conform.py --adapter "python conformance/adapters/python_adapter.py"` |
| TypeScript, `typescript/` | collector, stamper, receiver | the specification's author | `SPEC.md` and `spec/vocabularies.json`; writing it found the five ambiguities in `docs/ambiguities.md` | `python tools/conform.py --adapter "node conformance/adapters/typescript_adapter.mjs"` |
| Go, `go/` | collector, stamper | OpenAI GPT-6 Sol | `SPEC.md` and `spec/vocabularies.json`, without the other implementations' sources, revised only from compiler, test and conformance output, which includes fixture results (`go/README.md`, `go/AMBIGUITIES.md`) | `python tools/conform.py --adapter "go -C go run ./cmd/conform"` |

**Still wanted: an implementation written by a person other than the specification's author, from the documents alone.** It is the one test none of the above can be. If yours disagrees with a fixture or a conformance case, the disagreement is the contribution: open an issue saying what you read the text to mean.

## Listing yours

Open a pull request adding a row. Say which roles it implements, who wrote it and from what, and give the command that runs `tools/conform.py` against it with its adapter (`conformance/README.md`). An implementation outside this repository is listed with a link and the commit it was checked at.
