import json
from pathlib import Path

from os_llm_scan.manifest import Manifest
from os_llm_scan.report.html import build_html


def _scan_with_evaluation(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "01_metadata.json").write_text(json.dumps({
        "id":"meta-llama/Foo","sha":"abc"*20,"license":"llama-3","siblings":[],"tags":[]}))
    (tmp_path / "raw" / "02_sha256.json").write_text(json.dumps({"files":[]}))
    (tmp_path / "raw" / "03_format_inventory.json").write_text(json.dumps({
        "safetensors":[],"unsafe_format":[],"other":[],
        "counts":{"safetensors":0,"unsafe_format":0,"other":0}}))
    (tmp_path / "raw" / "13_eval_summary.json").write_text(json.dumps({
        "policy_sha256":"deadbeef",
        "categories":{
            "prompt_injection":{"engine":"garak","probes_run":100,"failures":3,
                "failure_rate":0.03,
                "thresholds":{"error":0.05,"warning":0.01},
                "verdict":"warning","examples":[]},
        },
        "overall_verdict":"warning",
    }))
    return tmp_path


def test_html_includes_gate_verdict_pill(tmp_path):
    scan = _scan_with_evaluation(tmp_path)
    m = Manifest.create(scan_dir=scan, repo="meta-llama/Foo", revision="main",
                        source_mode="hf", source_abs_path=None)
    html = build_html(scan, sarif={"runs":[]}, manifest=m)
    assert "WARNING" in html.upper() or "warning" in html
    assert "PROMPT_INJECTION" in html.upper() or "prompt_injection" in html
    assert "id=\"eval\"" in html or "id='eval'" in html


def test_html_no_eval_summary_uses_placeholder(tmp_path):
    # 01-03 only, no 13
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "01_metadata.json").write_text(json.dumps({
        "id":"x","sha":"a"*40,"license":"apache-2.0","siblings":[],"tags":[]}))
    (tmp_path / "raw" / "02_sha256.json").write_text(json.dumps({"files":[]}))
    (tmp_path / "raw" / "03_format_inventory.json").write_text(json.dumps({
        "safetensors":[],"unsafe_format":[],"other":[],
        "counts":{"safetensors":0,"unsafe_format":0,"other":0}}))
    m = Manifest.create(scan_dir=tmp_path, repo="x", revision="main",
                        source_mode="hf", source_abs_path=None)
    html = build_html(tmp_path, sarif={"runs":[]}, manifest=m)
    assert "id=\"eval\"" in html or "id='eval'" in html
    assert "pending" in html.lower() or "behavioural" in html.lower()
