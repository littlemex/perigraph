"""One verdict over records grouped as one arm (SPEC section 4): the rules that read several records at once.

A receiver asks this before publishing one number for an arm. Every rule here only subtracts: an arm whose records all
say nothing about a part is admitted exactly as an arm whose records all say the same thing, so no declaration can
lift a refusal, and a declaration that differs between records can cause one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from perigraph.record import Record
from perigraph.vocab import KNOWN_WHEN_ABSENT_AS, UNIFORM_WITHIN_ARM


@dataclass(frozen=True)
class ArmAdmission:
    """`admitted`, `refused` or `unknown` (SPEC section 0.5), and every reason found, in rule order."""

    outcome: str
    reasons: tuple[str, ...] = ()


def _state(record: Record, kind: str) -> tuple[str, str]:
    """A record's state for one `uniform_within_arm` part: ("held", digest) at canonical_value, ("none", "") when absent
    as not_provided, and ("unknown", "") for anything else, including a part held at another boundary."""
    for p in record.parts:
        if p.kind == kind:
            if p.boundary == "canonical_value" and p.content_digest:
                return "held", p.content_digest
            return "unknown", ""
    for a in record.absences:
        if a.kind == kind:
            return ("none", "") if a.reason == KNOWN_WHEN_ABSENT_AS else ("unknown", "")
    return "unknown", ""


def admit_arm(records: Iterable[Record]) -> ArmAdmission:
    """Whether one verdict may be given over these records as one arm. Records that all lack the unlisted pair refuse
    nothing by that rule."""
    rs = list(records)
    if not rs:
        return ArmAdmission("refused", ("an arm of no records",))
    refused: list[str] = []
    unknown: list[str] = []
    for i, r in enumerate(rs):
        if not r.admissible_to_a_verdict():
            refused.append(f"record {i}: {r.why_not()}")
    ids = {r.identity if r.has_identity else None for r in rs}
    if len(ids - {None}) > 1:
        refused.append(f"{len(ids - {None})} harness identities in one arm")
    models = {r.model.model_identity if (r.model is not None and r.model.has_model_identity) else None for r in rs}
    if len(models) > 1:
        refused.append(f"{len(models)} model identity states in one arm (some may be none)")
    for kind in UNIFORM_WITHIN_ARM:
        states = [_state(r, kind) for r in rs]
        held = {d for s, d in states if s == "held"}
        if len(held) > 1:
            refused.append(f"{kind} is held with {len(held)} different digests")
        elif held and any(s == "none" for s, _ in states):
            refused.append(f"{kind} is held by some records and absent as {KNOWN_WHEN_ABSENT_AS} in others")
        elif any(s == "unknown" for s, _ in states):
            unknown.append(f"{kind} is unknown for some record")
    unlisted = {None if r.unlisted is None else (frozenset(r.unlisted), r.unlisted_omitted) for r in rs}
    if len(unlisted) > 1:
        refused.append("the records' unlisted request members differ, or some records name them and some do not")
    if refused:
        return ArmAdmission("refused", tuple(refused))
    if unknown:
        return ArmAdmission("unknown", tuple(unknown))
    return ArmAdmission("admitted")
