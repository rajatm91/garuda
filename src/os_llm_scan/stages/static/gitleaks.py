"""Step 10 — gitleaks secrets scan (JSON + native SARIF)."""
from __future__ import annotations
import logging, shutil, time

from ...context import ScanContext, StageResult
from ...util.io import write_stub
from ...util.proc import run_tool

log = logging.getLogger(__name__)
JSON_OUT = "10_gitleaks.json"
SARIF_OUT = "10_gitleaks.sarif"
BIN = "gitleaks"


def run(ctx: ScanContext) -> StageResult:
    json_p = ctx.raw_dir / JSON_OUT
    sarif_p = ctx.raw_dir / SARIF_OUT
    t0 = time.monotonic()
    json_p.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which(BIN) is None:
        reason = f"{BIN} not installed"
        write_stub(json_p, reason); write_stub(sarif_p, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=json_p, skip_reason=reason)
    run_tool(BIN, [BIN, "detect", "--no-git", "--report-format", "json",
                   "--report-path", str(json_p), "--source", str(ctx.scan_dir)],
             cwd=ctx.scan_dir)
    run_tool(BIN, [BIN, "detect", "--no-git", "--report-format", "sarif",
                   "--report-path", str(sarif_p), "--source", str(ctx.scan_dir)],
             cwd=ctx.scan_dir)
    return StageResult(ran=json_p.exists(), duration_s=time.monotonic() - t0,
                       output_path=json_p,
                       skip_reason=None if json_p.exists() else "gitleaks no output")
