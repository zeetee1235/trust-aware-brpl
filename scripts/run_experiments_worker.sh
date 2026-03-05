#!/bin/bash
# Worker script for parallel experiment execution
# Usage: ./run_experiments_worker.sh WORKER_ID TOTAL_WORKERS RESULTS_BASE [QUEUE_FILE]
#        ./run_experiments_worker.sh --print-experiments

set -e

PRINT_ONLY=0
if [ "${1:-}" = "--print-experiments" ]; then
    PRINT_ONLY=1
fi

WORKER_ID=${1:-1}
TOTAL_WORKERS=${2:-8}
RESULTS_BASE=${3:-"results/experiments-$(date +%Y%m%d-%H%M%S)"}
QUEUE_FILE=${4:-""}

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_DIR"
WORKER_ENV_ROOT="$PROJECT_DIR/.parallel_worker_env"
WORKER_ENV_DIR="$WORKER_ENV_ROOT/worker${WORKER_ID}"
WORKER_CONFIG_DIR="$WORKER_ENV_DIR/configs"
WORKER_MOTES_DIR="$WORKER_ENV_DIR/motes"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[WORKER-${WORKER_ID}]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WORKER-${WORKER_ID}]${NC} $1"
}

log_error() {
    echo -e "${RED}[WORKER-${WORKER_ID}]${NC} $1"
}

# Cleanup on exit
cleanup_on_exit() {
    log_warn "Cleaning up worker ${WORKER_ID}..."
    pkill -P $$ trust_engine 2>/dev/null || true
    rm -rf "$WORKER_ENV_DIR" 2>/dev/null || true
}

if [ "$PRINT_ONLY" -eq 0 ]; then
    trap cleanup_on_exit EXIT INT TERM
fi

# Configuration (same as original script)
QUICK_PREVIEW=${QUICK_PREVIEW:-1}
SIM_TIME=${SIM_TIME:-600}
ATTACK_RATES=($(seq 0 5 100))
SEEDS=(123456 234567 345678 456789 567890)
INCLUDE_OPTIONAL_SCENARIOS=1
SEND_INTERVAL_SECONDS=${SEND_INTERVAL_SECONDS:-30}
WARMUP_SECONDS=${WARMUP_SECONDS:-120}
CHECKPOINT_TAIL_LINES=${CHECKPOINT_TAIL_LINES:-20}
ENABLE_CHECKPOINT_SUMMARY=${ENABLE_CHECKPOINT_SUMMARY:-0}
COOJA_TIMEOUT=${COOJA_TIMEOUT:-800}
TRUST_ENGINE_STARTUP_WAIT=${TRUST_ENGINE_STARTUP_WAIT:-1}
# Fixed parameter set for this campaign
LAMBDA_SET=(6)
GAMMA_SET=(4)
ATTACK_MODE_SET=(2)  # combined only
SINK_DELTA_SET=(1)
TRUST_ALPHA_SET=(1.0)
TRUST_POLL_MS=${TRUST_POLL_MS:-1000}
SINK_MIN_HOP=${SINK_MIN_HOP:-256}
SINK_TAU=${SINK_TAU:-0}
SINK_LAMBDA_ADV=${SINK_LAMBDA_ADV:-0.01}
SINK_LAMBDA_STAB=${SINK_LAMBDA_STAB:-0.01}
SINK_BETA=${SINK_BETA:-0.1}
SINK_KAPPA=${SINK_KAPPA:-0}
SINK_W1=${SINK_W1:-0.5}
SINK_W2=${SINK_W2:-0.5}
TRUST_ENGINE_ALPHA=${TRUST_ENGINE_ALPHA:-0.4}
TRUST_ENGINE_MISS_THRESHOLD=${TRUST_ENGINE_MISS_THRESHOLD:-2}
TRUST_ENGINE_FWD_DROP_THRESHOLD=${TRUST_ENGINE_FWD_DROP_THRESHOLD:-0.12}
if [ -n "${BLACKLIST_TRUST_THRESHOLD_NORM_SET:-}" ]; then
    BLACKLIST_TRUST_THRESHOLD_NORM_SET=($BLACKLIST_TRUST_THRESHOLD_NORM_SET)
