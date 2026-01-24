"""
Context Building Utilities - Shared functions for VRAM-aware context calculation

This module eliminates code duplication between context_builder.py and cache_handler.py
by providing common utility functions for context budget calculation.
"""

from typing import Tuple, TYPE_CHECKING

from ..context_manager import get_max_available_context, calculate_adaptive_reserve
from ..config import (
    SYSTEM_PROMPT_ESTIMATE_RAG,
    SYSTEM_PROMPT_ESTIMATE_CACHE,
    TOKENS_PER_HISTORY_TURN,
    CHARS_PER_TOKEN,
    MAX_RAG_CONTEXT_TOKENS,
    MAIN_LLM_FALLBACK_CONTEXT,
    XTTS_VRAM_MB,
    VRAM_CONTEXT_RATIO_DENSE
)
from ..formatting import format_number
from ..logging_utils import log_message
from ..model_vram_cache import get_ollama_calibration, get_rope_factor_for_model

if TYPE_CHECKING:
    from ...state import AIState


def get_agent_num_ctx(
    agent: str,
    state: "AIState",
    model_id: str,
    fallback: int = MAIN_LLM_FALLBACK_CONTEXT  # Use config constant (32K) as default
) -> Tuple[int, str]:
    """
    Determine num_ctx for a specific agent.

    This is the SINGLE SOURCE OF TRUTH for num_ctx determination.
    All code that needs to determine num_ctx for an agent should use this function.

    IMPORTANT: This function applies XTTS VRAM reservation when TTS is enabled on GPU.
    The returned num_ctx is already reduced by ~14K tokens when XTTS uses GPU VRAM.

    Args:
        agent: Agent identifier - "aifred", "sokrates", or "salomo"
        state: AIState instance containing per-agent settings
        model_id: Ollama model ID (e.g., "qwen3:14b")
        fallback: Default value if no calibration available (default: MAIN_LLM_FALLBACK_CONTEXT = 32K)

    Returns:
        Tuple of (num_ctx, source) where source is one of:
        - "manual" - User explicitly set a manual value
        - "VRAM cache" - Value from VRAM calibration cache
        - "VRAM cache (XTTS: -X tok)" - With XTTS reservation applied
        - "fallback" - No calibration available, using fallback

    Examples:
        >>> num_ctx, source = get_agent_num_ctx("aifred", state, "qwen3:14b")
        >>> print(f"Using {num_ctx} tokens ({source})")
        Using 111360 tokens (VRAM cache)

        >>> num_ctx, source = get_agent_num_ctx("sokrates", state, "qwen3:8b")
        >>> print(f"Using {num_ctx} tokens ({source})")
        Using 4096 tokens (manual)
    """
    # Validate agent name
    if agent not in ("aifred", "sokrates", "salomo"):
        raise ValueError(f"Unknown agent: {agent}. Must be 'aifred', 'sokrates', or 'salomo'.")

    # Check if manual mode is enabled for this agent
    enabled_attr = f"num_ctx_manual_{agent}_enabled"
    value_attr = f"num_ctx_manual_{agent}"

    if getattr(state, enabled_attr, False):
        # Manual mode: use user-configured value (no XTTS adjustment for manual)
        manual_value = getattr(state, value_attr, fallback)
        return (manual_value if manual_value else fallback, "manual")

    # Auto mode: try VRAM calibration cache
    rope_factor = get_rope_factor_for_model(model_id)
    cached_ctx = get_ollama_calibration(model_id, rope_factor)

    if cached_ctx:
        num_ctx = cached_ctx
        source = "VRAM cache"
    else:
        # No calibration available - use fallback
        num_ctx = fallback
        source = "fallback"

    # TTS Debug Output - show active TTS configuration
    enable_tts = getattr(state, 'enable_tts', False)
    tts_engine = getattr(state, 'tts_engine', '')
    tts_streaming = getattr(state, 'tts_streaming', False)
    tts_autoplay = getattr(state, 'tts_autoplay', False)

    if enable_tts:
        # Build TTS status string
        tts_mode_parts = []
        if tts_streaming:
            tts_mode_parts.append("Streaming")
        if tts_autoplay:
            tts_mode_parts.append("Auto-Play")
        tts_mode = ", ".join(tts_mode_parts) if tts_mode_parts else "Manual"

        if 'xtts' in tts_engine.lower():
            # XTTS: Check GPU/CPU mode and apply VRAM reservation
            xtts_force_cpu = getattr(state, 'xtts_force_cpu', False)
            device_mode = "CPU" if xtts_force_cpu else "GPU"

            if not xtts_force_cpu:
                # GPU mode: Apply VRAM reservation
                xtts_token_reserve = int(XTTS_VRAM_MB / VRAM_CONTEXT_RATIO_DENSE)
                original_ctx = num_ctx
                num_ctx = max(2048, num_ctx - xtts_token_reserve)
                source = f"{source} (XTTS: -{format_number(xtts_token_reserve)} tok)"
                log_message(f"🔊 TTS: XTTS ({device_mode}), {tts_mode} | VRAM: {format_number(original_ctx)} → {format_number(num_ctx)} tok (-{format_number(xtts_token_reserve)})")
            else:
                # CPU mode: No VRAM reservation needed
                log_message(f"🔊 TTS: XTTS ({device_mode}), {tts_mode} | No VRAM reservation (CPU mode)")
        else:
            # Other TTS engines (Edge TTS, Google TTS, etc.) - no VRAM impact
            log_message(f"🔊 TTS: {tts_engine}, {tts_mode} | No VRAM impact (cloud/CPU)")

    return (num_ctx, source)


