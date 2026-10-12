"""Model overview (name, provider, architecture, size, context, modality, license)."""
from __future__ import annotations

from typing import Any

_CTX_KEYS = ("max_position_embeddings", "max_sequence_length", "seq_length", "n_positions")


def _cfg_get(cfg: dict, key: str) -> Any:
    """Look in config, then its text sub-config (multimodal models nest the LLM there)."""
    if cfg.get(key) is not None:
        return cfg[key]
    return (cfg.get("text_config") or {}).get(key)


def _human(n: int | None) -> str | None:
    if not n:
        return None
    for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= div:
            return f"{n / div:.2f}{unit}"
    return str(n)


def model_summary(meta: dict, licenses: dict | None = None) -> dict[str, Any]:
    cfg = meta.get("config") or {}
    params = meta.get("parameters") or {}
    archs = cfg.get("architectures") or []
    experts = _cfg_get(cfg, "num_experts") or _cfg_get(cfg, "num_local_experts")
    active = _cfg_get(cfg, "num_experts_per_tok") or _cfg_get(cfg, "top_k_experts")
    ctx = next((v for k in _CTX_KEYS if (v := _cfg_get(cfg, k))), None)

    inputs = ["text"] if cfg or meta.get("pipeline_tag") else []
    if "vision_config" in cfg:
        inputs.append("image")
    files = {s.get("name") for s in meta.get("siblings") or []}
    if "video_preprocessor_config.json" in files:
        inputs.append("video")
    if "audio_config" in cfg:
        inputs.append("audio")

    lic_files = [f["path"] for f in (licenses or {}).get("files") or []]
    return {
        "name": meta.get("id"),
        "version": {"revision": meta.get("revision_requested"), "commit_sha": meta.get("sha"),
                    "last_modified": meta.get("last_modified")},
        "provider": meta.get("author") or (meta.get("id") or "").split("/")[0] or None,
        "base_model": meta.get("base_model"),
        "architecture": {
            "class": archs[0] if archs else None,
            "model_type": cfg.get("model_type"),
            "moe": {"experts": experts, "active_per_token": active} if experts else None,
        },
        "parameters": {"total": params.get("total"), "human": _human(params.get("total")),
                       "by_dtype": params.get("by_dtype")},
        "context_window": {"tokens": ctx, "sliding_window": _cfg_get(cfg, "sliding_window")},
        "modality": {"pipeline_tag": meta.get("pipeline_tag"), "inputs": inputs,
                     "outputs": ["text"] if (meta.get("pipeline_tag") or "").endswith("to-text")
                     or meta.get("pipeline_tag") == "text-generation" else None},
        "license": {"declared": meta.get("license"), "name": meta.get("license_name"),
                    "link": meta.get("license_link"), "files": lic_files},
    }
