from unittest.mock import patch, MagicMock

from garuda.stages.dynamic.inference import resolve_target, InferenceHandle


def test_resolve_target_uses_litellm_base_url(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "http://lite:4000")
    monkeypatch.setenv("TARGET_MODEL_API_KEY", "sk-target")
    with patch("garuda.stages.dynamic.inference.requests.get") as g:
        g.return_value = MagicMock(
            status_code=200, raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "ollama/llama3.1"}]})
        h = resolve_target("ollama/llama3.1")
    assert isinstance(h, InferenceHandle)
    assert h.base_url == "http://lite:4000"
    assert h.api_key == "sk-target"
    assert h.mode == "litellm"


def test_resolve_target_falls_back_to_litellm_api_key(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "http://lite:4000")
    monkeypatch.delenv("TARGET_MODEL_API_KEY", raising=False)
    monkeypatch.setenv("LITELLM_API_KEY", "sk-shared")
    with patch("garuda.stages.dynamic.inference.requests.get") as g:
        g.return_value = MagicMock(
            status_code=200, raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "ollama/llama3.1"}]})
        h = resolve_target("ollama/llama3.1")
    assert h.api_key == "sk-shared"


def test_resolve_target_missing_base_url_raises(monkeypatch):
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    import pytest
    with pytest.raises(RuntimeError, match="LITELLM_BASE_URL"):
        resolve_target("ollama/llama3.1")


def test_resolve_target_model_missing_raises(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "http://lite:4000")
    monkeypatch.setenv("TARGET_MODEL_API_KEY", "k")
    with patch("garuda.stages.dynamic.inference.requests.get") as g:
        g.return_value = MagicMock(
            status_code=200, raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "other-model"}]})
        import pytest
        with pytest.raises(RuntimeError):
            resolve_target("ollama/llama3.1")
