#!/bin/bash
# Aggressive VRAM Maximization Test
# Target: Only 500-800MB free VRAM

MODEL="/home/mp/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
KCPP="/usr/local/bin/koboldcpp"
PORT=5001

echo "=========================================="
echo "  Aggressive VRAM Maximization Test"
echo "  Target: 500-800MB free VRAM"
echo "=========================================="
echo ""

cleanup() {
    pkill -9 -f "koboldcpp.*gguf" 2>/dev/null || true
    sleep 2
}

test_context() {
    local ctx=$1
    echo ""
    echo "Testing Context: $ctx tokens..."
    cleanup

    "$KCPP" "$MODEL" --port $PORT --contextsize $ctx --gpulayers -1 --usecublas --blasbatchsize 512 --quantkv 2 --flashattention > /tmp/kcpp_max.log 2>&1 &
    local pid=$!

    # Wait for ready
    for i in {1..120}; do
        if curl -s http://127.0.0.1:$PORT/api/v1/model >/dev/null 2>&1; then
            sleep 3
            local vram=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits)
            local used=$(echo "$vram" | cut -d',' -f1 | xargs)
            local free=$(echo "$vram" | cut -d',' -f2 | xargs)
            echo "✅ SUCCESS: ${used}MB used, ${free}MB free"
            cleanup
            return 0
        fi
        if ! kill -0 $pid 2>/dev/null; then
            echo "❌ FAILED: Process died (OOM?)"
            tail -20 /tmp/kcpp_max.log | grep -i "error\|memory\|failed" || echo "(no error found)"
            cleanup
            return 1
        fi
        sleep 1
    done

    echo "❌ TIMEOUT"
    cleanup
    return 1
}

# Binary search for maximum context
# Start: 81920 works, let's try higher
echo "Starting binary search for maximum context..."
echo ""

# Try progressively larger contexts
for ctx in 90000 100000 110000 120000 130000 140000 150000; do
    if test_context $ctx; then
        echo "→ $ctx tokens: SUCCESS"
    else
        echo "→ $ctx tokens: FAILED"
        echo ""
        echo "Maximum found around previous value"
        break
    fi
done

echo ""
echo "=========================================="
echo "  Finding exact maximum..."
echo "=========================================="

# Fine-tune around the limit
for ctx in 145000 142000 141000 140500; do
    if test_context $ctx; then
        echo "→ $ctx tokens: SUCCESS - checking higher..."
    else
        echo "→ $ctx tokens: FAILED - limit reached"
        break
    fi
done

echo ""
echo "Test complete! Check results above."
