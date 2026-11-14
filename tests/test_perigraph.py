"""Tests for the record, the wire form and the injection.

The measurement every refusal here comes from: same model, same 1,187 items, one sentence of the instruction changed --
0.6243 against 0.7447, with per-item agreement 0.7346, so one item in four flips. Twelve points from one sentence, which
is why the instruction is hashed raw and why a part nobody named is treated as a defect rather than an omission.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import perigraph as pg  # noqa: E402
from perigraph import collect, record as rec, vocab, wire  # noqa: E402

TERSE = "Answer with the option letter only. Do not explain."
EXPLAIN = "Think step by step, then answer with the option letter."

BODY = {
    "messages": [{"role": "system", "content": TERSE}, {"role": "user", "content": "Q1"}],
    "tools": [{"function": {"name": "search", "parameters": {"type": "object"}}}],
    "temperature": 0.0,
    "top_p": 1.0,
}


def read(body=None):
    return collect.from_request(body if body is not None else BODY, collector="t", version="1")


def part(**kw):
    base = dict(kind="instruction", sourcing="in_the_request", content_digest=rec.digest(TERSE))
    base.update(kw)
    return rec.Part(**base)


# --- the spec is the source, and its classifications are total ------------------------------------------------------------

def test_every_absence_reason_is_blamed_and_every_determinism_licenses_something():
    """Checked when the module loads rather than left to a test, because a value missing from one of these tables does not
    fail loudly -- it falls through to the reader's default."""
    assert set(vocab.ABSENCE_BLAMES) == set(vocab.ABSENCE_REASONS)
    assert set(vocab.DIVERGENCE_LICENSES) == set(vocab.TOOL_DETERMINISM)
    assert set(vocab.ABSENCE_BLAMES.values()) == {"sender", "collector", "nobody"}


def test_the_identity_permissions_are_subsets_of_their_own_vocabularies():
    assert set(vocab.IDENTIFYING_SOURCING) <= set(vocab.SOURCING)
    assert set(vocab.IDENTIFYING_BOUNDARIES) <= set(vocab.BOUNDARIES)
    assert set(vocab.NEVER_IDENTIFYING) <= set(vocab.PARTS)
    assert set(vocab.REFINES_ONLY) <= set(vocab.PARTS) and set(vocab.MUST_BE_KNOWN_FOR_IDENTITY) <= set(vocab.PARTS)


def test_conformance_names_what_a_second_implementation_has_to_reproduce():
    """Data rather than assertions, so an implementation in another language can compare its own tables against the same
    file without reimplementing this module's opinions."""
    c = pg.conformance()
    assert c["namespace"] == "perigraph" and c["spec_version"] == 3
    assert set(c) == {"spec_version", "namespace", "parts", "model_parts", "answer_modes", "lineage_methods",
                      "lineage_set_roles", "sourcing", "boundaries", "absence_reasons", "status", "context_crossings",
                      "tool_determinism", "billed_legs"}


def test_a_broken_spec_is_refused_when_it_is_read():
    with pytest.raises(vocab.Unidentified, match="falls through to the reader's default"):
        saved = dict(vocab.ABSENCE_BLAMES)
        try:
            vocab.ABSENCE_BLAMES.pop("redacted")
            vocab.check_spec_is_total()
        finally:
            vocab.ABSENCE_BLAMES.clear()
            vocab.ABSENCE_BLAMES.update(saved)


# --- whose absence it is --------------------------------------------------------------------------------------------------

def test_the_senders_silence_and_our_blindness_are_different_records():
    assert rec.Absence(kind="decoding", reason="not_provided").blames == "sender"
    ours = rec.Absence(kind="decoding", reason="not_reachable", detail="SDK renamed the sampling block")
    assert ours.blames == "collector"


def test_our_own_failure_has_to_say_what_we_were_doing():
    with pytest.raises(vocab.Unidentified, match="nobody described"):
        rec.Absence(kind="decoding", reason="extraction_failed")


def test_a_detail_is_refused_where_there_was_no_moment_to_describe():
    with pytest.raises(vocab.Unidentified, match="no such moment"):
        rec.Absence(kind="decoding", reason="not_provided", detail="we were busy")


# --- only what the model provably read can identify -----------------------------------------------------------------------

