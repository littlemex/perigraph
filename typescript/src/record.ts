/**
 * The record: parts held, parts absent with whose absence each is, and how the collector itself did.
 *
 * Written from `SPEC.md` sections 1 and 2. Three places needed a decision the spec did not supply, and each is marked
 * `AMBIGUITY` below with what was chosen and why. They are not defects in this file -- they are the spec being read for
 * the first time by something other than its author.
 */
import { createHash } from "node:crypto";

import {
  ABSENCE_BLAMES,
  ABSENCE_REASONS,
  ADMISSIBLE_STATUS,
  BOUNDARIES,
  DETAIL_REQUIRED_WHEN_BLAMES,
  DIGEST,
  IDENTIFYING_BOUNDARIES,
  IDENTIFYING_SOURCING,
  NEVER_IDENTIFYING,
  PARTS,
  SOURCING,
  STATUS,
  Unidentified,
} from "./vocab.js";

/**
 * Hash a part's content.
 *
 * AMBIGUITY 1 (now fixed in the spec): section 5 said "lowercase hex sha256 of the part's bytes" and never said what
 * bytes a STRING has. UTF-8 is the only defensible reading and is what the first implementation did, but nothing said
 * so -- and a UTF-16 implementation would have produced a different identity for every non-ASCII instruction while
 * passing every test it wrote for itself.
 */
export function digest(payload: string): string {
  if (payload.trim() === "") {
    throw new Unidentified(
      "an empty payload has no content to identify; a part that is genuinely empty is a part that was not applied, " +
        "and that is a different record",
    );
  }
  return createHash(DIGEST.algorithm).update(Buffer.from(payload, "utf8")).digest("hex");
}

export interface PartInput {
  kind: string;
  sourcing: string;
  label?: string;
  contentDigest?: string;
  boundary?: string;
  readLagSeconds?: number | null;
}

export class Part {
  readonly kind: string;
  readonly sourcing: string;
  readonly label: string;
  readonly contentDigest: string;
  readonly boundary: string;
  readonly readLagSeconds: number | null;

  constructor(input: PartInput) {
    this.kind = input.kind;
    this.sourcing = input.sourcing;
    this.label = input.label ?? "";
    this.contentDigest = input.contentDigest ?? "";
    this.boundary = input.boundary ?? "model_visible";
    this.readLagSeconds = input.readLagSeconds ?? null;

    if (!PARTS.includes(this.kind)) {
      throw new Unidentified(
        `${this.kind} is not one of ${PARTS}. A part nobody named is a part that can change without the identity ` +
          `changing, which is the defect this vocabulary exists to close`,
      );
    }
    if (!SOURCING.includes(this.sourcing)) throw new Unidentified(`${this.sourcing} is not one of ${SOURCING}`);
    if (!BOUNDARIES.includes(this.boundary)) throw new Unidentified(`${this.boundary} is not one of ${BOUNDARIES}`);
    if (this.sourcing === "not_observable" && this.contentDigest !== "") {
      throw new Unidentified(
        `${this.kind} is recorded as not observable and carries a digest, so something was hashed. If bytes exist, ` +
          `name the mode that produced them; if they do not, the digest is of something else`,
      );
    }
    if (this.sourcing === "pulled_by_us" && this.readLagSeconds === null) {
      throw new Unidentified(
        `${this.kind} was pulled and carries no lag. We read at one moment and the request ran at another; a lag ` +
          `nobody wrote down is a lag nobody can bound`,
      );
    }
    if (this.sourcing !== "pulled_by_us" && this.readLagSeconds !== null) {
      throw new Unidentified(
        `${this.kind} is ${this.sourcing} and carries a read lag, which only a pulled fact has`,
      );
    }
    if (this.readLagSeconds !== null && this.readLagSeconds < 0) {
      throw new Unidentified(
        `readLagSeconds=${this.readLagSeconds} would mean it was read after the request it describes`,
      );
    }
  }

  /** All three conditions, per SPEC section 2. A part failing any of them is recorded and never enters the hash. */
  get identifying(): boolean {
    if (NEVER_IDENTIFYING.includes(this.kind)) return false;
    if (this.contentDigest === "") return false;
    if (!IDENTIFYING_BOUNDARIES.includes(this.boundary)) return false;
    return IDENTIFYING_SOURCING.includes(this.sourcing);
  }

  toString(): string {
    const who: Record<string, string> = {
      in_the_request: "in the request",
      pulled_by_us: "pulled",
      pushed_by_owner: "owner says",
      not_observable: "NOT OBSERVABLE",
    };
    let head = `${this.kind} (${who[this.sourcing]}`;
    if (this.readLagSeconds !== null) head += `, ${this.readLagSeconds}s before the request`;
    head += ")";
    const label = this.label === "" ? "" : ` ${this.label}`;
    const dig = this.contentDigest === "" ? "" : ` ${this.contentDigest.slice(0, 8)}@${this.boundary}`;
    return head + label + dig;
  }
}

export class Absence {
  readonly kind: string;
  readonly reason: string;
  readonly detail: string;

  constructor(kind: string, reason: string, detail = "") {
    this.kind = kind;
    this.reason = reason;
    this.detail = detail;
    if (!PARTS.includes(kind)) {
      throw new Unidentified(
        `${kind} is not one of ${PARTS}. An absence of something the vocabulary does not name is a hole in the ` +
          `vocabulary rather than in the record`,
      );
    }
    if (!ABSENCE_REASONS.includes(reason)) throw new Unidentified(`${reason} is not one of ${ABSENCE_REASONS}`);
    if (this.blames === DETAIL_REQUIRED_WHEN_BLAMES && detail === "") {
      throw new Unidentified(
        `${kind} is absent because of us (${reason}) and carries no detail. A measurement failure nobody described ` +
          `will read as the sender's silence at every later glance`,
      );
    }
    if (this.blames !== DETAIL_REQUIRED_WHEN_BLAMES && detail !== "") {
      throw new Unidentified(
        `${kind} is absent as ${reason}, which is not our failure, and carries detail. Detail here describes what we ` +
          `were doing when we failed; there is no such moment`,
      );
    }
  }

