#!/usr/bin/env bash
# run_sweep.sh
# Headless Cooja sweep: 4 protocols × 30 seeds (queue-based worker pool)
#
# Usage:
#   ./scripts/run_sweep.sh [--protocols RPL,BRPL,SMTRUST,TABRPL] [--seeds 1-30] [--jobs 8] [--rerun]
#
# Strategy:
#   Maintain a shared job queue and let a fixed-size worker pool pull jobs
#   one at a time. Each worker uses its own Gradle home and temp workspace to
#   avoid lock-file collisions during parallel Cooja runs.
#   A monitor loop prints queue progress, and worker failures surface the
#   latest log lines immediately.
#
# Output:
#   results/<PROTOCOL>/<seed>/sim.log  — CSV lines from COOJA.testlog
#   results/<PROTOCOL>/<seed>/done     — sentinel file on completion

set -euo pipefail

# ------------------------------------------------------------------ #
# Defaults
# ------------------------------------------------------------------ #
PROTOCOLS="RPL BRPL SMTRUST TABRPL"
SEED_START=1
SEED_END=30
PARALLEL_JOBS=8
FORCE_RERUN=0
MONITOR_INTERVAL=15
ERROR_TAIL_LINES=40
COOJA_GRADLEW="/home/dev/contiki-ng/tools/cooja/gradlew"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCENARIOS_DIR="${ROOT_DIR}/configs/scenarios"
RESULTS_DIR="${ROOT_DIR}/results"
WORKER_ROOT="${ROOT_DIR}/.parallel_worker_env"
DEFAULT_GRADLE_HOME="${HOME}/.gradle"
FALLBACK_GRADLE_BIN="$(find "${DEFAULT_GRADLE_HOME}/wrapper/dists" -path '*/bin/gradle' -type f 2>/dev/null | head -n 1)"

# ------------------------------------------------------------------ #
# Argument parsing
# ------------------------------------------------------------------ #
while [[ $# -gt 0 ]]; do
  case "$1" in
    --protocols)  PROTOCOLS="${2//,/ }"; shift 2;;
    --seeds)
      SEED_START="${2%-*}"
      SEED_END="${2#*-}"
      shift 2
      ;;
    --rerun|--force-rerun) FORCE_RERUN=1; shift;;
    --jobs)       PARALLEL_JOBS="$2"; shift 2;;
    --monitor-interval) MONITOR_INTERVAL="$2"; shift 2;;
    *) echo "Unknown option: $1" >&2; exit 1;;
  esac
done

mkdir -p "$RESULTS_DIR"
mkdir -p "$WORKER_ROOT"

# ------------------------------------------------------------------ #
# Validate
# ------------------------------------------------------------------ #
if [[ ! -x "$COOJA_GRADLEW" ]]; then
  echo "ERROR: Cooja gradlew not found at $COOJA_GRADLEW" >&2; exit 1
fi
for PROTO in $PROTOCOLS; do
  if [[ ! -f "$SCENARIOS_DIR/GRID6x6_${PROTO}.csc" ]]; then
    echo "ERROR: scenario not found: GRID6x6_${PROTO}.csc" >&2; exit 1
  fi
done

