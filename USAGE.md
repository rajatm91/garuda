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

Env:
```bash
cp .env.example .env
# edit .env, then:
set -a; source .env; set +a
```

---

## 1. Quickest scan (HF source, static only)

```bash
export HF_TOKEN=hf_xxx
uv run scan static meta-llama/Llama-3.1-8B-Instruct
```

Resolves `main` to commit SHA. Downloads weights. Runs 10 static checks. Skips checks whose binary is missing (writes stub).

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

---

## 2. Offline scan (model already on disk)

```bash
uv run scan static --local-path /data/models/Llama-3.1-8B-Instruct \
  --repo-id meta-llama/Llama-3.1-8B-Instruct
```

`weights/` becomes symlink to `--local-path`. Skip HF download.

```bash
export GRYPE_DB_AUTO_UPDATE=false   # if no internet for CVE DB refresh
```

---

## 3. Behavioural eval against existing endpoint

Pre-req: LiteLLM proxy with `gemini-2.5-flash`; target model hosted OpenAI-compatible.

```bash
export LITELLM_BASE_URL=http://litellm.internal:4000
export LITELLM_API_KEY=sk-...
export TARGET_MODEL_API_KEY=sk-...

SCAN=scan_meta-llama_Llama-3.1-8B-Instruct_<ts>

uv run scan dynamic "$SCAN" \
  --endpoint https://api.together.xyz/v1 \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --policy policy.yaml
```

Steps run:
1. Pydantic-validates `policy.yaml`
2. Pings LiteLLM judge `/v1/models`
3. Health-checks target endpoint
4. garak (security probes: prompt-injection, jailbreak, sys-prompt leak, PII)
5. promptfoo redteam (quality probes: bias, hallucination, toxicity)
6. Applies policy → `raw/13_eval_summary.json`
7. Writes `reports/policy.applied.yaml` snapshot
8. Updates `manifest.json`

Regenerate combined report:
```bash
uv run scan report "$SCAN"
```

Gate verdict pill (PASS / WARNING / FAIL) lands in Section 1 of HTML. Section 5 = per-category eval cards.

---

## 4. Local-serve target (offline)

```bash
uv run scan dynamic "$SCAN" \
  --serve-local \
  --local-path /data/models/Llama-3.1-8B-Instruct \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --backend transformers \
  --policy policy.yaml
```

Spawns `scan serve` as subprocess. Waits `/v1/models` (120 s timeout). Atexit + SIGTERM cleanup.

`--backend vllm` is a stub in v2.0; falls back to transformers.

---

## 5. Full pipeline

```bash
uv run scan all meta-llama/Llama-3.1-8B-Instruct \
  --endpoint https://api.together.xyz/v1 \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --policy policy.yaml
```

= `static` → `dynamic` → `report` chained.

Offline:
```bash
uv run scan all --local-path /data/models/Llama-3.1-8B-Instruct \
  --repo-id meta-llama/Llama-3.1-8B-Instruct \
  --serve-local --backend transformers \
  --policy policy.yaml
```

---

## 6. Reading outputs

### `manifest.json`
Pipeline state. `stages.dynamic.policy_sha256` = effective policy fingerprint.

### `raw/NN_<tool>.*` — load-bearing contract

| File | Tool |
|---|---|
| `01_metadata.json` | HF model_info / offline config.json |
| `02_sha256.json` | weight hashes |
| `03_format_inventory.json` | safetensors vs unsafe-format |
| `04_modelaudit.json` | promptfoo modelaudit |
| `05_picklescan.json` | second-opinion file-format scan |
| `06_pip_audit.json` | Python dep CVE |
| `07_pip_licenses.json` | Python dep licences |
| `08_sbom.{cdx,spdx}.json` | syft SBOM |
| `09_grype.{json,sarif}` | grype CVE |
| `10_gitleaks.{json,sarif}` | gitleaks secrets |
| `11_garak.jsonl` | garak probes |
| `12_promptfoo.json` | promptfoo redteam |
| `13_eval_summary.json` | policy-applied verdict |

### `reports/scan_results.sarif`
SARIF 2.1.0. Submit to GHAS / Azure DevOps / DefectDojo / SonarQube. `EVAL-OVERALL` rule = single field CI scrapes for gate enforcement.

