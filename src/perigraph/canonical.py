"""The `canonical_value` serialisation (`digest.canonical_value_serialisation`): RFC 8785, one restriction, one relaxation.

**Why this exists, when section 2.3 once said there was nothing neutral to legislate.** A `parsed` digest could stay
collector-local because it never keyed anything. `generation_controls` keys the harness identity, and a harness
identity compares across collectors, so its payload needs one byte sequence that Python, TypeScript and Go all produce.
RFC 8785 is that sequence, and its number rule is ECMAScript's, which is why the layout below copies `Number::toString`
rather than any Python formatting: `json.dumps` gives `1e-07` and `1.0`, and both are wrong here.

The one restriction beyond RFC 8785 exists because three languages decode differently before any serialiser runs: an
integer above 2**53 - 1 is exact in Python and already rounded in JavaScript and Go, so all three refuse it alike. The
relaxation is that a repeated member name takes its last value, as the reference parsers do; RFC 8785 requires I-JSON.
"""
from __future__ import annotations

import hashlib
import math
from decimal import Decimal

#: The largest integer every reference implementation holds exactly (2**53 - 1).
MAX_SAFE_INTEGER = 9007199254740991


class NotCanonical(ValueError):
    """The value cannot be serialised at `canonical_value`. The message names the cause and never quotes the value."""


def _number(v: float | int) -> str:
    if isinstance(v, int):
        if abs(v) > MAX_SAFE_INTEGER:
            raise NotCanonical("an integer whose magnitude exceeds 9007199254740991")
        return str(v)
    if not math.isfinite(v):
        raise NotCanonical("a number that is not finite")
    if v == int(v):
        if abs(v) > MAX_SAFE_INTEGER:
            raise NotCanonical("an integer whose magnitude exceeds 9007199254740991")
        return str(int(v))  # -0.0 gives "0"
    # Shortest round-trip digits, laid out as ECMAScript Number::toString (RFC 8785 section 3.2.2.3).
    sign, digits, exp = Decimal(repr(v)).as_tuple()
    s = "".join(map(str, digits)).rstrip("0") or "0"
    # repr may carry trailing zeros in the digit tuple; recompute the exponent against the stripped digits.
    exp += len(digits) - len(s)
    k = len(s)
    n = exp + k  # v = 0.s * 10**n
    if k <= n <= 21:
        out = s + "0" * (n - k)
    elif 0 < n <= 21:
        out = s[:n] + "." + s[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * (-n) + s
    else:
        e = n - 1
        mant = s[0] + ("." + s[1:] if k > 1 else "")
        out = mant + "e" + ("+" if e > 0 else "-") + str(abs(e))
    return ("-" if sign else "") + out


_ESC = {0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r", 0x22: '\\"', 0x5C: "\\\\"}


def _string(s: str) -> str:
    out = ['"']
    for ch in s:
        c = ord(ch)
        if 0xD800 <= c <= 0xDFFF:
            raise NotCanonical("a string that is not a sequence of Unicode scalar values")
        if c in _ESC:
            out.append(_ESC[c])
        elif c < 0x20:
            out.append(f"\\u{c:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _utf16(name: str) -> bytes:
    return name.encode("utf-16-be", "surrogatepass")


def serialise(value: object) -> str:
    """The canonical text of a decoded JSON value. Raises `NotCanonical` for anything outside the JSON types, a
    non-finite number, an unsafe integer, or a string or member name that is not well formed."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    # The JSON data model, as a language's JSON serialiser writes it: a tuple is an array, and subclasses of dict, str,
    # int and float are those (SPEC 2.4). bool was tested above, before int.
    if isinstance(value, (int, float)):
        return _number(int(value) if isinstance(value, int) else float(value))
    if isinstance(value, str):
        return _string(str(value))
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(serialise(x) for x in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise NotCanonical("an object member name that is not a string")
        for k in value:
            _string(k)
        return "{" + ",".join(_string(str(k)) + ":" + serialise(value[k]) for k in sorted(value, key=_utf16)) + "}"
    raise NotCanonical(f"a value of type {type(value).__name__}, which is not a JSON type")


def canonical_digest(value: object) -> str:
    """sha256 of the utf-8 bytes of `serialise(value)`."""
    return hashlib.sha256(serialise(value).encode("utf-8")).hexdigest()
