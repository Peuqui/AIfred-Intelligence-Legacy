# AIfred Deployment Guide

Setup guide for a fresh AIfred installation with the llama.cpp backend (llama-swap).

**Last updated:** 2026-02-18

---

## Overview

AIfred uses **llama-swap** as a proxy daemon for llama.cpp. llama-swap manages
multiple models and loads them on demand. The **autoscan** mechanism detects new
models automatically and configures them without any manual YAML editing.

```
User <-> AIfred (Reflex web app) <-> llama-swap (:11435) <-> llama-server (per model)
```

---

## 1. Prerequisites

### Hardware
- NVIDIA GPU with CUDA support (Compute Capability >= 6.1, Pascal or newer)
- Recommended: >= 24 GB VRAM for useful model sizes

### Software
- Linux with systemd (Ubuntu/Debian recommended)
- CUDA Toolkit >= 12.0
- Python 3.10+
- Git

---

## 2. Build llama.cpp

```bash
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp
cmake -B build -DGGML_CUDA=ON
cmake --build build -j$(nproc)

# Verify the binary exists
ls ~/llama.cpp/build/bin/llama-server
```

> **Note:** The autoscan expects the binary at `~/llama.cpp/build/bin/llama-server`
> by default. If it lives elsewhere, add one existing YAML entry with the correct
> path — the autoscan reads the binary path from existing config entries.

---

## 3. Install llama-swap

```bash
# Download the binary from GitHub Releases
# https://github.com/mostlygeek/llama-swap/releases
wget -O ~/llama-swap https://github.com/mostlygeek/llama-swap/releases/latest/download/llama-swap-linux-amd64
chmod +x ~/llama-swap

# Create the config directory
mkdir -p ~/.config/llama-swap
```

```bash
# Create the config directory — the autoscan creates the config file itself
mkdir -p ~/.config/llama-swap
```

> **Note:** The autoscan creates `config.yaml` from scratch when models are found.
> An empty stub is only needed if you start llama-swap before downloading any models.

---

## 4. Set up AIfred

```bash
git clone https://github.com/Peuqui/AIfred-Intelligence ~/Projekte/AIfred-Intelligence
cd ~/Projekte/AIfred-Intelligence

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 5. Set up systemd services

### llama-swap service (with autoscan)

```bash
mkdir -p ~/.config/systemd/user

cat > ~/.config/systemd/user/llama-swap.service << 'EOF'
[Unit]
Description=llama-swap - LLM Model Proxy
After=network.target

[Service]
Type=simple
ExecStartPre=/home/YOUR_USER/Projekte/AIfred-Intelligence/venv/bin/python \
    /home/YOUR_USER/Projekte/AIfred-Intelligence/scripts/llama-swap-autoscan.py
ExecStart=/home/YOUR_USER/llama-swap \
    --config /home/YOUR_USER/.config/llama-swap/config.yaml \
    --listen :11435
Restart=on-failure
RestartSec=5
TimeoutStartSec=300
Environment=PATH=/usr/local/cuda/bin:/usr/local/bin:/usr/bin:/bin
Environment=LD_LIBRARY_PATH=/usr/local/cuda/lib64
Environment=CUDA_DEVICE_ORDER=FASTEST_FIRST
Environment=GGML_CUDA_GRAPH_OPT=1

[Install]
WantedBy=default.target
EOF

# Replace YOUR_USER with your actual username
sed -i "s/YOUR_USER/$USER/g" ~/.config/systemd/user/llama-swap.service

systemctl --user daemon-reload
systemctl --user enable llama-swap
```

### AIfred service

```bash
cat > ~/.config/systemd/user/aifred-intelligence.service << 'EOF'
[Unit]
Description=AIfred Intelligence
After=network.target llama-swap.service

[Service]
Type=simple
WorkingDirectory=/home/YOUR_USER/Projekte/AIfred-Intelligence
ExecStart=/home/YOUR_USER/Projekte/AIfred-Intelligence/venv/bin/reflex run \
    --env prod --loglevel warning
Restart=on-failure
RestartSec=5
Environment=LLAMACPP_URL=http://localhost:11435/v1

[Install]
WantedBy=default.target
EOF

sed -i "s/YOUR_USER/$USER/g" ~/.config/systemd/user/aifred-intelligence.service
systemctl --user daemon-reload
systemctl --user enable aifred-intelligence
```

---

## 6. Adding models

The autoscan detects models from three sources automatically. After adding a model,
restart llama-swap and it will be configured and ready.

```bash
systemctl --user restart llama-swap
```

### Option A: Ollama

```bash
ollama pull qwen3:14b
systemctl --user restart llama-swap
```

The autoscan will:
1. Read the Ollama manifest to find the GGUF blob
2. Create a symlink `~/models/Qwen3-14B-Q8_0.gguf` → Ollama blob
3. Run a 6-second compatibility test with llama-server
4. Write an entry to `~/.config/llama-swap/config.yaml`
5. Update the `groups.main.members` list in the config

> **Limitation:** Vision-Language (VL) models pulled via Ollama (e.g. `qwen3-vl`)
> are not compatible with llama-server. Ollama's GGUF blobs omit the MRoPE
> metadata key that llama.cpp requires. The autoscan detects this automatically
> and adds the model to the skip list with a hint. Use Option B for VL models.

### Option B: HuggingFace

```bash
# Install the HF CLI (one-time, includes the 'hf' command)
pip install huggingface_hub

