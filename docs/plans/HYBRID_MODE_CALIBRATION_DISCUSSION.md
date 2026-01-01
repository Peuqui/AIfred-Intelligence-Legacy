# Hybrid Mode Calibration: Discussion and Options

**Date:** 2025-12-29
**Status:** Discussion / Not yet implemented

## Background

The current calibration works as follows:
1. **GPU-only first**: Attempts to find maximum context purely in VRAM
2. **Automatic Hybrid Fallback**: If the model doesn't fit in VRAM at all (120B, 70B), it automatically switches to hybrid mode
3. **No optional Hybrid**: Models that *just barely* fit in VRAM (e.g., 32B with 40K context) are not offered hybrid mode

## The Problem

Example: `qwen3:32b`
- Fits completely in VRAM (18.8 GB)
- Calibrates to ~40,960 tokens (GPU-only)
- Could potentially reach 80-100K tokens with hybrid mode
- **But**: The user has no way to choose this

Larger models with small GPU-only context could benefit from hybrid, but the user doesn't know this and has no option to activate it.

## Possible Solutions

### Option A: "Extended Calibration" Button

```
[Calibrate] [Calibrate Hybrid]
```

- Separate button for hybrid calibration
- User consciously decides: "I want more context, accept slower performance"

| Pro | Con |
|-----|-----|
| Explicit user control | Increased UI complexity |
| Easy to understand | Two buttons for similar function |

---

### Option B: Automatic Hybrid Recommendation

After GPU-only calibration:
```
GPU-only: 40,960 tok
With Hybrid mode ~95,000 tok would be possible
   [Calibrate Hybrid?]
```

- System calculates whether hybrid would be worthwhile
- Shows potential gain

| Pro | Con |
|-----|-----|
| Informs user about possibilities | More logic needed |
| Unobtrusive | Estimate could be inaccurate |
| Only when relevant |  |

---

### Option C: Memory Mode Dropdown (similar to RoPE)

```
Memory Mode: [GPU-only]
             [GPU-only]
             [Hybrid (CPU+GPU)]
```

- Similar to the RoPE dropdown
- Per-model setting
- Calibrated values stored separately for each mode

| Pro | Con |
|-----|-----|
| Consistent UI (like RoPE) | Even more dropdowns in settings |
| Flexible per-model control | Could overwhelm users |
| Transparency | More complex state logic |

**Implementation:**
- New state field `aifred_memory_mode: str = "gpu"` (gpu/hybrid)
- VRAM cache stores both values: `max_context_gpu_only` and `max_context_hybrid`
- UI shows dropdown under model select (like RoPE)
- On change, the corresponding calibrated value is used

---

### Option D: Intelligent Auto-Decision

- System decides based on:
  - Available RAM
  - Gain from hybrid (>50% more context?)
  - Performance tradeoff

| Pro | Con |
|-----|-----|
| "It just works" | Less user control |
| No UI changes needed | Hard to predict |
|  | Magic behavior (undesirable) |

---

## Recommendation

**Option C (Memory Mode Dropdown)** appears most sensible:

1. **Consistency**: Matches the existing RoPE dropdown pattern
2. **Transparency**: User explicitly sees which mode they're using
3. **Flexibility**: Can be different per model
4. **Calibration**: Each mode has its own calibrated value

**Alternative**: Option B (recommendation after calibration) as a middle ground - shows the option without overloading the UI.

## Open Questions

1. Should hybrid mode be configurable per agent (AIfred, Sokrates, Salomo)?
2. How do we communicate the performance tradeoff to the user?
3. Do we need a "Reset to GPU-only" option if hybrid is too slow?
4. Should calibration determine both modes simultaneously or sequentially?

## Affected Files (estimated)

- `aifred/state.py` - New state fields, memory mode handling
- `aifred/aifred.py` - UI for memory mode dropdown
- `aifred/backends/ollama.py` - Extend calibration logic
- `aifred/lib/model_vram_cache.py` - New field for hybrid context
- `aifred/lib/gpu_utils.py` - Adjust calculate_vram_based_context
