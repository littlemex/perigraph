# Ambiguities and readings

## Clarified by the current specification

- **System messages:** Only string `content` in system-role messages supplies `instruction`. Multiple strings are joined with one U+000A in message order. An instruction empty after trimming the specified Unicode `White_Space` property is `not_provided`; otherwise its digest uses the untrimmed, joined text. Any non-string or missing system content fails the entire instruction extraction, with its message index and JSON type in the detail; content is never quoted.
- **Empty request values:** An empty `tools` array is `not_provided`. An empty `response_format` object is `not_provided` for both `readout` and `decoding`, although independently supplied sampler settings can still supply `decoding`.
- **Malformed request fields:** A non-object body fails extraction for every part in the static manifest. A wrongly typed `messages` array or entry fails both parts read from messages. A wrongly typed `tools` array, entry, or present `function` object fails `tool_schemas`, without affecting parts read elsewhere. Such input does not by itself make the collector’s terminal status `collector_failed`.
- **Manifest and wire form:** Manifest order has no meaning; an empty manifest is the empty string. A request-only collector writes four `not_observable` model absences and omits both model identities. All three identity attributes are omitted when absent.
- **Precision:** An empty value, or `auto` as any value or as a dtype name, is unresolved. The `auto` comparison trims the Unicode `White_Space` property specified in section 1.2 and ignores ASCII case. Accepted values are digested as read, without trimming. `PrecisionDigest` returns an error for an unresolved value; a collector recording the failed observation reports `precision` as `extraction_failed`.

## Remaining interpretations and limitations

- A nonempty `tools` array is held at a collector-local `parsed` boundary. The request does not provide the exact rendering of tool schemas shown to the model, so this digest cannot identify a harness.
- Assistant `tool_calls` or `function_call` and tool-role messages already present in the request supply a `parsed` trace. No future calls are inferred; absent such entries, `tool_trace` is `not_provided`.
- A nonempty `response_format` object supplies a `parsed` `readout`. Supplied sampler fields and a nonempty `response_format` form a `parsed` `decoding` value; an omitted or empty field does not assert a default. The specification does not define a cross-collector serialization for these parsed values.
- Absent `loop`, `turn_budget`, `retry_policy`, and `context_partitioning` are `not_provided`; `tool_extension` is structurally `not_observable`. This adapter’s manifest is always `instruction,tool_schemas,tool_trace,readout,decoding`.
- Checkpoint paths are ordered by their UTF-8 bytes. The digest API receives paths and file digests, not an artifact root; the caller must resolve symlinks, hash file bytes, and enumerate every file the process read before invoking it.
- Precision lines are sorted by complete field name; runtime lines by distribution name. Nonempty serializations end in a newline. This API cannot itself verify that precision was read from loaded parameters or that a runtime package list is static per collector version.
- `Loaded` must be called during the load, in the process that loaded the model. Replacing a request record’s default model half with its result attaches that in-process stamp.

## New ambiguity

- Section 1.2 explicitly assigns shared failures to malformed `messages` entries, but does not say whether a malformed nested field used only for trace extraction, such as an assistant `tool_calls` value of the wrong type, must also fail `instruction`. This collector fails only `tool_trace` for that nested field; malformed shared message structure fails both.
