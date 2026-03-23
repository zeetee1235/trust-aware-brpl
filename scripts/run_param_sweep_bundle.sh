#!/usr/bin/env bash
# One-shot orchestrator for TA-BRPL parameter sweeps (no core code edits)
#
# It wraps existing generator scripts + run_sweep.sh:
#   - threshold / soft_penalty / relative / margin / path_margin / prr
# and can optionally chain loss-attack matrix sweep.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_SWEEP="${ROOT_DIR}/scripts/run_sweep.sh"
RUN_LOSS_ATTACK="${ROOT_DIR}/scripts/run_loss_attack_sweep.sh"

SEEDS="1-30"
JOBS=12
RERUN=0
DRY_RUN=0
LOSSES="90,70,50"             # maps to suffixes _LOSS90/_LOSS70/_LOSS50
FAMILIES="threshold,soft,relative,margin,path,prr"
WITH_LOSS_ATTACK=0
PROTOCOLS_BASE="RPL,BRPL,SMTRUST,TABRPL"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seeds) SEEDS="$2"; shift 2 ;;
    --jobs) JOBS="$2"; shift 2 ;;
    --rerun|--force-rerun) RERUN=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --losses) LOSSES="$2"; shift 2 ;;
    --families) FAMILIES="$2"; shift 2 ;;
    --with-loss-attack) WITH_LOSS_ATTACK=1; shift ;;
    --base-protocols) PROTOCOLS_BASE="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# family -> generator mapping
get_generator() {
  case "$1" in
    threshold) echo "scripts/generate_threshold_sweep_variants.py" ;;
    soft)      echo "scripts/generate_soft_penalty_sweep_variants.py" ;;
    relative)  echo "scripts/generate_relative_sweep_variants.py" ;;
    margin)    echo "scripts/generate_margin_sweep_variants.py" ;;
    path)      echo "scripts/generate_path_margin_sweep_variants.py" ;;
    prr)       echo "scripts/generate_prr_sweep_variants.py" ;;
    *) return 1 ;;
  esac
}

run_one_sweep() {
  local proto="$1"
  local suffix="$2"

  local cmd=("$RUN_SWEEP" --protocols "$proto" --seeds "$SEEDS" --jobs "$JOBS" --suffix "$suffix")
  if [[ "$RERUN" -eq 1 ]]; then
    cmd+=(--rerun)
  fi

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  DRY: ${cmd[*]}"
  else
    "${cmd[@]}"
  fi
}

IFS=',' read -r -a LOSS_ARR <<< "$LOSSES"
IFS=',' read -r -a FAMILY_ARR <<< "$FAMILIES"

# 1) Optional base protocol LOSS sweeps
for L in "${LOSS_ARR[@]}"; do
  LTRIM="${L// /}"
  SUFFIX="_LOSS${LTRIM}"
  echo "[BASE] protocols=${PROTOCOLS_BASE} suffix=${SUFFIX}"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  DRY: $RUN_SWEEP --protocols $PROTOCOLS_BASE --seeds $SEEDS --jobs $JOBS --suffix $SUFFIX $([[ "$RERUN" -eq 1 ]] && echo --rerun)"
  else
    if [[ "$RERUN" -eq 1 ]]; then
      "$RUN_SWEEP" --protocols "$PROTOCOLS_BASE" --seeds "$SEEDS" --jobs "$JOBS" --suffix "$SUFFIX" --rerun
    else
      "$RUN_SWEEP" --protocols "$PROTOCOLS_BASE" --seeds "$SEEDS" --jobs "$JOBS" --suffix "$SUFFIX"
    fi
  fi
done

# 2) Parameter-family sweeps
for fam in "${FAMILY_ARR[@]}"; do
  fam_trim="${fam// /}"
  [[ -z "$fam_trim" ]] && continue

  gen_rel="$(get_generator "$fam_trim" || true)"
  if [[ -z "$gen_rel" ]]; then
    echo "[WARN] unknown family: $fam_trim (skip)"
    continue
  fi

  gen_abs="${ROOT_DIR}/${gen_rel}"
  echo "[FAMILY] $fam_trim -> $gen_rel"

  proto_csv="$(python3 "$gen_abs")"
  if [[ -z "$proto_csv" ]]; then
    echo "[WARN] generator returned empty protocol list: $gen_rel"
    continue
  fi

  IFS=',' read -r -a PROTO_ARR <<< "$proto_csv"
  for proto in "${PROTO_ARR[@]}"; do
    ptrim="${proto// /}"
    [[ -z "$ptrim" ]] && continue
    for L in "${LOSS_ARR[@]}"; do
      LTRIM="${L// /}"
      SUFFIX="_LOSS${LTRIM}"
      echo "  [RUN] proto=${ptrim} suffix=${SUFFIX}"
      run_one_sweep "$ptrim" "$SUFFIX"
    done
  done
done

# 3) Optional loss-attack matrix sweep
if [[ "$WITH_LOSS_ATTACK" -eq 1 ]]; then
  echo "[MATRIX] run_loss_attack_sweep.sh"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    "$RUN_LOSS_ATTACK" --protocols "$PROTOCOLS_BASE" --seeds "$SEEDS" --jobs "$JOBS" --dry-run
  else
    if [[ "$RERUN" -eq 1 ]]; then
      "$RUN_LOSS_ATTACK" --protocols "$PROTOCOLS_BASE" --seeds "$SEEDS" --jobs "$JOBS" --rerun
    else
      "$RUN_LOSS_ATTACK" --protocols "$PROTOCOLS_BASE" --seeds "$SEEDS" --jobs "$JOBS"
    fi
  fi
fi

echo "[DONE] Parameter sweep bundle completed."
