import sys
from pathlib import Path

from garuda.util.proc import RunResult, run_tool


def test_run_tool_captures_exit_code(tmp_path: Path):
    res = run_tool("true", ["true"], cwd=tmp_path)
    assert isinstance(res, RunResult) and res.exit_code == 0


def test_run_tool_writes_stdout_to_file(tmp_path: Path):
    out = tmp_path / "out.txt"
    res = run_tool("echo", [sys.executable, "-c", "print('hello')"],
                   stdout_path=out, cwd=tmp_path)
    assert res.exit_code == 0
    assert out.read_text().strip() == "hello"


def test_run_tool_writes_stderr_to_file(tmp_path: Path):
    err = tmp_path / "err.txt"
    res = run_tool("err", [sys.executable, "-c",
                            "import sys; sys.stderr.write('oops\\n'); sys.exit(7)"],
                   stderr_path=err, cwd=tmp_path)
    assert res.exit_code == 7
    assert "oops" in err.read_text()


def test_run_tool_missing_binary_returns_nonzero(tmp_path: Path):
    res = run_tool("missing", ["definitely-not-a-binary-xyz"], cwd=tmp_path)
    assert res.exit_code != 0
