"""Step 04 — promptfoo's modelaudit. Replaces legacy modelscan."""
from __future__ import annotations
import logging
import shutil
import time

from ...context import ScanContext, StageResult
from ...util.io import write_stub
from ...util.proc import run_tool

log = logging.getLogger(__name__)
OUT = "04_modelaudit.json"
BIN = "modelaudit"


def run(ctx: ScanContext) -> StageResult:
    out_path = ctx.raw_dir / OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    if shutil.which(BIN) is None:
        reason = f"{BIN} not installed"
        write_stub(out_path, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=reason)
    stderr = ctx.raw_dir / "04_modelaudit.stderr.log"
    res = run_tool(BIN,
                   [BIN, "scan", str(ctx.weights_dir), "--format", "json",
                    "--output", str(out_path)],
                   stderr_path=stderr, cwd=ctx.scan_dir)
    if res.exit_code != 0:
        reason = f"{BIN} exit={res.exit_code}"
        if not out_path.exists():
            write_stub(out_path, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=reason)
    return StageResult(ran=True, duration_s=time.monotonic() - t0,
                       output_path=out_path, skip_reason=None)
