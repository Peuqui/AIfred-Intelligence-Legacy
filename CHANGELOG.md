# Changelog

All notable changes to AIfred Intelligence will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2025-11-25

### 🎯 KoboldCPP Dynamic RoPE Scaling & VRAM Optimization

#### Added
- **KoboldCPP Backend Support** ([aifred/backends/koboldcpp.py](aifred/backends/koboldcpp.py)):
  - Full KoboldCPP integration as fourth backend (alongside Ollama, vLLM, TabbyAPI)
  - Auto-start functionality with intelligent VRAM-based context calculation
  - Dynamic RoPE (Rotary Position Embedding) scaling for context extension
  - Single-pass optimization: calculates optimal context + RoPE factor before first start
  - OOM retry strategy with automatic MB/token adjustment

- **Intelligent Context + RoPE Calculation** ([aifred/lib/koboldcpp_manager.py:443-534](aifred/lib/koboldcpp_manager.py#L443-L534)):
  - New `calculate_optimal_context_and_rope()` method for VRAM-based optimization
  - Automatically determines if RoPE scaling is beneficial or if context is VRAM-limited
  - **Logic**:
    - If `max_tokens > native_context`: Apply RoPE scaling (extend context beyond native)
    - If `max_tokens ≤ native_context`: Use available VRAM without RoPE (VRAM-limited)
  - Caps RoPE factor at configurable maximum (default: 2.0x)
  - Caps context at KoboldCPP hard limit (262,144 tokens)

- **GGUF Metadata Utilities** ([aifred/lib/gguf_utils.py](aifred/lib/gguf_utils.py), [aifred/lib/gguf_utils_vision.py](aifred/lib/gguf_utils_vision.py)):
  - Extract native context from GGUF files (avoids hardcoded values)
  - Detect architecture (Qwen2, Llama, etc.) for accurate KV cache calculation
  - Extract quantization level from filename (Q4_K_M, Q8_0, etc.)
  - Calculate MB/token for KV cache based on architecture + quantization
  - Vision model support: VL models use same KV cache as text models (no multiplier)

- **Configuration Options** ([aifred/lib/config.py:228-259](aifred/lib/config.py#L228-L259)):
  ```python
  KOBOLDCPP_TARGET_FREE_VRAM_MB = 600        # Target free VRAM after start
  KOBOLDCPP_SAFETY_MARGIN_MB = 150           # CUDA scratch buffer (fixed)
  KOBOLDCPP_MAX_ROPE_FACTOR = 2.0            # Maximum RoPE scaling factor
  KOBOLDCPP_OOM_RETRY_MB_PER_TOKEN_ADJUSTMENT = 0.10  # 10% more conservative per retry
  KOBOLDCPP_MAX_OOM_RETRIES = 3              # Maximum retry attempts
  ```

#### Changed
- **Removed vLLM/TabbyAPI/KoboldCPP Automatik-LLM Messages** ([aifred/state.py:561,730,2130](aifred/state.py)):
  - Removed verbose "🔄 Automatik-LLM angepasst..." debug messages
  - These backends can only load one model - adjustment happens silently
  - Reduces console clutter and prevents horizontal scrolling

#### Fixed
- **KoboldCPP RoPE Calculation Bugs** (3 critical fixes):
  - **Bug #1**: Added KoboldCPP maximum context cap (262,144 tokens) - prevented exceeding hard limit
  - **Bug #2**: Removed incorrect `--overridenativecontext` parameter - was using wrong value
  - **Bug #3**: Fixed scope error with `log_feedback()` - replaced with `logger.info()` in calculation method

#### Technical Details

**RoPE Scaling Strategy:**
- **Small Models** (32k native context): Benefit from RoPE extension
  - Example: Qwen3-14B (32k native) → 65k with RoPE 2.0x @ RTX 3090 Ti
- **Large Models** (262k native context): Already at maximum
  - Example: Qwen3-VL-8B (262k native) → No RoPE needed, at KoboldCPP limit

**VRAM Calculation:**
```python
usable_vram = total_vram - model_size - safety_margin - target_free_vram
max_tokens = usable_vram / mb_per_token

if max_tokens > native_context:
    rope_factor = max_tokens / native_context  # Extend beyond native
    context = min(max_tokens, 262144)          # Cap at KoboldCPP max
else:
    rope_factor = 1.0                          # No RoPE, VRAM-limited
    context = max_tokens
```

**OOM Retry Strategy:**
If initial calculation is too optimistic:
1. Attempt 1: Optimal calculation with measured MB/token
2. Attempt 2: +10% more conservative MB/token → recalculate
3. Attempt 3: +10% again → recalculate
4. Fail after 3 attempts

**KV Cache Optimization:**
- Q4 quantization: 0.05 MB/token (75% savings vs FP16)
- Vision models: Same KV cache as text (vision encoder separate)
- Architecture-aware: Dense vs MoE models handled correctly

#### Files Modified
- [aifred/backends/koboldcpp.py](aifred/backends/koboldcpp.py): Complete backend implementation
- [aifred/lib/koboldcpp_manager.py](aifred/lib/koboldcpp_manager.py): Process management + optimization
- [aifred/lib/gguf_utils.py](aifred/lib/gguf_utils.py): GGUF metadata extraction
- [aifred/lib/gguf_utils_vision.py](aifred/lib/gguf_utils_vision.py): Architecture detection + KV cache calculation
- [aifred/lib/config.py](aifred/lib/config.py): KoboldCPP configuration constants
- [aifred/state.py](aifred/state.py): Removed verbose Automatik-LLM sync messages (3 locations)

#### Performance Results
**RTX 3090 Ti (24GB VRAM):**
- Qwen3-VL-8B (8.5 GB): 262,144 tokens (maximum, no RoPE needed)
- Qwen3-14B (8 GB): 65,536 tokens (32k native × 2.0 RoPE)
- Target free VRAM: ~600 MB (optimal for stability)

---

## [2.1.0] - 2025-11-22

### 🚀 Major Features

#### Unified VRAM Cache System
- **Created**: `aifred/lib/model_vram_cache.py` - Unified cache combining vLLM calibrations and VRAM ratio measurements
- **Backend-Aware Structure**: Single cache file with per-backend model tracking (Ollama/vLLM/TabbyAPI)
- **Automatic Migration**: Old `vllm_context_cache.json` automatically migrated to new unified format on first load
- **Universal VRAM Ratio Tracking**: Measures MB/token for ALL backends (Ollama active, vLLM/TabbyAPI for validation)
- **Architecture Detection**: Separate ratios for MoE vs Dense models (0.10 vs 0.15 MB/token)

### Added

#### Model VRAM Cache Functions
- **`load_cache()`**: Loads unified cache with automatic migration from old vLLM cache
- **`add_vram_measurement()`**: Records VRAM ratio measurements for any backend (with backend parameter)
- **`get_calibrated_ratio()`**: Returns measured MB/token ratio or default fallback
- **`add_vllm_calibration()`**: Stores vLLM-specific context calibration points
- **`interpolate_vllm_context()`**: Linear interpolation for vLLM context limits at different VRAM levels
- **`get_measurement_count()`**: Returns number of VRAM measurements for a model

#### Cache File Structure
```json
{
  "model_name": {
    "backend": "ollama|vllm|tabbyapi",
    "architecture": "moe|dense",
    "native_context": 262144,
    "gpu_model": "NVIDIA GeForce RTX 3090 Ti",
    "vram_ratio": {
      "measurements": [
        {
          "context_tokens": 20720,
          "measured_mb_per_token": 0.0872,
          "measured_at": "2025-11-22T02:30:00"
        }
      ],
      "avg_mb_per_token": 0.0872
    },
    "vllm_calibrations": [
      {
        "free_vram_mb": 22968,
        "max_context": 21608,
        "measured_at": "2025-11-21T23:31:17"
      }
    ]
  }
}
```

- **Dynamic Context Window Optimization** ([aifred/lib/context_manager.py:184-187](aifred/lib/context_manager.py#L184-L187)):
  - Removed fixed context size rounding (2K, 4K, 8K, etc.)
  - Now uses exact calculated `num_ctx` values for maximum efficiency
  - Automatically utilizes full VRAM-based limit for large contexts
  - **Example**: 42K needed → Uses 42K directly (instead of rounding to 64K or capping at 40K)
  - **Benefit**: ~7-10% more context available for long conversations without wasting RAM

- **Ollama: Loaded Model Context Detection** ([aifred/backends/ollama.py:610-640](aifred/backends/ollama.py#L610-L640)):
  - New `get_loaded_model_context()` method queries `/api/ps` for actual context length
  - Returns the exact `num_ctx` value a loaded model is using
  - Used for accurate history compression limits

### Changed

#### Updated All VRAM Cache Imports (6 Files Modified)
- **`aifred/lib/gpu_utils.py`** (Line 243):
  - Changed: `from .vram_ratio_cache import ...` → `from .model_vram_cache import ...`
  - Functions: `get_calibrated_ratio`, `get_measurement_count`

- **`aifred/lib/conversation_handler.py`** (Lines 498-513):
  - Changed: `from aifred.lib.vram_ratio_cache import add_measurement` → `from aifred.lib.model_vram_cache import add_vram_measurement`
  - **NEW Parameter**: Added `backend=backend_type` to measurement calls
  - Impact: VRAM measurements now backend-aware for Ollama/vLLM/TabbyAPI

- **`aifred/lib/vllm_manager.py`** (5 locations - lines 503, 557, 603, 780, 831):
  - Changed: `from aifred.lib.vllm_context_cache import ...` → `from aifred.lib.model_vram_cache import ...`
  - Function renames:
    - `interpolate_context` → `interpolate_vllm_context as interpolate_context`
    - `add_calibration_point` → `add_vllm_calibration as add_calibration_point`

- **`aifred/lib/vllm_utils.py`** (Lines 48, 75):
  - Changed: `from .vllm_context_cache import ...` → `from .model_vram_cache import ...`
  - Function renames:
    - `get_calibrations` → `get_vllm_calibrations as get_calibrations`
    - `interpolate_context` → `interpolate_vllm_context as interpolate_context`

### Removed

- **Deleted Old Cache Modules** (No backward compatibility per user requirement):
  - `aifred/lib/vram_ratio_cache.py` - Replaced by unified cache
  - `aifred/lib/vllm_context_cache.py` - Replaced by unified cache
  - `~/.config/aifred/vllm_context_cache.json` - Automatically migrated to `model_vram_cache.json`

### Fixed

#### Critical Web Research Crash - ValueError in Scraper Orchestrator
- **Problem**: `ValueError: too many values to unpack (expected 2)` during web research
- **Location**: [aifred/lib/research/scraper_orchestrator.py:158](aifred/lib/research/scraper_orchestrator.py#L158)
- **Root Cause**:
  - Line 84 `unload_and_preload()` returns 3 values: `(success, load_time, models)`
  - Line 128 correctly unpacks 3 values in the first code path
  - Line 158 **incorrectly** only unpacked 2 values: `success, load_time = await preload_task`
- **Impact**: Web research would crash when Main-LLM preload finished after scraping completed
- **Fix Applied**:
  ```python
  # Before (Line 158)
  success, load_time = await preload_task

  # After (Line 158-162)
  success, load_time, unloaded_models = await preload_task
  if unloaded_models:
      models_str = ", ".join(unloaded_models)
      log_message(f"🗑️ Entladene Modelle: {models_str}")
      yield {"type": "debug", "message": f"🗑️ Entladene Modelle: {models_str}"}
  ```
- **Additional Enhancement**: Now properly logs unloaded models in both code paths (lines 126-135, 158-169)
- **Testing**: Syntax validated with `python3 -m py_compile`

### Technical Details

#### Files Modified (7 total)
1. **Created**: [aifred/lib/model_vram_cache.py](aifred/lib/model_vram_cache.py) (420 lines)
   - Unified cache management with automatic migration
   - VRAM ratio tracking for all backends
   - vLLM calibration with linear interpolation

2. **Modified**: [aifred/lib/gpu_utils.py](aifred/lib/gpu_utils.py) (Line 243)
   - Updated imports from old `vram_ratio_cache` to `model_vram_cache`

3. **Modified**: [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py) (Lines 498-513)
   - Added `backend` parameter to VRAM measurement calls
   - Backend-aware measurement storage

4. **Modified**: [aifred/lib/vllm_manager.py](aifred/lib/vllm_manager.py) (5 locations)
   - Updated all vLLM cache function imports
   - Function alias mapping for compatibility

5. **Modified**: [aifred/lib/vllm_utils.py](aifred/lib/vllm_utils.py) (2 locations)
   - Updated vLLM utility imports

6. **Modified**: [aifred/lib/research/scraper_orchestrator.py](aifred/lib/research/scraper_orchestrator.py) (Lines 158-169)
   - **CRITICAL FIX**: Corrected async task unpacking
   - Added unloaded models logging

7. **Deleted**: `aifred/lib/vram_ratio_cache.py` - Functionality moved to unified cache
8. **Deleted**: `aifred/lib/vllm_context_cache.py` - Functionality moved to unified cache
9. **Deleted**: `~/.config/aifred/vllm_context_cache.json` - Auto-migrated to `model_vram_cache.json`

#### Cache Migration Details
- **Automatic**: No user intervention required
- **One-Time**: Migration runs on first `load_cache()` call
- **Data Preservation**: All vLLM calibrations preserved
- **Format**: 5 models migrated (Qwen3-8B-AWQ, Qwen3-4B, Qwen2.5-3B, Qwen3-4B-AWQ, Qwen3-30B-A3B-AWQ)
- **Location**: `~/.config/aifred/model_vram_cache.json`

#### Performance Impact
- **VRAM Optimization**: More accurate context limits with calibrated ratios
- **Bug Fix Impact**: Web research stability improved (no more mid-research crashes)
- **Cache Efficiency**: Single cache file instead of two separate files
- **Future-Ready**: Extensible for new backends (e.g., LM Studio, LocalAI)

#### GPU Performance Observations
- **MoE Models** (Qwen3-30B-A3B): 17-21% → 59-60% GPU utilization (prefill → generation)
  - Speed: 61.4 tok/s
  - Power: 117-221W
  - VRAM: 22.8 GB
  - **Reason**: Sparse activation (10-20% active parameters), memory-bound operation

- **Dense Models** (Qwen3-32B): 14-37% → 83-95% GPU utilization (prefill → generation)
  - Speed: 31.9 tok/s (50% slower)
  - Power: 118-446W (2x power consumption)
  - VRAM: 23.9 GB
  - **Reason**: All parameters active, compute-bound operation

- **Conclusion**: MoE ~60% GPU utilization at double the speed is expected and optimal behavior

### Changed (History Compression)
- **History Compression Context Limit** ([aifred/state.py:1404-1444](aifred/state.py#L1404-L1444)):
  - **Ollama**: Now uses `/api/ps` to get actual loaded model context (e.g., 40960 or 44051)
  - **vLLM/TabbyAPI**: Uses `calculate_dynamic_num_ctx()` for consistent limit calculation
  - **Result**: History percentage now shows accurate utilization
  - **Before**: "2,169 / 7,505 tok (28%)" ❌ (wrong VRAM calculation)
  - **After**: "2,169 / 40,960 tok (5%)" ✅ (actual model context)

### Fixed
- **vLLM Context Calibration Safety Buffer** ([aifred/lib/vllm_manager.py:537-544, 666-673](aifred/lib/vllm_manager.py#L537-L544)):
  - Changed from fixed 150 token buffer to 2% percentage-based safety margin
  - Applied iteratively at each calibration attempt
  - **Before**: 3 attempts needed, 150 tokens wasted regardless of context size
  - **After**: 2 attempts, scales with context (e.g., 440 tokens at 22K context)
  - **Result**: More efficient calibration with better success rate

- **vLLM: Automatik-LLM Synchronization** ([aifred/state.py:460-466, 566-571, 1786-1822](aifred/state.py#L1786-L1822)):
  - vLLM can only load ONE model at a time (unlike Ollama)
  - Now automatically syncs Automatik-LLM to match Main-LLM for vLLM backend
  - Applied at three points: model change, backend init (slow path), backend init (fast path)
  - **Before**: 404 errors when Automatik-LLM differed from Main-LLM
  - **After**: Automatic sync with debug message explaining why

- **YaRN Factor Reset on Model Change** ([aifred/state.py:1786-1822](aifred/state.py#L1786-L1822)):
  - YaRN factor now automatically resets to 1.0 when changing models
  - Prevents crashes from trying to load new model with old YaRN extension
  - Resets all YaRN state: factor, input, max_factor, max_tested
  - Shows loading spinner during model change (40-70 seconds for vLLM)

## [Unreleased] - 2025-11-18

### Changed
- **UI Layout Optimization** ([aifred/aifred.py:1486-1506](aifred/aifred.py#L1486-L1506)):
  - Improved usability by reordering main UI components
  - **New order**: Chat History → Input Controls → Debug Console & Settings
  - **Benefit**: After reading conversation, text input is directly accessible without scrolling
  - Debug console moved to bottom for quick access when needed

- **Query Optimization: URL Handling** ([prompts/de/query_optimization.txt](prompts/de/query_optimization.txt), [prompts/en/query_optimization.txt](prompts/en/query_optimization.txt)):
  - Enhanced query optimization to preserve URLs completely
  - **New rule**: URLs and web addresses (https://, www., domain.com, github.com/...) are returned UNFILTERED
  - **Examples added**: github.com/user/repo, example.com/blog/article
  - **Benefit**: Web search modes (quick/detailed) can now handle URL-based queries correctly without breaking them into keywords

### Fixed
- **Model Preload Order** ([aifred/backends/ollama.py](aifred/backends/ollama.py), [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py), [aifred/lib/research/scraper_orchestrator.py](aifred/lib/research/scraper_orchestrator.py), [aifred/state.py:1066-1086](aifred/state.py#L1066-L1086)):
  - Fixed unnecessary model unload/reload during preload phase
  - **Problem**: `preload_model()` internally called `unload_all_models()`, which unloaded ALL models including the target model if already loaded
  - **Symptom**: Debug showed `🗑️ Entladene Modelle: qwen3:4b, qwen3:14b` (14B shouldn't be there!)
  - **Root Cause**: Sequence was Automatik-LLM decision → preload → unload ALL → reload target
  - **Solution**: Removed `unload_all_models()` from `preload_model()` internals, added explicit calls before preload in callers
  - **Impact**: Eliminates unnecessary model reload, clearer debug output, proper VRAM management
  - Changed return signature: `tuple[bool, float, list[str]]` → `tuple[bool, float]`
  - Correct order now: Automatik decision → explicit unload → load Haupt-LLM

---

### 🧠 VRAM-Based Dynamic Context Window Calculation

#### Added
- **Automatic VRAM-Based Context Calculation** ([aifred/lib/gpu_utils.py](aifred/lib/gpu_utils.py)):
  - Dynamically calculates maximum practical `num_ctx` based on available GPU memory
  - Prevents CPU offloading by staying within VRAM limits
  - Two-scenario detection: Model loaded vs not loaded (via `/api/ps` endpoint)
  - Reads model size from blob filesystem (no hardcoded values)
  - Safety margin: 512 MB (optimized from initial 1024 MB)
  - KV-cache ratio: 0.097 MB/token (empirically measured for Qwen3 MoE models)
  - **VRAM Stabilization Polling** ([aifred/lib/gpu_utils.py:138-169](aifred/lib/gpu_utils.py#L138-L169)):
    - Waits for VRAM to stabilize after model preload (prevents premature measurement)
    - Polls every 200ms, requires 2 consecutive stable readings (< 50 MB difference)
    - Maximum wait time: 3 seconds
    - Ensures accurate context calculation after Ollama finishes loading model into VRAM

- **Model Load Detection** ([aifred/lib/gpu_utils.py:22-56](aifred/lib/gpu_utils.py#L22-L56)):
  - `is_model_loaded()` checks Ollama `/api/ps` endpoint
  - Prevents double-subtraction of model size from free VRAM
  - Scenario 1 (model NOT loaded): `vram_for_context = free_vram - model_size - margin`
  - Scenario 2 (model IS loaded): `vram_for_context = free_vram - margin`

- **Model Size Extraction** ([aifred/backends/ollama.py:430-520](aifred/backends/ollama.py#L430-L520)):
  - Enhanced `get_model_context_limit()` to return `(context_limit, model_size_bytes)`
  - Extracts blob path from modelfile (`FROM /path/to/blobs/sha256-...`)
  - Reads actual file size from filesystem (e.g., 17.28 GB for qwen3:30b)
  - Falls back gracefully if blob not found (no VRAM calculation)

- **Automatic Model Unloading** ([aifred/backends/ollama.py:349-454](aifred/backends/ollama.py#L349-L454)):
  - **Problem**: Multiple models loaded simultaneously (e.g., Automatik 3B + Main 30B) consumed VRAM
  - **Solution**: `preload_model()` now unloads ALL other models before loading requested model
  - Uses `/api/ps` to detect loaded models, then sends `keep_alive=0` to unload each
  - Returns list of unloaded models for debug output
  - **Impact**: Ensures maximum VRAM available for context calculation (23GB → 35K tokens instead of 730MB → 7K tokens)
  - **UI Feedback**: Shows `🗑️ Entladene Modelle: qwen2.5:3b` in debug console
  - **Bug Fix**: Added required `prompt` field to `/api/generate` unload request (prevents preload failure with 0.0s time)

- **UI Integration** ([aifred/aifred.py:1151-1188](aifred/aifred.py#L1151-L1188)):
  - Manual context override option (numeric input field)
  - Checkbox: "Setze Context-Fenster auf Basis von VRAM"
  - Warning message when manual override active
  - Real-time VRAM debug messages in UI console

- **Debug Logging** ([aifred/lib/gpu_utils.py:196-236](aifred/lib/gpu_utils.py#L196-L236)):
  - Detailed VRAM calculation messages collected as list
  - Yielded to UI console for real-time visibility
  - Shows: Free VRAM, model size, safety margin, calculated context, architectural limit
  - German number formatting (35.010 T instead of 35,010T)
  - **Improved Readability**: Spaces between numbers and units (e.g., `3853 MB` instead of `3853MB`, `0.097 MB/T` instead of `0.097MB/T`)

#### Configuration
- **Optimized Constants** ([aifred/lib/config.py](aifred/lib/config.py)):
  - `VRAM_SAFETY_MARGIN = 512` (MB) - reduced from 1024 MB
  - `VRAM_CONTEXT_RATIO = 0.097` (MB/token) - empirically measured
  - `ENABLE_VRAM_CONTEXT_CALCULATION = True` - feature flag

#### Performance Results (RTX 3090 Ti, 24GB VRAM)
- **qwen3:30b-a3b-instruct-2507-q4_K_M** (17.28 GB):
  - Free VRAM: 3908 MB
  - Context for KV-cache: 3396 MB (after 512 MB safety margin)
  - **Calculated Context**: 35,010 tokens (3396 MB / 0.097 MB/T)
  - Model architectural limit: 262,144 tokens
  - **Practical limit**: 35,010 tokens (VRAM-constrained, prevents CPU offloading)

- **qwen3:32b-q4_K_M** (18.81 GB, older generation):
  - Free VRAM: 1780 MB (with Whisper loaded)
  - Context for KV-cache: 1268 MB
  - **Calculated Context**: 13,072 tokens
  - Model architectural limit: 40,960 tokens (only!)
  - **Problem**: Input 16K tokens → exceeds 13K limit → CPU offloading (17.6 t/s instead of 80+ t/s)
  - **Recommendation**: Use qwen3:30b-a3b instead (newer, larger context, smaller size)

#### Impact
- **Before**: Hardcoded context windows → frequent CPU offloading on large inputs
- **After**: Automatic adaptation to available VRAM → maximizes usable context
- **User Benefit**: No more manual tuning, system automatically prevents CPU offloading

#### Technical Details
- **VRAM Query**: Uses `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits`
- **Model Load Detection**: HTTP GET to `http://localhost:11434/api/ps`
- **Fallback**: If VRAM calculation fails → use model's architectural limit
- **Validation**: Minimum 100 MB VRAM required, otherwise fallback to 2048 tokens

#### Files Modified
- [aifred/lib/gpu_utils.py](aifred/lib/gpu_utils.py): Lines 22-238 (VRAM calculation, stabilization polling, model load detection, improved debug formatting)
- [aifred/backends/ollama.py](aifred/backends/ollama.py): Lines 349-520 (automatic model unloading, model size extraction)
- [aifred/backends/base.py](aifred/backends/base.py): Lines 159-173 (preload_model signature updated)
- [aifred/backends/vllm.py](aifred/backends/vllm.py): Lines 221-239 (preload_model signature updated)
- [aifred/backends/tabbyapi.py](aifred/backends/tabbyapi.py): Lines 212-230 (preload_model signature updated)
- [aifred/lib/llm_client.py](aifred/lib/llm_client.py): Lines 183-198 (preload_model signature updated)
- [aifred/state.py](aifred/state.py): Lines 92, 556-603, 1017-1035, 1348-1372 (state management, preload with unload feedback, settings persistence)
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 419-437 (Automatik mode with unload feedback)
- [aifred/lib/config.py](aifred/lib/config.py): Lines 168-171 (VRAM constants)
- [aifred/aifred.py](aifred/aifred.py): Lines 1151-1188 (UI integration)

---

### ✂️ Token Optimization: Redundant Date Line Removed

#### Changed
- **Prompt Timestamp Format** ([aifred/lib/prompt_loader.py:137-147](aifred/lib/prompt_loader.py#L137-L147)):
  - Removed redundant `- Jahr: {now.year}` line from German timestamp
  - Removed redundant `- Year: {now.year}` line from English timestamp
  - Date already contains full year (`16.11.2025` or `2025-11-16`)
  - Separate year line was wasting tokens without adding information

#### Impact
- **Token Savings**: ~15 tokens saved per prompt (affects ALL prompts across all modes)
- **Information Loss**: None - full date already shows year
- **User Experience**: Cleaner prompt headers, more efficient token usage

#### Files Modified
- [aifred/lib/prompt_loader.py](aifred/lib/prompt_loader.py): Lines 137-147 (timestamp generation)

---

## [Unreleased] - 2025-11-15

### 🔍 Enhanced Debug Logging & Query Visibility

#### Added
- **Consistent Debug Logging Across All Modes** ([aifred/state.py:1014-1030](aifred/state.py#L1014-L1030), [aifred/lib/conversation_handler.py:395-414](aifred/lib/conversation_handler.py#L395-L414)):
  - "Eigenes Wissen" mode now shows comprehensive debug messages matching Automatik mode style
  - LLM preloading messages with precise timing: `🚀 Haupt-LLM wird vorgeladen...` → `✅ Haupt-LLM vorgeladen (X.Xs)`
  - System prompt creation confirmation
  - Token statistics: `📊 Haupt-LLM: input / num_ctx Tokens (max: limit)`
  - Temperature settings display
  - TTFT (Time To First Token) measurement
  - Final completion stats with tokens/s

- **Precise Preload Time Measurement** ([aifred/state.py:1019-1030](aifred/state.py#L1019-L1030)):
  - Ollama backend: Actual model loading time via `backend.preload_model()` (1-5 seconds)
  - vLLM/TabbyAPI: Preparation time only (models stay in VRAM, 0.1-0.5 seconds)
  - Backend-aware timing ensures accurate performance metrics

- **Optimized Query Display in Debug Console** ([aifred/lib/research/query_processor.py:61](aifred/lib/research/query_processor.py#L61)):
  - Shows the LLM-optimized search query after query optimization completes
  - Enables quality assessment of web research queries
  - Visible in all web research modes (Automatik, Websuche schnell, Websuche ausführlich)
  - Format: `🔎 Optimierte Query: [optimized search terms]`

#### Enhanced
- **Web Research Modes Debug Output** ([aifred/lib/research/query_processor.py:43-61](aifred/lib/research/query_processor.py#L43-L61)):
  - Query optimization progress: `🔍 Query-Optimierung läuft...`
  - Completion with timing: `✅ Query-Optimierung fertig (X.Xs)`
  - Optimized query display for quality assessment

#### Impact
- **Before**: Debug output varied significantly between modes, making performance comparison difficult
- **After**: All modes show consistent, detailed debug information for easier troubleshooting and optimization
- **User Benefit**: Better visibility into AIfred's internal processes, easier quality assessment of web searches

#### Files Modified
- [aifred/state.py](aifred/state.py): Lines 982-1030, 1036-1093 (Eigenes Wissen mode logging)
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 356-417 (Automatik mode logging)
- [aifred/lib/research/query_processor.py](aifred/lib/research/query_processor.py): Line 61 (optimized query display)

---

## [Unreleased] - 2025-11-14

### Fix: Research Mode Persistence

#### Fixed
- **Research Mode not persisted** ([aifred/state.py:1314](aifred/state.py#L1314)):
  - `set_research_mode_display()` changed the variable but didn't call `_save_settings()`
  - Settings infrastructure was complete (load + save to dict), only the trigger was missing
  - Inconsistent with other setters like `set_automatik_model()` which correctly save
  - Now calls `_save_settings()` after mode change to persist immediately

#### How it works
1. **Startup**: Loads `research_mode` from `settings.json` (Line 219) or falls back to `"automatik"` from `config.py`
2. **User changes mode**: UI calls `set_research_mode_display()` → `_save_settings()` → `settings.json` updated
3. **Next startup**: Saved mode is restored correctly

#### Impact
- **Before**: Research mode reset to default on every restart
- **After**: Research mode persists across sessions like all other settings

#### Files Modified
- [aifred/state.py](aifred/state.py): Line 1314 (added `_save_settings()` call)

---

### 🎯 Progress UI System Complete - MILESTONE

#### Added
- **Complete Progress Event Handling** ([aifred/state.py:942-960](aifred/state.py#L942-L960)):
  - Quick/Deep research modes now handle all progress events (`progress`, `history_update`, `thinking_warning`)
  - Identical event routing logic as Automatik mode
  - Shows Web-Scraping progress (1/3, 2/3, 3/3) and LLM generation phase
  - Visual feedback for all research pipeline stages

- **Pulsing Animation for All Modes** ([aifred/aifred.py:526,539,543](aifred/aifred.py#L526)):
  - Animation triggers on `progress_active | is_generating` (previously only `progress_active`)
  - "Generiere Antwort" now pulses in "none" mode (Eigenes Wissen) during LLM inference
  - Consistent visual feedback across all 4 research modes
  - Bold text weight during active phases

- **Dynamic Status Text** ([aifred/aifred.py:449-464](aifred/aifred.py#L449-L464)):
  - Status text shows "Generiere Antwort" when `is_generating=True` even if `progress_active=False`
  - Fixes idle state in "none" mode where status stayed on "Warte auf Eingabe"
  - Properly reflects system activity in all modes

#### Fixed
- **Progress Bar Visibility** ([assets/custom.css:90](assets/custom.css#L90)):
  - Removed `.rt-Box` from dark theme CSS selector
  - Orange progress bar fill (#e67700) was hidden by `!important` background override
  - Progress bar now visible in all research modes
  - Root cause: Commit d8e4d55 ("Force dark theme") introduced CSS specificity conflict

- **Missing Progress Events in Quick/Deep Modes**:
  - Quick/Deep modes had no progress event handling (only debug, content, result)
  - Web-Scraping and LLM phases were invisible to user
  - Now shows full pipeline: "Web-Scraping 1/7" → "Generiere Antwort"

#### Testing Results
- ✅ **Automatik Mode**: Progress bar + phases (Automatik → Scraping → LLM)
- ✅ **Quick Mode**: Progress bar + phases (Scraping 1/3 → LLM)
- ✅ **Deep Mode**: Progress bar + phases (Scraping 1/7 → LLM)
- ✅ **None Mode**: Pulsing "Generiere Antwort" during LLM

#### Technical Details
- Progress event flow: `scraper_orchestrator.py` → `orchestrator.py` → `state.py` → `aifred.py`
- Event types: `progress` (scraping, llm, compress), `debug`, `content`, `result`, `history_update`
- State variables: `progress_active`, `progress_phase`, `progress_current`, `progress_total`, `is_generating`
- Reflex reactive rendering: `rx.cond()` for conditional UI updates

#### Impact
- **Before**: Inconsistent progress feedback, Quick/Deep modes had no visual pipeline status
- **After**: Professional, consistent UI feedback across all modes. User always knows system status.
- **UX Improvement**: No more confusion about "is it working?" - clear visual feedback at every stage

#### Files Modified
- [assets/custom.css](assets/custom.css): Line 90 (removed `.rt-Box`)
- [aifred/state.py](aifred/state.py): Lines 942-960 (progress event handling)
- [aifred/aifred.py](aifred/aifred.py): Lines 449-464, 526, 539, 543 (status text, pulsing animation)
- [TODO.md](TODO.md): Comprehensive milestone documentation

---

### 🏷️ Source Label Consistency & Double Metadata Bug Fix

#### Fixed
- **Double Source Metadata Bug** ([aifred/lib/message_builder.py](aifred/lib/message_builder.py), [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py)):
  - Fixed issue where responses showed duplicate source labels (e.g., `( Inferenz: 62.3s, Quelle: Web-Recherche ) ( Inferenz: 53.2s, Quelle: LLM-Trainingsdaten )`)
  - Root cause: HTML metadata (`<span>` tags) and thinking collapsibles (`<details>` tags) were NOT removed from chat history before passing to LLM
  - LLM sometimes copied old metadata into new responses, resulting in duplicate sources
  - Solution: Enhanced `build_messages_from_history()` to strip ALL HTML tags and metadata using regex patterns

#### Changed
- **Message History Cleaning** ([aifred/lib/message_builder.py:86-100](aifred/lib/message_builder.py#L86-L100)):
  - Added `import re` for regex-based HTML tag removal
  - Four-step cleaning process for AI messages:
    1. Remove thinking collapsibles: `<details>...</details>`
    2. Remove metadata spans: `<span style="...">( Inferenz: ... )</span>`
    3. Fallback: Remove text-based metadata patterns
    4. Cleanup: Remove multiple newlines and excess whitespace
  - Prevents LLM from seeing or copying old metadata from history

- **Source Label Consistency** ([aifred/lib/conversation_handler.py:480-486](aifred/lib/conversation_handler.py#L480-L486)):
  - Replaced ambiguous `"LLM-Trainingsdaten"` label with context-aware labels:
    - `"Cache+LLM (RAG)"` - RAG context from Vector Cache
    - `"LLM (mit History)"` - Chat history available as context (NEW)
    - `"LLM"` - Pure LLM without additional context (NEW)
  - Consistent with existing labels: `"Vector Cache"` (direct hit), `"Web-Recherche"` (agent research)

#### Impact
- **Before**: Confusing duplicate source labels, inconsistent terminology
- **After**: Clean, single source label per response with clear context indication
- **User Experience**: Users can now clearly see where each response comes from:
  - First message: `( Inferenz: 2.5s, Quelle: LLM )`
  - Follow-up with history: `( Inferenz: 3.2s, Quelle: LLM (mit History) )`
  - RAG context: `( Inferenz: 4.1s, Quelle: Cache+LLM (RAG) )`
  - Web research: `( Inferenz: 62.3s, 35.2 tok/s, Quelle: Web-Recherche )`

#### Files Modified
- [aifred/lib/message_builder.py](aifred/lib/message_builder.py): Lines 11 (import re), 84-100 (HTML cleaning)
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 480-486 (source labels)

---

### 🧹 Debug Console Separator Structure

#### Fixed
- **Separator Placement Logic** ([aifred/lib/research/context_builder.py](aifred/lib/research/context_builder.py), [aifred/state.py](aifred/state.py)):
  - Separators now appear AFTER each logical processing unit (not before)
  - Implemented "separator marks end of unit" principle across all code paths
  - Eliminated double separators after LLM completion
  - Three logical units with proper separation:
    1. LLM Response Generation → Separator
    2. Vector Cache Decision (web research only) → Separator
    3. History Compression Check → Separator

#### Changed
- **Web Research Path** ([aifred/lib/research/context_builder.py:204-207](aifred/lib/research/context_builder.py#L204-L207)):
  - Added separator after "✅ Haupt-LLM fertig" message
  - Added separator after Cache-Decision block (lines 329-332)
- **Normal Chat Path** ([aifred/state.py:866-869](aifred/state.py#L866-L869)):
  - Removed redundant separator (conversation_handler already emits one)
- **Compression Check** ([aifred/state.py:997-1016](aifred/state.py#L997-L1016)):
  - Separator now appears after compression completion message

#### Impact
- **Debug Console Output**: Clean, predictable structure with logical block boundaries
- **Before**: Inconsistent separator placement, double separators in some paths
- **After**: Each processing unit ends with exactly one separator line

#### Files Modified
- [aifred/lib/research/context_builder.py](aifred/lib/research/context_builder.py): Lines 204-207, 329-332
- [aifred/state.py](aifred/state.py): Lines 866-869 (commented), 997-1016

---

### 🔄 Auto-Reload Model List on Backend Restart

#### Added
- **Model List Auto-Refresh on Ollama Restart** ([aifred/state.py:1044-1092](aifred/state.py#L1044-L1092)):
  - After Ollama service restart via UI, automatically reload model list from `/api/tags`
  - Update both session state (`self.available_models`) and global state (`_global_backend_state`)
  - No need to restart AIfred just to see newly downloaded models
  - Shows immediate feedback: "🔄 Reloading model list..." and "✅ Model list updated: N models found"

#### Changed
- **`restart_backend()` Method Enhancement**:
  - Added automatic model list refresh after Ollama restart
  - Uses same curl-based API call as initial backend initialization
  - Preserves existing vLLM/TabbyAPI restart logic unchanged

#### Impact
- **User Experience**: Download new models → Restart Ollama → Models instantly available in dropdown
- **Before**: Had to restart entire AIfred service to refresh model list
- **After**: Just click "Restart Ollama" button in system control panel

#### Files Modified
- [aifred/state.py](aifred/state.py): Lines 1044-1092

---

### 🌍 Language Detection for All Prompts

#### Fixed
- **Language Not Passed to Prompt Loading Functions** (8 locations across 7 files):
  - Language was detected but not passed as `lang=` parameter to prompt functions
  - German user queries were receiving English prompts despite correct detection
  - Root cause: Missing `detected_user_language` parameter in function calls

#### Changed
- **Intent Detection** ([aifred/lib/intent_detector.py](aifred/lib/intent_detector.py)):
  - Line 62: Added `lang=detected_user_language` to `get_intent_detection_prompt()`
  - Lines 110-113: Added language detection for followup intent classification
- **Query Optimization** ([aifred/lib/query_optimizer.py:47](aifred/lib/query_optimizer.py#L47)):
  - Added `lang=detected_user_language` to `get_query_optimization_prompt()`
- **Decision Making** ([aifred/lib/conversation_handler.py:268](aifred/lib/conversation_handler.py#L268)):
  - Added `lang=detected_user_language` to `get_decision_making_prompt()`
- **Cache Hit Prompt** ([aifred/lib/research/cache_handler.py:77](aifred/lib/research/cache_handler.py#L77)):
  - Added `lang=detected_user_language` to `load_prompt('system_rag_cache_hit')`
- **System RAG Prompt** ([aifred/lib/research/context_builder.py:99](aifred/lib/research/context_builder.py#L99)):
  - Added `lang=detected_user_language` and `user_text` parameter
- **Cache Decision** ([aifred/lib/research/context_builder.py:241](aifred/lib/research/context_builder.py#L241)):
  - Added `lang=detected_user_language` to `load_prompt('cache_decision')`
- **RAG Relevance Check** ([aifred/lib/rag_context_builder.py:89](aifred/lib/rag_context_builder.py#L89)):
  - Added `lang=detected_user_language` to `load_prompt('rag_relevance_check')`
- **History Summarization** ([aifred/lib/context_manager.py:290](aifred/lib/context_manager.py#L290)):
  - Special case: Detects language from first user message in conversation history
  - Fallback to "de" if no messages available

#### Impact
- **User Experience**: German queries now receive German prompts, English queries receive English prompts
- **All Subsystems Affected**: Intent detection, query optimization, research mode, cache decisions, history compression
- **Consistent i18n**: All 8 prompt loading locations now respect detected language

#### Files Modified
- [aifred/lib/intent_detector.py](aifred/lib/intent_detector.py): Lines 62, 110-113
- [aifred/lib/query_optimizer.py](aifred/lib/query_optimizer.py): Line 47
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 268-270
- [aifred/lib/research/cache_handler.py](aifred/lib/research/cache_handler.py): Lines 76-89
- [aifred/lib/research/context_builder.py](aifred/lib/research/context_builder.py): Lines 98-110, 244-251
- [aifred/lib/rag_context_builder.py](aifred/lib/rag_context_builder.py): Lines 86-100
- [aifred/lib/context_manager.py](aifred/lib/context_manager.py): Lines 289-301

---

### 🧠 Thinking Mode Support for Ollama and vLLM Backends

#### Added
- **Ollama Thinking Mode Implementation** ([aifred/backends/ollama.py](aifred/backends/ollama.py)):
  - Added `"think": true` API parameter support in `chat()` and `chat_stream()` methods
  - Parse separate `thinking` and `content` fields from Ollama response
  - Wrap thinking output in `<think>...</think>` tags for unified formatting
  - Streaming support: Properly handle thinking chunks before content chunks
- **vLLM Thinking Mode Enhancement** ([aifred/backends/vllm.py](aifred/backends/vllm.py)):
  - Improved type safety: Replaced `# type: ignore` with proper `Dict[str, Any]` annotations
  - Use `chat_template_kwargs: {"enable_thinking": bool}` in `extra_body` for Qwen3 models
  - Consistent implementation across `chat()` and `chat_stream()` methods
- **Unified Thinking Process Formatting** ([aifred/lib/formatting.py](aifred/lib/formatting.py)):
  - Created `format_metadata()` function for metadata display (color: `#bbb`, font-size: `0.85em`)
  - Enhanced `format_thinking_process()` with model name and inference time in collapsible header
  - Added line break reduction regex (`r'\n\n+'`) to reduce excessive blank lines while preserving paragraphs
  - Fallback logic for malformed `<think>` tags (missing opening tag)
  - Updated `build_debug_accordion()` with same improvements for agent research mode
- **UI Styling** ([aifred/theme.py](aifred/theme.py)):
  - Added `.thinking-compact` CSS class for proper paragraph spacing (`0.75em` margins)
  - Text color matches collapsible header (`#aaa`)
  - Compact spacing for first/last child elements
- **User Message HTML Rendering** ([aifred/aifred.py](aifred/aifred.py#L725)):
  - Changed from `rx.text()` to `rx.markdown()` to properly render HTML metadata spans
- **Settings Update** ([aifred/lib/settings.py](aifred/lib/settings.py#L74)):
  - Default `enable_thinking` set to `True` for optimal user experience

#### Changed
- **Type Safety Improvements**:
  - Import `Any` from typing in vLLM backend
  - Declare `extra_body: Dict[str, Any] = {}` instead of untyped dict with `# type: ignore`
  - Removed all type ignore comments in vLLM backend
- **Metadata Color**: Adjusted from `#999` → `#aaa` → `#bbb` for better readability
- **Collapsible Styling**: Removed complex inline div styling in favor of CSS class approach

#### Fixed
- **HTML Rendering in User Messages**: Metadata now properly displays as styled HTML instead of raw tags
- **Type Safety**: MyPy passes without warnings for vLLM `extra_body` dictionary assignments
- **Line Break Handling**: Regex correctly reduces 2+ consecutive newlines to exactly 2 (one blank line)
- **Paragraph Spacing**: Thinking process collapsibles now have proper spacing (not too cramped, not too spaced)

#### Technical Details
- **Ollama API**: Uses `"think": true` payload parameter (not `enable_thinking` in options)
- **Ollama Response Structure**: Provides separate `thinking` and `content` fields in message dict
- **vLLM API**: Uses `extra_body["chat_template_kwargs"] = {"enable_thinking": bool}`
- **Unified Format**: Both backends output `<think>...</think>` wrapped content for consistent parsing
- **Automatik-LLM**: Thinking mode intentionally DISABLED for all automatik tasks (8x faster decisions)

#### Files Modified
- [aifred/backends/ollama.py](aifred/backends/ollama.py): Lines 93-95, 116-125, 199-236
- [aifred/backends/vllm.py](aifred/backends/vllm.py): Lines 9, 79, 88-90, 163, 172-174
- [aifred/lib/formatting.py](aifred/lib/formatting.py): Lines 13-37, 64-152, 155-235
- [aifred/theme.py](aifred/theme.py): Lines 125-142
- [aifred/lib/settings.py](aifred/lib/settings.py): Line 74
- [aifred/aifred.py](aifred/aifred.py): Line 725
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 467-478

---

### 📱 Mobile Dropdown Optimization

#### Problem Solved
- **Fixed**: Select dropdowns disappeared below viewport on mobile devices
- **Impact**: Users couldn't select models/backends when list was too long or positioned at bottom
- **Root Cause**: Default "item-aligned" positioning opens downward without viewport awareness
- **Solution**: Intelligent positioning + scrollable dropdowns with max-height

#### Implementation
- **Intelligent Positioning**: Added `position="popper"` to all select dropdowns
  - Backend select, Model select, Automatik-Model select
  - Adapts to available viewport space (opens upward if no space below)
- **Scrollable Dropdowns**: CSS max-height with internal scroll
  - Max height: 300px or available viewport height (whichever is smaller)
  - Internal scrollbar when list exceeds height
  - Dropdown stays open while scrolling (no accidental close)
- **Mobile-Friendly**: Touch scroll works correctly inside dropdown

#### Files Modified
- [aifred/aifred.py](aifred/aifred.py): Added `position="popper"` to 3 select components
- [aifred/theme.py](aifred/theme.py): CSS for `.rt-SelectContent` and `.rt-SelectViewport`

---

### 🛡️ GPU Compatibility Backend Filter

#### Problem Solved
- **Fixed**: Incompatible backends (vLLM, TabbyAPI) were selectable on Pascal GPUs (P40, GTX 10 series)
- **Impact**: vLLM would crash with Triton compiler errors or be extremely slow (FP16 1:64 ratio)
- **Root Cause**: Backend selection showed all backends regardless of GPU capabilities
- **Solution**: Automatic backend filtering based on GPU detection

#### Implementation
- **GPU Detection**: Existing `GPUDetector` now filters UI backend options
  - Detects GPU compute capability and FP16 performance
  - Tesla P40 (Compute 6.1) → Only shows "ollama" backend
  - RTX 3060+ (Compute 8.6) → Shows "ollama", "vllm", "tabbyapi"
- **Auto-Switch**: If saved backend is incompatible, auto-switch to first available backend
- **UI Updates**:
  - Backend select dropdown shows only compatible backends
  - GPU info badge shows detected GPU and compute capability
  - Removed redundant GPU warning box (no longer needed)
- **Backend Requirements**:
  - **Ollama**: Works on ALL GPUs (Compute 3.5+, INT8/Q4/Q8 quantization)
  - **vLLM**: Requires Compute 7.0+, fast FP16 performance (Volta or newer)
  - **TabbyAPI**: Same as vLLM (Compute 7.0+, fast FP16)

#### GPU Compatibility Matrix
| GPU | Compute Cap | Available Backends | Reason |
|-----|-------------|-------------------|--------|
| Tesla P40 | 6.1 | ollama only | FP16 ratio 1:64 (extremely slow) |
| Tesla P100 | 6.0 | ollama only | Compute < 7.0 (Triton unsupported) |
| GTX 1080 Ti | 6.1 | ollama only | Pascal architecture (slow FP16) |
| RTX 2080 | 7.5 | ollama, vllm, tabbyapi | Turing (fast FP16, Tensor Cores) |
| RTX 3060 | 8.6 | ollama, vllm, tabbyapi | Ampere (fast FP16, AWQ Marlin) |
| RTX 4090 | 8.9 | ollama, vllm, tabbyapi | Ada Lovelace (excellent) |

#### Files Modified
- [aifred/state.py](aifred/state.py#L146): Added `available_backends` state field
- [aifred/state.py](aifred/state.py#L240-L251): Backend filtering logic on session load
- [aifred/aifred.py](aifred/aifred.py#L994): Dynamic backend select with `AIState.available_backends`
- [aifred/aifred.py](aifred/aifred.py#L1013-L1028): GPU info badge
- [aifred/lib/gpu_detection.py](aifred/lib/gpu_detection.py): Existing GPU detection (no changes)

---

### 📐 vLLM Context Auto-Detection (40K-128K+ Support)

#### Problem Solved
- **Fixed**: vLLM context limit was only 16K tokens
- **Impact**: Responses were cut off mid-sentence, chat history was severely limited
- **Root Cause**: Hardcoded context limits didn't match actual model capabilities
- **Solution**: Automatic detection from model's config.json

#### Implementation
- **Auto-Detection**: `get_model_max_position_embeddings()` reads `max_position_embeddings` from HuggingFace cache
  - Searches `~/.cache/huggingface/hub/models--{vendor}--{model}/snapshots/*/config.json`
  - Returns native context limit (e.g., 40,960 for Qwen3-8B-AWQ, 131,072 for Qwen2.5-Instruct)
  - No more hardcoded values - works with any model!
- **Enhanced**: `vLLMProcessManager.start()` uses auto-detected context
  - `max_model_len=None` triggers auto-detection
  - Falls back to vLLM default if config not found
- **YaRN Support**: Optional RoPE scaling for extending context beyond training limits
  - Accepts YaRN config dict: `{"rope_type": "yarn", "factor": 2.0, "original_max_position_embeddings": 40960}`
  - Can extend context (e.g., 40K → 80K with factor=2.0)
  - Not used by default - native context is sufficient
- **Error Diagnostics**: Improved vLLM startup error logging (captures stderr)
- **Memory Fix**: Increase GPU memory utilization to 95% (40K context needs ~5.6 GiB KV cache)
- **Compatibility**: Use vLLM v0.11.0 defaults (v1 engine with multiprocessing)

#### Context Limits
- **Before**: 16K tokens (hardcoded, responses cut off!)
- **After**: Hardware-constrained maximum:
  - **RTX 3060 (12GB, Ampere 8.6)**: **26,608 tokens** @ 90% GPU memory ✅ Tested
  - Native model support: 40,960 tokens (requires ~5.6 GiB KV cache)
- **Note**: Context size limited by VRAM + GPU architecture, not model capability
- **VRAM Usage**: ~12 GB (97.7% utilization) at 26K context - GPU fully utilized but stable
- **Future**: Can use YaRN for extension when more VRAM available (e.g., RTX 3090, A100, H100)

#### Files Modified
- [aifred/lib/vllm_manager.py](aifred/lib/vllm_manager.py#L19-L64): Added `get_model_max_position_embeddings()`
- [aifred/lib/vllm_manager.py](aifred/lib/vllm_manager.py#L134-L158): Auto-detect in `start()` method
- [aifred/state.py](aifred/state.py#L569-L580): Removed hardcoded values, use auto-detection

---

### ⚡ Backend Pre-Initialization (Page Reload Performance)

#### Problem Solved
- **Fixed**: Backend re-initialization on every page reload (F5)
- **Impact**: Eliminated 30-120s wait time on page refresh
- **Behavior**: Backend now initializes ONCE at server start, persists across page reloads

#### Implementation
- **Added**: Module-level `_global_backend_state` dict for persistent backend state
- **Added**: `_global_backend_initialized` flag to prevent redundant initialization
- **Refactored**: `on_load()` method with two-phase initialization:
  - **Global Phase** (runs once at server start):
    - Debug log initialization
    - Language settings
    - Vector Cache connection
    - GPU detection
  - **Session Phase** (runs per user/tab/reload):
    - Load user settings
    - Generate session ID
    - Restore backend state from global cache
- **Optimized**: `initialize_backend()` with fast/slow paths:
  - **Fast Path**: Backend already initialized → Restore from global state (instant!)
  - **Slow Path**: First initialization or backend switch → Full model loading
- **Optimized**: vLLM Process Manager persistence:
  - `_vllm_manager` stored in global state
  - vLLM server survives page reloads
  - Prevents unnecessary vLLM restarts (saves 70-120s)

#### State Persistence
- **Preserved on page reload**:
  - Chat history
  - Debug console messages
  - Backend configuration
  - Loaded models
  - vLLM server process
  - GPU detection results

#### Restart Buttons
- **Enhanced**: `restart_backend()` method:
  - Ollama: Restarts systemd service
  - vLLM: Stops and restarts vLLM server process
  - TabbyAPI: Shows info message (manual restart)
- **Preserved**: "AIfred Neustarten" button behavior:
  - Clears chat history, debug console, caches
  - Does NOT restart backend or vLLM
  - Soft restart for development (hot-reload mode)
  - Hard restart via systemd for production

#### Code Quality
- **Passed**: ruff linter checks (no errors)
- **Fixed**: Unused variable `research_result` in generate loop
- **Added**: Type annotations for `_global_backend_state: dict[str, Any]`
- **Tested**: Backend switching, page reload, restart buttons

---

### 🔍 GPU Detection & Compatibility Checking

#### GPU Detection System
- **Added**: `aifred/lib/gpu_detection.py` - Automatic GPU capability detection
- **Features**:
  - Detects GPU compute capability via nvidia-smi
  - Identifies compatible/incompatible backends per GPU
  - Warns about known GPU limitations (Tesla P40 FP16 issues, etc.)
- **State Integration**:
  - GPU info stored in AIState (gpu_name, gpu_compute_cap, gpu_warnings)
  - Detection runs on startup via `on_load()`
  - Debug console shows GPU capabilities and warnings

#### UI Warnings
- **Added**: Visual warning in Settings when vLLM selected on incompatible GPU
- **Shows**:
  - GPU name and compute capability
  - Backend requirements (Compute Cap 7.5+ for vLLM/AWQ)
  - Recommendation to switch to Ollama for better performance
- **Styling**: Red warning box with icon, auto-shows when vLLM + Pascal GPU

#### Download Scripts Enhanced
- **Enhanced**: `download_vllm_models.sh` with GPU compatibility check
- **Features**:
  - Automatic GPU detection before download
  - Detailed warning for incompatible GPUs (P40, GTX 10 series)
  - Explains why vLLM/AWQ won't work (Triton, FP16 ratio, Compute Cap)
  - Offers exit with recommendation to use Ollama
  - User can override with explicit confirmation

#### Documentation
- **Added**: `docs/GPU_COMPATIBILITY.md` - Comprehensive GPU compatibility guide
- **Covers**:
  - GPU compatibility matrix (Pascal, Turing, Ampere, Ada, Hopper)
  - Backend comparison (Ollama GGUF vs vLLM AWQ vs TabbyAPI EXL2)
  - Technical explanation of Pascal limitations
  - Performance benchmarks (P40 vs RTX 4090)
  - Recommendations by use case
  - Troubleshooting guide

#### Backend Compatibility Summary
- **Ollama (GGUF)**: ✅ Works on all GPUs (Compute Cap 3.5+)
- **vLLM (AWQ)**: ⚠️ Requires Compute Cap 7.5+ (Turing+), fast FP16
- **TabbyAPI (EXL2)**: ⚠️ Requires Compute Cap 7.0+ (Volta+), fast FP16

#### Known GPU Issues Documented
- **Tesla P40**: FP16 ratio 1:64 → vLLM/ExLlama ~1-5 tok/s (unusable)
- **Tesla P100**: FP16 ratio 1:2 → vLLM possible but slower than Ollama
- **GTX 10 Series**: Compute Cap 6.1 → vLLM not supported
- **Recommendation**: Use Ollama (GGUF) on Pascal GPUs for best performance

### 🚀 Performance - 8x Faster Automatik, 7s Saved per Web Research

#### vLLM Preloading Optimization
- **Skip unnecessary preloading** for vLLM/TabbyAPI (models stay in VRAM)
- **Result**: 7s faster web research, UI shows "ℹ️ Haupt-LLM bereits geladen"
- **Files**: `aifred/backends/vllm.py`, `aifred/backends/tabbyapi.py`, `aifred/lib/research/scraper_orchestrator.py`

#### Thinking Mode Disabled for Automatik Tasks
- **Problem**: Qwen3 Thinking Mode slowed decisions from 1-2s to 7-13s
- **Solution**: `enable_thinking=False` for all automatik tasks (decisions, intent, RAG)
- **Result**: 8x faster total flow (3s instead of 24s)
  - Automatik decision: 8.7s → 2.1s (4x faster)
  - Intent detection: 13.0s → 0.3s (43x faster)
- **Files**: Fixed parameter passing in `llm_client.py`, vLLM `chat_template_kwargs` structure, 9 LLM call sites

### 🎯 Context Window Improvements

#### Real Tokenizer instead of Estimation
- **Problem**: Token estimation (3.5 chars/token) was 25% too low → context overflow
- **Solution**: HuggingFace AutoTokenizer with local cache
- **Fallback**: 2.5 chars/token (conservative) when tokenizer unavailable
- **Files**: `aifred/lib/context_manager.py` + 5 call sites

#### vLLM Context Auto-Detection (16K → 40K for Qwen3)
- **Problem**: vLLM hardcoded to 16K despite Qwen3-8B supporting 40K
- **Solution**: Remove `--max-model-len` → auto-detect from model config
- **Benefits**:
  - Qwen3-8B: 40K context (matches Ollama)
  - Qwen2.5-32B: 128K context automatically
  - No hardcoding, each model uses native limit
- **Files**: `vllm_startup.py`, `aifred/lib/vllm_manager.py`

### 🐛 Bug Fixes

- **Backend switching**: Fixed AttributeError and wrong model selection
- **Dead code**: Removed 83 lines (77 unreachable + 6 unused variables)
- **UI**: Debug console limit 100 → 500 messages

### 🔄 Portability

- ✅ No absolute paths
- ✅ No system-specific dependencies
- ✅ HuggingFace tokenizer: offline-capable (local cache)
- ✅ vLLM auto-detection: works on any system
- ✅ Systemd services: Template-based with sed substitution
- ✅ **Fully portable to MiniPC**

### 📦 Model Configuration

#### Restructured Download Scripts with YaRN Support
- **Added**: Separate download scripts for better organization
  - `download_ollama_models.sh` - Ollama (GGUF) models
  - `download_vllm_models.sh` - vLLM (AWQ) models with YaRN docs
  - `download_all_models.sh` - Master script for both backends
- **Archived**: Old scripts renamed to `.old` (preserved for reference)

#### Qwen3 AWQ Models (Primary Recommendation)
- **Added**: Qwen3 AWQ series with YaRN context extension support
  - Qwen3-4B-AWQ (~2.5GB, 40K native, YaRN→128K)
  - Qwen3-8B-AWQ (~5GB, 40K native, YaRN→128K)
  - Qwen3-14B-AWQ (~8GB, 32K native, YaRN→128K)
- **Features**:
  - Optional Thinking Mode (enable_thinking parameter)
  - Newest generation (2025)
  - Flexible context: Native 32-40K, YaRN extendable to 64K/128K

#### Qwen2.5 Instruct-AWQ Models (Alternative)
- **Available**: As alternative option with native 128K context
  - Qwen2.5-7B-Instruct-AWQ (~4GB, 128K native)
  - Qwen2.5-14B-Instruct-AWQ (~8GB, 128K native)
  - Qwen2.5-32B-Instruct-AWQ (~18GB, 128K native)
- **Benefits**: No YaRN needed, older generation but proven stable

#### YaRN Context Extension Support
- **Documentation**: Added comprehensive YaRN configuration examples
- **Flexible Factors**:
  - factor=2.0 → 64K context (recommended for chat history)
  - factor=4.0 → 128K context (for long documents)
- **Implementation**: Command-line and Python examples in download scripts
- **Trade-offs**: Documented perplexity loss vs context gain

## [1.0.0] - 2025-11-10

### 🎉 Milestone: Vector Cache Production Ready

#### Added
- **ChromaDB Vector Cache**: Thread-safe semantic caching for web research results
  - Docker-based ChromaDB server mode (port 8000)
  - Automatic duplicate detection with configurable distance thresholds
  - Time-based cache invalidation (5-minute threshold for explicit research keywords)
  - Query-only embeddings for improved similarity matching (distance 0.000 for exact matches)
  - Auto-learning from web research results
- **Configurable Distance Thresholds** (`aifred/lib/config.py`):
  - `CACHE_DISTANCE_HIGH = 0.5` - High confidence cache hits
  - `CACHE_DISTANCE_MEDIUM = 0.85` - Medium confidence cache hits
  - `CACHE_DISTANCE_DUPLICATE = 0.3` - Duplicate detection for explicit keywords
  - `CACHE_TIME_THRESHOLD = 300` - 5 minutes for time-based invalidation
- **Enhanced Cache Logging**: Distance and confidence displayed for all cache operations (hits, misses, duplicates)
- **Docker Compose Consolidation**: Unified `docker/docker-compose.yml` with ChromaDB + optional SearXNG
- **Docker Documentation**: New `docker/README.md` with service management instructions

#### Changed
- **Vector Cache Architecture**: Migrated from PersistentClient to HttpClient (Docker server mode)
  - Fixes: File lock issues and deadlocks in async operations
  - Improvement: Thread-safe by design, no worker threads needed
- **Cache Query Strategy**: Implemented `query_newest()` method
  - Returns most recent match instead of best similarity match
  - Prevents outdated cache entries from being returned
- **Context Window Management**: Generous reserve strategy (8K-16K tokens) to prevent answer truncation
- **Project Structure**:
  - Moved `docker-compose.yml` from root to `docker/` directory
  - Consolidated separate ChromaDB and SearXNG compose files
- **Duplicate Detection**: Time-aware duplicate prevention
  - Skip save if similar entry exists and is < 5 minutes old
  - Allow new entry if existing entry is > 5 minutes old (allows updates)

#### Removed
- **Obsolete Implementations**: Deleted `archive/vector_cache_old/` directory
  - Old PersistentClient implementation (vector_cache.py)
  - Old worker thread implementation (vector_cache_v2.py)
  - Still available in git history if needed

#### Fixed
- **KeyError 'data'**: Fixed cache hit result format for explicit research keywords
- **Missing user_with_time**: Added timestamp generation for history entries
- **Cache Miss on Recent Entries**: Fixed `query_newest()` to find most recent duplicate
- **Duplicate Log Messages**: Proper distinction between saved entries and skipped duplicates
- **Distance Logging**: Distance now displayed for all cache operations (hits and misses)

#### Technical Details
- **ChromaDB Version**: Using latest ChromaDB Docker image
- **API Version**: ChromaDB v2 API (v1 deprecated)
- **Collection Management**:
  - Collection name: `research_cache`
  - Persistent storage: `./aifred_vector_cache/` (Docker volume)
  - Health checks: Automatic with 30s interval
- **Cache Statistics**: Available via `get_cache().get_stats()`

#### Migration Notes
- **Docker Commands Updated**: All docker-compose commands now require `-f docker/docker-compose.yml` or working from `docker/` directory
- **ChromaDB Reset**: Two methods documented in README
  - Option 1: Full restart (stop container, delete data, restart)
  - Option 2: API-based collection deletion (faster, no container restart)
- **Configuration**: All cache thresholds centralized in `aifred/lib/config.py`

---

## [1.1.0] - 2025-11-10

### 🧠 Intelligent Cache Decision System

#### Added
- **LLM-Based Cache Decision**: Automatic cache filtering with AI-powered override capability
  - Two-stage filter: Volatile keywords → LLM decision
  - Override logic: Concept questions (e.g., "Was ist Wetter?") are cached despite volatile keywords
  - Automatik-LLM makes decision (fast, deterministic with temperature=0.1)
- **Volatile Keywords List** (`aifred/lib/config.py`):
  - `CACHE_EXCLUDE_VOLATILE` - 40+ keywords for volatile data detection
  - Weather, finance, live sports, breaking news, time-specific queries
  - Triggers LLM decision for smart caching
- **Cache Decision Prompt** (`prompts/de/cache_decision.txt`):
  - Clear rules: Cache facts/concepts, don't cache live data
  - Examples for both cacheable and non-cacheable queries
  - Override examples for ambiguous cases
- **Source Attribution**: Transparent source labeling in chat history
  - "Quelle: LLM-Trainingsdaten" - Answer from model's training data
  - "Quelle: Vector Cache" - Answer from semantic cache
  - "Quelle: Session Cache" - Answer from session-based cache
  - "Quelle: Web-Recherche" - Answer from fresh web research
- **Cache Inspection Scripts**:
  - `scripts/list_cache.py` - List all cached entries with timestamps
  - `scripts/search_cache.py` - Semantic similarity search in cache

#### Changed
- **Cache Distance Thresholds**: Stricter matching for better quality
  - `CACHE_DISTANCE_MEDIUM` lowered from 0.85 to 0.5
  - Preparation for RAG mode (0.5-1.2 range)
- **Cache Auto-Learning Logic** (`context_builder.py`):
  - Intelligent filtering before saving to cache
  - LLM evaluates if content is timeless or volatile
  - Debug messages for cache decision transparency
- **Volatile Keywords**: Moved to external file for easier maintenance
  - Now loaded from `prompts/cache_volatile_keywords.txt`
  - Multilingual file (German + English keywords)
  - Easy to edit without code changes
  - 68 keywords covering weather, finance, sports, news, time references

#### Fixed
- **UnboundLocalError**: Fixed duplicate `load_prompt` import causing variable shadowing
  - Removed local imports at lines 231 and 261 in `context_builder.py`
  - Now uses module-level import correctly
- **Deadlock in Cache Decision**: Fixed LLM client resource conflict
  - Was creating new LLMClient instances for cache decision
  - Now uses existing `automatik_llm_client` parameter
  - Prevents deadlock when Haupt-LLM just finished generating
  - Removed unnecessary `from ..llm_client import LLMClient` import

#### Technical Details
- **Cache Decision Flow**:
  1. Check user query for volatile keywords
  2. If keyword found → Ask LLM (can override to "cacheable")
  3. If no keyword → Ask LLM (default decision)
  4. Save to cache only if LLM approves
- **Source Display Format**:
  - Appears at end of AI answer (not user question)
  - Format: `(Inferenz: 2.5s, Quelle: <source>)`
  - Consistent across all answer types

---

## [1.3.0] - 2025-11-11

### 🚀 Pure Semantic Deduplication + Smart Cache for Explicit Research

#### Added
- **Smart Cache-Check for Explicit Research Keywords** (`conversation_handler.py`):
  - Cache check BEFORE web research for keywords like "recherchiere", "google", "suche im internet"
  - Distance < 0.05 (practically identical) → Use cache (0.15s instead of 100s)
  - Distance ≥ 0.05 → Perform fresh research
  - Transparent display: Shows cache age (e.g., "Cache-Hit (681s old, d=0.0000)")
  - User can still force fresh research via UI mode selection (Web-Suche schnell/tief)
- **ChromaDB Maintenance Tool** (`chroma_maintenance.py`):
  - Display cache statistics (entries, age, size)
  - Find duplicates (text similarity-based)
  - Remove duplicates (keeps newest entry)
  - Delete old entries (by age threshold)
  - Clear entire database
  - Dry-run mode for safe testing

#### Changed
- **Pure Semantic Deduplication** (No Time Dependencies):
  - Removed: `CACHE_TIME_THRESHOLD` (5-minute logic)
  - New: Always update semantic duplicates (distance < 0.3) regardless of age
  - Benefit: Consistent behavior, no race conditions, latest data guaranteed
  - Affected files: `vector_cache.py`, `config.py`, `conversation_handler.py`
- **Automatik-LLM Default Model**:
  - Changed from `qwen3:8b` to `qwen2.5:3b`
  - Performance: 2.7x faster decisions (0.3s instead of 0.8s)
  - VRAM: ~63% reduction (~3GB instead of ~8GB)
  - Main LLM remains `qwen3:8b` for final answers

#### Fixed
- **LLMResponse AttributeError** (`context_builder.py`):
  - Fixed: `response.get('message', {}).get('content', '')` → `response.text`
  - Issue: LLMResponse is dataclass with `.text` attribute, not a dict
  - Affected: Cache decision logic (2 locations)
- **10x Python Duplicates**:
  - Root cause: Time-based logic allowed duplicates after 5 minutes
  - Fix: Pure semantic deduplication always updates duplicates
  - Result: No more duplicate cache entries

#### Performance
- **Identical Research Query**: ~667x faster (0.15s instead of 100s) ✅
- **Automatik Decision**: 2.7x faster (0.3s instead of 0.8s) ✅
- **VRAM Savings**: ~63% less for Automatik-LLM ✅

#### Breaking Changes
None - Fully backwards compatible

---

## [Unreleased]

### Planned Features
- RAG mode improvements: Better relevance detection
- Cache statistics dashboard in UI
- Export/import cache entries
- Multi-language support for cache queries
- Background cache cleanup scheduler

---

**Note**: This is the first formal release with changelog tracking. Previous development history is available in git commit history.
