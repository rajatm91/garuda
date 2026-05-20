from pathlib import Path
import yaml
import pytest

from os_llm_scan.stages.dynamic.policy import load_policy, Policy


def _write(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "p.yaml"; p.write_text(yaml.safe_dump(doc)); return p


def _base() -> dict:
    return {
        "version": 1,
        "categories": {
            "prompt_injection": {"engine":"garak","probes":["promptinject"],
                "sample_size":100,"thresholds":{"error":0.05,"warning":0.01}},
            "bias": {"engine":"promptfoo","plugins":["bias"],"sample_size":100,
                "thresholds":{"error":0.10,"warning":0.05}},
        },
    }


def test_valid_policy_loads(tmp_path):
    p = load_policy(_write(tmp_path, _base()))
    assert isinstance(p, Policy)
    assert p.categories["prompt_injection"].engine == "garak"


def test_bad_version_rejected(tmp_path):
    bad = _base(); bad["version"] = 2
    with pytest.raises(Exception):
        load_policy(_write(tmp_path, bad))


def test_garak_cat_with_plugins_rejected(tmp_path):
    bad = _base()
    bad["categories"]["prompt_injection"]["plugins"] = ["bias"]
    with pytest.raises(Exception):
        load_policy(_write(tmp_path, bad))


def test_pass_rate_thresholds_load(tmp_path):
    doc = _base()
    doc["categories"]["hallucination"] = {
        "engine":"promptfoo","plugins":["hallucination"],"sample_size":100,
        "thresholds":{"pass_rate_error":0.70,"pass_rate_warning":0.85}}
    p = load_policy(_write(tmp_path, doc))
    h = p.categories["hallucination"].thresholds
    assert getattr(h, "pass_rate_error", None) == 0.70
