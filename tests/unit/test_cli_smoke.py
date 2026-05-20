import subprocess
import sys

def test_scan_help_works():
    result = subprocess.run(
        [sys.executable, "-m", "os_llm_scan.cli", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    for sub in ("static", "dynamic", "all", "report", "serve"):
        assert sub in result.stdout, f"missing subcommand {sub} in --help"
