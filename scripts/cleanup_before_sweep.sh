#!/usr/bin/env bash
# Clean bulky generated artifacts before large sweep runs.
# Default: dry-run. Use --apply to actually delete.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APPLY=0
CLEAN_RESULTS=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --keep-results) CLEAN_RESULTS=0; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

cd "$ROOT_DIR"

print_size() {
  local path="$1"
  du -sh "$path" 2>/dev/null | awk '{print $1}' || true
}

delete_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    return 0
  fi

  local sz
  sz="$(print_size "$path")"
  if [[ "$APPLY" -eq 1 ]]; then
    rm -rf -- "$path"
    echo "[DEL] $path ${sz:+($sz)}"
  else
    echo "[DRY] $path ${sz:+($sz)}"
  fi
}

delete_glob() {
  local pattern="$1"
  shopt -s nullglob
  local paths=( $pattern )
  shopt -u nullglob
  for p in "${paths[@]}"; do
    delete_path "$p"
  done
}

echo "=== Cleanup before sweep ==="
echo "Mode: $([[ "$APPLY" -eq 1 ]] && echo APPLY || echo DRY-RUN)"

# 1) Worker environments / run caches
for p in \
  .parallel_worker_env \
  .parallel_worker_env_random \
  .parallel_worker_env_bak_* \
  .parallel_worker_env_loss* \
; do
  delete_glob "$p"
done

# 2) Results (optional)
if [[ "$CLEAN_RESULTS" -eq 1 ]]; then
  delete_path "results"
  if [[ "$APPLY" -eq 1 ]]; then
    mkdir -p results
  fi
else
  echo "[SKIP] results (kept by --keep-results)"
fi

# 3) Crash logs and temp files
for p in \
  hs_err_pid*.log \
  **/__pycache__ \
  configs/scenarios/tmp_*.csc \
  ./**/*.tmp \
; do
  delete_glob "$p"
done

# 4) Cooja native build artifacts
for p in \
  motes/build \
  ./*/workspace/motes/build \
; do
  delete_glob "$p"
done

# 5) LaTeX aux files in docs/paper (keep paper.tex/pdf)
for ext in aux bbl blg fdb_latexmk fls log out toc; do
  delete_glob "docs/paper/*.${ext}"
done

echo "=== Cleanup done ==="
if [[ "$APPLY" -eq 0 ]]; then
  echo "Run with: ./scripts/cleanup_before_sweep.sh --apply"
fi
