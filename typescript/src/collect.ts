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
import { Model, ModelAbsence } from "./model.js";
import { Absence, Manifest, Part, Record_, blank, digest } from "./record.js";
import { MODEL_PARTS, PARTS } from "./vocab.js";

/** Static per version: a manifest that adapted to what it found could never contradict a record. */
export const FROM_A_REQUEST = ["instruction", "request_template", "tool_schemas", "readout", "decoding"] as const;

/** Only the instruction is text the model provably read; the rest are protocol values whose rendering we do not hold. */
export const REQUEST_BOUNDARIES: Record<string, string> = {
  instruction: "model_visible",
  request_template: "model_visible",
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
  messages?: unknown;
  tools?: unknown;
  response_format?: unknown;
  [key: string]: unknown;
}

/** The JSON type of a value, as a detail names it. */
function jsonType(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (Array.isArray(v)) return "an array";
  switch (typeof v) {
    case "string":
      return "a string";
    case "number":
      return "a number";
    case "boolean":
      return "a boolean";
    case "object":
      return "an object";
    default:
      return typeof v;
  }
}

/**
 * The system text, newline-joined (SPEC 2.2), or the reason it cannot be read. A system message whose content is not a
 * string fails the whole part: the chat template decides how parts become text, and the request does not carry it. The
 * detail names the message and the type found and never quotes the content.
 */
function instructionOf(messages: unknown): [string, string] {
  if (messages === undefined || messages === null) return ["", ""];
  if (!Array.isArray(messages)) return ["", `messages is ${jsonType(messages)}, not an array`];
  for (const [i, m] of messages.entries()) {
    if (m === null || typeof m !== "object" || Array.isArray(m)) return ["", `messages[${i}] is ${jsonType(m)}, not an object`];
    // A message whose role cannot be read might have been a system message.
    if (!("role" in m)) return ["", `messages[${i}].role is missing, not a string`];
    if (typeof (m as { role: unknown }).role !== "string") {
      return ["", `messages[${i}].role is ${jsonType((m as { role: unknown }).role)}, not a string`];
    }
  }
  const texts: string[] = [];
  for (const [i, m] of (messages as Record<string, unknown>[]).entries()) {
    if (m.role !== "system") continue;
    if (!("content" in m)) return ["", `messages[${i}].content is missing, not a string`];
    if (typeof m.content !== "string") return ["", `messages[${i}].content is ${jsonType(m.content)}, not a string`];
    texts.push(m.content);
  }
  return [texts.join("\n"), ""];
}

/** The top-level member of a request body that carries the request template (binding: openai-chat-completions). */
export const TEMPLATE_FIELD = "perigraph_template";

const utf8 = new TextEncoder();
/** A lone surrogate, which utf-8 encoding would silently replace with U+FFFD. */
const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/;
const wellFormed = (s: string): boolean => !LONE_SURROGATE.test(s);
const isObject = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === "object" && !Array.isArray(v);

/** Whether `content` is segs[0] h1 segs[1] ... hn segs[n]; leftmost matching of each interior string decides it. */
function fits(content: Buffer, segs: Buffer[]): boolean {
  if (segs.length === 1) return content.equals(segs[0] as Buffer);
  const first = segs[0] as Buffer;
  const last = segs[segs.length - 1] as Buffer;
  if (content.length < first.length || !content.subarray(0, first.length).equals(first)) return false;
  let pos = first.length;
  for (const seg of segs.slice(1, -1)) {
    const j = content.indexOf(seg, pos);
    if (j < 0) return false;
    pos = j + seg.length;
  }
  return content.length - last.length >= pos && content.subarray(content.length - last.length).equals(last);
}

/**
 * The `request_template` payload, null when the request declares none, or the reason it cannot be read. Only the fixed
 * strings are digested, so the item never reaches the digest; a template that fixes no text other than white space is
 * treated as not sent, and that test comes after every check. Lengths are utf-8 byte counts, not `.length`.
 */
