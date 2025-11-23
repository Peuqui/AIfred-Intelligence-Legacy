#!/bin/bash
#
# KoboldCPP Installation Script für AIfred Intelligence
# Installiert KoboldCPP mit CUDA-Support für NVIDIA GPUs
#

set -e  # Exit on error

echo "=================================================="
echo "  KoboldCPP Installation für AIfred Intelligence"
echo "=================================================="
echo ""

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}❌ Dieses Script ist nur für Linux gedacht${NC}"
    exit 1
fi

# Check if NVIDIA GPU is available
# Try common nvidia-smi locations (for sudo environments and WSL2)
NVIDIA_SMI=""
for path in /usr/lib/wsl/lib/nvidia-smi /usr/bin/nvidia-smi /usr/local/cuda/bin/nvidia-smi; do
    if [ -x "$path" ]; then
        NVIDIA_SMI=$path
        break
    fi
done

if [ -z "$NVIDIA_SMI" ]; then
    echo -e "${YELLOW}⚠️  nvidia-smi nicht gefunden. KoboldCPP wird ohne GPU-Support installiert.${NC}"
    GPU_SUPPORT=false
else
    echo -e "${GREEN}✅ NVIDIA GPU gefunden:${NC}"
    $NVIDIA_SMI --query-gpu=name,memory.total --format=csv,noheader
    GPU_SUPPORT=true
fi

echo ""
echo "🔧 Installation startet..."
echo ""

# Installation directory
# Use original user's home even when running with sudo
if [ -n "$SUDO_USER" ]; then
    USER_HOME=$(eval echo ~$SUDO_USER)
else
    USER_HOME="$HOME"
fi
INSTALL_DIR="$USER_HOME/koboldcpp"
BINARY_PATH="/usr/local/bin/koboldcpp"

# Option 1: Try to install via binary release (fastest)
echo "📦 Methode 1: Binary Release herunterladen..."

# Select binary based on GPU support
if [ "$GPU_SUPPORT" = true ]; then
    CUDA_VERSION=$($NVIDIA_SMI | grep "CUDA Version" | awk '{print $9}')
    echo "   CUDA Version: $CUDA_VERSION"
    echo "   → Verwende Standard-Binary (enthält CUDA-Support für alle Versionen)"

    # Standard binary includes CUDA support for all CUDA versions
    BINARY_URL="https://github.com/LostRuins/koboldcpp/releases/latest/download/koboldcpp-linux-x64"
    BINARY_NAME="koboldcpp"
else
    echo "   → Verwende CPU-only Binary"
    BINARY_URL="https://github.com/LostRuins/koboldcpp/releases/latest/download/koboldcpp-linux-x64-nocuda"
    BINARY_NAME="koboldcpp-nocuda"
fi

# Download binary
echo "   Downloading from: $BINARY_URL"
TMP_BINARY="/tmp/$BINARY_NAME"

if wget -q --show-progress "$BINARY_URL" -O "$TMP_BINARY"; then
    chmod +x "$TMP_BINARY"

    # Test if binary works
    if "$TMP_BINARY" --help &> /dev/null; then
        echo -e "${GREEN}✅ Binary erfolgreich heruntergeladen und getestet${NC}"

        # Install to /usr/local/bin
        if sudo mv "$TMP_BINARY" "$BINARY_PATH"; then
            echo -e "${GREEN}✅ KoboldCPP installiert nach: $BINARY_PATH${NC}"
            INSTALL_SUCCESS=true
        else
            echo -e "${RED}❌ Konnte Binary nicht nach $BINARY_PATH verschieben${NC}"
            INSTALL_SUCCESS=false
        fi
    else
        echo -e "${YELLOW}⚠️  Binary funktioniert nicht. Versuche Kompilierung aus Source...${NC}"
        INSTALL_SUCCESS=false
    fi
else
    echo -e "${YELLOW}⚠️  Binary Download fehlgeschlagen. Versuche Kompilierung aus Source...${NC}"
    INSTALL_SUCCESS=false
fi