def test_a_harness_read_from_a_request_is_identified_by_its_instruction_and_nothing_else():
    """The finding, not a limitation. A tools array, a response format and the sampler settings are protocol values the
    provider renders however it likes, and the sender does not hold that rendering."""
    r = read()
    assert [p.kind for p in r.parts if p.identifying] == ["instruction"]
    assert {p.kind for p in r.parts if not p.identifying} == {"tool_schemas", "decoding"}
    assert collect.REQUEST_BOUNDARIES["instruction"] == "model_visible"
    assert set(collect.REQUEST_BOUNDARIES.values()) - {"model_visible"} == {"parsed"}


def test_a_parsed_digest_is_recorded_and_never_enters_the_hash():
    no_template = (rec.Absence(kind="request_template", reason="not_provided"),)
    only_instruction = rec.Record(manifest=rec.Manifest(collector="t", version="1", reaches=()),
                                  parts=(part(),), absences=no_template)
    with_a_parsed_part = rec.Record(
        manifest=rec.Manifest(collector="t", version="1", reaches=()),
        parts=(part(), part(kind="decoding", content_digest=rec.digest("temperature=0.0"), boundary="parsed")),
        absences=no_template)
    assert with_a_parsed_part.identity == only_instruction.identity


def test_the_instruction_is_hashed_raw_down_to_case_and_whitespace():
    """The invariant the whole thing rests on. The model reads the STRING, not its meaning: 0.6243 against 0.7447 came
    from one sentence's wording, so two spellings are two harnesses even where a human would call them the same."""
    base = read().identity
    for variant in (TERSE.lower(), TERSE.upper(), "  " + TERSE, TERSE + "\n", TERSE.replace(". ", ".  ")):
        other = read({**BODY, "messages": [{"role": "system", "content": variant}]})
        assert other.identity != base, repr(variant)


def test_a_trace_may_never_key_an_identity_even_though_we_hold_its_bytes():
    p = part(kind="tool_trace", content_digest="a" * 64, boundary="model_visible")
    assert p.identifying is False
    assert vocab.NEVER_IDENTIFYING == ("tool_trace",)


def test_two_wordings_are_two_harnesses():
    assert read().identity != read({**BODY, "messages": [{"role": "system", "content": EXPLAIN}]}).identity


def test_the_toolset_digest_does_not_depend_on_the_order_the_caller_listed_them():
    tools = [{"function": {"name": "a", "parameters": {}}}, {"function": {"name": "b", "parameters": {}}}]
    forward = {p.kind: p.content_digest for p in read({**BODY, "tools": tools}).parts}["tool_schemas"]
    reverse = {p.kind: p.content_digest for p in read({**BODY, "tools": list(reversed(tools))}).parts}["tool_schemas"]
    assert forward == reverse


# --- permissive toward the sender, exact about itself ---------------------------------------------------------------------

def test_the_senders_silence_is_not_a_contradiction():
    """A manifest claims it can reach a part IF it is there, not that it will be there."""
    r = read({"messages": [{"role": "system", "content": TERSE}]})
    assert r.contradictions == () and r.our_failures == ()
    assert r.admissible_to_a_verdict() is True


def test_a_denial_of_the_manifests_claim_is_a_contradiction():
    r = rec.Record(manifest=rec.Manifest(collector="t", version="1", reaches=("instruction", "decoding")),
                   parts=(part(),),
                   absences=(rec.Absence(kind="decoding", reason="not_reachable", detail="renamed field"),))
    assert r.contradictions == ("decoding",)
    assert r.admissible_to_a_verdict() is False


def test_a_claimed_part_nobody_said_anything_about_is_a_contradiction():
    r = rec.Record(manifest=rec.Manifest(collector="t", version="1", reaches=("instruction", "decoding")),
                   parts=(part(),))
    assert r.contradictions == ("decoding",)


def test_a_request_with_no_instruction_keeps_its_parts_and_supports_no_claim():
    r = read({"messages": [{"role": "user", "content": "Q"}], "temperature": 0.0})
    assert [p.kind for p in r.parts] == ["decoding"]
    assert r.has_identity is False
    with pytest.raises(vocab.Unidentified, match="constant across every possible harness"):
        r.identity
    assert r.admissible_to_a_verdict() is False


def test_a_collector_that_did_not_finish_cannot_look_complete():
    r = rec.Record(manifest=rec.Manifest(collector="t", version="1", reaches=()),
                   status="collector_failed", parts=(part(),))
    assert r.admissible_to_a_verdict() is False
    assert "does not describe the run" in r.why_not()