  get blames(): string {
    return ABSENCE_BLAMES[this.reason] as string;
  }

  toString(): string {
    const head = `${this.kind} absent (${this.reason}, blames ${this.blames})`;
    return this.detail === "" ? head : `${head}: ${this.detail}`;
  }
}

export class Manifest {
  constructor(
    readonly collector: string,
    readonly version: string,
    readonly reaches: readonly string[],
  ) {
    if (collector === "" || version === "") {
      throw new Unidentified(
        "a manifest without a collector and a version cannot be compared against another run's, so a part that " +
          "stopped being readable between two versions is a change nobody can attribute",
      );
    }
    const unknown = reaches.filter((r) => !PARTS.includes(r));
    if (unknown.length > 0) throw new Unidentified(`the manifest claims to reach ${unknown}, which are not parts`);
    if (new Set(reaches).size !== reaches.length) {
      throw new Unidentified(`the manifest lists a part twice in ${[...reaches].sort()}`);
    }
  }

  toString(): string {
    return `${this.collector}/${this.version} reaches [${this.reaches.join(", ")}]`;
  }
}

export class Record_ {
  readonly manifest: Manifest;
  readonly status: string;
  readonly parts: readonly Part[];
  readonly absences: readonly Absence[];

  constructor(manifest: Manifest, status = "complete", parts: readonly Part[] = [], absences: readonly Absence[] = []) {
    this.manifest = manifest;
    this.status = status;
    this.parts = parts;
    this.absences = absences;
    if (!STATUS.includes(status)) throw new Unidentified(`${status} is not one of ${STATUS}`);
    const held = parts.map((p) => p.kind);
    if (new Set(held).size !== held.length) {
      throw new Unidentified(`two parts share a kind in ${[...held].sort()}, so nothing says which one applied`);
    }
    const absent = absences.map((a) => a.kind);
    if (new Set(absent).size !== absent.length) {
      throw new Unidentified(`two absences share a kind in ${[...absent].sort()}`);
    }
    const both = held.filter((k) => absent.includes(k)).sort();
    if (both.length > 0) {
      throw new Unidentified(
        `${both} are recorded as held and as absent at once, so this record answers 'was this collected' two ways ` +
          `and a consumer reads whichever it happened to check first`,
      );
    }
  }

  get hasIdentity(): boolean {
    return this.parts.some((p) => p.identifying);
  }

  /**
   * AMBIGUITY 2 (now fixed in the spec): section 2 said "a digest over its identifying parts, sorted by part name" and
   * never said HOW they are joined, nor that the result is truncated. This implementation could not have produced an
   * identity matching the first one from the spec alone -- and two implementations that disagree on an identity cannot
   * group anything together, which is the one thing the identity is for.
   */
  get identity(): string {
    if (!this.hasIdentity) {
      throw new Unidentified(
        "no part of this record is identified by bytes we hold that the model provably read, so an identity would be " +
          "constant across every possible harness",
      );
    }
    const h = createHash(DIGEST.algorithm);
    for (const p of [...this.parts].filter((p) => p.identifying).sort((a, b) => (a.kind < b.kind ? -1 : 1))) {
      h.update(Buffer.from(`${p.kind}=${p.contentDigest};`, "utf8"));
    }
    return h.digest("hex").slice(0, DIGEST.identityLength);
  }

  get unaccounted(): string[] {
    const named = new Set([...this.parts.map((p) => p.kind), ...this.absences.map((a) => a.kind)]);
    return PARTS.filter((k) => !named.has(k));
  }

  get contradictions(): string[] {
    const held = new Set(this.parts.map((p) => p.kind));
    const denied = new Set(this.absences.filter((a) => a.reason === "not_reachable").map((a) => a.kind));
    const explained = new Set(this.absences.map((a) => a.kind));
    return this.manifest.reaches.filter((k) => denied.has(k) || (!held.has(k) && !explained.has(k)));
  }

  get ourFailures(): string[] {
    return this.absences.filter((a) => a.blames === "collector").map((a) => a.kind);
  }

  admissibleToAVerdict(): boolean {
    return ADMISSIBLE_STATUS.includes(this.status) && this.contradictions.length === 0 && this.hasIdentity;
  }

  whyNot(): string {
    if (this.admissibleToAVerdict()) {
      return `admissible: ${this.status}, no contradiction, identity ${this.identity}`;
    }
    const reasons: string[] = [];
    if (!ADMISSIBLE_STATUS.includes(this.status)) {
      reasons.push(`the collector reports ${this.status}, so the record does not describe the run it looks like`);
    }
    if (this.contradictions.length > 0) {
      reasons.push(
        `the manifest claims to reach ${this.contradictions} and did not deliver them, so no absence here can be read ` +
          `at face value`,
      );
    }
    if (!this.hasIdentity) {
      reasons.push(
        "no part was identified by bytes we hold that the model provably read, so the identity would be the same for " +
          "every possible harness",
      );
    }
    return "not admissible to a verdict -- " + reasons.join("; and ");
  }

  toString(): string {
    const who = this.hasIdentity ? this.identity : "no identity";
    return (
      `record ${who} (${this.status}); held ${this.parts.length}; absent ${this.absences.length}; ` +
      `unaccounted [${this.unaccounted.join(", ")}]; contradictions [${this.contradictions.join(", ")}]`
    );
  }
}
