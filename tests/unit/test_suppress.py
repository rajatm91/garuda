
from garuda.report.html import build_html
from garuda.report.suppress import apply_suppressions, is_suppressed


def _r(uri, level="error"):
    return {"ruleId": "r", "level": level, "message": {"text": f"in {uri}"},
            "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}}}]}


def _model(tmp_path):
    (tmp_path / "raw").mkdir(); w = tmp_path / "weights"; (w / "docs").mkdir(parents=True)
    (w / "README.md").write_text("# Model\ngit clone https://x\n")
    (w / "docs" / "readme.md").write_text("docs\n")
    (w / "sub").mkdir(); (w / "sub" / "README.md").write_bytes(b"\x80\x04\x95pickle\x00")
    (tmp_path / "outside.md").write_text("x")
    (w / "linked").mkdir(); (w / "linked" / "README.md").symlink_to(tmp_path / "outside.md")
    return tmp_path


def test_only_real_text_readmes_suppressed(tmp_path, monkeypatch):
    monkeypatch.delenv("GARUDA_IGNORE_FILES", raising=False)
    d = _model(tmp_path)
    sarif = {"runs": [{"tool": {"driver": {"name": "modelaudit"}}, "results": [
        _r("README.md"), _r("docs/readme.md"), _r("model.zip:README.md"),
        _r("sub/README.md"),      # pickle bytes named README.md
        _r("linked/README.md"),   # symlink out of the model
        _r("gone/README.md"),     # not on disk
        _r("config.json")]}]}
    apply_suppressions(sarif, d)
    assert [is_suppressed(r) for r in sarif["runs"][0]["results"]] == [
        True, True, False, False, False, False, False]
    html = build_html(d, sarif)
    assert "2 ignored by policy" in html and "FAIL" in html


def test_tool_emitted_suppressions_are_not_honoured(tmp_path):
    res = _r("modeling.py")
    res["suppressions"] = [{"kind": "inSource"}]  # e.g. a "# nosemgrep" comment in model code
    assert not is_suppressed(res)


def test_configurable_and_disableable(tmp_path, monkeypatch):
    d = _model(tmp_path)
    (d / "weights" / "NOTES.txt").write_text("n\n")
    monkeypatch.setenv("GARUDA_IGNORE_FILES", "")
    s = {"runs": [{"results": [_r("README.md")]}]}
    apply_suppressions(s, d)
    assert not is_suppressed(s["runs"][0]["results"][0])
    monkeypatch.setenv("GARUDA_IGNORE_FILES", "README.md,NOTES.txt")
    s = {"runs": [{"results": [_r("NOTES.txt")]}]}
    apply_suppressions(s, d)
    assert is_suppressed(s["runs"][0]["results"][0])
