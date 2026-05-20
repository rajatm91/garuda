import subprocess
import sys


def test_serve_help_shows_args():
    res = subprocess.run([sys.executable, "-m", "garuda.cli", "serve", "--help"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    for flag in ("--model-path", "--model-id", "--backend", "--port"):
        assert flag in res.stdout


def test_serve_vllm_stub_exits_2():
    res = subprocess.run(
        [sys.executable, "-m", "garuda.cli", "serve",
         "--model-path", "/tmp/x", "--model-id", "m", "--backend", "vllm"],
        capture_output=True, text=True)
    assert res.returncode == 2
