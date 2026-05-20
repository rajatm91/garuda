from pathlib import Path
from unittest.mock import patch, MagicMock

from garuda.context import ScanContext
from garuda.stages.dynamic import garak
from garuda.stages.dynamic.inference import InferenceHandle
from garuda.stages.dynamic.judge import JudgeHandle
from garuda.stages.dynamic.policy import (
    Policy, CategoryPolicy, FailureRateThresholds,
)


def _ctx(tmp_path): return ScanContext(scan_dir=tmp_path, repo="x",
                                       revision=None, local_path=None)


def _handle(): return InferenceHandle(base_url="http://x", model_id="m",
                                      api_key="k", mode="litellm")


def _judge(): return JudgeHandle(base_url="http://j", api_key="k",
                                 model="gemini-2.5-flash", temperature=0, max_tokens=10)


def _policy() -> Policy:
    return Policy(version=1, categories={
        "prompt_injection": CategoryPolicy(
            engine="garak", probes=["promptinject"], sample_size=100,
            thresholds=FailureRateThresholds(error=0.05, warning=0.01)),
    })


def test_garak_invocation_includes_probes(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.scan_dir.mkdir(exist_ok=True); ctx.raw_dir.mkdir()
    with patch("garuda.stages.dynamic.garak.run_tool") as rt, \
         patch("shutil.which", return_value="/usr/bin/python"):
        rt.return_value = MagicMock(exit_code=0)
        prefix = ctx.raw_dir / "11_garak"
        prefix.with_suffix(".report.jsonl").write_text('{"passed":true}\n')
        r = garak.run(ctx, _handle(), _judge(), _policy())
    assert r.ran is True
    argv = rt.call_args.args[1]
    assert "--target_type" in argv
    assert "--target_name" in argv
    assert "--probes" in argv
    assert "promptinject" in argv[argv.index("--probes") + 1]


def test_garak_no_categories_writes_stub(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.scan_dir.mkdir(exist_ok=True); ctx.raw_dir.mkdir()
    empty_policy = Policy(version=1, categories={
        "bias": CategoryPolicy(engine="promptfoo", plugins=["bias"], sample_size=10,
                               thresholds=FailureRateThresholds(error=0.5, warning=0.1))
    })
    r = garak.run(ctx, _handle(), _judge(), empty_policy)
    assert r.ran is False
    assert "no garak" in r.skip_reason