def test_a_part_cannot_be_held_and_absent_at_once():
    with pytest.raises(vocab.Unidentified, match="two ways"):
        rec.Record(manifest=rec.Manifest(collector="t", version="1", reaches=()),
                   parts=(part(),), absences=(rec.Absence(kind="instruction", reason="not_provided"),))


def test_the_manifest_is_static_per_version_so_it_can_actually_contradict():
    """A manifest built from what was found could never contradict a record, and contradicting one is the only thing it
    is for. So a body that carried nothing still claims all four."""
    assert read().manifest.reaches == collect.FROM_A_REQUEST
    assert read({"messages": []}).manifest.reaches == collect.FROM_A_REQUEST
    assert read({"messages": [{"role": "system", "content": TERSE}]}).manifest.reaches == collect.FROM_A_REQUEST


def test_the_collector_accounts_for_every_part_it_names():
    """Unaccounted is the silence an absence was invented to replace, so a real collector must leave none."""
    assert read().unaccounted == ()
    assert read({"messages": []}).unaccounted == ()


def test_a_pulled_fact_carries_its_lag_and_nothing_else_may():
    with pytest.raises(vocab.Unidentified, match="lag nobody wrote down"):
        part(sourcing="pulled_by_us")
    with pytest.raises(vocab.Unidentified, match="only a pulled fact has"):
        part(read_lag_seconds=3.0)


# --- what a request cannot carry, declared separately ---------------------------------------------------------------------

def test_a_declaration_replaces_the_absence_and_still_cannot_identify():
    d = collect.declare(read(), loop="react v3", turn_budget="8")
    declared = [p for p in d.parts if p.sourcing == "pushed_by_owner"]
    assert {p.kind for p in declared} == {"loop", "turn_budget"}
    assert not any(p.identifying for p in declared)
    assert {a.kind for a in d.absences} & {"loop", "turn_budget"} == set()
    assert d.identity == read().identity


def test_declaring_something_the_request_already_says_is_refused():
    """A claim standing in front of the evidence."""
    with pytest.raises(ValueError, match="claim standing in front of the evidence"):
        collect.declare(read(), instruction="terse")


# --- the wire form --------------------------------------------------------------------------------------------------------

def test_the_wire_form_round_trips():
    r = read()
    back = wire.from_attributes(wire.to_attributes(r))
    assert back.identity == r.identity
    assert sorted((a.kind, a.reason) for a in back.absences) == sorted((a.kind, a.reason) for a in r.absences)
    assert sorted((p.kind, p.boundary, p.content_digest) for p in back.parts) \
        == sorted((p.kind, p.boundary, p.content_digest) for p in r.parts)


def test_an_absent_identity_is_omitted_rather_than_empty():
    """An empty identity string compares equal to another empty one, which would group every unidentifiable run
    together -- the failure the identity rules exist to prevent, reintroduced by the transport."""
    attrs = wire.to_attributes(read({"messages": [{"role": "user", "content": "Q"}], "temperature": 0.0}))
    assert "perigraph.harness_identity" not in attrs
    assert not any(k.endswith("identity") for k in attrs)


def test_every_wire_value_is_a_scalar_a_tracer_will_accept():
    for key, value in wire.to_attributes(read()).items():
        assert isinstance(value, (str, int, float)), (key, type(value))


def test_a_version_this_reader_does_not_implement_is_refused_rather_than_guessed_at():
    attrs = wire.to_attributes(read())
    attrs["perigraph.spec_version"] = 99
    with pytest.raises(vocab.Unidentified, match="dropped absence"):
        wire.from_attributes(attrs)


# --- the injection --------------------------------------------------------------------------------------------------------

def test_wrapping_preserves_the_return_value_and_records_on_the_way_past():
    seen = []
    wrapped = pg.wrap(lambda body: {"ok": True}, on_record=seen.append)
    assert wrapped(BODY) == {"ok": True}
    assert seen[0].admissible_to_a_verdict() is True


def test_a_body_it_cannot_find_never_breaks_the_call():
    """A shim that can break the request it describes is a shim nobody leaves installed, and then there is no record."""
    seen = []
    wrapped = pg.wrap(lambda x: x * 2, on_record=seen.append)
    assert wrapped(21) == 42
    assert seen[0].status == "collector_failed"


def test_a_sink_that_raises_never_breaks_the_call_either():
    def explode(_):
        raise RuntimeError("the sink is broken")
    assert pg.wrap(lambda body: "sent", on_record=explode)(BODY) == "sent"


