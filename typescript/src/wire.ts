/**
 * The wire form: a record flattened into prefixed scalar attributes, and read back.
 *
 * AMBIGUITY 5 (now fixed in the spec): `perigraph.collector_reaches` is described as "comma-separated part names", and
 * nothing said what an EMPTY manifest looks like. An empty string and an absent key are different things on the wire,
 * and a reader splitting "" on "," gets `[""]` in both JavaScript and Python -- which is a manifest claiming a part
 * named empty-string, and `Manifest` then refuses the record. The first implementation filtered the empty entry out
 * silently; this one hit it as a crash on the first empty manifest it built.
 */
import { Model, ModelAbsence, ModelPart } from "./model.js";
import { Absence, Manifest, Part, Record_ } from "./record.js";
import { NAMESPACE, OPENAI_MEMBERS, SPEC_VERSION, UNLISTED_NAMES_MAX, UNLISTED_NAME_PATTERN, Unidentified } from "./vocab.js";

export const PREFIX = NAMESPACE;

export type Attributes = Record<string, string | number>;

export function toAttributes(record: Record_): Attributes {
  const out: Attributes = {
    [`${PREFIX}.spec_version`]: SPEC_VERSION,
    [`${PREFIX}.collector`]: record.manifest.collector,
    [`${PREFIX}.collector_version`]: record.manifest.version,
    [`${PREFIX}.collector_reaches`]: record.manifest.reaches.join(","),
    [`${PREFIX}.status`]: record.status,
  };
  // Omitted rather than empty: an empty identity compares equal to another empty identity, which would group every
  // unidentifiable run together -- the failure the identity rules exist to prevent, reintroduced by the transport.
  if (record.hasIdentity) out[`${PREFIX}.harness_identity`] = record.identity;
  if (record.unlisted !== null) {
    out[`${PREFIX}.request.unlisted`] = record.unlisted.join(",");
    out[`${PREFIX}.request.unlisted_omitted`] = record.unlistedOmitted;
  }
  const m = record.model;
  if (m instanceof Model) {
    out[`${PREFIX}.model_reaches`] = m.reaches.join(",");
    if (m.hasModelIdentity) out[`${PREFIX}.model_identity`] = m.modelIdentity;
    if (m.hasArtifactIdentity) out[`${PREFIX}.artifact_identity`] = m.artifactIdentity;
    for (const mp of m.parts) {
      const base = `${PREFIX}.model.${mp.kind}`;
      out[`${base}.sourcing`] = mp.sourcing;
      if (mp.contentDigest !== "") out[`${base}.digest`] = mp.contentDigest;
      if (mp.label !== "") out[`${base}.label`] = mp.label;
      if (mp.readLagSeconds !== null) out[`${base}.read_lag_seconds`] = mp.readLagSeconds;
    }
    for (const ma of m.absences) {
      out[`${PREFIX}.model_absent.${ma.kind}.reason`] = ma.reason;
      if (ma.detail !== "") out[`${PREFIX}.model_absent.${ma.kind}.detail`] = ma.detail;
    }
  }
  for (const p of record.parts) {
    const base = `${PREFIX}.part.${p.kind}`;
    out[`${base}.sourcing`] = p.sourcing;
    if (p.contentDigest !== "") {
      out[`${base}.digest`] = p.contentDigest;
      out[`${base}.boundary`] = p.boundary;
    }
    if (p.label !== "") out[`${base}.label`] = p.label;
    if (p.readLagSeconds !== null) out[`${base}.read_lag_seconds`] = p.readLagSeconds;
  }
  for (const a of record.absences) {
    out[`${PREFIX}.absent.${a.kind}.reason`] = a.reason;
    if (a.detail !== "") out[`${PREFIX}.absent.${a.kind}.detail`] = a.detail;
  }
  return out;
}

// A manifest read off the wire (section 6): empty entries dropped, and a repeated name counted once. The list is a set,
// and refusing a record for a repeated name would turn a cosmetic fault into a lost record.
function names(field: string): string[] {
  return [...new Set(field.split(",").filter((r) => r !== ""))];
}

