#!/bin/bash
# Cooja 시뮬레이션 headless 실행 스크립트

set -e

# Contiki-NG 경로 자동 설정
if [ -z "$CONTIKI_NG_PATH" ] || [ "$CONTIKI_NG_PATH" = "/path/to/contiki-ng" ]; then
    export CONTIKI_NG_PATH=/home/dev/contiki-ng
fi

# Contiki-NG 경로 확인
if [ ! -d "$CONTIKI_NG_PATH" ]; then
    echo "Error: CONTIKI_NG_PATH directory not found: $CONTIKI_NG_PATH"
    echo "Set it like: export CONTIKI_NG_PATH=/path/to/contiki-ng"
    exit 1
fi

# 프로젝트 디렉토리
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_DIR"

# 시뮬레이션 파일 확인 (옵션으로 경로 지정 가능)
SIMULATION_FILE="${2:-$PROJECT_DIR/configs/simulation.csc}"
if [ ! -f "$SIMULATION_FILE" ]; then
    echo "Error: $SIMULATION_FILE not found"
    exit 1
fi

# 시뮬레이션 시간 설정 (초 단위)
SIM_TIME_SEC=${1:-600}  # 기본 10분
SIM_TIME_MS=$((SIM_TIME_SEC * 1000))

# 로그 파일
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="COOJA.testlog"
mkdir -p "$LOG_DIR"

echo "============================================"
echo "Running Cooja in Headless Mode"
echo "============================================"
echo "Simulation file: $SIMULATION_FILE"
echo "Simulation time: ${SIM_TIME_SEC}s (${SIM_TIME_MS}ms)"
echo "Log output:      $LOG_DIR/$LOG_FILE"
echo "Cooja path:      $CONTIKI_NG_PATH"
echo ""

# 이전 로그 삭제
if [ -f "$LOG_DIR/$LOG_FILE" ]; then
    echo "Removing old log file..."
    rm -f "$LOG_DIR/$LOG_FILE"
fi

# Force rebuild to honor DEFINES changes
make -C "$PROJECT_DIR/motes" -f Makefile.receiver TARGET=cooja clean >/dev/null || true
make -C "$PROJECT_DIR/motes" -f Makefile.sender TARGET=cooja clean >/dev/null || true
make -C "$PROJECT_DIR/motes" -f Makefile.attacker TARGET=cooja clean >/dev/null || true

# ScriptRunner placeholder 채우기 (시뮬레이션 시간 설정)
SIM_TMP="$PROJECT_DIR/configs/simulation_tmp.csc"
sed \
  -e "s/@SIM_TIME_MS@/${SIM_TIME_MS}/g" \
  -e "s/@SIM_TIME_SEC@/${SIM_TIME_SEC}/g" \
  "$SIMULATION_FILE" > "$SIM_TMP"

echo "Starting simulation..."
echo "(This will take approximately ${SIM_TIME_SEC} seconds)"
echo ""

# Headless 모드로 Cooja 실행
cd "$CONTIKI_NG_PATH"

java --enable-preview -jar tools/cooja/build/libs/cooja.jar \
    --no-gui \
    --autostart \
    --contiki="$CONTIKI_NG_PATH" \
    --logdir="$LOG_DIR" \
    "$SIM_TMP" 2>&1 | tee "$LOG_DIR/cooja_output.log" &

COOJA_PID=$!
START_TS=$(date +%s)
echo "Progress: 0% (0/${SIM_TIME_SEC}s)"
while kill -0 "$COOJA_PID" 2>/dev/null; do
    sleep 2
    NOW_TS=$(date +%s)
    ELAPSED=$((NOW_TS - START_TS))
    if [ "$ELAPSED" -gt "$SIM_TIME_SEC" ]; then
        ELAPSED="$SIM_TIME_SEC"
    fi
    if [ "$SIM_TIME_SEC" -gt 0 ]; then
        PCT=$((ELAPSED * 100 / SIM_TIME_SEC))
    else
        PCT=100
    fi
    printf "\rProgress: %3d%% (%d/%ds)" "$PCT" "$ELAPSED" "$SIM_TIME_SEC"
done
wait "$COOJA_PID"
echo ""

# 실행 결과 확인
if [ -f "$LOG_DIR/$LOG_FILE" ]; then
    echo ""
echo "============================================"
echo "Simulation completed successfully!"
echo "============================================"
echo "Log saved to: $LOG_DIR/$LOG_FILE"
echo "Lines in log: $(wc -l < "$LOG_DIR/$LOG_FILE")"
echo ""

# Auto-parse and store results
RESULTS_DIR="$PROJECT_DIR/results"
RUN_STAMP="$(date +%Y%m%d-%H%M%S)"
RUN_DIR="$RESULTS_DIR/run-$RUN_STAMP"
mkdir -p "$RUN_DIR"

PARSE_OUT="$RUN_DIR/parse_results.txt"
echo "Parsing results..."
python3 "$PROJECT_DIR/tools/parse_results.py" "$LOG_DIR/$LOG_FILE" | tee "$PARSE_OUT"
echo ""

cp -f "$LOG_DIR/$LOG_FILE" "$RUN_DIR/"
cp -f "$LOG_DIR/cooja_output.log" "$RUN_DIR/" 2>/dev/null || true

echo "Results saved to: $RUN_DIR"
echo ""
else
    echo ""
    echo "Warning: Log file not found!"
    echo "Check $LOG_DIR/cooja_output.log for errors"
fi

rm -f "$SIM_TMP"
