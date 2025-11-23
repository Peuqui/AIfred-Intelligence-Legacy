#!/bin/bash
# Single KoboldCPP Configuration Test
# Usage: ./test_single_config.sh <context> <quantkv> <flashattn> <batch>
# Example: ./test_single_config.sh 65536 2 yes 512

CONTEXT=${1:-67139}
QUANTKV=${2:-2}
FLASH=${3:-yes}
BATCH=${4:-512}

MODEL="/home/mp/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
KCPP="/usr/local/bin/koboldcpp"

echo "======================================================"
echo "  Testing: Context=$CONTEXT, QuantKV=$QUANTKV, Flash=$FLASH, Batch=$BATCH"
echo "======================================================"
echo ""

# Build command
CMD="$KCPP \"$MODEL\" --port 5001 --contextsize $CONTEXT --gpulayers -1 --usecublas --blasbatchsize $BATCH --quantkv $QUANTKV"
if [ "$FLASH" == "yes" ]; then
    CMD="$CMD --flashattention"
fi

# Baseline
echo "VRAM before:"
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
echo ""

# Start KoboldCPP
echo "Starting KoboldCPP..."
eval "$CMD" > /tmp/kcpp_single_test.log 2>&1 &
PID=$!

# Wait for ready
echo "Waiting for server..."
for i in {1..120}; do
    if curl -s http://127.0.0.1:5001/api/v1/model >/dev/null 2>&1; then
        echo "✅ Server ready!"
        break
    fi
    sleep 1
done

# Measure VRAM
echo ""
echo "VRAM after startup:"
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
echo ""

# Run inference
echo "Running test inference..."
curl -s http://127.0.0.1:5001/v1/completions \
    -H "Content-Type: application/json" \
    -d '{"prompt": "def fibonacci(n):", "max_tokens": 50}' >/dev/null

sleep 2

echo "VRAM during inference:"
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
echo ""

echo "Press Enter to stop server and continue..."
read

# Cleanup
kill $PID 2>/dev/null
sleep 2
pkill -f koboldcpp || true

echo "Test complete!"
