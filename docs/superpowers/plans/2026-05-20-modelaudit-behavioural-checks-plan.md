# modelaudit Swap + Behavioural-Eval Stage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the toolkit as a Python package `os-llm-scan-toolkit`, swap modelscan → modelaudit, and add a dynamic behavioural-eval stage (prompt-injection, jailbreak, system-prompt leak, PII, bias, hallucination, toxicity) using garak + promptfoo, with gemini-2.5-flash judge via LiteLLM.

**Architecture:** Single `scan` console script with subcommands (`static`, `dynamic`, `all`, `report`, `serve`). Static stage = port of current bash pipeline with the step-04 tool swap. Dynamic stage wraps garak + promptfoo, applies `policy.yaml`, emits `13_eval_summary.json`. Reporting layer (SARIF aggregator + self-contained HTML) extended with new translators and a behavioural-eval section. Reproducibility preserved via the numbered `raw/NN_*.json` contract plus a new `manifest.json`.

**Tech Stack:** Python 3.10+, `huggingface_hub`, `modelaudit`, `picklescan`, `pip-audit`, `pip-licenses`, `garak`, `promptfoo` (Node CLI), LiteLLM, Pydantic v2, pytest, ruff, pyright. Optional: vLLM, transformers, FastAPI (local serve). External binaries: syft, grype, gitleaks.

