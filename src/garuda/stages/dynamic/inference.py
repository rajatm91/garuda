"""Inference resolver — endpoint only. Single InferenceHandle abstraction."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Callable, Literal

import requests


@dataclass
class InferenceHandle:
    base_url: str
    model_id: str
    api_key: str
    mode: Literal["endpoint"]
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
