"""Step 12 — semgrep over the custom Python code a model ships (trust_remote_code)."""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

from ...context import ScanContext, StageResult
from ...util.io import load_json, model_files, write_json, write_stub
from ...util.proc import run_tool

log = logging.getLogger(__name__)
OUT = "12_semgrep.sarif"
BIN = "semgrep"
BUNDLED_RULES = Path(__file__).with_name("semgrep_rules.yaml")
# Extra rule packs (comma-separated local YAML paths or registry ids). The Docker image
# pre-fetches p/python + p/security-audit and points this at the local copies (offline).
CONFIGS_ENV = "GARUDA_SEMGREP_CONFIGS"
TIMEOUT_S = 1800


def run(ctx: ScanContext) -> StageResult:
    out_path = ctx.raw_dir / OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    def skip(reason: str) -> StageResult:
        write_stub(out_path, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=reason)

    code = model_files(ctx.weights_dir, "*.py")  # no symlinks / nothing outside the model
    if not code:
        return skip("model ships no Python code")
    if shutil.which(BIN) is None:
        return skip(f"{BIN} not installed (runs in the garuda Docker image)")

    configs = [str(BUNDLED_RULES)]
    configs += [c.strip() for c in os.environ.get(CONFIGS_ENV, "").split(",") if c.strip()]
    out_path.unlink(missing_ok=True)  # never mistake a previous run's file for this one
    argv = [BIN, "scan", "--sarif", "--output", str(out_path), "--metrics=off",
            "--disable-version-check", "--no-git-ignore", "--quiet"]
    for c in configs:
        argv += ["--config", c]
    # Filenames come from the untrusted repo: "./" prefix so a file named "--config=…" or
    # "--exclude=…" can never be parsed as a flag. Relative + cwd=weights → model-relative URIs.
    targets = [str(p.relative_to(ctx.weights_dir)) for p in code]
    argv += [f"./{t}" for t in targets]
    res = run_tool(BIN, argv, stderr_path=ctx.raw_dir / "12_semgrep.stderr.log",
                   timeout=TIMEOUT_S, cwd=ctx.weights_dir)
    sarif = load_json(out_path)
    if not (isinstance(sarif, dict) and "runs" in sarif):
        return skip(f"{BIN} exit={res.exit_code}, no SARIF produced (see 12_semgrep.stderr.log)")
    write_json(out_path, _annotate(sarif, configs, targets))
    if res.exit_code != 0:  # semgrep exits 0 with findings; non-zero = errors → partial result
        return StageResult(ran=False, duration_s=time.monotonic() - t0, output_path=out_path,
                           skip_reason=f"{BIN} exit={res.exit_code}: results may be incomplete "
                                       "(see 12_semgrep.stderr.log)")
    return StageResult(ran=True, duration_s=time.monotonic() - t0,
                       output_path=out_path, skip_reason=None)


def _rule_prefixes(configs: list[str]) -> list[str]:
    """semgrep prefixes local-file rule ids with the rule file's directory, dotted
    (/app/src/garuda/stages/static/x.yaml → "app.src.garuda.stages.static."). That reads as if
    garuda's own code was scanned; strip it so ids show only the rule's real name."""
    out = []
    for c in configs:
        p = Path(c)
        if p.suffix in (".yaml", ".yml") and p.is_absolute():
            out.append(".".join(p.resolve().parent.parts[1:]) + ".")
    return sorted(out, key=len, reverse=True)


def _annotate(sarif: dict, configs: list[str], targets: list[str]) -> dict:
    prefixes = _rule_prefixes(configs)

    def clean(text: str) -> str:
        for p in prefixes:
            text = text.replace(p, "")
        return text

    for run in sarif.get("runs") or []:
        for rule in run.get("tool", {}).get("driver", {}).get("rules") or []:
            for key in ("id", "name"):
                if isinstance(rule.get(key), str):
                    rule[key] = clean(rule[key])
            for key in ("shortDescription", "fullDescription"):
                if isinstance((rule.get(key) or {}).get("text"), str):
                    rule[key]["text"] = clean(rule[key]["text"])
        for res in run.get("results") or []:
            if isinstance(res.get("ruleId"), str):
                res["ruleId"] = clean(res["ruleId"])
        # evidence that the model's own code (and only that) was evaluated
        run.setdefault("properties", {})["scannedFiles"] = targets
    return sarif
