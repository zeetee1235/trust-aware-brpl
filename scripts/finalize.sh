#!/usr/bin/env bash
# finalize.sh — Run after full sweep: parse + plot + analyze
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Parsing results ==="
python3 scripts/parse_results.py

echo ""
echo "=== Generating figures ==="
Rscript scripts/plot_main_figures.R

echo ""
echo "=== Statistical analysis ==="
python3 scripts/analyze_results.py

echo ""
echo "=== Seed counts ==="
for proto in RPL BRPL SMTRUST TABRPL; do
  n=$(ls results/$proto/ 2>/dev/null | wc -l)
  echo "  $proto: $n seeds"
done

echo ""
echo "Figures in: $(pwd)/figures/"
ls figures/*.pdf 2>/dev/null | xargs -I{} basename {}
