#!/bin/bash
# Test mit FIXEN GPU Layers (49) statt Auto-Detect
# Ziel: Maximalen Context bei minimalem freien VRAM finden

MODEL="/home/mp/models/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf"
KCPP="/usr/local/bin/koboldcpp"
PORT=5001
RESULTS="/tmp/max_context_fixed_layers.csv"

echo "=========================================="
echo "  Maximum Context Test (Fixed 49 Layers)"
echo "=========================================="
echo ""

echo "Test,Context,VRAM_Used_MB,VRAM_Free_MB,GPU_Layers,Status" > "$RESULTS"

cleanup() {
    pkill -9 -f "koboldcpp.*gguf" 2>/dev/null || true
    sleep 2
}

test_ctx() {
    local ctx=$1

    echo ""
    echo "Testing Context: $ctx tokens (ALL 49 layers forced)..."
    cleanup

    "$KCPP" "$MODEL" --port $PORT --contextsize $ctx --gpulayers 49 --usecuda --blasbatchsize 512 --quantkv 2 --flashattention > /tmp/kcpp_max_fixed.log 2>&1 &
    local pid=$!

    # Wait
    for i in {1..120}; do
        if curl -s http://127.0.0.1:$PORT/api/v1/model >/dev/null 2>&1; then
            sleep 3
            local vram=$(nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits)
            local used=$(echo "$vram" | cut -d',' -f1 | xargs)
            local free=$(echo "$vram" | cut -d',' -f2 | xargs)

            # Check actual layers from log
            local gpu_layers=$(grep "offloaded.*layers" /tmp/kcpp_max_fixed.log | tail -1 | grep -oP '\d+(?=/49)' || echo "49")

            echo "✅ Context: $ctx | VRAM: ${used}MB used, ${free}MB free | GPU Layers: $gpu_layers"
            echo "$ctx,$ctx,$used,$free,$gpu_layers,SUCCESS" >> "$RESULTS"

            cleanup
            return 0
        fi
        if ! kill -0 $pid 2>/dev/null; then
            echo "❌ FAILED (OOM or crash)"
            echo "$ctx,$ctx,N/A,N/A,N/A,FAILED" >> "$RESULTS"
            cleanup
            return 1
        fi
        sleep 1
    done

    echo "❌ TIMEOUT"
    cleanup
    return 1
}

# Test Sequenz: Finde den Sweet Spot wo wir <1GB frei haben
echo "Finding maximum context with <1GB free VRAM..."
echo ""

# Start bei 32K (wir wissen das funktioniert)
# Dann inkrementell hochgehen

for ctx in 40000 50000 60000 70000 75000 80000 85000 90000; do
    if test_ctx $ctx; then
        local free=$(tail -1 "$RESULTS" | cut -d',' -f4)
        echo "→ $ctx tokens: ${free}MB free"

        # Wenn weniger als 800MB frei, sind wir am Ziel
        if [ "$free" -lt 800 ] && [ "$free" != "N/A" ]; then
            echo ""
            echo "🎯 OPTIMAL gefunden bei $ctx tokens mit ${free}MB frei!"
            break
        fi
    else
        echo "→ $ctx tokens: FAILED - limit reached"
        break
    fi
done

echo ""
echo "=========================================="
echo "  Results:"
echo "=========================================="
column -t -s',' "$RESULTS"
echo ""
echo "Full results: $RESULTS"
