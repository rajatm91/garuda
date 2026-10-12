"""Aggregate raw/* into one SARIF 2.1.0 log."""
from __future__ import annotations

from pathlib import Path

from ..util.io import write_json
from .translators.review import build_review_run
from .translators.modelaudit import build_modelaudit_run
from .translators.picklescan import build_picklescan_run
from .translators.pip_audit import build_pip_audit_run
from .translators.embed import embed_runs

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
)


def build_sarif(scan_dir: Path, *, is_local_source: bool) -> dict:
    runs: list[dict] = [build_review_run(scan_dir, is_local_source=is_local_source)]
    for builder in (build_modelaudit_run, build_picklescan_run, build_pip_audit_run):
        r = builder(scan_dir)
        if r is not None:
            runs.append(r)
    runs.extend(embed_runs(scan_dir / "raw" / "09_grype.sarif"))
    runs.extend(embed_runs(scan_dir / "raw" / "10_gitleaks.sarif"))
    return {"$schema": SARIF_SCHEMA, "version": SARIF_VERSION, "runs": runs}


def write_sarif(scan_dir: Path, log: dict) -> Path:
    out = scan_dir / "reports" / "scan_results.sarif"
    write_json(out, log)
    return out
