"""Stage orchestration."""
from __future__ import annotations
import logging
import os
import time
from pathlib import Path

from huggingface_hub import snapshot_download

from .context import ScanContext
from .manifest import load_manifest, save_manifest
from .report.sarif import build_sarif, write_sarif
from .report.html import build_html
from .report.translators.garak import build_garak_run
from .report.translators.promptfoo import build_promptfoo_run
from .report.translators.eval_summary import build_eval_run
from .stages.dynamic import garak as garak_mod
from .stages.dynamic import promptfoo as promptfoo_mod
from .stages.dynamic.inference import resolve_target
from .stages.dynamic.judge import resolve_judge, sanity_ping
from .stages.dynamic.policy import apply_policy, load_policy, policy_sha256
from .stages.static import (  # noqa: F401  — populated into module namespace for mock-friendly _static_steps()
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
from .util.io import write_json

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
    if ctx.is_local_source:
        _symlink_local(ctx)
    else:
        ctx.weights_dir.mkdir(exist_ok=True)
        _download_weights(ctx)
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


def run_dynamic(scan_dir: Path, *, model_id: str, policy_path: Path) -> None:
    manifest = load_manifest(scan_dir)
    policy = load_policy(policy_path)

    print(f"[dynamic] judge  → {policy.judge.model} @ {policy.judge.base_url_env}")
    judge = resolve_judge(policy.judge)
    print(f"[dynamic] pinging judge {judge.base_url} …", flush=True)
    sanity_ping(judge)
    print("[dynamic] judge OK")

    print(f"[dynamic] target → {model_id} @ {judge.base_url}", flush=True)
    handle = resolve_target(model_id)
    print("[dynamic] target OK")

    ctx = ScanContext(scan_dir=scan_dir, repo=manifest.repo,
                      revision=manifest.revision_requested,
                      local_path=None)
    t0 = time.monotonic()
    try:
        print(f"[dynamic] running garak probes  (logs → {scan_dir}/raw/11_garak.stderr.log) …", flush=True)
        garak_mod.run(ctx, handle, judge, policy)
        print("[dynamic] garak done")
        print(f"[dynamic] running promptfoo redteam (logs → {scan_dir}/raw/12_promptfoo.stderr.log) …", flush=True)
        promptfoo_mod.run(ctx, handle, judge, policy)
        print("[dynamic] promptfoo done")
        summary = apply_policy(scan_dir, policy, policy_path)
        write_json(scan_dir / "raw" / "13_eval_summary.json", summary)
        (scan_dir / "reports").mkdir(parents=True, exist_ok=True)
        (scan_dir / "reports" / "policy.applied.yaml").write_text(policy_path.read_text())
    finally:
        handle.cleanup()

    manifest.mark_dynamic_done(
        duration_s=time.monotonic() - t0,
        inference={"mode": handle.mode, "url": handle.base_url,
                   "model_id": handle.model_id},
        judge={"provider": "litellm", "model": judge.model,
               "base_url": judge.base_url},
        policy_sha256=policy_sha256(policy_path),
    )
    save_manifest(manifest)


def run_report(scan_dir: Path) -> tuple[Path, Path]:
    """Regenerate SARIF + HTML from an existing scan directory."""
    manifest = load_manifest(scan_dir)
    is_local = manifest.source.get("mode") == "local_path"
    dynamic_runs = [
        r for r in (
            build_garak_run(scan_dir),
            build_promptfoo_run(scan_dir),
            build_eval_run(scan_dir),
        ) if r
    ]
    sarif = build_sarif(scan_dir, is_local_source=is_local, dynamic_runs=dynamic_runs)
    sarif_path = write_sarif(scan_dir, sarif)
    html_path = scan_dir / "reports" / "scan_report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(build_html(scan_dir, sarif, manifest))
    return sarif_path, html_path
