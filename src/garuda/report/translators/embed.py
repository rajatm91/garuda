"""Embed already-SARIF tool outputs (grype, gitleaks, semgrep) into the aggregate log."""
from __future__ import annotations

import json
from pathlib import Path


def _fill_levels(run: dict) -> dict:
    """Give every result an explicit level.

    SARIF lets a result omit ``level`` and inherit its rule's
    ``defaultConfiguration.level`` (semgrep does this), falling back to "warning".
    Downstream counters read ``result.level`` directly, so resolve it here.
    """
    rules = run.get("tool", {}).get("driver", {}).get("rules") or []
    by_id = {r.get("id"): r for r in rules}
    for res in run.get("results") or []:
        if res.get("level"):
            continue
        idx = res.get("ruleIndex")
        rule = rules[idx] if isinstance(idx, int) and 0 <= idx < len(rules) \
            else by_id.get(res.get("ruleId"), {})
        res["level"] = (rule.get("defaultConfiguration") or {}).get("level") or "warning"
    return run


def embed_runs(sarif_path: Path) -> list[dict]:
    """Return the ``runs`` array of a SARIF file, or [] if missing/empty/invalid."""
    if not sarif_path.exists() or sarif_path.stat().st_size == 0:
        return []
    try:
        runs = json.loads(sarif_path.read_text()).get("runs", [])
    except json.JSONDecodeError:
        return []
    return [_fill_levels(r) for r in runs if isinstance(r, dict)]
