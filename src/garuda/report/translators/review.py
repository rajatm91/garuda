"""Synthetic 'os-llm-review' SARIF run — built from steps 01-03."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from ...stages.static.semgrep import PARSE_RULE
from ...util.io import load_json
from ..model_card import model_summary

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
    {
        "id": "OLR007",
        "name": "RemoteCodeRequired",
        "shortDescription": {"text": "Loading the model runs its own Python code"},
        "fullDescription": {
            "text": "auto_map in config.json / tokenizer_config.json requires "
                    "trust_remote_code=True; the listed modules execute at load time."
        },
        "defaultConfiguration": {"level": "warning"},
    },
    {
        "id": "OLR008",
        "name": "RemoteCodeFromOtherRepo",
        "shortDescription": {"text": "auto_map pulls code from another repository"},
        "fullDescription": {
            "text": "A 'repo--module.Class' reference downloads and executes code from a "
                    "different Hugging Face repo, which this scan did not cover."
        },
        "defaultConfiguration": {"level": "error"},
    },
    {
        "id": "OLR009",
        "name": "EmptySbom",
        "shortDescription": {"text": "SBOM has no components"},
        "fullDescription": {
            "text": "syft catalogued 0 packages, so grype had nothing to match — "
                    "'no vulnerabilities' here means 'not checked'."
        },
        "defaultConfiguration": {"level": "note"},
    },
]

# every file transformers reads auto_map from (AutoConfig/Model, tokenizer, processors)
AUTO_MAP_CONFIGS = ("config.json", "tokenizer_config.json", "preprocessor_config.json",
                    "processor_config.json", "video_preprocessor_config.json")


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


def sbom_summary(scan_dir: Path) -> dict | None:
    """Component count + per-ecosystem counts from 08_sbom.cdx.json; None if syft didn't run."""
    sbom = load_json(scan_dir / "raw" / "08_sbom.cdx.json")
    if not isinstance(sbom, dict) or "bomFormat" not in sbom:
        return None
    comps = [c for c in sbom.get("components") or [] if isinstance(c, dict)]
    eco: Counter[str] = Counter()
    for c in comps:
        purl = str(c.get("purl") or "")
        # "pkg:pypi/torch@2.1" → "pypi"; no purl → syft's component type (e.g. "file")
        eco[purl[4:].partition("/")[0] if purl.startswith("pkg:")
            else str(c.get("type") or "other")] += 1
    return {"components": len(comps), "ecosystems": dict(eco.most_common())}


def _auto_map_refs(weights: Path) -> tuple[list[tuple[str, str, str]], list[str]]:
    """(config file, Auto class, class reference) for every auto_map / custom_pipelines
    entry, plus config files that exist but could not be read safely (fail closed)."""
    refs: list[tuple[str, str, str]] = []
    unchecked: list[str] = []
    real_root = weights.resolve()
    for name in AUTO_MAP_CONFIGS:
        p = weights / name
        if not p.exists() and not p.is_symlink():
            continue
        # untrusted model content: never follow a symlink out of the model
        cfg = (load_json(p) if p.is_file() and not p.is_symlink()
               and p.resolve().is_relative_to(real_root) else None)
        if not isinstance(cfg, dict):
            unchecked.append(name)
            continue
        entries = list((cfg.get("auto_map") or {}).items()) \
            if isinstance(cfg.get("auto_map"), dict) else []
        pipes = cfg.get("custom_pipelines")
        if isinstance(pipes, dict):
            entries += [(f"pipeline:{task}", spec.get("impl"))
                        for task, spec in pipes.items() if isinstance(spec, dict)]
        for auto_cls, ref in entries:
            # tokenizer entries are [slow, fast] pairs, either may be null
            for r in ref if isinstance(ref, list) else [ref]:
                if isinstance(r, str) and r:
                    refs.append((name, str(auto_cls), r))
    return refs, unchecked


def _semgrep_covered(scan_dir: Path) -> set[str]:
    """Files 12_semgrep fully analysed: submitted targets minus any it flagged as partial.
    A failure with no file attached (bad run, rule load error) means nothing is trusted."""
    covered: set[str] = set()
    semgrep = load_json(scan_dir / "raw" / "12_semgrep.sarif") or {}
    for run in semgrep.get("runs") or []:
        partial = set()
        for res in run.get("results") or []:
            if res.get("ruleId") != PARSE_RULE:
                continue
            uris = [((loc.get("physicalLocation") or {}).get("artifactLocation") or {})
                    .get("uri") for loc in res.get("locations") or []]
            if not any(uris):
                return set()
            partial.update(u for u in uris if u)
        if any(inv.get("executionSuccessful") is False for inv in run.get("invocations") or []):
            return set()
        covered |= set((run.get("properties") or {}).get("scannedFiles") or []) - partial
    return covered


def _remote_code_results(scan_dir: Path) -> list[dict]:
    refs, unchecked = _auto_map_refs(scan_dir / "weights")
    out = [_result(
        "OLR007", "warning",
        f"{cfg} is a symlink, escapes the model, or is not valid JSON — could not check "
        "whether it makes transformers run custom code.",
        file_uri=cfg, properties={"config": cfg, "checked": False}) for cfg in unchecked]
    if not refs:
        return out
    scanned = _semgrep_covered(scan_dir)
    own_repo = str((load_json(scan_dir / "raw" / "01_metadata.json") or {}).get("id") or "")
    local: dict[str, list[str]] = {}
    for cfg, auto_cls, ref in refs:
        repo, sep, cls_ref = ref.partition("--")
        # no prefix, or one naming this very repo → the code is in the scanned snapshot
        if not sep or (own_repo and repo.lower() == own_repo.lower()):
            repo, cls_ref = "", (cls_ref if sep else ref)
        module = cls_ref.rpartition(".")[0].replace(".", "/") + ".py"
        if repo:
            out.append(_result(
                "OLR008", "error",
                f"{cfg} auto_map {auto_cls} loads {module} from another repo '{repo}' — "
                "that code runs at load time and was not scanned.",
                file_uri=cfg,
                properties={"repo": repo, "module": module, "autoClass": auto_cls,
                            "reference": ref}))
        else:
            local.setdefault(module, []).append(f"{auto_cls} ({cfg})")
    for module, users in sorted(local.items()):
        path = scan_dir / "weights" / module
        exists = (path.is_file() and not path.is_symlink()
                  and path.resolve().is_relative_to((scan_dir / "weights").resolve()))
        covered = module in scanned
        gaps = [s for s, bad in (("file missing from model", not exists),
                                 ("not fully analysed by 12_semgrep", not covered)) if bad]
        out.append(_result(
            "OLR007", "warning",
            f"trust_remote_code required: {module} executes at load "
            f"(via {', '.join(users)})." + (f" {'; '.join(gaps).capitalize()}." if gaps else ""),
            file_uri=module,
            properties={"module": module, "usedBy": users, "exists": exists,
                        "semgrepScanned": covered}))
    return out


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
    results.extend(_remote_code_results(scan_dir))
    sbom = sbom_summary(scan_dir)
    if sbom is not None and not sbom["components"]:
        results.append(_result(
            "OLR009", "note",
            "No dependency inventory — syft found 0 packages, so grype had nothing to match.",
            file_uri="raw/08_sbom.cdx.json"))
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
        "properties": {"modelSummary": model_summary(
            meta, load_json(scan_dir / "raw" / "07_licenses.json"))},
    }
