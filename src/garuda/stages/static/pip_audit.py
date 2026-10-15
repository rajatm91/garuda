"""Step 06 — pip-audit of the requirements files the model ships.

When the repo ships no requirements file, record the third-party packages its custom
code imports instead: undeclared, unpinned dependencies that nothing can CVE-audit.
"""
from __future__ import annotations

import ast
import logging
import re
import shutil
import sys
import time
from pathlib import Path

from ...context import ScanContext, StageResult
from ...util.io import load_json, model_files, write_json, write_stub
from ...util.proc import run_tool

log = logging.getLogger(__name__)
OUT = "06_pip_audit.json"
BIN = "pip-audit"
MAX_REQ_BYTES = 1_000_000
# The model repo is untrusted: its requirements file must never steer pip (custom index,
# includes, editables, URLs/paths). Only plain `name==version` pins are audited, and
# pip-audit runs with --disable-pip --no-deps so nothing is downloaded, built or installed.
_PINNED = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9._,-]+\])?\s*==\s*[A-Za-z0-9.+!_-]+"
                     r"\s*(;[^@]*)?$")


def unsafe_lines(req: Path) -> list[str]:
    """Lines that are not plain pins (comments/blank lines allowed)."""
    if req.stat().st_size > MAX_REQ_BYTES:
        return [f"<file larger than {MAX_REQ_BYTES} bytes>"]
    bad = []
    for raw in req.read_text(errors="replace").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if line and not line.startswith("#") and not _PINNED.match(line):
            bad.append(raw.strip()[:200])
    return bad


def requirements_files(weights_dir: Path) -> list[Path]:
    return model_files(weights_dir, "requirements*.txt")


def third_party_imports(weights_dir: Path) -> dict[str, list[str]]:
    """{top-level module: [files importing it]} over shipped *.py, minus stdlib and the
    repo's own modules. Parsed with ast only — model code is never executed. Names are
    import names, not PyPI names (PIL, not pillow)."""
    files = [p for p in model_files(weights_dir, "*.py") if p.stat().st_size <= MAX_REQ_BYTES]
    local = {p.stem for p in files} | {p.parent.name for p in files if p.parent != weights_dir}
    found: dict[str, set[str]] = {}
    for f in files:
        try:
            tree = ast.parse(f.read_bytes())
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top not in sys.stdlib_module_names and top not in local and top != "__future__":
                    found.setdefault(top, set()).add(str(f.relative_to(weights_dir)))
    return {k: sorted(v) for k, v in sorted(found.items())}


def run(ctx: ScanContext) -> StageResult:
    out_path = ctx.raw_dir / OUT
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    def skip(reason: str) -> StageResult:
        write_stub(out_path, reason)
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=reason)

    reqs = requirements_files(ctx.weights_dir)
    if not reqs:
        reason = "model ships no requirements*.txt"
        write_json(out_path, {"skipped": reason,
                              "undeclared_imports": third_party_imports(ctx.weights_dir)})
        return StageResult(ran=False, duration_s=time.monotonic() - t0,
                           output_path=out_path, skip_reason=reason)
    if shutil.which(BIN) is None:
        return skip(f"{BIN} not installed")

    dependencies, audited, failed = [], [], []
    for req in reqs:
        rel = str(req.relative_to(ctx.weights_dir))
        if bad := unsafe_lines(req):
            failed.append({"file": rel, "refused": "non-pinned or pip-option lines", "lines": bad})
            continue
        part = ctx.raw_dir / f"06_pip_audit.{len(audited) + len(failed)}.json"
        part.unlink(missing_ok=True)
        res = run_tool(BIN, [BIN, "--disable-pip", "--no-deps", "-r", str(req),
                             "--format", "json", "--output", str(part)],
                       stderr_path=ctx.raw_dir / "06_pip_audit.stderr.log", cwd=ctx.scan_dir)
        data = load_json(part)
        part.unlink(missing_ok=True)
        # exit 1 = vulnerabilities found (completed audit)
        if res.exit_code in (0, 1) and isinstance(data, dict) and "dependencies" in data:
            dependencies += [{**d, "requirements_file": rel} for d in data["dependencies"]]
            audited.append(rel)
        else:
            failed.append({"file": rel, "exit_code": res.exit_code})

    if not audited:
        return skip(f"{BIN} failed on every requirements file: {failed}")
    write_json(out_path, {"requirements_files": audited, "failed": failed,
                          "dependencies": dependencies})
    return StageResult(ran=not failed, duration_s=time.monotonic() - t0, output_path=out_path,
                       skip_reason=f"{BIN} failed on {failed}" if failed else None)
