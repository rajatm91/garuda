"""Step 12 — semgrep over the custom Python code a model ships (trust_remote_code)."""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from ...context import ScanContext, StageResult
from ...util.io import is_hf_cache, load_json, model_files, write_json, write_stub
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
    unscanned = _unscannable_code(ctx.weights_dir)  # still importable → must be reported
    compiled = _compiled_code(ctx.weights_dir)      # importable, but not reviewable as source
    if not code and not unscanned and not compiled:
        return skip("model ships no Python code")
    if shutil.which(BIN) is None:
        return skip(f"{BIN} not installed (runs in the garuda Docker image)")

    configs = [str(BUNDLED_RULES)]
    configs += [c.strip() for c in os.environ.get(CONFIGS_ENV, "").split(",") if c.strip()]
    out_path.unlink(missing_ok=True)  # never mistake a previous run's file for this one
    targets = [str(p.relative_to(ctx.weights_dir)) for p in code]
    exit_code = 0
    if code:
        exit_code = _scan(ctx, code, targets, configs, out_path)
        sarif = load_json(out_path)
        if not (isinstance(sarif, dict) and "runs" in sarif):
            return skip(f"{BIN} exit={exit_code}, no SARIF produced "
                        "(see 12_semgrep.stderr.log)")
    else:
        sarif = {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "Semgrep OSS"}},
                                                "results": []}]}
    sarif = _annotate(sarif, configs, targets, unscanned, compiled)
    partial = _parse_failures(sarif)
    write_json(out_path, sarif)
    if partial:  # semgrep exits 0 on syntax errors: those files were (partly) not analysed
        return StageResult(ran=False, duration_s=time.monotonic() - t0, output_path=out_path,
                           skip_reason=f"{BIN} could not fully parse {len(partial)} file(s): "
                                       f"{', '.join(partial[:5])}")
    if exit_code != 0:  # semgrep exits 0 with findings; non-zero = errors → partial result
        return StageResult(ran=False, duration_s=time.monotonic() - t0, output_path=out_path,
                           skip_reason=f"{BIN} exit={exit_code}: results may be incomplete "
                                       "(see 12_semgrep.stderr.log)")
    return StageResult(ran=True, duration_s=time.monotonic() - t0,
                       output_path=out_path, skip_reason=None)


def _scan(ctx: ScanContext, code: list[Path], targets: list[str], configs: list[str],
          out_path: Path) -> int:
    """Run semgrep on a private copy of the code.

    Scanning in place would let the model steer coverage: a shipped ``.semgrepignore`` could
    exclude its own files, and with no ignore file semgrep's defaults skip tests/, build/,
    vendor/ … . The staging dir holds only the code plus an empty ``.semgrepignore`` (which
    disables the defaults), and the size cap is lifted so large obfuscated files are scanned.
    """
    with tempfile.TemporaryDirectory(prefix="garuda-semgrep-") as tmp:
        stage = Path(tmp)
        (stage / ".semgrepignore").write_text("")
        for src, rel in zip(code, targets, strict=True):
            dst = stage / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        argv = [BIN, "scan", "--sarif", "--output", str(out_path), "--metrics=off",
                "--disable-version-check", "--no-git-ignore", "--max-target-bytes=0",
                "--timeout=0", "--quiet"]  # no per-file size/time caps that silently skip
        for c in configs:
            argv += ["--config", c]
        # Untrusted filenames: "./" prefix so "--config=…"/"--exclude=…" is never a flag.
        argv += [f"./{t}" for t in targets]
        res = run_tool(BIN, argv, stderr_path=ctx.raw_dir / "12_semgrep.stderr.log",
                       timeout=TIMEOUT_S, cwd=stage)
    return res.exit_code


def _unscannable_code(root: Path) -> list[str]:
    """*.py the model ships that we must not read (symlink / resolves outside the model) but
    that Python could still import."""
    real_root = root.resolve()
    out = []
    for p in root.rglob("*.py"):
        rel = p.relative_to(root)
        if is_hf_cache(rel):
            continue
        if p.is_symlink() or not p.resolve().is_relative_to(real_root):
            out.append(str(rel))
    return sorted(out)


UNSCANNED_RULE = "garuda.model-code.unscanned-code"
COMPILED_RULE = "garuda.model-code.compiled-code"
PARSE_RULE = "garuda.model-code.not-fully-parsed"
_COMPILED_SUFFIXES = {".pyc", ".pyo", ".so", ".pyd", ".dylib", ".dll"}
_SYNTAX_AT = re.compile(r"at line (?P<file>\S+?):\d+")


def _compiled_code(root: Path) -> list[str]:
    """Native/bytecode modules custom code could import — no source to review."""
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")
                  if p.suffix.lower() in _COMPILED_SUFFIXES and not is_hf_cache(p.relative_to(root)))


def _parse_failures(sarif: dict) -> list[str]:
    """Files semgrep reported syntax/parse errors for, added as warning results.

    semgrep keeps exit 0 and executionSuccessful=true and only emits a warning notification,
    so a file written in syntax semgrep can't parse (or simply broken) would look scanned."""
    files: list[str] = []
    for run in sarif.get("runs") or []:
        for inv in run.get("invocations") or []:
            for n in inv.get("toolExecutionNotifications") or []:
                text = (n.get("message") or {}).get("text") or ""
                kind = (n.get("descriptor") or {}).get("id") or ""
                if "syntax error" not in (kind + text).lower() and n.get("level") != "error":
                    continue
                m = _SYNTAX_AT.search(text)
                f = (m.group("file") if m else "") .removeprefix("./")
                files.append(f or "<unknown>")
                run.setdefault("results", []).append({
                    "ruleId": PARSE_RULE, "level": "warning",
                    "message": {"text": "semgrep could not fully parse this file, so parts of it "
                                        f"were not analysed: {text.splitlines()[0][:200]}"},
                    **({"locations": [{"physicalLocation": {"artifactLocation": {"uri": f}}}]}
                       if f else {}),
                })
    return sorted(set(files))


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


def _annotate(sarif: dict, configs: list[str], targets: list[str],
              unscanned: list[str] | None = None, compiled: list[str] | None = None) -> dict:
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
    if unscanned and sarif.get("runs"):
        run = sarif["runs"][0]
        run.setdefault("results", []).extend(
            {"ruleId": UNSCANNED_RULE, "level": "error",
             "message": {"text": "Code file is a symlink or resolves outside the model, so it "
                                 "was not scanned — but Python may still import it."},
             "locations": [{"physicalLocation": {"artifactLocation": {"uri": rel}}}]}
            for rel in unscanned)
        run["properties"]["unscannedFiles"] = unscanned
    if compiled and sarif.get("runs"):
        run = sarif["runs"][0]
        run.setdefault("results", []).extend(
            {"ruleId": COMPILED_RULE, "level": "warning",
             "message": {"text": "Compiled/native module shipped with the model — it can be "
                                 "imported by custom code but has no source to review."},
             "locations": [{"physicalLocation": {"artifactLocation": {"uri": rel}}}]}
            for rel in compiled)
        run.setdefault("properties", {})["compiledFiles"] = compiled
    return sarif
