"""Step 09 — grype CVE scan (JSON + native SARIF)."""
from __future__ import annotations

import logging
import shutil
import time

from ...context import ScanContext, StageResult
from ...util.io import load_json, write_stub
from ...util.proc import run_tool

log = logging.getLogger(__name__)
JSON_OUT = "09_grype.json"
SARIF_OUT = "09_grype.sarif"
BIN = "grype"


def run(ctx: ScanContext) -> StageResult:
    json_p = ctx.raw_dir / JSON_OUT
    sarif_p = ctx.raw_dir / SARIF_OUT
    cdx = ctx.raw_dir / "08_sbom.cdx.json"
    t0 = time.monotonic()
    json_p.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which(BIN) is None:
        reason = f"{BIN} not installed"
        write_stub(json_p, reason); write_stub(sarif_p, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=json_p, skip_reason=reason)
    sbom = load_json(cdx)
    if not sbom or "skipped" in sbom:
        reason = "08_sbom.cdx.json missing or stub"
        write_stub(json_p, reason); write_stub(sarif_p, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=json_p, skip_reason=reason)
    for p in (json_p, sarif_p):
        p.unlink(missing_ok=True)  # never mistake a previous run's file for this one
    stderr = ctx.raw_dir / "09_grype.stderr.log"
    run_tool(BIN, [BIN, f"sbom:{cdx}", "-o", "json", "--file", str(json_p)],
             stderr_path=stderr, cwd=ctx.scan_dir)
    run_tool(BIN, [BIN, f"sbom:{cdx}", "-o", "sarif", "--file", str(sarif_p)],
             stderr_path=stderr, cwd=ctx.scan_dir)
    # A file existing is not success: grype with an unusable vuln DB writes 0-byte output.
    data, sarif = load_json(json_p), load_json(sarif_p)
    if not (isinstance(data, dict) and "matches" in data and isinstance(sarif, dict)
            and "runs" in sarif):
        reason = f"grype produced no valid result (see {stderr.name})"
        write_stub(json_p, reason); write_stub(sarif_p, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=json_p, skip_reason=reason)
    return StageResult(ran=True, duration_s=time.monotonic() - t0,
                       output_path=json_p, skip_reason=None)
