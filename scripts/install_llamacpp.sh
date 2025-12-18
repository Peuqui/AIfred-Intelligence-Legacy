#!/bin/bash
#
# llama.cpp Installation Script for AIfred Intelligence
# Installs llama.cpp Server with CUDA support for NVIDIA GPUs
# Supports: Router Mode, MoE Expert Offloading (--n-cpu-moe)
#
# Usage:
#   ./install_llamacpp.sh              # Interactive install
#   ./install_llamacpp.sh --compile    # Force compilation from source
#   ./install_llamacpp.sh --binary     # Force binary download (if available)
#

set -e  # Exit on error

echo "=================================================="
echo "  llama.cpp Server Installation for AIfred"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
FORCE_COMPILE=false
FORCE_BINARY=false
for arg in "$@"; do
    case $arg in
        --compile)
            FORCE_COMPILE=true
            ;;
        --binary)
            FORCE_BINARY=true
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --compile    Force compilation from source (recommended for CUDA)"
            echo "  --binary     Force binary download (may not have optimal CUDA)"
            echo "  --help       Show this help message"
            exit 0
            ;;
    esac
done

# Check if running on Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}Error: This script is for Linux only${NC}"
    exit 1
fi

# Detect nvidia-smi (for CUDA detection)
NVIDIA_SMI=""
for path in /usr/lib/wsl/lib/nvidia-smi /usr/bin/nvidia-smi /usr/local/cuda/bin/nvidia-smi; do
    if [ -x "$path" ]; then
        NVIDIA_SMI=$path
        break
    fi
done

if [ -z "$NVIDIA_SMI" ]; then
    echo -e "${YELLOW}Warning: nvidia-smi not found. llama.cpp will be built without GPU support.${NC}"
    GPU_SUPPORT=false
else
    echo -e "${GREEN}NVIDIA GPU detected:${NC}"
    $NVIDIA_SMI --query-gpu=name,memory.total,compute_cap --format=csv,noheader
    GPU_SUPPORT=true

    # Get CUDA version
    CUDA_VERSION=$($NVIDIA_SMI | grep -oP "CUDA Version: \K[0-9.]+" || echo "unknown")
    echo -e "CUDA Version: ${BLUE}$CUDA_VERSION${NC}"
fi

echo ""
echo "Starting installation..."
echo ""

# Installation directories
# Use original user's home even when running with sudo
if [ -n "$SUDO_USER" ]; then
    USER_HOME=$(eval echo ~$SUDO_USER)
else
    USER_HOME="$HOME"
fi

INSTALL_DIR="$USER_HOME/llama.cpp"
BINARY_PATH="/usr/local/bin/llama-server"
MODELS_DIR="$USER_HOME/models"  # Shared with KoboldCPP

# Ensure models directory exists
mkdir -p "$MODELS_DIR"

