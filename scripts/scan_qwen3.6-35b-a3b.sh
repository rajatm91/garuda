#!/usr/bin/env bash
# Static scan of Qwen/Qwen3.6-35B-A3B → SARIF + HTML evidence pack.
#
# Usage:  scripts/scan_qwen3.6-35b-a3b.sh [revision]      (default: main)
# Env:    read from ./.env if present — HF_TOKEN (avoids HF rate limits),
#         HF_XET_HIGH_PERFORMANCE=1 (faster download)
# Needs:  ~72 GB free disk for weights. syft/grype/gitleaks optional (soft-skip).
set -euo pipefail

REPO="Qwen/Qwen3.6-35B-A3B"
REVISION="${1:-main}"
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
OUT="scan_${REPO//\//_}_$(date -u +%Y%m%dT%H%M%SZ)"

uv run scan all "$REPO" \
  --revision "$REVISION" \
  --expect-publisher Qwen \
  --out "$OUT"

echo
echo "SARIF: $OUT/reports/scan_results.sarif"
echo "HTML:  $OUT/reports/scan_report.html"
echo "Free ~72 GB when done:  rm -rf $OUT/weights"
