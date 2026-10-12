"""Step 01 — capture HF model_info OR read on-disk config.json (offline mode)."""
from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi

from ...context import ScanContext, StageResult
from ...util.io import write_json, write_stub

log = logging.getLogger(__name__)
OUT = "01_metadata.json"
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def run(ctx: ScanContext) -> StageResult:
    out_path = ctx.raw_dir / OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    try:
        data = _from_local(ctx.local_path, ctx.repo) if ctx.is_local_source \
               else _from_hf(ctx.repo, ctx.revision or "main")
        write_json(out_path, data)
        return StageResult(ran=True, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=None)
    except Exception as e:
        log.exception("metadata step failed")
        reason = f"hf metadata error: {e}"
        write_stub(out_path, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=reason)


def _from_hf(repo: str, revision: str) -> dict[str, Any]:
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    info = api.model_info(repo, revision=revision, files_metadata=True)
    card = info.card_data.to_dict() if info.card_data else {}
    return {
        "id": info.id, "sha": info.sha, "revision_requested": revision,
        "tags": list(info.tags or []),
        "license": card.get("license"),
        "license_name": card.get("license_name"),
        "license_link": card.get("license_link"),
        "pipeline_tag": info.pipeline_tag,
        "last_modified": str(info.last_modified) if info.last_modified else None,
        "downloads": info.downloads,
        "library_name": info.library_name,
        "siblings": [
            {"name": s.rfilename, "size": getattr(s, "size", None),
             "blob_id": getattr(s, "blob_id", None), "lfs": bool(getattr(s, "lfs", False))}
            for s in (info.siblings or [])
        ],
    }


def _from_local(local: Path, repo: str) -> dict[str, Any]:
    import json
    config = {}
    cfg_path = local / "config.json"
    if cfg_path.exists():
        config = json.loads(cfg_path.read_text())
    license_val = None
    readme = local / "README.md"
    if readme.exists():
        m = _FRONTMATTER.search(readme.read_text())
        if m:
            import yaml
            try:
                fm = yaml.safe_load(m.group(1)) or {}
                license_val = fm.get("license")
            except yaml.YAMLError:
                pass
    return {
        "id": repo, "sha": None, "revision_requested": None,
        "tags": [], "license": license_val,
        "license_name": None, "license_link": None,
        "pipeline_tag": config.get("model_type"),
        "last_modified": None, "downloads": None,
        "library_name": "local",
        "siblings": [],
    }
