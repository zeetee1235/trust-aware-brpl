#!/bin/bash
# Run simulation with external trust_engine in real-time

set -e

# Environment setup
if [ -z "$CONTIKI_NG_PATH" ] || [ "$CONTIKI_NG_PATH" = "/path/to/contiki-ng" ]; then
    export CONTIKI_NG_PATH=/home/dev/contiki-ng
fi

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_DIR"

# Parse arguments
SIM_TIME_SEC=${1:-600}
SIMULATION_FILE="${2:-$PROJECT_DIR/configs/simulation.csc}"

LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

TRUST_FEEDBACK_PATH="$LOG_DIR/trust_updates.txt"
TRUST_METRICS_PATH="$LOG_DIR/trust_metrics.csv"
BLACKLIST_PATH="$LOG_DIR/blacklist.csv"
COOJA_LOG="$LOG_DIR/COOJA.testlog"

echo "============================================"
echo "Running Simulation with External Trust Engine"
echo "============================================"
echo "Simulation time: ${SIM_TIME_SEC}s"
echo "Simulation file: $SIMULATION_FILE"
echo "Trust engine: tools/trust_engine"
echo ""

# Build trust_engine if not exists
if [ ! -f "$PROJECT_DIR/tools/trust_engine/target/release/trust_engine" ]; then
    echo "Building trust_engine..."
    cd "$PROJECT_DIR/tools/trust_engine"
    cargo build --release
    cd "$PROJECT_DIR"
fi

# Clean old logs
rm -f "$COOJA_LOG" "$TRUST_FEEDBACK_PATH" "$TRUST_METRICS_PATH" "$BLACKLIST_PATH"

# Prepare simulation config
SIM_TIME_MS=$((SIM_TIME_SEC * 1000))
SIM_TMP="$PROJECT_DIR/configs/simulation_tmp.csc"
touch "$TRUST_FEEDBACK_PATH"
sed \
  -e "s/@SIM_TIME_MS@/${SIM_TIME_MS}/g" \
  -e "s/@SIM_TIME_SEC@/${SIM_TIME_SEC}/g" \
  -e "s#@TRUST_FEEDBACK_PATH@#${TRUST_FEEDBACK_PATH}#g" \
  "$SIMULATION_FILE" > "$SIM_TMP"

# Disable SerialSocketServer if requested
if [ "${SERIAL_SOCKET_DISABLE:-0}" = "1" ]; then
    python3 - <<'PY'
import re
from pathlib import Path
path = Path("configs/simulation_tmp.csc")
data = path.read_text()
data = re.sub(r"<plugin>\s*org\.contikios\.cooja\.serialsocket\.SerialSocketServer.*?</plugin>\s*", "", data, flags=re.S)
path.write_text(data)
PY
fi

echo "Starting trust_engine in background..."
"$PROJECT_DIR/tools/trust_engine/target/release/trust_engine" \
    --input "$COOJA_LOG" \
    --output "$TRUST_FEEDBACK_PATH" \
    --metrics-out "$TRUST_METRICS_PATH" \
    --blacklist-out "$BLACKLIST_PATH" \
    --metric ewma \
    --alpha 0.2 \
    --ewma-min 700 \
    --miss-threshold 5 \
    --follow \
    --poll-ms 200 &

TRUST_ENGINE_PID=$!
echo "Trust engine PID: $TRUST_ENGINE_PID"

# Give trust_engine time to start
sleep 1

echo ""
echo "Starting Cooja simulation..."
cd "$CONTIKI_NG_PATH"

java --enable-preview ${JAVA_OPTS} \
    -jar tools/cooja/build/libs/cooja.jar \
    --no-gui \
    --autostart \
    --contiki="$CONTIKI_NG_PATH" \
    --logdir="$LOG_DIR" \
    "$SIM_TMP" 2>&1 | grep -v "ContikiRS232" &

COOJA_PID=$!
echo "Cooja PID: $COOJA_PID"

# Monitor progress
START_TS=$(date +%s)
while kill -0 "$COOJA_PID" 2>/dev/null; do
    ELAPSED=$(($(date +%s) - START_TS))
    PERCENT=$((ELAPSED * 100 / SIM_TIME_SEC))
    echo -ne "\rProgress: ${PERCENT}% (${ELAPSED}/${SIM_TIME_SEC}s)"
    sleep 2
done
echo ""

# Wait for simulation to complete
wait "$COOJA_PID"
COOJA_EXIT=$?

echo ""
echo "Simulation completed. Stopping trust_engine..."
kill "$TRUST_ENGINE_PID" 2>/dev/null || true
wait "$TRUST_ENGINE_PID" 2>/dev/null || true

echo ""
echo "============================================"
echo "Results:"
echo "============================================"
echo "Cooja log:        $COOJA_LOG"
echo "Trust updates:    $TRUST_FEEDBACK_PATH"
echo "Trust metrics:    $TRUST_METRICS_PATH"
echo "Blacklist:        $BLACKLIST_PATH"
echo ""

# Save results
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RESULTS_DIR="$PROJECT_DIR/results/run-$TIMESTAMP"
mkdir -p "$RESULTS_DIR"
cp "$COOJA_LOG" "$RESULTS_DIR/" 2>/dev/null || true
cp "$TRUST_FEEDBACK_PATH" "$RESULTS_DIR/" 2>/dev/null || true
cp "$TRUST_METRICS_PATH" "$RESULTS_DIR/" 2>/dev/null || true
cp "$BLACKLIST_PATH" "$RESULTS_DIR/" 2>/dev/null || true
echo "Results saved to: $RESULTS_DIR"

# Parse results
if [ -f "$PROJECT_DIR/tools/parse_results.py" ]; then
    echo ""
    echo "Parsing results..."
    python3 "$PROJECT_DIR/tools/parse_results.py" "$COOJA_LOG"
fi

exit $COOJA_EXIT
