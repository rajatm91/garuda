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
