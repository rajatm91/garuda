import pytest
from unittest.mock import patch, MagicMock

from os_llm_scan.stages.dynamic.inference import resolve_endpoint, InferenceHandle


def test_resolve_endpoint_health_check_ok(monkeypatch):
    monkeypatch.setenv("TARGET_MODEL_API_KEY", "k")
    with patch("os_llm_scan.stages.dynamic.inference.requests.get") as g:
        g.return_value = MagicMock(
            status_code=200, raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "Foo"}]})
        h = resolve_endpoint("https://api.x.com/v1", "Foo")
    assert isinstance(h, InferenceHandle)
    assert h.mode == "endpoint" and h.api_key == "k"


def test_resolve_endpoint_model_missing_raises(monkeypatch):
    monkeypatch.setenv("TARGET_MODEL_API_KEY", "k")
    with patch("os_llm_scan.stages.dynamic.inference.requests.get") as g:
        g.return_value = MagicMock(
            status_code=200, raise_for_status=lambda: None,
            json=lambda: {"data": [{"id": "Other"}]})
        with pytest.raises(RuntimeError):
            resolve_endpoint("https://api.x.com/v1", "Foo")
