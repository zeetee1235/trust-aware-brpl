#!/bin/bash
# Sweep ATTACK_DROP_PCT for a given Cooja config and summarize results.

set -euo pipefail

usage() {
  echo "Usage: $0 --sim <config.csc> --time <seconds> --drops <csv> --label <label>"
  echo "Example: $0 --sim configs/simulation_chain_brpl.csc --time 600 --drops 0,10,30,50,70,90 --label brpl"
}

SIM=""
SIM_TIME=""
DROPS=""
LABEL=""

while [ $# -gt 0 ]; do
  case "$1" in
    --sim) SIM="$2"; shift 2 ;;
    --time) SIM_TIME="$2"; shift 2 ;;
    --drops) DROPS="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    *) usage; exit 1 ;;
  esac
done

if [ -z "$SIM" ] || [ -z "$SIM_TIME" ] || [ -z "$DROPS" ] || [ -z "$LABEL" ]; then
  usage
  exit 1
fi

if [ ! -f "$SIM" ]; then
  echo "Error: simulation file not found: $SIM"
  exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT_DIR="results/sweep-${STAMP}-${LABEL}"
mkdir -p "$OUT_DIR"

SUMMARY="$OUT_DIR/summary.csv"
echo "label,drop_pct,pdr_overall,avg_delay_ms,sample_count,run_dir" > "$SUMMARY"

IFS=',' read -r -a DROP_LIST <<< "$DROPS"

for drop in "${DROP_LIST[@]}"; do
  TMP_SIM="/tmp/sim_${LABEL}_${drop}.csc"
  sed "s/ATTACK_DROP_PCT=[0-9]\\+/ATTACK_DROP_PCT=${drop}/g" "$SIM" > "$TMP_SIM"

  # Force rebuild so new ATTACK_DROP_PCT is applied
  make -C motes -f Makefile.attacker TARGET=cooja clean >/dev/null

  ./scripts/run_simulation.sh "$SIM_TIME" "$TMP_SIM"

  RUN_DIR="$(ls -td results/run-* | head -1)"
  PARSE_FILE="${RUN_DIR}/parse_results.txt"

  PDR="$(awk -F'PDR=' '/Overall:/ {gsub(/%/,"",$2); gsub(/ /,"",$2); print $2}' "$PARSE_FILE")"
  AVG_DELAY="$(awk -F'Average:' '/Average:/ {gsub(/ms/,"",$2); gsub(/ /,"",$2); print $2}' "$PARSE_FILE")"
  SAMPLE_COUNT="$(awk -F': ' '/Sample count:/ {print $2}' "$PARSE_FILE")"

  echo "${LABEL},${drop},${PDR},${AVG_DELAY:-},${SAMPLE_COUNT:-},${RUN_DIR}" >> "$SUMMARY"
done

echo "Sweep complete: $SUMMARY"
