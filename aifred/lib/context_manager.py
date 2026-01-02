"""
Context Manager - Token and Context Window Management

Handles context limits and token estimation for LLMs:
- Query model context limits from backends (on-demand, no caching)
- Calculate optimal num_ctx for requests
- Token estimation for messages (using HuggingFace tokenizers)
- History compression (summarize_history_if_needed)
"""

import re
import time
import asyncio
from typing import Dict, List, Optional, AsyncIterator
from .logging_utils import log_message, console_separator
from .prompt_loader import load_prompt
from .formatting import format_number
from .config import (
    HISTORY_COMPRESSION_TRIGGER,
    HISTORY_COMPRESSION_TARGET,
    HISTORY_SUMMARY_RATIO,
    HISTORY_SUMMARY_MIN_TOKENS,
    HISTORY_SUMMARY_TOLERANCE,
    HISTORY_MAX_SUMMARIES,
    HISTORY_SUMMARY_MAX_RATIO,
    HISTORY_SUMMARY_TEMPERATURE,
    DEBUG_LOG_RAW_MESSAGES
)

# Global tokenizer cache (model_name -> tokenizer)
_tokenizer_cache = {}


def parse_model_size_from_name(model_name: str) -> float:
    """
    Extract model size (in billions of parameters) from model name.

    Supports common naming patterns:
    - "qwen3:8b" → 8.0
    - "gemma2:2b" → 2.0
    - "llama3.1:70b-instruct-q4_K_M" → 70.0
    - "phi3:3.8b" → 3.8
    - "mistral:7b" → 7.0
    - "qwen2.5-coder:32b" → 32.0

    Args:
        model_name: Model identifier (e.g., "qwen3:8b", "gemma2:2b-instruct")

    Returns:
        float: Size in billions (e.g., 8.0 for 8B), or 0.0 if not parseable
    """
    if not model_name:
        return 0.0

    # Convert to lowercase for matching
    name_lower = model_name.lower()

    # Pattern: look for number followed by 'b' (billions)
    # Matches: 8b, 70b, 3.8b, 0.5b, etc.
    pattern = r'[:\-_]?(\d+(?:\.\d+)?)\s*b(?:[^a-z]|$)'
    match = re.search(pattern, name_lower)

    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    # Fallback: check for size in the tag after colon
    if ':' in model_name:
        tag = model_name.split(':')[1].lower()
        # Try to find number followed by 'b' in tag
        simple_match = re.search(r'^(\d+(?:\.\d+)?)\s*b', tag)
        if simple_match:
            try:
                return float(simple_match.group(1))
            except ValueError:
                pass

    return 0.0


def get_largest_compression_model(
    aifred_model: str,
    sokrates_model: str,
    salomo_model: str
) -> str:
    """
    Select the largest model from AIfred, Sokrates, and Salomo for compression.

    Compression quality is critical - use the most capable model available.
    Falls back to aifred_model if sizes cannot be determined.

    Args:
        aifred_model: AIfred's model ID
        sokrates_model: Sokrates' model ID
        salomo_model: Salomo's model ID

    Returns:
        str: Model ID of the largest model (by parameter count)
    """
    candidates = [
        (aifred_model, parse_model_size_from_name(aifred_model)),
        (sokrates_model, parse_model_size_from_name(sokrates_model)),
        (salomo_model, parse_model_size_from_name(salomo_model)),
    ]

    # Filter out empty models and sort by size (descending)
    valid_candidates = [(m, s) for m, s in candidates if m and s > 0]

    if not valid_candidates:
        # Fallback: return first non-empty model
        for model, _ in candidates:
            if model:
                return model
        return aifred_model  # Ultimate fallback

    # Sort by size descending, return largest
    valid_candidates.sort(key=lambda x: x[1], reverse=True)
    largest_model, largest_size = valid_candidates[0]

    log_message(f"🗜️ Compression model: {largest_model} ({largest_size}B) - largest of AIfred/Sokrates/Salomo")

    return largest_model


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


