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
  assert.equal(attrs["perigraph.identity"], undefined);
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
  cases: { name: string; body: unknown; identity: string; instruction_digest: string | null }[];
};

test("every golden identity is reproduced", () => {
  // This is the test that justifies the second implementation existing. The identity serialisation and the utf-8
  // encoding were NOT in the spec; this file could not have matched these values until they were added.
  for (const c of FIXTURES.cases) {
    const r = fromRequest(c.body as pg.Body, { collector: "fixture", version: "1" });
    assert.equal(r.identity, c.identity, c.name);
    const got = r.parts.find((p) => p.kind === "instruction")?.contentDigest ?? null;
    assert.equal(got, c.instruction_digest, c.name);
  }
});

test("a non-ascii instruction is covered, because that is where an encoding disagreement shows", () => {
  const anyNonAscii = FIXTURES.cases.some((c) =>
    ((c.body as { messages: { content?: string }[] }).messages ?? []).some((m) =>
      [...(m.content ?? "")].some((ch) => ch.codePointAt(0)! > 127),
    ),
  );
  assert.ok(anyNonAscii);
});
