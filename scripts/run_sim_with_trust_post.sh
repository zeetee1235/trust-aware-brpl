#!/bin/bash
# Simplified: Run simulation first, then process trust

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_DIR"

SIM_TIME_SEC=${1:-600}
SIMULATION_FILE="${2:-$PROJECT_DIR/configs/simulation.csc}"

echo "============================================"
echo "Running Simulation with Post-Analysis Trust Engine"
echo "============================================"
echo "Simulation time: ${SIM_TIME_SEC}s"
echo ""

# Build trust_engine if needed
if [ ! -f "$PROJECT_DIR/tools/trust_engine/target/release/trust_engine" ]; then
    echo "Building trust_engine..."
    cd "$PROJECT_DIR/tools/trust_engine"
    cargo build --release
    cd "$PROJECT_DIR"
fi

# Run simulation
echo "Step 1: Running Cooja simulation..."
./scripts/run_simulation.sh "$SIM_TIME_SEC" "$SIMULATION_FILE"

# Process trust
echo ""
echo "Step 2: Processing trust with external engine..."
LOG_DIR="$PROJECT_DIR/logs"
COOJA_LOG="$LOG_DIR/COOJA.testlog"
TRUST_FEEDBACK="$LOG_DIR/trust_updates.txt"
TRUST_METRICS="$LOG_DIR/trust_metrics.csv"
BLACKLIST="$LOG_DIR/blacklist.csv"

"$PROJECT_DIR/tools/trust_engine/target/release/trust_engine" \
    --input "$COOJA_LOG" \
    --output "$TRUST_FEEDBACK" \
    --metrics-out "$TRUST_METRICS" \
    --blacklist-out "$BLACKLIST" \
    --metric ewma \
    --alpha 0.2 \
    --ewma-min 700 \
    --miss-threshold 5

echo ""
echo "============================================"
echo "Trust Analysis Complete"
echo "============================================"
echo "Trust updates:    $TRUST_FEEDBACK"
echo "Trust metrics:    $TRUST_METRICS"
echo "Blacklist:        $BLACKLIST"
echo ""

# Show summary
if [ -f "$TRUST_METRICS" ]; then
    echo "Trust Metrics Summary:"
    echo "---------------------"
    tail -10 "$TRUST_METRICS"
fi

echo ""
if [ -f "$TRUST_FEEDBACK" ]; then
    TRUST_COUNT=$(wc -l < "$TRUST_FEEDBACK")
    echo "Total trust updates: $TRUST_COUNT"
fi

if [ -f "$BLACKLIST" ] && [ $(wc -l < "$BLACKLIST") -gt 1 ]; then
    echo ""
    echo "Blacklisted nodes:"
    tail -n +2 "$BLACKLIST"
fi
