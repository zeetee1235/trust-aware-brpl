#!/usr/bin/env bash
# Periodically monitor result growth and trigger parse_results.py.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS_DIR="${ROOT_DIR}/results"
META_DIR="${RESULTS_DIR}/_meta"
PARSE_SCRIPT="${ROOT_DIR}/scripts/parse_results.py"

INTERVAL=120
MIN_NEW_DONE=300
THRESHOLD_GB=120
ONCE=0

usage() {
  cat <<USAGE
Usage: ./scripts/watch_storage_parse.sh [options]

Options:
  --interval SEC       Poll interval (default: 120)
  --min-new-done N     Run parser when done markers increased by N (default: 300)
  --threshold-gb N     Run parser when results dir >= N GiB (default: 120)
  --once               Evaluate once and exit
  -h, --help           Show help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval) INTERVAL="$2"; shift 2 ;;
    --min-new-done) MIN_NEW_DONE="$2"; shift 2 ;;
    --threshold-gb) THRESHOLD_GB="$2"; shift 2 ;;
    --once) ONCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

mkdir -p "$META_DIR"
LOG_FILE="${META_DIR}/watch_storage_parse.log"
STATE_FILE="${META_DIR}/watch_storage_parse.state"
LOCK_FILE="${META_DIR}/watch_storage_parse.lock"

count_done() {
  local n
  n="$(find "$RESULTS_DIR" -type f -name done 2>/dev/null | wc -l || true)"
  if [[ -z "$n" ]]; then
    n=0
  fi
  printf '%s\n' "$n"
}

results_size_gb() {
  local k
  k="$(du -sk "$RESULTS_DIR" 2>/dev/null | awk '{print $1}' || true)"
  if [[ -z "$k" ]]; then
    k=0
  fi
  echo $((k / 1024 / 1024))
}

read_state() {
  LAST_PARSED_DONE=0
  if [[ -f "$STATE_FILE" ]]; then
    LAST_PARSED_DONE="$(awk -F'=' '$1=="last_parsed_done"{print $2}' "$STATE_FILE" | tail -n1 || true)"
    if [[ -z "${LAST_PARSED_DONE}" ]]; then
      LAST_PARSED_DONE=0
    fi
  fi
}

write_state() {
  local done_now="$1"
  cat > "$STATE_FILE" <<STATE
last_parsed_done=${done_now}
updated_at=$(date '+%F %T %Z')
STATE
}

run_parse() {
  local reason="$1" done_now="$2" size_gb="$3"
  {
    echo "[$(date '+%F %T %Z')] [PARSE] reason=${reason} done=${done_now} size_gb=${size_gb}"
    python3 "$PARSE_SCRIPT"
    echo "[$(date '+%F %T %Z')] [PARSE] done"
  } >> "$LOG_FILE" 2>&1
}

loop_once() {
  local done_now size_gb delta reason
  read_state
  done_now=$(count_done)
  size_gb=$(results_size_gb)
  delta=$((done_now - LAST_PARSED_DONE))
  reason=""

  if [[ "$size_gb" -ge "$THRESHOLD_GB" ]]; then
    reason="size>=${THRESHOLD_GB}GiB"
  elif [[ "$delta" -ge "$MIN_NEW_DONE" ]]; then
    reason="new_done>=${MIN_NEW_DONE}"
  fi

  echo "[$(date '+%F %T %Z')] done=${done_now} delta=${delta} size_gb=${size_gb} threshold=${THRESHOLD_GB}" >> "$LOG_FILE"

  if [[ -n "$reason" ]]; then
    if mkdir "$LOCK_FILE" 2>/dev/null; then
      trap 'rmdir "$LOCK_FILE" 2>/dev/null || true' RETURN
      run_parse "$reason" "$done_now" "$size_gb"
      write_state "$done_now"
      rmdir "$LOCK_FILE" 2>/dev/null || true
      trap - RETURN
    else
      echo "[$(date '+%F %T %Z')] [SKIP] parse lock exists" >> "$LOG_FILE"
    fi
  fi
}

if [[ "$ONCE" -eq 1 ]]; then
  loop_once
  exit 0
fi

while true; do
  loop_once
  sleep "$INTERVAL"
done
