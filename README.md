# OS LLM Security Scan Toolkit

Static + behavioural scan toolkit for open-source Hugging Face LLMs (Llama, Gemma, Qwen, etc.).
Produces SARIF 2.1.0 + self-contained HTML evidence packs for InfoSec + MRMC review.

## 1. Install

```bash
# Core install (static stage only)
uv add garuda

# With behavioural-eval support
uv add "garuda[dynamic]"
```

Garuda does not host target models. Use an external OpenAI-compatible runtime —
e.g. [Ollama](https://ollama.com/), [llama.cpp server](https://github.com/ggerganov/llama.cpp/tree/master/examples/server),
or [vLLM](https://github.com/vllm-project/vllm) — and point `scan dynamic --endpoint` at it.

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

# Dynamic (behavioural) scan against an existing endpoint
export LITELLM_BASE_URL=http://litellm.internal:4000
export TARGET_MODEL_API_KEY=sk-...
scan dynamic scan_meta-llama_Llama-3.1-8B-Instruct_<ts>/ \
  --endpoint https://api.together.xyz/v1 \
  --model meta-llama/Llama-3.1-8B-Instruct

# Full pipeline (static + dynamic + report)
scan all meta-llama/Llama-3.1-8B-Instruct \
  --endpoint https://api.together.xyz/v1 --model meta-llama/Llama-3.1-8B-Instruct

# Regenerate reports only
scan report scan_meta-llama_Llama-3.1-8B-Instruct_<ts>/
```

## 3. Environment variables

| Var | When | Notes |
|---|---|---|
| `HF_TOKEN` | Static + HF source | Required for gated models (Llama, Gemma, some Qwen) |
| `TARGET_MODEL_API_KEY` | Dynamic + `--endpoint` | Auth token for target inference endpoint |
| `LITELLM_BASE_URL` | Dynamic | Mandatory — LiteLLM proxy base URL for judge model |
| `LITELLM_API_KEY` | Dynamic | Optional — only if proxy auth required |
| `GRYPE_DB_AUTO_UPDATE` | Static + offline | Set `false` to skip CVE DB refresh |
| `SCAN_DEBUG` | Any | Set `1` to enable DEBUG logs |

## 4. Output structure

Every run creates `scan_<repo>_<UTC>/`:

- `manifest.json` — pipeline state, tool versions, judge config, policy SHA-256.
- `raw/01_metadata.json` through `raw/13_eval_summary.json` — native + translated outputs.
- `reports/scan_results.sarif` — single aggregated SARIF 2.1.0 log (submit to GHAS, DefectDojo, etc).
- `reports/scan_report.html` — self-contained HTML for ticket attachment.
- `reports/policy.applied.yaml` — effective policy snapshot.

## 5. Behavioural eval coverage (NIST AI 600-1 + OWASP LLM Top 10)

| Category | Engine | NIST | OWASP |
|---|---|---|---|
| Prompt injection | garak | #9 Information Security | LLM01 |
| Jailbreak / harmful content | garak | #3, #11 | LLM09-adj |
| System-prompt leakage | garak | #9 | LLM07 |
| PII / data leakage | garak | #4 | LLM02 |
| Bias / fairness | promptfoo | #6 | — |
| Hallucination / factuality | promptfoo | #2 | LLM09 |
| Toxicity | promptfoo | #3, #11 | — |

Single judge model (`gemini-2.5-flash` via LiteLLM) grades both engines. Thresholds + sample sizes configured in `policy.yaml`.

## 6. NOT covered in v1

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
- Effective policy SHA-256 (`manifest.json.stages.dynamic.policy_sha256`)
- UTC timestamps everywhere

A second engineer re-running with the same `--policy` file and same SHA will get identical results.

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
| `LITELLM_BASE_URL unset` | Export the LiteLLM proxy URL before `scan dynamic` |
| `model X not in endpoint /models` | Confirm `--model` matches what `/v1/models` returns |
| `modelaudit not installed` | Comes with `garuda` core — verify `uv pip list \| grep modelaudit` |
| `garak failed to fetch probe data` | Set `policy.offline: true` to skip HF-hosted probes |
| `404 from HF` | Set `HF_TOKEN` and accept license on model page |

## 11. Architecture

See `docs/superpowers/specs/2026-05-20-modelaudit-behavioural-checks-design.md` for the full design (3 stages, single `scan` CLI, numbered `raw/NN_*.json` filename contract).
