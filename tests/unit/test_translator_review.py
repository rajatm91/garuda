import json
from pathlib import Path

from garuda.report.translators.review import build_review_run


def _scan(tmp_path: Path) -> Path:
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "01_metadata.json").write_text(json.dumps({
        "id": "meta-llama/Foo", "sha": "abc123" * 10, "license": "llama-3",
        "siblings": [{"name": "x"}] * 5, "tags": ["llama"]}))
    (tmp_path / "raw" / "02_sha256.json").write_text(json.dumps(
        {"files": [{"path": "a", "size": 1, "sha256": "x" * 64}]}))
    (tmp_path / "raw" / "03_format_inventory.json").write_text(json.dumps({
        "safetensors": [], "unsafe_format": [{"path": "m.bin", "size": 1, "sha256": "x" * 64}],
        "other": [], "counts": {"safetensors": 0, "unsafe_format": 1, "other": 0}}))
    return tmp_path


def test_review_emits_metadata_and_unsafe_results(tmp_path):
    run = build_review_run(_scan(tmp_path), is_local_source=False)
    ids = {r["ruleId"] for r in run["results"]}
    assert {"OLR001", "OLR002", "OLR003", "OLR004"} <= ids


def test_review_emits_local_source_note(tmp_path):
    run = build_review_run(_scan(tmp_path), is_local_source=True)
    assert any(r["ruleId"] == "OLR006" for r in run["results"])
