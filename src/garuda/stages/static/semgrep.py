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

    # Case-insensitive, incl. .pyw: "Modeling.PY" is still Python that custom code can load.
    code = [p for p in model_files(ctx.weights_dir, "*") if _is_python(p)]
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
    # semgrep picks the language from the extension → stage non-".py" names as "<name>.py"
    staged = {t if t.endswith(".py") else f"{t}.py": t for t in targets}
    exit_code = 0
    if code:
        exit_code = _scan(ctx, code, list(staged), configs, out_path)
        sarif = load_json(out_path)
        if not (isinstance(sarif, dict) and "runs" in sarif):
            return skip(f"{BIN} exit={exit_code}, no SARIF produced "
                        "(see 12_semgrep.stderr.log)")
        _unstage_uris(sarif, staged)
    else:
        sarif = {"version": "2.1.0", "runs": [{"tool": {"driver": {"name": "Semgrep OSS"}},
                                                "results": []}]}
    sarif = _annotate(sarif, configs, targets, unscanned, compiled)
    if exit_code != 0 and sarif.get("runs"):
        # file-less PARSE_RULE result = whole run untrusted (review's OLR007 coverage reads this)
        sarif["runs"][0].setdefault("results", []).append({
            "ruleId": PARSE_RULE, "level": "warning",
            "message": {"text": f"semgrep exited {exit_code}; results may be incomplete."}})
    partial = _analysis_failures(sarif, staged)
    write_json(out_path, sarif)
    if partial:  # semgrep exits 0 on these: affected files/rules were (partly) not analysed
        return StageResult(ran=False, duration_s=time.monotonic() - t0, output_path=out_path,
                           skip_reason=f"{BIN} reported {len(partial)} analysis problem(s): "
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
                "--timeout=0", "--disable-nosem",  # model code can't "# nosemgrep" itself
                "--quiet"]  # no per-file size/time caps that silently skip
        for c in configs:
            argv += ["--config", c]
        # Untrusted filenames: "./" prefix so "--config=…"/"--exclude=…" is never a flag.
        argv += [f"./{t}" for t in targets]
        res = run_tool(BIN, argv, stderr_path=ctx.raw_dir / "12_semgrep.stderr.log",
                       timeout=TIMEOUT_S, cwd=stage)
    return res.exit_code


_PY_SUFFIXES = {".py", ".pyw"}


def _is_python(p: Path) -> bool:
    return p.suffix.lower() in _PY_SUFFIXES


def _unstage_uris(sarif: dict, staged: dict[str, str]) -> None:
    """Map staged "<name>.py" URIs back to the model's real file names."""
    for run in sarif.get("runs") or []:
        for res in run.get("results") or []:
            for loc in res.get("locations") or []:
                art = (loc.get("physicalLocation") or {}).get("artifactLocation") or {}
                uri = str(art.get("uri", "")).removeprefix("./")
                if uri in staged:
                    art["uri"] = staged[uri]


def _unscannable_code(root: Path) -> list[str]:
    """*.py the model ships that we must not read (symlink / resolves outside the model) but
    that Python could still import."""
    real_root = root.resolve()
    out = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if not _is_python(p) or is_hf_cache(rel):
            continue
        if p.is_symlink() or not p.resolve().is_relative_to(real_root):
            out.append(str(rel))
    return sorted(out)


UNSCANNED_RULE = "garuda.model-code.unscanned-code"
COMPILED_RULE = "garuda.model-code.compiled-code"
PARSE_RULE = "garuda.model-code.not-fully-analysed"
_COMPILED_SUFFIXES = {".pyc", ".pyo", ".so", ".pyd", ".dylib", ".dll"}
_FILE_IN_TEXT = re.compile(r"(?P<file>[^\s`'\"]+\.pyw?(?:\.py)?)(?::\d+)?", re.IGNORECASE)


def _compiled_code(root: Path) -> list[str]:
    """Native/bytecode modules custom code could import — no source to review."""
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")
                  if p.suffix.lower() in _COMPILED_SUFFIXES and not is_hf_cache(p.relative_to(root)))


def _analysis_failures(sarif: dict, staged: dict[str, str]) -> list[str]:
    """Anything semgrep says it could not do — fail closed.

    semgrep keeps exit 0 and executionSuccessful=true for syntax errors, timeouts,
    out-of-memory, partial parsing, lexing errors and rules that fail to load, and only emits
    a notification. Every notification (and executionSuccessful=false) becomes a warning
    result and marks the step incomplete."""
    problems: list[str] = []
    for run in sarif.get("runs") or []:
        for inv in run.get("invocations") or []:
            if inv.get("executionSuccessful") is False:
                problems.append("execution unsuccessful")
                run.setdefault("results", []).append({
                    "ruleId": PARSE_RULE, "level": "warning",
                    "message": {"text": "semgrep reported an unsuccessful execution; results "
                                        "are incomplete."}})
            for n in inv.get("toolExecutionNotifications") or []:
                text = (n.get("message") or {}).get("text") or ""
                kind = (n.get("descriptor") or {}).get("id") or "notification"
                locs = [(lc.get("physicalLocation") or {}).get("artifactLocation", {}).get("uri")
                        for lc in n.get("locations") or []]
                m = _FILE_IN_TEXT.search(text)
                f = (next((u for u in locs if u), None) or (m.group("file") if m else ""))
                f = str(f).removeprefix("./")
                f = staged.get(f, f)
                problems.append(f"{kind}: {f or 'run'}")
                run.setdefault("results", []).append({
                    "ruleId": PARSE_RULE, "level": "warning",
                    "message": {"text": f"semgrep could not fully analyse this ({kind}), so "
                                        f"parts were not checked: {text.splitlines()[0][:200]}"
                                if text else f"semgrep {kind}"},
                    **({"locations": [{"physicalLocation": {"artifactLocation": {"uri": f}}}]}
                       if f else {}),
                })
    return sorted(set(problems))


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
