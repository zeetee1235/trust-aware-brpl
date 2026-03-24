#!/usr/bin/env bash
# One-shot launcher: random-topology sweep + parameter sweep bundle (+ optional extras)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
META_DIR="${ROOT_DIR}/results/_meta"
RANDOM_SWEEP="${ROOT_DIR}/scripts/run_random_topo_sweep.sh"
PARAM_BUNDLE="${ROOT_DIR}/scripts/run_param_sweep_bundle.sh"

JOBS=12
RERUN=1
WITH_LOSS_ATTACK=1
INCLUDE_PLAIN_BUNDLE=0
DRY_RUN=0
MEM_GUARD=1
MEM_PER_JOB_MIB=900
MEM_RESERVE_GIB=10
JAVA_XMX_MB=512
JAVA_XMS_MB=128
TEMP_GUARD=1
TEMP_CUTOFF_C=97
TEMP_CHECK_INTERVAL=5
TEMP_CONSECUTIVE=6
TEMP_GRACE_SEC=30

usage() {
  cat <<USAGE
Usage: ./scripts/run_all_sweeps_once.sh [options]

Options:
  --jobs N                 Parallel jobs per underlying sweep (default: 12)
  --no-rerun               Do not pass --rerun to child scripts
  --without-loss-attack    Run param bundle without LOSS x ATTACK matrix
  --include-plain-bundle   Run plain param bundle once before matrix bundle
  --no-mem-guard           Disable memory-based auto downscale for jobs
  --mem-per-job-mib N      Estimated memory per worker (default: 900)
  --mem-reserve-gib N      System memory to keep free (default: 10)
  --java-xmx-mb N          JVM max heap for Cooja Java process (default: 512)
  --java-xms-mb N          JVM initial heap (default: 128)
  --temp-cutoff C          Auto-interrupt when CPU temp >= C (default: 97)
  --temp-check SEC         Temp polling interval seconds (default: 5)
  --temp-consecutive N     Consecutive hot checks before interrupt (default: 6)
  --temp-grace SEC         Wait before SIGKILL after SIGTERM (default: 30)
  --no-temp-guard          Disable temperature watchdog
  --dry-run                Print commands only
  -h, --help               Show this help

Default behavior:
  1) random topology sweep (4800 runs)
  2) parameter sweep bundle with --with-loss-attack (5670 runs)
  Total expected: 10470 runs
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --jobs) JOBS="$2"; shift 2 ;;
    --no-rerun) RERUN=0; shift ;;
    --without-loss-attack) WITH_LOSS_ATTACK=0; shift ;;
    --include-plain-bundle) INCLUDE_PLAIN_BUNDLE=1; shift ;;
    --no-mem-guard) MEM_GUARD=0; shift ;;
    --mem-per-job-mib) MEM_PER_JOB_MIB="$2"; shift 2 ;;
    --mem-reserve-gib) MEM_RESERVE_GIB="$2"; shift 2 ;;
    --java-xmx-mb) JAVA_XMX_MB="$2"; shift 2 ;;
    --java-xms-mb) JAVA_XMS_MB="$2"; shift 2 ;;
    --temp-cutoff) TEMP_CUTOFF_C="$2"; shift 2 ;;
    --temp-check) TEMP_CHECK_INTERVAL="$2"; shift 2 ;;
    --temp-consecutive) TEMP_CONSECUTIVE="$2"; shift 2 ;;
    --temp-grace) TEMP_GRACE_SEC="$2"; shift 2 ;;
    --no-temp-guard) TEMP_GUARD=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

