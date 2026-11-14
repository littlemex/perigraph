# perigraph Go sender

The code and tests in this directory, except `cmd/crosscheck`, were written by OpenAI GPT-6 Sol from `SPEC.md` and `spec/vocabularies.json` alone, without the Python or TypeScript source or the fixtures, and revised only from compiler, test and conformance output. `cmd/crosscheck` was written by the reviewer. An implementation written by an independent person is still wanted (see `../CONTRIBUTING.md`).

Written from `SPEC.md` and its normative `spec/vocabularies.json`. Requires Go 1.22 and uses only the standard library.

`FromRequest` makes a partial-safe harness record from a decoded JSON object. An allocated empty map represents `{}`; a nil map represents a JSON `null` body. Use `FromRequestValue` when the decoded body might not be an object. A missing or `null` top-level request field means the sender supplied none; malformed fields and non-object bodies are reported through detailed `extraction_failed` absences rather than by withholding the record.

Attach the `ModelHalf` returned by `Loaded` when collecting in the process that loaded the model, then call `ToAttributes`. The model digest functions require observations of the loaded artifact and runtime; they do not read files or discover packages on the caller’s behalf.

Run tests with `go test ./...`. When the module is inside the spec repository, the tests also compare the SHA-256 of the embedded vocabulary with `../spec/vocabularies.json`. See `AMBIGUITIES.md` for remaining interpretations and API limitations.
