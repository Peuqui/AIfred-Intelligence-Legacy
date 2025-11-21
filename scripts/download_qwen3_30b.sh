#!/bin/bash

# Download Qwen3-30B-A3B and Qwen3-4B models for vLLM and TabbyAPI
# Uses standard HuggingFace cache location: ~/.cache/huggingface

echo "=========================================="
echo "Downloading Qwen3 Models for vLLM & TabbyAPI"
echo "=========================================="

# Activate virtual environment
source ./venv/bin/activate

echo ""
echo "1/4: Downloading Qwen3-30B-A3B AWQ (vLLM) - ~18GB"
echo "   Model: cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit"
./venv/bin/python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(repo_id='cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit')
print('✅ Qwen3-30B-A3B AWQ downloaded')
"

echo ""
echo "2/4: Downloading Qwen3-4B AWQ (vLLM) - ~2.8GB"
echo "   Model: cpatonn/Qwen3-4B-Instruct-2507-AWQ-4bit"
./venv/bin/python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(repo_id='cpatonn/Qwen3-4B-Instruct-2507-AWQ-4bit')
print('✅ Qwen3-4B AWQ downloaded')
"

echo ""
echo "3/4: Downloading Qwen3-30B-A3B EXL3 (TabbyAPI) - ~18GB"
echo "   Model: turboderp/Qwen3-30B-A3B-exl3"
./venv/bin/python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(repo_id='turboderp/Qwen3-30B-A3B-exl3')
print('✅ Qwen3-30B-A3B EXL3 downloaded')
"

echo ""
echo "4/4: Downloading Qwen3-4B EXL3 (TabbyAPI) - ~2.8GB"
echo "   Model: ArtusDev/Qwen_Qwen3-4B-Instruct-2507-EXL3"
./venv/bin/python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(repo_id='ArtusDev/Qwen_Qwen3-4B-Instruct-2507-EXL3')
print('✅ Qwen3-4B EXL3 downloaded')
"

echo ""
echo "=========================================="
echo "✅ All models downloaded successfully!"
echo "=========================================="
echo ""
echo "Models are cached in: ~/.cache/huggingface/hub"
echo ""
echo "Next steps:"
echo "1. For vLLM:     vllm serve cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit"
echo "2. For TabbyAPI: Configure model_dir to ~/.cache/huggingface/hub"