# Option 2: Compile from source if binary installation failed
if [ "$INSTALL_SUCCESS" != true ]; then
    echo ""
    echo "🔨 Methode 2: Aus Source kompilieren..."

    # Check dependencies
    echo "   Prüfe Abhängigkeiten..."
    MISSING_DEPS=()

    command -v git &> /dev/null || MISSING_DEPS+=("git")
    command -v make &> /dev/null || MISSING_DEPS+=("build-essential")
    command -v g++ &> /dev/null || MISSING_DEPS+=("g++")

    if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Fehlende Abhängigkeiten: ${MISSING_DEPS[*]}${NC}"
        echo "   Installiere Abhängigkeiten..."
        sudo apt-get update
        sudo apt-get install -y git build-essential
    fi

    # Clone repository
    if [ -d "$INSTALL_DIR" ]; then
        echo "   Verzeichnis existiert bereits. Aktualisiere..."
        cd "$INSTALL_DIR"
        git pull
    else
        echo "   Clone KoboldCPP Repository..."
        git clone https://github.com/LostRuins/koboldcpp "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi

    # Compile with CUDA if available
    echo "   Kompiliere KoboldCPP..."
    if [ "$GPU_SUPPORT" = true ]; then
        echo "   Mit CUDA Support..."
        make LLAMA_CUBLAS=1 -j$(nproc)
    else
        echo "   Ohne GPU Support (CPU only)..."
        make -j$(nproc)
    fi

    # Test compiled binary
    if [ -f "$INSTALL_DIR/koboldcpp" ]; then
        if "$INSTALL_DIR/koboldcpp" --help &> /dev/null; then
            echo -e "${GREEN}✅ Kompilierung erfolgreich${NC}"

            # Install to /usr/local/bin
            if sudo cp "$INSTALL_DIR/koboldcpp" "$BINARY_PATH"; then
                echo -e "${GREEN}✅ KoboldCPP installiert nach: $BINARY_PATH${NC}"
                INSTALL_SUCCESS=true
            else
                echo -e "${RED}❌ Konnte Binary nicht nach $BINARY_PATH kopieren${NC}"
                echo "   Binary liegt in: $INSTALL_DIR/koboldcpp"
                INSTALL_SUCCESS=false
            fi
        else
            echo -e "${RED}❌ Kompilierte Binary funktioniert nicht${NC}"
            INSTALL_SUCCESS=false
        fi
    else
        echo -e "${RED}❌ Kompilierung fehlgeschlagen${NC}"
        INSTALL_SUCCESS=false
    fi
fi

echo ""
echo "=================================================="

if [ "$INSTALL_SUCCESS" = true ]; then
    echo -e "${GREEN}✅ Installation abgeschlossen!${NC}"
    echo ""
    echo "KoboldCPP Version:"
    koboldcpp --version 2>&1 | head -n 1 || echo "   (Version check nicht verfügbar)"
    echo ""
    echo "📍 Binary Pfad: $BINARY_PATH"
    echo ""
    echo "🚀 Nächste Schritte:"
    echo "   1. GGUF Model herunterladen (siehe docs/koboldcpp_2x_p40_setup.md)"
    echo "   2. KoboldCPP in AIfred aktivieren (siehe unten)"
    echo ""
    echo "📝 Beispiel Start-Befehl:"
    echo "   koboldcpp ~/models/model.gguf \\"
    echo "     --port 5001 \\"
    echo "     --contextsize 32768 \\"
    echo "     --gpulayers 40 \\"
    echo "     --usecublas \\"
    echo "     --contextoffload \\"
    echo "     --tensor_split 1,0 \\"
    echo "     --flashattention \\"
    echo "     --quantkv"
    echo ""
else
    echo -e "${RED}❌ Installation fehlgeschlagen${NC}"
    echo ""
    echo "Mögliche Lösungen:"
    echo "   1. Manueller Download: https://github.com/LostRuins/koboldcpp/releases"
    echo "   2. Kompilierung aus Source: cd ~/koboldcpp && make LLAMA_CUBLAS=1"
    echo "   3. GitHub Issue erstellen: https://github.com/LostRuins/koboldcpp/issues"
    exit 1
fi

echo "=================================================="
