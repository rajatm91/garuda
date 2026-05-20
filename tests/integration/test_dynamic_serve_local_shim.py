import pytest
from pathlib import Path

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "tiny-model"


@pytest.mark.skipif(not (FIXTURE / "config.json").exists(),
                    reason="tiny-model fixture missing")
def test_list_models_route():
    pytest.importorskip("transformers")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from garuda.stages.dynamic import serve_local
    try:
        serve_local._load(FIXTURE, "tiny-model")
    except Exception as e:
        pytest.skip(f"tiny-model not loadable as causal LM: {e}")
    client = TestClient(serve_local._build_app())
    res = client.get("/v1/models")
    assert res.status_code == 200
    assert res.json()["data"][0]["id"] == "tiny-model"
