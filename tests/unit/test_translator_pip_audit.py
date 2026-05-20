from pathlib import Path

from garuda.report.translators.pip_audit import build_pip_audit_run

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "raw" / "06_pip_audit.json"


def test_emits_two_results(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "06_pip_audit.json").write_text(FIXTURE.read_text())
    run = build_pip_audit_run(tmp_path)
    levels = [r["level"] for r in run["results"]]
    assert levels == ["warning", "error"]


def test_returns_none_on_skip_stub(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "06_pip_audit.json").write_text('{"skipped":"x"}')
    assert build_pip_audit_run(tmp_path) is None
