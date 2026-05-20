import pytest
from unittest.mock import patch, MagicMock

from garuda.stages.dynamic.inference import resolve_target, InferenceHandle


def test_resolve_target_health_check_ok(monkeypatch):
    monkeypatch.setenv("TARGET_MODEL_API_KEY", "sk-target")
    with patch("garuda.stages.dynamic.inference.requests.get") as g:
        g.return_value = MagicMock(
            status_code=200, raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "ollama/llama3.1"}]})
        h = resolve_target("ollama/llama3.1", "http://lite:4000")
    assert isinstance(h, InferenceHandle)
    assert h.base_url == "http://lite:4000"
    assert h.api_key == "sk-target"
    assert h.mode == "litellm"


def test_resolve_target_missing_key_raises(monkeypatch):
    monkeypatch.delenv("TARGET_MODEL_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        resolve_target("ollama/llama3.1", "http://lite:4000")


def test_resolve_target_model_missing_raises(monkeypatch):
    monkeypatch.setenv("TARGET_MODEL_API_KEY", "k")
    with patch("garuda.stages.dynamic.inference.requests.get") as g:
        g.return_value = MagicMock(
            status_code=200, raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "other-model"}]})
        with pytest.raises(RuntimeError):
            resolve_target("ollama/llama3.1", "http://lite:4000")
