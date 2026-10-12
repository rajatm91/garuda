"""Step 11 provenance JSON → SARIF run."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ...util.io import load_json

RULES = {
    "PROV001": ("HashMismatch", "error", "Weight file does not match the hash HF published"),
    "PROV002": ("HashVerified", "note", "Weight files match the hashes HF published"),
    "PROV003": ("HashUnverifiable", "warning", "No published hash for weight file"),
    "PROV010": ("SignatureVerified", "note", "model.sig verified against expected signer"),
    "PROV011": ("SignatureInvalid", "error", "model.sig failed verification"),
    "PROV012": ("SignatureUnpinned", "warning", "model.sig present but signer not pinned"),
    "PROV013": ("SignatureAbsent", "note", "No model.sig signature shipped"),
    "PROV014": ("SignatureNotChecked", "warning", "model.sig could not be verified"),
    "PROV015": ("UnsignedFiles", "warning", "Files present that model.sig does not cover"),
    "PROV020": ("PublisherMismatch", "error", "Repo owner is not the expected publisher"),
    "PROV021": ("PublisherUnverified", "warning", "Publisher is not a verified HF organization"),
    "PROV022": ("PublisherVerified", "note", "Publisher is a verified HF organization"),
}


def _res(rule: str, msg: str, *, uri: str | None = None, props: dict | None = None) -> dict:
    r: dict[str, Any] = {"ruleId": rule, "level": RULES[rule][1], "message": {"text": msg}}
    if uri:
        r["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": uri}}}]
    if props:
        r["properties"] = props
    return r


def build_provenance_run(scan_dir: Path) -> dict | None:
    data = load_json(scan_dir / "raw" / "11_provenance.json")
    if not data or "skipped" in data:
        return None
    results = (_hashes(data.get("hash_check") or {})
               + _signature(data.get("signature") or {})
               + _publisher(data.get("publisher") or {}))
    return {
        "tool": {"driver": {
            "name": "garuda-provenance",
            "rules": [
                {"id": rid, "name": name, "shortDescription": {"text": text},
                 "defaultConfiguration": {"level": level}}
                for rid, (name, level, text) in RULES.items()
            ],
        }},
        "results": results,
        "invocations": [{"executionSuccessful": True}],
    }


def _hashes(h: dict) -> list[dict]:
    if "skipped" in h:
        return []
    out = [_res("PROV001", f"{m['path']}: local {m['local'][:12]}… ≠ published "
                           f"{m['published'][:12]}…", uri=m["path"], props=m)
           for m in h.get("mismatched", [])]
    out += [_res("PROV003", f"{p}: HF publishes no hash for this file", uri=p)
            for p in h.get("unverifiable", [])]
    if h.get("verified"):
        out.append(_res("PROV002", f"{len(h['verified'])} weight file(s) match HF-published hashes.",
                        props={"files": h["verified"]}))
    return out


def _signature(s: dict) -> list[dict]:
    status, f = s.get("status"), s.get("file")
    who = f"{s.get('identity') or 'unknown signer'} (issuer {s.get('issuer') or 'unknown'})"
    if status == "absent":
        out = [_res("PROV013", "Model ships no model.sig signature.")]
    elif status == "unpinned":
        out = [_res("PROV012", f"model.sig signed by {who}; pass --signer-identity/"
                               "--signer-issuer to verify.", uri=f)]
    elif status == "verified":
        out = [_res("PROV010", f"model.sig verified: signed by {who}.", uri=f)]
    elif status == "failed":
        out = [_res("PROV011", f"model.sig failed verification: {s.get('error')}", uri=f)]
    elif status == "error":
        out = [_res("PROV014", f"model.sig not verified: {s.get('error')}", uri=f)]
    else:
        out = []
    out += [_res("PROV015", f"{p}: not covered by model.sig", uri=p)
            for p in s.get("unsigned_files", [])]
    return out


def _publisher(p: dict) -> list[dict]:
    if "skipped" in p or not p.get("owner"):
        return []
    owner, expected = p["owner"], p.get("expected")
    props = {k: v for k, v in p.items() if v is not None}
    out = []
    if expected and owner.lower() != expected.lower():
        out.append(_res("PROV020", f"Repo owner '{owner}' is not expected publisher '{expected}'.",
                        props=props))
    if p.get("kind") == "org" and p.get("is_verified"):
        out.append(_res("PROV022", f"'{owner}' is a verified HF organization.", props=props))
    else:
        kind = "an individual user account" if p.get("kind") == "user" else "an unverified org"
        out.append(_res("PROV021", f"'{owner}' is {kind} "
                                   f"({p.get('num_followers')} followers, "
                                   f"{p.get('num_models')} models).", props=props))
    return out
