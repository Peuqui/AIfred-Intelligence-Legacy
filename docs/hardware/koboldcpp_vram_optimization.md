# KoboldCPP VRAM Optimization Guide

## Problem: Massive VRAM Waste with Auto-Detection

KoboldCPP's `--gpulayers -1` (auto-detection) is extremely conservative and leaves massive amounts of VRAM unused.

### Before Optimization

With `--gpulayers -1`:
- **32K Context**: Only 49/49 layers (100%), but 2.3GB VRAM wasted
- **128K Context**: Only **17/49 layers** (35%), **12GB VRAM wasted**!
- **256K Context**: **0 layers** on GPU, running on CPU

**Root Cause**: KoboldCPP's "Auto Recommended GPU Layers" algorithm is designed to prevent OOM crashes, not maximize VRAM usage.

---

## Solution: Use Explicit Layer Count

The documentation explicitly warns:
> "`--gpulayers -1` allows KoboldCpp to **guess** how many layers... though this is **often not the most accurate**"
>
> "You are recommended to determine the optimal layer fit through **trial and error**"

**Solution**: Extract actual layer count from GGUF metadata and use it explicitly instead of `-1`.

---

## Implementation in AIfred

### 1. Fix CUDA Flag Bug

Changed from `--usecublas` to `--usecuda` (correct for KoboldCPP 1.101.1+):

```python
# aifred/lib/koboldcpp_manager.py:210
elif vendor == "nvidia":
    cmd.append("--usecuda")  # NVIDIA CUDA (correct flag for KoboldCPP 1.101.1+)
```

### 2. Extract Layer Count from GGUF

Added `get_gguf_layer_count()` function to read layer count from GGUF metadata:

```python
# aifred/lib/gguf_utils.py
def get_gguf_layer_count(gguf_path: Path) -> Optional[int]:
    """
    Extract layer count (block_count) from GGUF model metadata.

    Returns:
        Number of transformer layers (e.g., 48 for 30B models)
    """
```

### 3. Use Explicit Layer Count Instead of -1

Modified `koboldcpp_manager.py` to use explicit layer count:

```python
# aifred/lib/koboldcpp_manager.py:195
if gpu_layers == -1:
    # Try to get actual layer count from GGUF
    layer_count = get_gguf_layer_count(model_file)
    if layer_count:
        # GGUF returns transformer blocks (48 for 30B models)
        # Total GPU layers = blocks + 1 output layer
        actual_gpu_layers = layer_count + 1  # 49 for 30B models
        logger.info(f"   🎯 GPU Layers: {actual_gpu_layers} (ALL - extracted from GGUF metadata)")
        logger.info(f"      Using explicit count instead of -1 to bypass conservative auto-detection")
```

---

## Results: Dramatic Improvement

### Final Optimized Results (RTX 3090 Ti 24GB)

**Production Configuration:**
- **Context**: 105,753 tokens (~106K)
- **VRAM Used**: ~24.0 GB
- **VRAM Free**: **515 MB** (optimal!)
- **GPU Layers**: 49/49 (100%)
- **VRAM Utilization**: **98.0%** ✅

### Test Results with Fixed 49 Layers (Stress Testing)

| Context | VRAM Used | VRAM Free | GPU Layers | VRAM Utilization |
|---------|-----------|-----------|------------|------------------|
| 32K | 22,032 MB | 2,282 MB | 49/49 (100%) | 90.6% |
| 40K | 22,271 MB | 2,043 MB | 49/49 (100%) | 91.6% |
| 50K | 22,531 MB | 1,783 MB | 49/49 (100%) | 92.7% |
| 60K | 22,778 MB | 1,536 MB | 49/49 (100%) | 93.7% |
| 70K | 23,054 MB | 1,260 MB | 49/49 (100%) | 94.8% |
| 80K | 23,317 MB | 997 MB | 49/49 (100%) | 95.9% |
| 90K | 23,677 MB | 637 MB | 49/49 (100%) | 97.4% |
| **106K** | **24,049 MB** | **515 MB** | 49/49 (100%) | **98.0%** ✅ (Production) |
| 110K | 23,988 MB | 322 MB | 49/49 (100%) | 98.7% (Tested stable) |
| 130K | 24,023 MB | 291 MB | 49/49 (100%) | 98.8% |
| 150K | 23,992 MB | 280 MB | 49/49 (100%) | 98.9% |

