#!/bin/bash
# Quick single-scenario test for topology validation

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_DIR"

# Single configuration
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RESULTS_BASE="results/quick_test_$TIMESTAMP"
mkdir -p "$RESULTS_BASE"

# Test scenario: BRPL + 30% Attack (Trust ON/OFF selectable)
SCENARIO="4_brpl_attack_notrust"
ROUTING="BRPL"
BRPL_MODE=1  # BRPL=1, MRHOF=0
ATTACK="ATTACK"
TRUST_ENABLED=${TRUST_ENABLED:-1}
ATTACK_RATE=${ATTACK_DROP_PCT:-30}
SEED=999888
ATTACKER_NODE_ID=2
TOPOLOGY=${TOPOLOGY:-configs/topologies/T3.csc}

if [ "$TRUST_ENABLED" -eq 1 ]; then
    SCENARIO="6_brpl_attack_trust"
else
    SCENARIO="4_brpl_attack_notrust"
fi

RUN_NAME="${SCENARIO}_p${ATTACK_RATE}_s${SEED}"
RUN_DIR="$RESULTS_BASE/$RUN_NAME"
mkdir -p "$RUN_DIR"

echo "========================================="
echo "토폴로지 검증 (새 TX=45m, 클러스터 배치)"
echo "========================================="
echo "Scenario: $SCENARIO"
echo "Attack Rate: ${ATTACK_RATE}%"
echo "========================================="

# Environment - Use submodule for build, system Cooja for simulation
export CONTIKI_NG_PATH="$PROJECT_DIR/contiki-ng-brpl"
export COOJA_PATH="/home/dev/contiki-ng"
export SERIAL_SOCKET_DISABLE=1
export JAVA_OPTS="-Xmx4G -Xms2G"

# Create temp config IN CONFIGS DIRECTORY (so ../motes path works)
TEMP_CONFIG="configs/temp_quick_$TIMESTAMP.csc"
SIM_TIME=600  # 600 seconds for chain topology multi-hop
SIM_TIME_MS=$((SIM_TIME * 1000))
TRUST_FEEDBACK_FILE="$PROJECT_DIR/$RUN_DIR/trust_feedback.txt"

# Replace all placeholders like run_experiments.sh does
sed -e "s/<randomseed>[0-9]*<\/randomseed>/<randomseed>$SEED<\/randomseed>/g" \
    -e "s/@SIM_TIME_MS@/${SIM_TIME_MS}/g" \
    -e "s/@SIM_TIME_SEC@/${SIM_TIME}/g" \
    -e "s|@TRUST_FEEDBACK_PATH@|${TRUST_FEEDBACK_FILE}|g" \
    -e "s/BRPL_MODE=[0-9]/BRPL_MODE=$BRPL_MODE/g" \
    -e "s/TRUST_ENABLED=[0-9]/TRUST_ENABLED=$TRUST_ENABLED/g" \
    -e "s/TRUST_LAMBDA=[0-9][0-9]*/TRUST_LAMBDA=${TRUST_LAMBDA:-0}/g" \
    -e "s/TRUST_GAMMA=[0-9][0-9]*/TRUST_GAMMA=${TRUST_GAMMA:-1}/g" \
    -e "/TRUST_GAMMA=/! s/TRUST_LAMBDA=${TRUST_LAMBDA:-0}/TRUST_LAMBDA=${TRUST_LAMBDA:-0},TRUST_GAMMA=${TRUST_GAMMA:-1}/g" \
    -e "s/ATTACK_DROP_PCT=[0-9][0-9]*/ATTACK_DROP_PCT=$ATTACK_RATE/g" \
    "$TOPOLOGY" > "$TEMP_CONFIG"

# Disable SerialSocketServer
awk '
  $0 ~ /<plugin>/ { in_plugin = 1; plugin_buf = $0; next }
  in_plugin && $0 ~ /org.contikios.cooja.serialsocket.SerialSocketServer/ { skip = 1 }
  in_plugin {
    plugin_buf = plugin_buf "\n" $0
    if($0 ~ /<\/plugin>/) {
      if(!skip) { print plugin_buf }
      in_plugin = 0; skip = 0; plugin_buf = ""
    }
    next
  }
  { print }
' "$TEMP_CONFIG" > "${TEMP_CONFIG}.tmp" && mv "${TEMP_CONFIG}.tmp" "$TEMP_CONFIG"

# Clean build
echo "[1/3] Cleaning build..."
rm -rf motes/build 2>/dev/null || true

# Run
echo "[2/3] Running simulation (400s, fast DIO for multi-hop)..."
LOG_DIR="$PROJECT_DIR/$RUN_DIR/logs"
mkdir -p "$LOG_DIR"

