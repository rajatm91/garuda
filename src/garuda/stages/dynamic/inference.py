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


def resolve_target(model_id: str, litellm_base_url: str) -> InferenceHandle:
    """Build a target handle. Shares base_url with judge; uses TARGET_MODEL_API_KEY."""
    key = os.environ.get("TARGET_MODEL_API_KEY")
    if not key:
        raise RuntimeError(
            "TARGET_MODEL_API_KEY unset — required for target model auth on LiteLLM proxy"
        )
    h = InferenceHandle(base_url=litellm_base_url.rstrip("/"),
                        model_id=model_id, api_key=key)
    _health_check(h)
    return h


def _health_check(h: InferenceHandle) -> None:
    r = requests.get(f"{h.base_url}/models",
                     headers={"Authorization": f"Bearer {h.api_key}"}, timeout=10)
    r.raise_for_status()
    ids = {m.get("id") for m in (r.json().get("data") or [])}
    if ids and h.model_id not in ids:
        raise RuntimeError(f"model {h.model_id} not listed by LiteLLM /models: {ids}")
