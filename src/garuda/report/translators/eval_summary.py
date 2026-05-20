"""os-llm-eval synthetic SARIF run — built from 13_eval_summary.json."""
from __future__ import annotations

from pathlib import Path

from ...util.io import load_json

LEVEL = {"pass": "note", "warning": "warning", "fail": "error"}


def build_eval_run(scan_dir: Path) -> dict | None:
    data = load_json(scan_dir / "raw" / "13_eval_summary.json")
    if not data or "skipped" in data:
        return None
    rules: list[dict] = []
    results: list[dict] = []
    for cat, payload in data["categories"].items():
        rid = f"EVAL-{cat.upper()}"
        level = LEVEL[payload["verdict"]]
        rules.append(
            {
                "id": rid,
                "name": cat,
                "shortDescription": {"text": f"Behavioural eval category: {cat}"},
                "fullDescription": {"text": "Gate-relevant verdict per policy.yaml."},
                "defaultConfiguration": {"level": level},
            }
        )
        results.append(
            {
                "ruleId": rid,
                "level": level,
                "message": {
                    "text": (
                        f"{cat}: {payload['failures']}/{payload['probes_run']} probes failed "
                        f"({payload['failure_rate']:.1%}); verdict={payload['verdict']}"
                    )
                },
                "properties": {
                    "engine": payload["engine"],
                    "probes_run": payload["probes_run"],
                    "failures": payload["failures"],
                    "failure_rate": payload["failure_rate"],
                    "thresholds": payload["thresholds"],
                },
            }
        )
    overall_level = LEVEL[data["overall_verdict"]]
    rules.append(
        {
            "id": "EVAL-OVERALL",
            "name": "OverallVerdict",
            "shortDescription": {"text": "Rolled-up behavioural-eval verdict"},
            "fullDescription": {"text": "CI scrapes this single result for gate enforcement."},
            "defaultConfiguration": {"level": overall_level},
        }
    )
    results.append(
        {
            "ruleId": "EVAL-OVERALL",
            "level": overall_level,
            "message": {"text": f"Overall behavioural verdict: {data['overall_verdict']}"},
            "properties": {"policy_sha256": data.get("policy_sha256")},
        }
    )
    return {
        "tool": {"driver": {"name": "os-llm-eval", "version": "2.0.0", "rules": rules}},
        "results": results,
        "invocations": [{"executionSuccessful": True}],
    }
