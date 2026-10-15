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


def test_relative_out_and_local_path_become_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "model").mkdir()
    with patch("garuda.runner.run_static", return_value=[]) as rs:
        rc = main(["static", "--local-path", "model", "--out", "out"])
    assert rc == 0
    ctx = rs.call_args.args[0]
    assert ctx.scan_dir == tmp_path.resolve() / "out"
    assert ctx.local_path == tmp_path.resolve() / "model"


def test_banner_shown_unless_quiet(tmp_path, capsys):
    (tmp_path / "model").mkdir()
    with patch("garuda.runner.run_static", return_value=[]):
        main(["static", "--local-path", str(tmp_path / "model"), "--out", str(tmp_path / "a")])
        assert "Scan dir" in capsys.readouterr().err
        main(["static", "-q", "--local-path", str(tmp_path / "model"), "--out", str(tmp_path / "b")])
        assert "garuda" not in capsys.readouterr().err
