#!/bin/bash
# Cooja 시뮬레이션 (JVM 크래시 완화 버전)
set -e

# JVM 메모리 설정
export JAVA_OPTS="-Xmx4G -Xms2G"

# SerialSocketServer 비활성화 (headless 모드 안정성)
export SERIAL_SOCKET_DISABLE=1

# Native access 경고 억제
JAVA_NATIVE_ACCESS="--enable-native-access=ALL-UNNAMED"

# 기존 run_simulation.sh 호출
exec "$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )/run_simulation.sh" "$@"
