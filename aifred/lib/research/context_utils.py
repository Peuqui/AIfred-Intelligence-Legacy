"""
Context Building Utilities - Shared functions for VRAM-aware context calculation

This module eliminates code duplication between context_builder.py and cache_handler.py
by providing common utility functions for context budget calculation.
"""

from ..context_manager import get_max_available_context, calculate_adaptive_reserve
from ..config import (
    SYSTEM_PROMPT_ESTIMATE_RAG,
    SYSTEM_PROMPT_ESTIMATE_CACHE,
    TOKENS_PER_HISTORY_TURN,
    CHARS_PER_TOKEN,
    MAX_RAG_CONTEXT_TOKENS
)
from ..formatting import format_number
from ..logging_utils import log_message


async def calculate_vram_aware_rag_budget(
    llm_client,
    model_choice: str,
    num_ctx_mode: str,
    num_ctx_manual: int,
    history: list,
    user_text: str,
    system_prompt_estimate: int,
    log_prefix: str = "RAG"
) -> tuple[int, int, int]:
    """
    Calculate VRAM-aware RAG context budget.

    This function consolidates the duplicated logic from context_builder.py
    and cache_handler.py into a single reusable utility.

    Args:
        llm_client: LLM client instance
        model_choice: Model name/ID
        num_ctx_mode: "auto_vram", "manual", or "auto_unlimited"
        num_ctx_manual: Manual context size (used if mode is "manual")
        history: Chat history list
        user_text: Current user message
        system_prompt_estimate: Token estimate for system prompt (RAG or Cache mode)
        log_prefix: Prefix for log messages (e.g., "RAG" or "Cache RAG")

    Returns:
        Tuple of (max_rag_tokens, actual_reserve, max_ctx)
    """
    # 1. VRAM-Limit vorab ermitteln (wenn auto_vram aktiv)
    if num_ctx_mode == "auto_vram":
        max_ctx, model_limit = await get_max_available_context(
            llm_client, model_choice,
            enable_vram_limit=True
        )
    elif num_ctx_mode == "manual":
        max_ctx = num_ctx_manual
        model_limit = num_ctx_manual
    else:
        # auto_unlimited: Kein VRAM-Limit
        max_ctx, model_limit = await get_max_available_context(
            llm_client, model_choice,
            enable_vram_limit=False
        )

    # 2. Fixe Overhead-Schätzung (System-Prompt, History, User-Message)
    history_estimate = len(history) * TOKENS_PER_HISTORY_TURN
    user_message_estimate = len(user_text) // CHARS_PER_TOKEN

    # 3. Base Input ohne RAG-Context
    base_input = system_prompt_estimate + history_estimate + user_message_estimate

    # 4. Adaptive Reserve-Berechnung
    # Priorität: Maximiere RAG-Content, reduziere Reserve stufenweise (8K → 6K → 4K)
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
    num_ctx_mode: str,
    num_ctx_manual: int,
    history: list,
    user_text: str
) -> tuple[int, int, int]:
    """
    Get RAG context budget for fresh web research.

    Convenience wrapper for calculate_vram_aware_rag_budget with RAG-specific settings.
    """
    return await calculate_vram_aware_rag_budget(
        llm_client=llm_client,
        model_choice=model_choice,
        num_ctx_mode=num_ctx_mode,
        num_ctx_manual=num_ctx_manual,
        history=history,
        user_text=user_text,
        system_prompt_estimate=SYSTEM_PROMPT_ESTIMATE_RAG,
        log_prefix="RAG"
    )


async def get_cache_context_budget(
    llm_client,
    model_choice: str,
    num_ctx_mode: str,
    num_ctx_manual: int,
    history: list,
    user_text: str
) -> tuple[int, int, int]:
    """
    Get context budget for cache-hit scenarios.

    Convenience wrapper for calculate_vram_aware_rag_budget with Cache-specific settings.
    Cache prompts are slightly larger, so we use SYSTEM_PROMPT_ESTIMATE_CACHE.
    """
    return await calculate_vram_aware_rag_budget(
        llm_client=llm_client,
        model_choice=model_choice,
        num_ctx_mode=num_ctx_mode,
        num_ctx_manual=num_ctx_manual,
        history=history,
        user_text=user_text,
        system_prompt_estimate=SYSTEM_PROMPT_ESTIMATE_CACHE,
        log_prefix="Cache RAG"
    )