def strip_non_llm_content(text: str) -> str:
    """
    Remove content that doesn't go to the LLM (thinking blocks, metadata).

    These are stored in history for UI/export but should not count towards
    token estimation since they are stripped before LLM calls.
    """
    if not text:
        return ""
    # <details>...</details> (Thinking blocks in UI - collapsible)
    text = re.sub(r'<details[^>]*>.*?</details>', '', text, flags=re.DOTALL)
    # <span>...</span> (Metadata spans)
    text = re.sub(r'<span[^>]*>.*?</span>', '', text, flags=re.DOTALL)
    # <think>...</think> (Raw thinking blocks)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return text.strip()


def estimate_tokens_from_history(history: List[tuple]) -> int:
    """
    Estimate token count from chat history (tuple format).

    Strips non-LLM content (thinking blocks, metadata) before estimation
    since these don't actually go to the LLM.

    Args:
        history: List of (user_msg, ai_msg) tuples

    Returns:
        int: Estimated token count (rule of thumb: 1 token ≈ 3.5 chars for German/mixed text)
    """
    total_size = 0
    for user_msg, ai_msg in history:
        total_size += len(strip_non_llm_content(user_msg))
        total_size += len(strip_non_llm_content(ai_msg))
    # 3.5 chars per token (better for German texts than 4)
    return int(total_size / 3.5)


def estimate_tokens_from_llm_history(llm_history: List[Dict[str, str]]) -> int:
    """
    Estimate token count from llm_history (dict format).

    llm_history is already cleaned - no stripping needed.

    Args:
        llm_history: List of {"role": ..., "content": ...} dicts

    Returns:
        int: Estimated token count
    """
    if not llm_history:
        return 0
    total_size = sum(len(msg.get("content", "")) for msg in llm_history)
    # 3.5 chars per token (better for German texts than 4)
    return int(total_size / 3.5)


def get_summary_target_tokens(tokens_to_compress: int) -> int:
    """
    Calculate dynamic summary size based on content being compressed.

    Summary = 25% of content being compressed (4:1 compression ratio).
    Minimum 500 tokens for meaningful summaries.

    Args:
        tokens_to_compress: Estimated tokens in content to be compressed

    Returns:
        int: Target token count for summary
    """
    target = int(tokens_to_compress * HISTORY_SUMMARY_RATIO)
    return max(HISTORY_SUMMARY_MIN_TOKENS, target)


def truncate_to_tokens(text: str, target_tokens: int) -> str:
    """
    Truncate text to approximately target token count.

    Uses char-based estimation (3.5 chars/token for German).

    Args:
        text: Text to truncate
        target_tokens: Target token count

    Returns:
        str: Truncated text (with ... indicator if truncated)
    """
    target_chars = int(target_tokens * 3.5)
    if len(text) <= target_chars:
        return text
    # Find last sentence boundary before limit
    truncated = text[:target_chars]
    last_period = truncated.rfind('. ')
    if last_period > target_chars * 0.7:  # At least 70% of content
        return truncated[:last_period + 1] + " [...]"
    return truncated + " [...]"


