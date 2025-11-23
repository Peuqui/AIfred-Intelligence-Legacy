#!/bin/bash
# KoboldCPP VRAM Quick Test - WORKING VERSION
set -e

MODEL_PATH="/home/mp/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
KOBOLDCPP_BIN="/usr/local/bin/koboldcpp"
PORT=5001
HOST="127.0.0.1"
RESULTS_FILE="/tmp/koboldcpp_vram_results.csv"

echo "=========================================="
echo "  KoboldCPP VRAM Test Suite"
echo "=========================================="
echo "Model: $(basename "$MODEL_PATH")"
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader)"
echo ""

# Initialize CSV
echo "Test,Context,QuantKV,FlashAttn,Batch,VRAM_Used_MB,VRAM_Free_MB,Status" > "$RESULTS_FILE"

cleanup() {
    echo "Stopping KoboldCPP..."
    pkill -9 -f "koboldcpp.*gguf" 2>/dev/null || true
    sleep 3
}

run_test() {
    local name=$1
    local ctx=$2
    local qkv=$3
    local flash=$4
    local batch=$5

    echo ""
    echo "=========================================="
    echo "TEST: $name"
    echo "  Context: $ctx, QuantKV: $qkv, Flash: $flash, Batch: $batch"
    echo "=========================================="

    cleanup

    # Build command and start
    echo "Starting KoboldCPP..."
    local model_path="$MODEL_PATH"
    if [ "$flash" == "yes" ]; then
        "$KOBOLDCPP_BIN" "$model_path" --port "$PORT" --host "$HOST" --contextsize "$ctx" --gpulayers -1 --usecublas --blasbatchsize "$batch" --quantkv "$qkv" --flashattention > /tmp/kcpp_output.log 2>&1 &
    else
        "$KOBOLDCPP_BIN" "$model_path" --port "$PORT" --host "$HOST" --contextsize "$ctx" --gpulayers -1 --usecublas --blasbatchsize "$batch" --quantkv "$qkv" > /tmp/kcpp_output.log 2>&1 &
    fi
    local pid=$!

    # Wait for server
    local ready=0
    for i in {1..120}; do
        if curl -s "http://$HOST:$PORT/api/v1/model" >/dev/null 2>&1; then
            ready=1
            break
        fi
        if ! kill -0 $pid 2>/dev/null; then
            echo "❌ Process died!"
            tail -20 /tmp/kcpp_output.log
            echo "$name,$ctx,$qkv,$flash,$batch,N/A,N/A,FAILED" >> "$RESULTS_FILE"
            return 1
        fi
        sleep 1
    done

    if [ $ready -eq 0 ]; then
        echo "❌ Timeout!"
        kill $pid 2>/dev/null || true
        echo "$name,$ctx,$qkv,$flash,$batch,N/A,N/A,TIMEOUT" >> "$RESULTS_FILE"
        return 1
    fi

    echo "✅ Server ready!"
    sleep 3

    # Measure VRAM
    local vram=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits)
    local used=$(echo "$vram" | cut -d',' -f1 | xargs)
    local free=$(echo "$vram" | cut -d',' -f2 | xargs)

    echo "VRAM: ${used}MB used, ${free}MB free"

    # Test inference
    echo "Running inference..."
    curl -s "http://$HOST:$PORT/v1/completions" \
        -H "Content-Type: application/json" \
        -d '{"prompt":"def fib(n):","max_tokens":50}' >/dev/null 2>&1 || true

    sleep 2

    # Measure during inference
    local vram2=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits)
    local used2=$(echo "$vram2" | cut -d',' -f1 | xargs)
    local free2=$(echo "$vram2" | cut -d',' -f2 | xargs)

    echo "VRAM (inference): ${used2}MB used, ${free2}MB free"

    # Save
    echo "$name,$ctx,$qkv,$flash,$batch,$used2,$free2,SUCCESS" >> "$RESULTS_FILE"

    cleanup
    return 0
}

# Run tests
echo ""
echo "Starting tests..."
echo ""

run_test "T1-Production" 67139 2 yes 512
run_test "T2-NoFlash" 32768 0 no 512
run_test "T3-Q8" 49152 1 yes 512
run_test "T4-MaxContext" 73728 2 yes 512
run_test "T5-SmallBatch" 67139 2 yes 256
run_test "T6-LargeBatch" 67139 2 yes 1024
run_test "T7-Conservative" 16384 2 yes 512
run_test "T8-Aggressive" 81920 2 yes 512

echo ""
echo "=========================================="
echo "  All Tests Complete!"
echo "=========================================="
echo ""
column -t -s',' "$RESULTS_FILE"
echo ""
echo "Results saved to: $RESULTS_FILE"
