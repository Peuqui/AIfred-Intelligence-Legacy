"""
Context Manager - Token and Context Window Management

Handles context limits and token estimation for LLMs:
- Query model context limits from backends (on-demand, no caching)
- Calculate optimal num_ctx for requests
- Token estimation for messages (using HuggingFace tokenizers)
- History compression (summarize_history_if_needed)
"""

import time
import asyncio
from typing import Dict, List, Optional, AsyncIterator
from .logging_utils import log_message, console_separator
from .prompt_loader import load_prompt
from .formatting import format_number
from .config import (
    HISTORY_COMPRESSION_THRESHOLD,
    HISTORY_MESSAGES_TO_COMPRESS,
    HISTORY_MAX_SUMMARIES,
    HISTORY_SUMMARY_TARGET_TOKENS,
    HISTORY_SUMMARY_TARGET_WORDS,
    HISTORY_SUMMARY_TEMPERATURE,
    HISTORY_SUMMARY_CONTEXT_LIMIT
)

# Global tokenizer cache (model_name -> tokenizer)
_tokenizer_cache = {}


def count_tokens_with_tokenizer(text: str, model_name: str) -> int:
    """
    Count tokens using HuggingFace AutoTokenizer (cached, fast after first load)

    Args:
        text: Text to tokenize
        model_name: HuggingFace model name (e.g., "Qwen/Qwen3-8B-AWQ")

    Returns:
        int: Exact token count
    """
    global _tokenizer_cache

    # Check cache first
    if model_name not in _tokenizer_cache:
        try:
            from transformers import AutoTokenizer
            # Load tokenizer (cached by HuggingFace after first download)
            _tokenizer_cache[model_name] = AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=True,
                local_files_only=False  # Allow download if not cached
            )
            log_message(f"✅ Loaded tokenizer for {model_name}")
        except Exception as e:
            log_message(f"⚠️ Could not load tokenizer for {model_name}: {e}")
            return None

    try:
        tokenizer = _tokenizer_cache[model_name]
        tokens = tokenizer.encode(text, add_special_tokens=True)
        return len(tokens)
    except Exception as e:
        log_message(f"⚠️ Tokenization failed: {e}")
        return None


def strip_thinking_blocks(text: str) -> str:
    """
    Remove <think>...</think> blocks from text (for History Compression).

    These blocks contain:
    - DeepSeek Reasoning (thinking process)
    - Vision-LLM JSON (structured extraction)

    Args:
        text: Text with potential <think> blocks

    Returns:
        Text without <think> blocks
    """
    import re
    # Remove all <think>...</think> blocks (non-greedy, multi-line)
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


def estimate_tokens(messages: List[Dict], model_name: Optional[str] = None) -> int:
    """
    Count tokens in messages using real tokenizer (with fallback)

    Args:
        messages: List of message dicts with 'content' key (str or list)
        model_name: Optional model name for accurate tokenization

    Returns:
        int: Token count (exact with tokenizer, estimated with fallback)
    """
    # Combine all message content (handle both str and multimodal list format)
    text_parts = []
    for m in messages:
        content = m['content']
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            # Multimodal content: extract text parts only (images don't count as text tokens)
            for part in content:
                if part.get("type") == "text":
                    text_parts.append(part.get("text", ""))

    total_text = "\n".join(text_parts)
    total_chars = len(total_text)

    # Try real tokenizer first (if model_name provided)
    if model_name:
        token_count = count_tokens_with_tokenizer(total_text, model_name)
        if token_count is not None:
            return token_count

    # Fallback: Conservative estimation (2.5 chars/token)
    # This overestimates tokens by ~20% to prevent context overflow
    return int(total_chars / 2.5)


def estimate_tokens_from_history(history: List[tuple]) -> int:
    """
    Estimate token count from chat history (tuple format)

    Args:
        history: List of (user_msg, ai_msg) tuples

    Returns:
        int: Estimated token count (rule of thumb: 1 token ≈ 3.5 chars for German/mixed text)
    """
    total_size = sum(len(user_msg) + len(ai_msg) for user_msg, ai_msg in history)
    # 3.5 chars per token (better for German texts than 4)
    return int(total_size / 3.5)