function templateOf(template: unknown, messages: unknown): [string | null, string] {
  if (template === undefined || template === null) return [null, ""];
  const where = TEMPLATE_FIELD;
  if (!isObject(template)) return [null, `${where} is ${jsonType(template)}, not an object`];
  const keys = Object.keys(template);
  if (keys.length !== 1 || keys[0] !== "messages") return [null, `${where} has members other than messages, or lacks messages`];
  const entries = template.messages;
  if (!Array.isArray(entries)) return [null, `${where}.messages is ${jsonType(entries)}, not an array`];
  if (!Array.isArray(messages)) return [null, `messages is ${messages === undefined ? "missing" : jsonType(messages)}, not an array`];
  if (entries.length !== messages.length) {
    return [null, `${where}.messages has ${entries.length} entries and messages has ${messages.length}`];
  }
  const payload: Buffer[] = [Buffer.from(`${entries.length}:`, "utf8")];
  let namesText = false;
  for (const [i, e] of entries.entries()) {
    const at = `${where}.messages[${i}]`;
    const m = messages[i] as unknown;
    if (!isObject(e) || !("role" in e) || Object.keys(e).some((k) => k !== "role" && k !== "fixed")) {
      return [null, `${at} is not an object with role and optionally fixed`];
    }
    const role = e.role;
    if (typeof role !== "string" || !isObject(m) || m.role !== role) {
      return [null, `${at}.role is not a string equal to messages[${i}].role`];
    }
    if (!wellFormed(role)) return [null, `${at}.role is not a sequence of Unicode scalar values`];
    const rb = Buffer.from(role, "utf8");
    if (!("fixed" in e)) {
      payload.push(Buffer.from(`${rb.length}:`, "utf8"), rb, Buffer.from("0:", "utf8"));
      continue;
    }
    if (role === "system") return [null, `${at} is a system entry with fixed strings; its text is the instruction part`];
    const strings = e.fixed;
    if (!Array.isArray(strings) || strings.length === 0 || !strings.every((g) => typeof g === "string")) {
      return [null, `${at}.fixed is not a non-empty array of strings`];
    }
    const strs = strings as string[];
    if (strs.slice(1, -1).some((g) => g === "")) {
      return [null, `${at}.fixed has an empty interior string; adjacent holes are one hole`];
    }
    const content = m.content;
    if (typeof content !== "string") {
      return [null, `messages[${i}].content is ${"content" in m ? jsonType(content) : "missing"}, not a string`];
    }
    if (!wellFormed(content) || !strs.every(wellFormed)) {
      return [null, `${at} or messages[${i}].content holds a string that is not a sequence of Unicode scalar values`];
    }
    const segs = strs.map((g) => Buffer.from(utf8.encode(g)));
    if (!fits(Buffer.from(utf8.encode(content)), segs)) return [null, `messages[${i}].content does not match ${at}.fixed`];
    namesText = namesText || strs.some((g) => !blank(g));
    payload.push(Buffer.from(`${rb.length}:`, "utf8"), rb, Buffer.from(`${segs.length}:`, "utf8"));
    for (const b of segs) payload.push(Buffer.from(`${b.length}:`, "utf8"), b);
  }
  if (!namesText) return [null, ""];
  return [Buffer.concat(payload).toString("utf8"), ""];
}

/** A request collector did not load the model, so it names the four model parts absent (SPEC 6). */
function finish(opts: { collector: string; version: string }, parts: Part[], absences: Absence[]): Record_ {
  const record = new Record_(
    new Manifest(opts.collector, opts.version, [...FROM_A_REQUEST]),
    "complete",
    parts,
    absences,
    new Model([], MODEL_PARTS.map((k) => new ModelAbsence(k, "not_observable"))),
  );
  if (record.unaccounted.length > 0) {
    throw new Error(`the collector left ${record.unaccounted} unaccounted for`);
  }
  return record;
}

