import json
from unittest.mock import patch

from os_llm_scan.cli import main
from os_llm_scan.manifest import Manifest, save_manifest


def _seed(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "01_metadata.json").write_text(json.dumps({
        "id": "meta-llama/Foo", "sha": "abc" * 20,
        "license": "llama-3", "siblings": [], "tags": []}))
    m = Manifest.create(scan_dir=tmp_path, repo="meta-llama/Foo", revision="main",
                        source_mode="hf", source_abs_path=None)
    save_manifest(m)


def test_dynamic_dispatch_calls_run_dynamic(tmp_path, monkeypatch):
    _seed(tmp_path)
    monkeypatch.setenv("LITELLM_BASE_URL", "http://lite:4000")
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(
        "version: 1\njudge: {}\ncategories: {prompt_injection: "
        "{engine: garak, probes: [promptinject], sample_size: 10, "
        "thresholds: {error: 0.5, warning: 0.1}}}"
    )
    with patch("os_llm_scan.runner.run_dynamic") as rd:
        rc = main(["dynamic", str(tmp_path),
                   "--endpoint", "http://api.x/v1", "--model", "Foo",
                   "--policy", str(policy_yaml)])
    assert rc == 0
    rd.assert_called_once()


def test_dynamic_requires_endpoint_or_serve_local(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        main(["dynamic", str(tmp_path), "--model", "Foo"])
