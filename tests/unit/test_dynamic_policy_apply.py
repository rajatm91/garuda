import json
from pathlib import Path

from os_llm_scan.stages.dynamic.policy import (
    Policy, CategoryPolicy, FailureRateThresholds, PassRateThresholds, apply_policy,
)


def _policy_path(tmp_path: Path) -> Path:
    p = tmp_path / "policy.yaml"; p.write_text("version: 1\ncategories: {}"); return p


def _setup(tmp_path: Path, garak_records, pf_results):
    (tmp_path / "raw").mkdir()
    with open(tmp_path / "raw" / "11_garak.jsonl", "w") as f:
        for r in garak_records:
            f.write(json.dumps(r) + "\n")
    (tmp_path / "raw" / "12_promptfoo.json").write_text(json.dumps({
        "results": {"results": pf_results}
    }))


def test_failure_rate_verdict_pass(tmp_path):
    pp = _policy_path(tmp_path)
    pol = Policy(version=1, categories={
        "prompt_injection": CategoryPolicy(
            engine="garak", probes=["promptinject"], sample_size=100,
            thresholds=FailureRateThresholds(error=0.5, warning=0.2))})
    _setup(tmp_path, [
        {"probe_classname":"PromptInject","passed":True}],[])
    summary = apply_policy(tmp_path, pol, pp)
    assert summary["categories"]["prompt_injection"]["verdict"] == "pass"
    assert summary["overall_verdict"] == "pass"


def test_failure_rate_verdict_fail(tmp_path):
    pp = _policy_path(tmp_path)
    pol = Policy(version=1, categories={
        "prompt_injection": CategoryPolicy(
            engine="garak", probes=["promptinject"], sample_size=100,
            thresholds=FailureRateThresholds(error=0.5, warning=0.2))})
    _setup(tmp_path, [
        {"probe_classname":"PromptInject","passed":False,"score":0.1},
        {"probe_classname":"PromptInject","passed":False,"score":0.1}],[])
    summary = apply_policy(tmp_path, pol, pp)
    assert summary["categories"]["prompt_injection"]["verdict"] == "fail"
    assert summary["overall_verdict"] == "fail"


def test_pass_rate_verdict(tmp_path):
    pp = _policy_path(tmp_path)
    pol = Policy(version=1, categories={
        "hallucination": CategoryPolicy(
            engine="promptfoo", plugins=["hallucination"], sample_size=100,
            thresholds=PassRateThresholds(pass_rate_error=0.7, pass_rate_warning=0.85))})
    _setup(tmp_path, [], [
        {"metadata":{"pluginId":"hallucination"},
         "assertions":[{"pass":False}]},
        {"metadata":{"pluginId":"hallucination"},
         "assertions":[{"pass":True}]}])
    summary = apply_policy(tmp_path, pol, pp)
    # 1/2 fail → failure_rate=0.5 → pass_rate=0.5 < 0.7 → fail
    assert summary["categories"]["hallucination"]["verdict"] == "fail"


def test_missing_files_zero(tmp_path):
    pp = _policy_path(tmp_path)
    pol = Policy(version=1, categories={
        "prompt_injection": CategoryPolicy(
            engine="garak", probes=["promptinject"], sample_size=100,
            thresholds=FailureRateThresholds(error=0.5, warning=0.2))})
    (tmp_path / "raw").mkdir()
    summary = apply_policy(tmp_path, pol, pp)
    assert summary["categories"]["prompt_injection"]["probes_run"] == 0
    assert summary["overall_verdict"] == "pass"
