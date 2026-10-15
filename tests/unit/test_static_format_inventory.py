import json
from pathlib import Path

from garuda.context import ScanContext
from garuda.stages.static import format_inventory as step


def _ctx(tmp_path): return ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)


def test_partitions_by_extension(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    sha = {"root": "/x", "files": [
        {"path": "model.safetensors", "size": 1, "sha256": "a"*64},
        {"path": "pytorch_model.bin", "size": 1, "sha256": "b"*64},
        {"path": "model.pt",          "size": 1, "sha256": "c"*64},
        {"path": "model.gguf",        "size": 1, "sha256": "d"*64},
    ]}
    (ctx.raw_dir / "02_sha256.json").write_text(json.dumps(sha))
    r = step.run(ctx)
    out = json.loads(r.output_path.read_text())
    assert out["counts"]["safetensors"] == 1
    assert out["counts"]["unsafe_format"] == 2
    assert out["counts"]["other"] == 1


def test_missing_sha_input_writes_stub(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.raw_dir.mkdir()
    r = step.run(ctx)
    assert r.ran is False
    assert r.skip_reason and "02_sha256.json" in r.skip_reason


def test_ckpt_is_unsafe_and_raises_olr001(tmp_path: Path):
    from garuda.report.translators import review
    from garuda.stages.static import sha256
    ctx = _ctx(tmp_path); ctx.weights_dir.mkdir(); ctx.raw_dir.mkdir()
    (ctx.weights_dir / "model.ckpt").write_bytes(b"x")
    sha256.run(ctx)
    out = json.loads(step.run(ctx).output_path.read_text())
    assert [f["path"] for f in out["unsafe_format"]] == ["model.ckpt"]
    assert "model.ckpt" in (ctx.raw_dir / "02_sha256.json").read_text()
    run = review.build_review_run(tmp_path, is_local_source=True)
    olr001 = [r for r in run["results"] if r["ruleId"] == "OLR001"]
    assert len(olr001) == 1 and olr001[0]["level"] == "warning"
