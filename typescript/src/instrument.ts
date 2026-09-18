/**
 * The injection: wrap what a sender already calls, and the record happens on the way past.
 *
 * The rule this file exists to hold: **it never breaks the call it describes.** A shim that can is a shim nobody leaves
 * installed, and then there is no record at all. A body it cannot find, a collector that threw, a sink that threw, a
 * tracer that rejects one attribute -- each degrades the record and lets the call through, and the degradation is
 * recorded as `collector_failed` so it cannot pass as the sender's silence.
 */
import { FROM_A_REQUEST, fromRequest, type Body } from "./collect.js";
import { Manifest, Record_ } from "./record.js";
import { toAttributes, type Attributes } from "./wire.js";

export const DEFAULT_COLLECTOR = "perigraph-typescript";
export const DEFAULT_VERSION = "0.1.0";

/** A span-ish thing. Structural rather than imported, so this package needs no tracer to compile. */
export interface SpanLike {
  setAttribute(key: string, value: string | number): unknown;
}

function failedRecord(collector: string, version: string): Record_ {
  return new Record_(new Manifest(collector, version, [...FROM_A_REQUEST]), "collector_failed");
}

export function observe(body: unknown, opts: { collector?: string; version?: string } = {}): Record_ {
  const collector = opts.collector ?? DEFAULT_COLLECTOR;
  const version = opts.version ?? DEFAULT_VERSION;
  try {
    if (typeof body !== "object" || body === null) throw new Error("not a body");
    return fromRequest(body as Body, { collector, version });
  } catch {
    return failedRecord(collector, version);
  }
}

export function emit(record: Record_, span?: SpanLike): Attributes {
  const attrs = toAttributes(record);
  if (span !== undefined) {
    for (const [key, value] of Object.entries(attrs)) {
      try {
        span.setAttribute(key, value);
      } catch {
        // One rejected attribute must not cost the rest of the record: a tracer with a key-length limit or a type
        // restriction is a normal thing to meet, and losing the whole record to it would be the shim breaking the
        // observability it was added to improve.
        continue;
      }
    }
  }
  return attrs;
}

export function wrap<A extends unknown[], R>(
  fn: (...args: A) => R,
  opts: { collector?: string; version?: string; onRecord?: (record: Record_) => void } = {},
): (...args: A) => R {
  const sink = opts.onRecord ?? ((r: Record_) => void emit(r));
  return (...args: A): R => {
    const body = args.find((a) => typeof a === "object" && a !== null && !Array.isArray(a));
    const record =
      body === undefined
        ? failedRecord(opts.collector ?? DEFAULT_COLLECTOR, opts.version ?? DEFAULT_VERSION)
        : observe(body, opts);
    try {
      sink(record);
    } catch {
      // The sink is the sender's code. Letting it break the call would make the shim the reason a request failed.
    }
    return fn(...args);
  };
}
