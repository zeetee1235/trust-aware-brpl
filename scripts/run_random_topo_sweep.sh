#!/usr/bin/env bash
# run_random_topo_sweep.sh
# Controlled-random topology sweep (density x topology-seed x run-seed x protocol)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCENARIOS_DIR="${ROOT_DIR}/configs/scenarios"
RANDOM_DIR="${SCENARIOS_DIR}/random_topo"
MANIFEST="${RANDOM_DIR}/manifest.json"
RESULTS_DIR="${ROOT_DIR}/results/random_topo"
COOJA_GRADLEW="/home/dev/contiki-ng/tools/cooja/gradlew"
WORKER_BASE_ROOT="${ROOT_DIR}/.parallel_worker_env_random"
DEFAULT_GRADLE_HOME="${HOME}/.gradle"

PROTOCOLS="RPL BRPL SMTRUST TABRPL"
DENSITIES="sparse,medium,dense"
TOPOLOGY_SEEDS="1-80"
RUN_SEEDS="1-5"
PARALLEL_JOBS=12
FORCE_RERUN=0
MONITOR_INTERVAL=20
ERROR_TAIL_LINES=40
DRY_RUN=0
KEEP_RUN_ROOT=0

RUN_ROOT=""
QUEUE_FILE=""
QUEUE_LOCK=""
STATUS_DIR=""
LOG_DIR=""
TOTAL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --protocols) PROTOCOLS="${2//,/ }"; shift 2 ;;
    --densities) DENSITIES="$2"; shift 2 ;;
    --topology-seeds) TOPOLOGY_SEEDS="$2"; shift 2 ;;
    --run-seeds) RUN_SEEDS="$2"; shift 2 ;;
    --jobs) PARALLEL_JOBS="$2"; shift 2 ;;
    --rerun|--force-rerun) FORCE_RERUN=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --keep-run-root) KEEP_RUN_ROOT=1; shift ;;
    --results-dir) RESULTS_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

mkdir -p "$RESULTS_DIR" "$WORKER_BASE_ROOT"

if [[ ! -x "$COOJA_GRADLEW" ]]; then
  echo "ERROR: Cooja gradlew not found at $COOJA_GRADLEW" >&2
  exit 1
fi

# 1) Generate random topology scenarios + manifest first
"${ROOT_DIR}/scripts/generate_random_topologies.py" \
  --protocols "$(echo "$PROTOCOLS" | tr ' ' ',')" \
  --densities "$DENSITIES" \
  --topology-seeds "$TOPOLOGY_SEEDS" \
  --out-dir "$RANDOM_DIR" \
  --manifest "$MANIFEST"

if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: manifest not found after generation: $MANIFEST" >&2
  exit 1
fi

mark_status() {
  local KIND="$1" PROTO="$2" DENSITY="$3" TOPO="$4" RUN_SEED="$5" WORKER_ID="$6"
  local STEM="${PROTO}_${DENSITY}_${TOPO}_${RUN_SEED}_w${WORKER_ID}"
  local KEY="${PROTO}_${DENSITY}_${TOPO}_${RUN_SEED}"

  rm -f "$STATUS_DIR"/queued/"$KEY" \
        "$STATUS_DIR"/running/"$STEM" \
        "$STATUS_DIR"/failed/"$STEM" \
        "$STATUS_DIR"/done/"$STEM"

  case "$KIND" in
    queued) : > "$STATUS_DIR/queued/$KEY" ;;
    running) : > "$STATUS_DIR/running/$STEM" ;;
    failed) : > "$STATUS_DIR/failed/$STEM" ;;
    done) : > "$STATUS_DIR/done/$STEM" ;;
  esac
}