# ------------------------------------------------------------------ #
# Worker: run one simulation
# Uses the original .csc (with full build commands) but patches randomseed.
# ------------------------------------------------------------------ #
run_one() {
  local PROTO="$1"
  local SEED="$2"
  local WORKER_ID="$3"
  local OUT_DIR="$RESULTS_DIR/${PROTO}/${SEED}"
  local LOG="$OUT_DIR/sim.log"
  local DONE="$OUT_DIR/done"
  local WORKER_DIR="$WORKER_ROOT/worker${WORKER_ID}"
  local GRADLE_HOME="$WORKER_DIR/gradle-home"
  local TMP_ROOT="$WORKER_DIR/tmp"
  local WS_ROOT="$WORKER_DIR/workspace"
  local WS_SCENARIOS="$WS_ROOT/configs/scenarios"
  local WORKER_LOG="$LOG_DIR/${PROTO}_${SEED}_w${WORKER_ID}.log"
  local GRADLE_CMD="$COOJA_GRADLEW"
  local JAVA_NET_OPTS="-Djava.net.preferIPv4Stack=true -Djava.net.preferIPv6Addresses=false"

  if [[ -f "$DONE" ]]; then
    mark_status done "$PROTO" "$SEED" "$WORKER_ID"
    echo "[W${WORKER_ID}] [SKIP] ${PROTO} seed=${SEED}"
    return 0
  fi
  mkdir -p "$OUT_DIR"
  mkdir -p "$GRADLE_HOME" "$TMP_ROOT"
  bootstrap_gradle_home "$GRADLE_HOME"
  prepare_worker_workspace "$WORKER_DIR"
  rm -f "$WORKER_LOG"

  if [[ -n "${FALLBACK_GRADLE_BIN:-}" && -x "${FALLBACK_GRADLE_BIN:-}" ]]; then
    GRADLE_CMD="$FALLBACK_GRADLE_BIN"
  fi

  # Patch randomseed into a temp copy of the CSC
  local TMP_CSC TMP_LOGDIR
  TMP_CSC=$(mktemp    "${WS_SCENARIOS}/tmp_${PROTO}_${SEED}_XXXXXX.csc")
  TMP_LOGDIR=$(mktemp -d "${TMP_ROOT}/tmp_log_${PROTO}_${SEED}_XXXXXX")

  python3 -c "
import re, sys
src = '${WS_SCENARIOS}/GRID6x6_${PROTO}.csc'
with open(src) as f:
    txt = f.read()
txt = re.sub(r'<randomseed>[^<]*</randomseed>',
             '<randomseed>${SEED}</randomseed>', txt)
with open('${TMP_CSC}', 'w') as f:
    f.write(txt)
"

  mark_status running "$PROTO" "$SEED" "$WORKER_ID"
  echo "[W${WORKER_ID}] [RUN ] ${PROTO} seed=${SEED}"

  if JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} ${JAVA_NET_OPTS}" \
      GRADLE_OPTS="${GRADLE_OPTS:-} ${JAVA_NET_OPTS}" \
      GRADLE_USER_HOME="$GRADLE_HOME" "$GRADLE_CMD" \
      --no-daemon --no-watch-fs --parallel --build-cache \
      -p "$(dirname "$COOJA_GRADLEW")" \
      run --args="--no-gui --autostart --logdir=${TMP_LOGDIR} ${TMP_CSC}" \
      > "$WORKER_LOG" 2>&1; then
    :
  else
    echo "[W${WORKER_ID}] [WARN] Cooja exited non-zero for ${PROTO} seed=${SEED}" >&2
  fi

  if [[ -f "${TMP_LOGDIR}/COOJA.testlog" ]]; then
    grep -E "^[0-9]+:(CSV,|ROUTING_READY|SIMULATION_DONE)" \
      "${TMP_LOGDIR}/COOJA.testlog" > "$LOG" || true
  fi

  rm -f "$TMP_CSC"
  rm -rf "$TMP_LOGDIR"

  if [[ -s "$LOG" ]]; then
    mark_status done "$PROTO" "$SEED" "$WORKER_ID"
    touch "$DONE"
    echo "[W${WORKER_ID}] [DONE] ${PROTO} seed=${SEED}"
  else
    mark_status failed "$PROTO" "$SEED" "$WORKER_ID"
    rm -f "$LOG"
    echo "[W${WORKER_ID}] [FAIL] ${PROTO} seed=${SEED} (missing or empty sim.log)" >&2
    print_log_tail "$WORKER_LOG" "$WORKER_ID"
    return 1
  fi
}

export -f run_one
export ROOT_DIR SCENARIOS_DIR RESULTS_DIR COOJA_GRADLEW WORKER_ROOT DEFAULT_GRADLE_HOME FALLBACK_GRADLE_BIN

