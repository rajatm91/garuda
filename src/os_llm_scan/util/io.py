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
