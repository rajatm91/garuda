from pathlib import Path
from unittest.mock import patch, MagicMock

from garuda.context import ScanContext
from garuda.stages.dynamic import promptfoo
from garuda.stages.dynamic.inference import InferenceHandle
from garuda.stages.dynamic.judge import JudgeHandle
from garuda.stages.dynamic.policy import (
    Policy, CategoryPolicy, FailureRateThresholds, PassRateThresholds,
)


def _ctx(tmp_path): return ScanContext(scan_dir=tmp_path, repo="x",
                                       revision=None, local_path=None)


def _policy() -> Policy:
    return Policy(version=1, categories={
        "bias": CategoryPolicy(engine="promptfoo", plugins=["bias"], sample_size=42,
            thresholds=FailureRateThresholds(error=0.1, warning=0.05)),
        "hallucination": CategoryPolicy(engine="promptfoo", plugins=["hallucination"],
            sample_size=77,
            thresholds=PassRateThresholds(pass_rate_error=0.7, pass_rate_warning=0.85)),
    })


def test_renders_config_with_sample_sizes(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.scan_dir.mkdir(exist_ok=True); ctx.raw_dir.mkdir()
    h = InferenceHandle("http://x", "m", "k", "endpoint")
    j = JudgeHandle("http://j", "k", "gemini-2.5-flash", 0, 10)
    with patch("garuda.stages.dynamic.promptfoo.run_tool") as rt, \
         patch("shutil.which", return_value="/usr/bin/promptfoo"):
        rt.return_value = MagicMock(exit_code=0)
        (ctx.raw_dir / "12_promptfoo.json").write_text("{}")
        r = promptfoo.run(ctx, h, j, _policy())
    assert r.ran is True
    cfg = (ctx.scan_dir / "12_promptfoo.config.yaml").read_text()
    assert "numTests: 42" in cfg
    assert "numTests: 77" in cfg
    assert "gemini-2.5-flash" in cfg


def test_no_promptfoo_categories_stubs(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.scan_dir.mkdir(exist_ok=True); ctx.raw_dir.mkdir()
    h = InferenceHandle("http://x", "m", "k", "endpoint")
    j = JudgeHandle("http://j", "k", "g", 0, 10)
    empty = Policy(version=1, categories={
        "prompt_injection": CategoryPolicy(
            engine="garak", probes=["promptinject"], sample_size=10,
            thresholds=FailureRateThresholds(error=0.5, warning=0.1)),
    })
    with patch("shutil.which", return_value="/usr/bin/promptfoo"):
        r = promptfoo.run(ctx, h, j, empty)
    assert r.ran is False
