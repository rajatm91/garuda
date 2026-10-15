"""Step 13 Hugging Face security-scan JSON → SARIF run."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...util.io import load_json

TOOL = "huggingface-security-scan"
RULES = {
    "HFSEC001": ("HFFlaggedUnsafe", "error", "Hugging Face's scanners flagged this file as unsafe"),
    "HFSEC002": ("HFSuspicious", "warning", "Hugging Face's scanners rated this file suspicious"),
    "HFSEC003": ("HFNotScanned", "note", "Hugging Face has not scanned this file"),
    "HFSEC004": ("HFScansIncomplete", "warning", "Hugging Face scans not complete for this repo"),
    "HFSEC005": ("HFScanSummary", "note", "Hugging Face security scan summary"),
}
_BAD = {"unsafe", "infected", "malicious", "dangerous"}
_SUSPECT = {"caution", "suspicious", "warning"}
_DONE = {"safe", "innocuous"} | _BAD | _SUSPECT
# HF sets safe=false while a (re)scan is pending — that is "no verdict yet", not "unsafe".
# Any other status with safe=false stays flagged (fail closed on statuses we don't know).
_PENDING = {"queued", "pending", "scanning", "in_progress", "in-progress", "unscanned"}


def _res(rule: str, msg: str, uri: str | None = None, props: dict | None = None) -> dict:
    r: dict[str, Any] = {"ruleId": rule, "level": RULES[rule][1], "message": {"text": msg}}
    if uri:
        r["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": uri}}}]
    if props:
        r["properties"] = props
    return r


def _statuses(sec: dict) -> tuple[str, str, str]:
    av = (sec.get("av_scan") or {}).get("status") or ""
    pk = (sec.get("pickle_import_scan") or {}).get("status") or ""
    return (sec.get("status") or "").lower(), av.lower(), pk.lower()


def build_hf_security_run(scan_dir: Path) -> dict | None:
    data = load_json(scan_dir / "raw" / "13_hf_security.json")
    if not data or "skipped" in data:
        return None
    results: list[dict] = []
    flagged: set[str] = set()
    safe = not_scanned = 0
    for f in data.get("files") or []:
        path, sec = f.get("path"), f.get("security")
        if not isinstance(sec, dict):  # HF returns no security block for non-LFS small files
            continue
        overall, av, pk = _statuses(sec)
        imports = (sec.get("pickle_import_scan") or {}).get("pickleImports") or []
        detail = {"overall": overall, "av_scan": av, "pickle_import_scan": pk}
        if (sec.get("safe") is False and overall not in _PENDING) or overall in _BAD or av in _BAD or pk in _BAD:
            msg = (sec.get("av_scan") or {}).get("message") or "flagged unsafe by Hugging Face"
            if imports:
                msg += f" · pickle imports: {', '.join(str(i) for i in imports[:8])}"
            results.append(_res("HFSEC001", msg, path, detail))
            flagged.add(path)
        elif overall in _SUSPECT or av in _SUSPECT or pk in _SUSPECT:
            results.append(_res("HFSEC002", f"rated {overall or av or pk} by Hugging Face", path,
                                detail))
            flagged.add(path)
        elif overall in _PENDING:
            not_scanned += 1
            results.append(_res("HFSEC003", f"Hugging Face scan {overall} — no verdict yet",
                                path, detail))
        elif av not in _DONE:
            not_scanned += 1
            results.append(_res("HFSEC003", f"antivirus scan status: {av or 'unknown'} "
                                            "(HF does not AV-scan very large files)", path, detail))
        else:
            safe += 1

    repo = data.get("repo_status") or {}
    for item in repo.get("filesWithIssues") or []:
        path = item.get("path") if isinstance(item, dict) else str(item)
        if path not in flagged:  # repo-level list can name files the per-file pass missed
            results.append(_res("HFSEC001", "listed in Hugging Face's filesWithIssues", path,
                                item if isinstance(item, dict) else None))
    if repo and not repo.get("scansDone", True):
        results.append(_res("HFSEC004", "Hugging Face reports scans still in progress"))
    results.append(_res(
        "HFSEC005",
        f"Hugging Face at commit {str(data.get('revision'))[:12]}: {safe} file(s) scanned safe, "
        f"{not_scanned} not antivirus-scanned by HF (its 'safe' label does not cover them — "
        f"modelaudit's results do), {len(repo.get('filesWithIssues') or [])} with issues.",
    ))
    return {
        "tool": {"driver": {
            "name": TOOL,
            "informationUri": "https://huggingface.co/docs/hub/security-malware",
            "rules": [{"id": rid, "name": n, "shortDescription": {"text": t},
                       "defaultConfiguration": {"level": lv}} for rid, (n, lv, t) in RULES.items()],
        }},
        "results": results,
        "invocations": [{"executionSuccessful": True}],
    }
