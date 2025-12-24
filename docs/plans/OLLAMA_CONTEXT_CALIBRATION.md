# Ollama Auto-Context Calibration

**Status:** Implementiert
**Version:** 2.0 (mit RoPE 2x Unterstützung)
**Erstellt:** 2025-12-24
**Aktualisiert:** 2025-12-24

## Overview

Automatic determination of maximum context window without CPU offloading for Ollama models.
Supports dual calibration modes: Native and RoPE 2x Extended.

---

## Core Concept

### `/api/ps` Response contains the key information:
```json
{
  "models": [{
    "name": "qwen3:14b",
    "size": 8900000000,        // Total memory (can be CPU+GPU)
    "size_vram": 8900000000,   // GPU memory ONLY
    "context_length": 81920    // Currently loaded context
  }]
}
```

**Rule:** `size == size_vram` → Model completely in VRAM, no CPU offload

---

## Features

### Dual Calibration System

| Mode | Description | Target |
|------|-------------|--------|
| **Native** | Calibrates up to model's native context limit | `max_context_gpu_only` |
| **RoPE 2x** | Calibrates up to 2x native limit (RoPE scaling) | `max_context_extended` |

### Per-Model Toggle

- Each model stores its own `use_extended` setting in the VRAM cache
- Toggle automatically loads when switching models
- UI reflects current model's setting

---

## Algorithm: Binary Search

```
Input: model_name, target_context (native or 2x native)
Output: max_context that fits in VRAM

1. low = 4096, high = target_context
2. Unload all models for clean VRAM measurement
3. Load model with num_ctx = mid
4. Query /api/ps → compare size vs size_vram
5. IF size == size_vram:
     result = mid
     low = mid  # Can fit more
   ELSE:
     high = mid  # CPU offload detected, reduce
6. REPEAT until converged
7. Save result to model_vram_cache.json
```

---

## Implementation

### Key Files

| File | Purpose |
|------|---------|
| `aifred/lib/model_vram_cache.py` | Cache functions for calibration data + per-model toggle |
| `aifred/backends/ollama.py` | `calibrate_max_context()`, `_is_fully_in_vram()` |
| `aifred/lib/gpu_utils.py` | `calculate_vram_based_context()` - reads toggle from cache |
| `aifred/state.py` | `calibrate_context()`, `set_calibrate_extended()` |
| `aifred/aifred.py` | Calibration button + RoPE 2x toggle in LLM settings |

### Cache Structure

```json
{
  "qwen3:14b": {
    "backend": "ollama",
    "native_context": 40960,
    "gpu_model": "NVIDIA GeForce RTX 3090 Ti",
    "use_extended": true,
    "ollama_calibrations": [
      {
        "max_context_gpu_only": 40960,
        "measured_at": "2025-12-24T18:22:57"
      },
      {
        "max_context_extended": 81920,
        "measured_at": "2025-12-24T18:36:21"
      }
    ]
  }
}
```

---

## UI Integration

### LLM Parameters Section

```
┌─────────────────────────────────────────┐
│ Context                                 │
│ ○ Auto  ○ Manual                        │
│                                         │
│ [Context kalibrieren] □ RoPE bis 2x     │
│                                         │
│ (Button shows "Kalibriere..." during    │
│  calibration with progress in debug)    │
└─────────────────────────────────────────┘
```

### Debug Console Output

```
18:36:09 | 🎚️ Calibration mode: RoPE 2x
18:36:12 | 🔧 Starting RoPE 2x calibration for qwen3:14b...
18:36:12 | 📊 RoPE 2x calibration: target 81.920 tok
18:36:12 | 📊 Native context: 40.960 tok
18:36:12 | 📊 Unloading all models...
18:36:14 | 📊 [1] Testing 80k...
18:36:21 | 📊 ✓ 80k fits in VRAM
18:36:21 | 📊 ✅ Calibrated (RoPE 2x): 81.920 tok
18:36:21 |    → Value will be used automatically on next inference
```

---

## Usage Flow

### 1. Initial Calibration

1. Select model in dropdown
2. Toggle "RoPE bis 2x" if desired (optional)
3. Click "Context kalibrieren"
4. Wait for binary search to complete
5. Calibrated value is saved and used automatically

### 2. Switching Models

- Toggle state automatically loads from cache
- If model has no calibration, warning appears in debug

### 3. Inference

- `gpu_utils.py` reads `use_extended` from cache
- Uses `max_context_extended` or `max_context_gpu_only` accordingly
- Falls back to dynamic VRAM calculation if no calibration exists

---

## Warnings

When toggling without calibration:
```
⚠️ No RoPE 2x calibration found - please calibrate first!
⚠️ No native calibration found - please calibrate first!
```

---

## Related Documentation

- [ollama-context-calculation.md](../architecture/ollama-context-calculation.md) - Technical flow details
- [LLM_PARAMETERS.md](../llm/LLM_PARAMETERS.md) - num_ctx parameter documentation

---

**Implemented:** 2025-12-24
