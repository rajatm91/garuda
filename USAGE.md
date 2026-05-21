# Garuda Usage Guide

End-to-end recipes for scanning open-source LLMs. See `README.md` for overview, `CLAUDE.md` for architecture, `docs/superpowers/specs/` for the design spec.

---

## 0. Install

```bash
git clone https://github.com/rajatm91/garuda.git
cd garuda
uv sync --all-extras          # includes garak + litellm (dynamic extras)
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

promptfoo (required for dynamic stage):

```bash
npm install -g promptfoo
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

`weights/` becomes symlink to `--local-path`. Skips HF download.

```bash
export GRYPE_DB_AUTO_UPDATE=false   # skip CVE DB refresh when no internet
```

---

## 3. Behavioural eval (dynamic stage)

Both the **judge model** (gemini-2.5-flash / grader) and the **target model** (the LLM under test)
must be registered in the same LiteLLM proxy. Garuda routes all inference through `LITELLM_BASE_URL`.

```bash
export LITELLM_BASE_URL=http://litellm.internal:4000
export LITELLM_API_KEY=sk-...           # judge model auth
export TARGET_MODEL_API_KEY=sk-...      # target model auth (falls back to LITELLM_API_KEY if unset)

SCAN=scan_Qwen_Qwen3-30B-A3B-Instruct-2507_<ts>

uv run scan dynamic "$SCAN" \
  --model Qwen/Qwen3-30B-A3B-Instruct-2507 \
  --policy policy.yaml
```

`--model` is the LiteLLM model alias for the target (the model being scanned, not the judge).

### Configuring the judge in policy.yaml

`base_url_env` and `api_key_env` accept either an env var name **or** a literal value:

```yaml
judge:
  base_url_env: LITELLM_BASE_URL        # reads $LITELLM_BASE_URL at runtime
  api_key_env:  LITELLM_API_KEY

  # — OR — put the values inline:
  base_url_env: http://localhost:4000
  api_key_env:  sk-my-key
```

### Monitoring progress

Dynamic stage logs subprocess output to files — watch them live with:

```bash
tail -f "$SCAN/raw/11_garak.stderr.log"    # garak probe progress
tail -f "$SCAN/raw/12_promptfoo.stdout.log" # promptfoo redteam progress
```

Terminal also prints each step:
```
[dynamic] judge  → gemini-2.5-flash @ LITELLM_BASE_URL
[dynamic] pinging judge http://litellm.internal:4000 …
[dynamic] judge OK
[dynamic] target → Qwen/Qwen3-30B-A3B-Instruct-2507 @ http://litellm.internal:4000
[dynamic] target OK
[dynamic] running garak probes  (logs → scan_.../raw/11_garak.stderr.log) …
[dynamic] garak done
[dynamic] running promptfoo redteam (logs → scan_.../raw/12_promptfoo.stderr.log) …
[dynamic] promptfoo done
```

### Steps run

1. Pydantic-validates `policy.yaml`
2. Pings LiteLLM judge `/models`
3. Health-checks target model on same proxy
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

## 4. Full pipeline

```bash
uv run scan all meta-llama/Llama-3.1-8B-Instruct \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --policy policy.yaml
```

= `static` → `dynamic` → `report` chained. Same env vars as §3 required.

Register Ollama, llama.cpp server, vLLM, or any cloud API as a LiteLLM virtual key and set `LITELLM_BASE_URL` to your proxy. Garuda does not bundle a local-serve shim.

---

## 5. Reading outputs

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
| `11_garak.stdout.log` | garak stdout (tail -f while running) |
| `11_garak.stderr.log` | garak stderr + progress |
| `12_promptfoo.json` | promptfoo redteam results |
| `12_promptfoo.stdout.log` | promptfoo stdout (tail -f while running) |
| `12_promptfoo.stderr.log` | promptfoo stderr |
| `13_eval_summary.json` | policy-applied verdict |

Files containing `{"skipped": "..."}` = tool absent or soft-failed. Pipeline continues.

### `reports/scan_results.sarif`
SARIF 2.1.0. Submit to GHAS / Azure DevOps / DefectDojo / SonarQube. `EVAL-OVERALL` rule = single field CI scrapes for gate enforcement.

### `reports/scan_report.html`
Self-contained. Inlined CSS, no CDN. Attach to ticket.

### `reports/policy.applied.yaml`
Reproducibility — exact policy used. Re-run with `--policy <file>` to reproduce.

---

## 6. Tuning `policy.yaml`

```bash
cp policy.yaml my-policy.yaml
# edit thresholds / sample sizes / probes
uv run scan dynamic "$SCAN" --model <NAME> --policy my-policy.yaml
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
Drops HF-hosted probes at runtime (e.g. `realtoxicityprompts`, `trainingdata`).
Use `policy.airgap.yaml` as a starting point — it has `offline: true` pre-set.

---

## 7. CI (GitHub Actions)

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

      - name: Install scanners + promptfoo
        run: |
          curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh  | sh -s -- -b /usr/local/bin
          curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin
          npm install -g promptfoo

      - name: Full scan
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
          LITELLM_BASE_URL: ${{ secrets.LITELLM_BASE_URL }}
          LITELLM_API_KEY: ${{ secrets.LITELLM_API_KEY }}
          TARGET_MODEL_API_KEY: ${{ secrets.TARGET_MODEL_API_KEY }}
        run: |
          uv run scan all "${{ inputs.model }}" \
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

## 8. Common workflows

### Re-run reports only
```bash
uv run scan report scan_<repo>_<ts>/
```
Idempotent. No network.

### Re-run dynamic only
```bash
uv run scan dynamic scan_<repo>_<ts>/ --model <NAME> --policy policy.yaml
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

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `LITELLM_BASE_URL unset` | env missing | `export LITELLM_BASE_URL=http://...:4000` or set `base_url_env: http://...` in policy |
| `model X not listed by LiteLLM /models` | `--model` mismatch | `curl $LITELLM_BASE_URL/models` — use exact id |
| `11_garak.jsonl: {"skipped": "garak not installed"}` | dynamic extra missing | `uv sync --extra dynamic` |
| `11_garak.jsonl: {"skipped": "garak exit=2"}` | bad garak flags / version | check `11_garak.stderr.log` |
| `12_promptfoo.json: {"skipped": ...}` | promptfoo not on PATH | `npm install -g promptfoo` |
| `04_modelaudit.json` shows `{"skipped": ...}` | extra not installed | `uv sync --all-extras` |
| `09_grype.json` stubbed | grype not on PATH | install grype |
| `manifest.json.skipped_steps` populated | binaries missing | expected; install or accept |
| `garak failed to fetch probe data` | online probe + no internet | set `offline: true` in policy |
| HF 401 | token missing / licence not accepted | set `HF_TOKEN`, accept on model page |
| Pydantic policy error | mixed `probes` + `plugins` | one engine per category |

---

## 10. NOT covered (v2.0 scope)

See spec §13:
- CBRN / weapon capability probes (need legally-cleared corpora)
- IP / training-data extraction beyond PII
- App-layer OWASP items (LLM05/06/08/10)
- Latency / throughput / capacity
- Entitlement bypass for RAG
- Network egress testing

Document these as separate items in MRMC submission.
