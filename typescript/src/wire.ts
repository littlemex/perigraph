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
import { NAMESPACE, SPEC_VERSION, Unidentified } from "./vocab.js";

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

export function fromAttributes(attrs: Attributes): Record_ {
  const got = attrs[`${PREFIX}.spec_version`];
  if (got !== SPEC_VERSION) {
    throw new Unidentified(
      `these attributes declare spec_version ${got} and this reader implements ${SPEC_VERSION}. Parsing it anyway ` +
        `would drop the fields this version does not know, and a dropped absence is a hole the sender declared and the ` +
        `reader cannot see`,
    );
  }
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
