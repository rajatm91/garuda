from garuda.report.html import build_html
from garuda.report.suppress import apply_suppressions, is_suppressed


def _r(uri, level="error"):
    return {"ruleId": "r", "level": level, "message": {"text": f"in {uri}"},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}}}]}


def test_readme_findings_suppressed_not_dropped(tmp_path, monkeypatch):
    monkeypatch.delenv("GARUDA_IGNORE_FILES", raising=False)
    (tmp_path / "raw").mkdir()
    sarif = {"runs": [{"tool": {"driver": {"name": "modelaudit"}}, "results": [
        _r("README.md"), _r("docs/readme.md"), _r("model.zip:README.md"), _r("config.json")]}]}
    apply_suppressions(sarif)
    res = sarif["runs"][0]["results"]
    assert [is_suppressed(r) for r in res] == [True, True, False, False]
    assert len(res) == 4  # kept in SARIF
    html = build_html(tmp_path, sarif)
    assert "2 ignored by policy" in html and "FAIL" in html  # 2 real errors still count
    assert "in README.md" not in html and "in model.zip:README.md" in html


def test_configurable_and_disableable(monkeypatch):
    monkeypatch.setenv("GARUDA_IGNORE_FILES", "")
    s = {"runs": [{"results": [_r("README.md")]}]}
    apply_suppressions(s)
    assert not is_suppressed(s["runs"][0]["results"][0])
    monkeypatch.setenv("GARUDA_IGNORE_FILES", "README.md,NOTES.txt")
    s = {"runs": [{"results": [_r("NOTES.txt")]}]}
    apply_suppressions(s)
    assert is_suppressed(s["runs"][0]["results"][0])
