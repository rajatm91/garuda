"""JSON I/O helpers with soft-fail semantics."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> Any | None:
    """Return parsed JSON, or None if missing/empty/invalid JSON."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:  # bad JSON or non-UTF-8 bytes
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


def model_files(root: Path, pattern: str) -> list[Path]:
    """Regular files under root matching pattern that really belong to the model.

    Model content is untrusted: skip symlinks and anything resolving outside root (a
    shipped ``requirements.txt -> ~/.ssh/config`` must not leak host files into the
    report), and snapshot_download's own bookkeeping files (see ``is_hf_cache``). Everything
    else — including files a repo commits under ``.cache/`` — is model content.
    """
    real_root = root.resolve()
    return sorted(
        p for p in root.rglob(pattern)
        if not is_hf_cache(p.relative_to(root))
        and not p.is_symlink() and p.is_file()
        and p.resolve().is_relative_to(real_root)
    )


_HF_BOOKKEEPING_SUFFIXES = {".metadata", ".lock", ".incomplete"}


def is_hf_cache(rel: Path) -> bool:
    """Only files snapshot_download itself writes. A repo can commit files under
    .cache/huggingface/ too (they land in the same place), so match exact names, never a
    whole directory: download/**/*.{metadata,lock,incomplete} and the .gitignore."""
    if rel.parts[:2] != (".cache", "huggingface"):
        return False
    if rel == Path(".cache/huggingface/.gitignore"):
        return True
    return rel.parts[2:3] == ("download",) and rel.suffix in _HF_BOOKKEEPING_SUFFIXES
