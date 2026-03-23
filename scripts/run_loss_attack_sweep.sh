#!/usr/bin/env bash
# Run LOSS x ATTACK_DROP matrix using existing run_sweep.sh (no core code changes)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
GEN="${ROOT_DIR}/scripts/generate_loss_attack_variants.py"
RUN_SWEEP="${ROOT_DIR}/scripts/run_sweep.sh"

PROTOCOLS="RPL,BRPL,SMTRUST,TABRPL"
SEEDS="1-30"
JOBS=12
LOSSES="0,10,20"
DROPS="0,30,50,70,100"
RERUN=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --protocols) PROTOCOLS="$2"; shift 2 ;;
    --seeds) SEEDS="$2"; shift 2 ;;
    --jobs) JOBS="$2"; shift 2 ;;
    --losses) LOSSES="$2"; shift 2 ;;
    --drops) DROPS="$2"; shift 2 ;;
    --rerun|--force-rerun) RERUN=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

python3 "$GEN" --protocols "$PROTOCOLS" --losses "$LOSSES" --drops "$DROPS"

IFS=',' read -r -a LOSS_ARR <<< "$LOSSES"
IFS=',' read -r -a DROP_ARR <<< "$DROPS"

TOTAL=$(( ${#LOSS_ARR[@]} * ${#DROP_ARR[@]} ))
IDX=0

for L in "${LOSS_ARR[@]}"; do
  LTRIM="${L// /}"
  LPAD=$(printf "%02d" "$LTRIM")
  for D in "${DROP_ARR[@]}"; do
    DTRIM="${D// /}"
    DPAD=$(printf "%03d" "$DTRIM")
    SUFFIX="_L${LPAD}_A${DPAD}"
    IDX=$((IDX + 1))

    echo "[${IDX}/${TOTAL}] loss=${LTRIM}% drop=${DTRIM}% suffix=${SUFFIX}"

    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "  DRY: $RUN_SWEEP --protocols $PROTOCOLS --seeds $SEEDS --jobs $JOBS --suffix $SUFFIX $([[ "$RERUN" -eq 1 ]] && echo --rerun)"
      continue
    fi

    if [[ "$RERUN" -eq 1 ]]; then
      "$RUN_SWEEP" --protocols "$PROTOCOLS" --seeds "$SEEDS" --jobs "$JOBS" --suffix "$SUFFIX" --rerun
    else
      "$RUN_SWEEP" --protocols "$PROTOCOLS" --seeds "$SEEDS" --jobs "$JOBS" --suffix "$SUFFIX"
    fi
  done
done

echo "[DONE] LOSS x ATTACK_DROP sweep completed."