const HEX64 = /^[0-9a-f]{64}$/;
const HEX24 = /^[0-9a-f]{24}$/;
const UNLISTED_NAME = new RegExp(UNLISTED_NAME_PATTERN);
const REQUIRED = ["spec_version", "collector", "collector_version", "collector_reaches", "status"];
const TOP_STRINGS = ["collector", "collector_version", "collector_reaches", "status", "model_reaches",
  "harness_identity", "model_identity", "artifact_identity"];
const PART_FIELDS: { [group: string]: string[] } = {
  part: ["sourcing", "digest", "boundary", "label", "read_lag_seconds"],
  model: ["sourcing", "digest", "label", "read_lag_seconds"],
  absent: ["reason", "detail"],
  model_absent: ["reason", "detail"],
};

// The shape rules of section 6 that no record object enforces on its own: required keys, value types, attributes of a
// part that carry no sourcing or reason, a boundary without a digest, and the length of digests and identities. Keys
// under `perigraph.ext.` are skipped (section 13.2), and keys outside the prefix belong to the carrier.
function checkShape(attrs: Attributes): void {
  for (const k of REQUIRED) if (!(`${PREFIX}.${k}` in attrs)) throw new Unidentified(`${PREFIX}.${k} is missing`);
  for (const k of TOP_STRINGS) {
    const key = `${PREFIX}.${k}`;
    if (key in attrs && typeof attrs[key] !== "string") throw new Unidentified(`${key} is not a string`);
  }
  const unlisted = `${PREFIX}.request.unlisted`;
  const unnamed = `${PREFIX}.request.unlisted_omitted`;
  if (unlisted in attrs !== unnamed in attrs) throw new Unidentified(`one of ${unlisted} and ${unnamed} is present without the other`);
  if (unlisted in attrs) {
    if (typeof attrs[unlisted] !== "string") throw new Unidentified(`${unlisted} is not a string`);
    const n = attrs[unnamed];
    if (typeof n !== "number" || !Number.isInteger(n) || n < 0) throw new Unidentified(`${unnamed} is not a non-negative integer`);
    const listed = names(attrs[unlisted] as string);
    if (listed.length > UNLISTED_NAMES_MAX) throw new Unidentified(`${unlisted} names more than ${UNLISTED_NAMES_MAX} members`);
    for (const name of listed) {
      if (!UNLISTED_NAME.test(name)) throw new Unidentified(`${unlisted} has an entry outside the binding's name pattern`);
      if (Object.hasOwn(OPENAI_MEMBERS, name)) throw new Unidentified(`${unlisted} names ${name}, which the binding reads`);
    }
  }
  for (const k of ["harness_identity", "model_identity", "artifact_identity"]) {
    const v = attrs[`${PREFIX}.${k}`];
    if (v !== undefined && !HEX24.test(String(v))) throw new Unidentified(`${PREFIX}.${k} is not 24 lowercase hex characters`);
  }
  for (const [key, value] of Object.entries(attrs)) {
    if (!key.startsWith(`${PREFIX}.`) || key.startsWith(`${PREFIX}.ext.`)) continue;
    const bits = key.split(".");
    if (bits.length !== 4) continue;
    const group = bits[1] as string;
    const name = bits[2] as string;
    const field = bits[3] as string;
    const fields = PART_FIELDS[group];
    if (fields === undefined || !fields.includes(field)) continue;
    const anchor = group === "part" || group === "model" ? "sourcing" : "reason";
    if (!(`${PREFIX}.${group}.${name}.${anchor}` in attrs)) {
      throw new Unidentified(`${key} is present and ${PREFIX}.${group}.${name}.${anchor} is not`);
    }
    if (field === "read_lag_seconds") {
      if (typeof value !== "number") throw new Unidentified(`${key} is not a number`);
    } else if (typeof value !== "string") {
      throw new Unidentified(`${key} is not a string`);
    }
    if (field === "digest" && !HEX64.test(value as string)) throw new Unidentified(`${key} is not 64 lowercase hex characters`);
    if (group === "part" && field === "boundary" && !(`${PREFIX}.part.${name}.digest` in attrs)) {
      throw new Unidentified(`${key} is present without a digest`);
    }
  }
}

