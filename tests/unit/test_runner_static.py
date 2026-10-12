from pathlib import Path
from unittest.mock import patch, MagicMock

from garuda.context import ScanContext, StageResult
from garuda.runner import run_static


def _ctx(tmp_path):
    return ScanContext(scan_dir=tmp_path, repo="x", revision="main", local_path=None)


def test_run_static_calls_every_step(tmp_path: Path):
    ctx = _ctx(tmp_path)
    ok = StageResult(True, 0.1, tmp_path / "x.json", None)
    fake = MagicMock(return_value=ok)
    with patch.multiple(
        "garuda.runner",
        metadata=MagicMock(run=fake),
        sha256=MagicMock(run=fake),
        format_inventory=MagicMock(run=fake),
        modelaudit=MagicMock(run=fake),
        picklescan_mod=MagicMock(run=fake),
        pip_audit=MagicMock(run=fake),
        pip_licenses=MagicMock(run=fake),
        syft=MagicMock(run=fake),
        grype=MagicMock(run=fake),
        gitleaks=MagicMock(run=fake),
        _download_weights=MagicMock(),
    ):
        run_static(ctx)
    assert fake.call_count == 10


def test_run_static_collects_skipped_steps(tmp_path: Path):
    ctx = _ctx(tmp_path)
    ok = StageResult(True, 0.1, tmp_path / "x.json", None)
    skip = StageResult(False, 0.1, tmp_path / "y.json", "missing")
    seq = iter([ok] * 7 + [skip] + [ok] * 2)
    fake = MagicMock(side_effect=lambda _ctx: next(seq))
    with patch.multiple(
        "garuda.runner",
        metadata=MagicMock(run=fake),
        sha256=MagicMock(run=fake),
        format_inventory=MagicMock(run=fake),
        modelaudit=MagicMock(run=fake),
        picklescan_mod=MagicMock(run=fake),
        pip_audit=MagicMock(run=fake),
        pip_licenses=MagicMock(run=fake),
        syft=MagicMock(run=fake),
        grype=MagicMock(run=fake),
        gitleaks=MagicMock(run=fake),
        _download_weights=MagicMock(),
    ):
        skipped = run_static(ctx)
    assert skipped == ["08_syft"]


def test_weights_downloaded_by_resolved_sha_after_metadata(tmp_path: Path):
    ctx = _ctx(tmp_path)
    ok = StageResult(True, 0.1, tmp_path / "x.json", None)

    def fake_metadata(c):
        (c.raw_dir / "01_metadata.json").write_text('{"sha": "deadbeef"}')
        return ok

    fake = MagicMock(return_value=ok)
    with patch.multiple(
        "garuda.runner",
        metadata=MagicMock(run=fake_metadata),
        sha256=MagicMock(run=fake),
        format_inventory=MagicMock(run=fake),
        modelaudit=MagicMock(run=fake),
        picklescan_mod=MagicMock(run=fake),
        pip_audit=MagicMock(run=fake),
        pip_licenses=MagicMock(run=fake),
        syft=MagicMock(run=fake),
        grype=MagicMock(run=fake),
        gitleaks=MagicMock(run=fake),
    ), patch("garuda.runner.snapshot_download") as dl:
        run_static(ctx)
    assert dl.call_args.kwargs["revision"] == "deadbeef"
    assert fake.call_count == 9


def test_download_without_sha_fails(tmp_path: Path):
    import pytest
    from garuda.runner import _download_weights
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    (ctx.raw_dir / "01_metadata.json").write_text('{"skipped": "hf metadata error"}')
    with patch("garuda.runner.snapshot_download") as dl, pytest.raises(RuntimeError):
        _download_weights(ctx)
    dl.assert_not_called()
