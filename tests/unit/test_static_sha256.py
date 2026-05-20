import json
from pathlib import Path

from os_llm_scan.context import ScanContext
from os_llm_scan.stages.static import sha256 as step


def _ctx(tmp_path): return ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)


def test_hashes_known_extensions(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.weights_dir.mkdir(); ctx.raw_dir.mkdir()
    (ctx.weights_dir / "model.safetensors").write_bytes(b"a" * 100)
    (ctx.weights_dir / "pytorch_model.bin").write_bytes(b"b" * 50)
    (ctx.weights_dir / "tokenizer.json").write_text("{}")
    r = step.run(ctx)
    out = json.loads(r.output_path.read_text())
    names = sorted(f["path"] for f in out["files"])
    assert names == ["model.safetensors", "pytorch_model.bin"]
    for f in out["files"]:
        assert len(f["sha256"]) == 64


def test_empty_weights_dir_writes_empty_list(tmp_path: Path):
    ctx = _ctx(tmp_path); ctx.weights_dir.mkdir(); ctx.raw_dir.mkdir()
    r = step.run(ctx)
    assert json.loads(r.output_path.read_text()) == {"root": str(ctx.weights_dir), "files": []}
