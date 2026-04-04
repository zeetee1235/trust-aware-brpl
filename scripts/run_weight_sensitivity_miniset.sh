#!/usr/bin/env bash
# Local weight-sensitivity sweep on the 9-pair random-topology miniset.
# Purpose: post-hoc robustness check around the current operating point.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COOJA_GRADLEW="/home/dev/contiki-ng/tools/cooja/gradlew"
RESULTS_DIR="${ROOT_DIR}/results/weight_sensitivity_miniset"
TMP_SCEN_DIR="${RESULTS_DIR}/_tmp_scenarios"
TMP_LOG_ROOT="${RESULTS_DIR}/_tmp_logs"
GRADLE_USER_HOME_DIR="/tmp/ta-brpl-gradle-home"
DEFAULT_GRADLE_HOME="${HOME}/.gradle"
JAVA_NET_OPTS="-Djava.net.preferIPv4Stack=true -Djava.net.preferIPv6Addresses=false"

mkdir -p "$RESULTS_DIR" "$TMP_SCEN_DIR" "$TMP_LOG_ROOT" "$GRADLE_USER_HOME_DIR"

if [[ ! -x "$COOJA_GRADLEW" ]]; then
  echo "ERROR: Cooja gradlew not found at $COOJA_GRADLEW" >&2
  exit 1
fi

# Coarse local grid around the current (5,3,2) operating point.
WEIGHTS=(
  "4,2,4"
  "4,3,3"
  "4,4,2"
  "5,2,3"
  "5,3,2"
  "5,4,1"
  "6,1,3"
  "6,2,2"
  "6,3,1"
  "7,2,1"
)

if [[ -n "${WEIGHTS_OVERRIDE:-}" ]]; then
  IFS=';' read -r -a WEIGHTS <<< "${WEIGHTS_OVERRIDE}"
fi

DENSITIES=(sparse medium dense)
TOPOS=(001 002 003)
RUN_SEED=1

makefile_for_weight() {
  local WF="$1" WC="$2" WH="$3"
  local NAME="Makefile.tabrpl_w${WF}${WC}${WH}_heat"
  local PATH_OUT="${ROOT_DIR}/motes/${NAME}"
  if [[ ! -f "$PATH_OUT" ]]; then
    cat > "$PATH_OUT" <<EOF
include Makefile.tabrpl
CFLAGS += -DTA_TRUST_W_FWD=${WF}
CFLAGS += -DTA_TRUST_W_CTRL=${WC}
CFLAGS += -DTA_TRUST_W_HON=${WH}
EOF
  fi
  printf '%s\n' "$NAME"
}

run_one() {
  local WF="$1" WC="$2" WH="$3" DENSITY="$4" TOPO="$5"
  local SCEN="${ROOT_DIR}/configs/scenarios/random_topo/${DENSITY}/topo_${TOPO}/RT_TABRPL_${DENSITY}_topo_${TOPO}.csc"
  local TAG="w${WF}${WC}${WH}"
  local OUT_DIR="${RESULTS_DIR}/${TAG}/${DENSITY}/topo_${TOPO}/TABRPL/${RUN_SEED}"
  local LOG="${OUT_DIR}/sim.log"
  local DONE="${OUT_DIR}/done"
  local MAKEFILE
  MAKEFILE="$(makefile_for_weight "$WF" "$WC" "$WH")"

  mkdir -p "$OUT_DIR"
  if [[ -f "$DONE" && -s "$LOG" ]]; then
    echo "[SKIP] ${TAG} ${DENSITY} topo_${TOPO}"
    return 0
  fi

  local TMP_SCEN
  TMP_SCEN="$(dirname "$SCEN")/RT_TABRPL_${DENSITY}_topo_${TOPO}_${TAG}.csc"
  local TMP_LOGDIR="${TMP_LOG_ROOT}/${TAG}_${DENSITY}_${TOPO}"
  rm -rf "$TMP_LOGDIR"
  mkdir -p "$TMP_LOGDIR"

  sed "s/Makefile\\.tabrpl/${MAKEFILE}/g" "$SCEN" > "$TMP_SCEN"

  echo "[RUN ] ${TAG} ${DENSITY} topo_${TOPO}"
  if JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} ${JAVA_NET_OPTS}" \
      JAVA_OPTS="${JAVA_OPTS:-} ${JAVA_NET_OPTS}" \
      GRADLE_OPTS="${GRADLE_OPTS:-} ${JAVA_NET_OPTS}" \
      GRADLE_USER_HOME="${GRADLE_USER_HOME_DIR}" "$COOJA_GRADLEW" \
      --no-daemon --no-watch-fs \
      -p "$(dirname "$COOJA_GRADLEW")" \
      run --args="--no-gui --autostart --logdir=${TMP_LOGDIR} ${TMP_SCEN}" \
      > "${OUT_DIR}/worker.log" 2>&1; then
    :
  else
    echo "[WARN] Cooja exited non-zero for ${TAG} ${DENSITY} topo_${TOPO}" >&2
  fi

  if [[ -f "${TMP_LOGDIR}/COOJA.testlog" ]]; then
    grep -E "^[0-9]+:(CSV,|ROUTING_READY|SIMULATION_DONE)" \
      "${TMP_LOGDIR}/COOJA.testlog" > "$LOG" || true
  fi

  if [[ -s "$LOG" ]]; then
    touch "$DONE"
    echo "[DONE] ${TAG} ${DENSITY} topo_${TOPO}"
  else
    echo "[FAIL] ${TAG} ${DENSITY} topo_${TOPO}" >&2
    tail -n 40 "${OUT_DIR}/worker.log" >&2 || true
    return 1
  fi
}

bootstrap_gradle_home() {
  local SRC_DISTS="${DEFAULT_GRADLE_HOME}/wrapper/dists"
  local DST_DISTS="${GRADLE_USER_HOME_DIR}/wrapper/dists"
  if [[ -d "$DST_DISTS" ]]; then return 0; fi
  if [[ ! -d "$SRC_DISTS" ]]; then return 0; fi
  mkdir -p "${GRADLE_USER_HOME_DIR}/wrapper"
  cp -a "$SRC_DISTS" "${GRADLE_USER_HOME_DIR}/wrapper/" 2>/dev/null || true
}

main() {
  bootstrap_gradle_home
  for spec in "${WEIGHTS[@]}"; do
    IFS=',' read -r WF WC WH <<< "$spec"
    for density in "${DENSITIES[@]}"; do
      for topo in "${TOPOS[@]}"; do
        run_one "$WF" "$WC" "$WH" "$density" "$topo"
      done
    done
  done
}

main "$@"
