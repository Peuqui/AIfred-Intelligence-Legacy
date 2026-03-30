#!/bin/bash
# Detect the fastest GPU by VRAM size (largest = fastest in our setup)
# Writes FASTEST_GPU_ID to .env files for docker-compose

FASTEST_GPU_ID=$(nvidia-smi --query-gpu=index,memory.total --format=csv,noheader,nounits | sort -t',' -k2 -rn | head -1 | cut -d',' -f1 | tr -d ' ')

if [ -z "$FASTEST_GPU_ID" ]; then
    echo "No GPU detected, defaulting to 0"
    FASTEST_GPU_ID=0
fi

GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader -i "$FASTEST_GPU_ID" | tr -d ' ')
echo "Fastest GPU: index=$FASTEST_GPU_ID ($GPU_NAME)"

# Write .env for each TTS docker-compose directory
for dir in xtts moss-tts; do
    ENV_FILE="$(dirname "$0")/$dir/.env"
    if [ -f "$ENV_FILE" ]; then
        # Update existing FASTEST_GPU_ID or append
        if grep -q "FASTEST_GPU_ID" "$ENV_FILE"; then
            sed -i "s/FASTEST_GPU_ID=.*/FASTEST_GPU_ID=$FASTEST_GPU_ID/" "$ENV_FILE"
        else
            echo "FASTEST_GPU_ID=$FASTEST_GPU_ID" >> "$ENV_FILE"
        fi
    else
        echo "FASTEST_GPU_ID=$FASTEST_GPU_ID" > "$ENV_FILE"
    fi
    echo "  → $ENV_FILE: FASTEST_GPU_ID=$FASTEST_GPU_ID"
done
