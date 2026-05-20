"""Synthetic 'os-llm-review' SARIF run — built from steps 01-03."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...util.io import load_json

RULES = [
    {
        "id": "OLR001",
        "name": "PickleFormatDetected",
        "shortDescription": {"text": "Model contains unsafe-format weight files"},
        "fullDescription": {
            "text": "torch.load formats permit arbitrary code execution. Prefer .safetensors."
        },
        "defaultConfiguration": {"level": "warning"},
    },
    {
        "id": "OLR002",
        "name": "MetadataCaptured",
        "shortDescription": {"text": "Model metadata recorded"},
        "fullDescription": {"text": "HF metadata captured for inventory."},
        "defaultConfiguration": {"level": "note"},
    },
    {
        "id": "OLR003",
        "name": "WeightsHashed",
        "shortDescription": {"text": "SHA-256 inventory generated"},
        "fullDescription": {"text": "Weight files hashed. Re-check at deploy time."},
        "defaultConfiguration": {"level": "note"},
    },
    {
        "id": "OLR004",
        "name": "LicenseRequiresReview",
        "shortDescription": {"text": "Model license requires Legal review"},
        "fullDescription": {"text": "Custom OS LLM licenses require Legal sign-off."},
        "defaultConfiguration": {"level": "warning"},
    },
    {
        "id": "OLR005",
        "name": "GatedModel",
        "shortDescription": {"text": "Model is gated on Hugging Face"},
        "fullDescription": {"text": "Vendor-terms acceptance required. Record who + when."},
        "defaultConfiguration": {"level": "note"},
    },
    {
        "id": "OLR006",
        "name": "LocalModelSource",
        "shortDescription": {"text": "Scan used a local on-disk model"},
        "fullDescription": {
            "text": "--local-path mode bypasses HF Hub. SHA pin = hash-list digest."
        },
        "defaultConfiguration": {"level": "note"},
    },
]


def _result(
    rule_id: str,
    level: str,
    msg: str,
    *,
    file_uri: str | None = None,
    properties: dict | None = None,
) -> dict[str, Any]:
    r: dict[str, Any] = {"ruleId": rule_id, "level": level, "message": {"text": msg}}
    if file_uri:
        r["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": file_uri}}}]
    if properties:
        r["properties"] = properties
    return r


def build_review_run(scan_dir: Path, *, is_local_source: bool) -> dict:
    results: list[dict] = []
    meta = load_json(scan_dir / "raw" / "01_metadata.json") or {}
    if meta and "id" in meta:
        sha = meta.get("sha") or "n/a"
        results.append(
            _result(
                "OLR002",
                "note",
                f"Model {meta.get('id')} resolved to SHA {sha[:12]}…",
                properties={
                    "license": meta.get("license"),
                    "file_count": len(meta.get("siblings", [])),
                },
            )
        )
        lic = (meta.get("license") or "").lower()
        if any(k in lic for k in ("llama", "gemma", "tongyi", "qwen", "other")):
            results.append(
                _result(
                    "OLR004",
                    "warning",
                    f"Custom/restricted license: '{meta.get('license')}'. Legal review required.",
                    properties={"license": meta.get("license")},
                )
            )
    sha_inv = load_json(scan_dir / "raw" / "02_sha256.json") or {}
    if sha_inv.get("files"):
        results.append(
            _result(
                "OLR003",
                "note",
                f"Hashed {len(sha_inv['files'])} weight file(s).",
                properties={"file_count": len(sha_inv["files"])},
            )
        )
    fmt = load_json(scan_dir / "raw" / "03_format_inventory.json") or {}
    for f in fmt.get("unsafe_format") or []:
        results.append(
            _result(
                "OLR001",
                "warning",
                f"Unsafe-format weight file: {f['path']} ({f.get('size', 0):,} bytes).",
                file_uri=f["path"],
                properties={"size": f.get("size"), "sha256": f.get("sha256")},
            )
        )
    if is_local_source:
        results.append(
            _result(
                "OLR006",
                "note",
                "Scan ran against a local on-disk model (no HF Hub pin).",
            )
        )
    return {
        "tool": {
            "driver": {
                "name": "os-llm-review",
                "version": "2.0.0",
                "informationUri": "https://internal/os-llm-review",
                "rules": RULES,
            }
        },
        "results": results,
        "invocations": [{"executionSuccessful": True}],
    }
