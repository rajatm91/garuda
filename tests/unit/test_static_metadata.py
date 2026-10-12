import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from garuda.context import ScanContext
from garuda.stages.static import metadata


def _ctx(tmp_path: Path, local: Path | None = None) -> ScanContext:
    return ScanContext(scan_dir=tmp_path, repo="meta-llama/Foo", revision="main", local_path=local)


def test_metadata_writes_01_metadata(tmp_path: Path):
    ctx = _ctx(tmp_path)
    fake_info = MagicMock()
    fake_info.id = "meta-llama/Foo"; fake_info.sha = "abc123" * 10
    fake_info.tags = ["llama"]; fake_info.pipeline_tag = "text-generation"
    fake_info.last_modified = None; fake_info.downloads = 42
    fake_info.library_name = "transformers"; fake_info.siblings = []
    card = MagicMock(); card.to_dict.return_value = {"license": "llama-3"}
    fake_info.card_data = card
    with patch("garuda.stages.static.metadata.HfApi") as Api:
        Api.return_value.model_info.return_value = fake_info
        r = metadata.run(ctx)
    out = json.loads(r.output_path.read_text())
    assert r.ran is True
    assert out["id"] == "meta-llama/Foo"
    assert out["license"] == "llama-3"


def test_metadata_local_path_reads_config(tmp_path: Path):
    local = tmp_path / "L"; local.mkdir()
    (local / "config.json").write_text('{"model_type":"llama"}')
    (local / "README.md").write_text("---\nlicense: apache-2.0\n---\n# hi")
    ctx = _ctx(tmp_path / "out", local=local)
    r = metadata.run(ctx)
    out = json.loads(r.output_path.read_text())
    assert out["sha"] is None
    assert out["license"] == "apache-2.0"
    assert out["library_name"] == "local"


def test_metadata_hf_failure_writes_stub(tmp_path: Path):
    ctx = _ctx(tmp_path)
    with patch("garuda.stages.static.metadata.HfApi") as Api:
        Api.return_value.model_info.side_effect = RuntimeError("401")
        r = metadata.run(ctx)
    assert r.ran is False
    assert json.loads(r.output_path.read_text())["skipped"].startswith("hf metadata error")
