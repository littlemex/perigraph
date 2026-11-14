"""The wire form: a record flattened into prefixed scalar attributes, and read back.

Flat and scalar because it has to ride on a span any tracer already emits, and because the receiver that matters most is
one nobody wrote yet. A nested structure would need a serialiser on both sides and would put the shape of the record into
the transport, where a change to it becomes a compatibility break.

**Keys are indexed by part name, never by position.** An integer index reorders when a collector learns to read one more
part, and every historical record then means something different. A part name does not move.
"""
from __future__ import annotations

import re

from perigraph.model import Model, ModelAbsence, ModelPart
from perigraph.record import Absence, Manifest, Part, Record
from perigraph.vocab import NAMESPACE, SPEC_VERSION, Unidentified

PREFIX = NAMESPACE


def to_attributes(record: Record) -> dict[str, str | int | float]:
    """Flatten a record for carriage. Absent-by-omission is deliberate: a key with an empty value would be a claim.

    `perigraph.harness_identity` is omitted rather than empty when the record has none. An empty identity string is a value that
    compares equal to another empty identity string, which would group every unidentifiable run together -- the exact
    failure the identity rules exist to prevent, reintroduced by the transport.
    """
    out: dict[str, str | int | float] = {
        f"{PREFIX}.spec_version": SPEC_VERSION,
        f"{PREFIX}.collector": record.manifest.collector,
        f"{PREFIX}.collector_version": record.manifest.version,
        f"{PREFIX}.collector_reaches": ",".join(record.manifest.reaches),
        f"{PREFIX}.status": record.status,
    }
    if record.has_identity:
        out[f"{PREFIX}.harness_identity"] = record.identity
    m = record.model
    if m is not None:
        out[f"{PREFIX}.model_reaches"] = ",".join(m.reaches)
        if m.has_model_identity:
            out[f"{PREFIX}.model_identity"] = m.model_identity
        if m.has_artifact_identity:
            out[f"{PREFIX}.artifact_identity"] = m.artifact_identity
        for mp in m.parts:
            base = f"{PREFIX}.model.{mp.kind}"
            out[f"{base}.sourcing"] = mp.sourcing
            if mp.content_digest:
                out[f"{base}.digest"] = mp.content_digest
            if mp.label:
                out[f"{base}.label"] = mp.label
            if mp.read_lag_seconds is not None:
                out[f"{base}.read_lag_seconds"] = mp.read_lag_seconds
        for ma in m.absences:
            out[f"{PREFIX}.model_absent.{ma.kind}.reason"] = ma.reason
            if ma.detail:
                out[f"{PREFIX}.model_absent.{ma.kind}.detail"] = ma.detail
    for p in record.parts:
        base = f"{PREFIX}.part.{p.kind}"
        out[f"{base}.sourcing"] = p.sourcing
        if p.content_digest:
            out[f"{base}.digest"] = p.content_digest
            out[f"{base}.boundary"] = p.boundary
        if p.label:
            out[f"{base}.label"] = p.label
        if p.read_lag_seconds is not None:
            out[f"{base}.read_lag_seconds"] = p.read_lag_seconds
    for a in record.absences:
        out[f"{PREFIX}.absent.{a.kind}.reason"] = a.reason
        if a.detail:
            out[f"{PREFIX}.absent.{a.kind}.detail"] = a.detail
    return out


def _names(field: str) -> tuple[str, ...]:
    """A manifest read off the wire (section 6): empty entries dropped, and a repeated name counted once.

    The list is a set. A collector SHOULD NOT repeat a name, and a receiver that refused a record for doing so would turn
    a cosmetic fault into a lost record -- which section 1.1 forbids a receiver to cause.
    """
    return tuple(dict.fromkeys(r for r in field.split(",") if r))


_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX24 = re.compile(r"[0-9a-f]{24}")
_REQUIRED = ("spec_version", "collector", "collector_version", "collector_reaches", "status")
_TOP_STRINGS = ("collector", "collector_version", "collector_reaches", "status", "model_reaches",
                "harness_identity", "model_identity", "artifact_identity")
_PART_FIELDS = {"part": ("sourcing", "digest", "boundary", "label", "read_lag_seconds"),
                "model": ("sourcing", "digest", "label", "read_lag_seconds"),
                "absent": ("reason", "detail"), "model_absent": ("reason", "detail")}


