#!/bin/bash
# Compare Trust OFF vs ON for a single topology using single_test.sh

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_DIR"

echo "========================================="
echo "Trust ON/OFF Comparison (single_test.sh)"
echo "========================================="

run_case() {
  local trust="$1"
  echo ""
  echo "---- TRUST_ENABLED=$trust ----"
  TRUST_ENABLED="$trust" ./scripts/single_test.sh
}

run_case 0
run_case 1

echo ""
echo "Done. Compare latest results under results/quick_test_*."
