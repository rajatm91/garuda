from pathlib import Path

from garuda.report.translators.picklescan import build_picklescan_run

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "raw" / "05_picklescan.json"


def test_emits_two_results_with_expected_levels(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "05_picklescan.json").write_text(FIXTURE.read_text())
    run = build_picklescan_run(tmp_path)
    assert run is not None
    levels = [r["level"] for r in run["results"]]
    assert levels == ["note", "error"]


def test_returns_none_on_skip_stub(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "05_picklescan.json").write_text('{"skipped":"x"}')
    assert build_picklescan_run(tmp_path) is None
