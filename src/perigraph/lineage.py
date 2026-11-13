"""Lineage: how a tuned model came to be, as a document its trainer writes about one artifact (spec section 10).

Outside any record, because whoever serves the model holds its bytes and not its history; never identifying, because
two trainings that produced the same bytes are the same model; and subtract-only, because nobody downstream can check
it. What it is for is the refusal it can trigger: a model trained on the items it is now being judged on.

The receiver rules this module implements:

* a lineage whose `subject` is not the artifact observed is read as **absent** -- R5's history beside R6's bytes would
  otherwise describe a model that is not there;
* an absent lineage, a missing ancestor, or a cited set nobody can open is **unknown, never clean**;
* a claim may trigger a refusal and may never lift one: there is no `excluded` role, because it could only ever lift.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from perigraph.vocab import LINEAGE_FIELDS, LINEAGE_METHODS, LINEAGE_SET_ROLES, LINEAGE_SIGNAL_FORMS, SPEC_VERSION, \
    Unidentified

_IDENTITY = re.compile(r"[0-9a-f]{24}")
_DIGEST = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class SetRef:
    role: str
    digest: str


@dataclass(frozen=True)
class Lineage:
    subject: str
    parent: str
    method: str
    sets: tuple[SetRef, ...] = ()
    signal: tuple[str, str] | None = None
    trainer: str = ""

    def __post_init__(self) -> None:
        if not _IDENTITY.fullmatch(self.subject):
            raise Unidentified(f"lineage subject {self.subject!r} is not an artifact identity")
        if self.parent != "none" and not _IDENTITY.fullmatch(self.parent):
            raise Unidentified(f"lineage parent {self.parent!r} is neither an artifact identity nor 'none'")
        if self.parent == self.subject:
            raise Unidentified("a lineage cannot name its own subject as its parent")
        if self.method not in LINEAGE_METHODS:
            raise Unidentified(f"lineage method {self.method!r} is not one of {LINEAGE_METHODS}")
        if (self.method == "pretrained") != (self.parent == "none"):
            raise Unidentified("a pretrained artifact has no parent, and only a pretrained one has none")
        for s in self.sets:
            if s.role not in LINEAGE_SET_ROLES:
                raise Unidentified(f"set role {s.role!r} is not one of {LINEAGE_SET_ROLES}")
            if not _DIGEST.fullmatch(s.digest):
                raise Unidentified(f"set digest {s.digest!r} is not lowercase hex sha256 of a manifest file")
        if self.signal is not None:
            form, value = self.signal
            if form not in LINEAGE_SIGNAL_FORMS:
                raise Unidentified(f"signal form {form!r} is not one of {LINEAGE_SIGNAL_FORMS}")
            if form == "artifact_identity" and not _IDENTITY.fullmatch(value):
                raise Unidentified(f"signal {value!r} is not an artifact identity")
            if form == "digest" and not _DIGEST.fullmatch(value):
                raise Unidentified(f"signal {value!r} is not a sha256 digest")
            if form == "label" and not value:
                raise Unidentified("a label signal with no text says nothing")
        elif self.method in ("distillation", "rl"):
            raise Unidentified(f"a {self.method} lineage names what its signal came from, even if only as a label")


def load(doc: Mapping[str, object]) -> Lineage:
    """Read a lineage document, refusing a version or a field this reader does not implement."""
    if doc.get("spec_version") != SPEC_VERSION:
        raise Unidentified(f"lineage spec_version {doc.get('spec_version')!r}; this reader implements {SPEC_VERSION}")
    unknown = sorted(set(doc) - set(LINEAGE_FIELDS))
    if unknown:
        raise Unidentified(f"lineage carries {unknown}, which are not lineage fields; a field a reader drops is a claim "
                           f"it silently ignored")
    raw_sets = doc.get("sets") or []
    if not isinstance(raw_sets, list) or not all(isinstance(s, Mapping) for s in raw_sets):
        raise Unidentified("sets is a list of {role, digest} objects")
    sets = tuple(SetRef(str(s["role"]), str(s["digest"])) for s in raw_sets)
    sig = doc.get("signal")
    signal = None
    if sig is not None:
        if not isinstance(sig, Mapping) or len(sig) != 1:
            raise Unidentified("signal is one {form: value} pair")
        (form, value), = sig.items()
        signal = (str(form), str(value))
    return Lineage(subject=str(doc.get("subject", "")), parent=str(doc.get("parent", "")),
                   method=str(doc.get("method", "")), sets=sets, signal=signal, trainer=str(doc.get("trainer", "")))


def about(lineage: Lineage | None, observed_artifact: str | None) -> Lineage | None:
    """The lineage as it applies to what was observed: None (unknown) unless its subject is that artifact."""
    if lineage is None or observed_artifact is None or lineage.subject != observed_artifact:
        return None
    return lineage


def chain(subject: str, documents: Mapping[str, Lineage]) -> tuple[tuple[Lineage, ...], bool]:
    """Walk from `subject` to a pretrained root. Returns the documents found and whether the chain is complete.

    An incomplete chain is not an error -- it is the answer "unknown", which a receiver must not read as clean."""
    out: list[Lineage] = []
    seen: set[str] = set()
    at = subject
    while True:
        doc = documents.get(at)
        if doc is None or doc.subject != at:
            return tuple(out), False
        if at in seen:
            raise Unidentified(f"lineage chain loops at {at}")
        seen.add(at)
        out.append(doc)
        if doc.parent == "none":
            return tuple(out), True
        at = doc.parent


def trained_on_anywhere(subject: str, documents: Mapping[str, Lineage], set_digest: str) -> bool | None:
    """True when the chain says the set was trained on or consulted, None when the chain is incomplete and says nothing,
    False only when the whole chain is present and never names it. Only True can be acted on as a refusal."""
    docs, complete = chain(subject, documents)
    if any(s.digest == set_digest for d in docs for s in d.sets):
        return True
    return False if complete else None