def test_a_collector_that_crashed_emits_a_record_rather_than_nothing(monkeypatch):
    """A collector cannot record its own absence: if a crashed shim emitted nothing, the run would be indistinguishable
    from a run that never happened."""
    from perigraph import instrument

    def broken(*_a, **_k):
        raise RuntimeError("a bug in the collector")
    monkeypatch.setattr(instrument, "from_request", broken)
    r = pg.observe(BODY)
    assert r.status == "collector_failed"
    assert r.admissible_to_a_verdict() is False


def test_a_body_that_is_not_an_object_is_named_not_a_crash():
    """SPEC 1.2: a request we cannot parse is an absence we name. The status stays complete, because this collector
    finished; every manifest part says what was found."""
    a = pg.to_attributes(pg.observe(None))
    assert a["perigraph.status"] == "complete"
    for k in ("instruction", "tool_schemas", "readout", "decoding"):
        assert a[f"perigraph.absent.{k}.reason"] == "extraction_failed"
        assert a[f"perigraph.absent.{k}.detail"] == "the body is null, not an object"


def test_messages_that_is_not_an_array_fails_only_what_is_read_from_messages():
    a = pg.to_attributes(pg.observe({"messages": "x", "temperature": 0.0}))
    assert a["perigraph.absent.instruction.reason"] == "extraction_failed"
    assert a["perigraph.absent.instruction.detail"] == "messages is a string, not an array"
    assert a["perigraph.part.decoding.sourcing"] == "in_the_request"


def test_a_system_message_with_an_array_of_parts_fails_the_instruction_without_quoting_it():
    """SPEC 2.2: the chat template decides how parts become text, and the request does not carry it. The two reference
    senders used to render the same array as two different strings and so gave one request two identities."""
    body = {"messages": [{"role": "system", "content": "Terse."},
                         {"role": "system", "content": [{"type": "text", "text": "secret prompt"}]}]}
    a = pg.to_attributes(pg.observe(body))
    assert a["perigraph.absent.instruction.reason"] == "extraction_failed"
    assert a["perigraph.absent.instruction.detail"] == "messages[1].content is an array, not a string"
    assert "secret" not in json.dumps(a)
    assert "perigraph.harness_identity" not in a


def test_a_request_collector_says_the_model_was_not_observable():
    """SPEC 6: a collector that did not load the model names the four model parts absent instead of leaving them out."""
    a = pg.to_attributes(pg.observe(BODY))
    for k in ("checkpoint", "precision", "runtime", "answer_mode"):
        assert a[f"perigraph.model_absent.{k}.reason"] == "not_observable"
    assert "perigraph.model_identity" not in a and "perigraph.artifact_identity" not in a


def test_a_record_with_no_model_half_is_read_not_refused():
    """SPEC 6: a missing model half is a hole nobody named, read as unknown; a provider's label is the other form."""
    a = {k: v for k, v in pg.to_attributes(pg.observe(BODY)).items() if "model" not in k}
    assert wire.from_attributes(a).model is None
    a["perigraph.model.checkpoint.sourcing"], a["perigraph.model.checkpoint.label"] = "not_observable", "provider-x"
    assert not wire.from_attributes(a).model.has_model_identity


@pytest.mark.parametrize("field", ["messages", "tools", "response_format", "temperature"])
def test_a_null_top_level_field_is_one_the_sender_did_not_send(field):
    """SPEC 1.2: missing or null means the sender sent none, as clients that serialise an unset field as null mean."""
    body = {**BODY, field: None}
    without = {k: v for k, v in BODY.items() if k != field}
    assert pg.to_attributes(pg.observe(body)) == pg.to_attributes(pg.observe(without))


def test_emit_returns_the_attributes_when_there_is_no_tracer():
    attrs = pg.emit(read(), span=None)
    assert attrs["perigraph.status"] == "complete"


def test_emit_sets_every_attribute_on_a_span_and_survives_one_it_rejects():
    """One rejected attribute must not cost the rest of the record. The rejected key is the FIRST one emitted, so a reader
    that stopped on the first refusal instead of skipping it would lose everything after -- which a rejection on a late
    key would not have detected."""
    rejected = "perigraph.collector"

    class Span:
        def __init__(self):
            self.attrs = {}

        def set_attribute(self, key, value):
            if key == rejected:
                raise ValueError("this tracer dislikes this key")
            self.attrs[key] = value

    span = Span()
    attrs = pg.emit(read(), span=span)
    assert list(attrs)[1] == rejected, "the rejected key has to be early for this test to mean anything"
    assert rejected not in span.attrs
    assert set(attrs) - {rejected} == set(span.attrs), "everything except the rejected key should have been set"