# Global cache for VRAM limits (prevents recalculation during history compression)
# Separate limits for AIfred and Sokrates since they use different models
_last_vram_limit_cache = {
    "limit": 0,           # Legacy/default (for compression, uses min of both)
    "aifred_limit": 0,    # AIfred's model-specific limit
    "sokrates_limit": 0   # Sokrates' model-specific limit
}

# Reserve tiers for LLM output (stepwise reduction before content truncation)
OUTPUT_RESERVE_PREFERRED = 32768  # 32K - Ideal for detailed answers (4x increased for 108K+ context)
OUTPUT_RESERVE_REDUCED = 6144     # 6K - Acceptable when VRAM is tight
OUTPUT_RESERVE_MINIMUM = 4096     # 4K - Minimum, below this content is truncated

# For backward compatibility (used in calculate_dynamic_num_ctx)
OUTPUT_RESERVE_TOKENS = OUTPUT_RESERVE_PREFERRED


def calculate_adaptive_reserve(
    available_context: int,
    base_input: int,
    max_rag_target: int
) -> tuple[int, int]:
    """
    Calculate adaptive reserve and RAG budget.

    Priority: Maximize reserve (32K), then reduce stepwise if RAG too tight.

    Steps:
    1. Try with 32K reserve → if RAG >= max_rag_target: perfect
    2. If 32K RAG tight but > min threshold: use 32K with reduced RAG
    3. If RAG < min threshold: Reduce reserve to 6K
    4. If 6K RAG tight: use 6K with reduced RAG
    5. If RAG < min threshold: Reduce to 4K (minimum)
    6. Only THEN: Truncate RAG content to available budget

    Args:
        available_context: Max available context (VRAM/model limited)
        base_input: Estimated input without RAG (system prompt + history + user)
        max_rag_target: Target size for RAG context (e.g., MAX_RAG_CONTEXT_TOKENS = 20K)

    Returns:
        tuple[int, int]: (actual_reserve, max_rag_tokens)
    """
    from .logging_utils import log_message
    from .formatting import format_number

    # Minimum RAG before reserve is reduced (80% of target)
    min_rag_threshold = int(max_rag_target * 0.8)  # e.g., 16K with 20K target

    # Step 1: Try with full reserve (32K)
    rag_budget_32k = available_context - base_input - OUTPUT_RESERVE_PREFERRED
    if rag_budget_32k >= max_rag_target:
        return OUTPUT_RESERVE_PREFERRED, max_rag_target
    if rag_budget_32k >= min_rag_threshold:
        # RAG slightly tight but acceptable - keep 32K reserve
        log_message(f"ℹ️ RAG slightly reduced: {format_number(max_rag_target)} → {format_number(rag_budget_32k)} tok (Reserve: 32K)")
        return OUTPUT_RESERVE_PREFERRED, rag_budget_32k

    # Step 2: Reduce to 6K reserve (VRAM tight)
    rag_budget_6k = available_context - base_input - OUTPUT_RESERVE_REDUCED
    if rag_budget_6k >= max_rag_target:
        log_message(f"⚠️ Reserve reduced: 32K → 6K (RAG budget: {format_number(rag_budget_6k)} tok)")
        return OUTPUT_RESERVE_REDUCED, max_rag_target
    if rag_budget_6k >= min_rag_threshold:
        # RAG slightly tight but acceptable - keep 6K reserve
        log_message(f"⚠️ Reserve reduced: 32K → 6K, RAG: {format_number(rag_budget_6k)} tok")
        return OUTPUT_RESERVE_REDUCED, rag_budget_6k

    # Step 3: Reduce to 4K reserve (minimum)
    rag_budget_4k = available_context - base_input - OUTPUT_RESERVE_MINIMUM
    if rag_budget_4k >= max_rag_target:
        log_message(f"⚠️ Reserve reduced: 32K → 4K (RAG budget: {format_number(rag_budget_4k)} tok)")
        return OUTPUT_RESERVE_MINIMUM, max_rag_target

    # Step 4: Reserve at minimum, RAG truncated
    if rag_budget_4k > 0:
        log_message(f"⚠️ RAG content truncated: {format_number(max_rag_target)} → {format_number(rag_budget_4k)} tok (reserve: 4K)")
        return OUTPUT_RESERVE_MINIMUM, max(4096, rag_budget_4k)  # At least 4K RAG

    # Extreme case: No space for RAG (should never happen)
    log_message(f"❌ Critical: No space for RAG content! (available: {format_number(available_context)}, base: {format_number(base_input)})")
    return OUTPUT_RESERVE_MINIMUM, 4096  # Fallback: Minimum RAG


