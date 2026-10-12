"""modelaudit JSON output → SARIF run."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...util.io import load_json

SEV2LEVEL = {
    "critical": "error",
    "high": "error",
    "error": "error",
    "medium": "warning",
    "warning": "warning",
    "low": "note",
    "info": "note",
    "debug": "note",
}
INCOMPLETE = "MODELAUDIT-INCOMPLETE"


def _result(rid: str, level: str, text: str, uri: str | None, props: dict) -> dict[str, Any]:
    r: dict[str, Any] = {"ruleId": rid, "level": level, "message": {"text": text},
                         "properties": props}
    if uri:
        r["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": uri}}}]
    return r


def build_modelaudit_run(scan_dir: Path) -> dict | None:
    data = load_json(scan_dir / "raw" / "04_modelaudit.json")
    if not data or "skipped" in data:
        return None
    rules: dict[str, dict] = {}
    results: list[dict[str, Any]] = []
    for issue in data.get("issues") or []:
        details = issue.get("details")
        dtype = details.get("type") if isinstance(details, dict) else None
        rid = "MODELAUDIT-" + str(issue.get("rule_id") or dtype or "GENERIC")
        sev = (issue.get("severity") or "medium").lower()
        level = SEV2LEVEL.get(sev, "warning")
        # 0.2.x: message + location + dict details; older shape: details text + file
        text = issue.get("message") or (details if isinstance(details, str) else None) \
            or "Modelaudit issue."
        name = issue.get("category") or dtype or "modelaudit-finding"
        rules.setdefault(rid, {
            "id": rid, "name": name,
            "shortDescription": {"text": name},
            "defaultConfiguration": {"level": level},
        })
        results.append(_result(rid, level, text, issue.get("file") or issue.get("location"),
                               {"severity": sev, "category": name}))

    # Checks modelaudit could not finish (e.g. shard pinning unavailable on macOS) — the
    # file was NOT scanned, so say so instead of letting it look clean.
    for check in data.get("checks") or []:
        details = check.get("details")
        if isinstance(details, dict) and details.get("analysis_incomplete"):
            rules.setdefault(INCOMPLETE, {
                "id": INCOMPLETE, "name": "AnalysisIncomplete",
                "shortDescription": {"text": "modelaudit could not fully analyse a file"},
                "defaultConfiguration": {"level": "warning"},
            })
            reason = details.get("error") or details.get("scan_outcome_reason") or ""
            results.append(_result(
                INCOMPLETE, "warning",
                f"{check.get('name')}: {check.get('message')}" + (f" ({reason})" if reason else ""),
                check.get("location"),
                {"check": check.get("name"), "scan_outcome": details.get("scan_outcome")},
            ))
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
        "invocations": [{"executionSuccessful": not data.get("has_errors", False)}],
    }
