"""Stage orchestration."""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from types import ModuleType

from huggingface_hub import snapshot_download

from .context import ScanContext
from .manifest import load_manifest
from .report.html import build_html
from .report.sarif import build_sarif, write_sarif
from .stages.static import (  # noqa: F401  — populated into module namespace for mock-friendly _static_steps()
    format_inventory,
    gitleaks,
    grype,
    hf_security,
    licenses,
    metadata,
    modelaudit,
    pip_audit,
    provenance,
    semgrep,
    sha256,
    syft,
)
from .stages.static import picklescan as picklescan_mod  # noqa: F401
from .util.io import load_json

log = logging.getLogger(__name__)


def _static_steps() -> list[tuple[str, ModuleType]]:
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
        ("07_licenses",         m.licenses),
        ("08_syft",             m.syft),
        ("09_grype",            m.grype),
        ("10_gitleaks",         m.gitleaks),
        ("11_provenance",       m.provenance),
        ("12_semgrep",          m.semgrep),
        ("13_hf_security",      m.hf_security),
    ]


def run_static(ctx: ScanContext) -> list[str]:
    ctx.scan_dir.mkdir(parents=True, exist_ok=True)
    ctx.raw_dir.mkdir(exist_ok=True)
    steps = _static_steps()
    t0 = time.monotonic()
    if ctx.is_local_source:
        _symlink_local(ctx)
        skipped = _run_steps(ctx, steps, len(steps))
    else:
        # 01_metadata resolves --revision to a commit SHA; weights are then fetched by that SHA.
        skipped = _run_steps(ctx, steps[:1], len(steps))
        ctx.weights_dir.mkdir(exist_ok=True)
        _download_weights(ctx)
        skipped += _run_steps(ctx, steps[1:], len(steps), start=2)
    log.info("static stage done in %.1fs: %d ran, %d skipped%s",
             time.monotonic() - t0, len(steps) - len(skipped), len(skipped),
             f" ({', '.join(skipped)})" if skipped else "")
    return skipped


def _run_steps(ctx: ScanContext, steps: list[tuple[str, ModuleType]], total: int,
               start: int = 1) -> list[str]:
    skipped = []
    for i, (label, mod) in enumerate(steps, start):
        log.info("[%2d/%d] %s ...", i, total, label)
        r = mod.run(ctx)
        if r.ran:
            log.info("[%2d/%d] %s ok (%.1fs)", i, total, label, r.duration_s)
        else:
            log.info("[%2d/%d] %s skipped: %s", i, total, label, r.skip_reason)
            skipped.append(label)
    return skipped


def _download_weights(ctx: ScanContext) -> None:
    sha = (load_json(ctx.raw_dir / "01_metadata.json") or {}).get("sha")
    if not sha:
        raise RuntimeError("cannot pin weights: 01_metadata.json has no resolved commit SHA")
    log.info("downloading %s @ %s ...", ctx.repo, sha[:12])
    t0 = time.monotonic()
    snapshot_download(
        repo_id=ctx.repo,
        revision=sha,
        local_dir=str(ctx.weights_dir),
        token=os.environ.get("HF_TOKEN"),
    )
    log.info("download done (%.1fs)", time.monotonic() - t0)


def _symlink_local(ctx: ScanContext) -> None:
    assert ctx.local_path is not None
    if ctx.weights_dir.exists() and not ctx.weights_dir.is_symlink():
        return
    if ctx.weights_dir.is_symlink():
        ctx.weights_dir.unlink()
    ctx.weights_dir.symlink_to(ctx.local_path)


def run_report(scan_dir: Path) -> tuple[Path, Path]:
    """Regenerate SARIF + HTML from an existing scan directory."""
    manifest = load_manifest(scan_dir)
    is_local = manifest.source.get("mode") == "local_path"
    sarif = build_sarif(scan_dir, is_local_source=is_local)
    sarif_path = write_sarif(scan_dir, sarif)
    html_path = scan_dir / "reports" / "scan_report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(build_html(scan_dir, sarif))
    return sarif_path, html_path
