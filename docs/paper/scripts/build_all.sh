#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$PROJECT_DIR"

RUNS_PDR_CSV="${1:-}"
OUT_DIR="${2:-docs/paper/figures}"

if [[ -z "$RUNS_PDR_CSV" ]]; then
  LATEST=$(ls -td results/experiments-* 2>/dev/null | head -n 1 || true)
  if [[ -z "$LATEST" ]]; then
    echo "No results/experiments-* found."
    exit 1
  fi

  if [[ -f "$LATEST/parsed_quick/runs_pdr.csv" ]]; then
    RUNS_PDR_CSV="$LATEST/parsed_quick/runs_pdr.csv"
  elif [[ -f "$LATEST/parsed/runs_pdr.csv" ]]; then
    RUNS_PDR_CSV="$LATEST/parsed/runs_pdr.csv"
  else
    echo "runs_pdr.csv not found in latest results dir: $LATEST"
    echo "Provide path explicitly: docs/paper/scripts/build_all.sh <runs_pdr.csv>"
    exit 1
  fi
fi

echo "[paper] input CSV: $RUNS_PDR_CSV"
echo "[paper] output dir: $OUT_DIR"

python3 docs/paper/scripts/build_schematic_svgs.py
Rscript docs/paper/scripts/build_paper_figures.R "$RUNS_PDR_CSV" "$OUT_DIR" "docs/paper/data/attacker_parent_ratio_cache.csv"

echo "[paper] done"