mkdir -p "$META_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${META_DIR}/run_all_sweeps_${TS}.log"
PID_FILE="${META_DIR}/run_all_sweeps_${TS}.pid"
META_FILE="${META_DIR}/run_all_sweeps_${TS}.meta"
OVERHEAT_FLAG="${META_DIR}/run_all_sweeps_${TS}.overheat"
ln -sfn "$(basename "$LOG_FILE")" "${META_DIR}/run_all_sweeps_latest.log"
ln -sfn "$(basename "$PID_FILE")" "${META_DIR}/run_all_sweeps_latest.pid"
ln -sfn "$(basename "$META_FILE")" "${META_DIR}/run_all_sweeps_latest.meta"
ln -sfn "$(basename "$OVERHEAT_FLAG")" "${META_DIR}/run_all_sweeps_latest.overheat"

detect_total_mem_mib() {
  awk '/MemTotal:/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || true
}

REQUESTED_JOBS="$JOBS"
TOTAL_MEM_MIB="$(detect_total_mem_mib)"
RESERVE_MIB=$((MEM_RESERVE_GIB * 1024))
SAFE_JOBS_MEM="$REQUESTED_JOBS"
if [[ "$MEM_GUARD" -eq 1 && -n "$TOTAL_MEM_MIB" && "$TOTAL_MEM_MIB" -gt 0 && "$MEM_PER_JOB_MIB" -gt 0 ]]; then
  local_budget=$((TOTAL_MEM_MIB - RESERVE_MIB))
  if [[ "$local_budget" -lt "$MEM_PER_JOB_MIB" ]]; then
    SAFE_JOBS_MEM=1
  else
    SAFE_JOBS_MEM=$((local_budget / MEM_PER_JOB_MIB))
    if [[ "$SAFE_JOBS_MEM" -lt 1 ]]; then SAFE_JOBS_MEM=1; fi
  fi
  if [[ "$JOBS" -gt "$SAFE_JOBS_MEM" ]]; then
    JOBS="$SAFE_JOBS_MEM"
  fi
fi

if [[ "$JAVA_XMS_MB" -gt "$JAVA_XMX_MB" ]]; then
  JAVA_XMS_MB="$JAVA_XMX_MB"
fi
export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS:-} -Xms${JAVA_XMS_MB}m -Xmx${JAVA_XMX_MB}m"

RERUN_FLAG=()
if [[ "$RERUN" -eq 1 ]]; then
  RERUN_FLAG=(--rerun)
fi

PARAM_FLAGS=()
if [[ "$WITH_LOSS_ATTACK" -eq 1 ]]; then
  PARAM_FLAGS+=(--with-loss-attack)
fi

RANDOM_TOTAL=4800
PARAM_TOTAL=3870
if [[ "$WITH_LOSS_ATTACK" -eq 1 ]]; then
  PARAM_TOTAL=5670
fi
if [[ "$INCLUDE_PLAIN_BUNDLE" -eq 1 && "$WITH_LOSS_ATTACK" -eq 1 ]]; then
  PARAM_TOTAL=$((PARAM_TOTAL + 3870))
fi
GRAND_TOTAL=$((RANDOM_TOTAL + PARAM_TOTAL))
RANDOM_BASE=$(find "${ROOT_DIR}/results/random_topo" -type f -name done 2>/dev/null | wc -l || true)
PARAM_BASE=$(find "${ROOT_DIR}/results" -type f -name done ! -path "${ROOT_DIR}/results/random_topo/*" 2>/dev/null | wc -l || true)

printf '%s\n' "$$" > "$PID_FILE"
cat > "$META_FILE" <<META
log_file=${LOG_FILE}
pid_file=${PID_FILE}
random_total=${RANDOM_TOTAL}
param_total=${PARAM_TOTAL}
random_base=${RANDOM_BASE}
param_base=${PARAM_BASE}
overheat_flag=${OVERHEAT_FLAG}
requested_jobs=${REQUESTED_JOBS}
effective_jobs=${JOBS}
mem_guard=${MEM_GUARD}
total_mem_mib=${TOTAL_MEM_MIB}
mem_per_job_mib=${MEM_PER_JOB_MIB}
mem_reserve_gib=${MEM_RESERVE_GIB}
safe_jobs_mem=${SAFE_JOBS_MEM}
jvm_xms_mb=${JAVA_XMS_MB}
jvm_xmx_mb=${JAVA_XMX_MB}
temp_guard=${TEMP_GUARD}
temp_cutoff_c=${TEMP_CUTOFF_C}
temp_check_interval=${TEMP_CHECK_INTERVAL}
temp_consecutive=${TEMP_CONSECUTIVE}
META

