# Hybrid Mode (VRAM + RAM Offloading)

**Version:** 2.10.6+
**Status:** Production
**Backend:** Ollama only
**Feature:** Automatic detection and optimization

---

## Overview

Hybrid Mode is an automatic optimization technique used when LLM models are larger than available VRAM. Instead of failing or using a smaller model, AIfred calculates an optimal context window size that fits the model partially in VRAM and offloads the rest to RAM.

**Key Benefits:**
- Run larger models than VRAM capacity allows
- Automatic calculation - no manual configuration
- Optimizes for maximum context while preventing RAM exhaustion
- Graceful degradation with safety margins

**Example Scenario:**
```
Hardware: 1x RTX 3060 (12GB VRAM), 32GB RAM
Model: Qwen3:30B (~17GB)
Result: Model fits with ~8K context (VRAM + RAM hybrid)
Without Hybrid: Model would fail to load
```

---

## How It Works

### Traditional GPU-Only Mode

```
┌─────────────────────────────┐
│  GPU VRAM (24GB)            │
│                             │
│  Model Weights: 17GB        │
│  KV Cache: 5GB (32K ctx)    │
│  Overhead: 2GB              │
│                             │
│  Total: 24GB ✅             │
└─────────────────────────────┘
```

### Hybrid Mode (VRAM + RAM)

```
┌─────────────────────────────┐  ┌─────────────────────────────┐
│  GPU VRAM (12GB)            │  │  System RAM (32GB)          │
│                             │  │                             │
│  Model Weights: 10GB ─────────→ Model Weights: 7GB          │
│  KV Cache: 1.5GB (8K ctx)   │  │  KV Cache: (offload buffer) │
│  Overhead: 0.5GB            │  │  Free: 23GB (reserve: 4GB)  │
│                             │  │                             │
│  Total: 12GB ✅             │  │  Used: 9GB ✅               │
└─────────────────────────────┘  └─────────────────────────────┘
```

**Tradeoff:**
- Smaller context window than GPU-only
- Slightly slower inference (RAM access overhead)
- BUT: Model runs that otherwise wouldn't fit

---

## Automatic Detection

Hybrid Mode detection runs during **Ollama context calibration** (`calibrate_ollama_context`):

### Detection Logic

```python
# 1. Measure hardware
free_vram_mb = get_free_vram_mb()      # e.g., 12,000 MB
free_ram_mb = get_free_ram_mb()        # e.g., 30,000 MB
model_size_mb = model_size_bytes / MB  # e.g., 17,300 MB

# 2. Check if hybrid mode needed
if model_size_mb > free_vram_mb:
    # Model doesn't fit in VRAM alone
    if free_ram_mb is None:
        # Cannot measure RAM - fallback to binary search
        use_binary_search()
    else:
        # RAM measurable - use hybrid mode calculation
        use_hybrid_mode_calculation()
else:
    # Model fits in VRAM - use GPU-only mode
    use_gpu_only_calculation()
```

### Hybrid Mode Calculation

**Step 1: Calculate available memory for context**
```python
# Available VRAM for KV cache (after model weights)
vram_for_context = free_vram_mb - model_size_mb

# Available RAM for model overflow + reserve
dynamic_reserve = get_dynamic_ram_reserve(free_ram_mb)
ram_for_overflow = free_ram_mb - dynamic_reserve
```

**Step 2: Estimate context window**
```python
# Use conservative VRAM-to-context ratio
if is_moe_model(model):
    ratio = VRAM_CONTEXT_RATIO_MOE  # ~250 MB per 1K tokens
else:
    ratio = VRAM_CONTEXT_RATIO_DENSE  # ~180 MB per 1K tokens

# Calculate tokens (in thousands)
estimated_ctx_k = vram_for_context / ratio

# Apply RAM constraint
max_overflow_ctx_k = ram_for_overflow / ratio
total_ctx_k = min(estimated_ctx_k, max_overflow_ctx_k)

# Convert to tokens and clamp
calculated_ctx = int(total_ctx_k * 1024)
calculated_ctx = max(HYBRID_MIN_CONTEXT, calculated_ctx)  # At least 2K
calculated_ctx = min(calculated_ctx, native_ctx)          # At most native
```

