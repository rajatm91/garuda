import json
from pathlib import Path
from unittest.mock import patch

from garuda.context import ScanContext
from garuda.stages.static import modelaudit as step


def _ctx(tmp_path): return ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)


def test_modelaudit_runs_and_writes_output(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir(); ctx.weights_dir.mkdir()
    with patch("garuda.stages.static.modelaudit.run_tool") as rt, \
         patch("shutil.which", return_value="/usr/bin/modelaudit"):
        rt.return_value.exit_code = 0
        (ctx.raw_dir / "04_modelaudit.json").write_text(
            '{"scanner_version":"1.0","issues":[],"summary":{"total_issues":0}}')
        r = step.run(ctx)
    assert r.ran is True
    rt.assert_called_once()
    argv = rt.call_args.args[1]
    assert "modelaudit" in argv[0] and "scan" in argv


def test_modelaudit_exit_1_with_findings_counts_as_ran(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir(); ctx.weights_dir.mkdir()
    with patch("garuda.stages.static.modelaudit.run_tool") as rt, \
         patch("shutil.which", return_value="/usr/bin/modelaudit"):
        rt.return_value.exit_code = 1
        (ctx.raw_dir / "04_modelaudit.json").write_text('{"issues":[{"severity":"critical"}]}')
        r = step.run(ctx)
    assert r.ran is True


def test_modelaudit_exit_2_is_skip(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir(); ctx.weights_dir.mkdir()
    with patch("garuda.stages.static.modelaudit.run_tool") as rt, \
         patch("shutil.which", return_value="/usr/bin/modelaudit"):
        rt.return_value.exit_code = 2
        r = step.run(ctx)
    assert r.ran is False
    assert json.loads(r.output_path.read_text())["skipped"] == "modelaudit exit=2"


def test_modelaudit_missing_binary_writes_stub(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir(); ctx.weights_dir.mkdir()
    with patch("shutil.which", return_value=None):
        r = step.run(ctx)
    assert r.ran is False
    assert json.loads(r.output_path.read_text())["skipped"].startswith("modelaudit not installed")