async def get_max_available_context(
    llm_client,
    model_name: str,
    enable_vram_limit: bool = True
) -> tuple[int, int]:
    """
    Calculate max available context BEFORE context building.

    This function determines the practical limit BEFORE the RAG context is built,
    so build_context() knows how much space is available.

    Args:
        llm_client: LLMClient instance
        model_name: Model name
        enable_vram_limit: Whether VRAM-based limiting is applied

    Returns:
        tuple[int, int]: (max_practical_ctx, model_limit)
    """
    # Query model limit from backend
    model_limit, _ = await llm_client.get_model_context_limit(model_name)

    if enable_vram_limit:
        backend = llm_client._get_backend()
        max_practical_ctx, _ = await backend.calculate_practical_context(model_name)
    else:
        max_practical_ctx = model_limit

    return min(max_practical_ctx, model_limit), model_limit


async def calculate_dynamic_num_ctx(
    llm_client,
    model_name: str,
    messages: List[Dict],
    llm_options: Optional[Dict] = None,
    enable_vram_limit: bool = True,
    state = None  # Optional: AIState instance for storing VRAM limit
) -> tuple[int, list[str]]:
    """
    Calculate optimal num_ctx based on message size, model limit AND VRAM.

    This function is CENTRAL for all context calculations!
    It queries the model limit directly (~30ms) and calculates optimal num_ctx.

    The calculation considers:
    1. Message size × 2 (50/50 rule: 50% input, 50% output)
    2. Model maximum (via backend query)
    3. VRAM-based practical limit (NEW! prevents CPU offload)
    4. User override (if set in llm_options)

    Args:
        llm_client: LLMClient instance (any backend type)
        model_name: Model name (e.g., "qwen3:8b", "phi3:mini")
        messages: List of message dicts with 'content' key
        llm_options: Dict with optional 'num_ctx' override
        enable_vram_limit: Whether VRAM-based limiting is applied (default: True)

    Returns:
        tuple[int, list[str]]: (num_ctx, debug_messages)
            - num_ctx: Optimal num_ctx (rounded to standard sizes, clipped to practical limit)
            - debug_messages: VRAM debug messages for UI console (to be yielded by caller)

    Raises:
        RuntimeError: If model info cannot be queried
    """
    # Check for manual override
    user_num_ctx = llm_options.get('num_ctx') if llm_options else None
    if user_num_ctx:
        log_message(f"🎯 Context Window: {user_num_ctx} Tokens (manually set)")
        return user_num_ctx, []  # No VRAM messages for manual override

    # Calculate tokens from message size
    estimated_tokens = estimate_tokens(messages)  # 1 token ≈ 3.5 chars

    # Constant 8K reserve for LLM output
    # For research (summarization), output is SHORTER than input, so 8K is sufficient
    # (~6000 words / 4-5 A4 pages for detailed answers)
    reserve = OUTPUT_RESERVE_TOKENS  # 8192

    needed_tokens = estimated_tokens + reserve

    # Query model limit from backend (~40ms, does NOT load model!)
    model_limit, _ = await llm_client.get_model_context_limit(model_name)

    # NEW: Backend-specific practical limit calculation
    # - Ollama: Dynamic VRAM calculation (based on current free VRAM)
    # - vLLM: Cached startup value (FIXED, cannot be changed at runtime)
    # - TabbyAPI: Cached startup value or API query
    # - KoboldCPP: Cached startup value (FIXED, num_ctx not changeable at runtime)
    vram_debug_msgs = []
    backend = llm_client._get_backend()
    backend_type = type(backend).__name__

    if enable_vram_limit:
        # Use backend-specific context calculation
        max_practical_ctx, vram_debug_msgs = await backend.calculate_practical_context(model_name)
    else:
        # VRAM limit disabled - use full model limit
        max_practical_ctx = model_limit
        log_message(f"⚠️ VRAM limit disabled - using full model limit {model_limit:,} (risk: CPU offload)")

    # Backend-specific context calculation
    calculated_ctx = needed_tokens

    if backend_type == "KoboldCPPBackend":
        # KoboldCPP: num_ctx is FIXED at server start, cannot be changed at runtime
        # We MUST always use the full context (max_practical_ctx = startup value)
        final_num_ctx = max_practical_ctx
        log_message(
            f"🎯 KoboldCPP: Using fixed startup context: {format_number(final_num_ctx)} tok "
            f"(~{format_number(estimated_tokens)} needed, {format_number(calculated_ctx)} calculated)"
        )
    else:
        # Ollama/vLLM/TabbyAPI: Dynamic num_ctx calculation possible
        # gpu_utils.calculate_vram_based_context() returns:
        # - Calibrated: the measured max_context_gpu_only value
        # - Uncalibrated: dynamically calculated VRAM-based value
        # In both cases: Clip to model limit
        final_num_ctx = min(max_practical_ctx, model_limit)

    # Store VRAM limit in global cache for history compression
    # (prevents history from recalculating the limit)
    # This is called for AIfred (main LLM), so store in aifred_limit too
    _last_vram_limit_cache["limit"] = min(max_practical_ctx, model_limit)
    _last_vram_limit_cache["aifred_limit"] = min(max_practical_ctx, model_limit)

    # Optional: Also store in state if provided
    if state is not None:
        state.last_vram_limit = min(max_practical_ctx, model_limit)

    # Log Context Window Info (only for Ollama/vLLM/TabbyAPI)
    if backend_type != "KoboldCPPBackend":
        # Calculate available output space
        available_output = final_num_ctx - estimated_tokens
        log_message(
            f"🎯 Context Window: {format_number(final_num_ctx)} tok "
            f"(Input: ~{format_number(estimated_tokens)}, Output space: ~{format_number(available_output)}, "
            f"VRAM limit: {format_number(max_practical_ctx)}, Model max: {format_number(model_limit)})"
        )

    return final_num_ctx, vram_debug_msgs