export function fromAttributes(attrs: Attributes): Record_ {
  const unlisted = `${PREFIX}.request.unlisted`;
  const got = attrs[`${PREFIX}.spec_version`];
  if (got !== SPEC_VERSION) {
    throw new Unidentified(
      `these attributes declare spec_version ${got} and this reader implements ${SPEC_VERSION}. Parsing it anyway ` +
        `would drop the fields this version does not know, and a dropped absence is a hole the sender declared and the ` +
        `reader cannot see`,
    );
  }
  checkShape(attrs);
  const parts: Part[] = [];
  const absences: Absence[] = [];
  const mparts: ModelPart[] = [];
  const mabsences: ModelAbsence[] = [];
  for (const [key, value] of Object.entries(attrs)) {
    if (key.startsWith(`${PREFIX}.model.`) && key.endsWith(".sourcing")) {
      const kind = key.slice(`${PREFIX}.model.`.length, -".sourcing".length);
      const base = `${PREFIX}.model.${kind}`;
      const lag = attrs[`${base}.read_lag_seconds`];
      mparts.push(
        new ModelPart({
          kind,
          sourcing: String(value),
          contentDigest: String(attrs[`${base}.digest`] ?? ""),
          label: String(attrs[`${base}.label`] ?? ""),
          readLagSeconds: lag === undefined ? null : Number(lag),
        }),
      );
      continue;
    }
    if (key.startsWith(`${PREFIX}.model_absent.`) && key.endsWith(".reason")) {
      const kind = key.slice(`${PREFIX}.model_absent.`.length, -".reason".length);
      mabsences.push(new ModelAbsence(kind, String(value), String(attrs[`${PREFIX}.model_absent.${kind}.detail`] ?? "")));
      continue;
    }
    if (key.startsWith(`${PREFIX}.part.`) && key.endsWith(".sourcing")) {
      const kind = key.slice(`${PREFIX}.part.`.length, -".sourcing".length);
      const base = `${PREFIX}.part.${kind}`;
      const lag = attrs[`${base}.read_lag_seconds`];
      parts.push(
        new Part({
          kind,
          sourcing: String(value),
          label: String(attrs[`${base}.label`] ?? ""),
          contentDigest: String(attrs[`${base}.digest`] ?? ""),
          boundary: String(attrs[`${base}.boundary`] ?? "model_visible"),
          readLagSeconds: lag === undefined ? null : Number(lag),
        }),
      );
    } else if (key.startsWith(`${PREFIX}.absent.`) && key.endsWith(".reason")) {
      const kind = key.slice(`${PREFIX}.absent.`.length, -".reason".length);
      absences.push(new Absence(kind, String(value), String(attrs[`${PREFIX}.absent.${kind}.detail`] ?? "")));
    }
  }
  // See AMBIGUITY 5: splitting "" on "," yields [""], which is a part named empty-string.
  const reaches = names(String(attrs[`${PREFIX}.collector_reaches`] ?? ""));
  let model: Model | null = null;
  if (`${PREFIX}.model_reaches` in attrs || mparts.length > 0 || mabsences.length > 0) {
    const mreach = names(String(attrs[`${PREFIX}.model_reaches`] ?? ""));
    model = new Model(mparts, mabsences, mreach);
  }
  const record = new Record_(
    new Manifest(String(attrs[`${PREFIX}.collector`]), String(attrs[`${PREFIX}.collector_version`]), reaches),
    String(attrs[`${PREFIX}.status`]),
    parts,
    absences,
    model,
    unlisted in attrs ? names(String(attrs[unlisted])) : null,
    unlisted in attrs ? Number(attrs[`${PREFIX}.request.unlisted_omitted`]) : 0,
  );
  const checks: [string, boolean, () => string][] = [
    [`${PREFIX}.harness_identity`, record.hasIdentity, () => record.identity],
    [`${PREFIX}.model_identity`, model !== null && model.hasModelIdentity, () => model!.modelIdentity],
    [`${PREFIX}.artifact_identity`, model !== null && model.hasArtifactIdentity, () => model!.artifactIdentity],
  ];
  for (const [key, have, get] of checks) {
    if (key in attrs && (!have || attrs[key] !== get())) {
      throw new Unidentified(`${key}=${attrs[key]} does not follow from the parts this record carries`);
    }
  }
  return record;
}