**Step 3: Test and fine-tune**
```python
# Load model with calculated context
success = await preload_model(model, num_ctx=calculated_ctx)

if not success:
    # Fallback to minimum
    calculated_ctx = HYBRID_MIN_CONTEXT  # 2048 tokens

# Measure actual RAM usage
actual_free_ram = get_free_ram_mb()
difference = actual_free_ram - dynamic_reserve

if difference > 2048:  # More than 2GB headroom
    # Try increasing context by 25%
    increase_ctx = int(calculated_ctx * 1.25)
    test_and_adopt_if_successful(increase_ctx)

elif difference < 0:  # Below reserve
    # Reduce context by 25% iteratively
    reduce_ctx = int(calculated_ctx * 0.75)
    reduce_until_reserve_met_or_minimum(reduce_ctx)
```

---

## Configuration Parameters

### Constants (in `aifred/lib/config.py`)

```python
# Minimum context window for hybrid mode
HYBRID_MIN_CONTEXT = 2048  # 2K tokens (conservative fallback)

# Minimum RAM reserve to prevent swapping
RAM_RESERVE_MIN = 2048  # 2 GB minimum

# VRAM-to-context ratios (MB per 1K tokens)
VRAM_CONTEXT_RATIO_DENSE = 180  # Dense models (e.g., Llama, Qwen)
VRAM_CONTEXT_RATIO_MOE = 250    # MoE models (e.g., Qwen3-MoE)
```

### Dynamic RAM Reserve

**Purpose:** Leave enough RAM free to prevent swapping

**Calculation:**
```python
def get_dynamic_ram_reserve(free_ram_mb: float) -> float:
    """
    Scale reserve based on available RAM.

    More RAM = larger reserve (to be safe)
    Less RAM = smaller reserve (to maximize usage)
    """
    if free_ram_mb >= 64000:  # 64GB+
        return 8192  # 8 GB reserve
    elif free_ram_mb >= 32000:  # 32-64GB
        return 4096  # 4 GB reserve
    elif free_ram_mb >= 16000:  # 16-32GB
        return 3072  # 3 GB reserve
    else:  # <16GB
        return RAM_RESERVE_MIN  # 2 GB minimum
```

---

## Examples

### Example 1: RTX 3060 (12GB) + Qwen3:30B

**Scenario:**
```
Model: Qwen3:30B-A3B (~17GB)
VRAM: 12GB free
RAM: 32GB free
```

**Calculation:**
```python
# 1. Detect hybrid mode (model > VRAM)
model_size = 17,300 MB
free_vram = 12,000 MB
→ Hybrid mode needed

# 2. Calculate available memory
vram_for_context = 12,000 - 17,300 = -5,300 MB (negative!)
# Model overflows into RAM by ~5.3GB

dynamic_reserve = 4,096 MB (32GB RAM → 4GB reserve)
ram_for_overflow = 32,000 - 4,096 = 27,904 MB

# 3. Estimate context (MoE model)
ratio = 250 MB/K tokens
ram_overflow_ctx = 27,904 / 250 = 111K tokens
vram_ctx = 0 (no VRAM left for context)

# Conservative estimate considering model overflow
estimated_ctx = 8,192 tokens (8K)

# 4. Test and fine-tune
Load with 8K → Success ✅
Measure RAM: 23GB free (above 4GB reserve)
→ Try 10K → Success ✅
→ Final: 10,240 tokens (10K context)
```

**Result:**
```
✅ Hybrid Mode: 10K context
   VRAM: Model partially (7GB) + Overhead
   RAM: Model overflow (10GB) + Context buffer
   Usable: 10K tokens vs 0K without hybrid
```

### Example 2: Dual Tesla P40 (48GB) + Qwen3:120B

**Scenario:**
```
Model: Qwen3:120B (~70GB)
VRAM: 48GB free
RAM: 128GB free
```

**Calculation:**
```python
# 1. Detect hybrid mode
model_size = 70,000 MB
free_vram = 48,000 MB
→ Hybrid mode needed

# 2. Calculate
vram_for_context = 48,000 - 70,000 = -22,000 MB
# Massive overflow into RAM

dynamic_reserve = 8,192 MB (128GB → 8GB reserve)
ram_for_overflow = 128,000 - 8,192 = 119,808 MB

# 3. Estimate (Dense model)
ratio = 180 MB/K tokens
max_ctx = 119,808 / 180 = 665K tokens

# But realistic: Model overflow + context buffer
estimated_ctx = 7,402 tokens (native limit for this model)

# 4. Final
→ 7,402 tokens (native context, limited by model)
```

