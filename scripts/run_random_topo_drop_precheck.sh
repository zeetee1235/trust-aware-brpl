#!/usr/bin/env bash
# Short pre-main sanity check for 4-way random-topology drop sweep.
# Goal: prove pipeline/policy snapshot runs cleanly before full main experiment.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER="${ROOT_DIR}/scripts/run_random_topo_drop_sweep.sh"
SUMMARIZER="${ROOT_DIR}/scripts/summarize_random_topo_drop_sweep.py"

PROTOCOLS="RPL,BRPL,SMTRUST,TABRPL"
DENSITIES="sparse,medium,dense"
TOPOLOGY_SEEDS="1-3"
RUN_SEEDS="1-2"
DROPS="0,25,50,75,100"
JOBS=12
RESULTS_ROOT="${ROOT_DIR}/results/random_topo_drop_precheck"
RERUN=1
DRY_RUN=0
KEEP_RUN_ROOT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --protocols) PROTOCOLS="$2"; shift 2 ;;
    --densities) DENSITIES="$2"; shift 2 ;;
    --topology-seeds) TOPOLOGY_SEEDS="$2"; shift 2 ;;
    --run-seeds) RUN_SEEDS="$2"; shift 2 ;;
    --drops) DROPS="$2"; shift 2 ;;
    --jobs) JOBS="$2"; shift 2 ;;
    --results-root) RESULTS_ROOT="$2"; shift 2 ;;
    --no-rerun) RERUN=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --keep-run-root) KEEP_RUN_ROOT=1; shift ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -x "$RUNNER" ]]; then
  echo "ERROR: missing runner: $RUNNER" >&2
  exit 1
fi
if [[ ! -f "$SUMMARIZER" ]]; then
  echo "ERROR: missing summarizer: $SUMMARIZER" >&2
  exit 1
fi

mkdir -p "$RESULTS_ROOT"

CMD=(
  bash "$RUNNER"
  --protocols "$PROTOCOLS"
  --densities "$DENSITIES"
  --topology-seeds "$TOPOLOGY_SEEDS"
  --run-seeds "$RUN_SEEDS"
  --drops "$DROPS"
  --jobs "$JOBS"
  --results-root "$RESULTS_ROOT"
)
if [[ "$RERUN" -eq 1 ]]; then
  CMD+=(--rerun)
fi
if [[ "$DRY_RUN" -eq 1 ]]; then
  CMD+=(--dry-run)
fi
if [[ "$KEEP_RUN_ROOT" -eq 1 ]]; then
  CMD+=(--keep-run-root)
fi

"${CMD[@]}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[INFO] dry-run mode: skip validation/report."
  exit 0
fi

EXPECTED_PER_DROP="$(PYTHONPATH="${ROOT_DIR}:${PYTHONPATH:-}" python3 - <<PY
from scripts.generate_random_topologies import parse_spec
proto_n = len([x for x in "${PROTOCOLS}".split(",") if x.strip()])
density_n = len([x for x in "${DENSITIES}".split(",") if x.strip()])
topo_n = len(parse_spec("${TOPOLOGY_SEEDS}"))
run_n = len(parse_spec("${RUN_SEEDS}"))
print(proto_n * density_n * topo_n * run_n)
PY
)"

python3 "$SUMMARIZER" \
  --results-root "$RESULTS_ROOT" \
  --expected-jobs "$EXPECTED_PER_DROP" \
  --drops "$DROPS"

REPORT="${RESULTS_ROOT}/precheck_report.md"
PASS=1

{
  echo "# Random Topology 4-way Drop Precheck"
  echo ""
  echo "- protocols: \`$PROTOCOLS\`"
  echo "- densities: \`$DENSITIES\`"
  echo "- topology_seeds: \`$TOPOLOGY_SEEDS\`"
  echo "- run_seeds: \`$RUN_SEEDS\`"
  echo "- drops: \`$DROPS\`"
  echo "- expected_jobs_per_drop: \`$EXPECTED_PER_DROP\`"
  echo ""
  echo "| drop | done | sim.log | drop-tag mismatch files | status |"
  echo "|---:|---:|---:|---:|---|"
} > "$REPORT"

IFS=',' read -r -a DROP_LIST <<< "$DROPS"
for raw in "${DROP_LIST[@]}"; do
  drop="${raw//[[:space:]]/}"
  if [[ -z "$drop" ]]; then
    continue
  fi
  dpad=$(printf "%03d" "$drop")
  dir="${RESULTS_ROOT}/drop_${dpad}"

  done_n=$(find "$dir" -type f -name done 2>/dev/null | wc -l)
  sim_n=$(find "$dir" -type f -name sim.log 2>/dev/null | wc -l)

  mismatch_n="$(python3 - <<PY
from pathlib import Path
root = Path("${dir}")
needle = "drop_pct=${drop}"
bad = 0
for p in root.rglob("sim.log"):
    txt = p.read_text(errors="replace")
    if needle not in txt:
        bad += 1
print(bad)
PY
)"

  status="PASS"
  if [[ "$done_n" -ne "$EXPECTED_PER_DROP" || "$sim_n" -ne "$EXPECTED_PER_DROP" || "$mismatch_n" -ne 0 ]]; then
    status="FAIL"
    PASS=0
  fi

  echo "| ${drop} | ${done_n} | ${sim_n} | ${mismatch_n} | ${status} |" >> "$REPORT"
done

if [[ "$PASS" -eq 1 ]]; then
  {
    echo ""
    echo "**Overall:** PASS"
    echo ""
    echo "This precheck is sufficient to start the full main experiment."
  } >> "$REPORT"
  echo "[PASS] precheck complete: $REPORT"
else
  {
    echo ""
    echo "**Overall:** FAIL"
    echo ""
    echo "Fix pipeline issues before launching the full main experiment."
  } >> "$REPORT"
  echo "[FAIL] precheck failed: $REPORT" >&2
  exit 1
fi
