import json
from pathlib import Path
from os_llm_scan.context import ScanContext
from os_llm_scan.stages.static import format_inventory as step


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
    assert "02_sha256.json" in r.skip_reason
