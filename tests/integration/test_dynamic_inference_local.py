import os
import pytest
import requests
import subprocess
import sys
import time
from pathlib import Path

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("SCAN_TEST_LOCAL_SERVE") != "1",
                       reason="SCAN_TEST_LOCAL_SERVE=1 required"),
]

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "tiny-model"


def test_local_serve_starts_and_lists_models(tmp_path):
    pytest.importorskip("transformers")
    port = 8765
    proc = subprocess.Popen([sys.executable, "-m", "os_llm_scan.cli", "serve",
                              "--model-path", str(FIXTURE), "--model-id", "tm",
                              "--backend", "transformers", "--port", str(port)])
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                r = requests.get(f"http://127.0.0.1:{port}/v1/models", timeout=2)
                if r.ok:
                    assert r.json()["data"][0]["id"] == "tm"
                    return
            except requests.exceptions.RequestException:
                pass
            time.sleep(2)
        pytest.fail("local serve did not become ready in 60s")
    finally:
        proc.terminate()
        proc.wait(timeout=10)
