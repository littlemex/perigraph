/**
 * The closed vocabularies, read from the normative spec rather than retyped beside it.
 *
 * This file is the reason a second implementation is worth having. Retyping a list is how two sides drift, so both read
 * `vocabularies.json` -- and where this implementation had to GUESS because the spec did not say, the guess is marked
 * `AMBIGUITY` in a comment. Those marks are the deliverable: a spec with one implementation has not been tested as a
 * spec, and every one of them is a sentence that read two ways.
 */
import { createRequire } from "node:module";

const require_ = createRequire(import.meta.url);
const SPEC = require_("../vocabularies.json") as SpecShape;

interface Vocabulary {
  values: string[];
  may_key_identity?: string[];
}

interface SpecShape {
  spec_version: number;
  namespace: string;
  parts: Vocabulary;
  sourcing: Vocabulary;
  boundaries: Vocabulary;
  never_identifying: Vocabulary;
  absence_reasons: Vocabulary & { blames: Record<string, string>; detail_required_when_blames: string };
  status: Vocabulary & { admissible_to_a_verdict: string[] };
  context_crossings: Vocabulary;
  tool_determinism: Vocabulary & { divergence_licenses: Record<string, string> };
  occasion: { fields: string[] };
  billed_legs: Vocabulary & { all_or_nothing: string[] };
  digest?: { algorithm?: string; encoding?: string; identity_length?: number; serialisation?: string };
}

export const SPEC_VERSION = SPEC.spec_version;
export const NAMESPACE = SPEC.namespace;
export const PARTS = SPEC.parts.values;
export const SOURCING = SPEC.sourcing.values;
export const IDENTIFYING_SOURCING = SPEC.sourcing.may_key_identity ?? [];
export const BOUNDARIES = SPEC.boundaries.values;
export const IDENTIFYING_BOUNDARIES = SPEC.boundaries.may_key_identity ?? [];
export const NEVER_IDENTIFYING = SPEC.never_identifying.values;
export const ABSENCE_REASONS = SPEC.absence_reasons.values;
export const ABSENCE_BLAMES = SPEC.absence_reasons.blames;
export const DETAIL_REQUIRED_WHEN_BLAMES = SPEC.absence_reasons.detail_required_when_blames;
export const STATUS = SPEC.status.values;
export const ADMISSIBLE_STATUS = SPEC.status.admissible_to_a_verdict;
export const CONTEXT_CROSSINGS = SPEC.context_crossings.values;
export const TOOL_DETERMINISM = SPEC.tool_determinism.values;
export const DIVERGENCE_LICENSES = SPEC.tool_determinism.divergence_licenses;
export const OCCASION_FIELDS = SPEC.occasion.fields;
export const BILLED_LEGS = SPEC.billed_legs.values;

/** How an identity and a part digest are computed. Added to the spec BECAUSE this implementation could not
 *  interoperate without it -- see `docs/ambiguities.md`. */
export const DIGEST = {
  algorithm: SPEC.digest?.algorithm ?? "sha256",
  encoding: SPEC.digest?.encoding ?? "utf-8",
  identityLength: SPEC.digest?.identity_length ?? 24,
  serialisation: SPEC.digest?.serialisation ?? "part_name_equals_digest_semicolon",
};

/** A record was built in a way that lets two different harnesses wear one identity. */
export class Unidentified extends Error {
  constructor(message: string) {
    super(message);
    this.name = "Unidentified";
  }
}

/** What a third implementation must reproduce. Returned as data so it can be compared without sharing this file. */
export function conformance(): Record<string, unknown> {
  return {
    spec_version: SPEC_VERSION,
    namespace: NAMESPACE,
    parts: PARTS,
    sourcing: SOURCING,
    boundaries: BOUNDARIES,
    absence_reasons: ABSENCE_REASONS,
    status: STATUS,
    context_crossings: CONTEXT_CROSSINGS,
    tool_determinism: TOOL_DETERMINISM,
    billed_legs: BILLED_LEGS,
  };
}

/**
 * Refuse a spec whose classifications do not cover their own vocabularies.
 *
 * Run at module load, for the same reason the Python side does it: a value missing from one of these tables does not
 * fail loudly on its own, it falls through to whatever this reader's default is -- which is how a measurement failure
 * gets recorded as a fact about the world.
 */
export function checkSpecIsTotal(): void {
  const blamed = Object.keys(ABSENCE_BLAMES).sort();
  if (JSON.stringify(blamed) !== JSON.stringify([...ABSENCE_REASONS].sort())) {
    throw new Unidentified(
      `absence_reasons.blames covers ${blamed} and the vocabulary is ${[...ABSENCE_REASONS].sort()}. A reason with no ` +
        `blame falls through to the reader's default, which is how a collector's failure gets recorded as the sender's silence`,
    );
  }
  const licensed = Object.keys(DIVERGENCE_LICENSES).sort();
  if (JSON.stringify(licensed) !== JSON.stringify([...TOOL_DETERMINISM].sort())) {
    throw new Unidentified(
      `tool_determinism.divergence_licenses covers ${licensed} and the vocabulary is ${[...TOOL_DETERMINISM].sort()}`,
    );
  }
  for (const [name, subset, whole] of [
    ["sourcing", IDENTIFYING_SOURCING, SOURCING],
    ["boundaries", IDENTIFYING_BOUNDARIES, BOUNDARIES],
    ["never_identifying", NEVER_IDENTIFYING, PARTS],
  ] as const) {
    const extra = subset.filter((v) => !whole.includes(v));
    if (extra.length > 0) {
      throw new Unidentified(`${name} names ${extra}, which is not in its own vocabulary`);
    }
  }
}

checkSpecIsTotal();
