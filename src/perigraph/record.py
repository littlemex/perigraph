"""The record: parts held, parts absent with whose absence each is, and how the collector itself did.

Every refusal in this module exists because a number was published and had to be withdrawn. They are stated as
construction-time errors where the wrong object should not exist, and as read-time errors where the object is fine and
the thing being asked of it is not -- the split matters, and putting a refusal in the wrong one of the two was itself a
defect found by writing the first collector.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from perigraph.vocab import (ABSENCE_BLAMES, ABSENCE_REASONS, ADMISSIBLE_STATUS, BOUNDARIES,
                            DETAIL_REQUIRED_WHEN_BLAMES, KEYING_BOUNDARY, IDENTIFYING_SOURCING,
                            KNOWN_WHEN_ABSENT_AS, NEVER_IDENTIFYING, PARTS, MUST_BE_KNOWN_FOR_IDENTITY, REFINES_ONLY,
                            SOURCING, STATUS,
                            Unidentified)

if TYPE_CHECKING:  # pragma: no cover
    from perigraph.model import Model


#: The Unicode White_Space property (section 1.2). Named rather than `str.strip()`, which also strips U+001C-U+001F,
#: because three languages' default trims disagree at the edges and an emptiness test decides whether a part exists.
WHITE_SPACE = ("\u0009\u000a\u000b\u000c\u000d\u0020\u0085\u00a0\u1680" + "".join(chr(c) for c in range(0x2000, 0x200b))
               + "\u2028\u2029\u202f\u205f\u3000")


def blank(text: str) -> bool:
    """Empty after removing leading and trailing White_Space (section 1.2)."""
    return not text.strip(WHITE_SPACE)


def digest(payload: str) -> str:
    """Hash a part's content. Over the bytes, because that is the only thing a label cannot drift away from."""
    if blank(payload):
        raise Unidentified("an empty payload has no content to identify; a part that is genuinely empty is a part that "
                           "was not applied, and that is a different record")
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class Part:
    """One component of the harness, with how we know it, what its digest is over, and what that permits.

    `label` is for a reader and is explicitly **not** a key. A version string the owner controls can stay `v3` while the
    text under it changes, which is the failure this separation exists to prevent -- and it is a failure this project
    recorded twice, once for a model name and once for a prompt condition called "terse".
    """

    kind: str
    sourcing: str
    label: str = ""
    content_digest: str = ""
    boundary: str = "model_visible"
    #: How long before the request a pulled fact was read. Required there and refused elsewhere: a fetched copy
    #: describes a different moment than the request, and a lag nobody wrote down is a lag nobody can bound.
    read_lag_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in PARTS:
            raise Unidentified(
                f"{self.kind!r} is not one of {PARTS}. A part nobody named is a part that can change without the "
                f"identity changing, which is the defect this vocabulary exists to close")
        if self.sourcing not in SOURCING:
            raise Unidentified(f"{self.sourcing!r} is not one of {SOURCING}")
        if self.boundary not in BOUNDARIES:
            raise Unidentified(f"{self.boundary!r} is not one of {BOUNDARIES}")
        if self.sourcing == "loaded_by_us":
            raise Unidentified(
                f"{self.kind!r} is a harness part and cannot be loaded_by_us: that sourcing means the collector loaded "
                f"the model, and a harness part is what surrounded it")
        if self.sourcing == "not_observable" and self.content_digest:
            raise Unidentified(
                f"{self.kind!r} is recorded as not observable and carries a digest, so something was hashed. If bytes "
                f"exist, name the mode that produced them; if they do not, the digest is of something else")
        if self.sourcing == "pulled_by_us" and self.read_lag_seconds is None:
            raise Unidentified(
                f"{self.kind!r} was pulled and carries no lag. We read at one moment and the request ran at another; a "
                f"lag nobody wrote down is a lag nobody can bound, and everything that changed inside it is invisible")
        if self.sourcing != "pulled_by_us" and self.read_lag_seconds is not None:
            raise Unidentified(
                f"{self.kind!r} is {self.sourcing!r} and carries a read lag, which only a pulled fact has: bytes in the "
                f"request have no lag by definition, and a pushed claim's timing is the owner's word")
        if self.read_lag_seconds is not None and self.read_lag_seconds < 0:
            raise Unidentified(f"read_lag_seconds={self.read_lag_seconds!r} would mean it was read after the request "
                               f"it describes")

    @property
    def identifying(self) -> bool:
        """Whether this part may contribute to the identity. Three conditions, and all of them are needed.

        An earlier version refused a part whose digest was over the wrong boundary, and that was the wrong mechanism: a
        `tools` array is **in the request** and is **not text the model reads**, so `in_the_request` with a `parsed`
        digest is the common case and refusing it made the ordinary part unrepresentable. Excluding it from the hash
        instead makes the wrong identity unrepresentable while the part stays recorded.
        """
        if self.kind in NEVER_IDENTIFYING:
            return False
        if not self.content_digest:
            return False
        # Per part, not per boundary (keying_boundary): a boundary that may key one part must not let every part held at
        # it key, or tool_schemas at canonical_value would establish an identity on its own.
        if KEYING_BOUNDARY.get(self.kind) != self.boundary:
            return False
        return self.sourcing in IDENTIFYING_SOURCING

    def __str__(self) -> str:
        who = {"in_the_request": "in the request", "pulled_by_us": "pulled", "pushed_by_owner": "owner says",
               "not_observable": "NOT OBSERVABLE", "loaded_by_us": "loaded"}[self.sourcing]
        head = f"{self.kind} ({who}"
        if self.read_lag_seconds is not None:
            head += f", {self.read_lag_seconds:g}s before the request"
        head += ")"
        tail = f" {self.label}" if self.label else ""
        return head + tail + (f" {self.content_digest[:8]}@{self.boundary}" if self.content_digest else "")