print_log_tail() {
  local FILE="$1" WORKER_ID="$2"
  if [[ -f "$FILE" ]]; then
    echo "[W${WORKER_ID}] [ERROR] log tail: $FILE" >&2
    tail -n "$ERROR_TAIL_LINES" "$FILE" >&2 || true
  fi
}

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
  local WS_SCENARIOS="${WS_ROOT}/configs/scenarios"

  mkdir -p "$WS_SCENARIOS"
  mkdir -p "${WS_ROOT}/configs"
  rm -rf "${WS_ROOT}/motes"
  cp -a "${ROOT_DIR}/motes" "${WS_ROOT}/"
  cp -a "${ROOT_DIR}/project-conf.h" "${WS_ROOT}/project-conf.h"
  rm -rf "${WS_SCENARIOS}/random_topo"
  mkdir -p "${WS_SCENARIOS}"
  cp -a "${RANDOM_DIR}" "${WS_SCENARIOS}/"
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
  local PROTO="$1" DENSITY="$2" TOPO="$3" RUN_SEED="$4" SCEN_REL="$5" WORKER_ID="$6"
  local OUT_DIR="${RESULTS_DIR}/${DENSITY}/${TOPO}/${PROTO}/${RUN_SEED}"
  local LOG="${OUT_DIR}/sim.log"
  local DONE="${OUT_DIR}/done"

  local WORKER_DIR="${RUN_ROOT}/worker${WORKER_ID}"
  local GRADLE_HOME="${WORKER_DIR}/gradle-home"
  local TMP_ROOT="${WORKER_DIR}/tmp"
  local WS_ROOT="${WORKER_DIR}/workspace"
  local WORKER_LOG="${LOG_DIR}/${PROTO}_${DENSITY}_${TOPO}_${RUN_SEED}_w${WORKER_ID}.log"
  local JAVA_NET_OPTS="-Djava.net.preferIPv4Stack=true -Djava.net.preferIPv6Addresses=false"

  local SCEN_ABS="${WS_ROOT}/${SCEN_REL}"

  if [[ -f "$DONE" ]]; then
    mark_status done "$PROTO" "$DENSITY" "$TOPO" "$RUN_SEED" "$WORKER_ID"
    echo "[W${WORKER_ID}] [SKIP] ${PROTO} ${DENSITY} ${TOPO} seed=${RUN_SEED}"
    return 0
  fi

  mkdir -p "$OUT_DIR" "$GRADLE_HOME" "$TMP_ROOT"
  bootstrap_gradle_home "$GRADLE_HOME"
  prepare_worker_workspace "$WORKER_DIR"
  rm -f "$WORKER_LOG"

  if [[ ! -f "$SCEN_ABS" ]]; then
    echo "[W${WORKER_ID}] [FAIL] missing scenario: $SCEN_ABS" >&2
    mark_status failed "$PROTO" "$DENSITY" "$TOPO" "$RUN_SEED" "$WORKER_ID"
    return 1
  fi

  local TMP_CSC TMP_LOGDIR
  TMP_CSC=$(mktemp "$(dirname "$SCEN_ABS")/tmp_${PROTO}_${DENSITY}_${TOPO}_${RUN_SEED}_XXXXXX.csc")
  TMP_LOGDIR=$(mktemp -d "${TMP_ROOT}/tmp_log_${PROTO}_${RUN_SEED}_XXXXXX")

  python3 - <<PY
import re
src = r"${SCEN_ABS}"
dst = r"${TMP_CSC}"
with open(src, 'r', encoding='utf-8') as f:
    txt = f.read()
txt = re.sub(r'<randomseed>[^<]*</randomseed>', '<randomseed>${RUN_SEED}</randomseed>', txt)
with open(dst, 'w', encoding='utf-8') as f:
    f.write(txt)
PY

  mark_status running "$PROTO" "$DENSITY" "$TOPO" "$RUN_SEED" "$WORKER_ID"
  echo "[W${WORKER_ID}] [RUN ] ${PROTO} ${DENSITY} ${TOPO} seed=${RUN_SEED}"

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
    echo "[W${WORKER_ID}] [WARN] Cooja exited non-zero for ${PROTO} ${DENSITY} ${TOPO} seed=${RUN_SEED}" >&2
  fi

  if [[ -f "${TMP_LOGDIR}/COOJA.testlog" ]]; then
    grep -E "^[0-9]+:(CSV,|ROUTING_READY|SIMULATION_DONE)" \
      "${TMP_LOGDIR}/COOJA.testlog" > "$LOG" || true
  fi

  rm -f "$TMP_CSC"
  rm -rf "$TMP_LOGDIR"

  if [[ -s "$LOG" ]]; then
    touch "$DONE"
    mark_status done "$PROTO" "$DENSITY" "$TOPO" "$RUN_SEED" "$WORKER_ID"
    echo "[W${WORKER_ID}] [DONE] ${PROTO} ${DENSITY} ${TOPO} seed=${RUN_SEED}"
  else
    rm -f "$LOG"
    mark_status failed "$PROTO" "$DENSITY" "$TOPO" "$RUN_SEED" "$WORKER_ID"
    echo "[W${WORKER_ID}] [FAIL] ${PROTO} ${DENSITY} ${TOPO} seed=${RUN_SEED}" >&2
    print_log_tail "$WORKER_LOG" "$WORKER_ID"
    return 1
  fi
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
  local WORKER_ID="$1" JOB=""
  while true; do
    JOB="$(pop_job)"
    if [[ -z "$JOB" ]]; then break; fi

    IFS='|' read -r PROTO DENSITY TOPO RUN_SEED SCEN_REL <<< "$JOB"
    run_one "$PROTO" "$DENSITY" "$TOPO" "$RUN_SEED" "$SCEN_REL" "$WORKER_ID" || true
  done
}

export -f mark_status print_log_tail bootstrap_gradle_home prepare_worker_workspace pop_job run_one monitor_loop worker_loop
export ROOT_DIR SCENARIOS_DIR RANDOM_DIR RESULTS_DIR COOJA_GRADLEW RUN_ROOT DEFAULT_GRADLE_HOME
export QUEUE_FILE QUEUE_LOCK STATUS_DIR LOG_DIR TOTAL MONITOR_INTERVAL ERROR_TAIL_LINES FORCE_RERUN

# Build jobs from manifest
RUN_SEED_LIST=$(PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}" python3 - <<PY
from scripts.generate_random_topologies import parse_spec
print(' '.join(str(x) for x in parse_spec('${RUN_SEEDS}')))
PY
)

