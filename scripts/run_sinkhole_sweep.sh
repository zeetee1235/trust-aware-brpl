#!/usr/bin/env bash
# run_sinkhole_sweep.sh
# new.md experiment matrix:
#   Topology  x Protocol  x Scenario   x Seeds
#   Grid,Bottle x BRPL,TABRPL x SinkOnly,SinkDrop50 x 1-5
# Total: 2 x 2 x 2 x 5 = 40 runs

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCENARIOS_DIR="${ROOT_DIR}/configs/scenarios"
RESULTS_DIR="${ROOT_DIR}/results/sinkhole_sweep"
COOJA_GRADLEW="/home/dev/contiki-ng/tools/cooja/gradlew"
WORKER_BASE_ROOT="${ROOT_DIR}/.parallel_worker_env_sink"
DEFAULT_GRADLE_HOME="${HOME}/.gradle"

PARALLEL_JOBS=8
FORCE_RERUN=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --jobs)       PARALLEL_JOBS="$2"; shift 2 ;;
    --rerun)      FORCE_RERUN=1; shift ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --results-dir) RESULTS_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

mkdir -p "$RESULTS_DIR" "$WORKER_BASE_ROOT"

if [[ ! -x "$COOJA_GRADLEW" ]]; then
  echo "ERROR: Cooja gradlew not found at $COOJA_GRADLEW" >&2
  exit 1
fi

# Scenario list: <label>|<csc_path_relative_to_ROOT>
SCENARIOS=(
  "GRID_BRPL_SINK_ONLY|configs/scenarios/GRID6x6_BRPL_SINK_ONLY.csc"
  "GRID_TABRPL_SINK_ONLY|configs/scenarios/GRID6x6_TABRPL_SINK_ONLY.csc"
  "GRID_BRPL_SINK_DROP50|configs/scenarios/GRID6x6_BRPL_SINK_DROP50.csc"
  "GRID_TABRPL_SINK_DROP50|configs/scenarios/GRID6x6_TABRPL_SINK_DROP50.csc"
  "BOTTLE_BRPL_SINK_ONLY|configs/scenarios/BOTTLE_BRPL_SINK_ONLY.csc"
  "BOTTLE_TABRPL_SINK_ONLY|configs/scenarios/BOTTLE_TABRPL_SINK_ONLY.csc"
  "BOTTLE_BRPL_SINK_DROP50|configs/scenarios/BOTTLE_BRPL_SINK_DROP50.csc"
  "BOTTLE_TABRPL_SINK_DROP50|configs/scenarios/BOTTLE_TABRPL_SINK_DROP50.csc"
)
RUN_SEEDS=(1 2 3 4 5)

# Build job queue: label|seed|csc_rel
JOBS=()
for SCEN in "${SCENARIOS[@]}"; do
  IFS='|' read -r LABEL CSC_REL <<< "$SCEN"
  for SEED in "${RUN_SEEDS[@]}"; do
    JOBS+=("${LABEL}|${SEED}|${CSC_REL}")
  done
done
TOTAL="${#JOBS[@]}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "=== DRY RUN ==="
  echo "Total jobs: $TOTAL"
  for J in "${JOBS[@]}"; do echo "  $J"; done
  exit 0
fi

# Force rerun: remove existing results
if [[ "$FORCE_RERUN" -eq 1 ]]; then
  echo "=== Removing existing sinkhole sweep results ==="
  rm -rf "$RESULTS_DIR"
  mkdir -p "$RESULTS_DIR"
fi

RUN_ROOT="$(mktemp -d "${WORKER_BASE_ROOT}/run_XXXXXX")"
STATUS_DIR="${RUN_ROOT}/status"
LOG_DIR="${RUN_ROOT}/logs"
QUEUE_FILE="${RUN_ROOT}/queue.txt"
QUEUE_LOCK="${QUEUE_FILE}.lock"

mkdir -p "$STATUS_DIR/queued" "$STATUS_DIR/running" "$STATUS_DIR/done" "$STATUS_DIR/failed" "$LOG_DIR"
touch "$QUEUE_LOCK"
printf '%s\n' "${JOBS[@]}" > "$QUEUE_FILE"

for J in "${JOBS[@]}"; do
  IFS='|' read -r LABEL SEED _ <<< "$J"
  : > "$STATUS_DIR/queued/${LABEL}_s${SEED}"
done

