import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from garuda.context import ScanContext
from garuda.report.translators.hf_security import build_hf_security_run
from garuda.stages.static import hf_security as step


def _ctx(tmp_path, local=False):
    ctx = ScanContext(scan_dir=tmp_path, repo="acme/m", revision="main",
                      local_path=tmp_path / "w" if local else None)
    ctx.raw_dir.mkdir(parents=True)
    return ctx


def _file(path, sec):
    f = MagicMock(spec=["path", "security"])
    f.path, f.security = path, sec
    return f


SAFE = {"safe": True, "status": "safe", "av_scan": {"status": "safe"},
        "pickle_import_scan": {"status": "unscanned", "pickleImports": []}}


def test_fetches_at_pinned_commit_in_batches(tmp_path: Path):
    ctx = _ctx(tmp_path)
    names = [f"model-{i:05d}.safetensors" for i in range(150)]
    (ctx.raw_dir / "01_metadata.json").write_text(json.dumps(
        {"sha": "abc123", "siblings": [{"name": n} for n in names]}))
    api = MagicMock()
    api.model_info.return_value = MagicMock(security_repo_status={"scansDone": True,
                                                                  "filesWithIssues": []})
    api.get_paths_info.side_effect = lambda repo, paths, **kw: [_file(p, SAFE) for p in paths]
    with patch.object(step, "HfApi", return_value=api):
        r = step.run(ctx)
    assert r.ran is True
    assert api.model_info.call_args.kwargs == {"revision": "abc123", "securityStatus": True}
    assert api.get_paths_info.call_count == 2  # 100 + 50
    assert all(c.kwargs["revision"] == "abc123" for c in api.get_paths_info.call_args_list)
    assert len(json.loads(r.output_path.read_text())["files"]) == 150


def test_local_and_api_failure_are_skips(tmp_path: Path):
    assert "local source" in (step.run(_ctx(tmp_path, local=True)).skip_reason or "")
    ctx = _ctx(tmp_path / "b")
    (ctx.raw_dir / "01_metadata.json").write_text(json.dumps({"sha": "s", "siblings": []}))
    with patch.object(step, "HfApi", side_effect=ConnectionError("offline")):
        r = step.run(ctx)
    assert r.ran is False and "offline" in (r.skip_reason or "")


def test_translator_levels(tmp_path: Path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "13_hf_security.json").write_text(json.dumps({
        "revision": "abc123def456",
        "repo_status": {"scansDone": False, "filesWithIssues": [{"path": "evil.bin"},
                                                                {"path": "other.pkl"}]},
        "files": [
            {"path": "ok.safetensors", "security": SAFE},
            {"path": "evil.bin", "security": {"safe": False, "status": "unsafe",
                "av_scan": {"status": "safe"},
                "pickle_import_scan": {"status": "dangerous", "pickleImports": ["os.system"]}}},
            {"path": "odd.bin", "security": {"safe": True, "status": "caution",
                "av_scan": {"status": "safe"}, "pickle_import_scan": {"status": "suspicious"}}},
            {"path": "new.safetensors", "security": {"safe": True, "status": "safe",
                "av_scan": {"status": "queued"}, "pickle_import_scan": {"status": "unscanned"}}},
            {"path": "README.md", "security": None},
        ]}))
    run = build_hf_security_run(tmp_path)
    assert run is not None and run["tool"]["driver"]["name"] == "huggingface-security-scan"
    got = [(r["ruleId"], r["level"], ((r.get("locations") or [{}])[0].get("physicalLocation") or {})
            .get("artifactLocation", {}).get("uri")) for r in run["results"]]
    assert got == [
        ("HFSEC001", "error", "evil.bin"),
        ("HFSEC002", "warning", "odd.bin"),
        ("HFSEC003", "note", "new.safetensors"),
        ("HFSEC001", "error", "other.pkl"),   # repo-level list, not in per-file pass
        ("HFSEC004", "warning", None),
        ("HFSEC005", "note", None),
    ]
    assert "os.system" in run["results"][0]["message"]["text"]


def test_pending_rescan_is_not_a_verdict(tmp_path: Path):
    # Real HF response for a shard queued for re-scan: safe=false but no verdict yet.
    queued = {"safe": False, "status": "queued", "av_scan": {"status": "unscanned"},
              "pickle_import_scan": {"status": "unscanned"}}
    weird = {**queued, "status": "something-new"}  # unknown status: still fail closed
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "13_hf_security.json").write_text(json.dumps({
        "revision": "abc", "repo_status": {"scansDone": True, "filesWithIssues": []},
        "files": [{"path": "a.safetensors", "security": queued},
                  {"path": "b.safetensors", "security": weird}]}))
    run = build_hf_security_run(tmp_path)
    assert run is not None
    by_path = {r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]: r["ruleId"]
               for r in run["results"] if r.get("locations")}
    assert by_path == {"a.safetensors": "HFSEC003", "b.safetensors": "HFSEC001"}
