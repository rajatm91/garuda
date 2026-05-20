import shutil
from pathlib import Path
from os_llm_scan.report.translators.promptfoo import build_promptfoo_run

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "raw" / "12_promptfoo.json"


def test_emits_one_result_per_failed(tmp_path):
    (tmp_path / "raw").mkdir()
    shutil.copy(FIXTURE, tmp_path / "raw" / "12_promptfoo.json")
    run = build_promptfoo_run(tmp_path)
    assert len(run["results"]) == 1
    assert run["results"][0]["ruleId"] == "PROMPTFOO-hallucination"


def test_skip_stub_returns_none(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "12_promptfoo.json").write_text('{"skipped":"x"}')
    assert build_promptfoo_run(tmp_path) is None