# Download a model (lands in ~/.cache/huggingface/hub/)
hf download Qwen/Qwen3-14B-GGUF --include "Qwen3-14B-Q8_0.gguf"

# VL model with projector (mmproj)
hf download Qwen/Qwen3-VL-8B-Instruct-GGUF \
    --include "Qwen3-VL-8B-Instruct-Q4_K_M.gguf" "mmproj-Qwen3-VL-8B-Instruct-F16.gguf"

systemctl --user restart llama-swap
```

The autoscan will:
1. Scan `~/.cache/huggingface/hub/` for GGUFs in the active snapshot
2. Create a symlink `~/models/Qwen3-14B-Q8_0.gguf` → HF cache path
3. Run the compatibility test and write the YAML entry
4. Update the `groups.main.members` list in the config

VL models are detected automatically when a matching `mmproj-*.gguf` file is
present in the same HF snapshot. The YAML entry will include `--mmproj` automatically.

### Option C: Manual GGUF

```bash
# Drop the file directly into ~/models/
cp /path/to/Model.gguf ~/models/

# Or create a symlink
ln -s /path/to/Model.gguf ~/models/Model.gguf

systemctl --user restart llama-swap
```

### Why ~/models/?

This directory acts as a **unified namespace** for all model sources:
- Ollama blobs have SHA256 hash names (`sha256-6335adf...`) — unusable directly
  in the YAML config
- HuggingFace cache paths are long and nested
  (`~/.cache/huggingface/hub/models--Qwen--Qwen3-14B-GGUF/snapshots/{hash}/...`)
- Manual GGUFs need a defined home

The autoscan always scans `~/models/` and writes `~/models/Name.gguf` into the
YAML. All three sources flow through this namespace via symlinks.

---

## 7. Start and verify

```bash
# Start llama-swap (autoscan runs as part of startup)
systemctl --user start llama-swap

# Watch the autoscan output
journalctl --user -u llama-swap -b | head -60

# Check available models
curl -s http://localhost:11435/v1/models | python3 -m json.tool

# Start AIfred
systemctl --user start aifred-intelligence
```

Typical autoscan output:
```
=== llama-swap Autoscan ===

Scanning Ollama models...
  + Symlink: Qwen3-14B-Q8_0.gguf → sha256-6335adf...
  = Exists:  Qwen3-8B-Q4_K_M.gguf
  ~ Skip:    nomic-embed-text-v2-moe (embedding model)
  3 Ollama models found, 1 new symlinks created

Scanning HuggingFace cache...
  No HuggingFace cache found or empty.

Scanning ~/models/ for GGUFs...
  Found 5 GGUFs, 1 new

Testing new models for llama-server compatibility...
  ✓ Qwen3-14B-Q8_0 (OK)

Updating llama-swap-config.yaml...
  + Added: Qwen3-14B-Q8_0 (native context: 40960)

Updating VRAM cache...
  + Added: Qwen3-14B-Q8_0

Done. 1 model(s) added to config, 1 VRAM cache entries created.
Groups updated: main → [Qwen3-14B-Q8_0, Qwen3-8B-Q4_K_M]
```

---

## 8. VRAM calibration

New models are added with their **native context** from the GGUF metadata.
This is often larger than what actually fits in VRAM.

To calibrate in the AIfred UI:
1. Select the new model in AIfred
2. Click **"Calibrate"** in the debug panel at the bottom
3. The algorithm runs a binary search to find the true maximum context
4. Results are saved to `data/model_vram_cache.json` and the YAML is updated

Without calibration the model still works — it runs with the native context.
If that exceeds VRAM, the first request will fail with an OOM error.

---

## 9. Troubleshooting

### Model does not appear in AIfred

```bash
# Check the YAML
cat ~/.config/llama-swap/config.yaml

# Check autoscan output
journalctl --user -u llama-swap -b | grep -A5 "Autoscan"

# Run autoscan manually
source ~/Projekte/AIfred-Intelligence/venv/bin/activate
python ~/Projekte/AIfred-Intelligence/scripts/llama-swap-autoscan.py
```

### Model ended up in the skip list

```bash
cat ~/.config/llama-swap/autoscan-skip.json
# Remove the entry to re-test after a llama.cpp update:
nano ~/.config/llama-swap/autoscan-skip.json
systemctl --user restart llama-swap
```

### llama-server binary not found

The autoscan reads the binary path from existing YAML entries. If no entries exist
yet, it falls back to `~/llama.cpp/build/bin/llama-server`. If the binary is
elsewhere, add a temporary entry with the correct path:

```yaml
# ~/.config/llama-swap/config.yaml
models:
  _dummy:
    cmd: /your/path/to/llama-server --port ${PORT} --model /dev/null
    ttl: 1
```

Run autoscan once, then remove the `_dummy` entry.

### OOM crash / context too large

```bash
# Run calibration in AIfred UI, or reduce the context manually:
nano ~/.config/llama-swap/config.yaml
# Adjust the -c parameter for the affected model
systemctl --user restart llama-swap
```

---

## Related documents

- [llamacpp-setup.md](llamacpp-setup.md) — Hardware benchmarks, performance flags,
  multi-GPU configuration, Flash Attention details