# --- the golden fixtures both implementations must reproduce ---------------------------------------------------------------

FIXTURES = json.loads((ROOT / "spec" / "fixtures" / "identity.json").read_text(encoding="utf-8"))


def test_every_golden_identity_is_reproduced():
    """The fixtures exist because the second implementation could not have matched these from the spec alone: nothing said
    how the identity combines its parts, that it is truncated, or what bytes a string has. A divergence here is now a test
    failure on both sides rather than something discovered by comparing two records in production."""
    for case in FIXTURES["cases"]:
        r = collect.from_request(case["body"], collector="fixture", version="1")
        if case["identity"] is None:
            assert not r.has_identity, case["name"]
        else:
            assert r.identity == case["identity"], case["name"]
        got = next((p.content_digest for p in r.parts if p.kind == "instruction"), None)
        assert got == case["instruction_digest"], case["name"]


def test_a_non_ascii_instruction_is_covered_because_that_is_where_an_encoding_disagreement_shows():
    """A UTF-16 implementation would produce a different identity for every non-ASCII instruction while passing every test
    it wrote for itself, so the fixture set has to contain one."""
    assert any(any(ord(c) > 127 for c in m.get("content", ""))
               for case in FIXTURES["cases"] for m in case["body"]["messages"])


def test_the_fixtures_hold_no_parsed_digest():
    """A `parsed` digest is collector-local by spec, and the two reference implementations legitimately disagree on one.
    Pinning one here would freeze an accident of a serialiser."""
    assert all("instruction_digest" in case
               and set(case) <= {"name", "body", "identity", "instruction_digest", "request_template"}
               for case in FIXTURES["cases"])


# --- the prose and the normative JSON must not drift apart -----------------------------------------------------------------

SPEC_MD = (ROOT / "SPEC.md").read_text(encoding="utf-8")
RAW_SPEC = json.loads((ROOT / "spec" / "vocabularies.json").read_text(encoding="utf-8"))


def test_every_closed_vocabulary_value_appears_in_the_prose():
    """SPEC.md says the JSON wins where they disagree, and that is the right tie-break -- but a reader follows the prose,
    so a value the prose never mentions is a value nobody implements. This was not hypothetical: the digest rules, the
    collector-local rule and the ninth receiver obligation lived in the JSON for a commit while SPEC.md said nothing."""
    for section in ("parts", "model_parts", "answer_modes", "sourcing", "boundaries", "absence_reasons", "status",
                    "context_crossings", "tool_determinism", "billed_legs"):
        for value in RAW_SPEC[section]["values"]:
            assert value in SPEC_MD, f"{section}.{value} is in the vocabulary and not in SPEC.md"


def test_every_receiver_obligation_appears_in_the_prose():
    """Checked by the distinctive phrase rather than the whole sentence, because the prose is allowed to word it its own
    way -- what is not allowed is the prose being silent about a refusal that decides conformance."""
    markers = {
        "status is not complete": "status",
        "record with no harness identity": "no identifying part",
        "not_reachable": "not_reachable",
        "not model_visible": "model_visible",
        "missing different facts": "missing different facts",
        "different turn counts": "turn count",
        "context_partitioning is unrecorded": "context_partitioning",
        "two `parsed` digests produced by different collectors": "collector-local",
        "occasion and the tool declared determinism": "declared_deterministic",
        "sourcing is not loaded_by_us": "loaded_by_us",
        "distinct harness identities derived from them": "distinct harness identities derived from them",
        "more than one model identity": "more than one model identity",
        "do not carry that model identity": "do not carry that model identity",
        "two model identities produced by different collectors": "artifact identity",
    }
    obligations = RAW_SPEC["receiver_obligations"]["must_refuse"]
    assert len(obligations) == len(markers), (
        f"{len(obligations)} obligations and {len(markers)} markers; a new obligation needs a marker here and a sentence "
        f"in SPEC.md, and adding one is a breaking change under section 6")
    matched = set()
    for phrase, marker in markers.items():
        hits = [o for o in obligations if phrase in o]
        assert len(hits) == 1, f"{phrase!r} matches {len(hits)} obligations; a marker has to name exactly one"
        matched.add(hits[0])
        assert marker in SPEC_MD, f"SPEC.md never mentions {marker!r}, which decides conformance"
    assert matched == set(obligations), f"unmatched: {sorted(set(obligations) - matched)}"


