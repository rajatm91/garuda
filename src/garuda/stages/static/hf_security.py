"""Step 13 — Hugging Face's own security scan results (antivirus + pickle-import scan)."""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from huggingface_hub import HfApi

from ...context import ScanContext, StageResult
from ...util.io import load_json, write_json, write_stub

log = logging.getLogger(__name__)
OUT = "13_hf_security.json"
BATCH = 100  # paths per paths-info request


def run(ctx: ScanContext) -> StageResult:
    out_path = ctx.raw_dir / OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    def skip(reason: str) -> StageResult:
        write_stub(out_path, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=reason)

    if ctx.is_local_source:
        return skip("local source — no Hugging Face scan to fetch")
    meta = load_json(ctx.raw_dir / "01_metadata.json") or {}
    sha = meta.get("sha")
    if not sha:
        return skip("01_metadata.json has no resolved commit SHA")
    paths = [s["name"] for s in meta.get("siblings") or [] if s.get("name")]
    try:
        data = _fetch(ctx.repo, sha, paths)
    except Exception as e:
        log.exception("HF security scan fetch failed")
        return skip(f"Hugging Face API error: {type(e).__name__}: {e}")
    write_json(out_path, data)
    return StageResult(ran=True, duration_s=time.monotonic() - t0,
                       output_path=out_path, skip_reason=None)


def _fetch(repo: str, sha: str, paths: list[str]) -> dict[str, Any]:
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    info = api.model_info(repo, revision=sha, securityStatus=True)
    files = []
    for i in range(0, len(paths), BATCH):
        for f in api.get_paths_info(repo, paths[i:i + BATCH], expand=True, revision=sha):
            sec = getattr(f, "security", None)
            if getattr(f, "path", None) and not hasattr(f, "tree_id"):  # files only, not dirs
                files.append({"path": f.path, "security": sec if isinstance(sec, dict) else None})
    return {
        "revision": sha,
        "repo_status": getattr(info, "security_repo_status", None),
        "files": sorted(files, key=lambda x: x["path"]),
    }
