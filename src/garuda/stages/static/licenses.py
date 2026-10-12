"""Step 07 — license files the model ships, next to the license its card declares."""
from __future__ import annotations

import hashlib
import re
import time

from ...context import ScanContext, StageResult
from ...util.io import load_json, model_files, write_json

OUT = "07_licenses.json"
_LICENSE_NAME = re.compile(r"^(licen[cs]e|notice|copying)", re.IGNORECASE)


def run(ctx: ScanContext) -> StageResult:
    out_path = ctx.raw_dir / OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    meta = load_json(ctx.raw_dir / "01_metadata.json") or {}
    files = []
    for p in model_files(ctx.weights_dir, "*"):
        if not _LICENSE_NAME.match(p.name):
            continue
        h = hashlib.sha256()
        with p.open("rb") as fh:  # stream: a "LICENSE" file may be arbitrarily large
            head = fh.read(4096)
            h.update(head)
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        first = next((ln.strip() for ln in head.decode("utf-8", "replace").splitlines()
                      if ln.strip()), "")
        files.append({"path": str(p.relative_to(ctx.weights_dir)), "size": p.stat().st_size,
                      "sha256": h.hexdigest(), "first_line": first[:200]})
    write_json(out_path, {
        "declared": {k: meta.get(k) for k in ("license", "license_name", "license_link")},
        "files": files,
    })
    return StageResult(ran=True, duration_s=time.monotonic() - t0,
                       output_path=out_path, skip_reason=None)
