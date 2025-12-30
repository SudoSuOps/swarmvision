#!/bin/bash
# SwarmAgent Installation Script
# Microscaler onboarding for SwarmVision distributed compute
# See: docs/protocol/Microscaler.onboarding.md

set -e

REPO="https://github.com/SudoSuOps/swarmvision"
INSTALL_DIR="$HOME/.swarmagent"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.swarmagent"

echo "=============================================="
echo "SwarmAgent Installer"
echo "SwarmVision Protocol v0.2"
echo "=============================================="
echo
echo "Microscaler Onboarding"
echo "See: docs/protocol/Microscaler.onboarding.md"
echo

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3.10+ is required"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python: $PYTHON_VERSION"

# Check for NVIDIA GPU
echo
echo "=== Hardware Detection ==="
if command -v nvidia-smi &> /dev/null; then
    GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1)
    DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
    echo "GPUs: $GPU_COUNT"
    echo "Model: $GPU_INFO"
    echo "Driver: $DRIVER"
else
    echo "GPU: None detected"
    echo "Warning: Microscalers require ≥1 GPU"
fi

# Check CPU
CPU_CORES=$(nproc 2>/dev/null || echo "unknown")
echo "CPU Cores: $CPU_CORES"

# Check RAM
if [ -f /proc/meminfo ]; then
    RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    RAM_GB=$((RAM_KB / 1024 / 1024))
    echo "RAM: ${RAM_GB} GB"
fi

echo

# Create directories
echo "[1/5] Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/proofs"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$BIN_DIR"
mkdir -p "$CONFIG_DIR"

# Clone or update repository
echo "[2/5] Downloading SwarmAgent..."
if [ -d "$INSTALL_DIR/src" ]; then
    cd "$INSTALL_DIR/src"
    git pull --quiet
else
    git clone --quiet --depth 1 "$REPO" "$INSTALL_DIR/src"
fi

# Install dependencies
echo "[3/5] Installing dependencies..."
cd "$INSTALL_DIR/src"
pip3 install --quiet --user -r requirements.txt 2>/dev/null || true

# Create launcher script
echo "[4/5] Creating launcher..."
cat > "$BIN_DIR/swarmagent" << 'EOF'
#!/bin/bash
SCRIPT_DIR="$HOME/.swarmagent/src"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
python3 -m swarmagent.cli.main "$@"
EOF
chmod +x "$BIN_DIR/swarmagent"

# Create example config
echo "[5/5] Creating config template..."
if [ ! -f "$CONFIG_DIR/env.example" ]; then
cat > "$CONFIG_DIR/env.example" << 'EOF'
# SwarmAgent Configuration
# Copy to .env and fill in values

# Required: Your ENS identity (*.swarmcompute.eth)
SWARMCOMPUTE_ENS=yourname.swarmcompute.eth

# Required: SwarmVision OS endpoint (mesh address)
SWARMVISION_URL=http://swarmvision.mesh:8000

# Required: Wallet private key (controls ENS identity)
# NEVER share this key
SWARMAGENT_PRIVATE_KEY=

# Optional: Region hint
# SWARMVISION_REGION=us-east
EOF
fi

# Add to PATH if needed
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo
    echo "Add to your shell profile:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo
echo "=============================================="
echo "Installation complete!"
echo "=============================================="
echo
echo "=== Microscaler Onboarding Steps ==="
echo
echo "1. Get ENS identity:"
echo "   Register *.swarmcompute.eth at app.ens.domains"
echo
echo "2. Configure:"
echo "   cp ~/.swarmagent/env.example ~/.swarmagent/.env"
echo "   # Edit .env with your ENS and private key"
echo
echo "3. Register agent:"
echo "   swarmagent register --ens yourname.swarmcompute.eth"
echo
echo "4. Connect to mesh:"
echo "   # Tailscale or Headscale required"
echo "   tailscale up"
echo
echo "5. Start earning:"
echo "   swarmagent start"
echo
echo "6. Check status:"
echo "   swarmagent status"
echo "   swarmagent capabilities"
echo
echo "Docs: https://github.com/SudoSuOps/swarmvision/docs/protocol/"
echo