**Result:**
```
✅ Hybrid Mode: 7.4K context
   VRAM: Model partially (48GB)
   RAM: Model overflow (22GB) + Context buffer (1GB)
   Usable: Full native context despite insufficient VRAM
```

### Example 3: Failed Hybrid Mode

**Scenario:**
```
Model: Qwen3:120B (~70GB)
VRAM: 12GB free
RAM: 16GB free (too small!)
```

**Calculation:**
```python
# 1. Detect hybrid mode
model_size = 70,000 MB
free_vram = 12,000 MB
free_ram = 16,000 MB
→ Hybrid mode needed

# 2. Check feasibility
ram_for_overflow = 16,000 - 3,072 = 12,928 MB
model_overflow = 70,000 - 12,000 = 58,000 MB

# Model overflow (58GB) > Available RAM (13GB)
→ IMPOSSIBLE ❌

# 3. Fallback
Try HYBRID_MIN_CONTEXT (2K) → Likely fails
→ Model cannot load
```

**Result:**
```
❌ Hybrid Mode Failed: Insufficient RAM
   Model: 70GB
   VRAM: 12GB
   RAM: 13GB usable (after reserve)
   Needed: 58GB RAM overflow

   Recommendation: Use smaller model or add more RAM
```

---

## Debug Output

### Successful Hybrid Mode

```
17:05:03.187 | 📦 Model 'qwen3:30b' size: 17.3GB (context limit: 32,768 tokens)
17:05:05.311 | 🔄 Models unloaded: qwen3:4b, qwen3:30b
17:05:05.311 | ✅ VRAM released
17:05:05.312 | Model: 17.3 GB | VRAM: 12.0 GB | RAM: 30.0 GB
17:05:05.312 | ✅ Hybrid mode: Model (17.3 GB) > VRAM (12.0 GB) → using RAM (30.0 GB)
17:05:05.312 | → Calculated: 8.192 tokens (VRAM: -5.3 GB, RAM: 26.0 GB usable)
17:05:05.312 | → Loading with 8.192 tokens...
17:05:07.413 | ✅ Model loaded successfully
17:05:09.413 | → Actual RAM after load: 23.0 GB
17:05:09.413 | → Headroom detected - trying 10.240 tokens...
17:05:12.100 | ✅ Increased to 10.240 tokens
17:05:14.100 | → Final: VRAM 11.5 GB | RAM 20.5 GB free
17:05:14.101 | 🎯 Calibrated: 10.240 tok (measured max_context_hybrid)
```

### Failed Hybrid Mode

```
17:05:03.187 | 📦 Model 'qwen3:120b' size: 70.0GB (context limit: 7,402 tokens)
17:05:05.311 | Model: 70.0 GB | VRAM: 12.0 GB | RAM: 16.0 GB
17:05:05.312 | ⚠️ Model (70.0 GB) > VRAM (12.0 GB)
17:05:05.312 | ⚠️ Model overflow (58.0 GB) > Available RAM (13.0 GB)
17:05:05.312 | ❌ Hybrid mode impossible - model too large
17:05:05.312 | → Fallback to 2.048 tokens...
17:05:07.500 | ❌ Even 2.048 tokens failed
17:05:07.500 | __RESULT__:0
```

---

## Performance Characteristics

### Latency Impact

**GPU-Only Mode:**
```
Inference Speed: 100 tok/s (baseline)
TTFT: 0.3s
```

**Hybrid Mode (VRAM + RAM):**
```
Inference Speed: 60-80 tok/s (20-40% slower)
TTFT: 0.5-0.8s (RAM access overhead)
```

**Why slower:**
- Model weights split across VRAM and RAM
- RAM access is ~10x slower than VRAM
- PCIe transfer overhead for offloaded layers

### Memory Bandwidth

**VRAM (Tesla P40):**
- Bandwidth: 347 GB/s
- Latency: ~10ns

**DDR4-3200 RAM:**
- Bandwidth: 25.6 GB/s
- Latency: ~60ns

