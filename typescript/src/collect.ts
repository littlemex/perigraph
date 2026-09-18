/**
 * Read a request body into a record. Pure, no network, no tracer.
 *
 * AMBIGUITY 3 (now fixed in the spec): the spec never said how a `parsed` payload is serialised before hashing, and it
 * cannot -- the first implementation used Python's `repr`, which no other language reproduces. `0.0` renders as "0.0"
 * there and "0" here, so a `decoding` digest computed by these two implementations of the same request will differ.
 *
 * That is now stated rather than papered over: a `parsed` digest is **collector-local**. It is comparable only against
 * another digest from the same collector and version, and since a `parsed` digest can never key an identity, nothing
 * that matters was lost. What WAS lost before saying it: somebody would have compared two and concluded the harnesses
 * differed.
 *
 * AMBIGUITY 4 (now fixed in the spec): with several system messages, nothing said how they combine. Joining with a
 * newline is what the first implementation did, and because the instruction digest KEYS THE IDENTITY, two collectors
 * choosing differently would give two identities for one request.
 */
import { Absence, Manifest, Part, Record_, digest } from "./record.js";
import { PARTS } from "./vocab.js";

/** Static per version: a manifest that adapted to what it found could never contradict a record. */
export const FROM_A_REQUEST = ["instruction", "tool_schemas", "readout", "decoding"] as const;

/** Only the instruction is text the model provably read; the rest are protocol values whose rendering we do not hold. */
export const REQUEST_BOUNDARIES: Record<string, string> = {
  instruction: "model_visible",
  tool_schemas: "parsed",
  readout: "parsed",
  decoding: "parsed",
};

export const DECODING_KEYS = ["temperature", "top_p", "top_k", "seed"] as const;

/** Parts a request body has no place to put. Their absence is the SENDER's. */
export const PUSHED_PARTS = ["loop", "turn_budget", "retry_policy", "context_partitioning"] as const;

/** Collector-local rendering of protocol scalars. See AMBIGUITY 3. */
function scalars(pairs: [string, unknown][]): string {
  return pairs.map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(";");
}

export interface Body {
  messages?: { role?: string; content?: unknown }[];
  tools?: { function?: { name?: string; parameters?: unknown }; name?: string; parameters?: unknown }[];
  response_format?: unknown;
  [key: string]: unknown;
}

export function fromRequest(body: Body, opts: { collector: string; version: string }): Record_ {
  const parts: Part[] = [];
  const absences: Absence[] = [];

  const hold = (kind: string, payload: string, label = ""): void => {
    parts.push(
      new Part({
        kind,
        sourcing: "in_the_request",
        label,
        contentDigest: digest(payload),
        boundary: REQUEST_BOUNDARIES[kind] as string,
      }),
    );
  };

  const messages = body.messages ?? [];
  // Newline-joined, per the spec's serialisation section. This keys the identity, so it is normative rather than local.
  const instruction = messages
    .filter((m) => m.role === "system")
    .map((m) => String(m.content ?? ""))
    .join("\n");
  if (instruction.trim() !== "") {
    // Hashed RAW, down to case and whitespace: the model reads the string and not its meaning.
    hold("instruction", instruction);
  } else {
    absences.push(new Absence("instruction", "not_provided"));
  }

  const tools = body.tools;
  if (tools !== undefined && tools.length > 0) {
    // Sorted: the order a caller lists tools in is not part of what it offered.
    const shapes = tools
      .map((t) => {
        const fn = t.function ?? t;
        return scalars([
          ["name", fn.name],
          ["params", fn.parameters],
        ]);
      })
      .sort();
    hold("tool_schemas", shapes.join("|"), `${tools.length} tool(s)`);
  } else {
    absences.push(new Absence("tool_schemas", "not_provided"));
  }

  const fmt = body.response_format;
  if (fmt !== undefined && fmt !== null) {
    const label = typeof fmt === "object" && fmt !== null && "type" in fmt ? String((fmt as { type: unknown }).type) : "";
    hold("readout", scalars([["response_format", fmt]]), label);
  } else {
    absences.push(new Absence("readout", "not_provided"));
  }

  const knobs = DECODING_KEYS.filter((k) => k in body).map((k) => [k, body[k]] as [string, unknown]);
  if (knobs.length > 0) {
    hold("decoding", scalars(knobs), knobs.map(([k]) => k).join(","));
  } else {
    absences.push(new Absence("decoding", "not_provided"));
  }

  for (const kind of PUSHED_PARTS) absences.push(new Absence(kind, "not_provided"));
  absences.push(new Absence("tool_extension", "not_observable"));
  // At request time the calls have not happened, so there is nothing the sender could have supplied.
  absences.push(new Absence("tool_trace", "not_provided"));

  const record = new Record_(
    new Manifest(opts.collector, opts.version, [...FROM_A_REQUEST]),
    "complete",
    parts,
    absences,
  );
  if (record.unaccounted.length > 0) {
    throw new Error(`the collector left ${record.unaccounted} unaccounted for`);
  }
  return record;
}

/** Attach what the owner says about the parts a request cannot carry, replacing their `not_provided` absences. */
export function declare(record: Record_, pushed: Partial<Record<(typeof PUSHED_PARTS)[number], string>>): Record_ {
  const unknown = Object.keys(pushed).filter((k) => !(PUSHED_PARTS as readonly string[]).includes(k));
  if (unknown.length > 0) {
    throw new Error(
      `${unknown} are not parts a request body fails to carry; a declaration about something we can read from the ` +
        `request would be a claim standing in front of the evidence`,
    );
  }
  const kept = record.absences.filter((a) => !(a.kind in pushed));
  const declared = Object.entries(pushed)
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(
      ([kind, value]) =>
        new Part({
          kind,
          sourcing: "pushed_by_owner",
          label: value as string,
          contentDigest: digest(value as string),
          boundary: "parsed",
        }),
    );
  return new Record_(record.manifest, record.status, [...record.parts, ...declared], kept);
}

export { PARTS };