**Package management:** uv (https://docs.astral.sh/uv/). Build backend: hatchling. All install/sync/run commands use `uv` — `uv sync`, `uv pip install -e .`, `uv run pytest`, `uv add <pkg>`, `uv lock`. Lock file `uv.lock` is committed. `.venv/` is auto-created and gitignored.

**Spec:** `docs/superpowers/specs/2026-05-20-modelaudit-behavioural-checks-design.md`

---

## File Layout (summary)

Full layout in spec §5.2 and §5.3. This plan creates the following groups:

- **Package root:** `pyproject.toml`, `policy.yaml`, `src/os_llm_scan/{cli,runner,manifest,context}.py`
- **Static stages:** `src/os_llm_scan/stages/static/*.py` — one module per step 01–10
- **Dynamic stages:** `src/os_llm_scan/stages/dynamic/{inference,serve_local,judge,garak,promptfoo,policy}.py`
- **Reporting:** `src/os_llm_scan/report/{sarif,html}.py` + `src/os_llm_scan/report/translators/*.py`
- **Utilities:** `src/os_llm_scan/util/{io,proc}.py`
- **Tests:** `tests/unit/test_*.py` + `tests/integration/*.py` + `tests/fixtures/`

Each module is matched 1:1 to a `tests/unit/test_<module>.py`. Files that change together live together — every step module sits next to its tests in the same logical group.

**Deletions at end:** `run_scans.sh`, `to_sarif.py`, `to_html.py`.

---

## Task Map

| Phase | Tasks | Output |
|---|---|---|
| 0 — Bootstrap | T0.1–T0.5 | Package skeleton, test infra, util modules, context, manifest |
| 1 — Static stages | T1.1–T1.10 | Per-step modules + runner |
| 2 — Reporting | T2.1–T2.9 | SARIF aggregator, translators (static set), HTML |
| 3 — Static CLI | T3.1–T3.3 | `scan static` + `scan report` end-to-end |
| 4 — Policy + judge | T4.1–T4.3 | Pydantic policy model, default YAML, judge config |
| 5 — Inference + serve | T5.1–T5.4 | `InferenceHandle`, local backend, `scan serve` |
| 6 — Probe wrappers | T6.1–T6.3 | garak, promptfoo, policy-application module |
| 7 — Dynamic reporting | T7.1–T7.4 | garak/promptfoo/eval translators, HTML section 5 |
| 8 — Dynamic CLI + `all` | T8.1–T8.2 | `scan dynamic` + `scan all` |
| 9 — Cleanup | T9.1–T9.3 | Remove old files, refresh README + CLAUDE.md |

---

## Phase 0 — Bootstrap

### Task 0.1: Package skeleton + `scan --help`

**Files:**
- Create: `pyproject.toml`
- Create: `src/os_llm_scan/__init__.py`
- Create: `src/os_llm_scan/cli.py`
- Create: `tests/__init__.py`, `tests/unit/__init__.py`
- Test: `tests/unit/test_cli_smoke.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_cli_smoke.py`:
```python
import subprocess
import sys

def test_scan_help_works():
    result = subprocess.run(
        [sys.executable, "-m", "os_llm_scan.cli", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    for sub in ("static", "dynamic", "all", "report", "serve"):
        assert sub in result.stdout, f"missing subcommand {sub} in --help"
```

- [ ] **Step 2: Verify it fails**

Run: `pytest tests/unit/test_cli_smoke.py -v`
Expected: `ModuleNotFoundError: No module named 'os_llm_scan'`.

- [ ] **Step 3: Write `pyproject.toml`** (hatchling backend, uv-managed)

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "os-llm-scan-toolkit"
version = "2.0.0"
description = "Static + behavioural scan toolkit for open-source LLMs"
requires-python = ">=3.10"
dependencies = [
  "huggingface_hub>=0.24",
  "modelaudit>=0.1",
  "picklescan>=0.0.20",
  "pip-audit>=2.7",
  "pip-licenses>=4.4",
  "pydantic>=2.5",
  "pyyaml>=6.0",
  "jinja2>=3.1",
  "requests>=2.31",
]

[project.optional-dependencies]
dynamic = ["garak>=0.9", "litellm>=1.40"]
local-serve = [
  "vllm>=0.5; sys_platform == 'linux'",
  "transformers>=4.42",
  "fastapi>=0.110",
  "uvicorn>=0.30",
]

[project.scripts]
scan = "os_llm_scan.cli:main"

[dependency-groups]
dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.5", "pyright>=1.1.370", "jsonschema>=4.22"]

[tool.hatch.build.targets.wheel]
packages = ["src/os_llm_scan"]

[tool.pytest.ini_options]
markers = [
  "integration: end-to-end pipeline tests",
  "golden: golden-file HTML regression",
]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py310"
```

Also create `.python-version` (single line: `3.11`) so `uv` selects a consistent interpreter, and `.gitignore` containing `.venv/`, `__pycache__/`, `*.egg-info/`, `dist/`, `build/`.

- [ ] **Step 4: Write `src/os_llm_scan/__init__.py`**

```python
__version__ = "2.0.0"
```

- [ ] **Step 5: Write `src/os_llm_scan/cli.py`**

```python
"""scan — open-source LLM evidence-pack toolkit."""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scan", description="OS LLM scan toolkit")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("static", help="Static evidence-pack stage")
    sub.add_parser("dynamic", help="Behavioural-eval stage")
    sub.add_parser("all", help="static + dynamic + report")
    sub.add_parser("report", help="Regenerate SARIF + HTML from an existing scan dir")
    sub.add_parser("serve", help="Internal: host a model for local-serve mode")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(f"cmd={args.cmd}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Sync deps + create venv**

```bash
uv sync --all-extras
```

Expected: `.venv/` created, `uv.lock` written, package installed editable, dev deps + optional extras resolved.

If `modelaudit` or `garak` are not resolvable on PyPI yet, drop them from `dependencies` temporarily and proceed — flag in your report.

- [ ] **Step 7: Verify test passes**

Run: `uv run pytest tests/unit/test_cli_smoke.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git init
git add pyproject.toml uv.lock .python-version .gitignore src/ tests/
git commit -m "chore: scaffold os-llm-scan-toolkit package (uv + hatchling)"
```

Throughout the rest of the plan, every `pytest …` invocation should be read as `uv run pytest …`, every `python -m …` as `uv run python -m …`, and dependency changes go through `uv add <pkg>` (which edits `pyproject.toml` + `uv.lock`) rather than hand-editing.

---

### Task 0.2: `util/io.py` — JSON helpers + soft-fail stub

**Files:**
- Create: `src/os_llm_scan/util/__init__.py` (empty)
- Create: `src/os_llm_scan/util/io.py`
- Test: `tests/unit/test_util_io.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_util_io.py
import json
from pathlib import Path

from os_llm_scan.util.io import load_json, write_json, write_stub


def test_load_json_returns_none_for_missing(tmp_path: Path):
    assert load_json(tmp_path / "missing.json") is None


def test_load_json_returns_none_for_empty(tmp_path: Path):
    p = tmp_path / "e.json"; p.write_text("")
    assert load_json(p) is None


def test_load_json_returns_none_for_invalid(tmp_path: Path):
    p = tmp_path / "b.json"; p.write_text("{nope")
    assert load_json(p) is None


def test_load_json_returns_parsed(tmp_path: Path):
    p = tmp_path / "ok.json"; p.write_text('{"a": 1}')
    assert load_json(p) == {"a": 1}


def test_write_json_creates_parent(tmp_path: Path):
    p = tmp_path / "nested" / "out.json"
    write_json(p, {"a": 1})
    assert json.loads(p.read_text()) == {"a": 1}


def test_write_stub_writes_skip_reason(tmp_path: Path):
    p = tmp_path / "stub.json"
    write_stub(p, "syft not installed")
    assert json.loads(p.read_text()) == {"skipped": "syft not installed"}
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/unit/test_util_io.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# src/os_llm_scan/util/io.py
"""JSON I/O helpers with soft-fail semantics."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any | None:
    """Return parsed JSON, or None if missing/empty/invalid. Never raises."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def write_json(path: Path, data: Any, indent: int = 2) -> None:
    """Write JSON with parent-dir creation. Atomic via os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=indent, default=str))
    tmp.replace(path)


def write_stub(path: Path, reason: str) -> None:
    """Write a {'skipped': reason} stub for soft-failed / missing-tool steps."""
    write_json(path, {"skipped": reason})
```

Also create `src/os_llm_scan/util/__init__.py` (empty).

- [ ] **Step 4: Verify pass**

Run: `pytest tests/unit/test_util_io.py -v`
Expected: PASS 6/6.

- [ ] **Step 5: Commit**

```bash
git add src/os_llm_scan/util/ tests/unit/test_util_io.py
git commit -m "feat: util/io.py — JSON read/write + soft-fail stubs"
```

---

### Task 0.3: `util/proc.py` — file-streaming subprocess wrapper

**Files:**
- Create: `src/os_llm_scan/util/proc.py`
- Test: `tests/unit/test_util_proc.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_util_proc.py
import sys
from pathlib import Path

from os_llm_scan.util.proc import RunResult, run_tool


def test_run_tool_captures_exit_code(tmp_path: Path):
    res = run_tool("true", ["true"], cwd=tmp_path)
    assert isinstance(res, RunResult) and res.exit_code == 0


def test_run_tool_writes_stdout_to_file(tmp_path: Path):
    out = tmp_path / "out.txt"
    res = run_tool("echo", [sys.executable, "-c", "print('hello')"],
                   stdout_path=out, cwd=tmp_path)
    assert res.exit_code == 0
    assert out.read_text().strip() == "hello"


def test_run_tool_writes_stderr_to_file(tmp_path: Path):
    err = tmp_path / "err.txt"
    res = run_tool("err", [sys.executable, "-c",
                            "import sys; sys.stderr.write('oops\\n'); sys.exit(7)"],
                   stderr_path=err, cwd=tmp_path)
    assert res.exit_code == 7
    assert "oops" in err.read_text()


def test_run_tool_missing_binary_returns_nonzero(tmp_path: Path):
    res = run_tool("missing", ["definitely-not-a-binary-xyz"], cwd=tmp_path)
    assert res.exit_code != 0
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/unit/test_util_proc.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# src/os_llm_scan/util/proc.py
"""Subprocess wrapper. Streams stdout/stderr to files. Returns exit code + duration."""
from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    duration_s: float


def run_tool(
    name: str,
    argv: list[str],
    *,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
    timeout: int | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> RunResult:
    log.info("run %s: %s", name, " ".join(argv))
    t0 = time.monotonic()

    stdout_f = open(stdout_path, "wb") if stdout_path else subprocess.DEVNULL
    stderr_f = open(stderr_path, "wb") if stderr_path else subprocess.DEVNULL
    try:
        proc = subprocess.Popen(argv, stdout=stdout_f, stderr=stderr_f, cwd=cwd, env=env)
        try:
            exit_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            exit_code = 124
    except FileNotFoundError:
        exit_code = 127
    finally:
        for f in (stdout_f, stderr_f):
            if hasattr(f, "close"):
                f.close()

    dur = time.monotonic() - t0
    log.info("run %s: exit=%d duration=%.2fs", name, exit_code, dur)
    return RunResult(exit_code=exit_code, duration_s=dur)
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/unit/test_util_proc.py -v`
Expected: PASS 4/4.

- [ ] **Step 5: Commit**

```bash
git add src/os_llm_scan/util/proc.py tests/unit/test_util_proc.py
git commit -m "feat: util/proc.py — file-streaming subprocess wrapper"
```

---

### Task 0.4: `context.py` — ScanContext + StageResult

**Files:**
- Create: `src/os_llm_scan/context.py`
- Test: `tests/unit/test_context.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_context.py
from pathlib import Path

from os_llm_scan.context import ScanContext, StageResult


def test_scan_context_paths(tmp_path: Path):
    ctx = ScanContext(scan_dir=tmp_path, repo="meta-llama/Foo", revision="main", local_path=None)
    assert ctx.raw_dir == tmp_path / "raw"
    assert ctx.weights_dir == tmp_path / "weights"
    assert ctx.reports_dir == tmp_path / "reports"


def test_scan_context_local_path_mode(tmp_path: Path):
    src = tmp_path / "L"; src.mkdir()
    ctx = ScanContext(scan_dir=tmp_path / "out", repo="local:L", revision=None, local_path=src)
    assert ctx.is_local_source is True


def test_scan_context_hf_mode(tmp_path: Path):
    ctx = ScanContext(scan_dir=tmp_path, repo="meta-llama/Foo", revision="main", local_path=None)
    assert ctx.is_local_source is False


def test_stage_result_ran():
    r = StageResult(ran=True, duration_s=12.5, output_path=Path("/tmp/x.json"), skip_reason=None)
    assert r.ran is True and r.skip_reason is None


def test_stage_result_skipped():
    r = StageResult(ran=False, duration_s=0.0, output_path=Path("/tmp/x.json"),
                    skip_reason="syft missing")
    assert r.ran is False and r.skip_reason == "syft missing"
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/unit/test_context.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# src/os_llm_scan/context.py
"""ScanContext + StageResult — shared types passed through the stage pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScanContext:
    scan_dir: Path
    repo: str
    revision: str | None
    local_path: Path | None  # None → HF Hub source

    @property
    def raw_dir(self) -> Path:
        return self.scan_dir / "raw"

    @property
    def weights_dir(self) -> Path:
        return self.scan_dir / "weights"

    @property
    def reports_dir(self) -> Path:
        return self.scan_dir / "reports"

    @property
    def is_local_source(self) -> bool:
        return self.local_path is not None


@dataclass(frozen=True)
class StageResult:
    ran: bool
    duration_s: float
    output_path: Path
    skip_reason: str | None
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/unit/test_context.py -v`
Expected: PASS 5/5.

- [ ] **Step 5: Commit**

```bash
git add src/os_llm_scan/context.py tests/unit/test_context.py
git commit -m "feat: ScanContext + StageResult dataclasses"
```

---

### Task 0.5: `manifest.py` — `manifest.json` lifecycle

**Files:**
- Create: `src/os_llm_scan/manifest.py`
- Test: `tests/unit/test_manifest.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/test_manifest.py
import json
from pathlib import Path

from os_llm_scan.manifest import Manifest, load_manifest, save_manifest


def test_manifest_create_writes_minimal_shape(tmp_path: Path):
    m = Manifest.create(scan_dir=tmp_path, repo="meta-llama/Foo", revision="main",
                        source_mode="hf", source_abs_path=None)
    save_manifest(m)
    j = json.loads((tmp_path / "manifest.json").read_text())
    assert j["version"] == "2.0.0"
    assert j["repo"] == "meta-llama/Foo"
    assert j["source"]["mode"] == "hf"
    assert j["stages"]["static"]["ran"] is False
    assert j["stages"]["dynamic"]["ran"] is False


def test_manifest_local_source(tmp_path: Path):
    m = Manifest.create(scan_dir=tmp_path, repo="local:L", revision=None,
                        source_mode="local_path", source_abs_path="/data/L")
    save_manifest(m)
    j = json.loads((tmp_path / "manifest.json").read_text())
    assert j["source"]["mode"] == "local_path"
    assert j["source"]["abs_path"] == "/data/L"


def test_load_round_trip(tmp_path: Path):
    m = Manifest.create(scan_dir=tmp_path, repo="x", revision="main",
                        source_mode="hf", source_abs_path=None)
    save_manifest(m)
    loaded = load_manifest(tmp_path)
    assert loaded.repo == "x" and loaded.version == "2.0.0"


def test_manifest_mark_static_done(tmp_path: Path):
    m = Manifest.create(scan_dir=tmp_path, repo="x", revision="main",
                        source_mode="hf", source_abs_path=None)
    m.mark_static_done(duration_s=400.0, skipped_steps=["08_syft"])
    save_manifest(m)
    j = json.loads((tmp_path / "manifest.json").read_text())
    assert j["stages"]["static"]["ran"] is True
    assert j["stages"]["static"]["duration_s"] == 400.0
    assert j["stages"]["static"]["skipped_steps"] == ["08_syft"]
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/unit/test_manifest.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# src/os_llm_scan/manifest.py
"""manifest.json — explicit pipeline-state record (spec §5.4)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .util.io import load_json, write_json

MANIFEST_VERSION = "2.0.0"


@dataclass
class Manifest:
    version: str
    repo: str
    revision_requested: str | None
    resolved_sha: str | None
    source: dict[str, Any]
    timestamp: str
    stages: dict[str, dict[str, Any]]
    tool_versions: dict[str, str] = field(default_factory=dict)
    scan_dir: Path | None = None  # not serialised

    @classmethod
    def create(cls, *, scan_dir: Path, repo: str, revision: str | None,
               source_mode: str, source_abs_path: str | None) -> "Manifest":
        return cls(
            version=MANIFEST_VERSION,
            repo=repo,
            revision_requested=revision,
            resolved_sha=None,
            source={"mode": source_mode, "abs_path": source_abs_path, "weights_sha256": None},
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            stages={
                "static":  {"ran": False, "duration_s": 0.0, "skipped_steps": []},
                "dynamic": {"ran": False, "duration_s": 0.0,
                            "inference": None, "judge": None, "policy_sha256": None},
            },
            scan_dir=scan_dir,
        )

    def mark_static_done(self, *, duration_s: float, skipped_steps: list[str]) -> None:
        self.stages["static"] = {
            "ran": True, "duration_s": duration_s, "skipped_steps": skipped_steps,
        }

    def mark_dynamic_done(self, *, duration_s: float, inference: dict,
                          judge: dict, policy_sha256: str) -> None:
        self.stages["dynamic"] = {
            "ran": True, "duration_s": duration_s,
            "inference": inference, "judge": judge, "policy_sha256": policy_sha256,
        }

    def to_dict(self) -> dict:
        d = asdict(self); d.pop("scan_dir", None); return d


def save_manifest(m: Manifest) -> None:
    assert m.scan_dir is not None, "scan_dir required to save"
    write_json(m.scan_dir / "manifest.json", m.to_dict())


def load_manifest(scan_dir: Path) -> Manifest:
    data = load_json(scan_dir / "manifest.json")
    if data is None:
        raise FileNotFoundError(f"manifest.json missing in {scan_dir}")
    return Manifest(
        version=data["version"], repo=data["repo"],
        revision_requested=data.get("revision_requested"),
        resolved_sha=data.get("resolved_sha"),
        source=data.get("source", {}), timestamp=data["timestamp"],
        stages=data["stages"], tool_versions=data.get("tool_versions", {}),
        scan_dir=scan_dir,
    )
```

- [ ] **Step 4: Verify pass**

Run: `pytest tests/unit/test_manifest.py -v`
Expected: PASS 4/4.

- [ ] **Step 5: Commit**

```bash
git add src/os_llm_scan/manifest.py tests/unit/test_manifest.py
git commit -m "feat: manifest.py — manifest.json lifecycle"
```

---

**Phase 0 complete.** Phase 1 (static stages 01–10) follows.

Each static-stage task has the same shape: failing test for `run(ctx) → StageResult`, then implementation, then commit. Test pattern (use for every static task):

```python
# tests/unit/test_static_<name>.py — template
from os_llm_scan.context import ScanContext
from os_llm_scan.stages.static import <name>


def test_<name>_writes_expected_filename(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.raw_dir.mkdir(parents=True)
    result = <name>.run(ctx)
    assert result.output_path.name == "<NN>_<name>.json"
    assert result.output_path.exists()


def test_<name>_soft_fail_writes_stub(tmp_path, monkeypatch):
    # monkey-patch underlying tool to simulate failure
    ...
```

Subsequent phases continue in `2026-05-20-modelaudit-behavioural-checks-plan-part2.md` (created in Task 1.0).

---

## Phase 1 — Static stages 01–10

See part 2 for individual task bodies (T1.1 through T1.10). Each follows the static-stage test template above and implements the contract in spec §6.1.

## Phase 2 — Reporting

See part 2 for T2.1–T2.9. Builds the SARIF aggregator + translators + HTML renderer. Translator implementation follows spec §9.

## Phase 3 — Static CLI

See part 2 for T3.1–T3.3. Wires `scan static`, `scan report`, integration test against `tests/fixtures/tiny-model/`.

## Phase 4 — Policy + judge

See part 2 for T4.1–T4.3. Pydantic policy model implementing spec §8; default `policy.yaml` shipped at repo root; judge config from spec §7.2.

## Phase 5 — Inference + serve

See part 2 for T5.1–T5.4. `InferenceHandle` (spec §7.1), local backend, `scan serve` subcommand.

## Phase 6 — Probe wrappers

See part 2 for T6.1–T6.3. garak wrapper (spec §7.3), promptfoo wrapper (spec §7.4), policy-application + `13_eval_summary.json` (spec §7.5).

## Phase 7 — Dynamic reporting

See part 2 for T7.1–T7.4. Translators for `11_garak.jsonl`, `12_promptfoo.json`, synthetic `os-llm-eval` run, HTML section 5.

## Phase 8 — Dynamic CLI + `all`

See part 2 for T8.1–T8.2. `scan dynamic` + `scan all` subcommands.

## Phase 9 — Cleanup

See part 2 for T9.1–T9.3. Delete old files (`run_scans.sh`, `to_sarif.py`, `to_html.py`), refresh README and CLAUDE.md.

---

## Self-review checklist (executed by author)

- [ ] **Spec coverage** — every numbered section in the spec maps to at least one task in this plan.
- [ ] **Placeholder scan** — no "TBD", "TODO", "implement later" tokens.
- [ ] **Type consistency** — `ScanContext`, `StageResult`, `Manifest`, `InferenceHandle` referenced consistently across all phases.

Part 2 file (`…-part2.md`) carries the remaining task bodies (T1.1 onward). Reason for the split: keep individual files under 1500 lines so reviewers can read them top-to-bottom.
