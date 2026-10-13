"""Reviewer notes: human context attached to a scan (scan_dir/review_notes.json).

Format: [{"title": str, "note": str, "applies_to": "<model-relative path>" | null}, ...]
Notes are rendered in the HTML summary, stored in SARIF run properties, and copied onto every
finding whose location matches ``applies_to`` (result.properties.reviewerNote).
"""
from __future__ import annotations

from pathlib import Path

from ..util.io import load_json

FILE = "review_notes.json"


def load_notes(scan_dir: Path) -> list[dict]:
    data = load_json(scan_dir / FILE)
    if not isinstance(data, list):
        return []
    return [
        {"title": str(n.get("title") or "Reviewer note"), "note": str(n["note"]),
         "applies_to": str(n["applies_to"]) if n.get("applies_to") else None}
        for n in data if isinstance(n, dict) and n.get("note")
    ]


def apply_notes(sarif: dict, notes: list[dict]) -> dict:
    if not notes:
        return sarif
    by_path: dict[str, list[str]] = {}
    for n in notes:
        if n["applies_to"]:
            by_path.setdefault(n["applies_to"], []).append(f"{n['title']}: {n['note']}")
    runs = sarif.get("runs") or []
    for run in runs:
        for res in run.get("results") or []:
            locs = res.get("locations") or []
            uri = (locs[0].get("physicalLocation") or {}).get("artifactLocation", {}).get("uri") \
                if locs else None
            if uri in by_path:
                res.setdefault("properties", {})["reviewerNote"] = " | ".join(by_path[uri])
    if runs:
        runs[0].setdefault("properties", {})["reviewerNotes"] = notes
    return sarif