else
    BLACKLIST_TRUST_THRESHOLD_NORM_SET=(0.90)
fi
if [ -n "${BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM_SET:-}" ]; then
    BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM_SET=($BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM_SET)
else
    BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM_SET=(0.95)
fi

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

# Build all experiment configurations
build_experiment_list() {
    local experiments=()
    for topo in "${TOPOLOGIES[@]}"; do
        TOPO_NAME=$(basename "$topo" .csc)
        ATTACKER_NODE_ID="${ATTACKER_NODE_ID:-2}"
        ATTACKER_FROM_CSV="$(get_attacker_id_from_csv "$TOPO_NAME" || true)"
        if [ -n "$ATTACKER_FROM_CSV" ]; then
            ATTACKER_NODE_ID="$ATTACKER_FROM_CSV"
        fi
        
        for scenario_name in $(echo "${!SCENARIOS[@]}" | tr ' ' '\n' | sort); do
            IFS=',' read -r routing attack trust <<< "${SCENARIOS[$scenario_name]}"
            
            for attack_rate in "${ATTACK_RATES[@]}"; do
                if [ "$attack" == "ATTACK" ] && [ "$attack_rate" -eq 0 ]; then
                    continue
                fi
                if [ "$attack" == "NO_ATTACK" ] && [ "$attack_rate" -gt 0 ]; then
                    continue
                fi
                
                if [ "$trust" -eq 1 ] && [ "$attack" == "ATTACK" ]; then
                    for ATTACK_MODE in "${ATTACK_MODE_SET[@]}"; do
                        for SINKHOLE_RANK_DELTA in "${SINK_DELTA_SET[@]}"; do
                            for TRUST_ALPHA in "${TRUST_ALPHA_SET[@]}"; do
                                for TRUST_LAMBDA in "${LAMBDA_SET[@]}"; do
                                    for TRUST_PENALTY_GAMMA in "${GAMMA_SET[@]}"; do
                                        for BLACKLIST_TRUST_THRESHOLD_NORM in "${BLACKLIST_TRUST_THRESHOLD_NORM_SET[@]}"; do
                                            for BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM in "${BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM_SET[@]}"; do
                                                for seed in "${SEEDS[@]}"; do
                                                    experiments+=("$topo|$TOPO_NAME|$scenario_name|$routing|$attack|$trust|$attack_rate|$ATTACK_MODE|$SINKHOLE_RANK_DELTA|$TRUST_ALPHA|$TRUST_LAMBDA|$TRUST_PENALTY_GAMMA|$seed|$ATTACKER_NODE_ID|$BLACKLIST_TRUST_THRESHOLD_NORM|$BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM")
                                                done
                                            done
                                        done
                                    done
                                done
                            done
                        done
                    done
                else
                    for ATTACK_MODE in "${ATTACK_MODE_SET[@]}"; do
                        for seed in "${SEEDS[@]}"; do
                            experiments+=("$topo|$TOPO_NAME|$scenario_name|$routing|$attack|$trust|$attack_rate|$ATTACK_MODE|0|1.0|0|1|$seed|$ATTACKER_NODE_ID|0.90|0.95")
                        done
                    done
                fi
            done
        done
    done
    printf '%s\n' "${experiments[@]}"
}

if [ "$PRINT_ONLY" -eq 1 ]; then
    build_experiment_list
    exit 0
fi

prepare_worker_env() {
    log_info "Preparing isolated worker environment: $WORKER_ENV_DIR"
    rm -rf "$WORKER_ENV_DIR"
    mkdir -p "$WORKER_CONFIG_DIR"
    cp -a "$PROJECT_DIR/motes" "$WORKER_MOTES_DIR"
    ln -s "$PROJECT_DIR/contiki-ng-brpl" "$WORKER_ENV_DIR/contiki-ng-brpl"
}

