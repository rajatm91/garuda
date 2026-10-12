# Garuda Usage Guide

End-to-end recipes for scanning open-source LLMs. See `README.md` for overview, `CLAUDE.md` for architecture, `docs/superpowers/specs/` for the design spec.

---

## 0. Install

```bash
git clone https://github.com/rajatm91/garuda.git
cd garuda
uv sync --all-extras
uv run scan --help
uv run pytest -q
```

Optional external binaries (soft-skip if absent):

```bash
# macOS
brew install syft grype gitleaks

# Linux
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh  | sh -s -- -b /usr/local/bin
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin
curl -sSfL https://raw.githubusercontent.com/gitleaks/gitleaks/master/install.sh | sh -s -- -b /usr/local/bin
```

Env vars: `HF_TOKEN` (gated HF models), `GRYPE_DB_AUTO_UPDATE` (`false` to skip CVE DB refresh), `SCAN_DEBUG` (`1` = debug logging).

---

## 1. Quickest scan (HF source, static only)

```bash
export HF_TOKEN=hf_xxx
uv run scan static meta-llama/Llama-3.1-8B-Instruct
```

Resolves `main` to commit SHA. Downloads weights. Runs 11 static checks. Skips checks whose binary is missing (writes stub).

Output dir: `scan_<safe-repo>_<UTC>/`

Generate reports:
```bash
uv run scan report scan_meta-llama_Llama-3.1-8B-Instruct_<ts>/
```

Open `reports/scan_report.html`. Attach `reports/scan_results.sarif` to ticket.

Reclaim disk:
```bash
rm -rf scan_*/weights/
```

Step 11 provenance flags (all optional):

- `--expect-publisher ORG` — error if the repo owner differs. Without it, unverified orgs / user accounts are warnings.
- `--signer-identity ID --signer-issuer URL` — verify `model.sig` (OpenSSF model-signing / Sigstore) against this signer. Without them a present signature is reported as *unpinned* (warning) with the signer identity found in it.

---

## 2. Offline scan (model already on disk)

```bash
uv run scan static --local-path /data/models/Llama-3.1-8B-Instruct \
  --repo-id meta-llama/Llama-3.1-8B-Instruct
```

`weights/` becomes symlink to `--local-path`. Skips HF download.

```bash
export GRYPE_DB_AUTO_UPDATE=false   # skip CVE DB refresh when no internet
```

---

## 3. Full pipeline

```bash
uv run scan all meta-llama/Llama-3.1-8B-Instruct
```

= `static` → `report` chained. Takes the same args as `static` (`--revision`, `--out`, or `--local-path` + `--repo-id`).

---

## 4. Docker

The image bundles syft, grype (with a cached CVE DB, `GRYPE_DB_AUTO_UPDATE=false`) and gitleaks. Entrypoint is `scan`; mount models at `/models` and output at `/scans`.

```bash
docker build -t garuda .
docker run --rm -v /data/models:/models -v "$PWD/scans":/scans \
  garuda all --local-path /models/mymodel --out /scans/run1
```

---

## 5. Reading outputs

### `manifest.json`
Pipeline state. `stages.static.skipped_steps` lists steps whose tool was absent or soft-failed.

### `raw/NN_<tool>.*` — load-bearing contract

| File | Tool |
|---|---|
| `01_metadata.json` | HF model_info / offline config.json |
| `02_sha256.json` | weight hashes |
| `03_format_inventory.json` | safetensors vs unsafe-format |
| `04_modelaudit.json` | modelaudit |
| `05_picklescan.json` | second-opinion file-format scan |
| `06_pip_audit.json` | Python dep CVE |
| `07_pip_licenses.json` | Python dep licences |
| `08_sbom.{cdx,spdx}.json` | syft SBOM |
| `09_grype.{json,sarif}` | grype CVE |
| `10_gitleaks.{json,sarif}` | gitleaks secrets |
| `11_provenance.json` | hash check vs HF-published hashes, `model.sig` signature, publisher identity |

Files containing `{"skipped": "..."}` = tool absent or soft-failed. Pipeline continues.

### `reports/scan_results.sarif`
SARIF 2.1.0, one `run` per tool (grype + gitleaks native SARIF embedded verbatim). Submit to GHAS / Azure DevOps / DefectDojo / SonarQube.

### `reports/scan_report.html`
Self-contained. Inlined CSS, no CDN. Attach to ticket. Sections:

1. Executive summary
2. Model identity
3. Integrity & format inventory
4. Findings by tool
5. License inventory
6. Attestation

---

## 6. CI (GitHub Actions)

```yaml
name: model-scan
on:
  workflow_dispatch:
    inputs:
      model: { type: string, required: true }

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-extras

      - name: Install scanners
        run: |
          curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh  | sh -s -- -b /usr/local/bin
          curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin

      - name: Full scan
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: uv run scan all "${{ inputs.model }}"

      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: scan_*/reports/scan_results.sarif

      - name: Upload HTML
        uses: actions/upload-artifact@v4
        with:
          name: scan-report
          path: scan_*/reports/scan_report.html
```

---

## 7. Common workflows

### Re-run reports only
```bash
uv run scan report scan_<repo>_<ts>/
```
Idempotent. No network.

### Compare two scans
```bash
diff <(jq -S . scan_A/reports/scan_results.sarif) <(jq -S . scan_B/reports/scan_results.sarif)
```

### Verify deployed weights match scan
```bash
# At scan:
jq -r '.files[] | "\(.sha256)  weights/\(.path)"' scan_*/raw/02_sha256.json > expected.sha256

# At deploy:
cd /path/to/deployed/weights
shasum -a 256 -c /path/to/expected.sha256
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `04_modelaudit.json` shows `{"skipped": ...}` | extra not installed | `uv sync --all-extras` |
| `09_grype.json` stubbed | grype not on PATH | install grype |
| `manifest.json` `stages.static.skipped_steps` populated | binaries missing | expected; install or accept |
| HF 401 | token missing / licence not accepted | set `HF_TOKEN`, accept on model page |

---

## 9. NOT covered (v2.0 scope)

See spec §13:
- Behavioural / dynamic evaluation (removed — garuda is static-only)
- CBRN / weapon capability probes (need legally-cleared corpora)
- IP / training-data extraction beyond PII
- App-layer OWASP items (LLM05/06/08/10)
- Latency / throughput / capacity
- Entitlement bypass for RAG
- Network egress testing

Document these as separate items in MRMC submission.
