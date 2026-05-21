"""Step 12 — promptfoo subprocess wrapper."""
from __future__ import annotations
import logging
import shutil
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ...context import ScanContext, StageResult
from ...util.io import write_stub
from ...util.proc import run_tool
from .inference import InferenceHandle
from .judge import JudgeHandle
from .policy import Policy

log = logging.getLogger(__name__)
OUT = "12_promptfoo.json"
TEMPLATE = "_promptfoo_config.yaml.j2"


def run(ctx: ScanContext, handle: InferenceHandle, judge: JudgeHandle,
        policy: Policy) -> StageResult:
    out_path = ctx.raw_dir / OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    if shutil.which("promptfoo") is None:
        write_stub(out_path, "promptfoo not installed")
        return StageResult(False, time.monotonic() - t0, out_path, "promptfoo missing")

    pf_cats = {k: v for k, v in policy.categories.items() if v.engine == "promptfoo"}
    if not pf_cats:
        write_stub(out_path, "no promptfoo categories")
        return StageResult(False, time.monotonic() - t0, out_path,
                           "no promptfoo categories")

    env = Environment(loader=FileSystemLoader(Path(__file__).parent),
                      autoescape=False, keep_trailing_newline=True)
    rendered = env.get_template(TEMPLATE).render(handle=handle, judge=judge, policy=policy)
    cfg = ctx.scan_dir / "12_promptfoo.config.yaml"
    cfg.write_text(rendered)

    res = run_tool(
        "promptfoo",
        ["promptfoo", "redteam", "run",
         "--config", str(cfg), "--output", str(out_path),
         "--no-progress-bar"],
        stdout_path=ctx.raw_dir / "12_promptfoo.stdout.log",
        stderr_path=ctx.raw_dir / "12_promptfoo.stderr.log",
        timeout=3600,
        cwd=ctx.scan_dir,
    )
    if res.exit_code != 0 and not out_path.exists():
        write_stub(out_path, f"promptfoo exit={res.exit_code}")
        return StageResult(False, time.monotonic() - t0, out_path,
                           f"promptfoo exit={res.exit_code}")
    return StageResult(True, time.monotonic() - t0, out_path, None)
