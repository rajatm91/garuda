"""Step 01 — capture HF model_info OR read on-disk config.json (offline mode)."""
from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi, hf_hub_download

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
        data = _from_local(ctx.local_path, ctx.repo) if ctx.local_path is not None \
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
    st = info.safetensors
    return {
        "id": info.id, "author": info.author, "sha": info.sha, "revision_requested": revision,
        "gated": info.gated,
        "base_model": card.get("base_model"),
        "parameters": {"total": st.total, "by_dtype": st.parameters} if st else None,
        "config": _hf_config(repo, info.sha),
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
             "blob_id": getattr(s, "blob_id", None), "lfs": bool(getattr(s, "lfs", False)),
             "sha256": s.lfs.sha256 if s.lfs else None}
            for s in (info.siblings or [])
        ],
    }


def _hf_config(repo: str, sha: str | None) -> dict[str, Any] | None:
    """config.json at the pinned commit (architecture, context window, modalities)."""
    import json
    try:
        path = hf_hub_download(repo, "config.json", revision=sha,
                               token=os.environ.get("HF_TOKEN"))
    except Exception as e:  # noqa: BLE001 — repos without config.json (e.g. GGUF-only)
        log.warning("config.json unavailable: %s", e)
        return None
    return json.loads(Path(path).read_text())


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
        "config": config or None,
        "siblings": [{"name": str(p.relative_to(local))} for p in sorted(local.rglob("*"))
                     if p.is_file() and not p.is_symlink()],
    }
