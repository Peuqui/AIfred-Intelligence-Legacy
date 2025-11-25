# vLLM Pascal Patches - Technical Analysis

**Research Date**: 2025-11-25
**Status**: Community Patches Available, Not Recommended for Production

---

## Executive Summary

vLLM does **not officially support** Pascal architecture GPUs (Compute Capability 6.1, e.g., Tesla P40, GTX 1080). However, community-maintained patches exist via [sasha0552/pascal-pkgs-ci](https://github.com/sasha0552/pascal-pkgs-ci).

**Key Finding**: **No performance benchmarks exist** for vLLM Pascal patches. The absence of published performance data suggests limited practical advantages over llama.cpp/KoboldCPP for single-user workloads.

**Recommendation for AIfred**: **Stay with KoboldCPP** for Pascal GPUs. vLLM Pascal patches add complexity without proven performance benefits for single-request inference.

---

## Official vLLM Requirements

| Component | Minimum Requirement | Pascal GPU Reality |
|-----------|-------------------|-------------------|
| **Compute Capability** | 7.0+ (Volta) | 6.1 (Below minimum) |
| **Triton Compiler** | SM 7.0+ | SM 6.1 (Rejected) |
| **Flash Attention 2** | Compute 8.0+ (Ampere) | Not available |
| **PagedAttention** | Compute 7.0+ | Possible with patches |

**Result**: Pascal GPUs are **explicitly unsupported** by vLLM project.

---

## Community Pascal Patches

### 1. Patch Source: sasha0552/pascal-pkgs-ci

**Repository**: https://github.com/sasha0552/pascal-pkgs-ci

**Supported vLLM Versions**:
- v0.5.5 through v0.10.0
- Nightly builds available

**Installation Methods**:

```bash
# Method 1: Docker (Recommended)
docker pull ghcr.io/sasha0552/vllm:v0.10.0

# Method 2: pip (Manual)
export PIP_EXTRA_INDEX_URL="https://sasha.github.io/pascal-pkgs-ci/"
pip3 install vllm-pascal==0.10.0
```

### 2. What Works

✅ **Basic Inference** (Confirmed by users)
- User @AslanEZ: "it works!" (Tesla P4 testing)
- User @torsteinelv: "finally made it work with some of my older gpus"
- Daily usage on P40 for ~1 month reported: "everything works fine"

✅ **PagedAttention** (With patches)
- Core vLLM feature for memory efficiency
- Works on Pascal after patching Triton

✅ **Multi-GPU** (Layer split)
- Can distribute layers across multiple P40s
- Similar to llama.cpp `--tensor-split`

### 3. What DOESN'T Work

❌ **Prefix Caching**
- Requires Triton's `tl.dot` operation
- Not available in Pascal-patched Triton
- Significant limitation for long-context workflows

❌ **Flash Attention 2**
- Requires Compute Capability 8.0+ (Ampere)
- Pascal lacks tensor cores
- Falls back to slower attention implementation

❌ **AWQ Marlin Kernel**
- Requires Compute Capability 8.0+ (Ampere)
- Not available on Pascal
- No quantization speedup benefits

❌ **Stable Wheels** (v0.6.5+)
- Repository notes: "wheels are currently in a soft-broken state due to PyTorch"
- Compatibility issues with recent PyTorch versions
- Installation increasingly fragile

---

## Performance Analysis

### Critical Issue: **No Benchmarks Available**

Despite community patches existing since 2024, **zero performance benchmarks** have been published:

- ❌ No tokens/second measurements
- ❌ No comparison vs llama.cpp/KoboldCPP
- ❌ No latency data
- ❌ No throughput comparisons
- ❌ No user-reported speed improvements

**Interpretation**: Lack of benchmarks is a **red flag**. If vLLM Pascal patches provided significant speedups, maintainers would publish data to promote adoption.

### Realistic Performance Expectations

**Single-Request Throughput** (AIfred use case):
- **Likely similar to llama.cpp**: No evidence of speedup
- **Possibly slower**: FP16 fallback penalties, missing optimizations
- **Key vLLM advantage (PagedAttention)** benefits multi-request batching, not single-user inference

**Multi-Request Batching** (Server use case):
- **PagedAttention**: Better memory efficiency for concurrent requests
- **Batch scheduling**: Improved throughput for multiple parallel queries
- **Use case**: Production API servers, not desktop assistants

### Known Pascal Performance Issues

From llama.cpp benchmarks (reference data):

**Tesla P40 + KoboldCPP (llama.cpp)**:
- 30B Q4_K_M: ~25-35 tok/s (measured)
- Flash Attention: Works (FP32 kernel, no tensor cores needed)
- VRAM utilization: 98% (optimized)

**Tesla P40 + ExLlamaV2** (FP16-based, similar to vLLM internals):
- 34B model: ~1.19 tok/s (extremely slow)
- 7B model: ~5-10 tok/s (slow)
- GPU utilization: 80W (underutilized due to FP16 bottleneck)

**Conclusion**: FP16-based inference engines (vLLM, ExLlamaV2) perform poorly on P40 due to 1:64 FP16:FP32 ratio.

---

## Technical Limitations

### 1. Triton Compiler Restrictions

**Problem**: Triton officially dropped SM60/SM61 support
- Affects P40, P100, P102, Quadro P5000, GTX 1080 family
- sasha0552's patches maintain compatibility
- Upstream rejected patch: "we dropped support for pre-A100 GPUs"

**Result**: Community patches required indefinitely, no upstream support.

### 2. FP16 Performance Bottleneck

**Tesla P40 FP16:FP32 Performance Ratio**: 1:64

vLLM uses FP16 internally for:
- Attention computation
- Matrix multiplications
- Intermediate activations

**Impact**: Every FP16 operation runs 64x slower than FP32 on P40.

**Comparison**:
| GPU | FP16:FP32 Ratio | vLLM Performance |
|-----|----------------|------------------|
| P40 | 1:64 | ❌ Very Poor |
| P100 | 1:2 | ⚠️ Fair |
| V100 | 1:1 | ✅ Good |
| A100 | 1:1 + Tensor Cores | ⭐ Excellent |

### 3. Missing Optimizations

**On Pascal, vLLM lacks**:
- Flash Attention 2 (requires Ampere)
- AWQ Marlin kernel (requires Ampere)
- Efficient FP16 kernels (requires tensor cores)
- Prefix caching (requires Triton tl.dot)

**Result**: Pascal gets "basic" vLLM without performance optimizations that make vLLM fast on modern GPUs.

---

## Installation Guide (For Testing Only)

**Warning**: Only recommended for experimentation, not production use.

### Method 1: Docker (Simplest)

```bash
# Pull pre-built image
docker pull ghcr.io/sasha0552/vllm:v0.10.0

# Run vLLM server
docker run --gpus all -p 8000:8000 \
  ghcr.io/sasha0552/vllm:v0.10.0 \
  --model /path/to/model \
  --gpu-memory-utilization 0.95
```

### Method 2: pip Installation

```bash
# Add Pascal package index
export PIP_EXTRA_INDEX_URL="https://sasha0552.github.io/pascal-pkgs-ci/"

# Install patched vLLM
pip3 install vllm-pascal==0.10.0

# Install patched Triton
# (Required separately due to PyTorch conflicts)
# See: https://github.com/sasha0552/pascal-pkgs-ci for instructions
```

### Method 3: Manual Patching

Not recommended. See [pascal-pkgs-ci README](https://github.com/sasha0552/pascal-pkgs-ci) for details.

---

## Comparison: vLLM Pascal vs KoboldCPP

| Feature | vLLM Pascal Patches | KoboldCPP (llama.cpp) |
|---------|-------------------|---------------------|
| **Pascal Support** | Community patches | Official support |
| **Installation** | Complex, fragile | Simple, one binary |
| **Performance** | Unknown (no benchmarks) | 25-35 tok/s (30B Q4) |
| **Flash Attention** | No (requires Ampere) | Yes (FP32 kernel) |
| **Prefix Caching** | No | Yes |
| **VRAM Optimization** | PagedAttention | Manual context sizing |
| **Multi-GPU** | Tensor parallelism | Layer split |
| **Model Formats** | Transformers, GGUF | GGUF, GGML |
| **Stability** | "Soft-broken" (v0.6.5+) | Stable |
| **Use Case** | Multi-request batching | Single-user inference |
| **Recommendation** | ⚠️ Experimental only | ✅ Production-ready |

---

## When vLLM Pascal Patches Make Sense

**✅ Use vLLM Pascal patches if**:
- You're running a multi-user inference server (batching benefits)
- You need to evaluate vLLM features before upgrading GPU
- You're conducting research on Pascal inference performance
- You have heterogeneous GPU clusters (mix Pascal + modern GPUs)

**❌ Don't use vLLM Pascal patches if**:
- You're running single-user applications (like AIfred)
- You need stable, production-ready inference
- You want optimal performance on Pascal hardware
- You lack expertise in managing patched dependencies

---

## Recommendation for AIfred

### Current Setup: KoboldCPP (Optimal ✅)

**Why KoboldCPP is better for Pascal**:

1. **Proven Performance**: 25-35 tok/s on P40 (30B Q4_K_M)
2. **Flash Attention Works**: FP32 kernel, no tensor cores needed
3. **98% VRAM Utilization**: Optimized context sizing
4. **Stability**: No patched dependencies
5. **Single-Request Optimized**: Perfect for desktop assistant

**KoboldCPP Advantages**:
- 26.8% faster than Ollama (measured benchmark)
- Native GGUF support with optimal quantization
- Simple installation (one binary)
- Multi-GPU support via `--tensor-split`
- RoPE scaling for context extension

### vLLM Pascal Alternative: Not Worth It ❌

**Problems for AIfred**:

1. **No Performance Gain**: No benchmarks showing speedup
2. **Missing Features**: No prefix caching (critical for long contexts)
3. **Fragile Installation**: "Soft-broken" wheels, patched dependencies
4. **Wrong Use Case**: PagedAttention benefits batching, not single requests
5. **FP16 Penalty**: P40's 1:64 FP16:FP32 ratio hurts vLLM's FP16-heavy kernels

**Bottom Line**: vLLM Pascal patches add complexity without proven benefits for AIfred's single-user, long-context workflow.

---

## Alternative Backends for Pascal

If you want to explore alternatives to KoboldCPP:

### 1. **Aphrodite Engine** (vLLM Fork)
- **Pascal Support**: Yes (native support claimed)
- **Repository**: https://github.com/PygmalionAI/aphrodite-engine
- **Advantage**: Built-in Pascal support, no patching needed
- **Disadvantage**: Less mature than vLLM, smaller community

### 2. **llama.cpp CLI** (Direct)
- **Pascal Support**: Full support
- **Advantage**: Most mature, fastest single-request inference
- **Disadvantage**: No OpenAI-compatible API (unlike KoboldCPP)

### 3. **Text-Generation-WebUI (Oobabooga)**
- **Pascal Support**: Yes (via multiple backends)
- **Backends**: llama.cpp, ExLlamaV2, Transformers
- **Advantage**: Web UI, multiple backend options
- **Disadvantage**: Heavier than KoboldCPP, slower startup

---

## Conclusion

**vLLM Pascal Patches: Technical Achievement, Practical Limitations**

The sasha0552 Pascal patches are an impressive **technical achievement** enabling basic vLLM functionality on unsupported hardware. However:

- ❌ **No performance benchmarks** (red flag)
- ❌ **Missing key features** (prefix caching, Flash Attention 2)
- ❌ **Fragile installation** (soft-broken wheels)
- ❌ **Wrong use case** for single-user inference
- ❌ **FP16 bottleneck** on Pascal architecture

**For AIfred Intelligence on Pascal GPUs**:

✅ **Recommendation: Keep using KoboldCPP**
- Proven performance (25-35 tok/s on 30B Q4)
- Flash Attention support (FP32 kernel)
- Stable, production-ready
- Optimized for single-request inference

⚠️ **Experimental Only**: Test vLLM Pascal patches only if you're willing to:
- Manage patched dependencies
- Accept potential instability
- Conduct your own benchmarks
- Troubleshoot integration issues

**Summary**: vLLM Pascal patches are a curiosity for researchers, not a production solution for Pascal-based LLM inference.

---

## References

- [vLLM Pascal GPU PR #4409](https://github.com/vllm-project/vllm/pull/4409) - Original Pascal support attempt (closed)
- [sasha0552/pascal-pkgs-ci](https://github.com/sasha0552/pascal-pkgs-ci) - Community Pascal patches repository
- [kalavai-net Issue #20](https://github.com/kalavai-net/kalavai-client/issues/20) - Pascal GPU compatibility discussion
- [vLLM Issue #963](https://github.com/vllm-project/vllm/issues/963) - Compute capability <7.0 support request
- [AIfred KoboldCPP VRAM Optimization](koboldcpp_vram_optimization.md) - Production Pascal setup guide

**Last Updated**: 2025-11-25
**Author**: Claude Code (Research Assistant)
