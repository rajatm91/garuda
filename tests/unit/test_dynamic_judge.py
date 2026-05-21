import pytest
from unittest.mock import patch, MagicMock

from garuda.stages.dynamic.policy import JudgeConfig
from garuda.stages.dynamic.judge import JudgeHandle, resolve_judge, sanity_ping


def test_resolve_judge_uses_env(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "http://lite.proxy:4000")
    monkeypatch.setenv("LITELLM_API_KEY", "sk-x")
    h = resolve_judge(JudgeConfig())
    assert isinstance(h, JudgeHandle)
    assert h.base_url == "http://lite.proxy:4000"
    assert h.model == "gemini-2.5-flash"


def test_resolve_judge_accepts_direct_url_in_policy(monkeypatch):
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    cfg = JudgeConfig(base_url_env="http://localhost:4000", api_key_env="sk-direct")
    h = resolve_judge(cfg)
    assert h.base_url == "http://localhost:4000"
    assert h.api_key == "sk-direct"


def test_resolve_judge_raises_without_base_url(monkeypatch):
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        resolve_judge(JudgeConfig())


def test_sanity_ping_calls_models_endpoint():
    h = JudgeHandle(base_url="http://x", api_key="k", model="m",
                    temperature=0, max_tokens=10)
    with patch("garuda.stages.dynamic.judge.requests.get") as g:
        g.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)
        sanity_ping(h)
        assert g.call_args[0][0] == "http://x/models"
