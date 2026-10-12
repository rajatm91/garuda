#!/usr/bin/env bash
# Static scan of google/gemma-4-26B-A4B-it → SARIF + HTML evidence pack.
#
# Usage:  scripts/scan_gemma-4-26b-a4b-it.sh [revision]      (default: main)
# Env:    read from ./.env if present — HF_TOKEN (avoids HF rate limits),
#         HF_XET_HIGH_PERFORMANCE=1 (faster download)
# Needs:  ~52 GB free disk for weights. syft/grype/gitleaks optional (soft-skip).
set -euo pipefail

REPO="google/gemma-4-26B-A4B-it"
REVISION="${1:-main}"
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
OUT="scan_${REPO//\//_}_$(date -u +%Y%m%dT%H%M%SZ)"

uv run scan all "$REPO" \
  --revision "$REVISION" \
  --expect-publisher google \
  --out "$OUT"

echo
echo "SARIF: $OUT/reports/scan_results.sarif"
echo "HTML:  $OUT/reports/scan_report.html"
echo "Free ~52 GB when done:  rm -rf $OUT/weights"
