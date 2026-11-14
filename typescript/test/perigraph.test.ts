import assert from "node:assert/strict";
import { test } from "node:test";

import * as pg from "../src/index.js";
import { fromRequest } from "../src/collect.js";
import * as vocab from "../src/vocab.js";
import { Absence, Manifest, Part, Record_, digest } from "../src/record.js";
import { fromAttributes, toAttributes } from "../src/wire.js";

const TERSE = "Answer with the option letter only. Do not explain.";
const EXPLAIN = "Think step by step, then answer with the option letter.";

const BODY = {
  messages: [
    { role: "system", content: TERSE },
    { role: "user", content: "Q1" },
  ],
  tools: [{ function: { name: "search", parameters: { type: "object" } } }],
  temperature: 0.0,
  top_p: 1.0,
};

const read = (body: unknown = BODY) => fromRequest(body as pg.Body, { collector: "t", version: "1" });
const part = (over: Partial<pg.Part> = {}) =>
  new Part({ kind: "instruction", sourcing: "in_the_request", contentDigest: digest(TERSE), ...over });

test("the spec's classifications are total", () => {
  assert.deepEqual(Object.keys(vocab.ABSENCE_BLAMES).sort(), [...vocab.ABSENCE_REASONS].sort());
  assert.deepEqual(Object.keys(vocab.DIVERGENCE_LICENSES).sort(), [...vocab.TOOL_DETERMINISM].sort());
});

test("the identity permissions are subsets of their own vocabularies", () => {
  for (const v of vocab.IDENTIFYING_SOURCING) assert.ok(vocab.SOURCING.includes(v));
  for (const v of vocab.IDENTIFYING_BOUNDARIES) assert.ok(vocab.BOUNDARIES.includes(v));
  for (const v of vocab.NEVER_IDENTIFYING) assert.ok(vocab.PARTS.includes(v));
});

test("a harness read from a request is identified by its instruction and nothing else", () => {
  const r = read();
  assert.deepEqual(r.parts.filter((p) => p.identifying).map((p) => p.kind), ["instruction"]);
  assert.deepEqual(
    r.parts.filter((p) => !p.identifying).map((p) => p.kind).sort(),
    ["decoding", "tool_schemas"],
  );
});

test("the instruction is hashed raw down to case and whitespace", () => {
  const base = read().identity;
  for (const variant of [TERSE.toLowerCase(), TERSE.toUpperCase(), "  " + TERSE, TERSE + "\n"]) {
    const other = read({ ...BODY, messages: [{ role: "system", content: variant }] });
    assert.notEqual(other.identity, base, JSON.stringify(variant));
  }
});

test("a parsed digest is recorded and never enters the hash", () => {
  const m = new Manifest("t", "1", []);
  const onlyInstruction = new Record_(m, "complete", [part()]);
  const withParsed = new Record_(m, "complete", [
    part(),
    part({ kind: "decoding", contentDigest: digest("temperature=0"), boundary: "parsed" }),
  ]);
  assert.equal(withParsed.identity, onlyInstruction.identity);
});

test("a trace may never key an identity even though we hold its bytes", () => {
  assert.equal(part({ kind: "tool_trace", contentDigest: "a".repeat(64), boundary: "model_visible" }).identifying, false);
});

test("two wordings are two harnesses", () => {
  assert.notEqual(read().identity, read({ ...BODY, messages: [{ role: "system", content: EXPLAIN }] }).identity);
});

test("the toolset digest does not depend on the order the caller listed them", () => {
  const tools = [
    { function: { name: "a", parameters: {} } },
    { function: { name: "b", parameters: {} } },
  ];
  const forward = read({ ...BODY, tools }).parts.find((p) => p.kind === "tool_schemas")!.contentDigest;
  const reverse = read({ ...BODY, tools: [...tools].reverse() }).parts.find((p) => p.kind === "tool_schemas")!
    .contentDigest;
  assert.equal(forward, reverse);
});

test("the sender's silence is not a contradiction", () => {
  const r = read({ messages: [{ role: "system", content: TERSE }] });
  assert.deepEqual(r.contradictions, []);
  assert.deepEqual(r.ourFailures, []);
  assert.equal(r.admissibleToAVerdict(), true);
});

test("a denial of the manifest's claim is a contradiction", () => {
  const r = new Record_(
    new Manifest("t", "1", ["instruction", "decoding"]),
    "complete",
    [part()],
    [new Absence("decoding", "not_reachable", "renamed field")],
  );
  assert.deepEqual(r.contradictions, ["decoding"]);
  assert.equal(r.admissibleToAVerdict(), false);
});