QUEUE_LINES=$(PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}" python3 - <<PY
import json
from scripts.generate_random_topologies import parse_spec
manifest=json.load(open('${MANIFEST}',encoding='utf-8'))
allow_proto=set('${PROTOCOLS}'.split())
allow_density=set([x.strip() for x in '${DENSITIES}'.split(',') if x.strip()])
allow_topo=set(parse_spec('${TOPOLOGY_SEEDS}'))
run_seeds=parse_spec('${RUN_SEEDS}')
for t in manifest['topologies']:
    if t['density'] not in allow_density:
        continue
    if int(t['topology_seed']) not in allow_topo:
        continue
    topo_name=t['topology_name']
    density=t['density']
    for p, rel in t['scenarios'].items():
        if p not in allow_proto:
            continue
        for rs in run_seeds:
            print(f"{p}|{density}|{topo_name}|{rs}|{rel}")
PY
)

mapfile -t JOBS < <(printf '%s\n' "$QUEUE_LINES" | sed '/^$/d')
TOTAL="${#JOBS[@]}"

if [[ "$TOTAL" -eq 0 ]]; then
  echo "ERROR: no jobs selected. check filters." >&2
  exit 1
fi

if [[ "$FORCE_RERUN" -eq 1 ]]; then
  echo "=== Removing existing random-topo results for selected jobs ==="
  for JOB in "${JOBS[@]}"; do
    IFS='|' read -r PROTO DENSITY TOPO RUN_SEED _ <<< "$JOB"
    rm -rf "${RESULTS_DIR}/${DENSITY}/${TOPO}/${PROTO}/${RUN_SEED}"
  done
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "=== DRY RUN ==="
  echo "Protocols : $PROTOCOLS"
  echo "Densities : $DENSITIES"
  echo "TopoSeeds : $TOPOLOGY_SEEDS"
  echo "RunSeeds  : $RUN_SEEDS"
  echo "Total jobs: $TOTAL"
  printf '%s\n' "${JOBS[@]}" | sed -n '1,20p'
  exit 0
fi

RUN_ROOT="$(mktemp -d "${WORKER_BASE_ROOT}/run_XXXXXX")"
STATUS_DIR="${RUN_ROOT}/status"
LOG_DIR="${RUN_ROOT}/logs"
mkdir -p "$STATUS_DIR/queued" "$STATUS_DIR/running" "$STATUS_DIR/done" "$STATUS_DIR/failed" "$LOG_DIR"

QUEUE_FILE="$(mktemp "${RUN_ROOT}/queue_XXXXXX.txt")"
QUEUE_LOCK="${QUEUE_FILE}.lock"
touch "$QUEUE_LOCK"
printf '%s\n' "${JOBS[@]}" > "$QUEUE_FILE"

for JOB in "${JOBS[@]}"; do
  IFS='|' read -r PROTO DENSITY TOPO RUN_SEED _ <<< "$JOB"
  mark_status queued "$PROTO" "$DENSITY" "$TOPO" "$RUN_SEED" "0"
done

cleanup_queue() {
  rm -f "$QUEUE_FILE" "$QUEUE_LOCK"
}
trap cleanup_queue EXIT

echo "=== Running random-topology sweep (${PARALLEL_JOBS} workers) ==="
echo "Protocols : $PROTOCOLS"
echo "Densities : $DENSITIES"
echo "TopoSeeds : $TOPOLOGY_SEEDS"
echo "RunSeeds  : $RUN_SEEDS"
echo "Total jobs: $TOTAL"
echo "Run root  : $RUN_ROOT"
echo "Results   : $RESULTS_DIR"

declare -a PIDS
MONITOR_PID=""

bash -c "monitor_loop" &
MONITOR_PID="$!"
for WORKER_ID in $(seq 1 "$PARALLEL_JOBS"); do
  bash -c "worker_loop $WORKER_ID" &
  PIDS+=("$!")
done

STATUS=0
for PID in "${PIDS[@]}"; do
  wait "$PID" || STATUS=1
done
wait "$MONITOR_PID" || true

FAIL_COUNT=$(find "$STATUS_DIR/failed" -type f | wc -l)
DONE_COUNT=$(find "$STATUS_DIR/done" -type f | wc -l)
if [[ "$FAIL_COUNT" -gt 0 ]]; then STATUS=1; fi

echo ""
if [[ "$STATUS" -eq 0 ]]; then
  echo "=== Random-topology sweep complete ==="
else
  echo "=== Random-topology sweep complete with failures ==="
fi
echo "Completed: $DONE_COUNT / $TOTAL"
echo "Failed   : $FAIL_COUNT / $TOTAL"
echo "Results  : $RESULTS_DIR"

if [[ "$KEEP_RUN_ROOT" -eq 1 ]]; then
  echo "Run root kept: $RUN_ROOT"
elif [[ "$STATUS" -eq 0 ]]; then
  rm -rf "$RUN_ROOT"
  echo "Run root cleaned: $RUN_ROOT"
else
  echo "Run root kept for failure debug: $RUN_ROOT"
fi

exit "$STATUS"
