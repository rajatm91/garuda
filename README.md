# OS LLM Security Scan Toolkit

Static security scan toolkit for open-source Hugging Face LLMs (Llama, Gemma, Qwen, etc.).
Produces SARIF 2.1.0 + self-contained HTML evidence packs for InfoSec + MRMC review.

## 1. Install

```bash
uv add garuda
```

External binaries (optional, soft-skip if absent):

```bash
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh  | sh -s -- -b /usr/local/bin
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin
curl -sSfL https://raw.githubusercontent.com/gitleaks/gitleaks/master/install.sh | sh -s -- -b /usr/local/bin
```

## 2. Quick start

```bash
# Static scan against HF Hub
scan static meta-llama/Llama-3.1-8B-Instruct --revision main

# Static scan against on-disk model
scan static --local-path /data/models/Llama-3.1-8B-Instruct

# Static scan + report in one go
scan all meta-llama/Llama-3.1-8B-Instruct

# Regenerate reports only
scan report scan_meta-llama_Llama-3.1-8B-Instruct_<ts>/
```

## 3. Environment variables

| Var | When | Notes |
|---|---|---|
| `HF_TOKEN` | Static + HF source | Required for gated models (Llama, Gemma, some Qwen) |
| `GRYPE_DB_AUTO_UPDATE` | Static + offline | Set `false` to skip CVE DB refresh |
| `SCAN_DEBUG` | Any | Set `1` to enable DEBUG logs |

## 4. Output structure

Every run creates `scan_<repo>_<UTC>/`:

- `manifest.json` — pipeline state, tool versions, skipped steps.
- `raw/01_metadata.json` through `raw/10_gitleaks.{json,sarif}` — native + translated outputs.
- `reports/scan_results.sarif` — single aggregated SARIF 2.1.0 log (submit to GHAS, DefectDojo, etc).
- `reports/scan_report.html` — self-contained HTML for ticket attachment.

## 5. Static steps

| # | Output | Tool | Purpose |
|---|---|---|---|
| 01 | `01_metadata.json` | huggingface_hub | HF model info, revision → commit SHA (or local `config.json`) |
| 02 | `02_sha256.json` | stdlib | SHA-256 of every weight file |
| 03 | `03_format_inventory.json` | stdlib | safetensors vs unsafe (pickle) formats |
| 04 | `04_modelaudit.json` | modelaudit | Malicious-payload scan across model formats |
| 05 | `05_picklescan.json` | picklescan | Second-opinion scan of pickle files |
| 06 | `06_pip_audit.json` | pip-audit | Python dependency CVEs |
| 07 | `07_pip_licenses.json` | pip-licenses | Dependency license inventory |
| 08 | `08_sbom.{cdx,spdx}.json` | syft | SBOM |
| 09 | `09_grype.{json,sarif}` | grype | CVEs from SBOM |
| 10 | `10_gitleaks.{json,sarif}` | gitleaks | Secrets |

Missing tool → `{"skipped": ...}` stub; step listed in `manifest.json` `stages.static.skipped_steps`.

## 6. NOT covered

- Behavioural testing (prompt injection, jailbreak, PII leakage, bias, toxicity, hallucination) — removed; static scan only for now.
- CBRN-info / weapon capability probes (NIST #1) — need legally-cleared corpora; defer to v2.
- IP / training-data extraction beyond standard PII (NIST #10) — defer to v2.
- Application-layer OWASP items: LLM05 (improper output handling), LLM06 (excessive agency), LLM08 (vector & embedding), LLM10 (unbounded consumption) — these are application concerns, not model properties.
- Latency / throughput / capacity testing.
- Entitlement bypass for RAG.

## 7. SARIF ingestion

```bash
gh api -X POST /repos/{owner}/{repo}/code-scanning/sarifs \
  -F commit_sha=$(git rev-parse HEAD) \
  -F ref=refs/heads/main \
  -F sarif=@reports/scan_results.sarif
```

For DefectDojo / Azure DevOps: see [Microsoft SARIF integration docs](https://docs.microsoft.com/en-us/azure/devops/repos/security/github-advanced-security-code-scanning).

## 8. Reproducibility

Every scan records:

- Resolved HF commit SHA (or hash-list digest for `--local-path` mode)
- Tool versions (in `manifest.json.tool_versions`)
- UTC timestamps everywhere

A second engineer re-running against the same SHA will get identical results (modulo CVE DB updates).

## 9. Model-specific notes

### Llama (Meta)

- License: **Llama Community License Agreement** — not OSI-approved open source.
- Has an Acceptable Use Policy (prohibits military, surveillance, CSAM, etc.).
- MAU clause: if your product exceeds 700M MAU at the time of release, you must
  request a separate license from Meta.
- Indemnity: none.

### Gemma (Google)

- License: **Gemma Terms of Use** + prohibited use policy.
- Allows commercial use.
- Distribution of derivatives must pass through the Gemma terms.
- Indemnity: none.

### Qwen (Alibaba)

- Varies by variant. Many Qwen2.5+ checkpoints are **Apache 2.0** (standard OSI).
- Some larger / older variants ship under the **Tongyi Qianwen License** with
  restrictions similar to Llama's (MAU clause, AUP).
- Always check the specific variant's `LICENSE` file.

**Action:** for each model, get the actual `LICENSE` file off the HF repo,
attach it to the Legal review request, do not summarise it.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `modelaudit not installed` | Comes with `garuda` core — verify `uv pip list \| grep modelaudit` |
| `404 from HF` | Set `HF_TOKEN` and accept license on model page |

## 11. Architecture

See `docs/superpowers/specs/2026-05-20-modelaudit-behavioural-checks-design.md` for the original design. Dynamic stage described there has been removed; static stage + numbered `raw/NN_*.json` filename contract still apply.
