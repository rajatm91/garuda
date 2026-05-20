import json
from unittest.mock import patch

from garuda.cli import main


def test_static_local_path_creates_scan_dir(tmp_path):
    local = tmp_path / "model"
    local.mkdir()
    (local / "config.json").write_text("{}")
    out = tmp_path / "out"
    with patch("garuda.runner.run_static", return_value=[]) as rs:
        rc = main(["static", "--local-path", str(local), "--out", str(out)])
    assert rc == 0
    assert rs.called
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["source"]["mode"] == "local_path"
    assert manifest["stages"]["static"]["ran"] is True
