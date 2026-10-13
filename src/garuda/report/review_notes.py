"""Reviewer notes: human context attached to a scan (scan_dir/review_notes.json).

Format: [{"title": str, "note": str, "applies_to": "<model-relative path>" | null,
          "level": "error" | "warning" | "note" (optional)}, ...]
A ``level`` re-levels every finding in ``applies_to`` (reviewer decision, e.g. a script that
only matters for old library versions); the tool's level is kept as properties.originalLevel.
Notes are rendered in the HTML summary, stored in SARIF run properties, and copied onto every
finding whose location matches ``applies_to`` (result.properties.reviewerNote).
"""
from __future__ import annotations

from pathlib import Path

from ..util.io import load_json

FILE = "review_notes.json"
_LEVELS = {"error", "warning", "note"}


def load_notes(scan_dir: Path) -> list[dict]:
    data = load_json(scan_dir / FILE)
    if not isinstance(data, list):
        return []
    return [
        {"title": str(n.get("title") or "Reviewer note"), "note": str(n["note"]),
         "applies_to": str(n["applies_to"]) if n.get("applies_to") else None,
         "level": n["level"] if n.get("level") in _LEVELS and n.get("applies_to") else None}
        for n in data if isinstance(n, dict) and n.get("note")
    ]


def apply_notes(sarif: dict, notes: list[dict]) -> dict:
    if not notes:
        return sarif
    by_path: dict[str, list[str]] = {}
    relevel: dict[str, str] = {}
    for n in notes:
        if n["applies_to"]:
            by_path.setdefault(n["applies_to"], []).append(f"{n['title']}: {n['note']}")
            if n["level"]:
                relevel[n["applies_to"]] = n["level"]
    runs = sarif.get("runs") or []
    for run in runs:
        for res in run.get("results") or []:
            locs = res.get("locations") or []
            uri = (locs[0].get("physicalLocation") or {}).get("artifactLocation", {}).get("uri") \
                if locs else None
            if uri in by_path:
                props = res.setdefault("properties", {})
                props["reviewerNote"] = " | ".join(by_path[uri])
                if uri in relevel and res.get("level") != relevel[uri]:
                    props["originalLevel"] = res.get("level")
                    res["level"] = relevel[uri]
    if runs:
        runs[0].setdefault("properties", {})["reviewerNotes"] = notes
    return sarif
