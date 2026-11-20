import json
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


_SUMMARY = ("----------- SCAN SUMMARY -----------\nScanned files: 1\nInfected files: {}\n"
            "Suspicious globals: {}\nDangerous globals: {}\n")


def _run(tmp_path, *items):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "05_picklescan.json").write_text(json.dumps({"results": [
        {"path": f"f{i}.pth", "exit_code": code, "stdout": out, "stderr": err}
        for i, (code, out, err) in enumerate(items)]}))
    run = build_picklescan_run(tmp_path)
    assert run is not None
    return [(r["ruleId"], r["level"]) for r in run["results"]], run


def test_clean_summary_is_note_not_dangerous(tmp_path):
    # Regression #34: "Dangerous globals: 0" contains "dangerous" — must not flag a clean file.
    got, run = _run(tmp_path, (0, _SUMMARY.format(0, 0, 0), ""))
    assert got == [("PICKLESCAN-CLEAN", "note")]
    assert run["results"][0]["message"]["text"] == \
        "picklescan: 0 infected, 0 dangerous, 0 suspicious globals"


def test_severity_matrix(tmp_path):
    got, _ = _run(
        tmp_path,
        (1, _SUMMARY.format(1, 0, 2), ""),        # dangerous globals → error
        (2, _SUMMARY.format(0, 0, 0), "boom"),    # scan error → error, fail closed
        (0, _SUMMARY.format(0, 3, 0), ""),        # suspicious only → warning
        (0, "", ""),                              # no summary → can't confirm clean
    )
    assert got == [("PICKLESCAN-DANGEROUS", "error"), ("PICKLESCAN-SCAN-ERROR", "error"),
                   ("PICKLESCAN-SUSPICIOUS", "warning"), ("PICKLESCAN-UNPARSED", "warning")]