QUEUE_FILE=""
QUEUE_LOCK=""
STATUS_DIR=""
LOG_DIR=""
TOTAL=0
print_log_tail() {
  local FILE="$1"
  local WORKER_ID="$2"

  if [[ -f "$FILE" ]]; then
    echo "[W${WORKER_ID}] [ERROR] log tail: $FILE" >&2
    tail -n "$ERROR_TAIL_LINES" "$FILE" >&2 || true
  fi
}

bootstrap_gradle_home() {
  local TARGET_HOME="$1"
  local SRC_DISTS="${DEFAULT_GRADLE_HOME}/wrapper/dists"
  local DST_DISTS="${TARGET_HOME}/wrapper/dists"

  if [[ -d "$DST_DISTS" ]]; then
    return 0
  fi
  if [[ ! -d "$SRC_DISTS" ]]; then
    return 0
  fi

  mkdir -p "${TARGET_HOME}/wrapper"
  cp -a "$SRC_DISTS" "${TARGET_HOME}/wrapper/" 2>/dev/null || true
}

prepare_worker_workspace() {
  local WORKER_DIR="$1"
  local WS_ROOT="${WORKER_DIR}/workspace"
  local WS_SCENARIOS="${WS_ROOT}/configs/scenarios"

  mkdir -p "$WS_SCENARIOS"
  mkdir -p "${WS_ROOT}/configs"
  rm -rf "${WS_ROOT}/motes"
  cp -a "${ROOT_DIR}/motes" "${WS_ROOT}/"
  cp -a "${ROOT_DIR}/project-conf.h" "${WS_ROOT}/project-conf.h"
  cp -a "${SCENARIOS_DIR}"/GRID6x6_*.csc "${WS_SCENARIOS}/"
  ln -sfn "${ROOT_DIR}/contiki-ng-brpl" "${WS_ROOT}/contiki-ng-brpl"
}

mark_status() {
  local KIND="$1"
  local PROTO="$2"
  local SEED="$3"
  local WORKER_ID="$4"
  local STEM="${PROTO}_${SEED}_w${WORKER_ID}"

  rm -f "$STATUS_DIR"/queued/"${PROTO}_${SEED}" \
        "$STATUS_DIR"/running/"${STEM}" \
        "$STATUS_DIR"/failed/"${STEM}" \
        "$STATUS_DIR"/done/"${STEM}"

  case "$KIND" in
    queued)
      : > "$STATUS_DIR/queued/${PROTO}_${SEED}"
      ;;
    running)
      : > "$STATUS_DIR/running/${STEM}"
      ;;
    failed)
      : > "$STATUS_DIR/failed/${STEM}"
      ;;
    done)
      : > "$STATUS_DIR/done/${STEM}"
      ;;
  esac
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

monitor_loop() {
  while true; do
    local RUNNING_COUNT DONE_COUNT FAIL_COUNT QUEUE_LEFT
    RUNNING_COUNT=$(find "$STATUS_DIR/running" -type f | wc -l)
    DONE_COUNT=$(find "$STATUS_DIR/done" -type f | wc -l)
    FAIL_COUNT=$(find "$STATUS_DIR/failed" -type f | wc -l)
    QUEUE_LEFT=$(wc -l < "$QUEUE_FILE")

    printf '[MON] total=%s done=%s running=%s failed=%s queued=%s\n' \
      "$TOTAL" "$DONE_COUNT" "$RUNNING_COUNT" "$FAIL_COUNT" "$QUEUE_LEFT"

    if [[ "$DONE_COUNT" -ge "$TOTAL" ]] || \
       [[ $((DONE_COUNT + FAIL_COUNT)) -ge "$TOTAL" && "$RUNNING_COUNT" -eq 0 && "$QUEUE_LEFT" -eq 0 ]]; then
      break
    fi

    sleep "$MONITOR_INTERVAL"
  done
}

worker_loop() {
  local WORKER_ID="$1"
  local JOB=""

  while true; do
    JOB="$(pop_job)"

    if [[ -z "$JOB" ]]; then
      break
    fi

    local PROTO="${JOB%%:*}"
    local SEED="${JOB##*:}"
    if ! run_one "$PROTO" "$SEED" "$WORKER_ID"; then
      continue
    fi
  done
}

