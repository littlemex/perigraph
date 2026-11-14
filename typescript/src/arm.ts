/**
 * One verdict over records grouped as one arm (SPEC section 4): the rules that read several records at once. Every
 * rule only subtracts: an arm whose records all say nothing about a part is admitted exactly as an arm whose records all
 * say the same thing, so no declaration can lift a refusal.
 */
import type { Record_ } from "./record.js";
import { KNOWN_WHEN_ABSENT_AS, UNIFORM_WITHIN_ARM } from "./vocab.js";

export interface ArmAdmission {
  outcome: "admitted" | "refused" | "unknown";
  reasons: string[];
}

function state(r: Record_, kind: string): [string, string] {
  const p = r.parts.find((x) => x.kind === kind);
  if (p !== undefined) return p.boundary === "canonical_value" && p.contentDigest !== "" ? ["held", p.contentDigest] : ["unknown", ""];
  const a = r.absences.find((x) => x.kind === kind);
  if (a !== undefined) return a.reason === KNOWN_WHEN_ABSENT_AS ? ["none", ""] : ["unknown", ""];
  return ["unknown", ""];
}

export function admitArm(records: readonly Record_[]): ArmAdmission {
  if (records.length === 0) return { outcome: "refused", reasons: ["an arm of no records"] };
  const refused: string[] = [];
  const unknown: string[] = [];
  records.forEach((r, i) => {
    if (!r.admissibleToAVerdict()) refused.push(`record ${i}: ${r.whyNot()}`);
  });
  const ids = new Set(records.filter((r) => r.hasIdentity).map((r) => r.identity));
  if (ids.size > 1) refused.push(`${ids.size} harness identities in one arm`);
  const models = new Set(records.map((r) => (r.model !== null && r.model.hasModelIdentity ? r.model.modelIdentity : null)));
  if (models.size > 1) refused.push(`${models.size} model identity states in one arm (some may be none)`);
  for (const kind of UNIFORM_WITHIN_ARM) {
    const states = records.map((r) => state(r, kind));
    const held = new Set(states.filter(([s]) => s === "held").map(([, d]) => d));
    if (held.size > 1) refused.push(`${kind} is held with ${held.size} different digests`);
    else if (held.size > 0 && states.some(([s]) => s === "none")) {
      refused.push(`${kind} is held by some records and absent as ${KNOWN_WHEN_ABSENT_AS} in others`);
    } else if (states.some(([s]) => s === "unknown")) unknown.push(`${kind} is unknown for some record`);
  }
  const unlisted = new Set(
    records.map((r) => (r.unlisted === null ? "<none>" : JSON.stringify([[...new Set(r.unlisted)].sort(), r.unlistedOmitted]))),
  );
  if (unlisted.size > 1) refused.push("the records' unlisted request members differ, or some records name them and some do not");
  if (refused.length > 0) return { outcome: "refused", reasons: refused };
  if (unknown.length > 0) return { outcome: "unknown", reasons: unknown };
  return { outcome: "admitted", reasons: [] };
}
