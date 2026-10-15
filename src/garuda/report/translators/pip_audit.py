"""pip-audit JSON output → SARIF run."""
from __future__ import annotations

from pathlib import Path

from ...util.io import load_json


def build_pip_audit_run(scan_dir: Path) -> dict | None:
    data = load_json(scan_dir / "raw" / "06_pip_audit.json")
    if not data:
        return None
    if "skipped" in data:
        return _undeclared_run(data.get("undeclared_imports") or {})
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
                    **({"locations": [{"physicalLocation": {"artifactLocation": {
                        "uri": dep["requirements_file"]}}}]} if dep.get("requirements_file") else {}),
                }
            )
    return _run(results)


def _undeclared_run(imports: dict[str, list[str]]) -> dict | None:
    """No requirements file shipped: report each third-party import as an undeclared,
    unpinned dependency (informational — no versions, so nothing to CVE-match)."""
    if not imports:
        return None
    results = [
        {
            "ruleId": "UNDECLARED-DEPENDENCY",
            "level": "note",
            "message": {"text": f"Model code imports '{mod}' but the repo ships no "
                                "requirements file, so its version is unpinned and was not "
                                "audited for CVEs."},
            "properties": {"package": mod},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": f}}} for f in files],
        }
        for mod, files in imports.items()
    ]
    return _run(results)


def _run(results: list[dict]) -> dict:
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
