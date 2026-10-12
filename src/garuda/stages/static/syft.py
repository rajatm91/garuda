"""Step 08 — syft SBOM (CycloneDX + SPDX)."""
from __future__ import annotations

import logging
import shutil
import time

from ...context import ScanContext, StageResult
from ...util.io import load_json, write_stub
from ...util.proc import run_tool

log = logging.getLogger(__name__)
CDX = "08_sbom.cdx.json"
SPDX = "08_sbom.spdx.json"
BIN = "syft"


def run(ctx: ScanContext) -> StageResult:
    cdx_path = ctx.raw_dir / CDX
    spdx_path = ctx.raw_dir / SPDX
    cdx_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    if shutil.which(BIN) is None:
        reason = f"{BIN} not installed"
        write_stub(cdx_path, reason); write_stub(spdx_path, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=cdx_path, skip_reason=reason)
    for p in (cdx_path, spdx_path):
        p.unlink(missing_ok=True)  # never mistake a previous run's file for this one
    run_tool(BIN, [BIN, "dir:.", "-o", f"cyclonedx-json={cdx_path}"], cwd=ctx.scan_dir)
    run_tool(BIN, [BIN, "dir:.", "-o", f"spdx-json={spdx_path}"], cwd=ctx.scan_dir)
    cdx, spdx = load_json(cdx_path), load_json(spdx_path)
    ok = isinstance(cdx, dict) and "bomFormat" in cdx and isinstance(spdx, dict) \
        and "spdxVersion" in spdx
    return StageResult(ran=ok, duration_s=time.monotonic() - t0,
                       output_path=cdx_path,
                       skip_reason=None if ok else "syft did not produce outputs")