detect_max_cpu_temp_c() {
  local max_c=-1
  local raw val

  for raw_file in /sys/class/thermal/thermal_zone*/temp /sys/class/hwmon/hwmon*/temp*_input; do
    [[ -r "$raw_file" ]] || continue
    raw="$(cat "$raw_file" 2>/dev/null || true)"
    [[ "$raw" =~ ^-?[0-9]+$ ]] || continue
    if (( raw >= 1000 || raw <= -1000 )); then
      val=$((raw / 1000))
    else
      val=$raw
    fi
    if (( val > max_c )); then
      max_c="$val"
    fi
  done

  if (( max_c >= 0 )); then
    printf '%s\n' "$max_c"
    return 0
  fi

  if command -v sensors >/dev/null 2>&1; then
    local smax
    smax="$(
      sensors 2>/dev/null \
      | grep -Eo '[+-]?[0-9]+(\.[0-9]+)?°C' \
      | sed -E 's/[+°C]//g' \
      | awk 'BEGIN{m=-1}{v=int($1+0); if(v>m)m=v}END{if(m>=0)print m}'
    )"
    if [[ -n "$smax" ]]; then
      printf '%s\n' "$smax"
      return 0
    fi
  fi

  return 1
}

temp_watchdog() {
  local child_pid="$1"
  local child_pgid="$2"
  local label="$3"
  local hot_count=0
  local temp_c=""

  while kill -0 "$child_pid" >/dev/null 2>&1; do
    temp_c="$(detect_max_cpu_temp_c || true)"
    if [[ -n "$temp_c" ]]; then
      if (( temp_c >= TEMP_CUTOFF_C )); then
        hot_count=$((hot_count + 1))
        echo "[TEMP ] ${label}: cpu_max=${temp_c}C threshold=${TEMP_CUTOFF_C}C hot=${hot_count}/${TEMP_CONSECUTIVE}"
      else
        hot_count=0
      fi

      if (( hot_count >= TEMP_CONSECUTIVE )); then
        {
          echo "time=$(date '+%F %T %Z')"
          echo "label=${label}"
          echo "temp_c=${temp_c}"
          echo "cutoff_c=${TEMP_CUTOFF_C}"
          echo "consecutive=${TEMP_CONSECUTIVE}"
        } > "$OVERHEAT_FLAG"

        echo "[ABORT] Overheat guard triggered for ${label} (cpu_max=${temp_c}C). Sending SIGTERM."
        if [[ -n "$child_pgid" ]]; then
          kill -TERM "-${child_pgid}" >/dev/null 2>&1 || kill -TERM "$child_pid" >/dev/null 2>&1 || true
        else
          kill -TERM "$child_pid" >/dev/null 2>&1 || true
        fi

        sleep "$TEMP_GRACE_SEC"
        if kill -0 "$child_pid" >/dev/null 2>&1; then
          echo "[ABORT] ${label} still alive after ${TEMP_GRACE_SEC}s. Sending SIGKILL."
          if [[ -n "$child_pgid" ]]; then
            kill -KILL "-${child_pgid}" >/dev/null 2>&1 || kill -KILL "$child_pid" >/dev/null 2>&1 || true
          else
            kill -KILL "$child_pid" >/dev/null 2>&1 || true
          fi
        fi
        break
      fi
    fi

    sleep "$TEMP_CHECK_INTERVAL"
  done
}

