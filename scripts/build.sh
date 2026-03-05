#!/bin/bash
# Build motes for Cooja simulations

set -e

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$PROJECT_DIR"

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[BUILD]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[BUILD]${NC} $1"
}

log_error() {
    echo -e "${RED}[BUILD]${NC} $1"
}

# Set environment
export CONTIKI_NG_PATH="$PROJECT_DIR/contiki-ng-brpl"

log_info "Building motes for Cooja..."
log_info "CONTIKI_NG_PATH: $CONTIKI_NG_PATH"

cd motes

# Build receiver (root node)
if [ ! -f "build/cooja/receiver_root.cooja" ]; then
    log_info "Building receiver_root..."
    make -f Makefile.receiver TARGET=cooja || {
        log_error "Failed to build receiver_root"
        exit 1
    }
else
    log_info "receiver_root already built"
fi

# Build sender
if [ ! -f "build/cooja/sender.cooja" ]; then
    log_info "Building sender..."
    make -f Makefile.sender TARGET=cooja || {
        log_error "Failed to build sender"
        exit 1
    }
else
    log_info "sender already built"
fi

# Build attacker
if [ ! -f "build/cooja/attacker.cooja" ]; then
    log_info "Building attacker..."
    make -f Makefile.attacker TARGET=cooja || {
        log_error "Failed to build attacker"
        exit 1
    }
else
    log_info "attacker already built"
fi

cd "$PROJECT_DIR"

log_info "All motes built successfully!"
log_info "Build artifacts in: motes/build/cooja/"
