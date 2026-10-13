import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from garuda.context import ScanContext
from garuda.stages.static import semgrep as step


def _ctx(tmp_path):
    ctx = ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)
    ctx.raw_dir.mkdir(); ctx.weights_dir.mkdir()
    return ctx


def _fake(sarif: str | None):
    def run(name, argv, **_):
        if sarif is not None:
            Path(argv[argv.index("--output") + 1]).write_text(sarif)
        return MagicMock(exit_code=0)
    return run


def test_no_python_code_is_skip(tmp_path: Path):
    r = step.run(_ctx(tmp_path))
    assert r.ran is False and r.skip_reason == "model ships no Python code"


def test_runs_on_shipped_code_with_bundled_and_extra_configs(tmp_path: Path, monkeypatch):
    ctx = _ctx(tmp_path)
    (ctx.weights_dir / "modeling.py").write_text("import os\n")
    (ctx.weights_dir / "sub").mkdir()
    (ctx.weights_dir / "sub" / "audio.py").write_text("x = 1\n")
    secret = tmp_path / "host.py"
    secret.write_text("TOKEN = 1\n")
    (ctx.weights_dir / "evil.py").symlink_to(secret)  # never handed to semgrep
    monkeypatch.setenv(step.CONFIGS_ENV, "/opt/r/python.yml, /opt/r/audit.yml")
    with patch("garuda.stages.static.semgrep.run_tool",
               side_effect=_fake('{"runs": []}')) as rt, \
         patch("shutil.which", return_value="/usr/bin/semgrep"):
        r = step.run(ctx)
    assert r.ran is True
    argv = rt.call_args.args[1]
    configs = [argv[i + 1] for i, a in enumerate(argv) if a == "--config"]
    assert configs == [str(step.BUNDLED_RULES), "/opt/r/python.yml", "/opt/r/audit.yml"]
    assert "--metrics=off" in argv and argv[-2:] == ["./modeling.py", "./sub/audio.py"]
    assert rt.call_args.kwargs["cwd"] != ctx.weights_dir  # private staging copy
    assert "--max-target-bytes=0" in argv


def test_missing_binary_and_bad_output_are_skips(tmp_path: Path):
    ctx = _ctx(tmp_path)
    (ctx.weights_dir / "modeling.py").write_text("x = 1\n")
    with patch("shutil.which", return_value=None):
        assert "not installed" in (step.run(ctx).skip_reason or "")
    with patch("garuda.stages.static.semgrep.run_tool", side_effect=_fake("")), \
         patch("shutil.which", return_value="/usr/bin/semgrep"):
        r = step.run(ctx)
    assert r.ran is False
    assert "skipped" in json.loads(r.output_path.read_text())


def test_bundled_rules_file_is_well_formed():
    rules = yaml.safe_load(step.BUNDLED_RULES.read_text())["rules"]
    assert len(rules) >= 8
    for rule in rules:
        assert rule["id"].startswith("garuda.model-code.")
        assert rule["languages"] == ["python"] and rule["severity"] in {"ERROR", "WARNING", "INFO"}


def test_flag_like_filenames_cannot_become_options(tmp_path: Path):
    ctx = _ctx(tmp_path)
    (ctx.weights_dir / "--exclude=x.py").write_text("x = 1\n")
    with patch("garuda.stages.static.semgrep.run_tool",
               side_effect=_fake('{"runs": []}')) as rt, \
         patch("shutil.which", return_value="/usr/bin/semgrep"):
        step.run(ctx)
    argv = rt.call_args.args[1]
    assert "--exclude=x.py" not in argv and "./--exclude=x.py" in argv


def test_nonzero_exit_keeps_sarif_but_not_ran(tmp_path: Path):
    ctx = _ctx(tmp_path)
    (ctx.weights_dir / "modeling.py").write_text("x = 1\n")
    def fake(name, argv, **_):
        Path(argv[argv.index("--output") + 1]).write_text('{"runs": [{"results": []}]}')
        return MagicMock(exit_code=2)
    with patch("garuda.stages.static.semgrep.run_tool", side_effect=fake), \
         patch("shutil.which", return_value="/usr/bin/semgrep"):
        r = step.run(ctx)
    assert r.ran is False and "may be incomplete" in (r.skip_reason or "")
    assert "runs" in json.loads(r.output_path.read_text())  # evidence kept


