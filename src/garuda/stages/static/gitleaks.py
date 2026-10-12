"""Step 10 — gitleaks secrets scan (JSON + native SARIF)."""
from __future__ import annotations

import logging
import shutil
import time

from ...context import ScanContext, StageResult
from ...util.io import write_stub
from ...util.proc import run_tool

log = logging.getLogger(__name__)
JSON_OUT = "10_gitleaks.json"
SARIF_OUT = "10_gitleaks.sarif"
MAX_TARGET_MB = 100
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
    for p in (json_p, sarif_p):
        p.unlink(missing_ok=True)  # never mistake a previous run's report for this one
    # Secrets live in configs/tokenizer/README, not in multi-GB weight shards; skipping
    # big files keeps each pass from re-reading the whole model.
    common = ["detect", "--no-git", "--source", str(ctx.scan_dir),
              "--max-target-megabytes", str(MAX_TARGET_MB)]
    run_tool(BIN, [BIN, *common, "--report-format", "json", "--report-path", str(json_p)],
             cwd=ctx.scan_dir)
    run_tool(BIN, [BIN, *common, "--report-format", "sarif", "--report-path", str(sarif_p)],
             cwd=ctx.scan_dir)
    return StageResult(ran=json_p.exists(), duration_s=time.monotonic() - t0,
                       output_path=json_p,
                       skip_reason=None if json_p.exists() else "gitleaks no output")
