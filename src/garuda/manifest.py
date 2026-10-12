"""manifest.json — explicit pipeline-state record (spec §5.4)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .util.io import load_json, write_json

MANIFEST_VERSION = "2.0.0"


@dataclass
class Manifest:
    version: str
    repo: str
    revision_requested: str | None
    resolved_sha: str | None
    source: dict[str, Any]
    timestamp: str
    stages: dict[str, dict[str, Any]]
    tool_versions: dict[str, str] = field(default_factory=dict)
    scan_dir: Path | None = None  # not serialised

    @classmethod
    def create(cls, *, scan_dir: Path, repo: str, revision: str | None,
               source_mode: str, source_abs_path: str | None) -> "Manifest":
        return cls(
            version=MANIFEST_VERSION,
            repo=repo,
            revision_requested=revision,
            resolved_sha=None,
            source={"mode": source_mode, "abs_path": source_abs_path, "weights_sha256": None},
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            stages={
                "static":  {"ran": False, "duration_s": 0.0, "skipped_steps": []},
            },
            scan_dir=scan_dir,
        )

    def mark_static_done(self, *, duration_s: float, skipped_steps: list[str]) -> None:
        self.stages["static"] = {
            "ran": True, "duration_s": duration_s, "skipped_steps": skipped_steps,
        }

    def to_dict(self) -> dict:
        d = asdict(self); d.pop("scan_dir", None); return d


def save_manifest(m: Manifest) -> None:
    assert m.scan_dir is not None, "scan_dir required to save"
    write_json(m.scan_dir / "manifest.json", m.to_dict())


def load_manifest(scan_dir: Path) -> Manifest:
    data = load_json(scan_dir / "manifest.json")
    if data is None:
        raise FileNotFoundError(f"manifest.json missing in {scan_dir}")
    return Manifest(
        version=data["version"], repo=data["repo"],
        revision_requested=data.get("revision_requested"),
        resolved_sha=data.get("resolved_sha"),
        source=data.get("source", {}), timestamp=data["timestamp"],
        stages=data["stages"], tool_versions=data.get("tool_versions", {}),
        scan_dir=scan_dir,
    )
