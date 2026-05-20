"""Policy model + verdict logic (spec §8)."""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Literal, Union

import yaml
from pydantic import BaseModel, Field, model_validator


class FailureRateThresholds(BaseModel):
    error: float = Field(ge=0.0, le=1.0)
    warning: float = Field(ge=0.0, le=1.0)


class PassRateThresholds(BaseModel):
    pass_rate_error: float = Field(ge=0.0, le=1.0)
    pass_rate_warning: float = Field(ge=0.0, le=1.0)


class CategoryPolicy(BaseModel):
    engine: Literal["garak", "promptfoo"]
    probes: list[str] | None = None
    plugins: list[str] | None = None
    sample_size: int = Field(ge=1, le=10_000)
    thresholds: Union[FailureRateThresholds, PassRateThresholds]

    @model_validator(mode="after")
    def _engine_matches(self):
        if self.engine == "garak" and not self.probes:
            raise ValueError("garak engine requires probes list")
        if self.engine == "promptfoo" and not self.plugins:
            raise ValueError("promptfoo engine requires plugins list")
        if self.probes and self.plugins:
            raise ValueError("probes and plugins are mutually exclusive")
        return self


class JudgeConfig(BaseModel):
    base_url_env: str = "LITELLM_BASE_URL"
    api_key_env: str = "LITELLM_API_KEY"
    model: str = "gemini-2.5-flash"
    temperature: float = 0.0
    max_tokens: int = 1024
    rps_limit: int = 10


class Policy(BaseModel):
    version: Literal[1]
    offline: bool = False
    fail_fast: bool = False
    judge: JudgeConfig = JudgeConfig()
    categories: dict[str, CategoryPolicy]


def load_policy(path: Path) -> Policy:
    return Policy.model_validate(yaml.safe_load(path.read_text()))


def policy_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
