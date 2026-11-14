#!/usr/bin/env python3
"""Generate the JSON Schemas in spec/schema/ from spec/vocabularies.json.

The schema is generated rather than written because a second hand-kept copy of the closed vocabularies is how two
implementations drift (SPEC section 0.2). CI regenerates it and fails when the committed file differs.

    python tools/gen_schema.py           write the schemas
    python tools/gen_schema.py --check   exit 1 if a committed schema is not what the vocabulary generates

record.schema.json is the perigraph.* attributes of one record, lineage.schema.json a lineage document (section 10),
and vocabularies.schema.json the shape of spec/vocabularies.json itself.

What a JSON Schema can say is the shape: required keys, closed values, which keys go together. What it cannot say --
that an identity equals the digest of the parts it claims to be over, that a manifest is contradicted -- is checked by
the conformance cases under conformance/cases/.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
VOCAB = json.loads((ROOT / "spec" / "vocabularies.json").read_text(encoding="utf-8"))
SCHEMA_DIR = ROOT / "spec" / "schema"
P = VOCAB["namespace"]
HEX64 = "^[0-9a-f]{64}$"
HEX24 = "^[0-9a-f]{%d}$" % VOCAB["digest"]["identity_length"]


def esc(name: str) -> str:
    return re.escape(name)


def names_list_pattern(names: list[str]) -> str:
    alt = "|".join(esc(n) for n in names)
    return f"^(?:(?:{alt})?)(?:,(?:(?:{alt})?))*$"


def part_rules(prefix: str, absent_prefix: str, names: list[str], sourcing: list[str], with_boundary: bool) -> tuple[dict, list]:
    props: dict = {}
    rules: list = []
    blames = VOCAB["absence_reasons"]["blames"]
    collector_blamed = [r for r, who in blames.items() if who == VOCAB["absence_reasons"]["detail_required_when_blames"]]
    for n in names:
        b = f"{P}.{prefix}.{n}"
        a = f"{P}.{absent_prefix}.{n}"
        props[f"{b}.sourcing"] = {"enum": sourcing}
        props[f"{b}.digest"] = {"type": "string", "pattern": HEX64}
        props[f"{b}.label"] = {"type": "string"}
        props[f"{b}.read_lag_seconds"] = {"type": "number", "minimum": 0}
        if with_boundary:
            props[f"{b}.boundary"] = {"enum": VOCAB["boundaries"]["values"]}
        props[f"{a}.reason"] = {"enum": VOCAB["absence_reasons"]["values"]}
        props[f"{a}.detail"] = {"type": "string", "minLength": 1}
        rules.append({"$comment": f"{n}: a part is held or absent, never both",
                      "not": {"required": [f"{b}.sourcing", f"{a}.reason"]}})
        rules.append({"$comment": f"{n}: a read lag exactly when pulled_by_us",
                      "if": {"required": [f"{b}.sourcing"], "properties": {f"{b}.sourcing": {"const": "pulled_by_us"}}},
                      "then": {"required": [f"{b}.read_lag_seconds"]},
                      "else": {"not": {"required": [f"{b}.read_lag_seconds"]}}})
        rules.append({"$comment": f"{n}: digest, label and lag belong to a held part",
                      "if": {"not": {"required": [f"{b}.sourcing"]}},
                      "then": {"not": {"anyOf": [{"required": [f"{b}.digest"]}, {"required": [f"{b}.label"]}]
                                       + ([{"required": [f"{b}.boundary"]}] if with_boundary else [])}}})
        rules.append({"$comment": f"{n}: a part that is not observable has no bytes, so it has no digest",
                      "if": {"required": [f"{b}.sourcing"], "properties": {f"{b}.sourcing": {"const": "not_observable"}}},
                      "then": {"not": {"required": [f"{b}.digest"]}}})
        if n == "answer_mode":
            rules.append({"$comment": "answer_mode: a digested answer mode is labelled with its value (section 9)",
                          "if": {"required": [f"{b}.digest"]},
                          "then": {"required": [f"{b}.label"],
                                   "properties": {f"{b}.label": {"enum": VOCAB["answer_modes"]["values"]}}}})
        if with_boundary:
            rules.append({"$comment": f"{n}: a boundary exactly when there is a digest",
                          "if": {"required": [f"{b}.digest"]},
                          "then": {"required": [f"{b}.boundary"]},
                          "else": {"not": {"required": [f"{b}.boundary"]}}})
        rules.append({"$comment": f"{n}: a detail exactly when the absence blames the collector",
                      "if": {"required": [f"{a}.reason"], "properties": {f"{a}.reason": {"enum": collector_blamed}}},
                      "then": {"required": [f"{a}.detail"]},
                      "else": {"not": {"required": [f"{a}.detail"]}}})
    return props, rules


def build() -> dict:
    parts = VOCAB["parts"]["values"]
    model_parts = VOCAB["model_parts"]["values"]
    sourcing = VOCAB["sourcing"]["values"]
    harness_sourcing = [s for s in sourcing if s != "loaded_by_us"]
    model_sourcing = [s for s in sourcing if s != "in_the_request"]
    props = {
        f"{P}.spec_version": {"const": VOCAB["spec_version"]},
        f"{P}.collector": {"type": "string", "minLength": 1},
        f"{P}.collector_version": {"type": "string", "minLength": 1},
        f"{P}.collector_reaches": {"type": "string", "pattern": names_list_pattern(parts)},
        f"{P}.model_reaches": {"type": "string", "pattern": names_list_pattern(model_parts)},
        f"{P}.status": {"enum": VOCAB["status"]["values"]},
        f"{P}.harness_identity": {"type": "string", "pattern": HEX24},
        f"{P}.model_identity": {"type": "string", "pattern": HEX24},
        f"{P}.artifact_identity": {"type": "string", "pattern": HEX24},
    }
    hp, hr = part_rules("part", "absent", parts, harness_sourcing, True)
    mp, mr = part_rules("model", "model_absent", model_parts, model_sourcing, False)
    props.update(hp)
    props.update(mp)
    known_parts = "|".join(esc(n) for n in parts)
    known_model = "|".join(esc(n) for n in model_parts)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/littlemex/perigraph/blob/main/spec/schema/record.schema.json",
        "title": f"perigraph record, spec_version {VOCAB['spec_version']} (generated from spec/vocabularies.json)",
        "description": ("The perigraph.* attributes of one record. Attributes outside the perigraph. prefix are not "
                        "constrained, because a record rides on a span that carries others. This schema checks shape "
                        "only; identity recomputation and manifest contradiction are conformance cases."),
        "type": "object",
        "required": [f"{P}.spec_version", f"{P}.collector", f"{P}.collector_version", f"{P}.collector_reaches",
                     f"{P}.status"],
        "properties": props,
        "patternProperties": {
            f"^{esc(P)}\\.ext\\.[^.]+\\..+$": {"type": ["string", "number", "boolean"]},
            f"^{esc(P)}\\.(?:part|absent)\\.(?!(?:{known_parts})\\.)": False,
            f"^{esc(P)}\\.(?:model|model_absent)\\.(?!(?:{known_model})\\.)": False,
        },
        "allOf": hr + mr,
    }


def build_lineage() -> dict:
    lin = VOCAB["lineage"]
    ident = {"type": "string", "pattern": HEX24}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/littlemex/perigraph/blob/main/spec/schema/lineage.schema.json",
        "title": f"perigraph lineage document, spec_version {VOCAB['spec_version']} (generated from spec/vocabularies.json)",
        "description": ("One trainer's account of how one artifact came to be (SPEC section 10). Shape only: that the "
                        "parent differs from the subject, and what an incomplete chain means, are a receiver's rules."),
        "type": "object",
        "required": ["spec_version", "subject", "parent", "method"],
        "additionalProperties": False,
        "properties": {
            "spec_version": {"const": VOCAB["spec_version"]},
            "subject": ident,
            "parent": {"oneOf": [ident, {"const": "none"}]},
            "method": {"enum": lin["methods"]},
            "sets": {"type": "array", "items": {
                "type": "object", "required": ["role", "digest"], "additionalProperties": False,
                "properties": {"role": {"enum": lin["set_roles"]}, "digest": {"type": "string", "pattern": HEX64}}}},
            "signal": {"type": "object", "minProperties": 1, "maxProperties": 1, "additionalProperties": False,
                       "properties": {"artifact_identity": ident, "digest": {"type": "string", "pattern": HEX64},
                                      "label": {"type": "string", "minLength": 1}}},
            "trainer": {"type": "string"},
        },
        "allOf": [
            {"$comment": "a pretrained artifact has no parent, and only a pretrained one has none",
             "if": {"properties": {"method": {"const": "pretrained"}}},
             "then": {"properties": {"parent": {"const": "none"}}},
             "else": {"properties": {"parent": ident}}},
            {"$comment": "distillation and rl name what their signal came from",
             "if": {"properties": {"method": {"enum": ["distillation", "rl"]}}},
             "then": {"required": ["signal"]}},
        ],
    }


def build_vocabularies() -> dict:
    closed = {"type": "object", "required": ["values"],
              "properties": {"values": {"type": "array", "items": {"type": "string"}, "uniqueItems": True, "minItems": 1}}}
    keys = [k for k, val in VOCAB.items() if isinstance(val, dict) and "values" in val]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://github.com/littlemex/perigraph/blob/main/spec/schema/vocabularies.schema.json",
        "title": "The shape of spec/vocabularies.json (generated from it)",
        "description": ("Every closed vocabulary is an object whose `values` are unique strings. This schema is generated "
                        "from the file it describes, so it catches a copy that lost a vocabulary or broke one's shape, "
                        "not a value added in the wrong place -- that is what the conformance cases are for."),
        "type": "object",
        "required": ["spec_version", "namespace", "digest", "attributes", "receiver_obligations", "lineage"] + keys,
        "properties": {
            "spec_version": {"type": "integer"},
            "namespace": {"const": VOCAB["namespace"]},
            **{k: closed for k in keys},
            "receiver_obligations": {"type": "object", "required": ["must_refuse", "must_not_refuse"],
                                     "properties": {"must_refuse": {"type": "array", "items": {"type": "string"}},
                                                    "must_not_refuse": {"type": "array", "items": {"type": "string"}}}},
        },
    }


OUTPUTS = {"record.schema.json": build, "lineage.schema.json": build_lineage,
           "vocabularies.schema.json": build_vocabularies}


def main() -> int:
    stale = []
    for name, fn in OUTPUTS.items():
        path = SCHEMA_DIR / name
        text = json.dumps(fn(), indent=2, ensure_ascii=False) + "\n"
        if "--check" in sys.argv:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.write_text(text, encoding="utf-8")
            print(f"wrote spec/schema/{name}")
    if stale:
        print(f"{stale} are not what spec/vocabularies.json generates: run tools/gen_schema.py")
        return 1
    if "--check" in sys.argv:
        print("every schema matches the vocabulary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
