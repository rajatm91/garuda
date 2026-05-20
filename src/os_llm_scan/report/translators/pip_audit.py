"""pip-audit JSON output → SARIF run."""
from __future__ import annotations

from pathlib import Path

from ...util.io import load_json


def build_pip_audit_run(scan_dir: Path) -> dict | None:
    data = load_json(scan_dir / "raw" / "06_pip_audit.json")
    if not data or "skipped" in data:
        return None
    results = []
    for dep in data.get("dependencies", []):
        for v in dep.get("vulns", []):
            fixes = v.get("fix_versions") or []
            results.append(
                {
                    "ruleId": v.get("id", "PIP-AUDIT-UNKNOWN"),
                    "level": "warning" if fixes else "error",
                    "message": {"text": v.get("description", "Vulnerable package.")},
                    "properties": {
                        "package": dep.get("name"),
                        "version": dep.get("version"),
                        "fix_versions": fixes,
                        "aliases": v.get("aliases", []),
                    },
                }
            )
    return {
        "tool": {
            "driver": {
                "name": "pip-audit",
                "informationUri": "https://github.com/pypa/pip-audit",
            }
        },
        "results": results,
        "invocations": [{"executionSuccessful": True}],
    }
