/**
 * The `canonical_value` serialisation (`digest.canonical_value_serialisation`): RFC 8785, one restriction (the unsafe
 * integer) and one relaxation (a repeated member name takes its last value, as JSON.parse does).
 *
 * `JSON.stringify` on a finite number is already ECMAScript's `Number::toString`, which RFC 8785 adopts, so numbers need
 * only the finite and safe-integer checks. Strings need one more: `JSON.stringify` escapes a lone surrogate as `\udxxx`
 * where the definition fails the part. Member names are sorted with the default sort, which compares UTF-16 code units.
 */
import { createHash } from "node:crypto";

/** The largest integer every reference implementation holds exactly (2**53 - 1). */
export const MAX_SAFE_INTEGER = 9007199254740991;

/** The value cannot be serialised at `canonical_value`. The message names the cause, never the value. */
export class NotCanonical extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NotCanonical";
  }
}

function wellFormed(s: string): boolean {
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const d = s.charCodeAt(i + 1);
      if (!(d >= 0xdc00 && d <= 0xdfff)) return false;
      i++;
    } else if (c >= 0xdc00 && c <= 0xdfff) {
      return false;
    }
  }
  return true;
}

function str(s: string): string {
  if (!wellFormed(s)) throw new NotCanonical("a string that is not a sequence of Unicode scalar values");
  // JSON.stringify escapes exactly ", \ and U+0000-U+001F (with \b \t \n \f \r and lowercase \u00xx) on well-formed text.
  return JSON.stringify(s);
}

function num(v: number): string {
  if (!Number.isFinite(v)) throw new NotCanonical("a number that is not finite");
  if (Number.isInteger(v) && Math.abs(v) > MAX_SAFE_INTEGER) {
    throw new NotCanonical("an integer whose magnitude exceeds 9007199254740991");
  }
  return JSON.stringify(v); // -0 gives "0"
}

/** The canonical text of a decoded JSON value. Throws `NotCanonical` for anything outside the JSON types. */
export function serialise(value: unknown): string {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "number") return num(value);
  if (typeof value === "string") return str(value);
  if (Array.isArray(value)) return "[" + value.map((x) => serialise(x)).join(",") + "]";
  if (typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype) {
    const o = value as Record<string, unknown>;
    const keys = Object.keys(o);
    for (const k of keys) str(k);
    keys.sort();
    return "{" + keys.map((k) => str(k) + ":" + serialise(o[k])).join(",") + "}";
  }
  if (typeof value === "object" && Object.getPrototypeOf(value) === null) {
    return serialise(Object.assign(Object.create(Object.prototype), value));
  }
  throw new NotCanonical(`a value of type ${typeof value}, which is not a JSON type`);
}

/** sha256 of the utf-8 bytes of `serialise(value)`. */
export function canonicalDigest(value: unknown): string {
  return createHash("sha256").update(Buffer.from(serialise(value), "utf8")).digest("hex");
}
