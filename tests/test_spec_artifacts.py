"""The machine-readable spec: the generated schemas and registry are current, the examples mean what they say, and the
conformance runner both passes a conforming implementation and fails a non-conforming one."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import textwrap

import jsonschema
import pytest

from perigraph import lineage, wire

ROOT = pathlib.Path(__file__).resolve().parents[1]
RECORD = jsonschema.Draft202012Validator(json.loads((ROOT / "spec/schema/record.schema.json").read_text()))
LINEAGE = jsonschema.Draft202012Validator(json.loads((ROOT / "spec/schema/lineage.schema.json").read_text()))
EXAMPLES = sorted((ROOT / "spec/examples").glob("*.json"))


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)


@pytest.mark.parametrize("tool", ["tools/gen_schema.py", "tools/requirements.py"])
def test_generated_files_are_current(tool):
    r = run(tool, "--check")
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_schema_is_a_valid_schema_and_the_vocabulary_fits_its_own():
    for name in ("record", "lineage", "vocabularies"):
        jsonschema.Draft202012Validator.check_schema(json.loads((ROOT / f"spec/schema/{name}.schema.json").read_text()))
    jsonschema.validate(json.loads((ROOT / "spec/vocabularies.json").read_text()),
                        json.loads((ROOT / "spec/schema/vocabularies.schema.json").read_text()))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_examples_validate_and_mean_what_they_say(path):
    doc = json.loads(path.read_text())
    ids = {r["id"] for r in json.loads((ROOT / "spec/requirements.json").read_text())["requirements"]}
    assert doc["illustrates"] and set(doc["illustrates"]) <= ids
    if "attributes" in doc:
        assert not list(RECORD.iter_errors(doc["attributes"]))
        record = wire.from_attributes(doc["attributes"])
        got = "admitted" if record.admissible_to_a_verdict() else "refused"
        assert {"outcome": "stored", "verdict": got} == doc["receiver"]
    for d in doc.get("lineage", []):
        assert not list(LINEAGE.iter_errors(d))
        lineage.load(d)


def test_the_lineage_schema_refuses_what_the_reader_refuses():
    bad = [{"spec_version": 2, "subject": "a" * 24, "parent": "b" * 24, "method": "pretrained"},
           {"spec_version": 2, "subject": "a" * 24, "parent": "none", "method": "sft"},
           {"spec_version": 2, "subject": "a" * 24, "parent": "b" * 24, "method": "rl"},
           {"spec_version": 2, "subject": "a" * 24, "parent": "b" * 24, "method": "sft", "sets": [{"role": "excluded", "digest": "c" * 64}]},
           {"spec_version": 2, "subject": "a" * 24, "parent": "b" * 24, "method": "sft", "notes": "x"}]
    for d in bad:
        assert list(LINEAGE.iter_errors(d)), d
        with pytest.raises(Exception):
            lineage.load(d)


def test_the_runner_passes_the_reference_implementation(tmp_path):
    r = run("tools/conform.py", "--adapter", f"{sys.executable} conformance/adapters/python_adapter.py",
            "--json", str(tmp_path / "out.json"))
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr
    out = json.loads((tmp_path / "out.json").read_text())
    assert out["schema_checked"] and out["roles"] == ["collector", "stamper", "receiver"]


def test_the_runner_fails_a_receiver_that_admits_everything(tmp_path):
    adapter = tmp_path / "admit_all.py"
    adapter.write_text(textwrap.dedent("""
        import json, sys
        for line in sys.stdin:
            req = json.loads(line)
            reply = {"name": "admits everything", "roles": ["receiver"]} if req["op"] == "describe" else \\
                    {"outcome": "stored", "verdict": "admitted"}
            print(json.dumps({"id": req["id"], **reply}), flush=True)
    """))
    r = run("tools/conform.py", "--adapter", f"{sys.executable} {adapter}")
    assert r.returncode == 1
    cases = json.loads((ROOT / "conformance/cases/receiver.json").read_text())["cases"]
    should_fail = sum(1 for c in cases if c["expect"] != {"outcome": "stored", "verdict": "admitted"})
    assert r.stdout.count("FAIL  receiver/") == should_fail


def test_the_jsonl_binding_example_is_a_valid_admissible_record():
    text = (ROOT / "spec/bindings/jsonl.md").read_text()
    line = text.split("```json\n", 1)[1].split("\n```", 1)[0]
    attrs = json.loads(line)
    assert not list(RECORD.iter_errors(attrs))
    assert wire.from_attributes(attrs).admissible_to_a_verdict()


def test_the_readme_record_is_a_subset_of_what_the_quickstart_prints():
    import re
    out = subprocess.run([sys.executable, "examples/quickstart.py"], cwd=ROOT, capture_output=True, text=True,
                         check=True).stdout
    printed = json.loads(out[:out.rindex("}") + 1])
    shown = json.loads(re.search(r"```json\n(\{.*?\})\n```", (ROOT / "README.md").read_text(), re.S).group(1))
    assert {k: printed.get(k) for k in shown} == shown
    assert f"harness identity: {printed['perigraph.harness_identity']}" in (ROOT / "README.md").read_text()