run_one_experiment() {
    local exp_data="$1"
    IFS='|' read -r topo TOPO_NAME scenario_name routing attack trust attack_rate ATTACK_MODE SINKHOLE_RANK_DELTA TRUST_ALPHA TRUST_LAMBDA TRUST_PENALTY_GAMMA seed ATTACKER_NODE_ID BLACKLIST_TRUST_THRESHOLD_NORM BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM <<< "$exp_data"
    
    if [ "$trust" -eq 1 ] && [ "$attack" == "ATTACK" ]; then
        RUN_NAME="${TOPO_NAME}_${scenario_name}_p${attack_rate}_mode${ATTACK_MODE}_d${SINKHOLE_RANK_DELTA}_a${TRUST_ALPHA}_lam${TRUST_LAMBDA}_gam${TRUST_PENALTY_GAMMA}_bl${BLACKLIST_TRUST_THRESHOLD_NORM}_blc${BLACKLIST_TRUST_CLEAR_THRESHOLD_NORM}_s${seed}"
    else
        RUN_NAME="${TOPO_NAME}_${scenario_name}_p${attack_rate}_mode${ATTACK_MODE}_s${seed}"
    fi
    
    RUN_DIR="$RESULTS_BASE/$RUN_NAME"
    mkdir -p "$RUN_DIR"
    
    log_info "Running: $RUN_NAME"
    
    # Set environment
    export CONTIKI_NG_PATH="$PROJECT_DIR/contiki-ng-brpl"
    export COOJA_PATH="/home/dev/contiki-ng"
    export SERIAL_SOCKET_DISABLE=1
    export JAVA_OPTS="-Xmx4G -Xms2G"
    
    BRPL_MODE=1
    BASE_CONFIG="$topo"
    TEMP_CONFIG="$WORKER_CONFIG_DIR/temp_${RUN_NAME}.csc"
    SIM_TIME_MS=$((SIM_TIME * 1000))
    TRUST_FEEDBACK_FILE="$PROJECT_DIR/$RUN_DIR/trust_feedback.txt"
    
    # Create temporary config
    sed -e "s/<randomseed>[0-9]*<\/randomseed>/<randomseed>$seed<\/randomseed>/g" \
        -e "s/@SIM_TIME_MS@/${SIM_TIME_MS}/g" \
        -e "s/@SIM_TIME_SEC@/${SIM_TIME}/g" \
        -e "s/@TRUST_POLL_MS@/${TRUST_POLL_MS}/g" \
        -e "s|@TRUST_FEEDBACK_PATH@|${TRUST_FEEDBACK_FILE}|g" \
        -e "s/BRPL_MODE=[0-9]/BRPL_MODE=${BRPL_MODE}/g" \
        -e "s/TRUST_ENABLED=[0-9]/TRUST_ENABLED=${trust}/g" \
        -e "s/TRUST_LAMBDA=[0-9][0-9]*/TRUST_LAMBDA=${TRUST_LAMBDA}/g" \
        -e "s/TRUST_PENALTY_GAMMA=[0-9][0-9]*/TRUST_PENALTY_GAMMA=${TRUST_PENALTY_GAMMA}/g" \
        -e "s/TRUST_LAMBDA_CONF=[0-9][0-9]*/TRUST_LAMBDA_CONF=${TRUST_LAMBDA}/g" \
        -e "s/TRUST_PENALTY_GAMMA_CONF=[0-9][0-9]*/TRUST_PENALTY_GAMMA_CONF=${TRUST_PENALTY_GAMMA}/g" \
        -e "s/,PROJECT_CONF_PATH=[^,< ]*//g" \
        -e "s/,PROJECT_CONF_PATH=\\\"[^\\\"]*\\\"//g" \
        -e "s/TRUST_GAMMA=[0-9][0-9]*/TRUST_GAMMA=${TRUST_PENALTY_GAMMA}/g" \
        -e "/TRUST_GAMMA=/! s/TRUST_LAMBDA=${TRUST_LAMBDA}/TRUST_LAMBDA=${TRUST_LAMBDA},TRUST_GAMMA=${TRUST_PENALTY_GAMMA}/g" \
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
    
    log_info "  Using isolated motes directory: $WORKER_MOTES_DIR"
    # Clean build outputs to force recompilation with updated DEFINES
    rm -rf "$WORKER_MOTES_DIR/build/cooja" 2>/dev/null || true
    
    # Cooja will build automatically with the modified commands
    
    # Run simulation
    LOG_DIR="$PROJECT_DIR/$RUN_DIR/logs"
    mkdir -p "$LOG_DIR"
    
    # Start trust_engine only for trust-enabled runs
    TRUST_ENGINE_PID=""
    touch "$TRUST_FEEDBACK_FILE"
    touch "$LOG_DIR/COOJA.testlog"
    if [ "$trust" -eq 1 ]; then
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
    
    # Run Cooja
    timeout "$COOJA_TIMEOUT" java --enable-preview ${JAVA_OPTS} \
        -jar "$COOJA_PATH/tools/cooja/build/libs/cooja.jar" \
        --no-gui \
        --autostart \
        --contiki="$CONTIKI_NG_PATH" \
        --logdir="$LOG_DIR" \
        "$TEMP_CONFIG" > "$PROJECT_DIR/$RUN_DIR/cooja_output.log" 2>&1
    COOJA_EXIT=$?
    
    if [ $COOJA_EXIT -ne 0 ]; then
        log_error "Simulation failed: $RUN_NAME (exit: $COOJA_EXIT)"
        [ -n "$TRUST_ENGINE_PID" ] && kill -9 $TRUST_ENGINE_PID 2>/dev/null || true
        rm -f "$TEMP_CONFIG"
        return 1
    fi
    
    # Stop trust_engine
    if [ -n "$TRUST_ENGINE_PID" ]; then
        for _ in {1..10}; do
            if ! kill -0 $TRUST_ENGINE_PID 2>/dev/null; then
                break
            fi
            sleep 0.5
        done
        kill -9 $TRUST_ENGINE_PID 2>/dev/null || true
        wait $TRUST_ENGINE_PID 2>/dev/null || true
    fi
    
    rm -f "$TEMP_CONFIG"
    log_info "Completed: $RUN_NAME"
    return 0
}

