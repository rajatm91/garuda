"""Step 02 — SHA-256 every weight-format file."""
from __future__ import annotations
import hashlib
import logging
import os
import time
from pathlib import Path

from ...context import ScanContext, StageResult
from ...util.io import write_json

log = logging.getLogger(__name__)
OUT = "02_sha256.json"
EXTS = (".safetensors", ".bin", ".pt", ".pth", ".gguf", ".onnx", ".tflite", ".msgpack", ".h5")


def run(ctx: ScanContext) -> StageResult:
    out_path = ctx.raw_dir / OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    results = []
    for dp, _, files in os.walk(ctx.weights_dir):
        for f in files:
            if f.endswith(EXTS):
                full = Path(dp) / f
                h = hashlib.sha256()
                with open(full, "rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(chunk)
                results.append({
                    "path": str(full.relative_to(ctx.weights_dir)),
                    "size": full.stat().st_size,
                    "sha256": h.hexdigest(),
                })
    write_json(out_path, {"root": str(ctx.weights_dir), "files": results})
    return StageResult(ran=True, duration_s=time.monotonic() - t0,
                       output_path=out_path, skip_reason=None)
