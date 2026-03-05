#!/bin/bash
# Comprehensive experiment runner for Trust-Aware BRPL research
# Runs 6 essential + 2 optional scenarios with varying attack rates and seeds

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_DIR"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Cleanup on exit (Ctrl+C, kill, or normal exit)
cleanup_on_exit() {
    log_warn "Cleaning up before exit..."
    # Kill any running trust_engine processes
    pkill trust_engine 2>/dev/null || true
    # Remove temp config files
    rm -f "$PROJECT_DIR/configs/temp_*.csc" 2>/dev/null || true
    log_info "Cleanup done"
}

trap cleanup_on_exit EXIT INT TERM

# Configuration
QUICK_PREVIEW=${QUICK_PREVIEW:-1}  # set to 0 for full run
SIM_TIME=${SIM_TIME:-600}  # default: 10 minutes per simulation
ATTACK_RATES=($(seq 0 5 100))  # Drop percentages (0 for normal scenarios)
SEEDS=(123456 234567 345678 456789 567890)  # default: 5 seeds
INCLUDE_OPTIONAL_SCENARIOS=1  # include 8_brpl_normal_trust for normal + trust
SEND_INTERVAL_SECONDS=${SEND_INTERVAL_SECONDS:-30}
WARMUP_SECONDS=${WARMUP_SECONDS:-120}
PAUSE_BETWEEN_RUNS=${PAUSE_BETWEEN_RUNS:-0}  # set to 1 to confirm each run interactively
CHECKPOINT_TAIL_LINES=${CHECKPOINT_TAIL_LINES:-20}  # number of log lines to show after each run
ENABLE_CHECKPOINT_SUMMARY=${ENABLE_CHECKPOINT_SUMMARY:-0}
COOJA_TIMEOUT=${COOJA_TIMEOUT:-800}
TRUST_ENGINE_STARTUP_WAIT=${TRUST_ENGINE_STARTUP_WAIT:-1}
LAMBDA_SET=(6)
GAMMA_SET=(4)
ATTACK_MODE=${ATTACK_MODE:-0}
ATTACKER_NODE_ID=${ATTACKER_NODE_ID:-2}
SINKHOLE_RANK_DELTA=${SINKHOLE_RANK_DELTA:-1}
ATTACK_MODE_SET=(0 1 2)
SINK_DELTA_SET=(1 2 4)
TRUST_ALPHA_SET=(1.0 0.5)  # 1.0 = gray-only, 0.5 = sink-enabled (combined trust)
TRUST_POLL_MS=${TRUST_POLL_MS:-1000}
SINK_MIN_HOP=${SINK_MIN_HOP:-256}
SINK_TAU=${SINK_TAU:-0}
SINK_LAMBDA_ADV=${SINK_LAMBDA_ADV:-0.01}
SINK_LAMBDA_STAB=${SINK_LAMBDA_STAB:-0.01}
SINK_BETA=${SINK_BETA:-0.1}
SINK_KAPPA=${SINK_KAPPA:-0}
SINK_W1=${SINK_W1:-0.5}
SINK_W2=${SINK_W2:-0.5}
TRUST_ALPHA=${TRUST_ALPHA:-0.5}
TRUST_ENGINE_ALPHA=${TRUST_ENGINE_ALPHA:-0.4}
TRUST_ENGINE_MISS_THRESHOLD=${TRUST_ENGINE_MISS_THRESHOLD:-2}
TRUST_ENGINE_FWD_DROP_THRESHOLD=${TRUST_ENGINE_FWD_DROP_THRESHOLD:-0.12}
BLACKLIST_TRUST_THRESHOLD_NORM=${BLACKLIST_TRUST_THRESHOLD_NORM:-0.90}
BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM=${BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM:-0.95}

