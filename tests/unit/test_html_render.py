import json

from garuda.report.html import build_html


def _scan(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "raw" / "01_metadata.json").write_text(json.dumps({
        "id": "meta-llama/Foo", "sha": "abc" * 20, "license": "llama-3",
        "siblings": [], "tags": []}))
    (tmp_path / "raw" / "02_sha256.json").write_text(json.dumps({"files": []}))
    (tmp_path / "raw" / "03_format_inventory.json").write_text(json.dumps({
        "safetensors": [], "unsafe_format": [], "other": [],
        "counts": {"safetensors": 0, "unsafe_format": 0, "other": 0}}))
    return tmp_path


def test_html_renders_with_anchors(tmp_path):
    scan = _scan(tmp_path)
    html = build_html(scan, sarif={"runs": []})
    for anchor in ("#summary", "#model", "#integrity", "#findings", "#licenses", "#attestation"):
        assert anchor in html
    assert "modelaudit" in html.lower() or "modelaudit" in html
    assert "<!doctype html>" in html.lower() or "<!DOCTYPE html>" in html
