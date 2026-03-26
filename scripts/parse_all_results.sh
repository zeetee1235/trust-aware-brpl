#!/usr/bin/env bash
# Parse all sweep result directories (results/results_*) with parse_results.py.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PARSER="${ROOT_DIR}/scripts/parse_results.py"
RESULTS_ROOT="${ROOT_DIR}/results"

if [[ ! -f "$PARSER" ]]; then
  echo "ERROR: parser not found: $PARSER" >&2
  exit 1
fi

mapfile -t TARGET_DIRS < <(find "$RESULTS_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'results_*' | sort)

if [[ "${#TARGET_DIRS[@]}" -eq 0 ]]; then
  echo "No results_* directories found under $RESULTS_ROOT"
  exit 0
fi

for dir in "${TARGET_DIRS[@]}"; do
  echo "== Parse target: $dir =="

  sim_count="$(find "$dir" -type f -name 'sim.log' 2>/dev/null | wc -l)"
  if [[ "$sim_count" -eq 0 ]]; then
    echo "  [SKIP] sim.log not found"
    continue
  fi

  protocols="$(find "$dir" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | paste -sd, -)"
  if [[ -z "$protocols" ]]; then
    echo "  [SKIP] protocol directories not found"
    continue
  fi

  python3 "$PARSER" --results-dir "$dir" --protocols "$protocols"
done

echo "[DONE] parse_all_results.sh completed."