def test_rule_ids_lose_rule_file_path_prefix_and_targets_recorded(tmp_path: Path, monkeypatch):
    ctx = _ctx(tmp_path)
    (ctx.weights_dir / "video_io.py").write_text("x = 1\n")
    monkeypatch.setenv(step.CONFIGS_ENV, "/opt/semgrep-rules/python.yml")
    bundled = ".".join(step.BUNDLED_RULES.resolve().parent.parts[1:])
    sarif = {"runs": [{"tool": {"driver": {"name": "Semgrep OSS", "rules": [
        {"id": f"{bundled}.garuda.model-code.network-access",
         "name": f"{bundled}.garuda.model-code.network-access",
         "shortDescription": {"text": f"Semgrep Finding: {bundled}.garuda.model-code.network-access"}},
        {"id": "opt.semgrep-rules.python.lang.security.audit.x"}]}},
        "results": [{"ruleId": f"{bundled}.garuda.model-code.network-access"},
                    {"ruleId": "opt.semgrep-rules.python.lang.security.audit.x"}]}]}
    with patch("garuda.stages.static.semgrep.run_tool", side_effect=_fake(json.dumps(sarif))), \
         patch("shutil.which", return_value="/usr/bin/semgrep"):
        r = step.run(ctx)
    out = json.loads(r.output_path.read_text())["runs"][0]
    assert [x["ruleId"] for x in out["results"]] == [
        "garuda.model-code.network-access", "python.lang.security.audit.x"]
    assert out["properties"]["scannedFiles"] == ["video_io.py"]
    assert bundled not in json.dumps(out)  # no rule-file path left anywhere


def test_staging_ignores_model_semgrepignore_and_default_excludes(tmp_path: Path):
    ctx = _ctx(tmp_path)
    (ctx.weights_dir / ".semgrepignore").write_text("*.py\n")  # model tries to hide itself
    (ctx.weights_dir / "tests").mkdir()
    (ctx.weights_dir / "tests" / "evil.py").write_text("import os\n")  # default-ignored dir
    (ctx.weights_dir / "sub" / ".cache").mkdir(parents=True)
    (ctx.weights_dir / "sub" / ".cache" / "hidden.py").write_text("x = 1\n")
    (ctx.weights_dir / ".cache" / "huggingface").mkdir(parents=True)
    (ctx.weights_dir / ".cache" / "huggingface" / "hf.py").write_text("x = 1\n")  # HF's own
    seen: dict = {}
    def fake(name, argv, *, cwd, **_):
        stage = Path(cwd)
        seen["ignore"] = (stage / ".semgrepignore").read_text()
        seen["files"] = sorted(str(p.relative_to(stage)) for p in stage.rglob("*.py"))
        Path(argv[argv.index("--output") + 1]).write_text('{"runs": [{"results": []}]}')
        return MagicMock(exit_code=0)
    with patch("garuda.stages.static.semgrep.run_tool", side_effect=fake), \
         patch("shutil.which", return_value="/usr/bin/semgrep"):
        r = step.run(ctx)
    assert r.ran is True
    assert seen["ignore"] == ""  # model's .semgrepignore not used, defaults disabled
    assert seen["files"] == ["sub/.cache/hidden.py", "tests/evil.py"]


def test_symlinked_code_is_reported_not_silently_skipped(tmp_path: Path):
    ctx = _ctx(tmp_path)
    outside = tmp_path / "payload.py"
    outside.write_text("import os; os.system('id')\n")
    (ctx.weights_dir / "modeling.py").symlink_to(outside)
    with patch("garuda.stages.static.semgrep.run_tool") as rt, \
         patch("shutil.which", return_value="/usr/bin/semgrep"):
        r = step.run(ctx)
    rt.assert_not_called()  # nothing regular to scan, file never read
    run = json.loads(r.output_path.read_text())["runs"][0]
    assert [(x["ruleId"], x["level"]) for x in run["results"]] == [(step.UNSCANNED_RULE, "error")]
    assert run["properties"]["unscannedFiles"] == ["modeling.py"]