# Topology list (override with TOPOLOGIES env var)
# Example: TOPOLOGIES="configs/topologies/T1_S.csc configs/topologies/T3.csc" ./scripts/run_experiments.sh
TOPOLOGIES_DEFAULT=(
    configs/topologies/CLUSTER_S.csc
    configs/topologies/CLUSTER_M.csc
    configs/topologies/CLUSTER_L.csc
    configs/topologies/GRID_S.csc
    configs/topologies/GRID_M.csc
    configs/topologies/GRID_L.csc
    configs/topologies/RING_S.csc
    configs/topologies/RING_M.csc
    configs/topologies/RING_L.csc
)
if [ -n "${TOPOLOGIES:-}" ]; then
    # shellcheck disable=SC2206
    TOPOLOGIES=($TOPOLOGIES)
else
    TOPOLOGIES=("${TOPOLOGIES_DEFAULT[@]}")
fi

if [ "$QUICK_PREVIEW" -eq 1 ]; then
    SIM_TIME=240
    SEEDS=(123456)
    SEND_INTERVAL_SECONDS=10
    WARMUP_SECONDS=10
fi
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RESULTS_BASE="results/experiments-$TIMESTAMP"

mkdir -p "$RESULTS_BASE"

# Cleanup function - remove old temp files and orphaned processes
cleanup_previous_run() {
    log_info "Cleaning up previous run artifacts..."
    
    # Kill any orphaned trust_engine processes
    pkill -9 trust_engine 2>/dev/null || true
    
    # Remove temporary config files
    rm -f "$PROJECT_DIR/configs/temp_*.csc" 2>/dev/null || true
    
    # Clean build directory (will be rebuilt)
    rm -rf "$PROJECT_DIR/motes/build" 2>/dev/null || true
    
    log_info "Cleanup complete"
}

# Run cleanup before starting
cleanup_previous_run

# Scenarios definition: routing,has_attack,trust_enabled
# BRPL-only scenarios
declare -A SCENARIOS=(
    ["2_brpl_normal_notrust"]="BRPL,NO_ATTACK,0"
    ["4_brpl_attack_notrust"]="BRPL,ATTACK,0"
    ["6_brpl_attack_trust"]="BRPL,ATTACK,1"
)

if [ "$INCLUDE_OPTIONAL_SCENARIOS" -eq 1 ]; then
    SCENARIOS["8_brpl_normal_trust"]="BRPL,NO_ATTACK,1"
fi

get_attacker_id_from_csv() {
    local topo_name="$1"
    local topo_csv="configs/topologies/${topo_name}.csv"
    if [ ! -f "$topo_csv" ]; then
        return 1
    fi
    awk -F',' '$4=="attacker"{print $1; exit}' "$topo_csv"
}

summarize_run() {
    local run_dir="$1"
    local log_dir="$run_dir/logs"
    local testlog="$log_dir/COOJA.testlog"
    local exposure="$run_dir/exposure.csv"
    local parent="$run_dir/parent_switch.csv"
    local stats="$run_dir/stats.csv"
    local grep_cmd="grep -n"
    if command -v rg >/dev/null 2>&1; then
        grep_cmd="rg -n"
    fi

    echo ""
    log_info "Run summary checkpoint:"
    if [ -f "$testlog" ]; then
        $grep_cmd "BRPL_PARAMS" "$testlog" | tail -n 3 || true
        $grep_cmd "PARENT_CANDIDATE" "$testlog" | tail -n 2 || true
        echo ""
        echo "Last ${CHECKPOINT_TAIL_LINES} lines of COOJA.testlog:"
        tail -n "$CHECKPOINT_TAIL_LINES" "$testlog" || true
    else
        log_warn "Missing COOJA.testlog in $log_dir"
    fi

    if [ -f "$exposure" ]; then
        echo ""
        echo "Exposure (last row):"
        tail -n 1 "$exposure" || true
    fi
    if [ -f "$parent" ]; then
        echo ""
        echo "Parent switch (last row):"
        tail -n 1 "$parent" || true
    elif [ -f "$stats" ]; then
        echo ""
        echo "Stats (last row):"
        tail -n 1 "$stats" || true
    fi
}