def test_the_digest_rules_are_in_the_prose_because_they_are_what_interop_needs():
    for needle in ("sha256", "utf-8", "24", "U+000A"):
        assert needle in SPEC_MD, needle


def test_the_spec_declares_what_a_breaking_change_is():
    """A protocol whose compatibility rules are negotiable is a protocol two implementations disagree about quietly."""
    assert "## 7. Versioning" in SPEC_MD
    for needle in ("breaking", "spec_version"):
        assert needle in SPEC_MD, needle


# --- version 2: the model half ---------------------------------------------------------------------------------------

from perigraph import lineage as lin, model as mdl  # noqa: E402

MODEL_FIXTURES = json.loads((ROOT / "spec" / "fixtures" / "model_identity.json").read_text(encoding="utf-8"))


def _sha(text):
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _model(case):
    cp = mdl.checkpoint_digest([(p, _sha(t)) for p, t in case["files"].items()])
    return cp, mdl.loaded(checkpoint=cp, precision=mdl.precision_digest(case["precision"]),
                          runtime=mdl.runtime_digest(case["runtime"]), answer_mode=case["answer_mode"])


def test_every_model_fixture_reproduces():
    for case in MODEL_FIXTURES["cases"]:
        cp, m = _model(case)
        assert cp == case["checkpoint_digest"], case["name"]
        assert mdl.precision_digest(case["precision"]) == case["precision_digest"], case["name"]
        assert mdl.runtime_digest(case["runtime"]) == case["runtime_digest"], case["name"]
        assert m.model_identity == case["model_identity"], case["name"]
        assert m.artifact_identity == case["artifact_identity"], case["name"]


@pytest.mark.parametrize("precision", MODEL_FIXTURES["refused_precision"]["cases"])
def test_every_unresolved_precision_fixture_is_refused(precision):
    with pytest.raises(Exception):
        mdl.precision_digest(precision)


def test_int8_at_load_changes_the_model_identity_and_not_the_artifact_identity():
    """R6: dynamic int8 left the stored bytes unchanged and agreed with the GPU on 33-40 % of labels. Version 1 gave both
    one identity; here the model identities differ and the artifact identities agree, which is what a trainer needs."""
    bf16, int8 = (_model(c)[1] for c in MODEL_FIXTURES["cases"][:2])
    assert bf16.model_identity != int8.model_identity
    assert bf16.artifact_identity == int8.artifact_identity


def test_a_retrain_with_the_same_script_and_seed_is_a_different_artifact():
    """R12 -> R13: same recipe, 93.4 % label agreement. Different bytes, so a different artifact and model identity."""
    a = mdl.checkpoint_digest([("model.safetensors", _sha("run 1"))])
    b = mdl.checkpoint_digest([("model.safetensors", _sha("run 2"))])
    assert a != b


def test_option_scores_and_generated_text_are_different_models():
    """R5-R10 against R12: a score-trained student generated '1111'. The answer mode keys the model identity."""
    case = MODEL_FIXTURES["cases"][0]
    cp = case["checkpoint_digest"]
    a = mdl.loaded(checkpoint=cp, precision=case["precision_digest"], runtime=case["runtime_digest"],
                   answer_mode="generated_text")
    b = mdl.loaded(checkpoint=cp, precision=case["precision_digest"], runtime=case["runtime_digest"],
                   answer_mode="option_scores")
    assert a.model_identity != b.model_identity and a.artifact_identity == b.artifact_identity


def test_a_runtime_change_changes_the_model_identity():
    """R14: the serving image lost packages and the teacher re-answered 97 of 100 the same."""
    case = MODEL_FIXTURES["cases"][0]
    a = _model(case)[1]
    b = mdl.loaded(checkpoint=case["checkpoint_digest"], precision=case["precision_digest"],
                   runtime=mdl.runtime_digest({**case["runtime"], "torch": "2.15.1"}), answer_mode=case["answer_mode"])
    assert a.model_identity != b.model_identity


