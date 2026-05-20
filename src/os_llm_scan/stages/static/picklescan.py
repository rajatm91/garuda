"""Step 05 — second-opinion scan of unsafe-format weight files."""
from __future__ import annotations
import logging, subprocess, time

from ...context import ScanContext, StageResult
from ...util.io import load_json, write_json

log = logging.getLogger(__name__)
OUT = "05_picklescan.json"
BIN = "picklescan"


def run(ctx: ScanContext) -> StageResult:
    out_path = ctx.raw_dir / OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    inv = load_json(ctx.raw_dir / "03_format_inventory.json") or {}
    unsafe = inv.get("unsafe_format", [])
    if not unsafe:
        write_json(out_path, {"results": [], "note": "No unsafe-format files present."})
        return StageResult(ran=True, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=None)
    results = []
    for f in unsafe:
        full = ctx.weights_dir / f["path"]
        r = subprocess.run([BIN, "-p", str(full)], capture_output=True, text=True)
        results.append({
            "path": f["path"],
            "exit_code": r.returncode,
            "stdout": r.stdout[:2000],
            "stderr": r.stderr[:2000],
            "globals_found": "dangerous" in (r.stdout + r.stderr).lower(),
        })
    write_json(out_path, {"results": results})
    return StageResult(ran=True, duration_s=time.monotonic() - t0,
                       output_path=out_path, skip_reason=None)
