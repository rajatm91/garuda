import shutil
from pathlib import Path
from garuda.report.translators.garak import build_garak_run

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "raw" / "11_garak.jsonl"


def test_emits_one_result_per_failed(tmp_path):
    (tmp_path / "raw").mkdir()
    shutil.copy(FIXTURE, tmp_path / "raw" / "11_garak.jsonl")
    run = build_garak_run(tmp_path)
    assert len(run["results"]) == 2
    levels = sorted(r["level"] for r in run["results"])
    assert levels == ["error", "warning"]
    rule_ids = {r["ruleId"] for r in run["results"]}
    assert rule_ids == {"GARAK-PromptInject", "GARAK-Dan"}


def test_missing_file_returns_none(tmp_path):
    assert build_garak_run(tmp_path) is None
