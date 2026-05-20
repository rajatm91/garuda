import json
from pathlib import Path

from os_llm_scan.manifest import Manifest, save_manifest
from os_llm_scan.runner import run_report


def _setup_scan(tmp_path: Path) -> Path:
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "01_metadata.json").write_text(json.dumps({
        "id": "meta-llama/Foo", "sha": "abc" * 20, "license": "llama-3",
        "siblings": [], "tags": []}))
    (tmp_path / "raw" / "02_sha256.json").write_text(json.dumps({"files": []}))
    (tmp_path / "raw" / "03_format_inventory.json").write_text(json.dumps({
        "safetensors": [], "unsafe_format": [], "other": [],
        "counts": {"safetensors": 0, "unsafe_format": 0, "other": 0}}))
    m = Manifest.create(scan_dir=tmp_path, repo="meta-llama/Foo", revision="main",
                        source_mode="hf", source_abs_path=None)
    save_manifest(m)
    return tmp_path


def test_run_report_writes_both_files(tmp_path):
    scan = _setup_scan(tmp_path)
    sarif_path, html_path = run_report(scan)
    assert sarif_path.exists() and html_path.exists()
    log = json.loads(sarif_path.read_text())
    assert log["version"] == "2.1.0"
