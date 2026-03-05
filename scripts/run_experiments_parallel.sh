#!/bin/bash
# Parallel experiment runner - launches workers to run experiments via dynamic queue
# Each worker runs an independent Cooja instance

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_DIR"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[MAIN]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[MAIN]${NC} $1"
}

log_error() {
    echo -e "${RED}[MAIN]${NC} $1"
}

# Configuration
NUM_WORKERS=${NUM_WORKERS:-8}
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RESULTS_BASE="results/experiments-$TIMESTAMP"
WORKER_LOG_DIR="$RESULTS_BASE/worker_logs"
QUEUE_FILE="$RESULTS_BASE/queue_all.txt"
QUEUE_CURSOR_FILE="$QUEUE_FILE.cursor"
QUEUE_TOTAL_FILE="$QUEUE_FILE.total"
QUEUE_LOCK_FILE="$QUEUE_FILE.lock"

mkdir -p "$RESULTS_BASE"
mkdir -p "$WORKER_LOG_DIR"

log_info "============================================"
log_info "Parallel Experiment Runner (Dynamic Queue)"
log_info "============================================"
log_info "Workers: $NUM_WORKERS"
log_info "Results directory: $RESULTS_BASE"
log_info "Worker logs: $WORKER_LOG_DIR"
log_info "Queue file: $QUEUE_FILE"
log_info ""

# Build dependencies first
log_info "Checking dependencies..."

# Build motes if needed
if [ ! -f "motes/build/cooja/receiver_root.cooja" ]; then
    log_info "Building motes before starting workers..."
    if [ -f "scripts/setup_env.sh" ]; then
        source scripts/setup_env.sh
    fi
    if [ -f "scripts/build.sh" ]; then
        ./scripts/build.sh || {
            log_error "Failed to build motes"
            exit 1
        }
    else
        # Try direct make build
        log_info "Using direct make build..."
        export CONTIKI_NG_PATH="$PROJECT_DIR/contiki-ng-brpl"
        cd motes
        make -f Makefile.receiver TARGET=cooja && \
        make -f Makefile.sender TARGET=cooja && \
        make -f Makefile.attacker TARGET=cooja || {
            log_error "Failed to build motes"
            exit 1
        }
        cd "$PROJECT_DIR"
    fi
else
    log_info "Motes already built"
fi

# Build trust_engine if needed
if [ ! -f "tools/trust_engine/target/release/trust_engine" ]; then
    log_info "Building trust_engine..."
    cd tools/trust_engine
    cargo build --release
    cd "$PROJECT_DIR"
else
    log_info "trust_engine already built"
fi

# Cleanup previous runs
log_info "Cleaning up previous artifacts..."
pkill -9 trust_engine 2>/dev/null || true
rm -f "$PROJECT_DIR/configs/temp_*.csc" 2>/dev/null || true
rm -rf "$PROJECT_DIR/motes/build_worker"* 2>/dev/null || true

log_info ""
log_info "============================================"
log_info "Launching $NUM_WORKERS parallel workers..."
log_info "============================================"

# Build dynamic queue once from worker's experiment builder
log_info "Building dynamic queue..."
bash "$PROJECT_DIR/scripts/run_experiments_worker.sh" --print-experiments > "$QUEUE_FILE"
TOTAL_QUEUE=$(wc -l < "$QUEUE_FILE")
echo "0" > "$QUEUE_CURSOR_FILE"
echo "$TOTAL_QUEUE" > "$QUEUE_TOTAL_FILE"
touch "$QUEUE_LOCK_FILE"
log_info "Queue ready: $TOTAL_QUEUE experiments"

# Array to store worker PIDs
declare -a WORKER_PIDS=()

# Launch workers
for worker_id in $(seq 1 $NUM_WORKERS); do
    WORKER_LOG="$WORKER_LOG_DIR/worker_${worker_id}.log"
    log_info "Starting Worker $worker_id (log: $WORKER_LOG)"
    
    # Launch worker in background
    bash "$PROJECT_DIR/scripts/run_experiments_worker.sh" \
        "$worker_id" \
        "$NUM_WORKERS" \
        "$RESULTS_BASE" \
        "$QUEUE_FILE" \
        > "$WORKER_LOG" 2>&1 &
    
    WORKER_PID=$!
    WORKER_PIDS[$worker_id]=$WORKER_PID
    
    log_info "Worker $worker_id started (PID: $WORKER_PID)"
    
    # Small delay to avoid resource contention during startup
    sleep 2