async def summarize_history_if_needed(
    history: List[tuple],
    llm_client,
    model_name: str,
    context_limit: int,
    max_summaries: int = None
) -> AsyncIterator[Dict]:
    """
    Compress chat history when needed (context overflow prevention)

    Args:
        history: Chat history as list of (user_msg, ai_msg) tuples
        llm_client: LLM Client for summarization
        model_name: Main LLM model
        context_limit: Context window limit of the model
        max_summaries: Maximum number of summaries before FIFO (default: from config)

    Yields:
        Dict: Progress and debug messages

    Returns:
        None - Function does not modify history in-place, state update via yield
    """
    # Removed: Unnecessary debug line about function call details

    # Use config values as defaults
    if max_summaries is None:
        max_summaries = HISTORY_MAX_SUMMARIES

    # Token estimation & utilization check (ALWAYS first, for debug message)
    estimated_tokens = estimate_tokens_from_history(history)
    utilization = (estimated_tokens / context_limit) * 100
    threshold = int(context_limit * HISTORY_COMPRESSION_THRESHOLD)

    # Safety-Check: Always keep at least 1 message after compression!
    # CRITICAL: Prevents all messages from being compressed and chat becoming empty
    if len(history) <= HISTORY_MESSAGES_TO_COMPRESS:
        yield {"type": "debug", "message": f"📊 History: {format_number(estimated_tokens)} / {format_number(context_limit)} tok ({int(utilization)}%)"}
        log_message(f"⚠️ Compression aborted: {len(history)} messages would ALL be compressed → chat empty!")
        return

    if estimated_tokens < threshold:
        yield {"type": "debug", "message": f"📊 History: {format_number(estimated_tokens)} / {format_number(context_limit)} tok ({int(utilization)}%)"}
        return

    log_message(f"⚠️ History too long: {int(utilization)}% utilization ({format_number(estimated_tokens)} tok) > {format_number(threshold)} threshold → starting compression")

    # Progress indicator: Compressing context
    yield {"type": "progress", "phase": "compress"}
    yield {"type": "debug", "message": f"🗜️ History compression starting: {int(utilization)}% utilization ({format_number(estimated_tokens)} / {format_number(context_limit)} tok)"}

    # 4. Count existing summaries (check both German and English markers for backward compatibility)
    summary_count = sum(1 for user_msg, ai_msg in history if user_msg == "" and (ai_msg.startswith("[📊 Compressed") or ai_msg.startswith("[📊 Komprimiert")))

    # 5. FIFO when max_summaries already reached
    if summary_count >= max_summaries:
        log_message(f"⚠️ Max {max_summaries} summaries reached → deleting oldest summary (FIFO)")
        # Find and remove oldest summary
        for i, (user_msg, ai_msg) in enumerate(history):
            if user_msg == "" and (ai_msg.startswith("[📊 Compressed") or ai_msg.startswith("[📊 Komprimiert")):
                history.pop(i)
                yield {"type": "debug", "message": "🗑️ Oldest summary removed (FIFO)"}
                break

    # 6. Extract oldest messages to summarize (configurable count)
    messages_to_summarize = history[:HISTORY_MESSAGES_TO_COMPRESS]
    remaining_messages = history[HISTORY_MESSAGES_TO_COMPRESS:]

    log_message("📝 Preparing compression:")
    log_message(f"   └─ To compress: {len(messages_to_summarize)} messages")
    log_message(f"   └─ Model: {model_name}")
    log_message(f"   └─ Temperature: {HISTORY_SUMMARY_TEMPERATURE}")
    log_message(f"   └─ Context limit: {HISTORY_SUMMARY_CONTEXT_LIMIT}")

    # 7. Format conversation for LLM (without <think> blocks!)
    conversation_text = ""
    for i, (user_msg, ai_msg) in enumerate(messages_to_summarize, 1):
        # Remove <think> blocks from both messages
        clean_user_msg = strip_thinking_blocks(user_msg) if user_msg else ""
        clean_ai_msg = strip_thinking_blocks(ai_msg) if ai_msg else ""

        log_message(f"   └─ Message {i}: User={len(user_msg)}→{len(clean_user_msg)} chars, AI={len(ai_msg)}→{len(clean_ai_msg)} chars")
        conversation_text += f"User: {clean_user_msg}\nAI: {clean_ai_msg}\n\n"

    # Language detection for conversation (use first user text as reference)
    from .prompt_loader import detect_language
    first_user_msg = messages_to_summarize[0][0] if messages_to_summarize else ""
    detected_language = detect_language(first_user_msg) if first_user_msg else "de"

    # 8. Load Summarization Prompt
    summary_prompt = load_prompt(
        'history_summarization',
        lang=detected_language,
        conversation=conversation_text.strip(),
        max_tokens=HISTORY_SUMMARY_TARGET_TOKENS,
        max_words=HISTORY_SUMMARY_TARGET_WORDS
    )

    # 9. LLM Summarization (Main LLM for better quality)
    import datetime
    start_timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Milliseconds
    log_message(f"🗜️ [START {start_timestamp}] Compressing {HISTORY_MESSAGES_TO_COMPRESS} messages with {model_name}...")
    summary_start = time.time()

    # Token count before compression
    tokens_before = estimate_tokens_from_history(messages_to_summarize)

    summary_text = ""
    tokens_generated = 0

    try:
        # MUCH SIMPLER: Use chat() instead of chat_stream() - we don't need streaming!
        log_message("   Calling LLM (non-streaming)...")

        # Import backend types
        from ..backends.base import LLMMessage, LLMOptions

        # Create proper message and options objects
        messages = [LLMMessage(role="system", content=summary_prompt)]
        options = LLMOptions(
            temperature=HISTORY_SUMMARY_TEMPERATURE,
            num_ctx=HISTORY_SUMMARY_CONTEXT_LIMIT,
            enable_thinking=False  # Fast summarization, no reasoning needed
        )

        response = await llm_client.chat(
            model=model_name,
            messages=messages,
            options=options
        )

        # Evaluate response
        summary_time = time.time() - summary_start
        end_timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # Log raw response for debugging
        log_message(f"   Raw response type: {type(response)}")
        log_message(f"   Raw response: {response}")

        # Extract summary text (response is an LLMResponse object!)
        summary_text = response.text if response else ""

        # Extract metrics from LLMResponse
        if response:
            tokens_generated = response.tokens_generated
            tokens_per_second = response.tokens_per_second
        else:
            # Fallback: Estimate tokens based on text length
            tokens_generated = len(summary_text) // 4  # Rough estimate
            tokens_per_second = tokens_generated / summary_time if summary_time > 0 else 0

        # Detailed debug output
        log_message(f"✅ [END {end_timestamp}] Summary generated:")
        log_message(f"   └─ Chars generated: {len(summary_text)}")
        log_message(f"   └─ Tokens estimated: {format_number(tokens_generated)}")
        log_message(f"   └─ Time: {format_number(summary_time, 2)}s")
        log_message(f"   └─ Speed: {format_number(tokens_per_second, 1)} tok/s")
        if tokens_before > 0 and tokens_generated > 0:
            log_message(f"   └─ Compression: {format_number(tokens_before)} → {format_number(tokens_generated)} tok ({format_number(tokens_before/tokens_generated, 1)}:1 ratio)")
        console_separator()

    except asyncio.TimeoutError:
        log_message("⚠️ Async timeout during summary generation")
        yield {"type": "debug", "message": "⚠️ Summary generation timeout"}
        summary_text = ""  # Ensure empty on timeout
    except Exception as e:
        log_message(f"❌ Error during summary generation: {e}")
        yield {"type": "debug", "message": f"❌ Summary error: {e}"}
        summary_text = ""  # Ensure empty on error

    # 10. Only if summary was successfully generated
    if summary_text and len(summary_text.strip()) > 10:  # At least 10 characters
        # Create summary entry (collapsible format)
        summary_entry = (
            "",  # Empty user part
            f"[📊 Compressed: {len(messages_to_summarize)} Messages]\n{summary_text.strip()}"
        )
        # Build new history: [Summary] + [Remaining Messages]
        new_history = [summary_entry] + remaining_messages
    else:
        # On error: Keep history unchanged
        log_message("⚠️ Summary too short or empty - history remains unchanged")
        yield {"type": "debug", "message": "⚠️ Compression failed - history unchanged"}
        return  # Exit here without changes

    # Calculate new token count after compression
    new_tokens = estimate_tokens_from_history(new_history)
    compression_ratio = estimated_tokens / new_tokens if new_tokens > 0 else 0

    log_message("✅ History successfully compressed:")
    log_message(f"   └─ Messages: {len(history)} → {len(new_history)} ({len(remaining_messages)} visible)")
    log_message(f"   └─ Tokens: {format_number(estimated_tokens)} → {format_number(new_tokens)} ({format_number(compression_ratio, 1)}:1 ratio)")
    log_message(f"   └─ Space saved: {format_number(estimated_tokens - new_tokens)} tok")

    # Calculate new utilization after compression
    new_utilization = (new_tokens / context_limit) * 100

    # Count summaries in new history (check both German and English markers for backward compatibility)
    summaries_count = sum(1 for user_msg, ai_msg in new_history if user_msg == "" and (ai_msg.startswith("[📊 Compressed") or ai_msg.startswith("[📊 Komprimiert")))

    # 12. Yield update to state
    yield {"type": "history_update", "data": new_history}
    yield {"type": "debug", "message": f"📦 History compressed: {int(utilization)}% → {int(new_utilization)}% ({format_number(estimated_tokens)} → {format_number(new_tokens)} tok, {len(messages_to_summarize)}→1 messages, {summaries_count} summaries total)"}