test("a claimed part nobody said anything about is a contradiction", () => {
  const r = new Record_(new Manifest("t", "1", ["instruction", "decoding"]), "complete", [part()]);
  assert.deepEqual(r.contradictions, ["decoding"]);
});

test("a request with no instruction keeps its parts and supports no claim", () => {
  const r = read({ messages: [{ role: "user", content: "Q" }], temperature: 0 });
  assert.deepEqual(r.parts.map((p) => p.kind), ["decoding"]);
  assert.equal(r.hasIdentity, false);
  assert.throws(() => r.identity, /constant across every possible harness/);
  assert.equal(r.admissibleToAVerdict(), false);
});

test("a collector that did not finish cannot look complete", () => {
  const r = new Record_(new Manifest("t", "1", []), "collector_failed", [part()]);
  assert.equal(r.admissibleToAVerdict(), false);
  assert.match(r.whyNot(), /does not describe the run/);
});

test("a part cannot be held and absent at once", () => {
  assert.throws(
    () =>
      new Record_(new Manifest("t", "1", []), "complete", [part()], [new Absence("instruction", "not_provided")]),
    /two ways/,
  );
});

test("our own failure has to say what we were doing, and nothing else may", () => {
  assert.throws(() => new Absence("decoding", "extraction_failed"), /nobody described/);
  assert.throws(() => new Absence("decoding", "not_provided", "we were busy"), /no such moment/);
});

test("the collector accounts for every part it names", () => {
  assert.deepEqual(read().unaccounted, []);
  assert.deepEqual(read({ messages: [] }).unaccounted, []);
});

test("the manifest is static per version so it can actually contradict", () => {
  assert.deepEqual([...read().manifest.reaches], [...pg.FROM_A_REQUEST]);
  assert.deepEqual([...read({ messages: [] }).manifest.reaches], [...pg.FROM_A_REQUEST]);
});

test("a declaration replaces the absence and still cannot identify", () => {
  const d = pg.declare(read(), { loop: "react v3", turn_budget: "8" });
  const declared = d.parts.filter((p) => p.sourcing === "pushed_by_owner");
  assert.deepEqual(declared.map((p) => p.kind).sort(), ["loop", "turn_budget"]);
  assert.ok(!declared.some((p) => p.identifying));
  assert.equal(d.identity, read().identity);
});

test("the wire form round trips", () => {
  const r = read();
  const back = fromAttributes(toAttributes(r));
  assert.equal(back.identity, r.identity);
  assert.deepEqual(
    back.absences.map((a) => [a.kind, a.reason]).sort(),
    r.absences.map((a) => [a.kind, a.reason]).sort(),
  );
});

test("an empty manifest round trips rather than becoming a part named empty-string", () => {
  // AMBIGUITY 5: splitting "" on "," yields [""] in both languages.
  const r = new Record_(new Manifest("t", "1", []), "complete", [part()]);
  const back = fromAttributes(toAttributes(r));
  assert.deepEqual([...back.manifest.reaches], []);
});

test("an absent identity is omitted rather than empty", () => {
  const attrs = toAttributes(read({ messages: [{ role: "user", content: "Q" }], temperature: 0 }));
  assert.equal(attrs["perigraph.harness_identity"], undefined);
});

test("every wire value is a scalar a tracer will accept", () => {
  for (const [key, value] of Object.entries(toAttributes(read()))) {
    assert.ok(typeof value === "string" || typeof value === "number", key);
  }
});

test("a version this reader does not implement is refused rather than guessed at", () => {
  const attrs = toAttributes(read());
  attrs["perigraph.spec_version"] = 99;
  assert.throws(() => fromAttributes(attrs), /dropped absence/);
});

test("wrapping preserves the return value and records on the way past", () => {
  const seen: Record_[] = [];
  const wrapped = pg.wrap((_body: unknown) => ({ ok: true }), { onRecord: (r) => seen.push(r) });
  assert.deepEqual(wrapped(BODY), { ok: true });
  assert.equal(seen[0]!.admissibleToAVerdict(), true);
});

test("a body it cannot find never breaks the call", () => {
  const seen: Record_[] = [];
  const wrapped = pg.wrap((x: number) => x * 2, { onRecord: (r) => seen.push(r) });
  assert.equal(wrapped(21), 42);
  assert.equal(seen[0]!.status, "collector_failed");
});