# Progress tracking (account for skipped combos)
count_runs() {
    local total=0
    local scenario_name routing attack trust
    for topo in $TOPOLOGIES; do
        for scenario_name in "${!SCENARIOS[@]}"; do
            IFS=',' read -r routing attack trust <<< "${SCENARIOS[$scenario_name]}"
            for attack_rate in "${ATTACK_RATES[@]}"; do
                if [ "$attack" == "ATTACK" ] && [ "$attack_rate" -eq 0 ]; then
                    continue
                fi
                if [ "$attack" == "NO_ATTACK" ] && [ "$attack_rate" -gt 0 ]; then
                    continue
                fi
                if [ "$trust" -eq 1 ] && [ "$attack" == "ATTACK" ]; then
                    # trust + attack: sweep attack modes + sink delta + trust alpha + lambda/gamma
                    total=$((total + ${#SEEDS[@]} * ${#ATTACK_MODE_SET[@]} * ${#SINK_DELTA_SET[@]} * ${#TRUST_ALPHA_SET[@]} * ${#LAMBDA_SET[@]} * ${#GAMMA_SET[@]}))
                else
                    # no-attack or trust-off
                    total=$((total + ${#SEEDS[@]} * ${#ATTACK_MODE_SET[@]}))
                fi
            done
        done
    done
    echo "$total"
}

TOTAL_RUNS=$(count_runs)
CURRENT_RUN=0

log_info "============================================"
log_info "Trust-Aware BRPL Comprehensive Experiments"
log_info "============================================"
log_info "Total scenarios: ${#SCENARIOS[@]} (BRPL-only)"
log_info "Topologies: ${TOPOLOGIES[*]}"
log_info "Attack rates: ${ATTACK_RATES[@]}"
log_info "Seeds: ${#SEEDS[@]}"
log_info "Total runs: $TOTAL_RUNS"
log_info "Checkpoint summary: $ENABLE_CHECKPOINT_SUMMARY"
log_info "Results directory: $RESULTS_BASE"
log_info ""

render_progress() {
    local current="$1"
    local total="$2"
    local width=40
    local percent=$(( current * 100 / total ))
    local filled=$(( current * width / total ))
    local empty=$(( width - filled ))
    local bar=""
    for ((i=0; i<filled; i++)); do bar+="#"; done
    for ((i=0; i<empty; i++)); do bar+="-"; done
    printf "\r[%s] %3d%% (%d/%d)" "$bar" "$percent" "$current" "$total"
}

run_one() {
            # Set environment - Use submodule for build, system Cooja for simulation
            export CONTIKI_NG_PATH="$PROJECT_DIR/contiki-ng-brpl"
            export COOJA_PATH="/home/dev/contiki-ng"
            export SERIAL_SOCKET_DISABLE=1
            export JAVA_OPTS="-Xmx4G -Xms2G"
            
            # Prepare simulation config
            if [ "$routing" == "BRPL" ]; then
                BRPL_MODE=1
            else
                BRPL_MODE=0
            fi
            
            # Select config file (use topologies/*.csc as base)
            BASE_CONFIG="$topo"
            
            # Determine BRPL_MODE (BRPL-only)
            BRPL_MODE=1
            
            # Create temporary config with all modifications
            TEMP_CONFIG="$PROJECT_DIR/configs/temp_${RUN_NAME}.csc"
            SIM_TIME_MS=$((SIM_TIME * 1000))
            TRUST_FEEDBACK_FILE="$PROJECT_DIR/$RUN_DIR/trust_feedback.txt"

            # Replace all parameters
            TRUST_LAMBDA=${TRUST_LAMBDA:-0}
            TRUST_GAMMA=${TRUST_GAMMA:-1}
            ATTACK_MODE=${ATTACK_MODE:-0}
            ATTACKER_NODE_ID=${ATTACKER_NODE_ID:-2}
            SINKHOLE_RANK_DELTA=${SINKHOLE_RANK_DELTA:-1}
            TRUST_ALPHA=${TRUST_ALPHA:-0.5}
            sed -e "s/<randomseed>[0-9]*<\/randomseed>/<randomseed>$seed<\/randomseed>/g" \
                -e "s/@SIM_TIME_MS@/${SIM_TIME_MS}/g" \
                -e "s/@SIM_TIME_SEC@/${SIM_TIME}/g" \
                -e "s/@TRUST_POLL_MS@/${TRUST_POLL_MS}/g" \
                -e "s|@TRUST_FEEDBACK_PATH@|${TRUST_FEEDBACK_FILE}|g" \
                -e "s/BRPL_MODE=[0-9]/BRPL_MODE=${BRPL_MODE}/g" \
                -e "s/TRUST_ENABLED=[0-9]/TRUST_ENABLED=${trust}/g" \
                -e "s/TRUST_LAMBDA=[0-9][0-9]*/TRUST_LAMBDA=${TRUST_LAMBDA}/g" \
                -e "s/TRUST_PENALTY_GAMMA=[0-9][0-9]*/TRUST_PENALTY_GAMMA=${TRUST_PENALTY_GAMMA:-1}/g" \
                -e "s/TRUST_LAMBDA_CONF=[0-9][0-9]*/TRUST_LAMBDA_CONF=${TRUST_LAMBDA}/g" \
                -e "s/TRUST_PENALTY_GAMMA_CONF=[0-9][0-9]*/TRUST_PENALTY_GAMMA_CONF=${TRUST_PENALTY_GAMMA:-1}/g" \
                -e "s/,PROJECT_CONF_PATH=[^,< ]*//g" \
                -e "s/,PROJECT_CONF_PATH=\\\"[^\\\"]*\\\"//g" \
                -e "s/TRUST_GAMMA=[0-9][0-9]*/TRUST_GAMMA=${TRUST_GAMMA}/g" \
                -e "/TRUST_GAMMA=/! s/TRUST_LAMBDA=${TRUST_LAMBDA}/TRUST_LAMBDA=${TRUST_LAMBDA},TRUST_GAMMA=${TRUST_GAMMA}/g" \
                -e "s/ATTACK_MODE=[0-9][0-9]*/ATTACK_MODE=${ATTACK_MODE}/g" \
                -e "s/ATTACKER_NODE_ID=[0-9][0-9]*/ATTACKER_NODE_ID=${ATTACKER_NODE_ID}/g" \
                -e "s/SINKHOLE_RANK_DELTA=[0-9][0-9]*/SINKHOLE_RANK_DELTA=${SINKHOLE_RANK_DELTA}/g" \
                -e "s/ATTACK_DROP_PCT=[0-9][0-9]*/ATTACK_DROP_PCT=${attack_rate}/g" \
                -e "/ATTACK_MODE=/! s/ATTACK_DROP_PCT=${attack_rate}/ATTACK_DROP_PCT=${attack_rate},ATTACK_MODE=${ATTACK_MODE}/g" \
                -e "s/BLACKLIST_TRUST_THRESHOLD_NORM=[0-9.]\\+/BLACKLIST_TRUST_THRESHOLD_NORM=${BLACKLIST_TRUST_THRESHOLD_NORM}/g" \
                -e "s/BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM=[0-9.]\\+/BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM=${BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM}/g" \
                -e "s/SEND_INTERVAL_SECONDS=[0-9][0-9]*/SEND_INTERVAL_SECONDS=${SEND_INTERVAL_SECONDS}/g" \
                -e "s/WARMUP_SECONDS=[0-9][0-9]*/WARMUP_SECONDS=${WARMUP_SECONDS}/g" \
                "$PROJECT_DIR/$BASE_CONFIG" > "$TEMP_CONFIG"
            python3 - <<PY
import re
from pathlib import Path

path = Path("$TEMP_CONFIG")
text = path.read_text()

def fix_defines(match):
    defines = match.group(2)
    if "ATTACK_MODE=" not in defines:
        defines += f",ATTACK_MODE=${ATTACK_MODE}"
    if "ATTACKER_NODE_ID=" not in defines:
        defines += f",ATTACKER_NODE_ID=${ATTACKER_NODE_ID}"
    if "TRUST_ENABLED=" not in defines:
        defines += f",TRUST_ENABLED=${trust}"
    if "BLACKLIST_TRUST_THRESHOLD_NORM=" not in defines:
        defines += f",BLACKLIST_TRUST_THRESHOLD_NORM=${BLACKLIST_TRUST_THRESHOLD_NORM}"
    if "BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM=" not in defines:
        defines += f",BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM=${BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM}"
    return match.group(1) + defines

pattern = re.compile(r'(DEFINES=)([^"<]*)')
lines = []
for line in text.splitlines():
    if "DEFINES=" in line:
        line = pattern.sub(fix_defines, line, count=1)
    lines.append(line)
path.write_text("\\n".join(lines) + "\\n")
PY

            # Disable SerialSocketServer for headless runs (sandbox/network restrictions)
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
            
            # CRITICAL: Delete entire build directory to force full recompilation
            log_info "  Deleting build directory for clean slate..."
            rm -rf motes/build 2>/dev/null || true
            
            # Run simulation
            LOG_DIR="$PROJECT_DIR/$RUN_DIR/logs"
            mkdir -p "$LOG_DIR"
            
            # Start trust_engine only for trust-enabled runs
            TRUST_ENGINE_PID=""
            touch "$TRUST_FEEDBACK_FILE"
            touch "$LOG_DIR/COOJA.testlog"  # Pre-create log file for --follow mode
            if [ "$trust" -eq 1 ]; then
                log_info "  Starting trust_engine in real-time mode..."
                tools/trust_engine/target/release/trust_engine \
                    --input "$LOG_DIR/COOJA.testlog" \
                    --output "$TRUST_FEEDBACK_FILE" \
                    --metrics-out "$PROJECT_DIR/$RUN_DIR/trust_metrics.csv" \
                    --blacklist-out "$PROJECT_DIR/$RUN_DIR/blacklist.csv" \
                    --exposure-out "$PROJECT_DIR/$RUN_DIR/exposure.csv" \
                    --parent-out "$PROJECT_DIR/$RUN_DIR/parent_switch.csv" \
                    --stats-out "$PROJECT_DIR/$RUN_DIR/stats.csv" \
                    --final-out "$PROJECT_DIR/$RUN_DIR/trust_final.log" \
                    --stats-interval 200 \
                    --metric ewma \
                    --alpha "$TRUST_ENGINE_ALPHA" \
                    --ewma-min 0.7 \
                    --sink-min-hop "$SINK_MIN_HOP" \
                    --sink-tau "$SINK_TAU" \
                    --sink-lambda-adv "$SINK_LAMBDA_ADV" \
                    --sink-lambda-stab "$SINK_LAMBDA_STAB" \
                    --sink-beta "$SINK_BETA" \
                    --sink-kappa "$SINK_KAPPA" \
                    --sink-w1 "$SINK_W1" \
                    --sink-w2 "$SINK_W2" \
                    --trust-alpha "$TRUST_ALPHA" \
                --miss-threshold "$TRUST_ENGINE_MISS_THRESHOLD" \
                --forwarders-only \
                --fwd-drop-threshold "$TRUST_ENGINE_FWD_DROP_THRESHOLD" \
                --attacker-id "$ATTACKER_NODE_ID" \
                --follow > "$PROJECT_DIR/$RUN_DIR/trust_engine.log" 2>&1 &
                TRUST_ENGINE_PID=$!
                sleep "$TRUST_ENGINE_STARTUP_WAIT"
            fi
            
            timeout "$COOJA_TIMEOUT" java --enable-preview ${JAVA_OPTS} \
                -jar "$COOJA_PATH/tools/cooja/build/libs/cooja.jar" \
                --no-gui \
                --autostart \
                --contiki="$CONTIKI_NG_PATH" \
                --logdir="$LOG_DIR" \
                "$TEMP_CONFIG" > "$PROJECT_DIR/$RUN_DIR/cooja_output.log" 2>&1
            COOJA_EXIT=$?
            
            if [ $COOJA_EXIT -ne 0 ]; then
                log_error "Simulation failed for $RUN_NAME (exit code: $COOJA_EXIT)"
                [ -n "$TRUST_ENGINE_PID" ] && kill -9 $TRUST_ENGINE_PID 2>/dev/null || true
                rm -f "$TEMP_CONFIG"
                return
            fi
            
            # Stop trust_engine (allow graceful exit after SIMULATION_FINISHED)
            if [ -n "$TRUST_ENGINE_PID" ]; then
                for _ in {1..10}; do
                    if ! kill -0 $TRUST_ENGINE_PID 2>/dev/null; then
                        break
                    fi
                    sleep 0.5
                done
                if kill -0 $TRUST_ENGINE_PID 2>/dev/null; then
                    kill $TRUST_ENGINE_PID 2>/dev/null || true
                    sleep 1
                    if kill -0 $TRUST_ENGINE_PID 2>/dev/null; then
                        kill -9 $TRUST_ENGINE_PID 2>/dev/null || true
                    fi
                fi
                wait $TRUST_ENGINE_PID 2>/dev/null || true
                log_info "  Trust engine stopped"
            fi
            
            # Clean up temp config
            rm -f "$TEMP_CONFIG"
            
            # Parse results is handled by trust_engine outputs only
            if [ -f "$LOG_DIR/COOJA.testlog" ]; then
                log_info "  Logs captured: $LOG_DIR/COOJA.testlog"
            fi
            
            log_info "  Completed: $RUN_NAME"
            if [ "$ENABLE_CHECKPOINT_SUMMARY" -eq 1 ]; then
                summarize_run "$RUN_DIR"
            fi
            if [ "$PAUSE_BETWEEN_RUNS" -eq 1 ]; then
                echo ""
                read -r -p "Press Enter to continue..." _
            fi
            echo ""
}

# Build if needed
if [ ! -f "motes/build/cooja/receiver_root.cooja" ]; then
    log_info "Building motes..."
    if [ -f "scripts/setup_env.sh" ]; then
        source scripts/setup_env.sh
    fi
    if [ -f "scripts/build.sh" ]; then
        ./scripts/build.sh
    else
        log_warn "scripts/build.sh not found; relying on on-demand builds in Cooja."
    fi
fi

# Build trust_engine if needed
if [ ! -f "tools/trust_engine/target/release/trust_engine" ]; then
    log_info "Building trust_engine..."
    cd tools/trust_engine
    cargo build --release
    cd "$PROJECT_DIR"
fi

# Run experiments
    for topo in "${TOPOLOGIES[@]}"; do
    TOPO_NAME=$(basename "$topo" .csc)
    ATTACKER_NODE_ID="${ATTACKER_NODE_ID:-2}"
    ATTACKER_FROM_CSV="$(get_attacker_id_from_csv "$TOPO_NAME" || true)"
    if [ -n "$ATTACKER_FROM_CSV" ]; then
        ATTACKER_NODE_ID="$ATTACKER_FROM_CSV"
    else
        log_warn "No attacker node found in configs/topologies/${TOPO_NAME}.csv; using ATTACKER_NODE_ID=$ATTACKER_NODE_ID"
    fi
    for scenario_name in $(echo "${!SCENARIOS[@]}" | tr ' ' '\n' | sort); do
        IFS=',' read -r routing attack trust <<< "${SCENARIOS[$scenario_name]}"
        
        for attack_rate in "${ATTACK_RATES[@]}"; do
            # Skip attack scenarios when attack_rate=0
            if [ "$attack" == "ATTACK" ] && [ "$attack_rate" -eq 0 ]; then
                continue
            fi
            # Skip non-attack scenarios when attack_rate>0
            if [ "$attack" == "NO_ATTACK" ] && [ "$attack_rate" -gt 0 ]; then
                continue
            fi
            
            if [ "$trust" -eq 1 ] && [ "$attack" == "ATTACK" ]; then
                for ATTACK_MODE in "${ATTACK_MODE_SET[@]}"; do
                    for SINKHOLE_RANK_DELTA in "${SINK_DELTA_SET[@]}"; do
                        for TRUST_ALPHA in "${TRUST_ALPHA_SET[@]}"; do
                            for TRUST_LAMBDA in "${LAMBDA_SET[@]}"; do
                                for TRUST_PENALTY_GAMMA in "${GAMMA_SET[@]}"; do
                                    for seed in "${SEEDS[@]}"; do
                                        CURRENT_RUN=$((CURRENT_RUN + 1))
                                        PROGRESS=$((CURRENT_RUN * 100 / TOTAL_RUNS))
                                        render_progress "$CURRENT_RUN" "$TOTAL_RUNS"
                                        
                                        RUN_NAME="${TOPO_NAME}_${scenario_name}_p${attack_rate}_mode${ATTACK_MODE}_d${SINKHOLE_RANK_DELTA}_a${TRUST_ALPHA}_lam${TRUST_LAMBDA}_gam${TRUST_PENALTY_GAMMA}_s${seed}"
                                        RUN_DIR="$RESULTS_BASE/$RUN_NAME"
                                        mkdir -p "$RUN_DIR"
                                        
                                        log_info "[$CURRENT_RUN/$TOTAL_RUNS] ${PROGRESS}% - Running: $RUN_NAME"
                                        log_info "  Topology: $TOPO_NAME | Routing: $routing | Attack: ${attack_rate}% | Trust: $trust | Mode: ${ATTACK_MODE} | Delta: ${SINKHOLE_RANK_DELTA} | Alpha: ${TRUST_ALPHA} | Lambda: ${TRUST_LAMBDA} | Gamma: ${TRUST_PENALTY_GAMMA} | Seed: $seed"
                                        
                                        run_one
                                    done
                                done
                            done
                        done
                    done
                done
            else
                for ATTACK_MODE in "${ATTACK_MODE_SET[@]}"; do
                    for seed in "${SEEDS[@]}"; do
                        CURRENT_RUN=$((CURRENT_RUN + 1))
                        PROGRESS=$((CURRENT_RUN * 100 / TOTAL_RUNS))
                        render_progress "$CURRENT_RUN" "$TOTAL_RUNS"
                        
                        RUN_NAME="${TOPO_NAME}_${scenario_name}_p${attack_rate}_mode${ATTACK_MODE}_s${seed}"
                        RUN_DIR="$RESULTS_BASE/$RUN_NAME"
                        mkdir -p "$RUN_DIR"
                        
                        log_info "[$CURRENT_RUN/$TOTAL_RUNS] ${PROGRESS}% - Running: $RUN_NAME"
                        log_info "  Topology: $TOPO_NAME | Routing: $routing | Attack: ${attack_rate}% | Trust: $trust | Mode: ${ATTACK_MODE} | Seed: $seed"
                        
                        TRUST_LAMBDA=0
                        TRUST_PENALTY_GAMMA=1
                        TRUST_ALPHA=1.0
                        run_one
                    done
                done
            fi
        done  # attack rate loop
    done  # scenario loop
done  # topology loop

log_info "============================================"
log_info "All experiments completed!"
log_info "============================================"
echo ""
log_info "Results saved to: $RESULTS_BASE"
log_info "Summary file: (disabled; trust_engine outputs in each run dir)"
log_info ""
log_info "Next steps:"
log_info "  1. Use trust_engine outputs (exposure.csv / parent_switch.csv / stats.csv)"
log_info "  2. Check docs/report/ for figures"
log_info ""
