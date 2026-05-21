"""Step 11 — garak subprocess wrapper."""
from __future__ import annotations
import logging
import os
import sys
import time

from ...context import ScanContext, StageResult
from ...util.io import write_stub
from ...util.proc import run_tool
from .inference import InferenceHandle
from .judge import JudgeHandle
from .policy import Policy

log = logging.getLogger(__name__)
OUT_JSONL = "11_garak.jsonl"


def run(ctx: ScanContext, handle: InferenceHandle, judge: JudgeHandle,
        policy: Policy) -> StageResult:
    out_path = ctx.raw_dir / OUT_JSONL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    try:
        import garak  # noqa: F401
    except ImportError:
        write_stub(out_path, "garak not installed — run: uv sync --extra dynamic")
        return StageResult(False, time.monotonic() - t0, out_path, "garak not installed")

    probes = sorted({p for cat in policy.categories.values()
                       if cat.engine == "garak" for p in (cat.probes or [])
                       if not (policy.offline and p.startswith("realtoxicityprompts"))})
    if not probes:
        write_stub(out_path, "no garak categories in policy")
        return StageResult(False, time.monotonic() - t0, out_path,
                           "no garak categories in policy")

    prefix = ctx.raw_dir.resolve() / "11_garak"
    # Pass endpoint via env vars — works for garak 0.9 (OPENAI_API_BASE) and 0.10+ (OPENAI_BASE_URL)
    env = {
        **os.environ,
        "OPENAI_API_KEY": handle.api_key or "sk-none",
        "OPENAI_BASE_URL": handle.base_url,
        "OPENAI_API_BASE": handle.base_url,
    }
    res = run_tool(
        "garak",
        [sys.executable, "-m", "garak",
         "--model_type", "openai.OpenAICompatible",
         "--model_name", handle.model_id,
         "--probes", ",".join(probes),
         "--report_prefix", str(prefix)],
        stdout_path=ctx.raw_dir / "11_garak.stdout.log",
        stderr_path=ctx.raw_dir / "11_garak.stderr.log",
        timeout=3600,
        env=env,
        cwd=ctx.scan_dir,
    )
    if res.exit_code != 0:
        write_stub(out_path, f"garak exit={res.exit_code}")
        return StageResult(False, time.monotonic() - t0, out_path,
                           f"garak exit={res.exit_code}")
    report = prefix.with_suffix(".report.jsonl")
    if report.exists():
        out_path.write_bytes(report.read_bytes())
    return StageResult(True, time.monotonic() - t0, out_path, None)
