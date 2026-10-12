import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from garuda.context import ScanContext
from garuda.stages.static import grype as step


def _ctx(tmp_path): return ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)


def test_grype_missing_binary_writes_two_stubs(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    with patch("shutil.which", return_value=None):
        r = step.run(ctx)
    assert r.ran is False
    for name in ("09_grype.json", "09_grype.sarif"):
        assert json.loads((ctx.raw_dir / name).read_text())["skipped"] == "grype not installed"


def test_grype_missing_sbom_writes_two_stubs(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    # No 08_sbom.cdx.json present
    with patch("shutil.which", return_value="/usr/bin/grype"):
        r = step.run(ctx)
    assert r.ran is False
    for name in ("09_grype.json", "09_grype.sarif"):
        assert "missing or stub" in json.loads((ctx.raw_dir / name).read_text())["skipped"]


def test_grype_happy_path_runs_twice(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    (ctx.raw_dir / "08_sbom.cdx.json").write_text('{"bomFormat": "CycloneDX"}')
    def fake(name, argv, **_):  # grype writes --file in the requested -o format
        out = {"json": '{"matches": []}', "sarif": '{"runs": []}'}[argv[argv.index("-o") + 1]]
        Path(argv[argv.index("--file") + 1]).write_text(out)
        return MagicMock(exit_code=0)
    with patch("garuda.stages.static.grype.run_tool", side_effect=fake) as rt, \
         patch("shutil.which", return_value="/usr/bin/grype"):
        r = step.run(ctx)
    assert rt.call_count == 2
    assert r.ran is True


def test_grype_empty_output_is_not_ran(tmp_path: Path):
    """Old grype + unusable vuln DB wrote 0-byte files that used to count as success."""
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    (ctx.raw_dir / "08_sbom.cdx.json").write_text('{"bomFormat": "CycloneDX"}')
    def fake(name, argv, **_):
        Path(argv[argv.index("--file") + 1]).write_text("")
        return MagicMock(exit_code=0)
    with patch("garuda.stages.static.grype.run_tool", side_effect=fake), \
         patch("shutil.which", return_value="/usr/bin/grype"):
        r = step.run(ctx)
    assert r.ran is False and "no valid result" in (r.skip_reason or "")
