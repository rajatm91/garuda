import json
from pathlib import Path

from garuda.context import ScanContext
from garuda.stages.static import licenses as step


def test_inventories_shipped_license_files_and_declared(tmp_path: Path):
    ctx = ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)
    ctx.raw_dir.mkdir(); ctx.weights_dir.mkdir()
    (ctx.raw_dir / "01_metadata.json").write_text(json.dumps({"license": "apache-2.0"}))
    (ctx.weights_dir / "LICENSE").write_text("\n  Apache License\nVersion 2.0\n")
    (ctx.weights_dir / "NOTICE.md").write_text("Notice")
    (ctx.weights_dir / "LICENSE-MODEL").write_text("Model license")
    (ctx.weights_dir / "README.md").write_text("not a license")
    (ctx.weights_dir / ".cache").mkdir()
    (ctx.weights_dir / ".cache" / "LICENSE").write_text("hf cache, not model")
    r = step.run(ctx)
    assert r.ran is True
    out = json.loads(r.output_path.read_text())
    assert out["declared"]["license"] == "apache-2.0"
    assert [f["path"] for f in out["files"]] == ["LICENSE", "LICENSE-MODEL", "NOTICE.md"]
    assert out["files"][0]["first_line"] == "Apache License"


def test_no_license_files(tmp_path: Path):
    ctx = ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)
    ctx.raw_dir.mkdir(); ctx.weights_dir.mkdir()
    out = json.loads(step.run(ctx).output_path.read_text())
    assert out["files"] == [] and out["declared"]["license"] is None
