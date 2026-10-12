import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from garuda.context import ScanContext
from garuda.stages.static import syft as step


def _ctx(tmp_path): return ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)


def test_missing_syft_writes_two_stubs(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    with patch("shutil.which", return_value=None):
        r = step.run(ctx)
    assert r.ran is False
    for name in ("08_sbom.cdx.json", "08_sbom.spdx.json"):
        assert json.loads((ctx.raw_dir / name).read_text())["skipped"] == "syft not installed"


def test_runs_both_formats_when_present(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    def fake(name, argv, **_):
        fmt, path = argv[argv.index("-o") + 1].split("=", 1)
        Path(path).write_text('{"bomFormat": "CycloneDX"}' if fmt.startswith("cyclonedx")
                              else '{"spdxVersion": "SPDX-2.3"}')
        return MagicMock(exit_code=0)
    with patch("garuda.stages.static.syft.run_tool", side_effect=fake) as rt, \
         patch("shutil.which", return_value="/usr/bin/syft"):
        r = step.run(ctx)
    assert rt.call_count == 2
    assert r.ran is True
