"""Step 04 — promptfoo's modelaudit. Replaces legacy modelscan."""
from __future__ import annotations

import logging
import shutil
import time

from ...context import ScanContext, StageResult
from ...util.io import load_json, write_stub
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
    out_path.unlink(missing_ok=True)  # never mistake a previous run's file for this one
    # JSON via stdout, not --output: modelaudit 0.2.52's --output preflight crashes on macOS
    # (ctypes lookup of acl_extended_fd_np).
    res = run_tool(BIN, [BIN, "scan", str(ctx.weights_dir), "--format", "json"],
                   stdout_path=out_path, stderr_path=stderr, cwd=ctx.scan_dir)
    # Exit 1 = issues found (completed scan), 2 = operational error. A Python crash also
    # exits 1, so only a real result document (with files_scanned) counts as a scan.
    data = load_json(out_path)
    if not isinstance(data, dict) or "files_scanned" not in data:
        reason = f"{BIN} exit={res.exit_code}, no scan result (see {stderr.name})"
        write_stub(out_path, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=reason)
    if res.exit_code not in (0, 1):
        # Partial result: keep the JSON (findings + which files were not analysed reach the
        # report) but don't count the step as a completed scan.
        reason = f"{BIN} exit={res.exit_code}: analysis incomplete (see checks in {OUT})"
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=reason)
    return StageResult(ran=True, duration_s=time.monotonic() - t0,
                       output_path=out_path, skip_reason=None)
