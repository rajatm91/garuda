import json
from pathlib import Path

from garuda.report.translators.review import build_review_run
from garuda.stages.static.semgrep import PARSE_RULE


def _scan(tmp_path: Path) -> Path:
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "01_metadata.json").write_text(json.dumps({
        "id": "meta-llama/Foo", "sha": "abc123" * 10, "license": "llama-3",
        "siblings": [{"name": "x"}] * 5, "tags": ["llama"]}))
    (tmp_path / "raw" / "02_sha256.json").write_text(json.dumps(
        {"files": [{"path": "a", "size": 1, "sha256": "x" * 64}]}))
    (tmp_path / "raw" / "03_format_inventory.json").write_text(json.dumps({
        "safetensors": [], "unsafe_format": [{"path": "m.bin", "size": 1, "sha256": "x" * 64}],
        "other": [], "counts": {"safetensors": 0, "unsafe_format": 1, "other": 0}}))
    return tmp_path


def test_review_emits_metadata_and_unsafe_results(tmp_path):
    run = build_review_run(_scan(tmp_path), is_local_source=False)
    ids = {r["ruleId"] for r in run["results"]}
    assert {"OLR001", "OLR002", "OLR003", "OLR004"} <= ids


def test_review_emits_local_source_note(tmp_path):
    run = build_review_run(_scan(tmp_path), is_local_source=True)
    assert any(r["ruleId"] == "OLR006" for r in run["results"])


def _with_auto_map(tmp_path: Path, *, scanned: list[str]) -> Path:
    scan = _scan(tmp_path)
    w = scan / "weights"
    w.mkdir()
    (w / "config.json").write_text(json.dumps({"auto_map": {
        "AutoConfig": "configuration_foo.FooConfig",
        "AutoModelForCausalLM": "modeling_foo.FooModel",
        "AutoModel": "evil/repo--modeling_bar.BarModel"}}))
    (w / "tokenizer_config.json").write_text(json.dumps({"auto_map": {
        "AutoTokenizer": ["tokenization_foo.FooTok", None]}}))
    for f in ("configuration_foo.py", "modeling_foo.py"):
        (w / f).write_text("")
    (scan / "raw" / "12_semgrep.sarif").write_text(json.dumps(
        {"runs": [{"properties": {"scannedFiles": scanned}}]}))
    return scan


def test_review_lists_remote_code_modules(tmp_path):
    run = build_review_run(_with_auto_map(tmp_path, scanned=["modeling_foo.py"]),
                           is_local_source=False)
    olr7 = {r["properties"]["module"]: r for r in run["results"] if r["ruleId"] == "OLR007"}
    assert set(olr7) == {"configuration_foo.py", "modeling_foo.py", "tokenization_foo.py"}
    assert all(r["level"] == "warning" for r in olr7.values())
    assert olr7["modeling_foo.py"]["properties"]["semgrepScanned"] is True
    assert "not fully analysed by 12_semgrep" in olr7["configuration_foo.py"]["message"]["text"].lower()
    assert olr7["tokenization_foo.py"]["properties"]["exists"] is False
    assert olr7["tokenization_foo.py"]["properties"]["usedBy"] == [
        "AutoTokenizer (tokenizer_config.json)"]


def test_review_flags_cross_repo_remote_code_as_error(tmp_path):
    run = build_review_run(_with_auto_map(tmp_path, scanned=[]), is_local_source=False)
    olr8 = [r for r in run["results"] if r["ruleId"] == "OLR008"]
    assert len(olr8) == 1
    assert olr8[0]["level"] == "error"
    assert olr8[0]["properties"]["repo"] == "evil/repo"
    assert olr8[0]["properties"]["module"] == "modeling_bar.py"


def test_review_no_auto_map_no_remote_code_results(tmp_path):
    run = build_review_run(_scan(tmp_path), is_local_source=False)
    assert not {"OLR007", "OLR008"} & {r["ruleId"] for r in run["results"]}


def test_review_same_repo_prefix_is_local(tmp_path):
    scan = _with_auto_map(tmp_path, scanned=["modeling_foo.py"])
    (scan / "weights" / "config.json").write_text(json.dumps({"auto_map": {
        "AutoModel": "Meta-Llama/foo--modeling_foo.FooModel"}}))
    run = build_review_run(scan, is_local_source=False)
    assert not any(r["ruleId"] == "OLR008" for r in run["results"])
    olr7 = [r for r in run["results"] if r["ruleId"] == "OLR007"
            and r["properties"]["module"] == "modeling_foo.py"]
    assert olr7 and olr7[0]["properties"]["semgrepScanned"] is True


def _partial(scan: Path, *, uri: str | None) -> None:
    res = {"ruleId": PARSE_RULE, "level": "warning", "message": {"text": "x"}}
    if uri:
        res["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": uri}}}]
    (scan / "raw" / "12_semgrep.sarif").write_text(json.dumps({"runs": [{
        "results": [res],
        "properties": {"scannedFiles": ["modeling_foo.py", "configuration_foo.py"]}}]}))


def _scanned_flags(scan: Path) -> dict[str, bool]:
    run = build_review_run(scan, is_local_source=False)
    return {r["properties"]["module"]: r["properties"]["semgrepScanned"]
            for r in run["results"] if r["ruleId"] == "OLR007"}


def test_review_partial_semgrep_file_not_counted_as_scanned(tmp_path):
    scan = _with_auto_map(tmp_path, scanned=[])
    _partial(scan, uri="modeling_foo.py")
    flags = _scanned_flags(scan)
    assert flags["modeling_foo.py"] is False
    assert flags["configuration_foo.py"] is True


def test_review_run_level_semgrep_failure_trusts_nothing(tmp_path):
    scan = _with_auto_map(tmp_path, scanned=[])
    _partial(scan, uri=None)
    assert not any(_scanned_flags(scan).values())
