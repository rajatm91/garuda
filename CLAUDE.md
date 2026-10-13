# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A Python package (`garuda`) providing a single `scan` console script for static security evaluation of open-source LLMs. (Dynamic/behavioural stage was removed 2026-10-12 — static only for now.) uv-managed, hatchling build backend.

## Commands

```bash
# Install / sync (uv-managed)
uv sync --all-extras

# Run tests
uv run pytest                            # unit suite
uv run pytest -m integration             # integration tests
uv run pytest tests/unit/test_X.py -v    # single test

# Lint / type-check
uv run ruff check .
uv run pyright

# CLI
uv run scan static <repo> | --local-path <dir>
uv run scan all <repo> | --local-path <dir>   # static + report
uv run scan report <scan_dir>
```

## Architecture

Two-stage pipeline. Static writes `scan_<repo>_<UTC>/raw/`; report reads it.

```
scan static  → raw/01_metadata.json .. raw/13_hf_security.json
scan report  → reports/scan_results.sarif + reports/scan_report.html
```

Key modules:

- `src/garuda/cli.py` — argparse dispatch, `_cmd_static`/`_cmd_all`/etc.
- `src/garuda/runner.py` — `run_static`, `run_report`.
- `src/garuda/context.py` — `ScanContext`, `StageResult` (frozen dataclasses).
- `src/garuda/manifest.py` — `manifest.json` lifecycle (explicit pipeline state).
- `src/garuda/stages/static/*.py` — one module per static step 01–12 (11 = provenance: published-hash check, `model.sig` via model-signing, publisher identity; 12 = semgrep over shipped custom `*.py`, bundled rules in `semgrep_rules.yaml`, extra packs via `GARUDA_SEMGREP_CONFIGS`; 13 = Hugging Face's own security-scan results). Soft-fail discipline: missing tool → `{"skipped": "..."}` stub.
- `src/garuda/report/sarif.py` — aggregator (multiple `runs` per SARIF log).
- `src/garuda/report/html.py` — self-contained HTML report (no CDN).
- `src/garuda/report/translators/*.py` — per-tool JSON/JSONL → SARIF run.

## Conventions

- **Numbered `raw/NN_<tool>.{json,jsonl,sarif}` filenames are a load-bearing contract.** Don't rename. Translators hard-code them.
- **Soft-fail per step.** Optional binaries (syft/grype/gitleaks, modelaudit/picklescan) absent → stub JSON, pipeline continues. Skipped steps are recorded in `manifest.stages.<stage>.skipped_steps`.
- **Pinned SHA for HF sources.** `01_metadata.json` resolves `--revision` (default `main`) to a commit SHA; weights downloaded by SHA, not branch.
- **Run full scans in the Docker image.** modelaudit can't analyse weight shards on macOS (fd pinning) and semgrep is only installed in the image.
- **Self-contained HTML.** No external CSS/JS — must be attachable to a ticket.
- **Native SARIF in, native SARIF out** for grype + gitleaks (their `.sarif` outputs are embedded verbatim in `reports/scan_results.sarif`).

## Spec + plan

The design and implementation plan are committed in `docs/superpowers/specs/` and `docs/superpowers/plans/`. Treat the spec as the source of truth for static-stage invariants (its dynamic-stage sections are obsolete); the plan documents the build sequence (Phases 0–9, 43 tasks).
