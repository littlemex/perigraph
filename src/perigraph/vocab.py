"""The closed vocabularies, loaded from the normative spec rather than retyped beside it.

**Why this module reads a JSON file instead of declaring constants.** The protocol has two sides, and each needs the
same lists. Retyping them is how two sides drift, and drift here is not a cosmetic problem: a receiver that accepts a
sourcing mode the sender never meant will read a pushed claim as bytes it holds. So `spec/vocabularies.json` is
normative, this module is a reader of it, and `conformance()` below is what a second implementation runs to say it
implements the same protocol.

The file ships inside the package. A reader of an installed copy has to be able to check it against the vocabularies it
was built from, and a package that left the spec behind would be unverifiable by anyone who did not clone the source.
"""
from __future__ import annotations

import json
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parent / "vocabularies.json"
if not SPEC_PATH.exists():  # pragma: no cover - only on a source checkout
    SPEC_PATH = Path(__file__).resolve().parents[2] / "spec" / "vocabularies.json"

_SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))

SPEC_VERSION: int = _SPEC["spec_version"]
NAMESPACE: str = _SPEC["namespace"]

PARTS: tuple[str, ...] = tuple(_SPEC["parts"]["values"])
SOURCING: tuple[str, ...] = tuple(_SPEC["sourcing"]["values"])
IDENTIFYING_SOURCING: tuple[str, ...] = tuple(_SPEC["sourcing"]["may_key_identity"])
BOUNDARIES: tuple[str, ...] = tuple(_SPEC["boundaries"]["values"])
IDENTIFYING_BOUNDARIES: tuple[str, ...] = tuple(_SPEC["boundaries"]["may_key_identity"])
NEVER_IDENTIFYING: tuple[str, ...] = tuple(_SPEC["never_identifying"]["values"])
ABSENCE_REASONS: tuple[str, ...] = tuple(_SPEC["absence_reasons"]["values"])
ABSENCE_BLAMES: dict[str, str] = dict(_SPEC["absence_reasons"]["blames"])
DETAIL_REQUIRED_WHEN_BLAMES: str = _SPEC["absence_reasons"]["detail_required_when_blames"]
STATUS: tuple[str, ...] = tuple(_SPEC["status"]["values"])
ADMISSIBLE_STATUS: tuple[str, ...] = tuple(_SPEC["status"]["admissible_to_a_verdict"])
CONTEXT_CROSSINGS: tuple[str, ...] = tuple(_SPEC["context_crossings"]["values"])
TOOL_DETERMINISM: tuple[str, ...] = tuple(_SPEC["tool_determinism"]["values"])
DIVERGENCE_LICENSES: dict[str, str] = dict(_SPEC["tool_determinism"]["divergence_licenses"])
OCCASION_FIELDS: tuple[str, ...] = tuple(_SPEC["occasion"]["fields"])
BILLED_LEGS: tuple[str, ...] = tuple(_SPEC["billed_legs"]["values"])


class Unidentified(ValueError):
    """A record was built in a way that lets two different harnesses wear one identity.

    Raised at construction rather than reported later, because the whole point is to make the grouping wrong *before*
    anything is measured under it. Once two runs have been compared, the fact that they were different harnesses is not
    recoverable from the numbers.
    """


def conformance() -> dict[str, object]:
    """What a second implementation must reproduce to claim it implements this protocol.

    Returned as data rather than asserted here, so an implementation in another language can compare its own tables
    against the same file without reimplementing this module's opinions.
    """
    return {
        "spec_version": SPEC_VERSION,
        "namespace": NAMESPACE,
        "parts": PARTS,
        "sourcing": SOURCING,
        "boundaries": BOUNDARIES,
        "absence_reasons": ABSENCE_REASONS,
        "status": STATUS,
        "context_crossings": CONTEXT_CROSSINGS,
        "tool_determinism": TOOL_DETERMINISM,
        "billed_legs": BILLED_LEGS,
    }


def check_spec_is_total() -> None:
    """Refuse a spec whose classifications do not cover their own vocabularies.

    Every one of these is a table that decides what a value MEANS, and a value missing from one of them does not fail
    loudly on its own -- it falls through to whatever the reader's default is, which is exactly how a measurement
    failure gets recorded as a fact about the world. So the totality is checked when the module loads rather than left
    to a test somebody may not run.
    """
    if set(ABSENCE_BLAMES) != set(ABSENCE_REASONS):
        raise Unidentified(
            f"absence_reasons.blames covers {sorted(ABSENCE_BLAMES)} and the vocabulary is {sorted(ABSENCE_REASONS)}. "
            f"A reason with no blame falls through to the reader's default, which is how a collector's failure gets "
            f"recorded as the sender's silence")
    if set(DIVERGENCE_LICENSES) != set(TOOL_DETERMINISM):
        raise Unidentified(
            f"tool_determinism.divergence_licenses covers {sorted(DIVERGENCE_LICENSES)} and the vocabulary is "
            f"{sorted(TOOL_DETERMINISM)}. A determinism value with no licence would let a divergence be read as "
            f"whatever the caller hoped")
    for name, subset, whole in (("sourcing", IDENTIFYING_SOURCING, SOURCING),
                                ("boundaries", IDENTIFYING_BOUNDARIES, BOUNDARIES)):
        extra = set(subset) - set(whole)
        if extra:
            raise Unidentified(f"{name}.may_key_identity names {sorted(extra)}, which is not in its own vocabulary")
    extra_parts = set(NEVER_IDENTIFYING) - set(PARTS)
    if extra_parts:
        raise Unidentified(f"never_identifying names {sorted(extra_parts)}, which are not parts")


check_spec_is_total()
