#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <num_seeds> <sim_time_seconds> [start_seed] [end_seed]" >&2
  exit 1
fi

NUM_SEEDS="$1"
SIM_TIME="$2"
START_SEED="${3:-1}"
END_SEED="${4:-$NUM_SEEDS}"

if [ -n "${BATCH_DIR:-}" ]; then
  BASE_DIR="$BATCH_DIR"
else
  STAMP=$(date +%Y%m%d-%H%M%S)
  BASE_DIR="results/batch-${STAMP}"
fi
mkdir -p "$BASE_DIR"

run_one() {
  local mode="$1"   # brpl|mrhof
  local drop="$2"   # 50 or 0
  local seed="$3"

  local mode_label
  if [ "$mode" = "brpl" ]; then
    mode_label="brpl"
  else
    mode_label="mrhof"
  fi

  local drop_label
  if [ "$drop" = "0" ]; then
    drop_label="off"
  else
    drop_label="on"
  fi

  if [ -n "${ONLY_MODE:-}" ] && [ "$ONLY_MODE" != "$mode_label" ]; then
    return 0
  fi
  if [ -n "${ONLY_DROP:-}" ] && [ "$ONLY_DROP" != "$drop_label" ]; then
    return 0
  fi

  local out_dir="$BASE_DIR/${mode_label}_${drop_label}/seed${seed}"
  mkdir -p "$out_dir"

  local csc_tmp="configs/tmp_${mode_label}_${drop_label}_seed${seed}.csc"

  if [ -d "$out_dir/run" ]; then
    echo "Skip ${mode_label}_${drop_label} seed ${seed}: already exists"
    return 0
  fi

  python3 scripts/gen_random_topology.py \
    --outfile "$csc_tmp" \
    --mode "$mode" \
    --nodes 51 \
    --area 200 \
    --seed "$seed" \
    --attacker-x 20 \
    --attacker-y 0 \
    --attack-drop "$drop"

  ./scripts/run_simulation.sh "$SIM_TIME" "$csc_tmp"

  local latest_run
  latest_run=$(ls -td results/run-* | head -1)

  cp "$csc_tmp" "$out_dir/"
  mv "$latest_run" "$out_dir/run"
}

for seed in $(seq "$START_SEED" "$END_SEED"); do
  echo "=== Seed $seed: BRPL attack ON ==="
  run_one brpl 50 "$seed"
  echo "=== Seed $seed: BRPL attack OFF ==="
  run_one brpl 0 "$seed"
  echo "=== Seed $seed: MRHOF attack ON ==="
  run_one mrhof 50 "$seed"
  echo "=== Seed $seed: MRHOF attack OFF ==="
  run_one mrhof 0 "$seed"
  echo "=== Seed $seed done ==="
  echo
  sleep 1
  
  # avoid name collision for temp configs
  rm -f configs/tmp_*_seed${seed}.csc
 done

echo "Batch results saved under: $BASE_DIR"