# Main worker execution
log_info "Worker ${WORKER_ID}/${TOTAL_WORKERS} starting..."
log_info "Results directory: $RESULTS_BASE"
prepare_worker_env

# Build experiment list
ALL_EXPERIMENTS=($(build_experiment_list))
TOTAL_EXPERIMENTS=${#ALL_EXPERIMENTS[@]}

log_info "Total experiments in dataset: $TOTAL_EXPERIMENTS"

# Execute experiments from dynamic queue
COMPLETED=0
FAILED=0

if [ -z "$QUEUE_FILE" ]; then
    log_error "QUEUE_FILE is required for dynamic queue mode"
    exit 1
fi

QUEUE_CURSOR_FILE="${QUEUE_FILE}.cursor"
QUEUE_TOTAL_FILE="${QUEUE_FILE}.total"
QUEUE_LOCK_FILE="${QUEUE_FILE}.lock"

if [ ! -f "$QUEUE_FILE" ] || [ ! -f "$QUEUE_CURSOR_FILE" ] || [ ! -f "$QUEUE_TOTAL_FILE" ]; then
    log_error "Queue files missing: $QUEUE_FILE(.cursor/.total)"
    exit 1
fi

pop_next_experiment() {
    local next_idx total line_no exp
    exp=""

    exec 9>>"$QUEUE_LOCK_FILE"
    flock -x 9

    next_idx=$(cat "$QUEUE_CURSOR_FILE" 2>/dev/null || echo 0)
    total=$(cat "$QUEUE_TOTAL_FILE" 2>/dev/null || echo 0)

    if [ "$next_idx" -lt "$total" ]; then
        line_no=$((next_idx + 1))
        exp=$(sed -n "${line_no}p" "$QUEUE_FILE")
        echo $((next_idx + 1)) > "$QUEUE_CURSOR_FILE"
    fi

    flock -u 9
    exec 9>&-

    printf '%s' "$exp"
}

while true; do
    EXP_DATA="$(pop_next_experiment)"
    if [ -z "$EXP_DATA" ]; then
        break
    fi

    if run_one_experiment "$EXP_DATA"; then
        COMPLETED=$((COMPLETED + 1))
    else
        FAILED=$((FAILED + 1))
    fi
    log_info "Progress: done=$((COMPLETED + FAILED)) | Success: $COMPLETED | Failed: $FAILED"
done

log_info "============================================"
log_info "Worker ${WORKER_ID} finished!"
log_info "Completed: $COMPLETED | Failed: $FAILED"
log_info "============================================"
