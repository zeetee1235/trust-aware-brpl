#!/bin/bash
# Real-time monitoring script for parallel experiments

RESULTS_PATTERN=${1:-"results/experiments-*"}
REFRESH_SEC=${REFRESH_SEC:-3}
MAX_RECENT=${MAX_RECENT:-5}

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

strip_ansi() {
  sed -E 's/\x1b\[[0-9;]*m//g'
}

shorten() {
  local text="$1"
  local width="$2"
  if [ "${#text}" -le "$width" ]; then
    printf "%s" "$text"
  else
    printf "%s..." "${text:0:$((width-3))}"
  fi
}

find_latest_dir() {
  ls -td ${RESULTS_PATTERN} 2>/dev/null | head -1
}

get_worker_usage() {
  local pid="$1"
  if [ -z "$pid" ]; then
    echo "0.0 0"
    return
  fi
  {
    ps -p "$pid" -o %cpu=,rss= 2>/dev/null
    ps --ppid "$pid" -o %cpu=,rss= 2>/dev/null
  } | awk '{cpu+=$1; rss+=$2} END{printf "%.1f %.0f\n", cpu+0, (rss/1024)+0}'
}

get_system_load() {
  awk '{print $1 ", " $2 ", " $3}' /proc/loadavg 2>/dev/null || echo "N/A"
}

get_system_mem() {
  awk '
    /^MemTotal:/ {t=$2}
    /^MemAvailable:/ {a=$2}
    END {
      if (t > 0) {
        u=t-a
        printf "%.0f/%.0f MB (%.1f%%)", u/1024, t/1024, (u*100.0)/t
      } else {
        printf "N/A"
      }
    }
  ' /proc/meminfo 2>/dev/null
}

trap 'echo; echo "monitor stopped"; exit 0' INT TERM