TRUST_ENGINE_PID=""
echo "[2/3] Starting trust_engine..."
touch "$TRUST_FEEDBACK_FILE"
touch "$LOG_DIR/COOJA.testlog"
tools/trust_engine/target/release/trust_engine \
    --input "$LOG_DIR/COOJA.testlog" \
    --output "$TRUST_FEEDBACK_FILE" \
    --metrics-out "$PROJECT_DIR/$RUN_DIR/trust_metrics.csv" \
    --blacklist-out "$PROJECT_DIR/$RUN_DIR/blacklist.csv" \
    --exposure-out "$PROJECT_DIR/$RUN_DIR/exposure.csv" \
    --parent-out "$PROJECT_DIR/$RUN_DIR/parent_switch.csv" \
    --stats-out "$PROJECT_DIR/$RUN_DIR/stats.csv" \
    --stats-interval 200 \
    --metric ewma \
    --alpha 0.2 \
    --ewma-min 0.7 \
    --miss-threshold 5 \
    --forwarders-only \
    --fwd-drop-threshold 0.2 \
    --attacker-id 2 \
    --follow > "$PROJECT_DIR/$RUN_DIR/trust_engine.log" 2>&1 &
TRUST_ENGINE_PID=$!
sleep 2

timeout 800 java --enable-preview ${JAVA_OPTS} \
    -jar "$COOJA_PATH/tools/cooja/build/libs/cooja.jar" \
    --no-gui \
    --autostart \
    --contiki="$CONTIKI_NG_PATH" \
    --logdir="$LOG_DIR" \
    "$TEMP_CONFIG" > "$PROJECT_DIR/$RUN_DIR/cooja_output.log" 2>&1

COOJA_EXIT=$?
rm -f "$TEMP_CONFIG"

if [ -n "$TRUST_ENGINE_PID" ]; then
    sleep 2
    kill $TRUST_ENGINE_PID 2>/dev/null || true
    sleep 1
    kill -9 $TRUST_ENGINE_PID 2>/dev/null || true
    wait $TRUST_ENGINE_PID 2>/dev/null || true
fi

if [ $COOJA_EXIT -ne 0 ]; then
    echo "❌ Simulation failed (exit: $COOJA_EXIT)"
    tail -20 "$PROJECT_DIR/$RUN_DIR/cooja_output.log"
    exit 1
fi

echo "[3/3] Parsing results..."

# Analysis
LOG_FILE="$LOG_DIR/COOJA.testlog"
if [ ! -f "$LOG_FILE" ]; then
    echo "❌ Log file not found"
    exit 1
fi

sent=$(grep -c "CSV,TX," "$LOG_FILE" || true)
recv=$(grep -c "CSV,RX," "$LOG_FILE" || true)
sent=${sent:-0}
recv=${recv:-0}
pdr=$(echo "scale=2; if ($sent==0) 0 else $recv * 100 / $sent" | bc 2>/dev/null || echo "0")

echo ""
echo "========================================="
echo "Results:"
echo "  Sent: $sent, Received: $recv"
echo "  PDR: ${pdr}%"
echo "========================================="

echo ""
echo "Parent Relationships:"
grep "CSV,PARENT" "$LOG_FILE" | sort -u | while read line; do
    node=$(echo "$line" | cut -d, -f3)
    parent=$(echo "$line" | cut -d, -f4)
    
    parent_name=$parent
    [ "$parent" == "fe80::201:1:1:1" ] && parent_name="Root"
    last_hex=$(echo "$parent" | awk -F':' '{print $NF}')
    [ "$last_hex" == "$(printf "%x" "$ATTACKER_NODE_ID")" ] && parent_name="Attacker"
    
    node_name="Node$node"
    [ "$node" == "2" ] && node_name="Attacker"
    [ "$node" -ge 3 ] && node_name="Sender$node"
    
    printf "  %-12s → %s\n" "$node_name" "$parent_name"
done

echo ""
echo "========================================="
echo "Validation:"

# Check multi-hop routing
attacker_parent_count=$(awk -F',' -v aid="$ATTACKER_NODE_ID" '
  $1=="CSV" && $2=="PARENT" && $3>=4 && $3<=12 {
    split($4, parts, ":");
    if(length(parts) && parts[length(parts)] == sprintf("%x", aid)) { c++ }
  }
  END{print c+0}
' "$LOG_FILE")
if [ "$attacker_parent_count" -ge 3 ]; then
    echo "✅ Multi-hop routing confirmed (${attacker_parent_count}/5 senders via Attacker)"
else
    echo "❌ Multi-hop failed (only $attacker_parent_count senders via Attacker)"
fi

# Check attacker forwarding
fwd_lines=$(grep "CSV,FWD,3," "$LOG_FILE" | tail -1)
if [ -n "$fwd_lines" ]; then
    tx_ok=$(echo "$fwd_lines" | cut -d, -f5)
    echo "✅ Attacker forwarding packets (TX_OK=$tx_ok)"
else
    echo "❌ Attacker not forwarding"
fi

# Check attack effect
if [ "$(printf '%.0f' "$pdr")" -lt "80" ]; then
    echo "✅ Attack effective (PDR < 80%)"
else
    echo "⚠️  Attack may be weak (PDR = ${pdr}%)"
fi

echo "========================================="
echo "Full log: $LOG_FILE"