@dataclass(frozen=True)
class Absence:
    """One part that is not in the record, and whose absence it is.

    A part is present or absent and never both: the same kind appearing in both is a record that answers "was this
    collected" two ways, and a consumer reads whichever it happened to check first.
    """

    kind: str
    reason: str
    #: What the collector was doing when it failed. Required for a collector-blamed absence, because a measurement
    #: failure nobody described is one nobody can fix -- and refused elsewhere, since the sender's silence has no moment
    #: for us to describe.
    detail: str = ""

    def __post_init__(self) -> None:
        if self.kind not in PARTS:
            raise Unidentified(f"{self.kind!r} is not one of {PARTS}. An absence of something the vocabulary does not "
                               f"name is a hole in the vocabulary rather than in the record")
        if self.reason not in ABSENCE_REASONS:
            raise Unidentified(f"{self.reason!r} is not one of {ABSENCE_REASONS}")
        if self.blames == DETAIL_REQUIRED_WHEN_BLAMES and not self.detail:
            raise Unidentified(
                f"{self.kind!r} is absent because of us ({self.reason!r}) and carries no detail. This is the entry that "
                f"exists to be actionable: a measurement failure nobody described will read as the sender's silence at "
                f"every later glance")
        if self.blames != DETAIL_REQUIRED_WHEN_BLAMES and self.detail:
            raise Unidentified(
                f"{self.kind!r} is absent as {self.reason!r}, which is not our failure, and carries detail. Detail here "
                f"describes what we were doing when we failed; there is no such moment")

    @property
    def blames(self) -> str:
        return ABSENCE_BLAMES[self.reason]

    def __str__(self) -> str:
        head = f"{self.kind} absent ({self.reason}, blames {self.blames})"
        return head + (f": {self.detail}" if self.detail else "")


