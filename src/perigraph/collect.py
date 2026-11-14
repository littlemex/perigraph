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

from perigraph.model import Model, ModelAbsence
from perigraph.record import Absence, Manifest, Part, Record, blank, digest
from perigraph.vocab import MODEL_PARTS, PARTS

#: What this collector claims it can reach from a request body, and nothing more. **Static per version on purpose:** a
#: manifest that adapted to what it happened to find could never contradict a record, which is the one thing it is for.
FROM_A_REQUEST = ("instruction", "request_template", "tool_schemas", "readout", "decoding")

#: Which boundary each of those digests is actually over. This table is the finding; see the module docstring.
REQUEST_BOUNDARIES = {
    "instruction": "model_visible",
    "request_template": "model_visible",
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

    if not isinstance(body, dict):
        # Section 1.2: a body we cannot parse is an absence we name, never a record we withhold.
        found = _json_type(body)
        absences = [Absence(kind=k, reason="extraction_failed", detail=f"the body is {found}, not an object")
                    for k in FROM_A_REQUEST]
        absences += [Absence(kind=k, reason="not_provided") for k in PUSHED_PARTS]
        absences += [Absence(kind="tool_extension", reason="not_observable"),
                     Absence(kind="tool_trace", reason="not_provided")]
        return _record(collector, version, (), absences)

    instruction, failed = _instruction(body.get("messages"))
    if failed:
        absences.append(Absence(kind="instruction", reason="extraction_failed", detail=failed))
    elif not blank(instruction):
        # Hashed RAW, down to case and whitespace. The model reads the string and not its meaning, and 0.6243 against
        # 0.7447 came from one sentence's wording -- so two spellings are two harnesses even where a human would call
        # them the same instruction.
        hold("instruction", instruction)
    else:
        absences.append(Absence(kind="instruction", reason="not_provided"))

    template, failed = _template(body.get(TEMPLATE_FIELD), body.get("messages"))
    if failed:
        absences.append(Absence(kind="request_template", reason="extraction_failed", detail=failed))
    elif template is not None:
        hold("request_template", template)
    else:
        absences.append(Absence(kind="request_template", reason="not_provided"))

    tools = body.get("tools")
    bad_tool = (f"tools is {_json_type(tools)}, not an array" if tools is not None and not isinstance(tools, list) else
                next((f"tools[{i}] is {_json_type(t)}, not an object" for i, t in enumerate(tools or [])
                      if not isinstance(t, dict) or not isinstance(t.get("function", {}), dict)), ""))
    if bad_tool:
        absences.append(Absence(kind="tool_schemas", reason="extraction_failed", detail=bad_tool))
    elif tools:
        # Sorted by rendered shape: the order a caller lists tools in is not part of what it offered, and an unsorted
        # digest would make two identical toolsets look like two harnesses.
        shapes = sorted(_scalars([("name", (t.get("function") or t).get("name")),
                                 ("params", (t.get("function") or t).get("parameters"))]) for t in tools)
        hold("tool_schemas", "|".join(shapes), label=f"{len(tools)} tool(s)")
    else:
        absences.append(Absence(kind="tool_schemas", reason="not_provided"))

    fmt = body.get("response_format")
    bad_fmt = f"response_format is {_json_type(fmt)}, not an object" if fmt is not None and not isinstance(fmt, dict) \
        else ""
    if bad_fmt:
        absences.append(Absence(kind="readout", reason="extraction_failed", detail=bad_fmt))
    elif fmt:
        hold("readout", _scalars([("response_format", fmt)]),
             label=str(fmt.get("type", "")) if isinstance(fmt, dict) else "")
    else:
        # Not our failure. Without a declared format the answer is read out of prose by a convention on the caller's
        # side, and a mis-set convention has been measured to put 1,822 of 2,364 answers on one option.
        absences.append(Absence(kind="readout", reason="not_provided"))

    # A response_format constrains the grammar of the output, so it is decoding as well as readout (section 1).
    knobs = [(k, body[k]) for k in DECODING_KEYS if body.get(k) is not None] + ([("response_format", fmt)] if fmt else [])
    if bad_fmt:
        absences.append(Absence(kind="decoding", reason="extraction_failed", detail=bad_fmt))
    elif knobs:
        hold("decoding", _scalars(knobs), label=",".join(k for k, _ in knobs))
    else:
        absences.append(Absence(kind="decoding", reason="not_provided"))

    for kind in PUSHED_PARTS:
        absences.append(Absence(kind=kind, reason="not_provided"))
    absences.append(Absence(kind="tool_extension", reason="not_observable"))
    # At request time the calls have not happened, so there is nothing the sender could have supplied.
    absences.append(Absence(kind="tool_trace", reason="not_provided"))

    return _record(collector, version, parts, absences)


def _record(collector: str, version: str, parts, absences) -> Record:
    """A request collector did not load the model, so it says so for each model part (section 6) rather than leaving
    the model half out, which would be a hole nobody named."""
    record = Record(manifest=Manifest(collector=collector, version=version, reaches=FROM_A_REQUEST),
                    status="complete", parts=tuple(parts), absences=tuple(absences),
                    model=Model(absences=tuple(ModelAbsence(kind=k, reason="not_observable") for k in MODEL_PARTS)))
    assert not record.unaccounted, f"the collector left {record.unaccounted} unaccounted for"
    return record


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "an array"
    if isinstance(value, dict):
        return "an object"
    return type(value).__name__


def _instruction(messages: object) -> tuple[str, str]:
    """The system text, newline-joined (section 2.2), or the reason it cannot be read.

    A system message whose content is not a string fails the whole part: the text a model reads from an array of parts
    is the chat template's to decide, and the request does not carry the template. The detail names the message and the
    type found and never quotes the content."""
    if messages is None:
        return "", ""
    if not isinstance(messages, list):
        return "", f"messages is {_json_type(messages)}, not an array"
    texts = []
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            return "", f"messages[{i}] is {_json_type(m)}, not an object"
        # A message whose role cannot be read might have been a system message.
        if "role" not in m:
            return "", f"messages[{i}].role is missing, not a string"
        if not isinstance(m["role"], str):
            return "", f"messages[{i}].role is {_json_type(m['role'])}, not a string"
    for i, m in enumerate(messages):
        if m.get("role") != "system":
            continue
        if "content" not in m:
            return "", f"messages[{i}].content is missing, not a string"
        if not isinstance(m["content"], str):
            return "", f"messages[{i}].content is {_json_type(m['content'])}, not a string"
        texts.append(m["content"])
    return "\n".join(texts), ""


#: The top-level member of a request body that carries the request template (binding: openai-chat-completions).
TEMPLATE_FIELD = "perigraph_template"


def _template(template: object, messages: object) -> tuple[str | None, str]:
    """The `request_template` payload, None when the request declares none, or the reason it cannot be read.

    The template names the fixed text of each templated message as the strings around the holes the item went in, and
    is verified against the request: each such message's content must be its strings with something, possibly nothing,
    in each hole. Only the fixed strings are digested, so the item never reaches the digest. A template that fixes no
    text other than white space is treated as not sent (SPEC 1.2), and that test comes after every check."""
    if template is None:
        return None, ""
    where = TEMPLATE_FIELD
    if not isinstance(template, dict):
        return None, f"{where} is {_json_type(template)}, not an object"
    if set(template) != {"messages"}:
        return None, f"{where} has members other than messages, or lacks messages"
    entries = template["messages"]
    if not isinstance(entries, list):
        return None, f"{where}.messages is {_json_type(entries)}, not an array"
    if not isinstance(messages, list):
        return None, f"messages is {'missing' if messages is None else _json_type(messages)}, not an array"
    if len(entries) != len(messages):
        return None, f"{where}.messages has {len(entries)} entries and messages has {len(messages)}"
    payload = [f"{len(entries)}:".encode()]
    names_text = False
    for i, (e, m) in enumerate(zip(entries, messages)):
        at = f"{where}.messages[{i}]"
        if not isinstance(e, dict) or "role" not in e or not set(e) <= {"role", "fixed"}:
            return None, f"{at} is not an object with role and optionally fixed"
        role = e["role"]
        if not isinstance(role, str) or not isinstance(m, dict) or m.get("role") != role:
            return None, f"{at}.role is not a string equal to messages[{i}].role"
        rb = _utf8(role)
        if rb is None:
            return None, f"{at}.role is not a sequence of Unicode scalar values"
        if "fixed" not in e:
            payload.append(f"{len(rb)}:".encode() + rb + b"0:")
            continue
        if role == "system":
            return None, f"{at} is a system entry with fixed strings; its text is the instruction part"
        strings = e["fixed"]
        if not isinstance(strings, list) or not strings or not all(isinstance(g, str) for g in strings):
            return None, f"{at}.fixed is not a non-empty array of strings"
        if any(not g for g in strings[1:-1]):
            return None, f"{at}.fixed has an empty interior string; adjacent holes are one hole"
        content = m.get("content")
        if not isinstance(content, str):
            return None, f"messages[{i}].content is {'missing' if 'content' not in m else _json_type(content)}, not a string"
        segs = [_utf8(g) for g in strings]
        cb = _utf8(content)
        if cb is None or any(b is None for b in segs):
            return None, f"{at} or messages[{i}].content holds a string that is not a sequence of Unicode scalar values"
        if not _fits(cb, segs):
            return None, f"messages[{i}].content does not match {at}.fixed"
        names_text = names_text or any(not blank(g) for g in strings)
        payload.append(f"{len(rb)}:".encode() + rb + f"{len(segs)}:".encode()
                       + b"".join(f"{len(b)}:".encode() + b for b in segs))
    if not names_text:
        return None, ""
    return b"".join(payload).decode("utf-8"), ""


def _utf8(text: str) -> bytes | None:
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        return None


def _fits(content: bytes, segs: list[bytes]) -> bool:
    """Whether content is segs[0] h1 segs[1] ... hn segs[n] for some byte strings h. Leftmost matching of each interior
    string is enough: taking the earliest occurrence leaves the most room for the rest."""
    if len(segs) == 1:
        return content == segs[0]
    if not content.startswith(segs[0]):
        return False
    pos = len(segs[0])
    for seg in segs[1:-1]:
        j = content.find(seg, pos)
        if j < 0:
            return False
        pos = j + len(seg)
    return len(content) - len(segs[-1]) >= pos and content.endswith(segs[-1])


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
