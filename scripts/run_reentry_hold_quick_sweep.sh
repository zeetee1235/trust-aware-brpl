#!/usr/bin/env bash
# Quick sweep for NA re-entry suppression hold time.
# Runs random-topology quickcheck with minimal experiment-code changes by
# patching Makefile.tabrpl macro overrides between runs.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MAKEFILE="${ROOT_DIR}/motes/Makefile.tabrpl"
RUNNER="${ROOT_DIR}/scripts/run_random_topo_sweep.sh"

HOLDS="300,600,900"
ATT_MARGIN="180"
DENSITIES="sparse,medium,dense"
TOPOLOGY_SEEDS="1-25"
RUN_SEEDS="1-3"
PROTOCOLS="BRPL,TABRPL"
ATTACK_PROFILE="sinkhole_drop"
JOBS=12
RESULTS_ROOT="${ROOT_DIR}/results/random_topo_quick_att_reentry"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --holds) HOLDS="$2"; shift 2 ;;
    --att-margin) ATT_MARGIN="$2"; shift 2 ;;
    --densities) DENSITIES="$2"; shift 2 ;;
    --topology-seeds) TOPOLOGY_SEEDS="$2"; shift 2 ;;
    --run-seeds) RUN_SEEDS="$2"; shift 2 ;;
    --protocols) PROTOCOLS="$2"; shift 2 ;;
    --attack-profile) ATTACK_PROFILE="$2"; shift 2 ;;
    --jobs) JOBS="$2"; shift 2 ;;
    --results-root) RESULTS_ROOT="$2"; shift 2 ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$MAKEFILE" ]]; then
  echo "ERROR: missing makefile: $MAKEFILE" >&2
  exit 1
fi

if [[ ! -x "$RUNNER" ]]; then
  echo "ERROR: missing runner: $RUNNER" >&2
  exit 1
fi

BACKUP="$(mktemp)"
cp "$MAKEFILE" "$BACKUP"
restore_makefile() {
  cp "$BACKUP" "$MAKEFILE"
  rm -f "$BACKUP"
}
trap restore_makefile EXIT

set_macro() {
  local macro="$1"
  local value="$2"
  if rg -q "^CFLAGS \\+= -D${macro}=" "$MAKEFILE"; then
    sed -i "s|^CFLAGS += -D${macro}=.*$|CFLAGS += -D${macro}=${value}|g" "$MAKEFILE"
  else
    printf 'CFLAGS += -D%s=%s\n' "$macro" "$value" >> "$MAKEFILE"
  fi
}

set_macro "TA_TRUST_ATT_REENTRY_EXTRA_MARGIN" "$ATT_MARGIN"

IFS=',' read -r -a HOLD_LIST <<< "$HOLDS"
for hold in "${HOLD_LIST[@]}"; do
  hold="${hold//[[:space:]]/}"
  if [[ -z "$hold" ]]; then
    continue
  fi

  OUT_DIR="${RESULTS_ROOT}/hold_${hold}"
  echo "[RUN] TA_TRUST_ATT_REENTRY_HOLD_SECONDS=${hold} -> ${OUT_DIR}"
  set_macro "TA_TRUST_ATT_REENTRY_HOLD_SECONDS" "$hold"

  bash "$RUNNER" \
    --protocols "$PROTOCOLS" \
    --densities "$DENSITIES" \
    --topology-seeds "$TOPOLOGY_SEEDS" \
    --run-seeds "$RUN_SEEDS" \
    --attack-profile "$ATTACK_PROFILE" \
    --jobs "$JOBS" \
    --results-dir "$OUT_DIR" \
    --rerun
done

echo "[OK] quick sweep done: ${RESULTS_ROOT}"
