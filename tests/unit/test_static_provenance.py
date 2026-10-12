import base64
import datetime
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from huggingface_hub.errors import HfHubHTTPError

from garuda.context import ScanContext
from garuda.stages.static import provenance as step

ISSUER = "https://github.com/login/oauth"


def _ctx(tmp_path, **kw):
    ctx = ScanContext(scan_dir=tmp_path, repo="acme/model", revision="main",
                      local_path=kw.pop("local_path", None), **kw)
    ctx.raw_dir.mkdir(); ctx.weights_dir.mkdir()
    return ctx


def _write_raw(ctx, siblings, files):
    (ctx.raw_dir / "01_metadata.json").write_text(json.dumps({"siblings": siblings}))
    (ctx.raw_dir / "02_sha256.json").write_text(json.dumps({"files": files}))


def _bundle(identity="dev@acme.com", resources=("model.safetensors",)) -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sigstore")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(1)
        .not_valid_before(now).not_valid_after(now + datetime.timedelta(minutes=10))
        .add_extension(x509.SubjectAlternativeName([x509.RFC822Name(identity)]), critical=False)
        .add_extension(x509.UnrecognizedExtension(
            x509.ObjectIdentifier("1.3.6.1.4.1.57264.1.8"),
            b"\x0c" + bytes([len(ISSUER)]) + ISSUER.encode()), critical=False)
        .sign(key, hashes.SHA256())
    )
    payload = {"predicate": {"resources": [{"name": r} for r in resources]}}
    return json.dumps({
        "verificationMaterial": {"certificate": {"rawBytes": base64.b64encode(
            cert.public_bytes(serialization.Encoding.DER)).decode()}},
        "dsseEnvelope": {"payload": base64.b64encode(json.dumps(payload).encode()).decode()},
    })


def _no_publisher():
    return patch.object(step, "_publisher", return_value={"skipped": "test"})


def test_hash_check_verified_mismatched_unverifiable(tmp_path: Path):
    ctx = _ctx(tmp_path)
    _write_raw(ctx,
               siblings=[{"name": "a.safetensors", "sha256": "aa"},
                         {"name": "b.safetensors", "sha256": "bb"}],
               files=[{"path": "a.safetensors", "sha256": "aa"},
                      {"path": "b.safetensors", "sha256": "XX"},
                      {"path": "c.bin", "sha256": "cc"}])
    with _no_publisher():
        step.run(ctx)
    h = json.loads((ctx.raw_dir / "11_provenance.json").read_text())["hash_check"]
    assert h["verified"] == ["a.safetensors"]
    assert h["mismatched"] == [{"path": "b.safetensors", "local": "XX", "published": "bb"}]
    assert h["unverifiable"] == ["c.bin"]


def test_local_source_skips_hash_and_publisher(tmp_path: Path):
    ctx = _ctx(tmp_path, local_path=tmp_path / "weights")
    step.run(ctx)
    d = json.loads((ctx.raw_dir / "11_provenance.json").read_text())
    assert "skipped" in d["hash_check"] and "skipped" in d["publisher"]
    assert d["signature"] == {"status": "absent"}


def test_signature_unpinned_reports_signer_and_unsigned_files(tmp_path: Path):
    ctx = _ctx(tmp_path)
    (ctx.weights_dir / "model.sig").write_text(_bundle())
    (ctx.weights_dir / "model.safetensors").write_bytes(b"w")
    (ctx.weights_dir / "extra.bin").write_bytes(b"x")
    (ctx.weights_dir / ".cache" / "huggingface").mkdir(parents=True)
    (ctx.weights_dir / ".cache" / "huggingface" / "x.lock").write_text("")
    sig = step._signature(ctx)
    assert sig["status"] == "unpinned"
    assert sig["identity"] == "dev@acme.com" and sig["issuer"] == ISSUER
    assert sig["unsigned_files"] == ["extra.bin"]


def test_signature_pinned_outcomes(tmp_path: Path):
    ctx = _ctx(tmp_path, signer_identity="dev@acme.com", signer_issuer=ISSUER)
    (ctx.weights_dir / "model.sig").write_text(_bundle())
    for side_effect, status in ((None, "verified"),
                                (ValueError("Signature mismatch"), "failed"),
                                (RuntimeError("offline"), "error")):
        cfg = MagicMock()
        chain = cfg.return_value.use_sigstore_verifier.return_value.set_ignore_unsigned_files
        chain.return_value.verify.side_effect = side_effect
        with patch("model_signing.verifying.Config", cfg):
            assert step._signature(ctx)["status"] == status


def test_publisher_org_then_user_fallback(tmp_path: Path):
    ctx = _ctx(tmp_path, expect_publisher="acme")
    api = MagicMock()
    api.get_organization_overview.return_value = MagicMock(
        is_verified=True, num_models=5, num_followers=10)
    with patch.object(step, "HfApi", return_value=api):
        p = step._publisher(ctx)
    assert p["kind"] == "org" and p["is_verified"] is True and p["expected"] == "acme"

    api.get_organization_overview.side_effect = HfHubHTTPError("404", response=MagicMock(status_code=404))
    api.get_user_overview.return_value = MagicMock(num_models=1, num_followers=0,
                                                   createdAt="2026-10-01T00:00:00Z")
    with patch.object(step, "HfApi", return_value=api):
        p = step._publisher(ctx)
    assert p["kind"] == "user" and p["is_verified"] is False
