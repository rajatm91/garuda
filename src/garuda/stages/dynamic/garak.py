"""Step 11 — garak subprocess wrapper."""
from __future__ import annotations
import json
import logging
import shutil
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
    if shutil.which("python") is None:
        write_stub(out_path, "python not on PATH")
        return StageResult(False, time.monotonic() - t0, out_path, "python missing")

    probes = sorted({p for cat in policy.categories.values()
                       if cat.engine == "garak" for p in (cat.probes or [])
                       if not (policy.offline and p.startswith("realtoxicityprompts"))})
    if not probes:
        write_stub(out_path, "no garak categories in policy")
        return StageResult(False, time.monotonic() - t0, out_path,
                           "no garak categories in policy")

    gen_opts = ctx.scan_dir / "11_garak_generator.json"
    gen_opts.write_text(json.dumps({
        "openai": {"OpenAICompatible": {"uri": handle.base_url,
                                        "model": handle.model_id,
                                        "api_key": handle.api_key}}
    }))
    prefix = ctx.raw_dir / "11_garak"
    res = run_tool(
        "garak",
        ["python", "-m", "garak",
         "--target_type", "openai.OpenAICompatible",
         "--target_name", handle.model_id,
         "--generator_option_file", str(gen_opts),
         "--probes", ",".join(probes),
         "--report_prefix", str(prefix),
         "--narrow_output"],
        stderr_path=ctx.raw_dir / "11_garak.stderr.log",
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