async def prepare_main_llm(
    backend,
    llm_client,
    model_name: str,
    messages: list,
    num_ctx_mode: str = "auto",
    num_ctx_manual: int = 4096,
    backend_type: str = "ollama",
    enable_thinking: bool = False
):
    """
    Central function for Main-LLM preparation (AsyncGenerator).

    Guarantees correct order for Ollama Multi-GPU:
    1. Calculate num_ctx (Ollama auto: with unload + VRAM measurement)
    2. Preload with num_ctx (Ollama loads model + allocates KV-Cache)

    IMPORTANT: This function is ONLY for the Main-LLM!
    For Automatik-LLM, use prepare_automatik_llm() instead (small context).

    Yields debug messages immediately for UI, so user sees what's happening.

    Note: For Ollama, per-model RoPE 2x toggle is read automatically from VRAM cache.

    Args:
        backend: LLM Backend instance
        llm_client: LLMClient for context limit query
        model_name: Model name (pure ID without suffix)
        messages: Message list for token estimation
        num_ctx_mode: "auto" or "manual"
        num_ctx_manual: Manual value (only when mode="manual")
        backend_type: "ollama", "vllm", etc.
        enable_thinking: Whether to enable thinking mode during preload (Ollama-specific)

    Yields:
        dict: {"type": "debug", "message": "..."} for UI console
        dict: {"type": "result", "data": (final_num_ctx, preload_success, preload_time)} as last
    """
    from .formatting import format_number

    try:
        # 1. Calculate num_ctx (BEFORE preload!)
        log_message(f"🔄 prepare_main_llm: Start for {model_name} (mode={num_ctx_mode})")

        if num_ctx_mode == "manual":
            final_num_ctx = num_ctx_manual
            yield {"type": "debug", "message": f"🔧 Manual num_ctx: {num_ctx_manual:,}"}
            log_message(f"🔧 Manual num_ctx: {num_ctx_manual:,} (VRAM calculation skipped)")
        elif backend_type == "ollama":
            # Ollama auto: calculate_practical_context() does:
            # - unload_all_models() internally
            # - Wait 2s for VRAM release
            # - VRAM-based calculation (reads use_extended from cache per model)
            log_message(f"🔄 prepare_main_llm: Starting VRAM calculation")

            final_num_ctx, vram_msgs = await backend.calculate_practical_context(model_name)
            for msg in vram_msgs:
                yield {"type": "debug", "message": msg}
            log_message(f"✅ prepare_main_llm: VRAM calculation done → num_ctx={final_num_ctx:,}")

            # Set cache for history compression (this is for AIfred/main LLM)
            _last_vram_limit_cache["limit"] = final_num_ctx
            _last_vram_limit_cache["aifred_limit"] = final_num_ctx
        else:
            # Other backends: Standard calculation (no extended calibration support)
            final_num_ctx, vram_msgs = await calculate_dynamic_num_ctx(
                llm_client, model_name, messages, None,
                enable_vram_limit=True
            )
            for msg in vram_msgs:
                yield {"type": "debug", "message": msg}
            log_message(f"✅ prepare_main_llm: Context calculation done → num_ctx={final_num_ctx:,}")

        # 2. Preload with num_ctx (only Ollama - other backends have model at startup)
        preload_success = True
        preload_time = 0.0

        if backend_type == "ollama":
            formatted_ctx = format_number(final_num_ctx)
            yield {"type": "debug", "message": f"🚀 Main LLM ({model_name}) is being preloaded (num_ctx={formatted_ctx})..."}
            log_message(f"🔄 prepare_main_llm: Starting preload for {model_name} (num_ctx={final_num_ctx:,})...")

            # Give event loop a chance to flush the UI update before blocking preload
            import asyncio
            await asyncio.sleep(0)

            # NOTE: The actual fix is removing num_predict=1 from the preload in ollama.py
            # We can keep enable_thinking as is - the bug was num_predict=1
            preload_success, preload_time = await backend.preload_model(model_name, num_ctx=final_num_ctx, enable_thinking=enable_thinking)

            if preload_success:
                yield {"type": "debug", "message": f"✅ Main LLM preloaded ({preload_time:.1f}s)"}
                # Note: log_message() is called via add_debug() when yield is processed
            else:
                yield {"type": "debug", "message": f"⚠️ Main LLM preload failed ({preload_time:.1f}s)"}
                # Note: log_message() is called via add_debug() when yield is processed

        log_message(f"✅ prepare_main_llm: Done (num_ctx={final_num_ctx:,}, preload={preload_success})")

        # Final result as last yield
        yield {"type": "result", "data": (final_num_ctx, preload_success, preload_time)}

    except Exception as e:
        import traceback
        log_message(f"❌ prepare_main_llm EXCEPTION: {e}")
        log_message(f"   Traceback: {traceback.format_exc()}")
        # Re-raise so caller also sees the error
        raise


