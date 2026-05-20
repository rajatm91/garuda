from pathlib import Path
from unittest.mock import patch
from garuda.context import ScanContext
from garuda.stages.static import pip_audit as step


def _ctx(tmp_path): return ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)


def test_pip_audit_writes_output(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    with patch("garuda.stages.static.pip_audit.run_tool") as rt, \
         patch("shutil.which", return_value="/usr/bin/pip-audit"):
        rt.return_value.exit_code = 0
        (ctx.raw_dir / "06_pip_audit.json").write_text('{"dependencies":[]}')
        r = step.run(ctx)
    assert r.ran is True; rt.assert_called_once()


def test_pip_audit_missing_binary_writes_stub(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    with patch("shutil.which", return_value=None):
        r = step.run(ctx)
    assert r.ran is False
    assert "not installed" in r.skip_reason
