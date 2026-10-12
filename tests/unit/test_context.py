from pathlib import Path

from garuda.context import ScanContext, StageResult


def test_scan_context_paths(tmp_path: Path):
    ctx = ScanContext(scan_dir=tmp_path, repo="meta-llama/Foo", revision="main", local_path=None)
    assert ctx.raw_dir == tmp_path / "raw"
    assert ctx.weights_dir == tmp_path / "weights"
    assert ctx.reports_dir == tmp_path / "reports"


def test_scan_context_local_path_mode(tmp_path: Path):
    src = tmp_path / "L"; src.mkdir()
    ctx = ScanContext(scan_dir=tmp_path / "out", repo="local:L", revision=None, local_path=src)
    assert ctx.is_local_source is True


def test_scan_context_hf_mode(tmp_path: Path):
    ctx = ScanContext(scan_dir=tmp_path, repo="meta-llama/Foo", revision="main", local_path=None)
    assert ctx.is_local_source is False


def test_stage_result_ran():
    r = StageResult(ran=True, duration_s=12.5, output_path=Path("/tmp/x.json"), skip_reason=None)
    assert r.ran is True and r.skip_reason is None


def test_stage_result_skipped():
    r = StageResult(ran=False, duration_s=0.0, output_path=Path("/tmp/x.json"),
                    skip_reason="syft missing")
    assert r.ran is False and r.skip_reason == "syft missing"
