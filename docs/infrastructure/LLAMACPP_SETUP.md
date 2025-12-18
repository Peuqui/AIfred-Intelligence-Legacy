# llama.cpp Server Setup for AIfred Intelligence

Guide for installing and configuring llama.cpp Server with Router Mode for AIfred.

## Overview

llama.cpp Server provides:
- **Router Mode**: Dynamic model loading/unloading like Ollama
- **OpenAI-compatible API**: `/v1/chat/completions`
- **MoE Expert Offloading**: `--n-cpu-moe` for larger models with limited VRAM
- **Multi-GPU Support**: Automatic tensor distribution

## Quick Start

### 1. Install llama.cpp

```bash
# From AIfred project directory
./scripts/install_llamacpp.sh

# Or force compilation for optimal CUDA performance
./scripts/install_llamacpp.sh --compile
```

### 2. Download GGUF Models

```bash
# Create models directory (shared with KoboldCPP)
mkdir -p ~/models

# Download example model (Qwen3-30B-A3B MoE)
wget -P ~/models https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF/resolve/main/qwen3-30b-a3b-q8_0.gguf
```

### 3. Start Server

```bash
# Basic start (Router Mode)
llama-server \
  --models-dir ~/models \
  --host 0.0.0.0 \
  --port 8080 \
  -ngl 99 \
  --models-max 2
```

## Installation Methods

### Method 1: Installation Script (Recommended)

```bash
cd /path/to/AIfred-Intelligence
./scripts/install_llamacpp.sh
```

The script:
1. Detects your GPU and CUDA version
2. Compiles llama.cpp with optimal CUDA settings for your GPU
3. Installs `llama-server` to `/usr/local/bin/`

### Method 2: Manual Compilation

```bash
# Install dependencies
sudo apt install cmake g++ git nvidia-cuda-toolkit

# Clone repository
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp

# Build with CUDA
mkdir build && cd build
cmake .. -DGGML_CUDA=ON -DLLAMA_BUILD_SERVER=ON
cmake --build . --config Release -j$(nproc)

# Install
sudo cp bin/llama-server /usr/local/bin/
```

### Method 3: Prebuilt Binaries

Check [llama.cpp Releases](https://github.com/ggml-org/llama.cpp/releases) for prebuilt binaries.

Note: Prebuilt binaries may not be optimized for your specific GPU architecture.

## Configuration

### Router Mode (Dynamic Model Loading)

Router Mode allows loading/unloading models via API, similar to Ollama:

```bash
llama-server \
  --models-dir ~/models \    # Directory with GGUF files
  --models-max 2 \           # Max models in VRAM simultaneously
  --host 0.0.0.0 \
  --port 8080 \
  -ngl 99                    # Offload all layers to GPU
```

**API Endpoints:**
- `GET /models` - List available models
- `POST /models/load` - Load model into VRAM
- `POST /models/unload` - Unload model from VRAM
- `POST /v1/chat/completions` - OpenAI-compatible chat

### MoE Expert Offloading

For MoE models (Mixtral, Qwen3-A3B) with limited VRAM but ample RAM:

```bash
llama-server \
  --models-dir ~/models \
  -ngl 99 \
  --n-cpu-moe 12    # Offload 12 expert layers to CPU RAM
```

**How it works:**
- Dense/attention layers stay in VRAM (fast)
- Expert weights stored in CPU RAM
- Only active experts transferred during inference
- PCIe bandwidth is the bottleneck

**Requirements:**
- 64GB+ RAM recommended
- Fast DDR5 RAM improves performance
- AMD Zen 4/5 CPUs have high memory bandwidth

**Example Performance (from llama.cpp docs):**
- 120B MoE model: ~20 tok/s with 20GB GPU + 64GB RAM

### Multi-GPU Setup

For dual GPUs (e.g., 2x Tesla P40):

```bash
llama-server \
  --models-dir ~/models \
  -ngl 99 \
  --tensor-split 0.5,0.5 \    # Equal distribution
  --main-gpu 0                 # Primary GPU for compute
```

### Context Window

```bash
llama-server \
  --models-dir ~/models \
  -ngl 99 \
  -c 32768    # 32K context window
```

## Systemd Service

### Create Service File

```bash
sudo nano /etc/systemd/system/llamacpp.service
```

```ini
[Unit]
Description=llama.cpp Server (Router Mode)
After=network.target

[Service]
Type=simple
User=mp
Environment="CUDA_VISIBLE_DEVICES=0,1"
ExecStart=/usr/local/bin/llama-server \
    --models-dir /home/mp/models \
    --host 0.0.0.0 \
    --port 8080 \
    -ngl 99 \
    --models-max 2
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Enable Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable llamacpp
sudo systemctl start llamacpp
```

### Check Status

```bash
sudo systemctl status llamacpp
journalctl -u llamacpp -f
```

## AIfred Configuration

### config.py Settings

llama.cpp is pre-configured in AIfred:

```python
# aifred/lib/config.py

BACKEND_URLS = {
    ...
    "llamacpp": "http://localhost:8080",
}

BACKEND_DEFAULT_MODELS = {
    ...
    "llamacpp": {
        "selected_model": "Qwen3-30B-A3B-Q8_0.gguf",
        "automatik_model": "Qwen3-4B-Q8_0.gguf",
    },
}
```

### Select in AIfred UI

1. Open AIfred in browser
2. Go to Settings
3. Select "llama.cpp" from Backend dropdown

## Troubleshooting

### CUDA Not Detected

```bash
# Check CUDA installation
nvidia-smi
nvcc --version

# Reinstall CUDA toolkit
sudo apt install nvidia-cuda-toolkit

# Recompile llama.cpp
./scripts/install_llamacpp.sh --compile
```

### Out of Memory

```bash
# Reduce context size
llama-server ... -c 16384

# Use smaller quantization (Q4_K_M instead of Q8_0)

# Enable MoE offloading (for MoE models)
llama-server ... --n-cpu-moe 8
```

### Model Not Loading

```bash
# Check model file exists
ls -la ~/models/*.gguf

# Check server logs
journalctl -u llamacpp -n 50

# Test API directly
curl http://localhost:8080/models
```

### Port Already in Use

```bash
# Find process using port
sudo lsof -i :8080

# Kill process or use different port
llama-server ... --port 8081
```

## API Usage Examples

### List Models

```bash
curl http://localhost:8080/models
```

### Load Model

```bash
curl -X POST http://localhost:8080/models/load \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3-30b-a3b-q8_0.gguf"}'
```

### Chat Completion

```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-30b-a3b-q8_0.gguf",
    "messages": [{"role": "user", "content": "Hello!"}],
    "temperature": 0.7
  }'
```

### Unload Model

```bash
curl -X POST http://localhost:8080/models/unload \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3-30b-a3b-q8_0.gguf"}'
```

## Comparison with Other Backends

| Feature | Ollama | llama.cpp | KoboldCPP |
|---------|--------|-----------|-----------|
| Model Format | GGUF | GGUF | GGUF |
| Dynamic Loading | Yes | Yes (Router) | No |
| API Style | Custom | OpenAI | KoboldAI |
| MoE Offload | No | Yes | No |
| Ease of Use | High | Medium | Medium |
| Performance | Good | Excellent | Good |

## References

- [llama.cpp GitHub](https://github.com/ggml-org/llama.cpp)
- [Router Mode Blog](https://huggingface.co/blog/ggml-org/model-management-in-llamacpp)
- [Server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
