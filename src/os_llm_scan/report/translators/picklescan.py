"""Second-opinion scan JSON output → SARIF run."""
from __future__ import annotations

from pathlib import Path

from ...util.io import load_json

_SUFFIX = "picklescan"


def build_picklescan_run(scan_dir: Path) -> dict | None:
    data = load_json(scan_dir / "raw" / f"05_{_SUFFIX}.json")
    if not data or "skipped" in data or not data.get("results"):
        return None
    results = []
    for item in data["results"]:
        if item["exit_code"] != 0:
            level, rule = "error", "PICKLESCAN-DANGEROUS"
        elif item.get("globals_found"):
            level, rule = "warning", "PICKLESCAN-DANGEROUS"
        else:
            level, rule = "note", "PICKLESCAN-CLEAN"
        results.append(
            {
                "ruleId": rule,
                "level": level,
                "message": {"text": (item.get("stdout") or "")[:500] or "No issues."},
                "locations": [
                    {"physicalLocation": {"artifactLocation": {"uri": item["path"]}}}
                ],
                "properties": {"exit_code": item["exit_code"]},
            }
        )
    return {
        "tool": {
            "driver": {
                "name": _SUFFIX,
                "informationUri": f"https://github.com/mmaitre314/{_SUFFIX}",
            }
        },
        "results": results,
        "invocations": [{"executionSuccessful": True}],
    }
