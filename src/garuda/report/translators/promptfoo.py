"""promptfoo JSON output → SARIF run."""
from __future__ import annotations

from pathlib import Path

from ...util.io import load_json


def build_promptfoo_run(scan_dir: Path) -> dict | None:
    data = load_json(scan_dir / "raw" / "12_promptfoo.json")
    if not data or "skipped" in data:
        return None
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for result in (data.get("results", {}).get("results") or []):
        failed = [a for a in (result.get("assertions") or []) if not a.get("pass")]
        if not failed:
            continue
        plugin = (result.get("metadata") or {}).get("pluginId", "unknown")
        rid = f"PROMPTFOO-{plugin}"
        rules.setdefault(
            rid,
            {
                "id": rid,
                "name": plugin,
                "shortDescription": {"text": plugin},
                "fullDescription": {"text": f"promptfoo redteam plugin: {plugin}"},
                "defaultConfiguration": {"level": "warning"},
            },
        )
        results.append(
            {
                "ruleId": rid,
                "level": "warning",
                "message": {
                    "text": (result.get("response", {}).get("output", "") or "")[:500]
                },
                "properties": {
                    "prompt": ((result.get("prompt") or {}).get("raw", ""))[:500],
                    "failed_assertions": [a.get("type") for a in failed],
                    "score": result.get("score"),
                    "judge_model": (result.get("gradingResult") or {}).get("model"),
                    "detail_uri": f"raw/12_promptfoo/result-{result.get('id','')}.html",
                },
            }
        )
    return {
        "tool": {
            "driver": {
                "name": "promptfoo",
                "informationUri": "https://promptfoo.dev",
                "rules": list(rules.values()),
            }
        },
        "results": results,
        "invocations": [{"executionSuccessful": True}],
    }