bootstrap_gradle_home() {
  local TARGET_HOME="$1"
  local SRC_DISTS="${DEFAULT_GRADLE_HOME}/wrapper/dists"
  local DST_DISTS="${TARGET_HOME}/wrapper/dists"
  if [[ -d "$DST_DISTS" ]]; then return 0; fi
  if [[ ! -d "$SRC_DISTS" ]]; then return 0; fi
  mkdir -p "${TARGET_HOME}/wrapper"
  cp -a "$SRC_DISTS" "${TARGET_HOME}/wrapper/" 2>/dev/null || true
}

prepare_worker_workspace() {
  local WORKER_DIR="$1"
  local WS_ROOT="${WORKER_DIR}/workspace"
  mkdir -p "${WS_ROOT}/configs/scenarios"
  rm -rf "${WS_ROOT}/motes"
  cp -a "${ROOT_DIR}/motes" "${WS_ROOT}/"
  cp -a "${ROOT_DIR}/project-conf.h" "${WS_ROOT}/project-conf.h"
  # Copy only the 8 sinkhole scenario CSC files
  for CSC in "${ROOT_DIR}"/configs/scenarios/{GRID6x6,BOTTLE}*SINK*.csc; do
    cp "$CSC" "${WS_ROOT}/configs/scenarios/" 2>/dev/null || true
  done
  ln -sfn "${ROOT_DIR}/contiki-ng-brpl" "${WS_ROOT}/contiki-ng-brpl"
}

pop_job() {
  local JOB=""
  exec 9<>"$QUEUE_LOCK"
  flock -x 9
  if [[ -s "$QUEUE_FILE" ]]; then
    JOB=$(sed -n '1p' "$QUEUE_FILE")
    sed -i '1d' "$QUEUE_FILE"
  fi
  flock -u 9
  exec 9>&-
  printf '%s\n' "$JOB"
}

run_one() {
  local LABEL="$1" SEED="$2" CSC_REL="$3" WORKER_ID="$4"
  local OUT_DIR="${RESULTS_DIR}/${LABEL}/seed${SEED}"
  local LOG="${OUT_DIR}/sim.log"
  local DONE="${OUT_DIR}/done"

  if [[ -f "$DONE" ]]; then
    echo "[W${WORKER_ID}] [SKIP] ${LABEL} seed=${SEED}"
    return 0
  fi

  local WORKER_DIR="${RUN_ROOT}/worker${WORKER_ID}"
  local GRADLE_HOME="${WORKER_DIR}/gradle-home"
  local TMP_ROOT="${WORKER_DIR}/tmp"
  local WS_ROOT="${WORKER_DIR}/workspace"
  local WORKER_LOG="${LOG_DIR}/${LABEL}_s${SEED}_w${WORKER_ID}.log"
  local JAVA_NET_OPTS="-Djava.net.preferIPv4Stack=true -Djava.net.preferIPv6Addresses=false"

  local SCEN_ABS="${WS_ROOT}/${CSC_REL}"

  mkdir -p "$OUT_DIR" "$GRADLE_HOME" "$TMP_ROOT"
  bootstrap_gradle_home "$GRADLE_HOME"
  prepare_worker_workspace "$WORKER_DIR"
  rm -f "$WORKER_LOG"

  if [[ ! -f "$SCEN_ABS" ]]; then
    echo "[W${WORKER_ID}] [FAIL] missing scenario: $SCEN_ABS" >&2
    return 1
  fi

  # Patch randomseed
  local TMP_CSC TMP_LOGDIR
  TMP_CSC=$(mktemp "$(dirname "$SCEN_ABS")/tmp_${LABEL}_s${SEED}_XXXXXX.csc")
  TMP_LOGDIR=$(mktemp -d "${TMP_ROOT}/tmp_log_${LABEL}_s${SEED}_XXXXXX")

  python3 - <<PY
import re
with open(r"${SCEN_ABS}", 'r', encoding='utf-8') as f:
    txt = f.read()
txt = re.sub(r'<randomseed>[^<]*</randomseed>', '<randomseed>${SEED}</randomseed>', txt)
with open(r"${TMP_CSC}", 'w', encoding='utf-8') as f:
    f.write(txt)
PY

  echo "[W${WORKER_ID}] [RUN ] ${LABEL} seed=${SEED}"

  if JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} ${JAVA_NET_OPTS}" \
      JAVA_OPTS="${JAVA_OPTS:-} ${JAVA_NET_OPTS}" \
      GRADLE_OPTS="${GRADLE_OPTS:-} ${JAVA_NET_OPTS}" \
      GRADLE_USER_HOME="$GRADLE_HOME" "$COOJA_GRADLEW" \
      --no-daemon --no-watch-fs --parallel --build-cache \
      -p "$(dirname "$COOJA_GRADLEW")" \
      run --args="--no-gui --autostart --logdir=${TMP_LOGDIR} ${TMP_CSC}" \
      > "$WORKER_LOG" 2>&1; then
    :
  else
    echo "[W${WORKER_ID}] [WARN] Cooja exited non-zero for ${LABEL} seed=${SEED}" >&2
  fi

  if [[ -f "${TMP_LOGDIR}/COOJA.testlog" ]]; then
    grep -E "^[0-9]+:(CSV,|ROUTING_READY|SIMULATION_DONE)" \
      "${TMP_LOGDIR}/COOJA.testlog" > "$LOG" || true
  fi

  rm -f "$TMP_CSC"
  rm -rf "$TMP_LOGDIR"

  if [[ -s "$LOG" ]]; then
    touch "$DONE"
    echo "[W${WORKER_ID}] [DONE] ${LABEL} seed=${SEED}"
  else
    rm -f "$LOG"
    echo "[W${WORKER_ID}] [FAIL] ${LABEL} seed=${SEED}" >&2
    if [[ -f "$WORKER_LOG" ]]; then tail -20 "$WORKER_LOG" >&2 || true; fi
    return 1
  fi
}

