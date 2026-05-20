import json
from pathlib import Path
from unittest.mock import patch
from os_llm_scan.context import ScanContext
from os_llm_scan.stages.static import grype as step


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
    with patch("os_llm_scan.stages.static.grype.run_tool") as rt, \
         patch("shutil.which", return_value="/usr/bin/grype"):
        rt.return_value.exit_code = 0
        (ctx.raw_dir / "09_grype.json").write_text("{}")
        (ctx.raw_dir / "09_grype.sarif").write_text("{}")
        r = step.run(ctx)
    assert rt.call_count == 2
    assert r.ran is True