def test_no_model_identity_unless_all_four_parts_are_loaded_by_us():
    case = MODEL_FIXTURES["cases"][0]
    parts = list(_model(case)[1].parts)
    parts[1] = mdl.ModelPart("precision", "pushed_by_owner", case["precision_digest"])
    m = mdl.Model(parts=tuple(parts), reaches=vocab.MODEL_PARTS)
    assert not m.has_model_identity and m.has_artifact_identity
    with pytest.raises(vocab.Unidentified, match="precision"):
        m.model_identity


def test_a_cached_digest_is_pulled_and_needs_its_age():
    with pytest.raises(vocab.Unidentified, match="lag"):
        mdl.ModelPart("checkpoint", "pulled_by_us", "a" * 64)
    assert not mdl.ModelPart("checkpoint", "pulled_by_us", "a" * 64, read_lag_seconds=3600).identifying


def test_a_request_never_carries_a_model_part_and_a_harness_part_is_never_loaded():
    with pytest.raises(vocab.Unidentified, match="weights"):
        mdl.ModelPart("checkpoint", "in_the_request", "a" * 64)
    with pytest.raises(vocab.Unidentified, match="harness part"):
        rec.Part(kind="instruction", sourcing="loaded_by_us", content_digest=rec.digest(TERSE))


def test_unresolved_precision_is_refused_rather_than_hashed():
    with pytest.raises(vocab.Unidentified, match="unresolved"):
        mdl.precision_digest({"dtype": "auto"})


def test_a_provider_model_has_no_identity_and_stays_admissible():
    m = mdl.behind_a_provider("claude-haiku-4-5")
    r = rec.Record(manifest=read().manifest, parts=read().parts, absences=read().absences, model=m)
    assert not m.has_model_identity and not m.has_artifact_identity
    assert r.admissible_to_a_verdict()


def test_checkpoint_paths_are_normative():
    for bad in ("/abs", "a/../b", "a\tb", "a\nb", "a\\b", "./a"):
        with pytest.raises(vocab.Unidentified):
            mdl.checkpoint_digest([(bad, "a" * 64)])
    a = mdl.checkpoint_digest([("b", "a" * 64), ("a", "b" * 64)])
    assert a == mdl.checkpoint_digest([("a", "b" * 64), ("b", "a" * 64)])


def test_the_model_half_round_trips_over_the_wire_and_a_forged_identity_is_refused():
    case = MODEL_FIXTURES["cases"][2]
    base = read()
    r = rec.Record(manifest=base.manifest, parts=base.parts, absences=base.absences, model=_model(case)[1])
    attrs = wire.to_attributes(r)
    assert attrs["perigraph.model_identity"] == case["model_identity"]
    assert attrs["perigraph.artifact_identity"] == case["artifact_identity"]
    back = wire.from_attributes(attrs)
    assert back.model.model_identity == case["model_identity"]
    with pytest.raises(vocab.Unidentified, match="does not follow"):
        wire.from_attributes({**attrs, "perigraph.model_identity": "0" * 24})


def test_a_version_1_record_is_refused_by_a_version_2_reader():
    attrs = wire.to_attributes(read())
    with pytest.raises(vocab.Unidentified, match="spec_version"):
        wire.from_attributes({**attrs, "perigraph.spec_version": 1})


class _R:
    def __init__(self, model, collector="c", version="1"):
        self.model = model
        self.manifest = rec.Manifest(collector=collector, version=version, reaches=())


def test_receiver_refusals_over_model_identities():
    a, b = (_model(c)[1] for c in MODEL_FIXTURES["cases"][:2])
    mdl.refuse_mixed_model_identities({"student": [_R(a), _R(a)]})
    with pytest.raises(vocab.Unidentified, match="model identities"):
        mdl.refuse_mixed_model_identities({"student": [_R(a), _R(b)]})
    with pytest.raises(vocab.Unidentified, match="model identities"):
        mdl.refuse_mixed_model_identities({"student": [_R(a), _R(None)]})
    mdl.refuse_unbound_claim(a.model_identity, [_R(a)])
    with pytest.raises(vocab.Unidentified, match="something else"):
        mdl.refuse_unbound_claim(a.model_identity, [_R(b)])
    mdl.refuse_cross_collector_model_comparison(_R(a), _R(b))
    with pytest.raises(vocab.Unidentified, match="collector-local"):
        mdl.refuse_cross_collector_model_comparison(_R(a), _R(b, version="2"))


# --- version 2: lineage ------------------------------------------------------------------------------------------------

ROOT_ID, CHILD_ID, GRAND_ID = "1" * 24, "2" * 24, "3" * 24
CERT = "c" * 64


