"""Inference resolver — endpoint OR local-serve. Single InferenceHandle abstraction."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Callable, Literal
from pathlib import Path

import requests


@dataclass
class InferenceHandle:
    base_url: str
    model_id: str
    api_key: str
    mode: Literal["endpoint", "local"]
    cleanup: Callable[[], None] = field(default=lambda: None)


def resolve_endpoint(url: str, model_id: str) -> InferenceHandle:
    key = os.environ.get("TARGET_MODEL_API_KEY", "")
    h = InferenceHandle(base_url=url.rstrip("/"), model_id=model_id,
                        api_key=key, mode="endpoint")
    _health_check(h)
    return h


def _health_check(h: InferenceHandle) -> None:
    r = requests.get(f"{h.base_url}/models",
                     headers={"Authorization": f"Bearer {h.api_key}"}, timeout=10)
    r.raise_for_status()
    ids = {m.get("id") for m in (r.json().get("data") or [])}
    if ids and h.model_id not in ids:
        raise RuntimeError(f"model {h.model_id} not in endpoint /models: {ids}")


def resolve_local(model_path: Path, model_id: str, *,
                  backend: str = "transformers", port: int = 0) -> InferenceHandle:
    import socket
    import subprocess
    import sys
    import atexit
    import signal
    if port == 0:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "os_llm_scan.cli", "serve",
         "--model-path", str(model_path), "--model-id", model_id,
         "--backend", backend, "--port", str(port)],
    )

    def _cleanup() -> None:
        try:
            proc.terminate(); proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    atexit.register(_cleanup)
    signal.signal(signal.SIGTERM, lambda *_: _cleanup())
    _wait_ready(f"http://127.0.0.1:{port}", timeout_s=120)
    return InferenceHandle(
        base_url=f"http://127.0.0.1:{port}/v1",
        model_id=model_id, api_key="sk-local",
        mode="local", cleanup=_cleanup,
    )


def _wait_ready(base: str, timeout_s: int) -> None:
    import time
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/v1/models", timeout=2)
            if r.ok:
                return
        except requests.exceptions.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError(f"local serve did not become ready in {timeout_s}s")
