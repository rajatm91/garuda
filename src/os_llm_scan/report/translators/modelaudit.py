"""modelaudit JSON output → SARIF run."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...util.io import load_json

SEV2LEVEL = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "info": "note",
}


def build_modelaudit_run(scan_dir: Path) -> dict | None:
    data = load_json(scan_dir / "raw" / "04_modelaudit.json")
    if not data or "skipped" in data:
        return None
    rules: dict[str, dict] = {}
    results: list[dict[str, Any]] = []
    for issue in data.get("issues") or []:
        rid = "MODELAUDIT-" + str(issue.get("rule_id") or "GENERIC")
        sev = (issue.get("severity") or "medium").lower()
        level = SEV2LEVEL.get(sev, "warning")
        rules.setdefault(
            rid,
            {
                "id": rid,
                "name": issue.get("category") or "modelaudit-finding",
                "shortDescription": {"text": issue.get("category") or "modelaudit finding"},
                "fullDescription": {"text": issue.get("details") or "Detected by modelaudit."},
                "defaultConfiguration": {"level": level},
            },
        )
        result: dict[str, Any] = {
            "ruleId": rid,
            "level": level,
            "message": {"text": issue.get("details") or "Modelaudit issue."},
            "properties": {"severity": sev, "category": issue.get("category")},
        }
        if issue.get("file"):
            result["locations"] = [
                {"physicalLocation": {"artifactLocation": {"uri": issue["file"]}}}
            ]
        results.append(result)
    return {
        "tool": {
            "driver": {
                "name": "modelaudit",
                "version": str(data.get("scanner_version", "unknown")),
                "informationUri": "https://github.com/promptfoo/modelaudit",
                "rules": list(rules.values()),
            }
        },
        "results": results,
        "invocations": [{"executionSuccessful": True}],
    }
