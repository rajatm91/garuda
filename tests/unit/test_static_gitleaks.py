import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from garuda.context import ScanContext
from garuda.stages.static import gitleaks as step


def _ctx(tmp_path): return ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)


def test_gitleaks_missing_binary_writes_two_stubs(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    with patch("shutil.which", return_value=None):
        r = step.run(ctx)
    assert r.ran is False
    for name in ("10_gitleaks.json", "10_gitleaks.sarif"):
        assert json.loads((ctx.raw_dir / name).read_text())["skipped"] == "gitleaks not installed"


def test_gitleaks_happy_path_runs_twice(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    def fake(name, argv, **_):  # gitleaks writes the --report-path file
        Path(argv[argv.index("--report-path") + 1]).write_text("{}")
        return MagicMock(exit_code=0)
    with patch("garuda.stages.static.gitleaks.run_tool", side_effect=fake) as rt, \
         patch("shutil.which", return_value="/usr/bin/gitleaks"):
        r = step.run(ctx)
    assert rt.call_count == 2
    assert r.ran is True
    argv = rt.call_args.args[1]
    assert argv[argv.index("--max-target-megabytes") + 1] == "100"


def test_gitleaks_stale_report_is_not_reused(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    (ctx.raw_dir / "10_gitleaks.json").write_text("[]")
    with patch("garuda.stages.static.gitleaks.run_tool") as rt, \
         patch("shutil.which", return_value="/usr/bin/gitleaks"):
        rt.return_value.exit_code = 1  # crashed, wrote nothing
        r = step.run(ctx)
    assert r.ran is False
