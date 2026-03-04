#!/bin/bash
# TA-BRPL Ubuntu Setup Script
# Installs all dependencies and builds required components

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_info "============================================"
log_info "TA-BRPL Setup for Ubuntu"
log_info "============================================"
echo ""

# Check if running on Ubuntu/Debian
if ! command -v apt &> /dev/null; then
    log_error "This script requires apt package manager (Ubuntu/Debian)"
    exit 1
fi

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

# 1. Update package lists
log_info "Step 1/10: Updating package lists..."
sudo apt update

# 2. Install core build tools
log_info "Step 2/10: Installing core build tools..."
sudo apt install -y \
    build-essential \
    gcc \
    g++ \
    make \
    git \
    curl \
    wget \
    pkg-config \
    libssl-dev

# 3. Install Java (OpenJDK 17 for Cooja)
log_info "Step 3/10: Installing Java OpenJDK 17..."
sudo apt install -y openjdk-17-jdk openjdk-17-jre ant

# 4. Install Python and packages
log_info "Step 4/10: Installing Python and packages..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-numpy \
    python3-pandas \
    python3-matplotlib

# 5. Install R and packages
log_info "Step 5/10: Installing R and packages..."
sudo apt install -y r-base r-base-dev

log_info "Installing R packages (this may take a few minutes)..."
sudo R --quiet --no-save <<'EOF'
packages <- c("ggplot2", "dplyr", "tidyr", "readr", "scales", "gridExtra")
install.packages(packages, repos="https://cloud.r-project.org/", quiet=TRUE)
EOF

# 6. Install Rust and Cargo
log_info "Step 6/10: Installing Rust and Cargo..."
if ! command -v cargo &> /dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
    source "$HOME/.cargo/env"
    log_info "Rust installed successfully"
else
    log_info "Rust already installed, updating..."
    rustup update stable
fi

# Make sure cargo is in PATH for current session
export PATH="$HOME/.cargo/bin:$PATH"

# 7. Install additional utilities
log_info "Step 7/10: Installing additional utilities..."
sudo apt install -y \
    ripgrep \
    coreutils \
    findutils

# 8. Initialize git submodule
log_info "Step 8/10: Initializing git submodules..."
if [ ! -f "contiki-ng-brpl/.git" ]; then
    git submodule update --init --recursive
    log_info "Submodule initialized"
else
    log_info "Submodule already initialized"
fi

# 9. Build trust_engine
log_info "Step 9/10: Building trust_engine..."
if [ -d "tools/trust_engine" ]; then
    cd tools/trust_engine
    cargo build --release
    cd "$PROJECT_DIR"
    log_info "trust_engine built successfully"
else
    log_warn "tools/trust_engine directory not found, skipping"
fi

# 10. Set script permissions
log_info "Step 10/10: Setting script permissions..."
chmod +x scripts/*.sh 2>/dev/null || true

# Set environment variables
log_info ""
log_info "============================================"
log_info "Setup Complete!"
log_info "============================================"
echo ""

# Create environment setup script
cat > "$PROJECT_DIR/env.sh" <<'ENVEOF'
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
ENVEOF

chmod +x "$PROJECT_DIR/env.sh"

log_info "Environment setup script created: env.sh"
log_info ""
log_info "Next steps:"
log_info "  1. Source the environment (automatically done below):"
log_info "     source ./env.sh"
log_info ""
log_info "  2. Set COOJA_PATH if not auto-detected:"
log_info "     export COOJA_PATH=/path/to/contiki-ng"
log_info ""
log_info "  3. Build Cooja if needed:"
log_info "     cd \$COOJA_PATH/tools/cooja && ant jar"
log_info ""
log_info "  4. Run a quick test:"
log_info "     QUICK_PREVIEW=1 ./scripts/run_experiments.sh"
log_info ""
log_info "  5. Run full experiments:"
log_info "     ./scripts/run_experiments.sh"
log_info ""

# Check versions
echo ""
log_info "Installed versions:"
java -version 2>&1 | head -n 1
python3 --version
R --version | head -n 1
cargo --version
ant -version | head -n 1
echo ""

# Auto-source environment for convenience
log_info "Sourcing environment for current session..."
source "$PROJECT_DIR/env.sh"

log_info "Setup complete! You can now run experiments."
echo ""