def test_lineage_is_closed_and_subtract_only():
    root = lin.load({"spec_version": 3, "subject": ROOT_ID, "parent": "none", "method": "pretrained"})
    child = lin.load({"spec_version": 3, "subject": CHILD_ID, "parent": ROOT_ID, "method": "sft",
                      "sets": [{"role": "trained_on", "digest": CERT}]})
    grand = lin.load({"spec_version": 3, "subject": GRAND_ID, "parent": CHILD_ID, "method": "rl",
                      "signal": {"digest": "d" * 64}})
    docs = {d.subject: d for d in (root, child, grand)}
    # a quantised or RL child lists no sets, and its parent trained on the certification set: the chain finds it
    assert lin.trained_on_anywhere(GRAND_ID, docs, CERT) is True
    assert lin.trained_on_anywhere(GRAND_ID, docs, "e" * 64) is False
    # a missing ancestor is unknown, never clean
    assert lin.trained_on_anywhere(GRAND_ID, {GRAND_ID: grand}, "e" * 64) is None
    # a lineage about another artifact is read as absent
    assert lin.about(child, ROOT_ID) is None and lin.about(child, CHILD_ID) is child
    with pytest.raises(vocab.Unidentified, match="not one of"):
        lin.load({"spec_version": 3, "subject": CHILD_ID, "parent": ROOT_ID, "method": "sft",
                  "sets": [{"role": "excluded", "digest": CERT}]})
    with pytest.raises(vocab.Unidentified, match="signal"):
        lin.load({"spec_version": 3, "subject": CHILD_ID, "parent": ROOT_ID, "method": "distillation"})
    with pytest.raises(vocab.Unidentified, match="not lineage fields"):
        lin.load({"spec_version": 3, "subject": CHILD_ID, "parent": ROOT_ID, "method": "sft", "excluded": []})


def test_a_dtype_named_auto_is_unresolved_as_a_value_of_auto_is():
    """SPEC 9: torch_dtype="auto" in a configuration is a question, whether it lands in the name or the value."""
    from perigraph import model as pm
    for fields in ({"dtype.auto": "1", "quantisation": "none", "device": "cuda"},
                   {"dtype.bfloat16": "auto", "quantisation": "none", "device": "cuda"},
                   {"dtype.bfloat16": "1", "quantisation": "AUTO", "device": "cuda"}):
        with pytest.raises(pg.Unidentified):
            pm.precision_digest(fields)


def test_a_lone_surrogate_in_a_template_fails_the_part_and_withdraws_the_identity():
    """Not in the shared fixtures: a JSON reader that replaces a lone surrogate with U+FFFD (Go's does) cannot make this
    check, and the binding says such a collector is not conformant for that body rather than pretending it is."""
    body = {"messages": [{"role": "system", "content": "Terse."}, {"role": "user", "content": "\ud800 x"}],
            "perigraph_template": {"messages": [{"role": "system"}, {"role": "user", "fixed": ["\ud800 ", ""]}]}}
    r = pg.from_request(body, collector="t", version="1")
    assert [a.reason for a in r.absences if a.kind == "request_template"] == ["extraction_failed"]
    assert not r.has_identity


def test_a_template_beside_an_instruction_splits_and_alone_identifies_nothing():
    instr = {"role": "system", "content": "Terse."}
    plain = pg.from_request({"messages": [instr, {"role": "user", "content": "Q: x"}]}, collector="t", version="1")
    wrapped = pg.from_request({"messages": [instr, {"role": "user", "content": "Q: x"}], "perigraph_template": {
        "messages": [{"role": "system"}, {"role": "user", "fixed": ["Q: ", ""]}]}}, collector="t", version="1")
    alone = pg.from_request({"messages": [{"role": "user", "content": "Q: x"}], "perigraph_template": {
        "messages": [{"role": "user", "fixed": ["Q: ", ""]}]}}, collector="t", version="1")
    assert plain.identity != wrapped.identity
    assert any(p.kind == "request_template" for p in alone.parts) and not alone.has_identity


def test_the_white_space_set_is_the_one_the_vocabulary_lists():
    """The emptiness test decides whether a part exists, and each language's own trim strips a different set."""
    listed = {chr(c) for c in vocab._SPEC["white_space"]["code_points"]}
    assert set(rec.WHITE_SPACE) == listed
    assert all(rec.blank(ch) for ch in listed) and not rec.blank("\ufeff") and not rec.blank("\u001f")
