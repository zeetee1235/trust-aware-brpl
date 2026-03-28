#!/usr/bin/env bash
# Post-process random-topology main experiment results into paper artifacts.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS_DIR="${ROOT_DIR}/results/random_topo_main_v1"
PROTO_A="TABRPL"
PROTO_B="BRPL"
FIG_DIR="${ROOT_DIR}/docs/paper/figures/new/main"
OUT_DIR="${ROOT_DIR}/docs/paper/generated/main"
BUILD_PDF=1
BOOTSTRAP_RESAMPLES=10000

resolve_path_arg() {
  local p="$1"
  case "$p" in
    /*) printf '%s\n' "$p" ;;
    *) printf '%s\n' "${ROOT_DIR}/$p" ;;
  esac
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --results-dir) RESULTS_DIR="$(resolve_path_arg "$2")"; shift 2 ;;
    --proto-a) PROTO_A="$2"; shift 2 ;;
    --proto-b) PROTO_B="$2"; shift 2 ;;
    --fig-dir) FIG_DIR="$(resolve_path_arg "$2")"; shift 2 ;;
    --out-dir) OUT_DIR="$(resolve_path_arg "$2")"; shift 2 ;;
    --bootstrap-resamples) BOOTSTRAP_RESAMPLES="$2"; shift 2 ;;
    --no-pdf) BUILD_PDF=0; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

echo "=== Main experiment artifact generation ==="
echo "results : $RESULTS_DIR"
echo "proto A : $PROTO_A"
echo "proto B : $PROTO_B"
echo "fig dir : $FIG_DIR"
echo "out dir : $OUT_DIR"
echo "boot CI : $BOOTSTRAP_RESAMPLES resamples"

python3 "${ROOT_DIR}/docs/paper/generate_main_experiment_artifacts.py" \
  --results-dir "${RESULTS_DIR}" \
  --proto-a "${PROTO_A}" \
  --proto-b "${PROTO_B}" \
  --fig-dir "${FIG_DIR}" \
  --out-dir "${OUT_DIR}" \
  --bootstrap-resamples "${BOOTSTRAP_RESAMPLES}"

if [[ "$BUILD_PDF" -eq 1 ]]; then
  echo "=== Building paper PDF ==="
  (
    cd "${ROOT_DIR}/docs/paper"
    latexmk -pdf -interaction=nonstopmode paper.tex
  )
fi

echo "=== Done ==="
echo "snippet: ${OUT_DIR}/main_results_auto.tex"
echo "figures: ${FIG_DIR}"
