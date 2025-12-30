#!/bin/bash
# SwarmAgent Installation Script
# Installs SwarmAgent daemon for SwarmVision distributed compute

set -e

REPO="https://github.com/SudoSuOps/swarmvision"
INSTALL_DIR="$HOME/.swarmagent"
BIN_DIR="$HOME/.local/bin"

echo "=================================="
echo "SwarmAgent Installer"
echo "SwarmVision Protocol v0.1"
echo "=================================="
echo

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Python: $PYTHON_VERSION"

# Check for NVIDIA GPU (optional)
if command -v nvidia-smi &> /dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
    echo "GPU: $GPU_INFO"
else
    echo "GPU: None detected (CPU-only mode)"
fi

echo

# Create directories
echo "[1/4] Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/proofs"
mkdir -p "$BIN_DIR"

# Clone or update repository
echo "[2/4] Downloading SwarmAgent..."
if [ -d "$INSTALL_DIR/src" ]; then
    cd "$INSTALL_DIR/src"
    git pull --quiet
else
    git clone --quiet --depth 1 "$REPO" "$INSTALL_DIR/src"
fi

# Install dependencies
echo "[3/4] Installing dependencies..."
cd "$INSTALL_DIR/src"
pip3 install --quiet --user -r requirements.txt 2>/dev/null || true

# Create launcher script
echo "[4/4] Creating launcher..."
cat > "$BIN_DIR/swarmagent" << 'EOF'
#!/bin/bash
SCRIPT_DIR="$HOME/.swarmagent/src"
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
python3 -m swarmagent.cli.main "$@"
EOF
chmod +x "$BIN_DIR/swarmagent"

# Add to PATH if needed
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo
    echo "Add to your shell profile:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo
echo "=================================="
echo "Installation complete!"
echo "=================================="
echo
echo "Next steps:"
echo
echo "1. Register your agent:"
echo "   swarmagent register --ens yourname.swarmagent.eth"
echo
echo "2. Start earning:"
echo "   swarmagent start"
echo
echo "3. Check status:"
echo "   swarmagent status"
echo
