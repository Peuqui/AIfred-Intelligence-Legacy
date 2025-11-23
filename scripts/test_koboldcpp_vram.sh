#!/bin/bash
# KoboldCPP VRAM Usage Test Script
# Systematically tests different parameter combinations and measures VRAM usage

set -e

# Configuration
MODEL_PATH="/home/mp/.cache/lm-studio/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
KOBOLDCPP_BIN="/home/mp/.cache/koboldcpp/koboldcpp-linux-x64-cuda1240"
PORT=5001
HOST="127.0.0.1"
RESULTS_FILE="/tmp/koboldcpp_vram_test_results.csv"
GPU_ID=0

# Test parameters
declare -a CONTEXT_SIZES=(8192 16384 32768 65536)
declare -a QUANTKV_LEVELS=(0 1 2)  # 0=FP16, 1=Q8, 2=Q4
declare -a BATCH_SIZES=(128 256 512 1024)
declare -a FLASH_ATTENTION_OPTIONS=("enabled" "disabled")

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "  KoboldCPP VRAM Usage Test Suite"
echo "=================================================="
echo ""
echo "Model: $(basename "$MODEL_PATH")"
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader -i $GPU_ID)"
echo "Results: $RESULTS_FILE"
echo ""

# Initialize results file
echo "Test#,ContextSize,QuantKV,FlashAttn,BatchSize,VRAM_Used_MB,VRAM_Free_MB,Startup_Time_Sec,Status,Error" > "$RESULTS_FILE"

# Function to get VRAM usage
get_vram_usage() {
    nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits -i $GPU_ID
}

# Function to kill any running KoboldCPP instances
cleanup_koboldcpp() {
    echo -e "${YELLOW}[CLEANUP]${NC} Killing any running KoboldCPP instances..."
    pkill -f koboldcpp || true
    sleep 3
}

# Function to wait for server ready
wait_for_server() {
    local timeout=$1
    local start_time=$(date +%s)

    while true; do
        if curl -s "http://${HOST}:${PORT}/api/v1/model" >/dev/null 2>&1; then
            return 0
        fi

        local current_time=$(date +%s)
        local elapsed=$((current_time - start_time))

        if [ $elapsed -ge $timeout ]; then
            return 1
        fi

        sleep 1
    done
}

# Function to run a single test
run_test() {
    local test_num=$1
    local context_size=$2
    local quantkv=$3
    local flash_attn=$4
    local batch_size=$5

    echo ""
    echo -e "${GREEN}[TEST $test_num]${NC} Context=$context_size, QuantKV=$quantkv, FlashAttn=$flash_attn, Batch=$batch_size"

    # Build command
    local cmd="$KOBOLDCPP_BIN \"$MODEL_PATH\" --port $PORT --host $HOST --contextsize $context_size --gpulayers -1 --usecublas --blasbatchsize $batch_size --quantkv $quantkv"

    if [ "$flash_attn" == "enabled" ]; then
        cmd="$cmd --flashattention"
    fi

    # Get baseline VRAM before starting
    local vram_before=$(get_vram_usage)
    echo "  VRAM before: $vram_before"

    # Start KoboldCPP in background
    local start_time=$(date +%s)
    echo "  Starting KoboldCPP..."
    eval "$cmd" > /tmp/koboldcpp_test_output.log 2>&1 &
    local pid=$!

    # Wait for server to be ready (90 second timeout)
    if wait_for_server 90; then
        local end_time=$(date +%s)
        local startup_time=$((end_time - start_time))

        # Server is ready, measure VRAM
        sleep 2  # Let VRAM settle
        local vram_after=$(get_vram_usage)
        local vram_used=$(echo "$vram_after" | cut -d',' -f1 | xargs)
        local vram_free=$(echo "$vram_after" | cut -d',' -f2 | xargs)

        echo -e "  ${GREEN}✅ SUCCESS${NC} - VRAM: ${vram_used}MB used, ${vram_free}MB free, Startup: ${startup_time}s"

        # Run a test inference to measure VRAM during generation
        echo "  Running test inference..."
        curl -s "http://${HOST}:${PORT}/v1/completions" \
            -H "Content-Type: application/json" \
            -d '{
                "prompt": "What is the capital of France?",
                "max_tokens": 50,
                "temperature": 0.7
            }' > /dev/null 2>&1 || true

        # Measure VRAM during inference
        sleep 1
        local vram_during=$(get_vram_usage)
        local vram_used_infer=$(echo "$vram_during" | cut -d',' -f1 | xargs)
        local vram_free_infer=$(echo "$vram_during" | cut -d',' -f2 | xargs)

        echo "  VRAM during inference: ${vram_used_infer}MB used, ${vram_free_infer}MB free"

        # Save results
        echo "$test_num,$context_size,$quantkv,$flash_attn,$batch_size,$vram_used_infer,$vram_free_infer,$startup_time,SUCCESS," >> "$RESULTS_FILE"

    else
        local end_time=$(date +%s)
        local startup_time=$((end_time - start_time))

        echo -e "  ${RED}❌ FAILED${NC} - Server did not start within 90 seconds"

        # Check for OOM or other errors
        local error_msg=""
        if grep -q "out of memory" /tmp/koboldcpp_test_output.log; then
            error_msg="OOM"
        elif grep -q "CUDA error" /tmp/koboldcpp_test_output.log; then
            error_msg="CUDA_ERROR"
        else
            error_msg="TIMEOUT"
        fi

        echo "$test_num,$context_size,$quantkv,$flash_attn,$batch_size,N/A,N/A,$startup_time,FAILED,$error_msg" >> "$RESULTS_FILE"
    fi

    # Cleanup
    cleanup_koboldcpp
}

# Main test loop
test_num=1
total_tests=$((${#CONTEXT_SIZES[@]} * ${#QUANTKV_LEVELS[@]} * ${#FLASH_ATTENTION_OPTIONS[@]} * ${#BATCH_SIZES[@]}))

echo "=================================================="
echo "  Starting $total_tests tests..."
echo "=================================================="

for context_size in "${CONTEXT_SIZES[@]}"; do
    for quantkv in "${QUANTKV_LEVELS[@]}"; do
        for flash_attn in "${FLASH_ATTENTION_OPTIONS[@]}"; do
            for batch_size in "${BATCH_SIZES[@]}"; do

                # Skip invalid combinations
                if [ $quantkv -gt 0 ] && [ "$flash_attn" == "disabled" ]; then
                    echo ""
                    echo -e "${YELLOW}[SKIP $test_num]${NC} QuantKV=$quantkv requires FlashAttention"
                    test_num=$((test_num + 1))
                    continue
                fi

                run_test $test_num $context_size $quantkv $flash_attn $batch_size
                test_num=$((test_num + 1))

                # Brief pause between tests
                sleep 2
            done
        done
    done
done

echo ""
echo "=================================================="
echo "  Test Suite Complete!"
echo "=================================================="
echo ""
echo "Results saved to: $RESULTS_FILE"
echo ""
echo "Summary:"
column -t -s',' "$RESULTS_FILE" | head -20
echo ""
echo "To view full results:"
echo "  cat $RESULTS_FILE"
echo "  or"
echo "  column -t -s',' $RESULTS_FILE"