test("a sink that throws never breaks the call either", () => {
  const wrapped = pg.wrap((_body: unknown) => "sent", {
    onRecord: () => {
      throw new Error("the sink is broken");
    },
  });
  assert.equal(wrapped(BODY), "sent");
});

test("emit sets every attribute on a span and survives one it rejects", () => {
  const rejected = "perigraph.collector";
  const set: Record<string, string | number> = {};
  const span: pg.SpanLike = {
    setAttribute(key, value) {
      if (key === rejected) throw new Error("this tracer dislikes this key");
      set[key] = value;
    },
  };
  const attrs = pg.emit(read(), span);
  assert.equal(Object.keys(attrs)[1], rejected, "the rejected key has to be early for this test to mean anything");
  assert.equal(set[rejected], undefined);
  assert.deepEqual(
    Object.keys(attrs).filter((k) => k !== rejected).sort(),
    Object.keys(set).sort(),
  );
});

// --- the golden fixtures both implementations must reproduce -----------------------------------------------------------

import { createRequire } from "node:module";
const require_ = createRequire(import.meta.url);
const FIXTURES = require_("../fixtures-identity.json") as {
  cases: { name: string; body: unknown; identity: string | null; instruction_digest: string | null }[];
};

test("every golden identity is reproduced", () => {
  // This is the test that justifies the second implementation existing. The identity serialisation and the utf-8
  // encoding were NOT in the spec; this file could not have matched these values until they were added.
  for (const c of FIXTURES.cases) {
    const r = fromRequest(c.body as pg.Body, { collector: "fixture", version: "1" });
    if (c.identity === null) assert.equal(r.hasIdentity, false, c.name);
    else assert.equal(r.identity, c.identity, c.name);
    const got = r.parts.find((p) => p.kind === "instruction")?.contentDigest ?? null;
    assert.equal(got, c.instruction_digest, c.name);
  }
});

test("a non-ascii instruction is covered, because that is where an encoding disagreement shows", () => {
  const anyNonAscii = FIXTURES.cases.some((c) =>
    ((c.body as { messages: { content?: string }[] }).messages ?? []).some((m) =>
      typeof m.content === "string" && [...m.content].some((ch) => ch.codePointAt(0)! > 127),
    ),
  );
  assert.ok(anyNonAscii);
});

// --- version 2: the model half -------------------------------------------------------------------------------------------

import { createHash } from "node:crypto";
import * as model from "../src/model.js";

const MODEL_FIXTURES = require_("../fixtures-model-identity.json") as {
  cases: {
    name: string;
    files: Record<string, string>;
    precision: Record<string, string>;
    runtime: Record<string, string>;
    answer_mode: string;
    checkpoint_digest: string;
    precision_digest: string;
    runtime_digest: string;
    model_identity: string;
    artifact_identity: string;
  }[];
  refused_precision: { cases: Record<string, string>[] };
};

const sha = (t: string) => createHash("sha256").update(Buffer.from(t, "utf8")).digest("hex");

test("every golden model identity is reproduced", () => {
  for (const c of MODEL_FIXTURES.cases) {
    const cp = model.checkpointDigest(Object.entries(c.files).map(([p, t]) => [p, sha(t)] as [string, string]));
    assert.equal(cp, c.checkpoint_digest, c.name);
    assert.equal(model.precisionDigest(c.precision), c.precision_digest, c.name);
    assert.equal(model.runtimeDigest(c.runtime), c.runtime_digest, c.name);
    const m = model.loaded({ checkpoint: cp, precision: c.precision_digest, runtime: c.runtime_digest, answerMode: c.answer_mode });
    assert.equal(m.modelIdentity, c.model_identity, c.name);
    assert.equal(m.artifactIdentity, c.artifact_identity, c.name);
  }
});

test("every unresolved precision fixture is refused (SPEC 9)", () => {
  for (const p of MODEL_FIXTURES.refused_precision.cases) assert.throws(() => model.precisionDigest(p), JSON.stringify(p));
});

test("int8 at load is a different model and the same artifact", () => {
  const a = MODEL_FIXTURES.cases[0]!;
  const b = MODEL_FIXTURES.cases[1]!;
  assert.notEqual(a.model_identity, b.model_identity);
  assert.equal(a.artifact_identity, b.artifact_identity);
});

