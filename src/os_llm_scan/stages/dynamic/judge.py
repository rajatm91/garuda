"""LiteLLM-backed judge model resolution."""
from __future__ import annotations
import os
from dataclasses import dataclass

import requests

from .policy import JudgeConfig


@dataclass(frozen=True)
class JudgeHandle:
    base_url: str
    api_key: str
    model: str
    temperature: float
    max_tokens: int


def resolve_judge(cfg: JudgeConfig) -> JudgeHandle:
    base = os.environ.get(cfg.base_url_env)
    if not base:
        raise RuntimeError(f"{cfg.base_url_env} unset — judge required for dynamic stage")
    key = os.environ.get(cfg.api_key_env, "sk-litellm")
    return JudgeHandle(base_url=base.rstrip("/"), api_key=key, model=cfg.model,
                       temperature=cfg.temperature, max_tokens=cfg.max_tokens)


def sanity_ping(h: JudgeHandle, timeout_s: int = 10) -> None:
    r = requests.get(f"{h.base_url}/models",
                     headers={"Authorization": f"Bearer {h.api_key}"}, timeout=timeout_s)
    r.raise_for_status()
