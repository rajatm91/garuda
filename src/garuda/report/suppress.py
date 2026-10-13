"""Policy suppressions: findings in files we deliberately ignore (default README.md).

Findings are kept in SARIF with a standard ``suppressions`` entry (GHAS/DefectDojo treat
them as suppressed) and excluded from the HTML verdict and counts — never silently dropped.

Fail-closed rules (model content is untrusted):
- Only suppressions garuda adds count. Tool-emitted ones (e.g. from in-source comments)
  are ignored by ``is_suppressed``.
- A file is ignored only if it is a real, regular, non-symlink *text* file inside the model
  (UTF-8, no NUL bytes) — a pickle or archive merely *named* README.md stays a finding.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

IGNORE_ENV = "GARUDA_IGNORE_FILES"
DEFAULT_IGNORE = "README.md"
MARKER = "garuda-policy"
_TEXT_PROBE_BYTES = 1 << 20


def ignored_names() -> set[str]:
    raw = os.environ.get(IGNORE_ENV, DEFAULT_IGNORE)
    return {n.strip().lower() for n in raw.split(",") if n.strip()}


def _uri(res: dict) -> str | None:
    locs = res.get("locations") or []
    return (locs[0].get("physicalLocation") or {}).get("artifactLocation", {}).get("uri") \
        if locs else None


def is_suppressed(res: dict) -> bool:
    return any((s.get("properties") or {}).get("source") == MARKER
               for s in res.get("suppressions") or [] if isinstance(s, dict))


def _is_plain_text(weights: Path, rel: str) -> bool:
    root = weights.resolve()
    f = weights / rel
    if f.is_symlink() or not f.is_file() or not f.resolve().is_relative_to(root):
        return False
    with f.open("rb") as fh:
        head = fh.read(_TEXT_PROBE_BYTES)
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as e:  # tolerate a multi-byte char cut at the probe boundary
        return e.start >= len(head) - 4
    return True


def apply_suppressions(sarif: dict, scan_dir: Path, names: set[str] | None = None) -> dict:
    names = ignored_names() if names is None else names
    if not names:
        return sarif
    weights = scan_dir / "weights"
    for run in sarif.get("runs") or []:
        for res in run.get("results") or []:
            uri = _uri(res)
            # real files only: archive members ("x.zip:README.md") stay findings
            if not uri or ":" in uri or "!" in uri or uri.startswith("/"):
                continue
            name = PurePosixPath(uri).name
            if name.lower() in names and _is_plain_text(weights, uri.removeprefix("./")):
                res.setdefault("suppressions", []).append({
                    "kind": "external", "status": "accepted",
                    "justification": f"Findings in {name} are ignored by scan policy "
                                     f"({IGNORE_ENV}).",
                    "properties": {"source": MARKER},
                })
    return sarif