run_guarded() {
  local label="$1"
  shift
  local cmd=("$@")

  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY ] ${cmd[*]}"
    return 0
  fi

  if [[ "$TEMP_GUARD" -eq 0 ]]; then
    "${cmd[@]}"
    return $?
  fi

  rm -f "$OVERHEAT_FLAG"
  "${cmd[@]}" &
  local child_pid="$!"
  local child_pgid
  child_pgid="$(ps -o pgid= "$child_pid" 2>/dev/null | tr -d '[:space:]' || true)"

  temp_watchdog "$child_pid" "$child_pgid" "$label" &
  local watchdog_pid="$!"

  local rc=0
  if ! wait "$child_pid"; then
    rc=$?
  fi

  kill "$watchdog_pid" >/dev/null 2>&1 || true
  wait "$watchdog_pid" 2>/dev/null || true

  if [[ -f "$OVERHEAT_FLAG" ]]; then
    echo "[ABORT] ${label} interrupted by temperature guard."
    return 124
  fi

  return "$rc"
}

{
  echo "[START] $(date '+%F %T %Z')"
  echo "[INFO ] log: ${LOG_FILE}"
  echo "[INFO ] pid: ${PID_FILE}"
  echo "[INFO ] meta: ${META_FILE}"
  echo "[INFO ] jobs_requested=${REQUESTED_JOBS} jobs_effective=${JOBS} rerun=${RERUN} with_loss_attack=${WITH_LOSS_ATTACK} include_plain_bundle=${INCLUDE_PLAIN_BUNDLE}"
  echo "[INFO ] mem_guard=${MEM_GUARD} total_mem_mib=${TOTAL_MEM_MIB} mem_per_job_mib=${MEM_PER_JOB_MIB} reserve_gib=${MEM_RESERVE_GIB} safe_jobs_mem=${SAFE_JOBS_MEM}"
  echo "[INFO ] jvm_xms=${JAVA_XMS_MB}m jvm_xmx=${JAVA_XMX_MB}m"
  echo "[INFO ] expected_random=${RANDOM_TOTAL} expected_param=${PARAM_TOTAL} expected_total=${GRAND_TOTAL}"
  echo "[INFO ] baseline_random=${RANDOM_BASE} baseline_param=${PARAM_BASE}"
  echo "[INFO ] temp_guard=${TEMP_GUARD} cutoff=${TEMP_CUTOFF_C}C check=${TEMP_CHECK_INTERVAL}s consecutive=${TEMP_CONSECUTIVE} grace=${TEMP_GRACE_SEC}s"
  if [[ "$REQUESTED_JOBS" -ne "$JOBS" ]]; then
    echo "[WARN ] jobs downscaled by mem-guard: requested=${REQUESTED_JOBS} -> effective=${JOBS}"
  fi
  echo ""

  run_guarded "random-topology" "${RANDOM_SWEEP}" --jobs "$JOBS" "${RERUN_FLAG[@]}"

  if [[ "$INCLUDE_PLAIN_BUNDLE" -eq 1 ]]; then
    run_guarded "param-bundle-plain" "${PARAM_BUNDLE}" --jobs "$JOBS" "${RERUN_FLAG[@]}"
  fi

  run_guarded "param-bundle" "${PARAM_BUNDLE}" --jobs "$JOBS" "${RERUN_FLAG[@]}" "${PARAM_FLAGS[@]}"

  echo ""
  echo "[DONE ] $(date '+%F %T %Z')"
} 2>&1 | tee "$LOG_FILE"

echo "Latest log : ${META_DIR}/run_all_sweeps_latest.log"
echo "Latest pid : ${META_DIR}/run_all_sweeps_latest.pid"
echo "Latest meta: ${META_DIR}/run_all_sweeps_latest.meta"
echo "Latest temp: ${META_DIR}/run_all_sweeps_latest.overheat"
echo "Monitor    : ./scripts/monitor_all_sweeps.sh"
