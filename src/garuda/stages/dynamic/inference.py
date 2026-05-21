"""Inference resolver — single LiteLLM proxy for all target inference."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Callable, Literal

import requests


@dataclass
class InferenceHandle:
    base_url: str      # LITELLM_BASE_URL
    model_id: str      # LiteLLM model alias
    api_key: str       # TARGET_MODEL_API_KEY
    mode: Literal["litellm"] = "litellm"
    cleanup: Callable[[], None] = field(default=lambda: None)


def resolve_target(model_id: str) -> InferenceHandle:
    """Build a target handle. Uses same LITELLM_BASE_URL as the judge."""
    base_url = os.environ.get("LITELLM_BASE_URL")
    if not base_url:
        raise RuntimeError("LITELLM_BASE_URL unset — required for dynamic stage")
    key = os.environ.get("TARGET_MODEL_API_KEY") or os.environ.get("LITELLM_API_KEY", "")
    h = InferenceHandle(base_url=base_url.rstrip("/"), model_id=model_id, api_key=key)
    _health_check(h)
    return h


def _health_check(h: InferenceHandle) -> None:
    r = requests.get(f"{h.base_url}/models",
                     headers={"Authorization": f"Bearer {h.api_key}"}, timeout=10)
    r.raise_for_status()
    ids = {m.get("id") for m in (r.json().get("data") or [])}
    if ids and h.model_id not in ids:
        raise RuntimeError(f"model {h.model_id} not listed by LiteLLM /models: {ids}")
