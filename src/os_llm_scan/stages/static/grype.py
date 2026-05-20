"""Step 09 — grype CVE scan (JSON + native SARIF)."""
from __future__ import annotations
import logging, shutil, time

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
    run_tool(BIN, [BIN, f"sbom:{cdx}", "-o", "json",  "--file", str(json_p)], cwd=ctx.scan_dir)
    run_tool(BIN, [BIN, f"sbom:{cdx}", "-o", "sarif", "--file", str(sarif_p)], cwd=ctx.scan_dir)
    return StageResult(ran=json_p.exists(), duration_s=time.monotonic() - t0,
                       output_path=json_p,
                       skip_reason=None if json_p.exists() else "grype produced no output")