**Impact:**
- Layers in VRAM: Fast
- Layers in RAM: 10x slower
- Hybrid: Mixed performance based on layer distribution

---

## Limitations

1. **Ollama Only**
   - vLLM, TabbyAPI, KoboldCPP don't support auto hybrid mode
   - Those backends require manual layer splitting configuration

2. **Context Reduction**
   - Hybrid mode typically gives 25-50% of GPU-only context
   - Example: 32K GPU-only → 8-16K hybrid

3. **No Multi-GPU Hybrid**
   - Hybrid offloads to RAM, not to second GPU
   - Dual GPU still better than hybrid on single GPU

4. **RAM Speed Matters**
   - Faster RAM = better hybrid performance
   - DDR5 recommended over DDR4
   - Slow RAM can bottleneck inference

5. **Not All Models Benefit**
   - Small models (<12GB) don't need hybrid
   - Hybrid only helps when model > VRAM

---

## Recommendations

### When to Use Hybrid Mode

**Use hybrid if:**
- ✅ Model is 10-30% larger than VRAM
- ✅ You have sufficient RAM (2x model size recommended)
- ✅ You need that specific larger model
- ✅ Lower speed acceptable for better quality

**Avoid hybrid if:**
- ❌ Model is 2x+ larger than VRAM (too slow)
- ❌ You have limited RAM (<16GB)
- ❌ Speed is critical
- ❌ Smaller model gives acceptable results

### Optimization Tips

**1. Maximize VRAM:**
```bash
# Reduce Ollama overhead
export OLLAMA_GPU_OVERHEAD=536870912  # 512MB instead of 1GB
```

**2. Close other applications:**
```bash
# Free up RAM before calibration
pkill chrome
pkill code
```

**3. Use faster RAM:**
- DDR5 > DDR4
- Higher MHz better
- Dual-channel mode

**4. Consider quantization:**
```
Instead of: Qwen3:30B Q4 (17GB) in hybrid mode
Try: Qwen3:30B Q3 (13GB) in GPU-only mode
→ Faster inference, larger context
```

---

## Troubleshooting

### Hybrid mode fails to load

**Symptom:**
```
❌ Even 2.048 tokens failed
```

**Causes:**
1. Insufficient RAM (model overflow > free RAM)
2. RAM fragmentation (can't allocate contiguous block)
3. Other processes consuming RAM during calibration

**Fix:**
```bash
# 1. Free up RAM
sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'

# 2. Close applications
pkill chrome firefox code

# 3. Retry calibration
# (Restart AIfred)
```

### Context smaller than expected

**Symptom:**
```
✅ Hybrid mode: 4K context
(Expected: 8-10K)
```

**Causes:**
1. Conservative RAM reserve
2. Background RAM usage increased during calibration
3. MoE model (uses higher VRAM ratio)

**Fix:**
```python
# Temporary: Reduce RAM reserve
# In config.py (NOT recommended for production!)
RAM_RESERVE_MIN = 1024  # 1GB instead of 2GB
```

### Inference very slow

**Symptom:**
```
Inference: 20 tok/s (expected 60-80 tok/s)
```

**Causes:**
1. Slow RAM (DDR3, low MHz)
2. Single-channel RAM mode
3. Too much model in RAM (not enough in VRAM)

**Fix:**
1. Upgrade RAM speed
2. Use smaller model variant
3. Add more VRAM (upgrade GPU)

---

## Related Documentation

- [OLLAMA_VRAM_OPTIMIZATION.md](OLLAMA_VRAM_OPTIMIZATION.md) - VRAM optimization techniques
- [MEMORY_MANAGEMENT.md](MEMORY_MANAGEMENT.md) - Overall memory management
- [../hardware/HARDWARE_DETECTION.md](../hardware/HARDWARE_DETECTION.md) - GPU/RAM detection
- [../architecture/ollama-context-calculation.md](../architecture/ollama-context-calculation.md) - Context calculation details

---

## Changelog

**v2.10.6** (Dec 2025)
- Initial Hybrid Mode auto-detection
- Dynamic RAM reserve calculation
- Fine-tuning with 25% increments/reductions

**v2.10.7** (Dec 2025)
- Improved error handling for failed hybrid loads
- Better debug output for troubleshooting

---

**Last Updated:** 2025-12-26
**Maintainer:** AIfred Intelligence Team
