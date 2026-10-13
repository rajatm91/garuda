import json

from garuda.report.html import build_html
from garuda.report.review_notes import apply_notes, load_notes


def test_notes_attach_to_matching_findings_and_render(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "review_notes.json").write_text(json.dumps([
        {"title": "Only for old vLLM", "note": "Applies to vLLM <= 0.15 <script>",
         "applies_to": "hotpatch_vllm.py"},
        {"note": "general context"}, {"title": "no note field"}]))
    notes = load_notes(tmp_path)
    assert [n["title"] for n in notes] == ["Only for old vLLM", "Reviewer note"]
    sarif = {"runs": [{"tool": {"driver": {"name": "Semgrep OSS"}}, "results": [
        {"ruleId": "r", "level": "error", "message": {"text": "proc"},
         "locations": [{"physicalLocation": {"artifactLocation": {"uri": "hotpatch_vllm.py"}}}]},
        {"ruleId": "r", "level": "error", "message": {"text": "other"},
         "locations": [{"physicalLocation": {"artifactLocation": {"uri": "modeling.py"}}}]}]}]}
    apply_notes(sarif, notes)
    res = sarif["runs"][0]["results"]
    assert "vLLM <= 0.15" in res[0]["properties"]["reviewerNote"]
    assert "properties" not in res[1]
    assert sarif["runs"][0]["properties"]["reviewerNotes"] == notes
    html = build_html(tmp_path, sarif)
    assert "Reviewer notes" in html and "general context" in html
    assert "<script>" not in html and "&lt;script&gt;" in html  # escaped


def test_reviewer_level_override_keeps_original(tmp_path):
    (tmp_path / "review_notes.json").write_text(json.dumps([
        {"title": "old vLLM only", "note": "n", "applies_to": "hotpatch_vllm.py", "level": "warning"},
        {"title": "bad level ignored", "note": "n", "applies_to": "x.py", "level": "critical"}]))
    sarif = {"runs": [{"results": [
        {"ruleId": "r", "level": "error", "message": {"text": "proc"},
         "locations": [{"physicalLocation": {"artifactLocation": {"uri": "hotpatch_vllm.py"}}}]},
        {"ruleId": "r", "level": "error", "message": {"text": "x"},
         "locations": [{"physicalLocation": {"artifactLocation": {"uri": "x.py"}}}]}]}]}
    apply_notes(sarif, load_notes(tmp_path))
    a, b = sarif["runs"][0]["results"]
    assert a["level"] == "warning" and a["properties"]["originalLevel"] == "error"
    assert b["level"] == "error" and "originalLevel" not in b["properties"]
