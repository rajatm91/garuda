"""garak JSONL output → SARIF run."""
from __future__ import annotations

import json
from pathlib import Path

SEV2LEVEL = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "note",
    "info": "note",
}


def build_garak_run(scan_dir: Path) -> dict | None:
    p = scan_dir / "raw" / "11_garak.jsonl"
    if not p.exists() or p.stat().st_size == 0:
        return None
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("passed", True):
            continue
        probe = rec.get("probe_classname", "unknown")
        rid = f"GARAK-{probe}"
        sev = (rec.get("severity") or "medium").lower()
        level = SEV2LEVEL.get(sev, "warning")
        rules.setdefault(
            rid,
            {
                "id": rid,
                "name": probe,
                "shortDescription": {"text": probe},
                "fullDescription": {"text": rec.get("detector_description", probe)},
                "defaultConfiguration": {"level": level},
            },
        )
        results.append(
            {
                "ruleId": rid,
                "level": level,
                "message": {"text": (rec.get("output") or "")[:500]},
                "properties": {
                    "probe": probe,
                    "attempt_id": rec.get("attempt_id"),
                    "detector": rec.get("detector"),
                    "score": rec.get("score"),
                    "judge_rationale": (rec.get("detector_rationale") or "")[:500],
                },
            }
        )
    return {
        "tool": {
            "driver": {
                "name": "garak",
                "informationUri": "https://github.com/NVIDIA/garak",
                "rules": list(rules.values()),
            }
        },
        "results": results,
        "invocations": [{"executionSuccessful": True}],
    }
