import json

from garuda.report.sarif import build_sarif, write_sarif, SARIF_VERSION


def test_build_sarif_minimal(tmp_path):
    (tmp_path / "raw").mkdir()
    log = build_sarif(tmp_path, is_local_source=False)
    assert log["version"] == "2.1.0"
    assert log["runs"][0]["tool"]["driver"]["name"] == "os-llm-review"


def test_write_sarif_path(tmp_path):
    (tmp_path / "raw").mkdir()
    log = build_sarif(tmp_path, is_local_source=True)
    out = write_sarif(tmp_path, log)
    assert out == tmp_path / "reports" / "scan_results.sarif"
    assert json.loads(out.read_text())["version"] == "2.1.0"


def test_sarif_version_constant():
    assert SARIF_VERSION == "2.1.0"
