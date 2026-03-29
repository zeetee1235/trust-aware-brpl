#!/usr/bin/env bash
# Run 4-way random-topology reruns with attack-drop sweep under one fixed policy snapshot.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER="${ROOT_DIR}/scripts/run_random_topo_sweep.sh"

PROTOCOLS="RPL,BRPL,SMTRUST,TABRPL"
DENSITIES="sparse,medium,dense"
TOPOLOGY_SEEDS="1-25"
RUN_SEEDS="1-5"
ATTACK_PROFILE="sinkhole_drop"
DROPS="0,25,50,75,100"
JOBS=12
RESULTS_ROOT="${ROOT_DIR}/results/random_topo_drop_sweep"
RERUN=0
DRY_RUN=0
KEEP_RUN_ROOT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --protocols) PROTOCOLS="$2"; shift 2 ;;
    --densities) DENSITIES="$2"; shift 2 ;;
    --topology-seeds) TOPOLOGY_SEEDS="$2"; shift 2 ;;
    --run-seeds) RUN_SEEDS="$2"; shift 2 ;;
    --attack-profile) ATTACK_PROFILE="$2"; shift 2 ;;
    --drops) DROPS="$2"; shift 2 ;;
    --jobs) JOBS="$2"; shift 2 ;;
    --results-root) RESULTS_ROOT="$2"; shift 2 ;;
    --rerun|--force-rerun) RERUN=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --keep-run-root) KEEP_RUN_ROOT=1; shift ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -x "$RUNNER" ]]; then
  echo "ERROR: runner not found or not executable: $RUNNER" >&2
  exit 1
fi

IFS=',' read -r -a DROP_LIST <<< "$DROPS"
if [[ "${#DROP_LIST[@]}" -eq 0 ]]; then
  echo "ERROR: no drop values provided" >&2
  exit 1
fi

TOTAL="${#DROP_LIST[@]}"
INDEX=0
for d in "${DROP_LIST[@]}"; do
  drop="${d//[[:space:]]/}"
  if [[ -z "$drop" ]]; then
    continue
  fi
  if ! [[ "$drop" =~ ^[0-9]+$ ]]; then
    echo "ERROR: invalid drop value: $drop" >&2
    exit 1
  fi
  if (( drop < 0 || drop > 100 )); then
    echo "ERROR: drop value out of range [0,100]: $drop" >&2
    exit 1
  fi

  INDEX=$((INDEX + 1))
  DPAD=$(printf "%03d" "$drop")
  OUT_DIR="${RESULTS_ROOT}/drop_${DPAD}"
  echo "[${INDEX}/${TOTAL}] drop=${drop}% -> ${OUT_DIR}"

  CMD=(
    bash "$RUNNER"
    --protocols "$PROTOCOLS"
    --densities "$DENSITIES"
    --topology-seeds "$TOPOLOGY_SEEDS"
    --run-seeds "$RUN_SEEDS"
    --attack-profile "$ATTACK_PROFILE"
    --attack-drop-pct "$drop"
    --jobs "$JOBS"
    --results-dir "$OUT_DIR"
  )
  if [[ "$RERUN" -eq 1 ]]; then
    CMD+=(--rerun)
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    CMD+=(--dry-run)
  fi
  if [[ "$KEEP_RUN_ROOT" -eq 1 ]]; then
    CMD+=(--keep-run-root)
  fi

  "${CMD[@]}"
done

echo "[OK] random-topology drop sweep complete: ${RESULTS_ROOT}"
