"""Policy suppressions: findings in files we deliberately ignore (default README.md).

Findings are kept in SARIF with a standard ``suppressions`` entry (GHAS/DefectDojo treat
them as suppressed) and excluded from the HTML verdict and counts — never silently dropped.
"""
from __future__ import annotations

import os
from pathlib import PurePosixPath

IGNORE_ENV = "GARUDA_IGNORE_FILES"
DEFAULT_IGNORE = "README.md"


def ignored_names() -> set[str]:
    raw = os.environ.get(IGNORE_ENV, DEFAULT_IGNORE)
    return {n.strip().lower() for n in raw.split(",") if n.strip()}


def _uri(res: dict) -> str | None:
    locs = res.get("locations") or []
    return (locs[0].get("physicalLocation") or {}).get("artifactLocation", {}).get("uri") \
        if locs else None


def is_suppressed(res: dict) -> bool:
    return bool(res.get("suppressions"))


def apply_suppressions(sarif: dict, names: set[str] | None = None) -> dict:
    names = ignored_names() if names is None else names
    if not names:
        return sarif
    for run in sarif.get("runs") or []:
        for res in run.get("results") or []:
            uri = _uri(res)
            # real files only: archive members ("x.zip:README.md") stay findings
            if not uri or ":" in uri or "!" in uri:
                continue
            if PurePosixPath(uri).name.lower() in names:
                res["suppressions"] = [{
                    "kind": "external", "status": "accepted",
                    "justification": f"Findings in {PurePosixPath(uri).name} are ignored by "
                                     f"scan policy ({IGNORE_ENV}).",
                }]
    return sarif