async def prepare_automatik_llm(
    backend,
    model_name: str,
    backend_type: str = "ollama"
):
    """
    Preload Automatik-LLM with small context window.

    CRITICAL: Models like Qwen3:4B have 262K default context!
    Without explicit num_ctx, Ollama allocates HUGE KV-Cache across all GPUs.
    This function preloads with only 4K context to minimize VRAM usage.

    Args:
        backend: LLM Backend instance
        model_name: Model name (pure ID)
        backend_type: "ollama", "vllm", etc.

    Yields:
        dict: {"type": "debug", "message": "..."} for UI console
        dict: {"type": "result", "data": (success, load_time)} as last
    """
    from .formatting import format_number
    from .config import AUTOMATIK_LLM_NUM_CTX

    try:
        # Only Ollama needs preloading - other backends have models at startup
        if backend_type != "ollama":
            yield {"type": "result", "data": (True, 0.0)}
            return

        formatted_ctx = format_number(AUTOMATIK_LLM_NUM_CTX)
        yield {"type": "debug", "message": f"🤖 Automatik-LLM ({model_name}) is being preloaded (num_ctx={formatted_ctx})..."}
        log_message(f"🔄 prepare_automatik_llm: Preloading {model_name} with num_ctx={AUTOMATIK_LLM_NUM_CTX}")

        import asyncio
        await asyncio.sleep(0)  # Flush UI update

        success, load_time = await backend.preload_model(model_name, num_ctx=AUTOMATIK_LLM_NUM_CTX)

        if success:
            yield {"type": "debug", "message": f"✅ Automatik-LLM preloaded ({load_time:.1f}s)"}
        else:
            yield {"type": "debug", "message": f"⚠️ Automatik-LLM preload failed ({load_time:.1f}s)"}

        log_message(f"✅ prepare_automatik_llm: Done (success={success}, time={load_time:.1f}s)")
        yield {"type": "result", "data": (success, load_time)}

    except Exception as e:
        import traceback
        log_message(f"❌ prepare_automatik_llm EXCEPTION: {e}")
        log_message(f"   Traceback: {traceback.format_exc()}")
        raise

