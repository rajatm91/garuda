"""Second-opinion scan JSON output → SARIF run."""
from __future__ import annotations

import re
from pathlib import Path

from ...util.io import load_json

_SUFFIX = "picklescan"
_COUNT = re.compile(r"^(Infected files|Dangerous globals|Suspicious globals):\s*(\d+)", re.MULTILINE)


def _counts(stdout: str) -> dict[str, int]:
    """picklescan's SCAN SUMMARY lines → {"infected": n, "dangerous": n, "suspicious": n}."""
    return {k.split()[0].lower(): int(v) for k, v in _COUNT.findall(stdout)}


def _classify(exit_code: int, c: dict[str, int]) -> tuple[str, str]:
    # picklescan CLI: exit 0 = clean, 1 = dangerous globals found, 2 = scan error.
    if exit_code == 1 or c.get("infected", 0) or c.get("dangerous", 0):
        return "error", "PICKLESCAN-DANGEROUS"
    if exit_code != 0:
        return "error", "PICKLESCAN-SCAN-ERROR"  # fail closed: file not fully scanned
    if len(c) < 3:
        return "warning", "PICKLESCAN-UNPARSED"  # exit 0 but no summary → can't confirm clean
    if c["suspicious"]:
        return "warning", "PICKLESCAN-SUSPICIOUS"
    return "note", "PICKLESCAN-CLEAN"


def build_picklescan_run(scan_dir: Path) -> dict | None:
    data = load_json(scan_dir / "raw" / f"05_{_SUFFIX}.json")
    if not data or "skipped" in data or not data.get("results"):
        return None
    results = []
    for item in data["results"]:
        c = _counts(item.get("stdout") or "")
        level, rule = _classify(item["exit_code"], c)
        if len(c) == 3:
            text = (f"picklescan: {c['infected']} infected, {c['dangerous']} dangerous, "
                    f"{c['suspicious']} suspicious globals")
        else:
            text = f"picklescan exited {item['exit_code']} without a scan summary"
        err = (item.get("stderr") or "").strip()
        if level == "error" and err:
            text += f" ({err[-300:]})"
        results.append(
            {
                "ruleId": rule,
                "level": level,
                "message": {"text": text},
                "locations": [
                    {"physicalLocation": {"artifactLocation": {"uri": item["path"]}}}
                ],
                "properties": {"exit_code": item["exit_code"], **c},
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
