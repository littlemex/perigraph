"""What answered: the model parts, their digests, and the two identities over them (spec version 2, section 9).

Version 1 identified the harness only, and said so: two precisions of one checkpoint, and an answer read from option
scores against one parsed out of generated text, shared one identity. Every row of the table below happened in one
distillation record, and in every row the names stayed the same while the answers moved:

| moment | what changed | effect on answers |
|---|---|---|
| R5 -> R6, R12 -> R13 | the checkpoint was re-trained from the same script and seed | 93.4 % label agreement |
| R6 | dynamic int8 quantisation at load; the stored bytes did not change | 33-40 % agreement |
| R14 | the serving image lost packages | 97 of 100 re-answered the same |
| R5-R10 against R12 | option scores against generated text | the score-trained student generated "1111" |

So the model is described by four parts, each digested by the process that loaded it (`loaded_by_us`), and two
identities: `model_identity` over all four, comparable only within one collector and version because `precision` and
`runtime` are that collector's rendering, and `artifact_identity` over the checkpoint alone, comparable across
collectors because it is a digest of file bytes anybody holding the files can compute -- a trainer at save time
included.

Nothing here reads a network or a framework. A loader passes in what it loaded; the helpers only define how that is
turned into bytes, because that is the part two implementations would otherwise do differently.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping

from perigraph.record import WHITE_SPACE, digest
from perigraph.vocab import (ABSENCE_BLAMES, ABSENCE_REASONS, ANSWER_MODES, DETAIL_REQUIRED_WHEN_BLAMES,
                            IDENTIFYING_MODEL_SOURCING, MODEL_PARTS, SOURCING, Unidentified)

IDENTITY_LENGTH = 24


def checkpoint_digest(entries: Iterable[tuple[str, str]]) -> str:
    """The `checkpoint` digest over (relative POSIX path, sha256 of the file) pairs.

    Sorted by the path's utf-8 bytes rather than by Python's string order, so a second implementation in a language with
    a different collation cannot disagree. A path with a tab or a newline is refused, since those are the separators.
    """
    rows = []
    seen = set()
    for path, sha in entries:
        if not path or "\t" in path or "\n" in path:
            raise Unidentified(f"checkpoint path {path!r} is empty or contains a tab or a newline, which are the "
                               f"manifest's separators")
        if path.startswith("/") or "\\" in path or any(seg in ("", ".", "..") for seg in path.split("/")):
            raise Unidentified(f"checkpoint path {path!r} is not a normalised POSIX path relative to the artifact root")
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise Unidentified(f"checkpoint file {path!r} has digest {sha!r}, which is not lowercase hex sha256")
        if path in seen:
            raise Unidentified(f"checkpoint path {path!r} is listed twice")
        seen.add(path)
        rows.append((path.encode("utf-8"), f"{path}\t{sha}\n"))
    if not rows:
        raise Unidentified("a checkpoint with no files has no content to identify")
    text = "".join(r for _, r in sorted(rows))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def checkpoint_entries(root: str | Path, files: Iterable[str | Path]) -> list[tuple[str, str]]:
    """Hash the files a loader actually opened, as (relative path, sha256) pairs, with symlinks resolved.

    The loader names the files it read: an artifact directory can hold files nobody loads (an optimiser state, a stale
    shard), and hashing the directory would split two identical models over a file that never touched an answer.
    """
    base = Path(root)
    out = []
    for f in files:
        p = Path(f)
        rel = PurePosixPath(p.relative_to(base).as_posix() if p.is_absolute() else p.as_posix())
        full = (p if p.is_absolute() else base / p).resolve()
        h = hashlib.sha256()
        with open(full, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        out.append((str(rel), h.hexdigest()))
    return out


def lines_digest(pairs: Mapping[str, object], sep: str = "=") -> str:
    """The `precision` (sep '=') and `runtime` (sep '==') digests: one '<key><sep><value>\\n' line per entry, sorted."""
    if not pairs:
        raise Unidentified("an empty mapping has no content to identify")
    lines = []
    for k, v in pairs.items():
        k, v = str(k), str(v)
        if not k or "\n" in k or "\n" in v or sep in k:
            raise Unidentified(f"{k!r}={v!r} cannot be rendered as one line")
        lines.append((k.encode("utf-8"), f"{k}{sep}{v}\n"))
    return hashlib.sha256("".join(r for _, r in sorted(lines)).encode("utf-8")).hexdigest()


def precision_digest(fields: Mapping[str, object]) -> str:
    """Read off the loaded parameters, never the configuration: `auto` is not a precision, it is a question."""
    for k, v in fields.items():
        name = k.split(".", 1)[1] if k.startswith("dtype.") else None
        if str(v).strip(WHITE_SPACE).lower() in ("", "auto") or (
                name is not None and name.strip(WHITE_SPACE).lower() in ("", "auto")):
            raise Unidentified(f"precision field {k}={v!r} is unresolved; record the part as extraction_failed instead")
    return lines_digest(fields, "=")


def runtime_digest(packages: Mapping[str, str]) -> str:
    return lines_digest(packages, "==")


@dataclass(frozen=True)
class ModelPart:
    """One part of what answered. A model part carries no boundary: its content is defined by the spec per part."""

    kind: str
    sourcing: str
    content_digest: str = ""
    label: str = ""
    read_lag_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in MODEL_PARTS:
            raise Unidentified(f"{self.kind!r} is not one of {MODEL_PARTS}")
        if self.sourcing not in SOURCING:
            raise Unidentified(f"{self.sourcing!r} is not one of {SOURCING}")
        if self.sourcing == "in_the_request":
            raise Unidentified(f"model part {self.kind!r} cannot be in the request: a request does not carry weights")
        if self.sourcing == "not_observable" and self.content_digest:
            raise Unidentified(f"model part {self.kind!r} is not observable and carries a digest")
        if self.sourcing == "pulled_by_us" and self.read_lag_seconds is None:
            raise Unidentified(f"model part {self.kind!r} was pulled and carries no lag; a stamp read back over a "
                               f"separate request describes another moment, and possibly another replica")
        if self.sourcing != "pulled_by_us" and self.read_lag_seconds is not None:
            raise Unidentified(f"model part {self.kind!r} is {self.sourcing!r} and carries a read lag")
        if self.read_lag_seconds is not None and self.read_lag_seconds < 0:
            raise Unidentified(f"read_lag_seconds={self.read_lag_seconds!r} is negative")
        if self.content_digest and (len(self.content_digest) != 64
                                    or any(c not in "0123456789abcdef" for c in self.content_digest)):
            raise Unidentified(f"model part {self.kind!r} digest {self.content_digest!r} is not lowercase hex sha256")
        if self.kind == "answer_mode" and self.content_digest:
            if self.label not in ANSWER_MODES:
                raise Unidentified(f"answer_mode must be labelled with one of {ANSWER_MODES}, not {self.label!r}")
            if self.content_digest != digest(self.label):
                raise Unidentified(f"answer_mode digest does not match its label {self.label!r}")

    @property
    def identifying(self) -> bool:
        return bool(self.content_digest) and self.sourcing in IDENTIFYING_MODEL_SOURCING


@dataclass(frozen=True)
class ModelAbsence:
    """A model part not in the record, and whose absence it is -- the same blame rules as a harness absence."""

    kind: str
    reason: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.kind not in MODEL_PARTS:
            raise Unidentified(f"{self.kind!r} is not one of {MODEL_PARTS}")
        if self.reason not in ABSENCE_REASONS:
            raise Unidentified(f"{self.reason!r} is not one of {ABSENCE_REASONS}")
        blames = ABSENCE_BLAMES[self.reason]
        if blames == DETAIL_REQUIRED_WHEN_BLAMES and not self.detail:
            raise Unidentified(f"model part {self.kind!r} is absent because of us ({self.reason!r}) and says nothing "
                               f"about what failed")
        if blames != DETAIL_REQUIRED_WHEN_BLAMES and self.detail:
            raise Unidentified(f"model part {self.kind!r} is absent as {self.reason!r}, which is not our failure, and "
                               f"carries detail")

    @property
    def blames(self) -> str:
        return ABSENCE_BLAMES[self.reason]


def _identity(pairs: Iterable[tuple[str, str]]) -> str:
    h = hashlib.sha256()
    for kind, d in sorted(pairs):
        h.update(f"{kind}={d};".encode("utf-8"))
    return h.hexdigest()[:IDENTITY_LENGTH]


@dataclass(frozen=True)
class Model:
    """The model half of a record: parts held, parts absent, and which the collector claims it can reach."""

    parts: tuple[ModelPart, ...] = ()
    absences: tuple[ModelAbsence, ...] = ()
    reaches: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        held = [p.kind for p in self.parts]
        absent = [a.kind for a in self.absences]
        if len(set(held)) != len(held) or len(set(absent)) != len(absent):
            raise Unidentified("a model part is listed twice")
        if set(held) & set(absent):
            raise Unidentified(f"{sorted(set(held) & set(absent))} are recorded as held and absent at once")
        unknown = sorted(set(self.reaches) - set(MODEL_PARTS))
        if unknown or len(set(self.reaches)) != len(self.reaches):
            raise Unidentified(f"the manifest's model reach {list(self.reaches)} is not a set of model parts")

    @property
    def has_model_identity(self) -> bool:
        ids = {p.kind for p in self.parts if p.identifying}
        return ids == set(MODEL_PARTS)

    @property
    def model_identity(self) -> str:
        """Over all four parts or not at all: a model identity missing `precision` would let R6's int8 wear the bf16
        identity, and one missing `runtime` would let R14's broken image wear the working one."""
        if not self.has_model_identity:
            missing = sorted(set(MODEL_PARTS) - {p.kind for p in self.parts if p.identifying})
            raise Unidentified(f"no model identity: {missing} are not loaded_by_us with a digest")
        return _identity((p.kind, p.content_digest) for p in self.parts)

    @property
    def has_artifact_identity(self) -> bool:
        return any(p.kind == "checkpoint" and p.identifying for p in self.parts)

    @property
    def artifact_identity(self) -> str:
        if not self.has_artifact_identity:
            raise Unidentified("no artifact identity: the checkpoint is not loaded_by_us with a digest")
        cp = next(p for p in self.parts if p.kind == "checkpoint")
        return _identity([("checkpoint", cp.content_digest)])

    @property
    def contradictions(self) -> tuple[str, ...]:
        held = {p.kind for p in self.parts}
        denied = {a.kind for a in self.absences if a.reason == "not_reachable"}
        explained = {a.kind for a in self.absences}
        return tuple(k for k in self.reaches if k in denied or (k not in held and k not in explained))


