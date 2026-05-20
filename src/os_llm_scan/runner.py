"""Stage orchestration."""
from __future__ import annotations
import logging, os
from pathlib import Path

from huggingface_hub import snapshot_download

from .context import ScanContext
from .stages.static import (
    metadata,
    sha256,
    format_inventory,
    modelaudit,
    pip_audit,
    pip_licenses,
    syft,
    grype,
    gitleaks,
)
from .stages.static import picklescan as picklescan_mod  # noqa: F401

log = logging.getLogger(__name__)


def _static_steps() -> list[tuple[str, object]]:
    """Resolve step modules via current module attributes so they are mock-friendly."""
    import sys
    m = sys.modules[__name__]
    return [
        ("01_metadata",         m.metadata),
        ("02_sha256",           m.sha256),
        ("03_format_inventory", m.format_inventory),
        ("04_modelaudit",       m.modelaudit),
        ("05_picklescan",       m.picklescan_mod),
        ("06_pip_audit",        m.pip_audit),
        ("07_pip_licenses",     m.pip_licenses),
        ("08_syft",             m.syft),
        ("09_grype",            m.grype),
        ("10_gitleaks",         m.gitleaks),
    ]


def run_static(ctx: ScanContext) -> list[str]:
    ctx.scan_dir.mkdir(parents=True, exist_ok=True)
    ctx.raw_dir.mkdir(exist_ok=True)
    ctx.weights_dir.mkdir(exist_ok=True)
    if not ctx.is_local_source:
        _download_weights(ctx)
    else:
        _symlink_local(ctx)
    skipped = []
    for label, mod in _static_steps():
        log.info("===== %s =====", label)
        r = mod.run(ctx)
        if not r.ran:
            skipped.append(label)
    return skipped


def _download_weights(ctx: ScanContext) -> None:
    rev = ctx.revision or "main"
    snapshot_download(
        repo_id=ctx.repo,
        revision=rev,
        local_dir=str(ctx.weights_dir),
        local_dir_use_symlinks=False,
        token=os.environ.get("HF_TOKEN"),
    )


def _symlink_local(ctx: ScanContext) -> None:
    assert ctx.local_path is not None
    if ctx.weights_dir.exists() and not ctx.weights_dir.is_symlink():
        return
    if ctx.weights_dir.is_symlink():
        ctx.weights_dir.unlink()
    ctx.weights_dir.symlink_to(ctx.local_path)