export function fromRequest(body: Body, opts: { collector: string; version: string }): Record_ {
  const parts: Part[] = [];
  const absences: Absence[] = [];
  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    // SPEC 1.2: a body we cannot parse is an absence we name, never a record we withhold.
    const found = jsonType(body);
    for (const k of FROM_A_REQUEST) absences.push(new Absence(k, "extraction_failed", `the body is ${found}, not an object`));
    for (const k of PUSHED_PARTS) absences.push(new Absence(k, "not_provided"));
    absences.push(new Absence("tool_extension", "not_observable"));
    absences.push(new Absence("tool_trace", "not_provided"));
    return finish(opts, parts, absences);
  }

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

  const [instruction, failed] = instructionOf(body.messages);
  if (failed !== "") {
    absences.push(new Absence("instruction", "extraction_failed", failed));
  } else if (!blank(instruction)) {
    // Hashed RAW, down to case and whitespace: the model reads the string and not its meaning.
    hold("instruction", instruction);
  } else {
    absences.push(new Absence("instruction", "not_provided"));
  }

  const [template, templateFailed] = templateOf(body[TEMPLATE_FIELD], body.messages);
  if (templateFailed !== "") {
    absences.push(new Absence("request_template", "extraction_failed", templateFailed));
  } else if (template !== null) {
    hold("request_template", template);
  } else {
    absences.push(new Absence("request_template", "not_provided"));
  }

  const rawTools = body.tools;
  let badTool = "";
  if (rawTools !== undefined && rawTools !== null && !Array.isArray(rawTools)) {
    badTool = `tools is ${jsonType(rawTools)}, not an array`;
  } else if (Array.isArray(rawTools)) {
    const i = rawTools.findIndex((t) => t === null || typeof t !== "object" || Array.isArray(t) ||
      ("function" in t && (t.function === null || typeof t.function !== "object" || Array.isArray(t.function))));
    if (i >= 0) badTool = `tools[${i}] is ${jsonType(rawTools[i])}, not an object`;
  }
  const tools = (Array.isArray(rawTools) ? rawTools : undefined) as
    | { function?: { name?: string; parameters?: unknown }; name?: string; parameters?: unknown }[]
    | undefined;
  if (badTool !== "") {
    absences.push(new Absence("tool_schemas", "extraction_failed", badTool));
  } else if (tools !== undefined && tools.length > 0) {
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
  const badFmt = fmt !== undefined && fmt !== null && (typeof fmt !== "object" || Array.isArray(fmt))
    ? `response_format is ${jsonType(fmt)}, not an object` : "";
  // An empty object is a format the sender did not choose, as an empty `tools` array is tools it did not offer.
  const chosen = badFmt === "" && fmt !== undefined && fmt !== null && Object.keys(fmt).length > 0;
  if (badFmt !== "") {
    absences.push(new Absence("readout", "extraction_failed", badFmt));
  } else if (chosen) {
    const label = "type" in (fmt as object) ? String((fmt as { type: unknown }).type) : "";
    hold("readout", scalars([["response_format", fmt]]), label);
  } else {
    absences.push(new Absence("readout", "not_provided"));
  }

  // A response_format constrains the grammar of the output, so it is decoding as well as readout (SPEC 1).
  const knobs = DECODING_KEYS.filter((k) => body[k] !== undefined && body[k] !== null).map((k) => [k, body[k]] as [string, unknown]);
  if (chosen) knobs.push(["response_format", fmt]);
  if (badFmt !== "") {
    absences.push(new Absence("decoding", "extraction_failed", badFmt));
  } else if (knobs.length > 0) {
    hold("decoding", scalars(knobs), knobs.map(([k]) => k).join(","));
  } else {
    absences.push(new Absence("decoding", "not_provided"));
  }

  for (const kind of PUSHED_PARTS) absences.push(new Absence(kind, "not_provided"));
  absences.push(new Absence("tool_extension", "not_observable"));
  // At request time the calls have not happened, so there is nothing the sender could have supplied.
  absences.push(new Absence("tool_trace", "not_provided"));

  return finish(opts, parts, absences);
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
