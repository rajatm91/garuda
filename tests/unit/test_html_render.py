import json

from garuda.report.html import build_html


def _scan(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "raw" / "01_metadata.json").write_text(json.dumps({
        "id": "meta-llama/Foo", "sha": "abc" * 20, "license": "llama-3",
        "siblings": [], "tags": []}))
    (tmp_path / "raw" / "02_sha256.json").write_text(json.dumps({"files": []}))
    (tmp_path / "raw" / "03_format_inventory.json").write_text(json.dumps({
        "safetensors": [], "unsafe_format": [], "other": [],
        "counts": {"safetensors": 0, "unsafe_format": 0, "other": 0}}))
    return tmp_path


def test_html_renders_with_anchors(tmp_path):
    scan = _scan(tmp_path)
    html = build_html(scan, sarif={"runs": []})
    for anchor in ("#summary", "#model", "#integrity", "#findings", "#licenses"):
        assert anchor in html
    assert "modelaudit" in html.lower() or "modelaudit" in html
    assert "attestation" not in html.lower() and "Signature" not in html
    assert "do not constitute approval" not in html
    assert "<!doctype html>" in html.lower() or "<!DOCTYPE html>" in html


def test_repeated_findings_collapse_into_one_row(tmp_path):
    scan = _scan(tmp_path)
    results = [{"ruleId": "MODELAUDIT-INCOMPLETE", "level": "warning",
                "message": {"text": f"shard {i} not analysed"},
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": f"/w/m-{i}.st"}}}]}
               for i in range(6)]
    results.append({"ruleId": "MODELAUDIT-url", "level": "warning", "message": {"text": "URL x"}})
    sarif = {"runs": [{"tool": {"driver": {"name": "modelaudit", "version": "unknown"}},
                       "results": results}]}
    html = build_html(scan, sarif=sarif)
    assert "6 similar findings" in html and "m-5.st" in html and "URL x" in html
    assert "vunknown" not in html
    assert html.count('<td class=rule><code>MODELAUDIT-INCOMPLETE</code>') == 1


def test_modelaudit_warnings_and_notes_collapsed_errors_open(tmp_path):
    scan = _scan(tmp_path)
    res = [{"ruleId": "E1", "level": "error", "message": {"text": "bad pickle"}},
           {"ruleId": "W1", "level": "warning", "message": {"text": "url seen"}},
           {"ruleId": "N1", "level": "note", "message": {"text": "fyi"}}]
    run = lambda name: {"tool": {"driver": {"name": name}}, "results": res}
    html = build_html(scan, sarif={"runs": [run("modelaudit"), run("grype")]})
    ma, gr = html.split("<article")[1], html.split("<article")[2]
    assert ma.index("bad pickle") < ma.index("<details>")  # error visible
    assert "Show 1 warning</summary>" in ma and "Show 1 informational" in ma
    assert "Show 1 warning</summary>" not in gr  # other tools keep warnings open