done

log_info ""
log_info "All workers launched! PIDs: ${WORKER_PIDS[@]}"
log_info ""
log_info "============================================"
log_info "Monitoring workers..."
log_info "============================================"
log_info "Press Ctrl+C to stop all workers and exit"
log_info ""

# Cleanup function for graceful shutdown
cleanup_workers() {
    log_warn ""
    log_warn "Stopping all workers..."
    for worker_id in $(seq 1 $NUM_WORKERS); do
        pid=${WORKER_PIDS[$worker_id]}
        if [ -n "$pid" ] && kill -0 $pid 2>/dev/null; then
            log_warn "Stopping Worker $worker_id (PID: $pid)"
            kill $pid 2>/dev/null || true
        fi
    done
    
    # Wait a bit for graceful shutdown
    sleep 2
    
    # Force kill if still running
    for worker_id in $(seq 1 $NUM_WORKERS); do
        pid=${WORKER_PIDS[$worker_id]}
        if [ -n "$pid" ] && kill -0 $pid 2>/dev/null; then
            log_warn "Force killing Worker $worker_id (PID: $pid)"
            kill -9 $pid 2>/dev/null || true
        fi
    done
    
    # Cleanup orphaned processes and temp files
    pkill -9 trust_engine 2>/dev/null || true
    rm -f "$PROJECT_DIR/configs/temp_*.csc" 2>/dev/null || true
    rm -rf "$PROJECT_DIR/motes/build_worker"* 2>/dev/null || true
    
    log_info "Cleanup complete"
}

trap cleanup_workers EXIT INT TERM

# Monitor workers
ACTIVE_WORKERS=$NUM_WORKERS
CHECK_INTERVAL=10

while [ $ACTIVE_WORKERS -gt 0 ]; do
    sleep $CHECK_INTERVAL
    
    ACTIVE_WORKERS=0
    for worker_id in $(seq 1 $NUM_WORKERS); do
        pid=${WORKER_PIDS[$worker_id]}
        if [ -n "$pid" ] && kill -0 $pid 2>/dev/null; then
            ACTIVE_WORKERS=$((ACTIVE_WORKERS + 1))
        fi
    done
    
    if [ $ACTIVE_WORKERS -gt 0 ]; then
        CURSOR=$(cat "$QUEUE_CURSOR_FILE" 2>/dev/null || echo 0)
        TOTAL=$(cat "$QUEUE_TOTAL_FILE" 2>/dev/null || echo 0)
        if [ "$TOTAL" -gt 0 ]; then
            PCT=$(( CURSOR * 100 / TOTAL ))
        else
            PCT=0
        fi
        echo -ne "\r${CYAN}[MAIN]${NC} Active workers: $ACTIVE_WORKERS/$NUM_WORKERS | Queue: $CURSOR/$TOTAL (${PCT}%) | Elapsed: $(( $(date +%s) - $(stat -c %Y "$RESULTS_BASE") ))s    "
    fi
done

log_info ""
log_info "============================================"
log_info "All workers completed!"
log_info "============================================"

# Collect results summary
log_info ""
log_info "Results summary:"
TOTAL_RUNS=$(find "$RESULTS_BASE" -mindepth 1 -maxdepth 1 -type d ! -name "worker_logs" | wc -l)
log_info "  Total experiment runs: $TOTAL_RUNS"
log_info "  Results directory: $RESULTS_BASE"
log_info "  Worker logs: $WORKER_LOG_DIR"

# Check for failures
log_info ""
log_info "Checking worker logs for errors..."
for worker_id in $(seq 1 $NUM_WORKERS); do
    WORKER_LOG="$WORKER_LOG_DIR/worker_${worker_id}.log"
    if [ -f "$WORKER_LOG" ]; then
        FAILED_COUNT=$(grep -c "Simulation failed" "$WORKER_LOG" || true)
        COMPLETED_COUNT=$(grep -c "Completed:" "$WORKER_LOG" || true)
        log_info "  Worker $worker_id: $COMPLETED_COUNT completed, $FAILED_COUNT failed"
    fi
done

log_info ""
log_info "============================================"
log_info "Next steps:"
log_info "  1. Check worker logs: $WORKER_LOG_DIR/worker_*.log"
log_info "  2. Analyze results: scripts/analyze_results.R"
log_info "  3. Review experiment outputs in: $RESULTS_BASE"
log_info "============================================"
