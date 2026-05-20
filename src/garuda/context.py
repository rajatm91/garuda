"""ScanContext + StageResult — shared types passed through the stage pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScanContext:
    scan_dir: Path
    repo: str
    revision: str | None
    local_path: Path | None  # None → HF Hub source

    @property
    def raw_dir(self) -> Path:
        return self.scan_dir / "raw"

    @property
    def weights_dir(self) -> Path:
        return self.scan_dir / "weights"

    @property
    def reports_dir(self) -> Path:
        return self.scan_dir / "reports"

    @property
    def is_local_source(self) -> bool:
        return self.local_path is not None


@dataclass(frozen=True)
class StageResult:
    ran: bool
    duration_s: float
    output_path: Path
    skip_reason: str | None