worker_loop() {
  local WORKER_ID="$1" JOB=""
  while true; do
    JOB="$(pop_job)"
    if [[ -z "$JOB" ]]; then break; fi
    IFS='|' read -r LABEL SEED CSC_REL <<< "$JOB"
    run_one "$LABEL" "$SEED" "$CSC_REL" "$WORKER_ID" || true
  done
}

monitor_loop() {
  while true; do
    local DONE_COUNT FAIL_COUNT
    DONE_COUNT=$(find "$STATUS_DIR/done" -type f 2>/dev/null | wc -l || echo 0)
    FAIL_COUNT=$(find "$STATUS_DIR/failed" -type f 2>/dev/null | wc -l || echo 0)
    QUEUE_LEFT=$(wc -l < "$QUEUE_FILE" 2>/dev/null || echo 0)
    DONE_FILES=$(find "$RESULTS_DIR" -name "done" 2>/dev/null | wc -l || echo 0)
    printf '[MON] total=%s done=%s failed=%s queued=%s result_done=%s\n' \
      "$TOTAL" "$DONE_COUNT" "$FAIL_COUNT" "$QUEUE_LEFT" "$DONE_FILES"
    if [[ "$QUEUE_LEFT" -eq 0 ]]; then
      sleep 5
      break
    fi
    sleep 20
  done
}

export -f bootstrap_gradle_home prepare_worker_workspace pop_job run_one worker_loop
export ROOT_DIR SCENARIOS_DIR RESULTS_DIR COOJA_GRADLEW RUN_ROOT DEFAULT_GRADLE_HOME
export QUEUE_FILE QUEUE_LOCK STATUS_DIR LOG_DIR TOTAL

cleanup_queue() { rm -f "$QUEUE_FILE" "$QUEUE_LOCK"; }
trap cleanup_queue EXIT

echo "=== Sinkhole sweep ==="
echo "Total jobs: $TOTAL  (Workers: $PARALLEL_JOBS)"
echo "Results   : $RESULTS_DIR"
echo "Run root  : $RUN_ROOT"

declare -a PIDS
bash -c "monitor_loop" &
MON_PID=$!

for WID in $(seq 1 "$PARALLEL_JOBS"); do
  bash -c "worker_loop $WID" &
  PIDS+=("$!")
done

STATUS=0
for PID in "${PIDS[@]}"; do wait "$PID" || STATUS=1; done
wait "$MON_PID" || true

DONE_FILES=$(find "$RESULTS_DIR" -name "done" | wc -l)
echo ""
echo "=== Sinkhole sweep complete ==="
echo "Completed: $DONE_FILES / $TOTAL"
[[ "$STATUS" -ne 0 ]] && echo "Some runs failed — check $LOG_DIR"

if [[ "$STATUS" -eq 0 ]]; then rm -rf "$RUN_ROOT"; fi
exit "$STATUS"