# ============================================================
# Method 1: Compile from Source (Recommended for CUDA)
# ============================================================
compile_from_source() {
    echo -e "${BLUE}Compiling llama.cpp from source...${NC}"
    echo "This ensures optimal CUDA support for your GPU."
    echo ""

    # Check dependencies
    echo "Checking dependencies..."
    MISSING_DEPS=()

    command -v git &> /dev/null || MISSING_DEPS+=("git")
    command -v cmake &> /dev/null || MISSING_DEPS+=("cmake")
    command -v g++ &> /dev/null || MISSING_DEPS+=("g++")
    command -v make &> /dev/null || MISSING_DEPS+=("build-essential")

    if [ "$GPU_SUPPORT" = true ]; then
        # Check for CUDA toolkit
        if ! command -v nvcc &> /dev/null; then
            echo -e "${YELLOW}Warning: nvcc not found. Installing CUDA toolkit...${NC}"
            MISSING_DEPS+=("nvidia-cuda-toolkit")
        fi
    fi

    if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
        echo -e "${YELLOW}Installing missing dependencies: ${MISSING_DEPS[*]}${NC}"
        sudo apt-get update
        sudo apt-get install -y "${MISSING_DEPS[@]}"
    fi

    # Clone or update repository
    if [ -d "$INSTALL_DIR" ]; then
        echo "Updating existing repository..."
        cd "$INSTALL_DIR"
        git fetch --tags
        git checkout master
        git pull origin master
    else
        echo "Cloning llama.cpp repository..."
        git clone https://github.com/ggml-org/llama.cpp "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi

    # Get latest release tag
    LATEST_TAG=$(git describe --tags $(git rev-list --tags --max-count=1) 2>/dev/null || echo "master")
    echo -e "Building version: ${BLUE}$LATEST_TAG${NC}"
    git checkout "$LATEST_TAG" 2>/dev/null || echo "Using master branch"

    # Clean previous build
    rm -rf build
    mkdir -p build
    cd build

    # Configure with CMake
    # Note: llama.cpp migrated from Makefile to CMake in late 2024
    echo ""
    echo "Configuring build with CMake..."

    CMAKE_ARGS="-DLLAMA_BUILD_SERVER=ON"

    if [ "$GPU_SUPPORT" = true ]; then
        echo -e "${GREEN}Building with CUDA support${NC}"
        CMAKE_ARGS="$CMAKE_ARGS -DGGML_CUDA=ON"

        # Detect GPU compute capability for optimal build
        COMPUTE_CAP=$($NVIDIA_SMI --query-gpu=compute_cap --format=csv,noheader | head -n1 | tr -d '.')
        if [ -n "$COMPUTE_CAP" ]; then
            echo "GPU Compute Capability: ${COMPUTE_CAP:0:1}.${COMPUTE_CAP:1}"
            # Build for your specific GPU architecture (faster compile, optimal code)
            CMAKE_ARGS="$CMAKE_ARGS -DGGML_CUDA_ARCHITECTURES=$COMPUTE_CAP"
        fi
    else
        echo "Building CPU-only version"
    fi

    # CMake configure (simple 3-step process)
    echo ""
    echo "Step 1/3: cmake configure..."
    cmake .. $CMAKE_ARGS

    # CMake build
    echo ""
    echo "Step 2/3: cmake build (this takes 2-5 minutes)..."
    cmake --build . --config Release -j$(nproc)

    # Check if build succeeded
    if [ -f "bin/llama-server" ]; then
        echo ""
        echo "Step 3/3: Installing..."
        echo -e "${GREEN}Compilation successful!${NC}"

        # Install to /usr/local/bin
        # Check if target is a symlink pointing to our binary (already installed)
        if [ -L "$BINARY_PATH" ]; then
            LINK_TARGET=$(readlink -f "$BINARY_PATH")
            CURRENT_BINARY=$(readlink -f "bin/llama-server")
            if [ "$LINK_TARGET" = "$CURRENT_BINARY" ]; then
                echo -e "${GREEN}Already installed as symlink to: $LINK_TARGET${NC}"
                return 0
            fi
            # Different symlink - remove and reinstall
            sudo rm "$BINARY_PATH"
        fi

        # Remove existing file if present (not a symlink to us)
        if [ -f "$BINARY_PATH" ]; then
            sudo rm "$BINARY_PATH"
        fi

        # Create symlink (better than copy - auto-updates on rebuild)
        if sudo ln -s "$(readlink -f bin/llama-server)" "$BINARY_PATH"; then
            echo -e "${GREEN}Installed symlink: $BINARY_PATH → $(readlink -f bin/llama-server)${NC}"
            return 0
        else
            echo -e "${RED}Failed to install to $BINARY_PATH${NC}"
            return 1
        fi
    else
        echo -e "${RED}Compilation failed${NC}"
        return 1
    fi
}

# ============================================================
# Method 2: Download Prebuilt Binary
# ============================================================
download_binary() {
    echo -e "${BLUE}Downloading prebuilt binary...${NC}"
    echo -e "${YELLOW}Note: Prebuilt binaries may not have optimal CUDA support.${NC}"
    echo -e "${YELLOW}For best performance, use --compile flag.${NC}"
    echo ""

    # llama.cpp releases page
    RELEASES_URL="https://github.com/ggml-org/llama.cpp/releases/latest"

    # Get latest release version
    LATEST_VERSION=$(curl -s -I "$RELEASES_URL" | grep -i "location:" | sed 's/.*tag\///' | tr -d '\r\n')
    echo "Latest version: $LATEST_VERSION"

    # Binary names based on platform and GPU
    if [ "$GPU_SUPPORT" = true ]; then
        # Try CUDA binary first
        BINARY_NAME="llama-${LATEST_VERSION}-bin-ubuntu-x64-cuda.zip"
        BINARY_URL="https://github.com/ggml-org/llama.cpp/releases/download/${LATEST_VERSION}/${BINARY_NAME}"
    else
        BINARY_NAME="llama-${LATEST_VERSION}-bin-ubuntu-x64.zip"
        BINARY_URL="https://github.com/ggml-org/llama.cpp/releases/download/${LATEST_VERSION}/${BINARY_NAME}"
    fi

    echo "Downloading: $BINARY_URL"

    TMP_DIR=$(mktemp -d)
    cd "$TMP_DIR"

    if wget -q --show-progress "$BINARY_URL" -O "$BINARY_NAME" 2>/dev/null; then
        echo "Extracting..."
        unzip -q "$BINARY_NAME"

        # Find llama-server binary
        SERVER_BIN=$(find . -name "llama-server" -type f | head -n1)

        if [ -n "$SERVER_BIN" ] && [ -x "$SERVER_BIN" ]; then
            # Test binary
            if "$SERVER_BIN" --help &>/dev/null; then
                echo -e "${GREEN}Binary works!${NC}"

                if sudo mv "$SERVER_BIN" "$BINARY_PATH"; then
                    sudo chmod +x "$BINARY_PATH"
                    echo -e "${GREEN}Installed to: $BINARY_PATH${NC}"
                    rm -rf "$TMP_DIR"
                    return 0
                fi
            fi
        fi

        echo -e "${YELLOW}Binary download failed or doesn't work${NC}"
    else
        echo -e "${YELLOW}Download failed${NC}"
    fi

    rm -rf "$TMP_DIR"
    return 1
}

