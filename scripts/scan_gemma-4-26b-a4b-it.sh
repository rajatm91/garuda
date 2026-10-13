#!/usr/bin/env bash
# Static scan of google/gemma-4-26B-A4B-it inside the garuda Docker image → SARIF + HTML.
# Runs in Linux so modelaudit can fully analyse weight shards (its shard pinning
# is unavailable on macOS).
#
# Usage:  scripts/scan_gemma-4-26b-a4b-it.sh [revision]      (default: main)
# Env:    ./.env passed to the container if present — HF_TOKEN, HF_XET_HIGH_PERFORMANCE
# Needs:  docker, image garuda:latest (docker build -t garuda:latest .), ~52 GB free disk.
set -euo pipefail

REPO="google/gemma-4-26B-A4B-it"
REVISION="${1:-main}"
cd "$(dirname "$0")/.."
OUT="scan_${REPO//\//_}_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
ENV_FILE=()
[[ -f .env ]] && ENV_FILE=(--env-file .env)

docker run --rm "${ENV_FILE[@]}" -v "$PWD/$OUT":/scans/out garuda:latest \
  all "$REPO" --revision "$REVISION" --expect-publisher google --out /scans/out

echo
echo "SARIF: $OUT/reports/scan_results.sarif"
echo "HTML:  $OUT/reports/scan_report.html"
echo "Free ~52 GB when done:  rm -rf $OUT/weights"
