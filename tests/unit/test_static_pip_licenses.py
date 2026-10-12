from pathlib import Path
from unittest.mock import patch

from garuda.context import ScanContext
from garuda.stages.static import pip_licenses as step


def _ctx(tmp_path): return ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)


def test_pip_licenses_writes_output(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    with patch("garuda.stages.static.pip_licenses.run_tool") as rt, \
         patch("shutil.which", return_value="/usr/bin/pip-licenses"):
        rt.return_value.exit_code = 0
        (ctx.raw_dir / "07_pip_licenses.json").write_text('[]')
        r = step.run(ctx)
    assert r.ran is True; rt.assert_called_once()


def test_pip_licenses_missing_binary_writes_stub(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    with patch("shutil.which", return_value=None):
        r = step.run(ctx)
    assert r.ran is False
    assert "not installed" in r.skip_reason
