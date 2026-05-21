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


def _resolve_env_or_value(field: str, env_fallback: str = "") -> str:
    """Accept either a direct value (starts with http / sk- / etc.) or an env var name."""
    if field.startswith("http") or "/" in field or field.startswith("sk-"):
        return field
    return os.environ.get(field, env_fallback)


def resolve_judge(cfg: JudgeConfig) -> JudgeHandle:
    base = _resolve_env_or_value(cfg.base_url_env)
    if not base:
        raise RuntimeError(f"{cfg.base_url_env} unset — set env var or put URL directly in policy judge.base_url_env")
    key = _resolve_env_or_value(cfg.api_key_env, "sk-litellm")
    return JudgeHandle(base_url=base.rstrip("/"), api_key=key, model=cfg.model,
                       temperature=cfg.temperature, max_tokens=cfg.max_tokens)


def sanity_ping(h: JudgeHandle, timeout_s: int = 10) -> None:
    r = requests.get(f"{h.base_url}/models",
                     headers={"Authorization": f"Bearer {h.api_key}"}, timeout=timeout_s)
    r.raise_for_status()
