/**
 * What answered: the model parts, their digests, and the two identities over them (SPEC section 9).
 *
 * Written from SPEC.md section 9 and `vocabularies.json`, and checked against `fixtures-model-identity.json`. The
 * helpers take what a loader already knows -- (path, file sha256) pairs, resolved precision fields, resolved package
 * versions -- because how those become bytes is the part two implementations would otherwise do differently.
 */
import { createHash } from "node:crypto";

import { digest } from "./record.js";
import {
  ABSENCE_BLAMES,
  ABSENCE_REASONS,
  ANSWER_MODES,
  DETAIL_REQUIRED_WHEN_BLAMES,
  DIGEST,
  IDENTIFYING_MODEL_SOURCING,
  MODEL_PARTS,
  SOURCING,
  Unidentified,
} from "./vocab.js";

const HEX64 = /^[0-9a-f]{64}$/;

function sha256(text: string): string {
  return createHash(DIGEST.algorithm).update(Buffer.from(text, "utf8")).digest("hex");
}

/** Compare by utf-8 bytes, not by UTF-16 code units: the two orders differ above the BMP. */
function byUtf8(a: string, b: string): number {
  return Buffer.compare(Buffer.from(a, "utf8"), Buffer.from(b, "utf8"));
}

export function checkpointDigest(entries: Iterable<[string, string]>): string {
  const rows: [string, string][] = [];
  const seen = new Set<string>();
  for (const [path, sha] of entries) {
    if (path === "" || path.includes("\t") || path.includes("\n")) {
      throw new Unidentified(`checkpoint path ${JSON.stringify(path)} is empty or contains a tab or a newline`);
    }
    if (path.startsWith("/") || path.includes("\\") || path.split("/").some((s) => s === "" || s === "." || s === "..")) {
      throw new Unidentified(`checkpoint path ${JSON.stringify(path)} is not a normalised POSIX relative path`);
    }
    if (!HEX64.test(sha)) throw new Unidentified(`checkpoint file ${path} has a digest that is not lowercase hex sha256`);
    if (seen.has(path)) throw new Unidentified(`checkpoint path ${path} is listed twice`);
    seen.add(path);
    rows.push([path, `${path}\t${sha}\n`]);
  }
  if (rows.length === 0) throw new Unidentified("a checkpoint with no files has no content to identify");
  rows.sort((a, b) => byUtf8(a[0], b[0]));
  return sha256(rows.map((r) => r[1]).join(""));
}

export function linesDigest(pairs: Record<string, string>, sep: string): string {
  const keys = Object.keys(pairs);
  if (keys.length === 0) throw new Unidentified("an empty mapping has no content to identify");
  const rows: [string, string][] = [];
  for (const k of keys) {
    const v = String(pairs[k]);
    if (k === "" || k.includes("\n") || v.includes("\n") || k.includes(sep)) {
      throw new Unidentified(`${k}=${v} cannot be rendered as one line`);
    }
    rows.push([k, `${k}${sep}${v}\n`]);
  }
  rows.sort((a, b) => byUtf8(a[0], b[0]));
  return sha256(rows.map((r) => r[1]).join(""));
}

export function precisionDigest(fields: Record<string, string>): string {
  for (const [k, v] of Object.entries(fields)) {
    if (String(v).trim() === "" || String(v).trim().toLowerCase() === "auto") {
      throw new Unidentified(`precision field ${k}=${v} is unresolved; record the part as extraction_failed instead`);
    }
  }
  return linesDigest(fields, "=");
}

export function runtimeDigest(packages: Record<string, string>): string {
  return linesDigest(packages, "==");
}

export interface ModelPartInput {
  kind: string;
  sourcing: string;
  contentDigest?: string;
  label?: string;
  readLagSeconds?: number | null;
}

export class ModelPart {
  readonly kind: string;
  readonly sourcing: string;
  readonly contentDigest: string;
  readonly label: string;
  readonly readLagSeconds: number | null;