test("a request never carries a model part and a harness part is never loaded", () => {
  assert.throws(() => new model.ModelPart({ kind: "checkpoint", sourcing: "in_the_request", contentDigest: "a".repeat(64) }));
  assert.throws(() => new Part({ kind: "instruction", sourcing: "loaded_by_us", contentDigest: digest(TERSE) }));
});

test("the model half round-trips over the wire and a forged identity is refused", () => {
  const c = MODEL_FIXTURES.cases[2]!;
  const m = model.loaded({ checkpoint: c.checkpoint_digest, precision: c.precision_digest, runtime: c.runtime_digest, answerMode: c.answer_mode });
  const base = read();
  const r = new Record_(base.manifest, base.status, base.parts, base.absences, m);
  const attrs = toAttributes(r);
  assert.equal(attrs["perigraph.model_identity"], c.model_identity);
  assert.equal(attrs["perigraph.artifact_identity"], c.artifact_identity);
  const back = fromAttributes(attrs);
  assert.equal((back.model as model.Model).modelIdentity, c.model_identity);
  assert.throws(() => fromAttributes({ ...attrs, "perigraph.model_identity": "0".repeat(24) }), /does not follow/);
});

test("a body that is not an object is named, not a crash (SPEC 1.2)", () => {
  const a = toAttributes(read(null));
  assert.equal(a["perigraph.status"], "complete");
  for (const k of ["instruction", "tool_schemas", "readout", "decoding"]) {
    assert.equal(a[`perigraph.absent.${k}.reason`], "extraction_failed");
    assert.equal(a[`perigraph.absent.${k}.detail`], "the body is null, not an object");
  }
});

test("messages that is not an array fails only what is read from messages (SPEC 1.2)", () => {
  const a = toAttributes(read({ messages: "x", temperature: 0.0 }));
  assert.equal(a["perigraph.absent.instruction.reason"], "extraction_failed");
  assert.equal(a["perigraph.absent.instruction.detail"], "messages is a string, not an array");
  assert.equal(a["perigraph.part.decoding.sourcing"], "in_the_request");
});

test("a system message with an array of parts fails the instruction without quoting it (SPEC 2.2)", () => {
  const body = {
    messages: [
      { role: "system", content: "Terse." },
      { role: "system", content: [{ type: "text", text: "secret prompt" }] },
    ],
  };
  const a = toAttributes(read(body));
  assert.equal(a["perigraph.absent.instruction.reason"], "extraction_failed");
  assert.equal(a["perigraph.absent.instruction.detail"], "messages[1].content is an array, not a string");
  assert.ok(!JSON.stringify(a).includes("secret"));
  assert.ok(!("perigraph.harness_identity" in a));
});

test("a request collector says the model was not observable (SPEC 6)", () => {
  const a = toAttributes(read());
  for (const k of ["checkpoint", "precision", "runtime", "answer_mode"]) {
    assert.equal(a[`perigraph.model_absent.${k}.reason`], "not_observable");
  }
  assert.ok(!("perigraph.model_identity" in a) && !("perigraph.artifact_identity" in a));
});

test("a record with no model half is read, not refused (SPEC 6)", () => {
  const a: Record<string, string | number> = Object.fromEntries(
    Object.entries(toAttributes(read())).filter(([k]) => !k.includes("model")));
  assert.equal(fromAttributes(a).model, null);
  a["perigraph.model.checkpoint.sourcing"] = "not_observable";
  a["perigraph.model.checkpoint.label"] = "provider-x";
  assert.ok(!fromAttributes(a).model!.hasModelIdentity);
});

test("a null top-level field is one the sender did not send (SPEC 1.2)", () => {
  for (const field of ["messages", "tools", "response_format", "temperature"]) {
    const without = Object.fromEntries(Object.entries(BODY).filter(([k]) => k !== field));
    assert.deepEqual(toAttributes(read({ ...BODY, [field]: null })), toAttributes(read(without)));
  }
});

test("a dtype named auto is unresolved as a value of auto is (SPEC 9)", async () => {
  const { precisionDigest } = await import("../src/model.js");
  for (const f of [
    { "dtype.auto": "1", quantisation: "none", device: "cuda" },
    { "dtype.bfloat16": "auto", quantisation: "none", device: "cuda" },
    { "dtype.bfloat16": "1", quantisation: "AUTO", device: "cuda" },
  ]) {
    assert.throws(() => precisionDigest(f), pg.Unidentified);
  }
});
