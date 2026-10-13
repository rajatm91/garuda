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


def model_files(root: Path, pattern: str) -> list[Path]:
    """Regular files under root matching pattern that really belong to the model.

    Model content is untrusted: skip symlinks and anything resolving outside root (a
    shipped ``requirements.txt -> ~/.ssh/config`` must not leak host files into the
    report), and the HF download cache — only snapshot_download's own top-level
    ``.cache/huggingface/``; any other ``.cache`` dir is model content and is included so
    nothing can hide there.
    """
    real_root = root.resolve()
    return sorted(
        p for p in root.rglob(pattern)
        if not is_hf_cache(p.relative_to(root))
        and not p.is_symlink() and p.is_file()
        and p.resolve().is_relative_to(real_root)
    )


def is_hf_cache(rel: Path) -> bool:
    return rel.parts[:2] == (".cache", "huggingface")
