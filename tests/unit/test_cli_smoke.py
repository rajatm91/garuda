import subprocess
import sys

def test_scan_help_works():
    result = subprocess.run(
        [sys.executable, "-m", "garuda.cli", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    for sub in ("static", "dynamic", "all", "report"):
        assert sub in result.stdout, f"missing subcommand {sub} in --help"
