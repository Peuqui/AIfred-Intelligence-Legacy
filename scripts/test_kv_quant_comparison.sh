#!/bin/bash
# Comprehensive KV Cache Quantization Comparison
# Tests FP16, Q8, Q6, Q4 with various context sizes

MODEL="/home/mp/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
KCPP="/usr/local/bin/koboldcpp"
PORT=5001
RESULTS="/tmp/kv_quant_results.csv"

echo "=========================================="
echo "  KV Cache Quantization Comparison"
echo "=========================================="
echo ""

echo "Test,Context,KV_Quant,VRAM_Used_MB,VRAM_Free_MB,GPU_Layers,Status" > "$RESULTS"

cleanup() {
    pkill -9 -f "koboldcpp.*gguf" 2>/dev/null || true
    sleep 2
}

test_config() {
    local name=$1
    local ctx=$2
    local qkv=$3
    local qkv_name=$4

    echo ""
    echo "==========================================  "
    echo "TEST: $name"
    echo "  Context: $ctx, KV Quant: $qkv_name"
    echo "=========================================="

    cleanup

    "$KCPP" "$MODEL" --port $PORT --contextsize $ctx --gpulayers -1 --usecuda --blasbatchsize 512 --quantkv $qkv --flashattention > /tmp/kcpp_kv_test.log 2>&1 &
    local pid=$!

    # Wait
    for i in {1..120}; do
        if curl -s http://127.0.0.1:$PORT/api/v1/model >/dev/null 2>&1; then
            sleep 3

            # Get VRAM
            local vram=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits)
            local used=$(echo "$vram" | cut -d',' -f1 | xargs)
            local free=$(echo "$vram" | cut -d',' -f2 | xargs)

            # Get GPU layers from log
            local gpu_layers=$(grep "gpulayers=" /tmp/kcpp_kv_test.log | tail -1 | sed 's/.*gpulayers=\([0-9]*\).*/\1/')

            echo "✅ VRAM: ${used}MB used, ${free}MB free, GPU Layers: $gpu_layers"
            echo "$name,$ctx,$qkv_name,$used,$free,$gpu_layers,SUCCESS" >> "$RESULTS"

            cleanup
            return 0
        fi

        if ! kill -0 $pid 2>/dev/null; then
            echo "❌ FAILED (process died)"
            echo "$name,$ctx,$qkv_name,N/A,N/A,N/A,FAILED" >> "$RESULTS"
            cleanup
            return 1
        fi
        sleep 1
    done

    echo "❌ TIMEOUT"
    echo "$name,$ctx,$qkv_name,N/A,N/A,N/A,TIMEOUT" >> "$RESULTS"
    cleanup
    return 1
}

# Test matrix: Different contexts x Different quantizations
declare -A tests=(
    # 32K context
    ["32K-FP16"]="32768 0 FP16"
    ["32K-Q8"]="32768 1 Q8"
    ["32K-Q4"]="32768 2 Q4"

    # 64K context
    ["64K-FP16"]="65536 0 FP16"
    ["64K-Q8"]="65536 1 Q8"
    ["64K-Q4"]="65536 2 Q4"

    # 96K context
    ["96K-FP16"]="98304 0 FP16"
    ["96K-Q8"]="98304 1 Q8"
    ["96K-Q4"]="98304 2 Q4"

    # 128K context
    ["128K-FP16"]="131072 0 FP16"
    ["128K-Q8"]="131072 1 Q8"
    ["128K-Q4"]="131072 2 Q4"

    # 160K context
    ["160K-FP16"]="163840 0 FP16"
    ["160K-Q8"]="163840 1 Q8"
    ["160K-Q4"]="163840 2 Q4"

    # 192K context
    ["192K-FP16"]="196608 0 FP16"
    ["192K-Q8"]="196608 1 Q8"
    ["192K-Q4"]="196608 2 Q4"

    # Maximum (256K - model native limit)
    ["256K-Q8"]="262144 1 Q8"
    ["256K-Q4"]="262144 2 Q4"
)

echo "Running comprehensive KV quantization tests..."
echo "Total tests: ${#tests[@]}"
echo ""

# Run all tests
for test_name in "${!tests[@]}"; do
    IFS=' ' read -r ctx qkv qkv_name <<< "${tests[$test_name]}"
    test_config "$test_name" "$ctx" "$qkv" "$qkv_name"
done

echo ""
echo "=========================================="
echo "  All Tests Complete!"
echo "=========================================="
echo ""
column -t -s',' "$RESULTS"
echo ""
echo "Full results saved to: $RESULTS"
