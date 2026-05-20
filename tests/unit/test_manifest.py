import json
from pathlib import Path

from os_llm_scan.manifest import Manifest, load_manifest, save_manifest


def test_manifest_create_writes_minimal_shape(tmp_path: Path):
    m = Manifest.create(scan_dir=tmp_path, repo="meta-llama/Foo", revision="main",
                        source_mode="hf", source_abs_path=None)
    save_manifest(m)
    j = json.loads((tmp_path / "manifest.json").read_text())
    assert j["version"] == "2.0.0"
    assert j["repo"] == "meta-llama/Foo"
    assert j["source"]["mode"] == "hf"
    assert j["stages"]["static"]["ran"] is False
    assert j["stages"]["dynamic"]["ran"] is False


def test_manifest_local_source(tmp_path: Path):
    m = Manifest.create(scan_dir=tmp_path, repo="local:L", revision=None,
                        source_mode="local_path", source_abs_path="/data/L")
    save_manifest(m)
    j = json.loads((tmp_path / "manifest.json").read_text())
    assert j["source"]["mode"] == "local_path"
    assert j["source"]["abs_path"] == "/data/L"


def test_load_round_trip(tmp_path: Path):
    m = Manifest.create(scan_dir=tmp_path, repo="x", revision="main",
                        source_mode="hf", source_abs_path=None)
    save_manifest(m)
    loaded = load_manifest(tmp_path)
    assert loaded.repo == "x" and loaded.version == "2.0.0"


def test_manifest_mark_static_done(tmp_path: Path):
    m = Manifest.create(scan_dir=tmp_path, repo="x", revision="main",
                        source_mode="hf", source_abs_path=None)
    m.mark_static_done(duration_s=400.0, skipped_steps=["08_syft"])
    save_manifest(m)
    j = json.loads((tmp_path / "manifest.json").read_text())
    assert j["stages"]["static"]["ran"] is True
    assert j["stages"]["static"]["duration_s"] == 400.0
    assert j["stages"]["static"]["skipped_steps"] == ["08_syft"]
