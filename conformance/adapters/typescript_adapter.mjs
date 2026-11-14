// Conformance adapter for the TypeScript implementation (contract: conformance/README.md).
// Needs the built package: run `npm install && npm run build` in typescript/ first.
import { createHash } from "node:crypto";
import { createInterface } from "node:readline";
import { fromRequest } from "../../typescript/dist/src/collect.js";
import { fromAttributes, toAttributes } from "../../typescript/dist/src/wire.js";
import { checkpointDigest, loaded, precisionDigest, runtimeDigest } from "../../typescript/dist/src/model.js";
import { admitArm } from "../../typescript/dist/src/arm.js";
import { NotCanonical, serialise } from "../../typescript/dist/src/canonical.js";

const sha = (t) => createHash("sha256").update(Buffer.from(t, "utf8")).digest("hex");

const ops = {
  describe: () => ({ name: "perigraph (TypeScript)", roles: ["collector", "stamper", "receiver"] }),
  collect: (req) => ({ attributes: toAttributes(fromRequest(req.body, { collector: "conformance", version: "1" })) }),
  stamp: (req) => {
    try {
      const checkpoint = checkpointDigest(Object.entries(req.files).map(([p, t]) => [p, sha(t)]));
      const precision = precisionDigest(req.precision);
      const runtime = runtimeDigest(req.runtime);
      const m = loaded({ checkpoint, precision, runtime, answerMode: req.answer_mode });
      return {
        checkpoint_digest: checkpoint, precision_digest: precision, runtime_digest: runtime,
        model_identity: m.modelIdentity, artifact_identity: m.artifactIdentity,
      };
    } catch (e) {
      return { refused: String(e.message ?? e) };
    }
  },
  canonical: (req) => {
    try {
      return { canonical: serialise(JSON.parse(req.json)) };
    } catch (e) {
      if (e instanceof NotCanonical) return { fails: e.message };
      throw e;
    }
  },
  admit_arm: (req) => {
    let records;
    try {
      records = req.records.map((a) => fromAttributes(a));
    } catch (e) {
      return { outcome: "rejected", why: String(e.message ?? e) };
    }
    const v = admitArm(records);
    return { outcome: v.outcome, why: v.reasons.join("; ") };
  },
  receive: (req) => {
    try {
      const r = fromAttributes(req.attributes);
      return { outcome: "stored", verdict: r.admissibleToAVerdict() ? "admitted" : "refused" };
    } catch (e) {
      return { outcome: "rejected", why: String(e.message ?? e) };
    }
  },
};

for await (const line of createInterface({ input: process.stdin })) {
  const req = JSON.parse(line);
  process.stdout.write(JSON.stringify({ id: req.id, ...ops[req.op](req) }) + "\n");
}