def loaded(*, checkpoint: str, precision: str, runtime: str, answer_mode: str, labels: Mapping[str, str] | None = None,
           ) -> Model:
    """The model half as a loading process emits it: every part `loaded_by_us`, and the manifest claiming all four."""
    labels = dict(labels or {})
    parts = (ModelPart("checkpoint", "loaded_by_us", checkpoint, labels.get("checkpoint", "")),
             ModelPart("precision", "loaded_by_us", precision, labels.get("precision", "")),
             ModelPart("runtime", "loaded_by_us", runtime, labels.get("runtime", "")),
             ModelPart("answer_mode", "loaded_by_us", digest(answer_mode), answer_mode))
    return Model(parts=parts, reaches=MODEL_PARTS)


def behind_a_provider(label: str) -> Model:
    """A model served behind somebody else's API: nothing is observable, a label is all there is, and no identity."""
    return Model(parts=tuple(ModelPart(k, "not_observable", label=label if k == "checkpoint" else "")
                             for k in MODEL_PARTS))


# --- receiver refusals over many records ------------------------------------------------------------------------------

def refuse_mixed_model_identities(records_by_arm: Mapping[str, Iterable[object]]) -> None:
    """A verdict over records grouped as one arm that carry more than one model identity, or some with and some without.

    `records_by_arm` maps an arm name to records (anything with a `model` attribute that is a `Model` or None)."""
    for arm, records in records_by_arm.items():
        seen = set()
        for r in records:
            m = getattr(r, "model", None)
            seen.add(m.model_identity if (m is not None and m.has_model_identity) else None)
        if len(seen) > 1:
            shown = sorted(s or "<none>" for s in seen)
            raise Unidentified(f"arm {arm!r} groups records from {len(seen)} model identities {shown}; a verdict over "
                               f"them is a verdict over none of them")


def refuse_unbound_claim(bound_to: str, records: Iterable[object]) -> None:
    """A claim bound to a model identity, applied to records that do not carry that model identity."""
    for r in records:
        m = getattr(r, "model", None)
        got = m.model_identity if (m is not None and m.has_model_identity) else None
        if got != bound_to:
            raise Unidentified(f"the claim is bound to model {bound_to} and a record carries {got or '<none>'}; it is "
                               f"about something else")


def refuse_cross_collector_model_comparison(a: object, b: object) -> None:
    """Two model identities from different collectors or collector versions are not comparable: `precision` and
    `runtime` are each collector's rendering. Compare `artifact_identity` instead."""
    ma, mb = getattr(a, "manifest"), getattr(b, "manifest")
    if (ma.collector, ma.version) != (mb.collector, mb.version):
        raise Unidentified(f"model identities from {ma.collector}/{ma.version} and {mb.collector}/{mb.version} are "
                           f"collector-local; compare artifact identities instead")