### `reports/scan_report.html`
Self-contained. Inlined CSS, no CDN. Attach to ticket.

### `reports/policy.applied.yaml`
Reproducibility — exact policy used. Re-run with `--policy <file>` to reproduce.

---

## 7. Tuning `policy.yaml`

```bash
cp policy.yaml my-policy.yaml
# edit
uv run scan dynamic "$SCAN" --endpoint ... --policy my-policy.yaml
```

### Threshold shapes

Failure-rate (lower = better):
```yaml
thresholds: { error: 0.05, warning: 0.01 }
```

Pass-rate (higher = better; for hallucination/factuality):
```yaml
thresholds:
  pass_rate_error:   0.70
  pass_rate_warning: 0.85
```

### Sample size

`sample_size: N` per category. Larger N = better signal, slower, more judge cost. Default 100. MRMC submission: bump to 500.

### Engine per category

Invariant: each category names one engine.

```yaml
prompt_injection:
  engine: garak
  probes: [promptinject, latentinjection]

bias:
  engine: promptfoo
  plugins: [bias, competitors]
```

### Offline mode

```yaml
offline: true
```
Drops HF-hosted probes (e.g. realtoxicityprompts). promptfoo plugins still work as long as LiteLLM is reachable.

---

## 8. CI (GitHub Actions)

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
          LITELLM_BASE_URL: ${{ secrets.LITELLM_BASE_URL }}
          LITELLM_API_KEY: ${{ secrets.LITELLM_API_KEY }}
          TARGET_MODEL_API_KEY: ${{ secrets.TARGET_MODEL_API_KEY }}
        run: |
          uv run scan all "${{ inputs.model }}" \
            --endpoint "${{ secrets.TARGET_ENDPOINT }}" \
            --model "${{ inputs.model }}" \
            --policy policy.yaml

      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: scan_*/reports/scan_results.sarif

      - name: Upload HTML
        uses: actions/upload-artifact@v4
        with:
          name: scan-report
          path: scan_*/reports/scan_report.html

      - name: Gate
        run: |
          OVERALL=$(jq -r '.runs[] | select(.tool.driver.name=="os-llm-eval") | .results[] | select(.ruleId=="EVAL-OVERALL") | .level' scan_*/reports/scan_results.sarif)
          echo "Verdict: $OVERALL"
          [[ "$OVERALL" == "error" ]] && exit 1 || exit 0
```

---

## 9. Common workflows

### Re-run reports only
```bash
uv run scan report scan_<repo>_<ts>/
```
Idempotent. No network.

### Re-run dynamic only
```bash
uv run scan dynamic scan_<repo>_<ts>/ --endpoint <URL> --model <NAME> --policy policy.yaml
```
Overwrites `11/12/13_*`. Static outputs preserved.

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

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `LITELLM_BASE_URL unset` | env missing | `export LITELLM_BASE_URL=http://...:4000` |
| `model X not in endpoint /models` | --model mismatch | `curl $ENDPOINT/v1/models`, use exact id |
| `04_modelaudit.json` shows `{"skipped": ...}` | extra not installed | `uv sync --all-extras` |
| `09_grype.json` stubbed | grype not on PATH | install grype |
| `manifest.json.skipped_steps` populated | Some binaries missing | Expected; install or accept |
| `garak failed to fetch probe data` | offline + HF probe | Set `offline: true` in policy |
| `scan dynamic --serve-local` hangs | slow CPU model load | Wait, or use `--backend vllm` on GPU |
| HF 401 | token missing / licence not accepted | Set `HF_TOKEN`, accept on model page |
| Pydantic policy error | mixed `probes` + `plugins` | One engine per category |
| `scan all` exit 4 mid-run | judge unreachable | `scan report` separately for static-only |

---

## 11. NOT covered (v2.0 scope)

See spec §13:
- CBRN / weapon capability probes (need legally-cleared corpora)
- IP / training-data extraction beyond PII
- App-layer OWASP items (LLM05/06/08/10)
- Latency / throughput / capacity
- Entitlement bypass for RAG
- Network egress testing

Document these as separate items in MRMC submission.
