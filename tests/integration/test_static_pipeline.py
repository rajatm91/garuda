import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "tiny-model"


def test_scan_static_against_tiny_model(tmp_path: Path):
    out = tmp_path / "scan"
    res = subprocess.run(
        [sys.executable, "-m", "garuda.cli", "static",
         "--local-path", str(FIXTURE), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    assert (out / "manifest.json").exists()
    assert (out / "raw" / "01_metadata.json").exists()
    assert (out / "raw" / "04_modelaudit.json").exists()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["stages"]["static"]["ran"] is True


def test_scan_report_after_static(tmp_path: Path):
    out = tmp_path / "scan"
    subprocess.run(
        [sys.executable, "-m", "garuda.cli", "static",
         "--local-path", str(FIXTURE), "--out", str(out)],
        check=True,
    )
    res = subprocess.run(
        [sys.executable, "-m", "garuda.cli", "report", str(out)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    assert (out / "reports" / "scan_results.sarif").exists()
    assert (out / "reports" / "scan_report.html").exists()
