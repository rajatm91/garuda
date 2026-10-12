import json

from garuda.report.translators.provenance import build_provenance_run


def _run(tmp_path, data):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "11_provenance.json").write_text(json.dumps(data))
    run = build_provenance_run(tmp_path)
    assert run is not None
    return {(r["ruleId"], r["level"]) for r in run["results"]}


def test_findings_levels(tmp_path):
    got = _run(tmp_path, {
        "hash_check": {"verified": ["a"], "unverifiable": ["c"],
                       "mismatched": [{"path": "b", "local": "x" * 64, "published": "y" * 64}]},
        "signature": {"status": "unpinned", "file": "model.sig", "identity": "dev@acme.com",
                      "issuer": "https://x", "unsigned_files": ["extra.bin"]},
        "publisher": {"owner": "evil", "expected": "acme", "kind": "user", "is_verified": False},
    })
    assert got == {("PROV001", "error"), ("PROV002", "note"), ("PROV003", "warning"),
                   ("PROV012", "warning"), ("PROV015", "warning"),
                   ("PROV020", "error"), ("PROV021", "warning")}


def test_verified_org_and_signature(tmp_path):
    got = _run(tmp_path, {
        "hash_check": {"verified": ["a"], "mismatched": [], "unverifiable": []},
        "signature": {"status": "verified", "file": "model.sig", "unsigned_files": []},
        "publisher": {"owner": "acme", "expected": "ACME", "kind": "org", "is_verified": True},
    })
    assert got == {("PROV002", "note"), ("PROV010", "note"), ("PROV022", "note")}
