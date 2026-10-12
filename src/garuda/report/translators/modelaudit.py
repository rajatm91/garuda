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
# Docs are never loaded at inference time; a coverage cap there (e.g. modelaudit's hard-coded
# 32-URL listing limit on a README) is informational, not a gap in what the model executes.
_DOC_SUFFIXES = (".md", ".rst", ".txt")
# URLs in docs are examples for readers (e.g. a hosted-API snippet in a README), not endpoints
# the model contacts; in configs/templates/code they stay warnings.
_DOC_DOWNGRADE_TYPES = {"url_detected"}


def _is_doc(scan_dir: Path, location: str | None) -> bool:
    """True only for a real, top-level doc file of the model — fail closed otherwise.

    The location string alone is not trusted: archive members are reported as
    "archive.zip:member.md" and a pickle entry can end in ".txt", so a suffix check would
    downgrade findings inside loadable artefacts.
    """
    rel = _model_path(location)
    if not rel or ":" in rel or "!" in rel or not rel.lower().endswith(_DOC_SUFFIXES):
        return False
    root = (scan_dir / "weights").resolve()
    f = root / rel
    return (not f.is_symlink() and f.is_file() and f.resolve().is_relative_to(root))


def _model_path(location: str | None) -> str | None:
    """Absolute scanner path (host or container) → path relative to the model root."""
    if not location:
        return None
    loc = str(location)
    return loc.split("/weights/", 1)[1] if "/weights/" in loc else loc


def _line_of(scan_dir: Path, rel: str | None, position: Any) -> int | None:
    """1-based line for modelaudit's character offset, if the scanned file is still on disk."""
    if not rel or not isinstance(position, int) or position < 0:
        return None
    root = (scan_dir / "weights").resolve()
    f = (root / rel).resolve()
    if not f.is_relative_to(root) or not f.is_file():
        return None
    with f.open(encoding="utf-8", errors="replace") as fh:
        return fh.read(position).count("\n") + 1


def _result(rid: str, level: str, text: str, uri: str | None, props: dict,
            line: int | None = None) -> dict[str, Any]:
    r: dict[str, Any] = {"ruleId": rid, "level": level, "message": {"text": text},
                         "properties": props}
    if uri:
        loc: dict[str, Any] = {"artifactLocation": {"uri": uri}}
        if line:
            loc["region"] = {"startLine": line}
        r["locations"] = [{"physicalLocation": loc}]
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
        location = issue.get("file") or issue.get("location")
        if level == "warning" and dtype in _DOC_DOWNGRADE_TYPES and _is_doc(scan_dir, location):
            level = "note"
        rel = _model_path(location)
        line = _line_of(scan_dir, rel, details.get("position")) if isinstance(details, dict) \
            else None
        # 0.2.x: message + location + dict details; older shape: details text + file
        text = issue.get("message") or (details if isinstance(details, str) else None) \
            or "Modelaudit issue."
        name = issue.get("category") or dtype or "modelaudit-finding"
        rules.setdefault(rid, {
            "id": rid, "name": name,
            "shortDescription": {"text": name},
            "defaultConfiguration": {"level": level},
        })
        results.append(_result(rid, level, text, rel, {"severity": sev, "category": name}, line))

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
                INCOMPLETE, "note" if _is_doc(scan_dir, check.get("location")) else "warning",
                f"{check.get('name')}: {check.get('message')}" + (f" ({reason})" if reason else ""),
                _model_path(check.get("location")),
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