while true; do
  LATEST_DIR="$(find_latest_dir)"

  clear

  if [ -z "$LATEST_DIR" ]; then
    echo -e "${RED}No experiment directory found for pattern: ${RESULTS_PATTERN}${NC}"
    echo -e "${DIM}Tip: ./scripts/monitor_parallel.sh \"results/experiments-20260305-*\"${NC}"
    sleep "$REFRESH_SEC"
    continue
  fi

  WORKER_LOG_DIR="$LATEST_DIR/worker_logs"
  RUN_DIR_COUNT=$(find "$LATEST_DIR" -mindepth 1 -maxdepth 1 -type d ! -name "worker_logs" 2>/dev/null | wc -l)
  RUNNING_WORKERS=0
  FINISHED_WORKERS=0
  TOTAL_ASSIGNED=0
  TOTAL_DONE=0
  TOTAL_SUCCESS=0
  TOTAL_FAIL=0
  TOTAL_CPU="0.0"
  TOTAL_MEM_MB=0

  echo -e "${CYAN}${BOLD}Parallel Experiment Monitor${NC}"
  echo -e "${DIM}Directory:${NC} ${YELLOW}$(basename "$LATEST_DIR")${NC}    ${DIM}Refresh:${NC} ${REFRESH_SEC}s"
  echo ""

  if [ ! -d "$WORKER_LOG_DIR" ]; then
    echo -e "${YELLOW}No worker_logs directory yet: $WORKER_LOG_DIR${NC}"
    sleep "$REFRESH_SEC"
    continue
  fi

  printf "%b\n" "${BLUE}┌────────┬──────────┬──────────────┬───────────┬────────┬─────────┬──────────────────────────────────────┐${NC}"
  printf "%b\n" "${BLUE}│ Worker │ State    │ Progress     │ Result    │ CPU(%) │ MEM(MB) │ Current / Last                       │${NC}"
  printf "%b\n" "${BLUE}├────────┼──────────┼──────────────┼───────────┼────────┼─────────┼──────────────────────────────────────┤${NC}"

  for worker_log in $(ls "$WORKER_LOG_DIR"/worker_*.log 2>/dev/null | sort -V); do
    [ -f "$worker_log" ] || continue

    worker_num="$(basename "$worker_log" .log | sed 's/worker_//')"
    worker_pid="$(pgrep -f "run_experiments_worker.sh $worker_num " 2>/dev/null | head -1)"

    assigned=$(grep -m1 "Assigned experiments:" "$worker_log" | strip_ansi | sed -E 's/.*Assigned experiments: ([0-9]+).*/\1/' )
    [ -n "$assigned" ] || assigned=0

    success=$(grep -E "Completed: .*_s[0-9]+" "$worker_log" 2>/dev/null | wc -l)
    fail=$(grep -c "Simulation failed:" "$worker_log" 2>/dev/null || true)
    done=$((success + fail))

    TOTAL_ASSIGNED=$((TOTAL_ASSIGNED + assigned))
    TOTAL_DONE=$((TOTAL_DONE + done))
    TOTAL_SUCCESS=$((TOTAL_SUCCESS + success))
    TOTAL_FAIL=$((TOTAL_FAIL + fail))

    if [ -n "$worker_pid" ]; then
      state="${GREEN}RUNNING${NC}"
      RUNNING_WORKERS=$((RUNNING_WORKERS + 1))
      current_task=$(grep "Running:" "$worker_log" | tail -1 | strip_ansi | sed -E 's/.*Running: //')
      current_task="$(shorten "$current_task" 36)"
      current_display="${CYAN}${current_task}${NC}"
    else
      state="${YELLOW}FINISHED${NC}"
      FINISHED_WORKERS=$((FINISHED_WORKERS + 1))
      last_line=$(tail -1 "$worker_log" | strip_ansi)
      current_display="$(shorten "$last_line" 36)"
    fi

    if [ "$assigned" -gt 0 ]; then
      pct=$((done * 100 / assigned))
      progress="${done}/${assigned} (${pct}%)"
    else
      progress="${done}/? (-)"
    fi

    result="${GREEN}✓${success}${NC} ${RED}✗${fail}${NC}"

    read -r cpu mem_mb <<< "$(get_worker_usage "$worker_pid")"
    TOTAL_CPU="$(awk -v a="$TOTAL_CPU" -v b="$cpu" 'BEGIN{printf "%.1f", a+b}')"
    TOTAL_MEM_MB=$((TOTAL_MEM_MB + mem_mb))

    printf "│ %6s │ %-26b │ %-12s │ %-15b │ %6s │ %7s │ %-36b │\n" \
      "$worker_num" "$state" "$progress" "$result" "$cpu" "$mem_mb" "$current_display"
  done

  printf "%b\n" "${BLUE}└────────┴──────────┴──────────────┴───────────┴────────┴─────────┴──────────────────────────────────────┘${NC}"
  echo ""

  if [ "$TOTAL_ASSIGNED" -gt 0 ]; then
    overall_pct=$((TOTAL_DONE * 100 / TOTAL_ASSIGNED))
  else
    overall_pct=0
  fi

  echo -e "${BLUE}${BOLD}Overall${NC}"
  echo -e "  Workers   : ${GREEN}${RUNNING_WORKERS}${NC} running / ${YELLOW}${FINISHED_WORKERS}${NC} finished"
  echo -e "  Progress  : ${BOLD}${TOTAL_DONE}/${TOTAL_ASSIGNED}${NC} (${overall_pct}%)"
  echo -e "  Results   : ${GREEN}✓ ${TOTAL_SUCCESS}${NC}   ${RED}✗ ${TOTAL_FAIL}${NC}"
  echo -e "  Worker Res: CPU ${BOLD}${TOTAL_CPU}%${NC} / MEM ${BOLD}${TOTAL_MEM_MB} MB${NC}"
  echo -e "  System    : Load ${BOLD}$(get_system_load)${NC} | Mem ${BOLD}$(get_system_mem)${NC}"
  echo -e "  Run dirs  : ${RUN_DIR_COUNT}"
  echo ""

  echo -e "${BLUE}${BOLD}Recent Completed${NC}"
  recent_done=$(grep -hE "Completed: .*_s[0-9]+" "$WORKER_LOG_DIR"/worker_*.log 2>/dev/null | tail -n "$MAX_RECENT")
  if [ -n "$recent_done" ]; then
    while IFS= read -r line; do
      run_name=$(echo "$line" | strip_ansi | sed -E 's/.*Completed: //')
      worker=$(echo "$line" | strip_ansi | grep -oE "WORKER-[0-9]+" | sed 's/WORKER-//')
      echo -e "  ${GREEN}✓${NC} W${worker}: $(shorten "$run_name" 90)"
    done <<< "$recent_done"
  else
    echo -e "  ${DIM}No completed runs yet${NC}"
  fi
  echo ""

  echo -e "${RED}${BOLD}Recent Errors${NC}"
  recent_fail=$(grep -h "Simulation failed:" "$WORKER_LOG_DIR"/worker_*.log 2>/dev/null | tail -n "$MAX_RECENT")
  if [ -n "$recent_fail" ]; then
    while IFS= read -r line; do
      run_name=$(echo "$line" | strip_ansi | sed -E 's/.*Simulation failed: ([^ ]+).*/\1/')
      worker=$(echo "$line" | strip_ansi | grep -oE "WORKER-[0-9]+" | sed 's/WORKER-//')
      echo -e "  ${RED}✗${NC} W${worker}: $(shorten "$run_name" 90)"
    done <<< "$recent_fail"
  else
    echo -e "  ${DIM}No failures logged${NC}"
  fi
  echo ""

  echo -e "${CYAN}────────────────────────────────────────────────────────────────────────────────────────────${NC}"
  echo -e "  Ctrl+C to exit | tail -f ${WORKER_LOG_DIR}/worker_N.log"

  sleep "$REFRESH_SEC"
done
