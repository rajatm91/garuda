"""Step 03 — partition step-02 hashes by extension."""
from __future__ import annotations

import logging
import time

from ...context import ScanContext, StageResult
from ...util.io import load_json, write_json, write_stub

log = logging.getLogger(__name__)
OUT = "03_format_inventory.json"
# Pickle-capable (or code-executing) formats: torch/pickle/joblib, numpy with
# allow_pickle, Keras archives (Lambda layers).
UNSAFE_EXTS = (".bin", ".pt", ".pth", ".ckpt", ".pkl", ".pickle", ".joblib",
               ".npy", ".npz", ".keras")


def run(ctx: ScanContext) -> StageResult:
    out_path = ctx.raw_dir / OUT
    t0 = time.monotonic()
    sha = load_json(ctx.raw_dir / "02_sha256.json")
    if sha is None or "files" not in sha:
        reason = "02_sha256.json missing or invalid"
        write_stub(out_path, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=reason)
    safetensors, unsafe, other = [], [], []
    for f in sha["files"]:
        p = f["path"]
        if p.endswith(".safetensors"):
            safetensors.append(f)
        elif p.endswith(UNSAFE_EXTS):
            unsafe.append(f)
        else:
            other.append(f)
    write_json(out_path, {
        "safetensors": safetensors, "unsafe_format": unsafe, "other": other,
        "counts": {"safetensors": len(safetensors),
                   "unsafe_format": len(unsafe), "other": len(other)},
    })
    return StageResult(ran=True, duration_s=time.monotonic() - t0,
                       output_path=out_path, skip_reason=None)
