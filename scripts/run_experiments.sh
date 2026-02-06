#!/bin/bash
# Comprehensive experiment runner for Trust-Aware BRPL research
# Runs 6 essential + 2 optional scenarios with varying attack rates and seeds

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_DIR"

# Configuration
QUICK_PREVIEW=1  # set to 0 for full run
SIM_TIME=600  # default: 10 minutes per simulation
ATTACK_RATES=(0 30 50 70)  # Drop percentages (0 for normal scenarios)
SEEDS=(123456 234567 345678 456789 567890)  # default: 5 seeds
INCLUDE_OPTIONAL_SCENARIOS=0  # set to 1 to include 7/8 (Trust ON, no attack)
SEND_INTERVAL_SECONDS=30
WARMUP_SECONDS=120

# Topology list (override with TOPOLOGIES env var)
# Example: TOPOLOGIES="configs/topologies/T1_S.csc configs/topologies/T3.csc" ./scripts/run_experiments.sh
TOPOLOGIES_DEFAULT=$(ls configs/topologies/*.csc 2>/dev/null | tr '\n' ' ')
TOPOLOGIES="${TOPOLOGIES:-$TOPOLOGIES_DEFAULT}"

if [ "$QUICK_PREVIEW" -eq 1 ]; then
    SIM_TIME=240
    SEEDS=(123456)
    SEND_INTERVAL_SECONDS=10
    WARMUP_SECONDS=10
fi
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RESULTS_BASE="results/experiments-$TIMESTAMP"

mkdir -p "$RESULTS_BASE"

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

# Summary file
SUMMARY_FILE="$RESULTS_BASE/experiment_summary.csv"
echo "scenario,routing,attack_rate,trust,seed,pdr,avg_delay_ms,tx,rx,lost" > "$SUMMARY_FILE"

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
                total=$((total + ${#SEEDS[@]}))
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
log_info "Topologies: $TOPOLOGIES"
log_info "Attack rates: ${ATTACK_RATES[@]}"
log_info "Seeds: ${#SEEDS[@]}"
log_info "Total runs: $TOTAL_RUNS"
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
for topo in $TOPOLOGIES; do
    TOPO_NAME=$(basename "$topo" .csc)
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
            
            for seed in "${SEEDS[@]}"; do
                CURRENT_RUN=$((CURRENT_RUN + 1))
                PROGRESS=$((CURRENT_RUN * 100 / TOTAL_RUNS))
                render_progress "$CURRENT_RUN" "$TOTAL_RUNS"
                
                RUN_NAME="${TOPO_NAME}_${scenario_name}_p${attack_rate}_s${seed}"
                RUN_DIR="$RESULTS_BASE/$RUN_NAME"
                mkdir -p "$RUN_DIR"
                
                log_info "[$CURRENT_RUN/$TOTAL_RUNS] ${PROGRESS}% - Running: $RUN_NAME"
                log_info "  Topology: $TOPO_NAME | Routing: $routing | Attack: ${attack_rate}% | Trust: $trust | Seed: $seed"
            
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
            sed -e "s/<randomseed>[0-9]*<\/randomseed>/<randomseed>$seed<\/randomseed>/g" \
                -e "s/@SIM_TIME_MS@/${SIM_TIME_MS}/g" \
                -e "s/@SIM_TIME_SEC@/${SIM_TIME}/g" \
                -e "s|@TRUST_FEEDBACK_PATH@|${TRUST_FEEDBACK_FILE}|g" \
                -e "s/BRPL_MODE=[0-9]/BRPL_MODE=${BRPL_MODE}/g" \
                -e "s/TRUST_ENABLED=[0-9]/TRUST_ENABLED=${trust}/g" \
                -e "s/ATTACK_DROP_PCT=[0-9][0-9]*/ATTACK_DROP_PCT=${attack_rate}/g" \
                -e "s/SEND_INTERVAL_SECONDS=[0-9][0-9]*/SEND_INTERVAL_SECONDS=${SEND_INTERVAL_SECONDS}/g" \
                -e "s/WARMUP_SECONDS=[0-9][0-9]*/WARMUP_SECONDS=${WARMUP_SECONDS}/g" \
                "$PROJECT_DIR/$BASE_CONFIG" > "$TEMP_CONFIG"

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
            
            # Start trust_engine in background if trust is enabled
            TRUST_ENGINE_PID=""
            if [ "$trust" -eq 1 ]; then
                log_info "  Starting trust_engine in real-time mode..."
                touch "$TRUST_FEEDBACK_FILE"
                touch "$LOG_DIR/COOJA.testlog"  # Pre-create log file for --follow mode
                tools/trust_engine/target/release/trust_engine \
                    --input "$LOG_DIR/COOJA.testlog" \
                    --output "$TRUST_FEEDBACK_FILE" \
                    --metrics-out "$PROJECT_DIR/$RUN_DIR/trust_metrics.csv" \
                    --blacklist-out "$PROJECT_DIR/$RUN_DIR/blacklist.csv" \
                    --metric ewma \
                    --alpha 0.2 \
                    --ewma-min 0.7 \
                    --miss-threshold 5 \
                    --forwarders-only \
                    --fwd-drop-threshold 0.2 \
                    --follow > "$PROJECT_DIR/$RUN_DIR/trust_engine.log" 2>&1 &
                TRUST_ENGINE_PID=$!
                sleep 2
            fi
            
            timeout 800 java --enable-preview ${JAVA_OPTS} \
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
                continue
            fi
            
            # Stop trust_engine if it was running
            if [ -n "$TRUST_ENGINE_PID" ]; then
                sleep 2
                kill $TRUST_ENGINE_PID 2>/dev/null || true
                sleep 1
                kill -9 $TRUST_ENGINE_PID 2>/dev/null || true
                wait $TRUST_ENGINE_PID 2>/dev/null || true
                log_info "  Trust engine stopped"
            fi
            
            # Clean up temp config
            rm -f "$TEMP_CONFIG"
            
            # Parse results
            if [ -f "$LOG_DIR/COOJA.testlog" ]; then
                python3 tools/parse_results.py "$LOG_DIR/COOJA.testlog" > "$RUN_DIR/analysis.txt" 2>&1 || true
                
                # Extract metrics for summary
                PDR=$(grep "Overall:.*PDR=" "$RUN_DIR/analysis.txt" | sed -n 's/.*PDR=\s*\([0-9.]*\)%.*/\1/p' || echo "0")
                AVG_DELAY=$(grep "Average:" "$RUN_DIR/analysis.txt" | awk '{print $2}' || echo "0")
                TX=$(grep "Overall:.*TX=" "$RUN_DIR/analysis.txt" | sed -n 's/.*TX=\s*\([0-9]*\).*/\1/p' || echo "0")
                RX=$(grep "Overall:.*RX=" "$RUN_DIR/analysis.txt" | sed -n 's/.*RX=\s*\([0-9]*\).*/\1/p' || echo "0")
                LOST=$((TX - RX))
                
                echo "$scenario_name,$routing,$attack_rate,$trust,$seed,$PDR,$AVG_DELAY,$TX,$RX,$LOST" >> "$SUMMARY_FILE"
                
                log_info "  Results: PDR=${PDR}% | Delay=${AVG_DELAY}ms | TX=$TX | RX=$RX"
            fi
            
            log_info "  Completed: $RUN_NAME"
            echo ""
            done
        done
    done
done

log_info "============================================"
log_info "All experiments completed!"
log_info "============================================"
echo ""
log_info "Results saved to: $RESULTS_BASE"
log_info "Summary file: $SUMMARY_FILE"
log_info ""
log_info "Next steps:"
log_info "  1. Run R analysis: Rscript scripts/analyze_results.R $RESULTS_BASE"
log_info "  2. Check docs/report/ for figures"
log_info ""
