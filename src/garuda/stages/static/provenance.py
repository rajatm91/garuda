"""Step 11 — provenance: published-hash check, model signature, publisher identity."""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError

from ...context import ScanContext, StageResult
from ...util.io import load_json, write_json

log = logging.getLogger(__name__)
OUT = "11_provenance.json"
SIG_FILE = "model.sig"
# Fulcio cert extensions carrying the OIDC issuer (v2 = DER UTF8String, v1 = raw bytes).
_ISSUER_V2 = "1.3.6.1.4.1.57264.1.8"
_ISSUER_V1 = "1.3.6.1.4.1.57264.1.1"
# Files that are never part of a model's signed content.
_NOT_MODEL = (".cache/", ".git/", ".gitattributes", ".gitignore", SIG_FILE)


def run(ctx: ScanContext) -> StageResult:
    out_path = ctx.raw_dir / OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    local = "local source — no published record to compare against"
    data = {
        "hash_check": {"skipped": local} if ctx.is_local_source else _hash_check(ctx),
        "signature": _guard(_signature, ctx),
        "publisher": {"skipped": local} if ctx.is_local_source else _guard(_publisher, ctx),
    }
    write_json(out_path, data)
    return StageResult(ran=True, duration_s=time.monotonic() - t0,
                       output_path=out_path, skip_reason=None)


def _guard(fn, ctx: ScanContext) -> dict[str, Any]:
    try:
        return fn(ctx)
    except Exception as e:
        log.exception("provenance %s failed", fn.__name__)
        return {"skipped": f"{fn.__name__.lstrip('_')} error: {e}"}


def _hash_check(ctx: ScanContext) -> dict[str, Any]:
    meta = load_json(ctx.raw_dir / "01_metadata.json") or {}
    inv = load_json(ctx.raw_dir / "02_sha256.json") or {}
    if "skipped" in meta or "files" not in inv:
        return {"skipped": "01_metadata.json or 02_sha256.json missing"}
    published = {s["name"]: s["sha256"] for s in meta.get("siblings", []) if s.get("sha256")}
    verified, mismatched, unverifiable = [], [], []
    for f in inv["files"]:
        expected = published.get(f["path"])
        if expected is None:
            unverifiable.append(f["path"])
        elif expected == f["sha256"]:
            verified.append(f["path"])
        else:
            mismatched.append({"path": f["path"], "local": f["sha256"], "published": expected})
    return {"verified": verified, "mismatched": mismatched, "unverifiable": unverifiable}


def _signature(ctx: ScanContext) -> dict[str, Any]:
    sig = ctx.weights_dir / SIG_FILE
    if not sig.is_file():
        return {"status": "absent"}
    try:
        bundle = json.loads(sig.read_text())
        identity, issuer = _signer(bundle)
        signed = _signed_files(bundle)
    except Exception as e:  # noqa: BLE001 — any parse failure means a malformed bundle
        return {"status": "failed", "file": SIG_FILE, "error": f"unreadable signature: {e}"}
    out = {"file": SIG_FILE, "identity": identity, "issuer": issuer,
           "unsigned_files": _unsigned_files(ctx.weights_dir, signed)}
    if not (ctx.signer_identity and ctx.signer_issuer):
        return {**out, "status": "unpinned"}

    from model_signing import verifying
    from sigstore.errors import VerificationError
    out |= {"expected_identity": ctx.signer_identity, "expected_issuer": ctx.signer_issuer}
    try:
        (verifying.Config()
         .use_sigstore_verifier(identity=ctx.signer_identity, oidc_issuer=ctx.signer_issuer)
         .set_ignore_unsigned_files(True)
         .verify(ctx.weights_dir, sig))
    except (ValueError, VerificationError) as e:
        return {**out, "status": "failed", "error": str(e)}
    except Exception as e:  # noqa: BLE001 — trust-root fetch/network: verification never ran
        return {**out, "status": "error", "error": f"{type(e).__name__}: {e}"}
    return {**out, "status": "verified"}


def _signer(bundle: dict) -> tuple[str | None, str | None]:
    """Signer identity + OIDC issuer from the bundle's Fulcio cert (no trust check)."""
    from cryptography import x509

    vm = bundle.get("verificationMaterial", {})
    raw = (vm.get("certificate") or {}).get("rawBytes") \
        or ((vm.get("x509CertificateChain") or {}).get("certificates") or [{}])[0].get("rawBytes")
    if not raw:
        return None, None  # key-based signature: no identity
    cert = x509.load_der_x509_certificate(base64.b64decode(raw))
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    names = san.get_values_for_type(x509.RFC822Name) \
        + san.get_values_for_type(x509.UniformResourceIdentifier)
    issuer = None
    for ext in cert.extensions:
        if ext.oid.dotted_string == _ISSUER_V2:
            issuer = ext.value.value[2:].decode()  # strip DER UTF8String tag + short length
            break
        if ext.oid.dotted_string == _ISSUER_V1:
            issuer = ext.value.value.decode()
    return (names[0] if names else None), issuer


def _signed_files(bundle: dict) -> set[str]:
    payload = json.loads(base64.b64decode(bundle["dsseEnvelope"]["payload"]))
    names = (r["name"] for r in payload["predicate"]["resources"])
    # shard serialization names resources "path:start:end"
    return {n.rsplit(":", 2)[0] if n.count(":") >= 2 else n for n in names}


def _unsigned_files(root: Path, signed: set[str]) -> list[str]:
    present = (
        str(Path(dp, f).relative_to(root))
        for dp, _, files in os.walk(root) for f in files
    )
    return sorted(p for p in present if p not in signed and not p.startswith(_NOT_MODEL))


def _publisher(ctx: ScanContext) -> dict[str, Any]:
    owner = ctx.repo.split("/")[0]
    api = HfApi(token=os.environ.get("HF_TOKEN"))
    out: dict[str, Any] = {"owner": owner, "expected": ctx.expect_publisher}
    try:
        org = api.get_organization_overview(owner)
        out |= {"kind": "org", "is_verified": bool(org.is_verified),
                "num_models": org.num_models, "num_followers": org.num_followers}
    except HfHubHTTPError:  # not an org → try as a user account
        user = api.get_user_overview(owner)
        out |= {"kind": "user", "is_verified": False,
                "num_models": user.num_models, "num_followers": user.num_followers,
                "created_at": getattr(user, "createdAt", None)}
    return out
