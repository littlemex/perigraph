import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from replay_hops import hop_row  # noqa: E402


def test_a_dispatch_receipt_becomes_a_hop_row():
    rec = {"id": "r", "request_id": "q", "route_diagnostics": {"prepared_dispatch": {
        "version": 1, "wire_format": "openai.chat.v1", "sha256": "ab" * 32, "byte_length": 172}}}
    assert hop_row(rec) == {"format": 1, "hop": "vsr", "request_id": "q", "attempt": "r", "body_sha256": "ab" * 32,
                            "body_bytes": 172}


def test_a_record_without_a_receipt_has_no_digest(tmp_path):
    f = tmp_path / "x.json"
    f.write_text(json.dumps([{"id": "c", "request_id": "q2", "route_diagnostics": {}}]))
    out = subprocess.run([sys.executable, str(HERE / "replay_hops.py"), str(f)], capture_output=True, text=True,
                         check=True).stdout
    assert json.loads(out)["body_sha256"] == ""
