import json
from pathlib import Path
from unittest.mock import patch

from garuda.context import ScanContext
from garuda.stages.static import picklescan as step


def _ctx(tmp_path): return ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)


def test_skips_when_no_unsafe_files(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    (ctx.raw_dir / "03_format_inventory.json").write_text(json.dumps({
        "safetensors":[{"path":"m.safetensors","size":1,"sha256":"x"*64}],
        "unsafe_format":[], "other":[],
        "counts":{"safetensors":1,"unsafe_format":0,"other":0}}))
    r = step.run(ctx)
    out = json.loads(r.output_path.read_text())
    assert out["results"] == []
    assert "no unsafe-format" in out["note"].lower()


def test_runs_one_subprocess_per_unsafe_file(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir(); ctx.weights_dir.mkdir()
    (ctx.weights_dir / "pytorch_model.bin").write_bytes(b"x")
    (ctx.raw_dir / "03_format_inventory.json").write_text(json.dumps({
        "safetensors":[],
        "unsafe_format":[{"path":"pytorch_model.bin","size":1,"sha256":"x"*64}],
        "other":[], "counts":{"safetensors":0,"unsafe_format":1,"other":0}}))
    with patch("garuda.stages.static.picklescan.subprocess.run") as r:
        r.return_value.returncode = 0
        r.return_value.stdout = "ok"; r.return_value.stderr = ""
        res = step.run(ctx)
    assert r.called
    out = json.loads(res.output_path.read_text())
    assert len(out["results"]) == 1
    assert out["results"][0]["path"] == "pytorch_model.bin"