# ============================================================
# Main Installation Logic
# ============================================================
INSTALL_SUCCESS=false

if [ "$FORCE_COMPILE" = true ]; then
    # User requested compilation
    if compile_from_source; then
        INSTALL_SUCCESS=true
    fi
elif [ "$FORCE_BINARY" = true ]; then
    # User requested binary
    if download_binary; then
        INSTALL_SUCCESS=true
    else
        echo ""
        echo "Binary download failed. Falling back to compilation..."
        if compile_from_source; then
            INSTALL_SUCCESS=true
        fi
    fi
else
    # Default: Compile from source (recommended for CUDA)
    # Compilation gives optimal performance for your specific GPU
    if [ "$GPU_SUPPORT" = true ]; then
        echo -e "${BLUE}GPU detected - compiling from source for optimal CUDA performance${NC}"
        echo ""
    fi

    if compile_from_source; then
        INSTALL_SUCCESS=true
    else
        echo ""
        echo "Compilation failed. Trying binary download..."
        if download_binary; then
            INSTALL_SUCCESS=true
        fi
    fi
fi

# ============================================================
# Installation Summary
# ============================================================
echo ""
echo "=================================================="

if [ "$INSTALL_SUCCESS" = true ]; then
    echo -e "${GREEN}Installation complete!${NC}"
    echo ""

    # Show version
    echo "llama.cpp Server Version:"
    "$BINARY_PATH" --version 2>&1 | head -n 3 || echo "   (version check unavailable)"
    echo ""

    echo "Binary path: $BINARY_PATH"
    echo "Source code: $INSTALL_DIR"
    echo "Models dir:  $MODELS_DIR"
    echo ""

    echo -e "${BLUE}Next steps:${NC}"
    echo ""
    echo "1. Download GGUF models to $MODELS_DIR"
    echo "   Example: wget -P $MODELS_DIR https://huggingface.co/..."
    echo ""
    echo "2. Start llama.cpp Server (Router Mode):"
    echo ""
    echo -e "   ${GREEN}llama-server \\${NC}"
    echo -e "   ${GREEN}  --models-dir $MODELS_DIR \\${NC}"
    echo -e "   ${GREEN}  --host 0.0.0.0 \\${NC}"
    echo -e "   ${GREEN}  --port 8080 \\${NC}"
    echo -e "   ${GREEN}  -ngl 99 \\${NC}"
    echo -e "   ${GREEN}  --models-max 2${NC}"
    echo ""
    echo "3. For MoE Expert Offloading (requires 64GB+ RAM):"
    echo ""
    echo -e "   ${GREEN}llama-server \\${NC}"
    echo -e "   ${GREEN}  --models-dir $MODELS_DIR \\${NC}"
    echo -e "   ${GREEN}  -ngl 99 \\${NC}"
    echo -e "   ${GREEN}  --n-cpu-moe 12${NC}"
    echo ""
    echo "4. Create systemd service for auto-start:"
    echo "   See: docs/infrastructure/llamacpp-setup.md"
    echo ""
else
    echo -e "${RED}Installation failed!${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "1. Ensure CUDA toolkit is installed:"
    echo "   sudo apt install nvidia-cuda-toolkit"
    echo ""
    echo "2. Manual compilation:"
    echo "   cd $INSTALL_DIR"
    echo "   mkdir build && cd build"
    echo "   cmake .. -DGGML_CUDA=ON -DLLAMA_BUILD_SERVER=ON"
    echo "   cmake --build . --config Release -j\$(nproc)"
    echo ""
    echo "3. Check llama.cpp GitHub for issues:"
    echo "   https://github.com/ggml-org/llama.cpp/issues"
    exit 1
fi

echo "=================================================="