@dataclass(frozen=True)
class Manifest:
    """What the collector claims it can reach here, so `not_reachable` is checkable rather than merely spelled.

    This is SCITT's separation -- who said this against is this true -- applied to the collector instead of only to the
    harness owner. `reaches` is a claim, and that is why it is worth having: a claim can contradict a record, and a
    contradiction is louder than a hole.
    """

    collector: str
    version: str
    reaches: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.collector or not self.version:
            raise Unidentified(
                "a manifest without a collector and a version cannot be compared against another run's, so a part that "
                "stopped being readable between two versions is a change nobody can attribute")
        unknown = sorted(set(self.reaches) - set(PARTS))
        if unknown:
            raise Unidentified(f"the manifest claims to reach {unknown}, which are not parts")
        if len(set(self.reaches)) != len(self.reaches):
            raise Unidentified(f"the manifest lists a part twice in {sorted(self.reaches)}")

    def __str__(self) -> str:
        return f"{self.collector}/{self.version} reaches {list(self.reaches)}"


@dataclass(frozen=True)
class Record:
    """One run's record: the parts held, the parts not held, and how the collector itself did.

    **Toward the sender this is maximally permissive.** Any combination of parts may be absent and the record is still
    valid, because a collector that refuses a partial record produces no record, and a run that emitted nothing is
    indistinguishable from a run that emitted a perfect record of nothing.

    **About itself it is exact.** The status says whether the collector finished, and a collector that failed cannot
    present its failure as the sender's silence.
    """

    manifest: Manifest
    status: str = "complete"
    parts: tuple[Part, ...] = ()
    absences: tuple[Absence, ...] = ()
    #: What answered (spec section 9), present only when a collector in the loading process -- or a relay forwarding its
    #: stamp verbatim -- recorded it. `None` is not "the model is unknown to be different"; it is "nothing was said".
    model: "Model | None" = None
    #: The request members the collector saw and its binding does not read (`perigraph.request.unlisted`), by name only.
    #: `None` is "nothing was said", which is unknown; an empty tuple is "the collector looked and there were none".
    unlisted: "tuple[str, ...] | None" = None
    #: How many unlisted members were counted and not named (`perigraph.request.unlisted_omitted`).
    unlisted_omitted: int = 0

    def __post_init__(self) -> None:
        if self.unlisted is None and self.unlisted_omitted:
            raise Unidentified("a count of unnamed unlisted members without the unlisted list says the collector looked "
                               "and also that it said nothing")
        if self.unlisted_omitted < 0:
            raise Unidentified("an unlisted count below zero")
        if self.status not in STATUS:
            raise Unidentified(f"{self.status!r} is not one of {STATUS}")
        held = [p.kind for p in self.parts]
        if len(set(held)) != len(held):
            raise Unidentified(f"two parts share a kind in {sorted(held)}, so nothing says which one applied")
        absent = [a.kind for a in self.absences]
        if len(set(absent)) != len(absent):
            raise Unidentified(f"two absences share a kind in {sorted(absent)}, so nothing says why the part is missing")
        both = sorted(set(held) & set(absent))
        if both:
            raise Unidentified(
                f"{both} are recorded as held and as absent at once, so this record answers 'was this collected' two "
                f"ways and a consumer reads whichever it happened to check first")

    @property
    def has_identity(self) -> bool:
        """Whether an identity can be derived (SPEC section 2). Three conditions:

        * some part is identifying;
        * one of them is not `refines_only`. A template's split between fixed text and item is the requester's word, and
          generation controls name none of the text the model read: each may split an identity a held instruction
          establishes and may never establish one;
        * every `must_be_known_for_identity` part is held in the request at its `keying_boundary` boundary, or absent
          `not_provided`. A part the collector failed to read, could not reach, or did not mention might have been
          there, and a declaration in its place would lift that refusal on the owner's word."""
        identifying = [p for p in self.parts if p.identifying]
        if not any(p.kind not in REFINES_ONLY for p in identifying):
            return False
        held = {p.kind for p in self.parts if p.sourcing == "in_the_request" and KEYING_BOUNDARY.get(p.kind) == p.boundary}
        kept = {a.kind for a in self.absences if a.reason == KNOWN_WHEN_ABSENT_AS}
        return all(k in held or k in kept for k in MUST_BE_KNOWN_FOR_IDENTITY)

    @property
    def identity(self) -> str:
        """Derived from the identifying parts in a fixed order, so it cannot be kept across a change to them.

        Raised rather than returned when nothing identifies this record. The refusal belongs here rather than at
        construction: a request carrying sampler settings and no instruction yields parts that are real and cannot key
        anything, and refusing the object threw those parts away -- they then looked like parts the collector had never
        mentioned. The parts were never the problem.
        """
        if not self.has_identity:
            raise Unidentified(
                "no part of this record is identified by bytes we hold that the model provably read, so an identity "
                "would be constant across every possible harness. A record without one describes somebody's account of "
                "a run rather than the run")
        h = hashlib.sha256()
        for p in sorted((p for p in self.parts if p.identifying), key=lambda p: p.kind):
            h.update(f"{p.kind}={p.content_digest};".encode())
        return h.hexdigest()[:24]

    @property
    def harness_identity(self) -> str:
        """The version 2 name of `identity`; version 3 computes it the same way for a record with no request template."""
        return self.identity

    @property
    def unaccounted(self) -> tuple[str, ...]:
        """Parts this record says nothing about at all -- neither held nor explained.

        Distinct from an absence, and the distinction is the point: an absence is a statement, and this is the silence
        an absence was invented to replace.
        """
        named = {p.kind for p in self.parts} | {a.kind for a in self.absences}
        return tuple(k for k in PARTS if k not in named)

    @property
    def contradictions(self) -> tuple[str, ...]:
        """Parts the collector claims it can reach here and then denied, or said nothing about.

        **The sender's silence is not a contradiction**, and getting that wrong inverts the whole vocabulary. A manifest
        claims "I can reach this IF it is there", not "this will be there", so comparing it against the parts held would
        report a request that simply carried no sampler settings as the collector regressing.

        `extraction_failed` is consistent with the claim -- the capability exists and failed on this input -- and is
        reported by `our_failures` instead.
        """
        held = {p.kind for p in self.parts}
        denied = {a.kind for a in self.absences if a.reason == "not_reachable"}
        explained = {a.kind for a in self.absences}
        return tuple(k for k in self.manifest.reaches
                     if k in denied or (k not in held and k not in explained))

    @property
    def our_failures(self) -> tuple[str, ...]:
        """Absences that are ours rather than the sender's. Separated because only these are ours to fix."""
        return tuple(a.kind for a in self.absences if a.blames == "collector")

    def admissible_to_a_verdict(self) -> bool:
        """Whether anything may publish a claim from this record. Three conditions, each a different failure."""
        return (self.status in ADMISSIBLE_STATUS and not self.contradictions and not self.model_contradictions
                and self.has_identity)

    @property
    def model_contradictions(self) -> tuple[str, ...]:
        """The same test against the model manifest (section 1.3): a claimed model part denied or left unmentioned."""
        return self.model.contradictions if self.model is not None else ()

    def why_not(self) -> str:
        """One sentence naming everything standing between this record and a published claim."""
        if self.admissible_to_a_verdict():
            return f"admissible: {self.status}, no contradiction, identity {self.identity}"
        reasons = []
        if self.status not in ADMISSIBLE_STATUS:
            reasons.append(f"the collector reports {self.status!r}, so the record does not describe the run it looks "
                           f"like")
        if self.contradictions:
            reasons.append(f"the manifest claims to reach {list(self.contradictions)} and did not deliver them, so no "
                           f"absence here can be read at face value")
        if self.model_contradictions:
            reasons.append(f"the model manifest claims to reach {list(self.model_contradictions)} and did not deliver "
                           f"them")
        if not self.has_identity:
            reasons.append("no part was identified by bytes we hold that the model provably read, so the identity "
                           "would be the same for every possible harness")
        return "not admissible to a verdict -- " + "; and ".join(reasons)

    def __str__(self) -> str:
        who = self.identity if self.has_identity else "no identity"
        return (f"record {who} ({self.status}); held {len(self.parts)}; absent {len(self.absences)}; "
                f"unaccounted {list(self.unaccounted) or 'none'}; "
                f"contradictions {list(self.contradictions) or 'none'}")
