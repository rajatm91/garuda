import json
from pathlib import Path

from garuda.util.io import load_json, write_json, write_stub


def test_load_json_returns_none_for_missing(tmp_path: Path):
    assert load_json(tmp_path / "missing.json") is None


def test_load_json_returns_none_for_empty(tmp_path: Path):
    p = tmp_path / "e.json"; p.write_text("")
    assert load_json(p) is None


def test_load_json_returns_none_for_invalid(tmp_path: Path):
    p = tmp_path / "b.json"; p.write_text("{nope")
    assert load_json(p) is None


def test_load_json_returns_parsed(tmp_path: Path):
    p = tmp_path / "ok.json"; p.write_text('{"a": 1}')
    assert load_json(p) == {"a": 1}


def test_write_json_creates_parent(tmp_path: Path):
    p = tmp_path / "nested" / "out.json"
    write_json(p, {"a": 1})
    assert json.loads(p.read_text()) == {"a": 1}


def test_write_stub_writes_skip_reason(tmp_path: Path):
    p = tmp_path / "stub.json"
    write_stub(p, "syft not installed")
    assert json.loads(p.read_text()) == {"skipped": "syft not installed"}
