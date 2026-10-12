import json
from pathlib import Path

from garuda.report.translators.modelaudit import build_modelaudit_run

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "raw" / "04_modelaudit.with_findings.json"


def test_emits_one_result_per_issue(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "04_modelaudit.json").write_text(FIXTURE.read_text())
    run = build_modelaudit_run(tmp_path)
    assert run is not None
    levels = [r["level"] for r in run["results"]]
    assert "error" in levels and "warning" in levels
    assert {r["ruleId"] for r in run["results"]} == {"MODELAUDIT-MA-001", "MODELAUDIT-MA-007"}


def test_returns_none_on_missing_file(tmp_path):
    assert build_modelaudit_run(tmp_path) is None


def test_returns_none_on_skip_stub(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "04_modelaudit.json").write_text('{"skipped":"x"}')
    assert build_modelaudit_run(tmp_path) is None


def test_real_020x_shape_and_incomplete_checks(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "04_modelaudit.json").write_text(json.dumps({
        "files_scanned": 2, "has_errors": True,
        "issues": [{"message": "URL detected in model: https://x", "severity": "warning",
                    "location": "/w/README.md", "details": {"type": "url_detected"}}],
        "checks": [
            {"name": "Shard Scan Pinning", "status": "failed", "message": "Unable to bind shard",
             "location": "/w/model-00001.safetensors",
             "details": {"error": "descriptor-bound shard pinning unavailable",
                         "analysis_incomplete": True, "scan_outcome": "inconclusive"}},
            {"name": "Pickle Check", "status": "passed", "details": {}},
        ],
    }))
    run = build_modelaudit_run(tmp_path)
    assert run is not None
    got = [(r["ruleId"], r["level"], r["message"]["text"][:21]) for r in run["results"]]
    assert got == [("MODELAUDIT-url_detected", "warning", "URL detected in model"),  # not on disk
                   ("MODELAUDIT-INCOMPLETE", "warning", "Shard Scan Pinning: U")]
    assert run["invocations"][0]["executionSuccessful"] is False


def test_incomplete_on_docs_is_note_on_weights_is_warning(tmp_path):
    (tmp_path / "raw").mkdir(); (tmp_path / "weights").mkdir()
    (tmp_path / "weights" / "README.md").write_text("docs")
    chk = lambda loc: {"name": "C", "status": "failed", "message": "m", "location": loc,
                       "details": {"analysis_incomplete": True}}
    (tmp_path / "raw" / "04_modelaudit.json").write_text(json.dumps({
        "files_scanned": 3, "issues": [],
        "checks": [chk("/w/weights/README.md"), chk("/w/weights/model-1.safetensors"),
                   chk("/w/weights/config.json")]}))
    run = build_modelaudit_run(tmp_path)
    assert run is not None
    assert [r["level"] for r in run["results"]] == ["note", "warning", "warning"]


def test_found_in_relative_path_line_and_doc_url_downgrade(tmp_path):
    (tmp_path / "raw").mkdir(); (tmp_path / "weights").mkdir()
    readme = "line1\nline2\n'model_server': 'https://dashscope.example/v1',\n"
    (tmp_path / "weights" / "README.md").write_text(readme)
    url_issue = lambda loc: {"message": "URL detected", "severity": "warning",
                             "location": loc, "details": {"type": "url_detected",
                                                          "position": readme.index("https")}}
    (tmp_path / "raw" / "04_modelaudit.json").write_text(json.dumps({
        "files_scanned": 2, "issues": [url_issue("/scans/qwen/weights/README.md"),
                                       url_issue("/scans/qwen/weights/config.json")]}))
    run = build_modelaudit_run(tmp_path)
    assert run is not None
    doc, cfg = run["results"]
    assert doc["level"] == "note" and cfg["level"] == "warning"
    loc = doc["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "README.md" and loc["region"]["startLine"] == 3
    assert "region" not in cfg["locations"][0]["physicalLocation"]  # config.json not on disk


def test_doc_downgrade_fails_closed(tmp_path):
    """Archive members, symlinks and missing files keep their warning."""
    (tmp_path / "raw").mkdir(); w = tmp_path / "weights"; w.mkdir()
    (tmp_path / "outside.md").write_text("x")
    (w / "link.md").symlink_to(tmp_path / "outside.md")
    (w / "model.zip").write_bytes(b"zip")
    url = lambda loc: {"message": "URL", "severity": "warning", "location": loc,
                       "details": {"type": "url_detected"}}
    (tmp_path / "raw" / "04_modelaudit.json").write_text(json.dumps({"files_scanned": 3, "issues": [
        url("/s/weights/model.zip:payload/README.md"),  # archive member
        url("/s/weights/model.pt:data.txt"),            # pickle entry
        url("/s/weights/link.md"),                      # symlink out of the model
        url("/s/weights/gone.md"),                      # not on disk
    ]}))
    run = build_modelaudit_run(tmp_path)
    assert run is not None
    assert [r["level"] for r in run["results"]] == ["warning"] * 4
