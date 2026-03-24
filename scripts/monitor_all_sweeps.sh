#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PY_MONITOR="${ROOT_DIR}/scripts/monitor_all_sweeps_rich.py"

if [[ ! -f "$PY_MONITOR" ]]; then
  echo "Missing monitor script: $PY_MONITOR" >&2
  exit 1
fi

if ! python3 - <<'PY' >/dev/null 2>&1
import importlib.util
raise SystemExit(0 if importlib.util.find_spec('rich') else 1)
PY
then
  echo "Python package 'rich' is required. Install it and retry." >&2
  echo "Example: pip install rich" >&2
  exit 1
fi

exec python3 "$PY_MONITOR" --root "$ROOT_DIR" "$@"