### Stress Test Results (500 Token Inference)

All contexts from 90K-150K passed stress testing with long inference (500 tokens):
- ✅ No OOM errors
- ✅ No CUDA errors
- ✅ VRAM stable (max diff: ±42MB)
- ✅ No memory leaks

### Comparison: Before vs. After

**Before (Initial - with `--gpulayers -1` and 1.0x multiplier):**
- Context: 70,639 tokens
- GPU Layers: 49/49
- Free VRAM: 1,450 MB (wasted)
- VRAM Utilization: ~94%

**After (Final - optimized multiplier 0.91x + 150MB safety):**
- Context: **105,753 tokens** (production value)
- GPU Layers: 49/49 (ALL)
- Free VRAM: **515 MB** (optimal for CUBLAS buffer)
- VRAM Utilization: **98.0%**

**Improvement:**
- **+50% more context** (70K → 106K)
- **Same GPU layer count** (49/49)
- **65% less waste** (1,450 MB → 515 MB free)
- **Optimal VRAM efficiency** (94% → 98%)

---

## Optimal Configuration for RTX 3090 Ti (24GB)

### Production (Recommended) ✅
```python
# Automatically calculated by AIfred
context_size = 105_753  # ~106K tokens
gpu_layers = 49         # Extracted from GGUF (48 blocks + 1 output)
free_vram = ~515MB      # Optimal for CUBLAS buffer
vram_multiplier = 0.91  # Empirically calibrated
safety_margin = 150MB   # Minimum for CUBLAS
```

### Internal Configuration
```python
# aifred/lib/koboldcpp_manager.py
vram_multiplier = 0.91      # Model VRAM footprint (file_size × 0.91)
safety_margin_mb = 150      # CUBLAS scratch buffer minimum
mb_per_token = 0.05         # Q4 KV cache (75% savings vs FP16)
```

### KoboldCPP Parameters (Auto-Applied)
```python
--quantkv 2              # Q4 KV cache (75% VRAM savings)
--flashattention         # 30-50% VRAM savings at large contexts
--blasbatchsize 512      # Optimal for 24GB VRAM
--usecuda                # NVIDIA CUDA (KoboldCPP 1.101.1+)
--gpulayers 49           # All layers (extracted from GGUF)
```

---

## Key Takeaways

1. **Optimized VRAM Multiplier (0.91x)**
   - Empirically calibrated for Q4_K models
   - Accounts for actual model footprint vs file size
   - Combined with cache-based learning for other models

2. **Reduced Safety Margin (150MB)**
   - Down from 350MB conservative default
   - Minimum for CUBLAS scratch buffer
   - Maximizes context without OOM risk

3. **Explicit Layer Count from GGUF**
   - AIfred automatically extracts layer count
   - Uses explicit count instead of `-1` auto-detection
   - Bypasses KoboldCPP's conservative algorithm

4. **Fixed CUDA Flag Bug**
   - Changed `--usecublas` → `--usecuda` (KoboldCPP 1.101.1+)
   - Critical for GPU acceleration

5. **Q4 KV Cache is essential**
   - 75% VRAM savings vs. FP16
   - Enables 2-3x larger contexts
   - 0.05 MB/token vs 0.17-0.20 MB/token

6. **Cache-Based Calibration**
   - System learns optimal context for each model
   - Stores empirical measurements in `model_vram_cache.json`
   - Auto-adjusts on subsequent starts

7. **Optimal VRAM target: 400-600MB free**
   - Enough for CUBLAS scratch buffer
   - Minimizes waste
   - Proven stable under load (500+ token inference)

---

## References

- [KoboldCPP GitHub Wiki](https://github.com/LostRuins/koboldcpp/wiki)
- [KoboldCPP Issue #390 - Auto GPU Layers](https://github.com/LostRuins/koboldcpp/issues/390)
- [llama.cpp GPU Layers Discussion](https://github.com/ggml-org/llama.cpp/discussions/4049)
- Test Results: `/tmp/vram_stress_test.csv`
- Research: `/tmp/koboldcpp_vram_research.md`