export -f print_log_tail
export -f bootstrap_gradle_home
export -f prepare_worker_workspace
export -f mark_status
export -f pop_job
export -f monitor_loop
export -f worker_loop

# ------------------------------------------------------------------ #
# Dispatch simulations
# ------------------------------------------------------------------ #
JOBS=()
for PROTO in $PROTOCOLS; do
  for SEED in $(seq "$SEED_START" "$SEED_END"); do
    JOBS+=("${PROTO}:${SEED}")
  done
done

TOTAL="${#JOBS[@]}"
STATUS_DIR="${WORKER_ROOT}/status"
LOG_DIR="${WORKER_ROOT}/logs"
mkdir -p "$STATUS_DIR/queued" "$STATUS_DIR/running" "$STATUS_DIR/done" "$STATUS_DIR/failed" "$LOG_DIR"
rm -f "$STATUS_DIR"/queued/* "$STATUS_DIR"/running/* "$STATUS_DIR"/done/* "$STATUS_DIR"/failed/* 2>/dev/null || true

if [[ "$FORCE_RERUN" -eq 1 ]]; then
  echo "=== Removing existing results for selected jobs ==="
  for JOB in "${JOBS[@]}"; do
    PROTO="${JOB%%:*}"
    SEED="${JOB##*:}"
    rm -rf "$RESULTS_DIR/${PROTO}/${SEED}"
  done
  rm -f "$RESULTS_DIR"/pdr_summary.csv \
        "$RESULTS_DIR"/delay_summary.csv \
        "$RESULTS_DIR"/trust_trace.csv \
        "$RESULTS_DIR"/parent_churn.csv
fi

QUEUE_FILE=$(mktemp "${WORKER_ROOT}/queue_XXXXXX.txt")
QUEUE_LOCK="${QUEUE_FILE}.lock"
touch "$QUEUE_LOCK"
printf '%s\n' "${JOBS[@]}" > "$QUEUE_FILE"
for JOB in "${JOBS[@]}"; do
  PROTO="${JOB%%:*}"
  SEED="${JOB##*:}"
  mark_status queued "$PROTO" "$SEED" "0"
done

cleanup_queue() {
  rm -f "$QUEUE_FILE" "$QUEUE_LOCK"
}
trap cleanup_queue EXIT
export QUEUE_FILE QUEUE_LOCK STATUS_DIR LOG_DIR TOTAL MONITOR_INTERVAL ERROR_TAIL_LINES FORCE_RERUN

echo "=== Running ${TOTAL} simulations (${PARALLEL_JOBS} workers, queued) ==="
echo "    Protocols : $PROTOCOLS"
echo "    Seeds     : ${SEED_START}–${SEED_END}"
echo "    Queue     : $QUEUE_FILE"
echo "    Logs      : $LOG_DIR"
if [[ "$FORCE_RERUN" -eq 1 ]]; then
  echo "    Mode      : rerun from scratch"
fi
echo ""

PIDS=()
MONITOR_PID=""
bash -c "monitor_loop" &
MONITOR_PID="$!"
for WORKER_ID in $(seq 1 "$PARALLEL_JOBS"); do
  bash -c "worker_loop $WORKER_ID" &
  PIDS+=("$!")
done

STATUS=0
for PID in "${PIDS[@]}"; do
  if ! wait "$PID"; then
    STATUS=1
  fi
done

if [[ -n "$MONITOR_PID" ]]; then
  wait "$MONITOR_PID" || true
fi

FAIL_COUNT=$(find "$STATUS_DIR/failed" -type f | wc -l)
DONE_COUNT=$(find "$STATUS_DIR/done" -type f | wc -l)
if [[ "$FAIL_COUNT" -gt 0 ]]; then
  STATUS=1
fi

echo ""
if [[ "$STATUS" -eq 0 ]]; then
  echo "=== Sweep complete ==="
else
  echo "=== Sweep complete with failures ==="
fi
echo "Completed: $DONE_COUNT / $TOTAL"
echo "Failed   : $FAIL_COUNT / $TOTAL"
echo "Results in: $RESULTS_DIR"
exit "$STATUS"
