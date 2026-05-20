# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Python package (`garuda`) providing a single `scan` console script for static + behavioural security evaluation of open-source LLMs. uv-managed, hatchling build backend.

## Commands

```bash
# Install / sync (uv-managed)
uv sync --all-extras

# Run tests
uv run pytest                            # unit suite
uv run pytest -m integration             # integration tests (some gated on env vars)
uv run pytest tests/unit/test_X.py -v    # single test

# Lint / type-check
uv run ruff check .
uv run pyright

# CLI
uv run scan static <repo> | --local-path <dir>
uv run scan dynamic <scan_dir> --model MODEL_ALIAS  # LITELLM_BASE_URL must be set
uv run scan all ...
uv run scan report <scan_dir>
```

## Architecture

Three-stage pipeline. Static + dynamic both write into the same `scan_<repo>_<UTC>/raw/` and share the numbered-filename contract.

```
scan static  → raw/01_metadata.json .. raw/10_gitleaks.{json,sarif}
scan dynamic → raw/11_garak.jsonl + raw/12_promptfoo.json + raw/13_eval_summary.json
scan report  → reports/scan_results.sarif + reports/scan_report.html
```

Key modules:

- `src/garuda/cli.py` — argparse dispatch, `_cmd_static`/`_cmd_all`/etc.
- `src/garuda/runner.py` — `run_static`, `run_dynamic`, `run_report`.
- `src/garuda/context.py` — `ScanContext`, `StageResult` (frozen dataclasses).
- `src/garuda/manifest.py` — `manifest.json` lifecycle (explicit pipeline state).
- `src/garuda/stages/static/*.py` — one module per static step 01–10. Soft-fail discipline: missing tool → `{"skipped": "..."}` stub.
- `src/garuda/stages/dynamic/inference.py` — `InferenceHandle` abstraction (endpoint-only; target hosting is external).
- `src/garuda/stages/dynamic/judge.py` — LiteLLM judge config (`gemini-2.5-flash` default).
- `src/garuda/stages/dynamic/{garak,promptfoo}.py` — subprocess wrappers per engine.
- `src/garuda/stages/dynamic/policy.py` — Pydantic policy model + `apply_policy()` verdict roll-up.
- `src/garuda/report/sarif.py` — aggregator (multiple `runs` per SARIF log).
- `src/garuda/report/html.py` — self-contained HTML report (no CDN).
- `src/garuda/report/translators/*.py` — per-tool JSON/JSONL → SARIF run.

## Conventions

- **Numbered `raw/NN_<tool>.{json,jsonl,sarif}` filenames are a load-bearing contract.** Don't rename. Translators hard-code them.
- **Soft-fail per step.** Optional binaries (syft/grype/gitleaks, modelaudit/picklescan, garak/promptfoo) absent → stub JSON, pipeline continues. Skipped steps are recorded in `manifest.stages.<stage>.skipped_steps`.
- **Single-engine-per-category invariant** in `policy.yaml`. Each behavioural category names exactly one of `engine: garak` (probes) OR `engine: promptfoo` (plugins).
- **LiteLLM proxy is mandatory** for dynamic stage. `LITELLM_BASE_URL` unset → hard fail at dynamic-stage start.
- **Pinned SHA for HF sources.** `01_metadata.json` resolves `--revision` (default `main`) to a commit SHA; weights downloaded by SHA, not branch.
- **Self-contained HTML.** No external CSS/JS — must be attachable to a ticket.
- **Native SARIF in, native SARIF out** for grype + gitleaks (their `.sarif` outputs are embedded verbatim in `reports/scan_results.sarif`).

## Spec + plan

The design and implementation plan are committed in `docs/superpowers/specs/` and `docs/superpowers/plans/`. Treat the spec as the source of truth for invariants; the plan documents the build sequence (Phases 0–9, 43 tasks).
