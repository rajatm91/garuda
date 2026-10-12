import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from garuda.context import ScanContext
from garuda.stages.static import modelaudit as step


def _ctx(tmp_path):
    ctx = ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)
    ctx.raw_dir.mkdir()
    ctx.weights_dir.mkdir()
    return ctx


def _fake_tool(exit_code: int, stdout: str | None):
    """Stand-in for run_tool: writes `stdout` to stdout_path like the real binary would."""
    def run(name, argv, *, stdout_path=None, **_):
        if stdout is not None and stdout_path is not None:
            Path(stdout_path).write_text(stdout)
        return MagicMock(exit_code=exit_code)
    return run


def _run(ctx, exit_code, stdout):
    with patch("garuda.stages.static.modelaudit.run_tool", side_effect=_fake_tool(exit_code, stdout)) as rt, \
         patch("shutil.which", return_value="/usr/bin/modelaudit"):
        return step.run(ctx), rt


def test_modelaudit_runs_and_writes_output(tmp_path: Path):
    ctx = _ctx(tmp_path)
    r, rt = _run(ctx, 0, '{"files_scanned": 3, "issues": []}')
    assert r.ran is True
    argv = rt.call_args.args[1]
    assert "modelaudit" in argv[0] and "scan" in argv
    assert "--output" not in argv  # JSON comes via stdout (macOS --output crash in 0.2.52)


def test_modelaudit_exit_1_with_findings_counts_as_ran(tmp_path: Path):
    ctx = _ctx(tmp_path)
    r, _ = _run(ctx, 1, '{"files_scanned": 3, "issues": [{"severity": "critical"}]}')
    assert r.ran is True


def test_modelaudit_crash_exit_1_without_result_is_skip(tmp_path: Path):
    ctx = _ctx(tmp_path)
    r, _ = _run(ctx, 1, "")  # uncaught Python exception also exits 1, prints no JSON
    assert r.ran is False
    assert "no scan result" in json.loads(r.output_path.read_text())["skipped"]


def test_stale_output_from_previous_run_is_not_reused(tmp_path: Path):
    ctx = _ctx(tmp_path)
    (ctx.raw_dir / "04_modelaudit.json").write_text('{"files_scanned": 9, "issues": []}')
    r, _ = _run(ctx, 1, None)  # crash before writing anything
    assert r.ran is False


def test_modelaudit_exit_2_keeps_partial_result_but_is_not_ran(tmp_path: Path):
    ctx = _ctx(tmp_path)
    partial = '{"files_scanned": 42, "has_errors": true, "issues": [{"severity": "warning"}]}'
    r, _ = _run(ctx, 2, partial)
    assert r.ran is False and "incomplete" in (r.skip_reason or "")
    assert json.loads(r.output_path.read_text())["files_scanned"] == 42  # evidence kept


def test_modelaudit_missing_binary_writes_stub(tmp_path: Path):
    ctx = _ctx(tmp_path)
    with patch("shutil.which", return_value=None):
        r = step.run(ctx)
    assert r.ran is False
    assert json.loads(r.output_path.read_text())["skipped"].startswith("modelaudit not installed")
