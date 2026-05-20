import shutil
from pathlib import Path
from garuda.report.translators.eval_summary import build_eval_run

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "raw" / "13_eval_summary.json"


def test_emits_per_category_plus_overall(tmp_path):
    (tmp_path / "raw").mkdir()
    shutil.copy(FIXTURE, tmp_path / "raw" / "13_eval_summary.json")
    run = build_eval_run(tmp_path)
    rule_ids = {r["ruleId"] for r in run["results"]}
    assert "EVAL-PROMPT_INJECTION" in rule_ids
    assert "EVAL-BIAS" in rule_ids
    assert "EVAL-OVERALL" in rule_ids
    overall = [r for r in run["results"] if r["ruleId"] == "EVAL-OVERALL"][0]
    assert overall["level"] == "error"


def test_missing_returns_none(tmp_path):
    assert build_eval_run(tmp_path) is None
