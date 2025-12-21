"""
Cache Handler - Handles cache hits from previous research sessions

Extracted from perform_agent_research() to improve modularity.
"""

import time
from typing import Dict, List, Optional, AsyncIterator

from ..cache_manager import get_cached_research
from ..agent_tools import build_context
from ..prompt_loader import load_prompt
from ..context_manager import estimate_tokens, calculate_dynamic_num_ctx
from ..intent_detector import detect_cache_followup_intent, get_temperature_for_intent, get_temperature_label
from ..formatting import format_thinking_process, format_number, format_metadata
from ..logging_utils import log_message, console_separator, CONSOLE_SEPARATOR
from .context_utils import get_cache_context_budget
from ..streaming_utils import stream_llm_response
from ..config import DYNAMIC_NUM_PREDICT_SAFETY_MARGIN, DYNAMIC_NUM_PREDICT_MINIMUM


async def handle_cache_hit(
    session_id: Optional[str],
    user_text: str,
    history: List[tuple],
    model_choice: str,
    automatik_model: str,
    llm_client,
    automatik_llm_client,
    llm_options: Optional[Dict],
    temperature_mode: str,
    temperature: float,
    agent_start: float,
    num_ctx_mode: str = "auto_vram",
    num_ctx_manual: int = 16384
) -> AsyncIterator[Dict]:
    """
    Handles cache hit - uses cached research data to answer follow-up question

    Args:
        session_id: Session ID for cache lookup
        user_text: Current user question
        history: Chat history
        model_choice: Main LLM model name
        automatik_model: Automatik LLM model name
        llm_client: Main LLM client
        automatik_llm_client: Automatik LLM client
        llm_options: LLM options (num_ctx override, etc.)
        temperature_mode: 'manual' or 'auto'
        temperature: Temperature value (if manual)
        agent_start: Start time for timing

    Yields:
        Dict: Progress, debug, content, and result events
    """
    # 0. Cache-Check
    cache_entry = get_cached_research(session_id)
    cached_sources = cache_entry.get('scraped_sources', []) if cache_entry else []

    if not cached_sources or not cache_entry:
        # No cache hit
        if session_id:
            log_message(f"⚠️ No cache found for session {session_id[:8]}... → Normal web research")
        return

    # Cache-Hit! (cache_entry is guaranteed not None here)
    log_message(f"💾 Cache-Hit! Using cached research (Session {session_id[:8]}...)")
    log_message(f"   Original question: {cache_entry.get('user_text', 'N/A')[:80]}...")
    log_message(f"   Cache contains {len(cached_sources)} sources")

    # Console output for cache hit
    yield {"type": "debug", "message": f"💾 Cache-Hit! Using cached data ({len(cached_sources)} sources)"}
    original_q = cache_entry.get('user_text', 'N/A')
    yield {"type": "debug", "message": f"📋 Original question: {original_q[:60]}{'...' if len(original_q) > 60 else ''}"}

    # Use ALL sources from the cache
    scraped_only = cached_sources

    # ============================================================
    # VRAM-AWARE Context Building (via context_utils.py)
    # ============================================================
    max_rag_tokens, actual_reserve, max_ctx = await get_cache_context_budget(
        llm_client=llm_client,
        model_choice=model_choice,
        num_ctx_mode=num_ctx_mode,
        num_ctx_manual=num_ctx_manual,
        history=history,
        user_text=user_text
    )

    # 6. Build context with dynamic limit
    context = build_context(user_text, scraped_only, max_context_tokens=max_rag_tokens)

    # Language detection for user text
    from ..prompt_loader import detect_language
    detected_user_language = detect_language(user_text)

    # System prompt for cache hit: Use separate prompt file
    system_prompt = load_prompt(
        'system_rag_cache_hit',
        lang=detected_user_language,
        original_question=cache_entry.get('user_text', 'N/A'),
        current_question=user_text,
        current_year=time.strftime("%Y"),
        current_date=time.strftime("%d.%m.%Y"),
        context=context
    )

    # Generate response with cache data
    messages = []

    # Add history (if available) - LLM sees previous conversation
    for h in history:
        user_msg = h[0].split(" (STT:")[0].split(" (Agent:")[0] if " (STT:" in h[0] or " (Agent:" in h[0] else h[0]
        ai_msg = h[1].split(" (Inferenz:")[0] if " (Inferenz:" in h[1] else h[1]
        messages.extend([
            {'role': 'user', 'content': user_msg},
            {'role': 'assistant', 'content': ai_msg}
        ])

    # System prompt + current user question
    messages.insert(0, {'role': 'system', 'content': system_prompt})
    messages.append({'role': 'user', 'content': user_text})

    # Query main model context limit (if not manually set)
    if not (llm_options and llm_options.get('num_ctx')):
        model_limit, _ = await llm_client.get_model_context_limit(model_choice)
        log_message(f"📊 Main-LLM ({model_choice}): Max. Context = {format_number(model_limit)} tok (Model parameter from Ollama)")
        yield {"type": "debug", "message": f"📊 Main-LLM ({model_choice}): Max. Context = {format_number(model_limit)} tok"}

    # Count actual input tokens (using real tokenizer)
    input_tokens = estimate_tokens(messages, model_name=model_choice)

    # Dynamic num_ctx calculation with mode handling
    if num_ctx_mode == "manual":
        # Manual mode: Use user-specified value
        if llm_options is None:
            llm_options = {}
        llm_options['num_ctx'] = num_ctx_manual
        final_num_ctx = num_ctx_manual
        log_message(f"🔧 Manual num_ctx: {format_number(num_ctx_manual)} (VRAM calculation skipped)")
    else:
        # Auto mode: Determine VRAM limiting
        enable_vram_limit = (num_ctx_mode == "auto_vram")
        final_num_ctx, vram_debug_msgs = await calculate_dynamic_num_ctx(
            llm_client, model_choice, messages, llm_options,
            enable_vram_limit=enable_vram_limit
        )
        # Yield VRAM debug messages to UI console
        for msg in vram_debug_msgs:
            yield {"type": "debug", "message": msg}

    # Show both: actual input and context limit
    yield {"type": "debug", "message": f"📊 Input Context: ~{format_number(input_tokens)} tok"}
    if llm_options and llm_options.get('num_ctx'):
        log_message(f"🎯 Cache-Hit Context Window: {format_number(final_num_ctx)} tok (manual)")
        yield {"type": "debug", "message": f"🪟 num_ctx (Limit): {format_number(final_num_ctx)} tok (manual)"}
    else:
        log_message(f"🎯 Cache-Hit Context Window: {format_number(final_num_ctx)} tok (dynamic, ~{format_number(input_tokens)} tok needed)")
        yield {"type": "debug", "message": f"🪟 num_ctx (Limit): {format_number(final_num_ctx)} tok"}

    # Temperature decision: Manual override or Auto (intent detection)
    if temperature_mode == 'manual':
        final_temperature = temperature
        log_message(f"🌡️ Cache-Hit Temperature: {final_temperature} (MANUAL OVERRIDE)")
        yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (manual)"}
    else:
        # Auto: Intent detection for cache followup
        followup_intent = await detect_cache_followup_intent(
            original_query=cache_entry.get('user_text', ''),
            followup_query=user_text,
            automatik_model=automatik_model,
            llm_client=automatik_llm_client,
            llm_options=llm_options
        )
        final_temperature = get_temperature_for_intent(followup_intent)
        temp_label = get_temperature_label(followup_intent)
        log_message(f"🌡️ Cache-Hit Temperature: {final_temperature} (Intent: {followup_intent})")
        yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (auto, {temp_label})"}

    # Console: LLM starts
    yield {"type": "debug", "message": f"🤖 Main-LLM starting: {model_choice} (cache data)"}

    # Show LLM generation phase
    yield {"type": "progress", "phase": "llm"}

    # Calculate dynamic num_predict: Available output space after input tokens
    available_output = max(
        DYNAMIC_NUM_PREDICT_MINIMUM,
        final_num_ctx - input_tokens - DYNAMIC_NUM_PREDICT_SAFETY_MARGIN
    )

    log_message(f"🧮 Dynamic num_predict: {format_number(available_output)} tokens (num_ctx: {format_number(final_num_ctx)}, input: {format_number(input_tokens)}, margin: {DYNAMIC_NUM_PREDICT_SAFETY_MARGIN})")

    # Build LLM options (include enable_thinking from user settings)
    cache_llm_options = {
        'temperature': final_temperature,  # Adaptive or manual temperature!
        'num_ctx': final_num_ctx,  # Dynamically calculated or user-specified
        'num_predict': available_output  # Dynamic: Full available output space
    }

    # Add enable_thinking if provided in llm_options (user toggle)
    if llm_options and 'enable_thinking' in llm_options:
        cache_llm_options['enable_thinking'] = llm_options['enable_thinking']

    # Stream response using centralized utility
    final_answer = ""
    metrics = {}
    llm_time = 0.0
    tokens_per_sec = 0.0

    async for chunk in stream_llm_response(
        llm_client, model_choice, messages, cache_llm_options,
        ttft_label="TTFT"
    ):
        if chunk["type"] == "content":
            yield chunk
        elif chunk["type"] == "debug":
            yield chunk
        elif chunk["type"] == "thinking_warning":
            yield chunk
        elif chunk["type"] == "stream_result":
            # Final chunk with accumulated data
            final_answer = chunk["text"]
            metrics = chunk["metrics"]
            llm_time = chunk["inference_time"]
            tokens_per_sec = metrics.get("tokens_per_second", 0)

    total_time = time.time() - agent_start

    # Console: LLM finished (Cache-specific with total time)
    tokens_generated = metrics.get("tokens_generated", 0)
    yield {"type": "debug", "message": f"✅ Main-LLM done ({format_number(llm_time, 1)}s, {format_number(tokens_generated)} tok, {format_number(tokens_per_sec, 1)} tok/s, Cache-Total: {format_number(total_time, 1)}s)"}

    # Format <think> tags as collapsible (if present)
    final_answer_formatted = format_thinking_process(final_answer, model_name=model_choice, inference_time=llm_time, tokens_per_sec=tokens_per_sec)

    # Timing text
    timing_text = format_metadata(f"Cache-Hit: {format_number(total_time, 1)}s = LLM {format_number(llm_time, 1)}s    {format_number(tokens_per_sec, 1)} tok/s    Source: Session Cache")
    ai_text_with_timing = final_answer_formatted + "\n\n" + timing_text

    # Update History
    user_display = f"{user_text}\n{format_metadata(f'Agent: Cache-Hit    {len(cached_sources)} sources')}"
    ai_display = ai_text_with_timing
    history.append((user_display, ai_display))

    log_message(f"✅ Cache-based response done in {format_number(total_time, 1)}s")

    # Clear progress before final result
    yield {"type": "progress", "clear": True}

    # Separator after cache hit (log file + debug console)
    console_separator()
    yield {"type": "debug", "message": CONSOLE_SEPARATOR}

    # Yield final result
    yield {"type": "result", "data": (ai_text_with_timing, history, total_time)}