def _check_shape(attrs: dict) -> None:
    """The shape rules of section 6 that no record object enforces on its own: required keys, value types, attributes
    of a part that carry no sourcing or reason, a boundary without a digest, and the length of digests and identities.
    Keys under `perigraph.ext.` are skipped (section 13.2), and keys outside the prefix belong to the carrier."""
    for k in _REQUIRED:
        if f"{PREFIX}.{k}" not in attrs:
            raise Unidentified(f"{PREFIX}.{k} is missing")
    for k in _TOP_STRINGS:
        if f"{PREFIX}.{k}" in attrs and not isinstance(attrs[f"{PREFIX}.{k}"], str):
            raise Unidentified(f"{PREFIX}.{k} is not a string")
    for k in ("harness_identity", "model_identity", "artifact_identity"):
        v = attrs.get(f"{PREFIX}.{k}")
        if v is not None and not _HEX24.fullmatch(v):
            raise Unidentified(f"{PREFIX}.{k}={v!r} is not 24 lowercase hex characters")
    for key, value in attrs.items():
        if not key.startswith(f"{PREFIX}.") or key.startswith(f"{PREFIX}.ext."):
            continue
        bits = key.split(".")
        if len(bits) != 4 or bits[1] not in _PART_FIELDS:
            continue
        group, name, field = bits[1], bits[2], bits[3]
        if field not in _PART_FIELDS[group]:
            continue
        anchor = "sourcing" if group in ("part", "model") else "reason"
        if f"{PREFIX}.{group}.{name}.{anchor}" not in attrs:
            raise Unidentified(f"{key} is present and {PREFIX}.{group}.{name}.{anchor} is not")
        if field == "read_lag_seconds":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise Unidentified(f"{key} is not a number")
        elif not isinstance(value, str):
            raise Unidentified(f"{key} is not a string")
        if field == "digest" and not _HEX64.fullmatch(value):
            raise Unidentified(f"{key} is not 64 lowercase hex characters")
        if group == "part" and field == "boundary" and f"{PREFIX}.part.{name}.digest" not in attrs:
            raise Unidentified(f"{key} is present without a digest")


def from_attributes(attrs: dict) -> Record:
    """Rebuild a record from attributes, refusing a version this reader does not implement.

    Refused rather than best-effort parsed. A reader that guesses at an unknown version will read the fields it
    recognises and silently drop the rest, and dropping a field here means dropping an absence -- which turns a hole the
    sender was honest about into a hole nobody knows exists.
    """
    got = attrs.get(f"{PREFIX}.spec_version")
    if got != SPEC_VERSION:
        raise Unidentified(
            f"these attributes declare spec_version {got!r} and this reader implements {SPEC_VERSION}. Parsing it "
            f"anyway would drop the fields this version does not know, and a dropped absence is a hole the sender "
            f"declared and the reader cannot see")
    _check_shape(attrs)
    parts: list[Part] = []
    absences: list[Absence] = []
    mparts: list[ModelPart] = []
    mabsences: list[ModelAbsence] = []
    for key, value in attrs.items():
        if key.startswith(f"{PREFIX}.model.") and key.endswith(".sourcing"):
            kind = key[len(f"{PREFIX}.model."):-len(".sourcing")]
            base = f"{PREFIX}.model.{kind}"
            lag = attrs.get(f"{base}.read_lag_seconds")
            mparts.append(ModelPart(kind=kind, sourcing=str(value), content_digest=str(attrs.get(f"{base}.digest", "")),
                                    label=str(attrs.get(f"{base}.label", "")),
                                    read_lag_seconds=None if lag is None else float(lag)))
            continue
        if key.startswith(f"{PREFIX}.model_absent.") and key.endswith(".reason"):
            kind = key[len(f"{PREFIX}.model_absent."):-len(".reason")]
            mabsences.append(ModelAbsence(kind=kind, reason=str(value),
                                          detail=str(attrs.get(f"{PREFIX}.model_absent.{kind}.detail", ""))))
            continue
        if key.startswith(f"{PREFIX}.part.") and key.endswith(".sourcing"):
            kind = key[len(f"{PREFIX}.part."):-len(".sourcing")]
            base = f"{PREFIX}.part.{kind}"
            lag = attrs.get(f"{base}.read_lag_seconds")
            parts.append(Part(kind=kind, sourcing=str(value),
                              label=str(attrs.get(f"{base}.label", "")),
                              content_digest=str(attrs.get(f"{base}.digest", "")),
                              boundary=str(attrs.get(f"{base}.boundary", "model_visible" if f"{base}.digest" in attrs
                                                     else "parsed")),
                              read_lag_seconds=None if lag is None else float(lag)))
        elif key.startswith(f"{PREFIX}.absent.") and key.endswith(".reason"):
            kind = key[len(f"{PREFIX}.absent."):-len(".reason")]
            absences.append(Absence(kind=kind, reason=str(value),
                                    detail=str(attrs.get(f"{PREFIX}.absent.{kind}.detail", ""))))
    reaches = str(attrs.get(f"{PREFIX}.collector_reaches", ""))
    model = None
    if f"{PREFIX}.model_reaches" in attrs or mparts or mabsences:
        mreach = str(attrs.get(f"{PREFIX}.model_reaches", ""))
        model = Model(parts=tuple(mparts), absences=tuple(mabsences), reaches=_names(mreach))
    record = Record(manifest=Manifest(collector=str(attrs[f"{PREFIX}.collector"]),
                                      version=str(attrs[f"{PREFIX}.collector_version"]),
                                      reaches=_names(reaches)),
                    status=str(attrs[f"{PREFIX}.status"]),
                    parts=tuple(parts), absences=tuple(absences), model=model)
    # The identities on the wire are derived values. One that disagrees with the parts it claims to be over is a sender
    # that hashed something else, and reading it as given would key a comparison on bytes nobody can name.
    derived = {f"{PREFIX}.harness_identity": record.identity if record.has_identity else None,
               f"{PREFIX}.model_identity": model.model_identity if model and model.has_model_identity else None,
               f"{PREFIX}.artifact_identity": model.artifact_identity if model and model.has_artifact_identity else None}
    for key, want in derived.items():
        if key in attrs and attrs[key] != want:
            raise Unidentified(f"{key}={attrs[key]!r} does not follow from the parts this record carries")
    return record