def calculate_max_summaries(context_limit: int, avg_summary_tokens: int = 500) -> int:
    """
    Calculate how many summaries fit based on context limit.

    Rule: Summaries should use max HISTORY_SUMMARY_MAX_RATIO (20%) of context.
    This ensures small models (4K) don't get overwhelmed by summaries.

    Examples:
        4K Context:  4096 * 0.2 / 500 = 1-2 Summaries
        8K Context:  8192 * 0.2 / 500 = 3 Summaries
        32K Context: 32768 * 0.2 / 500 = 13 → capped at HISTORY_MAX_SUMMARIES (10)

    Args:
        context_limit: The model's context window size in tokens
        avg_summary_tokens: Average expected tokens per summary (default: 500)

    Returns:
        int: Maximum number of summaries allowed (at least 1, at most HISTORY_MAX_SUMMARIES)
    """
    max_summary_budget = int(context_limit * HISTORY_SUMMARY_MAX_RATIO)
    max_summaries = max(1, max_summary_budget // avg_summary_tokens)
    return min(max_summaries, HISTORY_MAX_SUMMARIES)


def is_summary_entry(user_msg: str, ai_msg: str) -> bool:
    """
    Check if a chat history entry is a summary.

    Supports both old format: [📊 Compressed: N Messages] / [📊 Komprimiert: N Messages]
    And new format: [📊 Summary #N|X Messages|Timestamp]

    Args:
        user_msg: User message part (should be empty for summaries)
        ai_msg: AI message part (contains summary marker)

    Returns:
        bool: True if this is a summary entry
    """
    if user_msg != "":
        return False
    return (
        ai_msg.startswith("[📊 Compressed") or
        ai_msg.startswith("[📊 Komprimiert") or
        ai_msg.startswith("[📊 Summary #")
    )


def count_summaries(history: List[tuple]) -> int:
    """Count the number of summary entries in chat history."""
    return sum(1 for user_msg, ai_msg in history if is_summary_entry(user_msg, ai_msg))


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
    max_summaries: int = None,
    llm_history: List[Dict[str, str]] = None,
    system_prompt_tokens: int = 0,
    detected_language: str = "de"
) -> AsyncIterator[Dict]:
    """
    Compress chat history when context utilization reaches trigger threshold.

    DUAL-UPDATE (v2.13.0+):
    - chat_history (UI): Original-Messages bleiben, Summary wird NACH komprimierten Messages eingefügt
    - llm_history (LLM): Alte Messages werden durch Summary ersetzt (ready-to-use für LLM)

    NEW ALGORITHM (dynamic, percentage-based):
    1. Trigger: >= 70% context utilization (HISTORY_COMPRESSION_TRIGGER)
    2. Target: Compress down to 30% (HISTORY_COMPRESSION_TARGET) - leaves room for ~2 roundtrips
    3. Summary size: 25% of compressed content (4:1 ratio, min 500 tokens)
    4. Tolerance: Allow up to 50% over target, then truncate

    No more fixed message count - compresses as much as needed to reach target!

    IMPORTANT (v2.14.0+): system_prompt_tokens is INCLUDED in utilization calculation!
    This prevents context overflow when system prompts are large (e.g., 2000+ tokens).

    Args:
        history: Chat history as list of (user_msg, ai_msg) tuples (UI - vollständig)
        llm_client: LLM Client for summarization
        model_name: Main LLM model
        context_limit: Context window limit of the model
        max_summaries: Maximum number of summaries before FIFO (default: from config)
        llm_history: LLM history as list of {"role": ..., "content": ...} dicts (LLM - komprimiert)
        system_prompt_tokens: Estimated tokens for system prompt(s) - included in utilization!

    Yields:
        Dict: Progress, debug messages, and history updates
        - {"type": "history_update", "chat_history": [...], "llm_history": [...]}

    Returns:
        None - Function does not modify history in-place, state update via yield
    """
    # Calculate dynamic max_summaries based on context limit
    # Small models (4K) get fewer summaries, large models (32K+) get more
    if max_summaries is None:
        max_summaries = calculate_max_summaries(context_limit)

    # Calculate thresholds from config
    trigger_threshold = int(context_limit * HISTORY_COMPRESSION_TRIGGER)  # 70%
    target_threshold = int(context_limit * HISTORY_COMPRESSION_TARGET)    # 30%

    # Token estimation - use llm_history if available (already cleaned, accurate)
    if llm_history:
        history_tokens = estimate_tokens_from_llm_history(llm_history)
    else:
        history_tokens = estimate_tokens_from_history(history)

    # CRITICAL (v2.14.0+): Include system prompt tokens in total!
    # This prevents overflow when system prompts are large (2000+ tokens).
    # Total = System Prompt + History (what actually goes to the LLM)
    total_tokens = system_prompt_tokens + history_tokens
    utilization = (total_tokens / context_limit) * 100

    # Debug: Show breakdown (System vs History)
    if system_prompt_tokens > 0:
        yield {"type": "debug", "message": f"📊 Context: System {format_number(system_prompt_tokens)} + History {format_number(history_tokens)} = {format_number(total_tokens)} / {format_number(context_limit)} tok ({int(utilization)}%)"}
    else:
        yield {"type": "debug", "message": f"📊 History: {format_number(history_tokens)} / {format_number(context_limit)} tok ({int(utilization)}%)"}

    # Check trigger: Only compress when >= 70% utilized
    if total_tokens < trigger_threshold:
        return

    # Safety: Need at least 2 messages (1 to compress, 1 to keep)
    if len(history) < 2:
        yield {"type": "debug", "message": f"📊 History: {format_number(total_tokens)} / {format_number(context_limit)} tok ({int(utilization)}%) - too few messages"}
        log_message(f"⚠️ Compression aborted: Only {len(history)} message(s) in history")
        return

    log_message(f"⚠️ History compression triggered: {int(utilization)}% utilization ({format_number(total_tokens)} tok) >= {int(HISTORY_COMPRESSION_TRIGGER*100)}% threshold")
    if system_prompt_tokens > 0:
        log_message(f"   └─ Breakdown: System {format_number(system_prompt_tokens)} + History {format_number(history_tokens)}")
    log_message(f"   └─ Target: {int(HISTORY_COMPRESSION_TARGET*100)}% = {format_number(target_threshold)} tok")

    # Progress indicator
    yield {"type": "progress", "phase": "compress"}
    yield {"type": "debug", "message": f"🗜️ Compressing: {int(utilization)}% → {int(HISTORY_COMPRESSION_TARGET*100)}% target ({format_number(total_tokens)} → {format_number(target_threshold)} tok)"}

    # Count existing summaries using helper function (supports old and new formats)
    summary_count = count_summaries(history)

    # ============================================================
    # FIFO: Only apply to llm_history, NOT chat_history! (v2.14.2+)
    # ============================================================
    # - chat_history (UI): Keep ALL summaries for user to see history
    # - llm_history (LLM): Apply FIFO, only newest summary stays (context limit)
    #
    # Count summaries in llm_history for FIFO decision
    llm_summary_count = 0
    if llm_history is not None:
        llm_summary_count = sum(
            1 for msg in llm_history
            if msg.get("role") == "system" and msg.get("content", "").startswith("[Summary]")
        )

    # FIFO only on llm_history - remove oldest summaries until below max
    while llm_summary_count >= max_summaries and llm_history is not None:
        log_message(f"⚠️ Max {max_summaries} summaries in LLM-History (have {llm_summary_count}) → removing oldest (FIFO)")
        for j, msg in enumerate(llm_history):
            if msg.get("role") == "system" and msg.get("content", "").startswith("[Summary]"):
                llm_history.pop(j)
                llm_summary_count -= 1
                yield {"type": "debug", "message": f"🗑️ Oldest LLM-Summary removed (FIFO, max={max_summaries})"}
                # NOTE: chat_history keeps ALL summaries - no removal there!
                break
        else:
            # No summary found to remove - shouldn't happen but safety
            break

    # Log how many summaries UI keeps (informational)
    if summary_count > 0:
        log_message(f"📌 Chat-History keeps {summary_count} summaries (UI display)")

    # DYNAMIC: Collect messages from front until remaining fits in target
    # IMPORTANT: Skip existing summaries - they should be preserved!
    #
    # CRITICAL FIX (v2.14.3+): Use llm_history for token calculation to match trigger!
    # The trigger uses estimate_tokens_from_llm_history(llm_history), so the loop must too.
    # Otherwise: Trigger fires at 70% but loop calculates different tokens and compresses 0 messages.
    messages_to_compress = []
    preserved_summaries = []  # Summaries at the front that we keep
    remaining_messages = history[:]
    current_tokens = history_tokens  # Use history tokens for compression calculation (system prompt is constant)

    # First, extract all summaries from the front and preserve them
    while remaining_messages:
        user_msg, ai_msg = remaining_messages[0]
        if is_summary_entry(user_msg, ai_msg):
            preserved_summaries.append(remaining_messages.pop(0))
        else:
            break  # Stop at first non-summary message

    # Build parallel llm_history lists for accurate token calculation
    # We need to track which llm_history entries correspond to which chat_history entries
    if llm_history is not None:
        # Create working copies of llm_history for token calculation
        # Skip summary entries (role=system, content starts with [Summary])
        llm_preserved_summaries = []
        llm_remaining = []
        for msg in llm_history:
            if msg.get("role") == "system" and msg.get("content", "").startswith("[Summary]"):
                llm_preserved_summaries.append(msg)
            else:
                llm_remaining.append(msg)

        llm_to_compress = []
        current_tokens = estimate_tokens_from_llm_history(llm_preserved_summaries + llm_remaining)

        # Compress until we're below target, keeping at least 1 message
        while current_tokens > target_threshold and len(remaining_messages) > 1 and len(llm_remaining) > 1:
            messages_to_compress.append(remaining_messages.pop(0))
            llm_to_compress.append(llm_remaining.pop(0))
            current_tokens = estimate_tokens_from_llm_history(llm_preserved_summaries + llm_remaining)
    else:
        # Fallback: No llm_history, use old method (less accurate but functional)
        current_tokens = estimate_tokens_from_history(preserved_summaries + remaining_messages)
        while current_tokens > target_threshold and len(remaining_messages) > 1:
            messages_to_compress.append(remaining_messages.pop(0))
            current_tokens = estimate_tokens_from_history(preserved_summaries + remaining_messages)

    # Safety: Must keep at least 1 message
    if len(remaining_messages) == 0 and messages_to_compress:
        remaining_messages = [messages_to_compress.pop()]

    # Log preserved summaries
    if preserved_summaries:
        log_message(f"📌 Preserving {len(preserved_summaries)} existing summary/summaries")

    # Calculate tokens being compressed
    tokens_to_compress = estimate_tokens_from_history(messages_to_compress)
    summary_target_tokens = get_summary_target_tokens(tokens_to_compress)
    summary_target_words = int(summary_target_tokens * 0.75)  # ~0.75 words per token for German

    log_message("📝 Compression plan:")
    log_message(f"   └─ Messages to compress: {len(messages_to_compress)}")
    log_message(f"   └─ Tokens to compress: {format_number(tokens_to_compress)}")
    log_message(f"   └─ Summary target: {format_number(summary_target_tokens)} tok (~{format_number(summary_target_words)} words)")
    log_message(f"   └─ Remaining after: {len(remaining_messages)} messages, ~{format_number(current_tokens)} tok")

    # Format conversation for LLM (without thinking blocks)
    conversation_text = ""
    for i, (user_msg, ai_msg) in enumerate(messages_to_compress, 1):
        clean_user_msg = strip_thinking_blocks(user_msg) if user_msg else ""
        clean_ai_msg = strip_thinking_blocks(ai_msg) if ai_msg else ""
        log_message(f"   └─ Msg {i}: User={len(user_msg)}→{len(clean_user_msg)}, AI={len(ai_msg)}→{len(clean_ai_msg)} chars")
        conversation_text += f"User: {clean_user_msg}\nAI: {clean_ai_msg}\n\n"

    # Use detected_language from Intent Detection (passed from state.py)

    # Load summarization prompt with dynamic target
    summary_prompt = load_prompt(
        'history_summarization',
        lang=detected_language,
        conversation=conversation_text.strip(),
        max_tokens=summary_target_tokens,
        max_words=summary_target_words
    )

    # LLM Summarization
    import datetime
    start_timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

    # Get num_ctx from VRAM cache (calibrated value for compression model)
    # IMPORTANT: Always use VRAM cache value, NOT manual settings!
    # Manual num_ctx is for testing agents, not for compression.
    from .model_vram_cache import get_ollama_calibration, get_rope_factor_for_model
    rope_factor = get_rope_factor_for_model(model_name)
    compression_num_ctx = get_ollama_calibration(model_name, rope_factor)
    if not compression_num_ctx:
        # Fallback: use context_limit (min of all agents) if not calibrated
        compression_num_ctx = context_limit
        log_message(f"⚠️ Compression model {model_name} not calibrated, using context_limit={context_limit}")

    log_message(f"🗜️ [START {start_timestamp}] Compressing {len(messages_to_compress)} messages with {model_name}...")
    log_message(f"   └─ Compression LLM: {model_name} (num_ctx={format_number(compression_num_ctx)}, from VRAM cache)")
    yield {"type": "debug", "message": f"🗜️ Compression LLM: {model_name} (num_ctx={format_number(compression_num_ctx)})"}
    summary_start = time.time()

    summary_text = ""
    tokens_generated = 0

    try:
        log_message("   Calling LLM (non-streaming)...")
        from ..backends.base import LLMMessage, LLMOptions

        messages = [LLMMessage(role="system", content=summary_prompt)]
        options = LLMOptions(
            temperature=HISTORY_SUMMARY_TEMPERATURE,
            num_ctx=compression_num_ctx,
            enable_thinking=False
        )

        # DEBUG: Log RAW messages sent to Compression LLM (controlled by DEBUG_LOG_RAW_MESSAGES)
        if DEBUG_LOG_RAW_MESSAGES:
            log_message("📤 [RAW] Compression - 1 message:")
            preview = summary_prompt[:300].replace("\n", "\\n") if summary_prompt else ""
            log_message(f"   [0] role=system, len={len(summary_prompt)}: {preview}...")

        response = await llm_client.chat(
            model=model_name,
            messages=messages,
            options=options
        )

        summary_time = time.time() - summary_start
        end_timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]

        summary_text = response.text if response else ""

        if response:
            tokens_generated = response.tokens_generated
            tokens_per_second = response.tokens_per_second
        else:
            tokens_generated = len(summary_text) // 4
            tokens_per_second = tokens_generated / summary_time if summary_time > 0 else 0

        log_message(f"✅ [END {end_timestamp}] Summary generated:")
        log_message(f"   └─ Chars: {len(summary_text)}, Tokens: ~{format_number(tokens_generated)}")
        log_message(f"   └─ Time: {format_number(summary_time, 2)}s, Speed: {format_number(tokens_per_second, 1)} tok/s")

        # TOLERANCE CHECK: Is summary too large?
        summary_tokens = int(len(summary_text) / 3.5)
        max_allowed = int(summary_target_tokens * (1 + HISTORY_SUMMARY_TOLERANCE))

        if summary_tokens > max_allowed:
            log_message(f"⚠️ Summary too large: {format_number(summary_tokens)} > {format_number(max_allowed)} (target + 50%) → truncating")
            summary_text = truncate_to_tokens(summary_text, max_allowed)
            yield {"type": "debug", "message": f"✂️ Summary truncated: {format_number(summary_tokens)} → ~{format_number(max_allowed)} tok"}

        if tokens_to_compress > 0 and tokens_generated > 0:
            log_message(f"   └─ Compression: {format_number(tokens_to_compress)} → {format_number(tokens_generated)} tok ({format_number(tokens_to_compress/tokens_generated, 1)}:1)")
        console_separator()

    except asyncio.TimeoutError:
        log_message("⚠️ Async timeout during summary generation")
        yield {"type": "debug", "message": "⚠️ Summary generation timeout"}
        summary_text = ""
    except Exception as e:
        log_message(f"❌ Error during summary generation: {e}")
        yield {"type": "debug", "message": f"❌ Summary error: {e}"}
        summary_text = ""

    # Build new histories only if summary successful
    if summary_text and len(summary_text.strip()) > 10:
        # New format: [📊 Summary #N|X Messages|Timestamp]
        # - N = sequential number (count of ALL existing summaries + 1)
        # - X Messages = how many messages were compressed
        # - Timestamp = when compression happened
        # NOTE: Use count_summaries(history) because with inline placement,
        #       old summaries are in the MIDDLE of history, not at the front!
        import datetime
        summary_number = count_summaries(history) + 1
        timestamp = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        summary_entry = (
            "",
            f"[📊 Summary #{summary_number}|{len(messages_to_compress)} Messages|{timestamp}]\n{summary_text.strip()}"
        )

        # ============================================================
        # DUAL-HISTORY UPDATE (v2.13.0+)
        # ============================================================
        # chat_history (UI): Original-Messages bleiben, Summary NACH komprimierten Messages
        # Reihenfolge: preserved_summaries + messages_to_compress + [summary_entry] + remaining_messages
        new_chat_history = preserved_summaries + messages_to_compress + [summary_entry] + remaining_messages

        # llm_history (LLM): Alte Messages durch Summary ersetzen
        new_llm_history = None
        if llm_history is not None:
            from .message_builder import clean_content_for_llm

            # Preserved summaries as system messages
            preserved_llm_summaries = [
                msg for msg in llm_history
                if msg.get("role") == "system" and msg.get("content", "").startswith("[Summary]")
            ]

            # New summary as system message (clean text only, no UI markers)
            summary_system_msg = {
                "role": "system",
                "content": f"[Summary]\n{summary_text.strip()}"
            }

            # Remaining messages: Convert from chat_history tuples
            # (messages_to_compress wurden komprimiert, remaining_messages bleiben)
            remaining_llm_messages = []
            for user_msg, ai_msg in remaining_messages:
                if is_summary_entry(user_msg, ai_msg):
                    # Skip summaries - already handled above
                    continue
                if user_msg == "" and ai_msg:
                    # Agent-only entry (Sokrates, Salomo, AIfred revision)
                    cleaned = clean_content_for_llm(ai_msg)
                    if cleaned:
                        remaining_llm_messages.append({"role": "assistant", "content": cleaned})
                else:
                    # Normal exchange
                    if user_msg:
                        remaining_llm_messages.append({"role": "user", "content": user_msg})
                    if ai_msg:
                        cleaned = clean_content_for_llm(ai_msg)
                        if cleaned:
                            remaining_llm_messages.append({"role": "assistant", "content": cleaned})

            new_llm_history = preserved_llm_summaries + [summary_system_msg] + remaining_llm_messages
    else:
        log_message("⚠️ Summary too short or empty - history remains unchanged")
        yield {"type": "debug", "message": "⚠️ Compression failed - history unchanged"}
        return

    # Calculate results (based on llm_history for accurate LLM token count)
    if new_llm_history is not None:
        new_history_tokens = estimate_tokens_from_history(
            [(msg.get("content", ""), "") for msg in new_llm_history]
        )
    else:
        new_history_tokens = estimate_tokens_from_history(new_chat_history)

    # Include system prompt in new utilization (same as trigger calculation)
    new_total_tokens = system_prompt_tokens + new_history_tokens
    new_utilization = (new_total_tokens / context_limit) * 100
    compression_ratio = history_tokens / new_history_tokens if new_history_tokens > 0 else 0
    summaries_count = count_summaries(new_chat_history)

    log_message("✅ History successfully compressed:")
    log_message(f"   └─ Chat-History: {len(history)} → {len(new_chat_history)} entries (UI vollständig)")
    if new_llm_history is not None:
        log_message(f"   └─ LLM-History: {len(new_llm_history)} messages (komprimiert)")
    log_message(f"   └─ History Tokens: {format_number(history_tokens)} → {format_number(new_history_tokens)} ({format_number(compression_ratio, 1)}:1)")
    log_message(f"   └─ Total (incl. System): {format_number(total_tokens)} → {format_number(new_total_tokens)} tok")
    log_message(f"   └─ Utilization: {int(utilization)}% → {int(new_utilization)}%")
    log_message(f"   └─ Space freed: {format_number(history_tokens - new_history_tokens)} tok")

    # Yield update to state (DUAL-HISTORY format)
    yield {
        "type": "history_update",
        "chat_history": new_chat_history,
        "llm_history": new_llm_history  # None if not provided
    }
    yield {"type": "debug", "message": f"📦 Compressed: {int(utilization)}% → {int(new_utilization)}% ({format_number(total_tokens)} → {format_number(new_total_tokens)} tok, {len(messages_to_compress)}→1 msg, {summaries_count} summaries)"}


async def prepare_main_llm(
    backend,
    llm_client,
    model_name: str,
    messages: list,
    num_ctx_mode: str = "auto",
    num_ctx_manual: int = 4096,
    backend_type: str = "ollama"
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
            log_message("🔄 prepare_main_llm: Starting VRAM calculation")

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
            yield {"type": "debug", "message": f"🚀 AIfred-LLM ({model_name}) is being preloaded (num_ctx={formatted_ctx})..."}
            log_message(f"🔄 prepare_main_llm: Starting preload for {model_name} (num_ctx={final_num_ctx:,})...")

            # Give event loop a chance to flush the UI update before blocking preload
            import asyncio
            await asyncio.sleep(0)

            preload_success, preload_time = await backend.preload_model(model_name, num_ctx=final_num_ctx)

            if preload_success:
                yield {"type": "debug", "message": f"✅ AIfred-LLM preloaded ({preload_time:.1f}s)"}
                # Note: log_message() is called via add_debug() when yield is processed
            else:
                yield {"type": "debug", "message": f"⚠️ AIfred-LLM preload failed ({preload_time:.1f}s)"}
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

