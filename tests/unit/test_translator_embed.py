import json

from os_llm_scan.report.translators.embed import embed_runs


def test_embed_empty_path_returns_empty(tmp_path):
    assert embed_runs(tmp_path / "nonexistent.sarif") == []


def test_embed_valid_sarif_returns_runs(tmp_path):
    sarif_path = tmp_path / "x.sarif"
    sarif_path.write_text(json.dumps({
        "version": "2.1.0",
        "runs": [{"tool": {"driver": {"name": "x"}}, "results": []}],
    }))
    runs = embed_runs(sarif_path)
    assert len(runs) == 1
    assert runs[0]["tool"]["driver"]["name"] == "x"


def test_embed_malformed_json_returns_empty(tmp_path):
    sarif_path = tmp_path / "broken.sarif"
    sarif_path.write_text("not valid json {{{")
    assert embed_runs(sarif_path) == []
