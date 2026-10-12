from garuda.report.model_card import model_summary

META = {
    "id": "Qwen/Qwen3.6-35B-A3B", "author": "Qwen", "sha": "995ad96", "revision_requested": "main",
    "last_modified": "2026-10-01", "license": "apache-2.0", "license_link": "https://x/LICENSE",
    "pipeline_tag": "image-text-to-text",
    "parameters": {"total": 35951822704, "by_dtype": {"BF16": 35951822704}},
    "siblings": [{"name": "video_preprocessor_config.json"}],
    "config": {"architectures": ["Qwen3_5MoeForConditionalGeneration"], "model_type": "qwen3_5_moe",
               "vision_config": {}, "text_config": {"max_position_embeddings": 262144,
                                                    "num_experts": 256, "num_experts_per_tok": 8}},
}


def test_summary_fields():
    s = model_summary(META, {"files": [{"path": "LICENSE"}]})
    assert s["name"] == "Qwen/Qwen3.6-35B-A3B" and s["provider"] == "Qwen"
    assert s["version"]["commit_sha"] == "995ad96"
    assert s["architecture"]["class"] == "Qwen3_5MoeForConditionalGeneration"
    assert s["architecture"]["moe"] == {"experts": 256, "active_per_token": 8}
    assert s["parameters"]["human"] == "35.95B"
    assert s["context_window"]["tokens"] == 262144
    assert s["modality"]["inputs"] == ["text", "image", "video"]
    assert s["modality"]["outputs"] == ["text"]
    assert s["license"] == {"declared": "apache-2.0", "name": None, "link": "https://x/LICENSE",
                            "files": ["LICENSE"]}


def test_missing_data_degrades_to_none():
    s = model_summary({"id": "local:m"})
    assert s["parameters"]["human"] is None and s["context_window"]["tokens"] is None
    assert s["architecture"]["moe"] is None and s["modality"]["inputs"] == []
