#!/bin/bash
# Source this file to set up environment for TA-BRPL

export JAVA_HOME=$(dirname $(dirname $(readlink -f $(which java))))
export JAVA_OPTS="-Xmx4G -Xms2G"
export CONTIKI_NG_PATH="$PWD/contiki-ng-brpl"
export SERIAL_SOCKET_DISABLE=1

# Check for COOJA_PATH
if [ -z "$COOJA_PATH" ]; then
    if [ -f "$HOME/contiki-ng/tools/cooja/build/libs/cooja.jar" ]; then
        export COOJA_PATH="$HOME/contiki-ng"
    elif [ -f "/home/dev/contiki-ng/tools/cooja/build/libs/cooja.jar" ]; then
        export COOJA_PATH="/home/dev/contiki-ng"
    elif [ -f "$PWD/contiki-ng-brpl/tools/cooja/build/libs/cooja.jar" ]; then
        export COOJA_PATH="$PWD/contiki-ng-brpl"
    else
        echo "WARNING: COOJA_PATH not set. Please set it manually:"
        echo "  export COOJA_PATH=/path/to/contiki-ng"
    fi
fi

# Add Rust to PATH if not already
if [ -f "$HOME/.cargo/env" ]; then
    source "$HOME/.cargo/env"
fi

echo "Environment configured:"
echo "  JAVA_HOME: $JAVA_HOME"
echo "  COOJA_PATH: $COOJA_PATH"
echo "  CONTIKI_NG_PATH: $CONTIKI_NG_PATH"
