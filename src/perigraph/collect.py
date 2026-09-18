"""Read a request body into a record. Pure, and that is the whole design of it.

No network and no tracer: a shim installed into a sender's process should not be able to fail because something it did
not need moved. It takes the dict a client is about to send.

**What it can and cannot reach, and why that is the finding rather than a limitation.** Only the instruction is text the
model provably read. A `tools` array, a `response_format` and the sampler settings are protocol values: the provider
renders them into the prompt however it likes, or not at all, and the sender does not hold that rendering. So they are
recorded with a `parsed` boundary and cannot key an identity -- which means **a harness read from a request body is
identified by its instruction and nothing else.**

That is the same fact the measurement found from the other side: one sentence of the instruction moved accuracy 12.04
points, and it is also the only part of a request whose exact bytes we can prove the model read.
"""
from __future__ import annotations

from perigraph.record import Absence, Manifest, Part, Record, digest
from perigraph.vocab import PARTS

#: What this collector claims it can reach from a request body, and nothing more. **Static per version on purpose:** a
#: manifest that adapted to what it happened to find could never contradict a record, which is the one thing it is for.
FROM_A_REQUEST = ("instruction", "tool_schemas", "readout", "decoding")

#: Which boundary each of those digests is actually over. This table is the finding; see the module docstring.
REQUEST_BOUNDARIES = {
    "instruction": "model_visible",
    "tool_schemas": "parsed",
    "readout": "parsed",
    "decoding": "parsed",
}

#: Sampler settings read from a body, in a fixed order. Fixed rather than sorted at use, so that adding a knob is a
#: visible edit here instead of a silent change to every digest ever computed.
DECODING_KEYS = ("temperature", "top_p", "top_k", "seed")

#: Parts a request body has no place to put. Their absence is the SENDER's -- the shim did not fail to find them, there
#: is nowhere in a request for them to be -- and saying so is the difference the absence vocabulary exists for.
PUSHED_PARTS = ("loop", "turn_budget", "retry_policy", "context_partitioning")


def _scalars(pairs: list[tuple[str, object]]) -> str:
    """Render protocol scalars for hashing, in the order given.

    Canonicalising **is** allowed here, and the rule that forbids it for the instruction says why: a machine reads these,
    so two spellings of the same setting behave identically. The instruction is the opposite case and is hashed raw.
    """
    return ";".join(f"{k}={v!r}" for k, v in pairs)


def from_request(body: dict, *, collector: str, version: str) -> Record:
    """Read what a request body says about the harness, and record whose absence each hole is."""
    parts: list[Part] = []
    absences: list[Absence] = []

    def hold(kind: str, payload: str, label: str = "") -> None:
        parts.append(Part(kind=kind, sourcing="in_the_request", label=label,
                          content_digest=digest(payload), boundary=REQUEST_BOUNDARIES[kind]))

    messages = body.get("messages") or []
    instruction = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
    if instruction.strip():
        # Hashed RAW, down to case and whitespace. The model reads the string and not its meaning, and 0.6243 against
        # 0.7447 came from one sentence's wording -- so two spellings are two harnesses even where a human would call
        # them the same instruction.
        hold("instruction", instruction)
    else:
        absences.append(Absence(kind="instruction", reason="not_provided"))

    tools = body.get("tools")
    if tools:
        # Sorted by rendered shape: the order a caller lists tools in is not part of what it offered, and an unsorted
        # digest would make two identical toolsets look like two harnesses.
        shapes = sorted(_scalars([("name", (t.get("function") or t).get("name")),
                                 ("params", (t.get("function") or t).get("parameters"))]) for t in tools)
        hold("tool_schemas", "|".join(shapes), label=f"{len(tools)} tool(s)")
    else:
        absences.append(Absence(kind="tool_schemas", reason="not_provided"))

    fmt = body.get("response_format")
    if fmt:
        hold("readout", _scalars([("response_format", fmt)]),
             label=str(fmt.get("type", "")) if isinstance(fmt, dict) else "")
    else:
        # Not our failure. Without a declared format the answer is read out of prose by a convention on the caller's
        # side, and a mis-set convention has been measured to put 1,822 of 2,364 answers on one option.
        absences.append(Absence(kind="readout", reason="not_provided"))

    knobs = [(k, body[k]) for k in DECODING_KEYS if k in body]
    if knobs:
        hold("decoding", _scalars(knobs), label=",".join(k for k, _ in knobs))
    else:
        absences.append(Absence(kind="decoding", reason="not_provided"))

    for kind in PUSHED_PARTS:
        absences.append(Absence(kind=kind, reason="not_provided"))
    absences.append(Absence(kind="tool_extension", reason="not_observable"))
    # At request time the calls have not happened, so there is nothing the sender could have supplied.
    absences.append(Absence(kind="tool_trace", reason="not_provided"))

    record = Record(manifest=Manifest(collector=collector, version=version, reaches=FROM_A_REQUEST),
                    status="complete", parts=tuple(parts), absences=tuple(absences))
    assert not record.unaccounted, f"the collector left {record.unaccounted} unaccounted for"
    return record


def declare(record: Record, **pushed: str) -> Record:
    """Attach what the owner says about the parts a request cannot carry, replacing their `not_provided` absences.

    Separate from `from_request` because the two are different kinds of fact and the record has to keep them apart. What
    a caller declares about its own loop is a claim we cannot check, so it enters as `pushed_by_owner` and can never key
    an identity however true it happens to be.
    """
    unknown = sorted(set(pushed) - set(PUSHED_PARTS))
    if unknown:
        raise ValueError(f"{unknown} are not parts a request body fails to carry; a declaration about something we can "
                         f"read from the request would be a claim standing in front of the evidence")
    kept = tuple(a for a in record.absences if a.kind not in pushed)
    declared = tuple(Part(kind=k, sourcing="pushed_by_owner", label=v, content_digest=digest(v), boundary="parsed")
                     for k, v in sorted(pushed.items()))
    return Record(manifest=record.manifest, status=record.status,
                  parts=record.parts + declared, absences=kept)
