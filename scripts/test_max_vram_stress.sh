#!/bin/bash
# Aggressive VRAM Stress Test mit längerer Inferenz
# Testet höhere Context-Größen UND längere Generation

MODEL="/home/mp/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
KCPP="/usr/local/bin/koboldcpp"
PORT=5001
RESULTS="/tmp/vram_stress_test.csv"

echo "=========================================="
echo "  VRAM Stress Test (High Context + Long Inference)"
echo "=========================================="
echo ""

echo "Test,Context,VRAM_Start_MB,VRAM_After_Inference_MB,VRAM_Free_MB,GPU_Layers,Status" > "$RESULTS"

cleanup() {
    pkill -9 -f "koboldcpp.*gguf" 2>/dev/null || true
    sleep 2
}

test_context_with_inference() {
    local ctx=$1

    echo ""
    echo "=========================================="
    echo "Testing Context: $ctx tokens (49 layers)"
    echo "=========================================="
    cleanup

    # Start KoboldCPP
    "$KCPP" "$MODEL" --port $PORT --contextsize $ctx --gpulayers 49 --usecuda --blasbatchsize 512 --quantkv 2 --flashattention > /tmp/kcpp_stress.log 2>&1 &
    local pid=$!

    # Wait for ready
    echo "Waiting for server..."
    for i in {1..120}; do
        if curl -s http://127.0.0.1:$PORT/api/v1/model >/dev/null 2>&1; then
            sleep 3

            # Measure VRAM at startup
            local vram_start=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits)
            local used_start=$(echo "$vram_start" | cut -d',' -f1 | xargs)
            local free_start=$(echo "$vram_start" | cut -d',' -f2 | xargs)

            echo "✅ Server ready!"
            echo "   VRAM at startup: ${used_start}MB used, ${free_start}MB free"

            # Check actual GPU layers
            local gpu_layers=$(grep "offloaded.*layers" /tmp/kcpp_stress.log | tail -1 | grep -oP '\d+(?=/49)' || echo "49")
            echo "   GPU Layers: $gpu_layers/49"

            # Run LONG inference (500 tokens)
            echo ""
            echo "Running LONG inference (500 tokens)..."
            echo "This will take a while..."

            local start_time=$(date +%s)
            curl -s http://127.0.0.1:$PORT/v1/completions \
                -H "Content-Type: application/json" \
                -d "{\"prompt\":\"Write a detailed explanation of how neural networks work, including backpropagation:\",\"max_tokens\":500,\"temperature\":0.7}" \
                > /tmp/inference_result.json
            local end_time=$(date +%s)
            local duration=$((end_time - start_time))

            echo "   Inference completed in ${duration}s"

            # Wait a bit for VRAM to settle
            sleep 5

            # Measure VRAM after inference
            local vram_after=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits)
            local used_after=$(echo "$vram_after" | cut -d',' -f1 | xargs)
            local free_after=$(echo "$vram_after" | cut -d',' -f2 | xargs)

            echo ""
            echo "   VRAM after inference: ${used_after}MB used, ${free_after}MB free"

            # Check if VRAM increased (memory leak?)
            local vram_diff=$((used_after - used_start))
            if [ $vram_diff -gt 100 ]; then
                echo "   ⚠️  VRAM increased by ${vram_diff}MB during inference!"
            else
                echo "   ✅ VRAM stable (diff: ${vram_diff}MB)"
            fi

            # Check for OOM in logs
            if grep -i "out of memory\|cuda error\|failed" /tmp/kcpp_stress.log > /dev/null 2>&1; then
                echo "   ❌ OOM or CUDA error detected!"
                echo "$ctx,$ctx,$used_start,$used_after,$free_after,$gpu_layers,FAILED_OOM" >> "$RESULTS"
                cleanup
                return 1
            fi

            echo "$ctx,$ctx,$used_start,$used_after,$free_after,$gpu_layers,SUCCESS" >> "$RESULTS"

            cleanup
            return 0
        fi

        if ! kill -0 $pid 2>/dev/null; then
            echo "❌ FAILED (process died)"
            echo "$ctx,$ctx,N/A,N/A,N/A,N/A,FAILED" >> "$RESULTS"
            cleanup
            return 1
        fi
        sleep 1
    done

    echo "❌ TIMEOUT"
    cleanup
    return 1
}

# Test progressively higher contexts
echo "Testing high context sizes with LONG inference..."
echo ""

for ctx in 90000 95000 100000 110000 120000 130000 140000 150000; do
    if test_context_with_inference $ctx; then
        echo "→ $ctx tokens: SUCCESS"
    else
        echo "→ $ctx tokens: FAILED - limit reached"
        echo ""
        echo "Maximum stable context found!"
        break
    fi
done

echo ""
echo "=========================================="
echo "  Final Results:"
echo "=========================================="
column -t -s',' "$RESULTS"
echo ""
echo "Full results: $RESULTS"