  constructor(input: ModelPartInput) {
    this.kind = input.kind;
    this.sourcing = input.sourcing;
    this.contentDigest = input.contentDigest ?? "";
    this.label = input.label ?? "";
    this.readLagSeconds = input.readLagSeconds ?? null;
    if (!MODEL_PARTS.includes(this.kind)) throw new Unidentified(`${this.kind} is not one of ${MODEL_PARTS}`);
    if (!SOURCING.includes(this.sourcing)) throw new Unidentified(`${this.sourcing} is not one of ${SOURCING}`);
    if (this.sourcing === "in_the_request") {
      throw new Unidentified(`model part ${this.kind} cannot be in the request: a request does not carry weights`);
    }
    if (this.sourcing === "not_observable" && this.contentDigest !== "") {
      throw new Unidentified(`model part ${this.kind} is not observable and carries a digest`);
    }
    if (this.sourcing === "pulled_by_us" && this.readLagSeconds === null) {
      throw new Unidentified(`model part ${this.kind} was pulled and carries no lag`);
    }
    if (this.sourcing !== "pulled_by_us" && this.readLagSeconds !== null) {
      throw new Unidentified(`model part ${this.kind} is ${this.sourcing} and carries a read lag`);
    }
    if (this.readLagSeconds !== null && this.readLagSeconds < 0) throw new Unidentified("negative read lag");
    if (this.contentDigest !== "" && !HEX64.test(this.contentDigest)) {
      throw new Unidentified(`model part ${this.kind} digest is not lowercase hex sha256`);
    }
    if (this.kind === "answer_mode" && this.contentDigest !== "") {
      if (!ANSWER_MODES.includes(this.label)) {
        throw new Unidentified(`answer_mode must be labelled with one of ${ANSWER_MODES}, not ${this.label}`);
      }
      if (this.contentDigest !== digest(this.label)) {
        throw new Unidentified(`answer_mode digest does not match its label ${this.label}`);
      }
    }
  }

  get identifying(): boolean {
    return this.contentDigest !== "" && IDENTIFYING_MODEL_SOURCING.includes(this.sourcing);
  }
}

export class ModelAbsence {
  constructor(
    readonly kind: string,
    readonly reason: string,
    readonly detail = "",
  ) {
    if (!MODEL_PARTS.includes(kind)) throw new Unidentified(`${kind} is not one of ${MODEL_PARTS}`);
    if (!ABSENCE_REASONS.includes(reason)) throw new Unidentified(`${reason} is not one of ${ABSENCE_REASONS}`);
    const blames = ABSENCE_BLAMES[reason];
    if (blames === DETAIL_REQUIRED_WHEN_BLAMES && detail === "") {
      throw new Unidentified(`model part ${kind} is absent because of us (${reason}) and says nothing about what failed`);
    }
    if (blames !== DETAIL_REQUIRED_WHEN_BLAMES && detail !== "") {
      throw new Unidentified(`model part ${kind} is absent as ${reason}, which is not our failure, and carries detail`);
    }
  }
}

function identity(pairs: [string, string][]): string {
  const h = createHash(DIGEST.algorithm);
  for (const [kind, d] of [...pairs].sort((a, b) => (a[0] < b[0] ? -1 : 1))) {
    h.update(Buffer.from(`${kind}=${d};`, "utf8"));
  }
  return h.digest("hex").slice(0, DIGEST.identityLength);
}

export class Model {
  constructor(
    readonly parts: readonly ModelPart[] = [],
    readonly absences: readonly ModelAbsence[] = [],
    readonly reaches: readonly string[] = [],
  ) {
    const held = parts.map((p) => p.kind);
    const absent = absences.map((a) => a.kind);
    if (new Set(held).size !== held.length || new Set(absent).size !== absent.length) {
      throw new Unidentified("a model part is listed twice");
    }
    if (held.some((k) => absent.includes(k))) throw new Unidentified("a model part is recorded as held and absent");
    if (reaches.some((r) => !MODEL_PARTS.includes(r)) || new Set(reaches).size !== reaches.length) {
      throw new Unidentified(`the manifest's model reach ${reaches} is not a set of model parts`);
    }
  }

  get hasModelIdentity(): boolean {
    const ids = new Set(this.parts.filter((p) => p.identifying).map((p) => p.kind));
    return MODEL_PARTS.every((k) => ids.has(k));
  }

  get modelIdentity(): string {
    if (!this.hasModelIdentity) throw new Unidentified("no model identity: not every model part is loaded_by_us");
    return identity(this.parts.map((p) => [p.kind, p.contentDigest]));
  }

  get hasArtifactIdentity(): boolean {
    return this.parts.some((p) => p.kind === "checkpoint" && p.identifying);
  }

  get artifactIdentity(): string {
    const cp = this.parts.find((p) => p.kind === "checkpoint" && p.identifying);
    if (cp === undefined) throw new Unidentified("no artifact identity: the checkpoint is not loaded_by_us");
    return identity([["checkpoint", cp.contentDigest]]);
  }
}

export function loaded(d: { checkpoint: string; precision: string; runtime: string; answerMode: string }): Model {
  return new Model(
    [
      new ModelPart({ kind: "checkpoint", sourcing: "loaded_by_us", contentDigest: d.checkpoint }),
      new ModelPart({ kind: "precision", sourcing: "loaded_by_us", contentDigest: d.precision }),
      new ModelPart({ kind: "runtime", sourcing: "loaded_by_us", contentDigest: d.runtime }),
      new ModelPart({ kind: "answer_mode", sourcing: "loaded_by_us", contentDigest: digest(d.answerMode), label: d.answerMode }),
    ],
    [],
    MODEL_PARTS,
  );
}
