"""Embed already-SARIF tool outputs (grype, gitleaks) into the aggregate log."""
from __future__ import annotations

import json
from pathlib import Path


def embed_runs(sarif_path: Path) -> list[dict]:
    """Return the ``runs`` array of a SARIF file, or [] if missing/empty/invalid."""
    if not sarif_path.exists() or sarif_path.stat().st_size == 0:
        return []
    try:
        return json.loads(sarif_path.read_text()).get("runs", [])
    except json.JSONDecodeError:
        return []