async def calculate_vram_aware_rag_budget(
    llm_client,
    model_choice: str,
    history: list,
    user_text: str,
    system_prompt_estimate: int,
    log_prefix: str = "RAG",
    state=None  # AIState object (REQUIRED for per-agent num_ctx lookup)
) -> tuple[int, int, int]:
    """
    Calculate VRAM-aware RAG context budget.

    This function consolidates the duplicated logic from context_builder.py
    and cache_handler.py into a single reusable utility.

    Args:
        llm_client: LLM client instance
        model_choice: Model name/ID
        history: Chat history list
        user_text: Current user message
        system_prompt_estimate: Token estimate for system prompt (RAG or Cache mode)
        log_prefix: Prefix for log messages (e.g., "RAG" or "Cache RAG")
        state: AIState object (REQUIRED for per-agent num_ctx lookup via get_agent_num_ctx)

    Returns:
        Tuple of (max_rag_tokens, actual_reserve, max_ctx)
    """
    # 1. Determine num_ctx using centralized function
    if state:
        max_ctx, ctx_source = get_agent_num_ctx("aifred", state, model_choice)
        if ctx_source == "manual":
            model_limit = max_ctx
        else:
            # Auto mode: max_ctx already contains VRAM-calibrated value
            model_limit = max_ctx
    else:
        # Fallback if no state provided (shouldn't happen)
        max_ctx, model_limit = await get_max_available_context(
            llm_client, model_choice,
            enable_vram_limit=True
        )

    # 2. Fixed overhead estimate (system prompt, history, user message)
    history_estimate = len(history) * TOKENS_PER_HISTORY_TURN
    user_message_estimate = len(user_text) // CHARS_PER_TOKEN

    # 3. Base input without RAG context
    base_input = system_prompt_estimate + history_estimate + user_message_estimate

    # 4. Adaptive reserve calculation
    # Priority: Maximize RAG content, reduce reserve gradually (8K → 6K → 4K)
    actual_reserve, max_rag_tokens = calculate_adaptive_reserve(
        available_context=max_ctx,
        base_input=base_input,
        max_rag_target=MAX_RAG_CONTEXT_TOKENS
    )

    log_message(f"📊 {log_prefix} Context Budget: {format_number(max_rag_tokens)} tok "
                f"(VRAM-max: {format_number(max_ctx)}, Reserve: {format_number(actual_reserve)})")

    return max_rag_tokens, actual_reserve, max_ctx


async def get_rag_context_budget(
    llm_client,
    model_choice: str,
    history: list,
    user_text: str,
    state=None  # AIState object (REQUIRED for per-agent num_ctx lookup)
) -> tuple[int, int, int]:
    """
    Get RAG context budget for fresh web research.

    Convenience wrapper for calculate_vram_aware_rag_budget with RAG-specific settings.
    """
    return await calculate_vram_aware_rag_budget(
        llm_client=llm_client,
        model_choice=model_choice,
        history=history,
        user_text=user_text,
        system_prompt_estimate=SYSTEM_PROMPT_ESTIMATE_RAG,
        log_prefix="RAG",
        state=state
    )


async def get_cache_context_budget(
    llm_client,
    model_choice: str,
    history: list,
    user_text: str,
    state=None  # AIState object (REQUIRED for per-agent num_ctx lookup)
) -> tuple[int, int, int]:
    """
    Get context budget for cache-hit scenarios.

    Convenience wrapper for calculate_vram_aware_rag_budget with Cache-specific settings.
    Cache prompts are slightly larger, so we use SYSTEM_PROMPT_ESTIMATE_CACHE.
    """
    return await calculate_vram_aware_rag_budget(
        llm_client=llm_client,
        model_choice=model_choice,
        history=history,
        user_text=user_text,
        system_prompt_estimate=SYSTEM_PROMPT_ESTIMATE_CACHE,
        log_prefix="Cache RAG",
        state=state
    )
