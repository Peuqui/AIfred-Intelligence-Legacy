"""
Cache Handler - Handles cache hits from previous research sessions

Extracted from perform_agent_research() to improve modularity.
"""

import datetime
import time  # For strftime
from typing import Dict, List, Optional, AsyncIterator

from ..cache_manager import get_cached_research
from ..timer import Timer
from ..tools import build_context
from ..prompt_loader import load_prompt, load_identity, load_personality, load_reasoning
from ..context_manager import estimate_tokens, calculate_dynamic_num_ctx, strip_thinking_blocks
from ..intent_detector import detect_cache_followup_intent, get_temperature_for_intent, get_temperature_label
from ..formatting import format_thinking_process, format_number, build_inference_metadata
from ..logging_utils import log_message, console_separator, CONSOLE_SEPARATOR
from .context_utils import get_cache_context_budget
from ..streaming_utils import stream_llm_response


async def handle_cache_hit(
    session_id: Optional[str],
    user_text: str,
    history: list,
    llm_history: List[Dict[str, str]],
    model_choice: str,
    automatik_model: str,
    llm_client,
    automatik_llm_client,
    llm_options: Optional[Dict],
    temperature_mode: str,
    temperature: float,
    agent_timer: Timer,
    state=None,  # AIState object (REQUIRED for per-agent num_ctx lookup)
    user_name: Optional[str] = None,
    detected_language: str = "de",
    automatik_num_ctx: Optional[int] = None,
    backend_type: str = "",
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

    # Cache-Hit! (cache_entry is guaranteed not None here, session_id must be valid)
    assert session_id is not None
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
        history=history,
        user_text=user_text,
        state=state
    )

    # 6. Build context with dynamic limit
    context = build_context(user_text, scraped_only, max_context_tokens=max_rag_tokens)

    # Use detected_language from Intent Detection (passed from caller)
    detected_user_language = detected_language

    # System prompt for cache hit with 4-layer merging:
    # Identity + Reasoning (if enabled) + Task prompt + Personality (if enabled)
    identity = load_identity("aifred", detected_user_language)
    reasoning = load_reasoning("aifred", detected_user_language)
    personality = load_personality("aifred", detected_user_language)
    task_prompt = load_prompt(
        'aifred/system_rag_cache_hit',
        lang=detected_user_language,
        original_question=cache_entry.get('user_text', 'N/A'),
        current_question=user_text,
        current_year=time.strftime("%Y"),
        current_date=time.strftime("%d.%m.%Y"),
        context=context
    )

    # Merge layers: Identity + Reasoning + Task + Personality
    prompt_parts = []
    if identity:
        prompt_parts.append(identity)
    if reasoning:
        prompt_parts.append(reasoning)
    prompt_parts.append(task_prompt)
    if personality:
        prompt_parts.append(personality)
    system_prompt = "\n\n".join(prompt_parts)

    # Generate response with cache data
    messages = []

    # Add history (if available) - LLM sees previous conversation
    # History entries are dicts with "role" and "content" keys
    for h in history:
        role = h.get("role", "")
        content = h.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({'role': role, 'content': content})

    # System prompt + current user question
    messages.insert(0, {'role': 'system', 'content': system_prompt})
    messages.append({'role': 'user', 'content': user_text})

    # Query main model context limit (if not manually set)
    if not (llm_options and llm_options.get('num_ctx')):
        model_limit, _ = await llm_client.get_model_context_limit(model_choice)
        log_message(f"📊 AIfred-LLM ({model_choice}): Max. Context = {format_number(model_limit)} tok (Model parameter from Ollama)")
        yield {"type": "debug", "message": f"📊 AIfred-LLM ({model_choice}): Max. Context = {format_number(model_limit)} tok"}

    # Count actual input tokens (using real tokenizer)
    input_tokens = estimate_tokens(messages, model_name=model_choice)

    # Dynamic num_ctx calculation using centralized function
    from .context_utils import get_agent_num_ctx
    if state:
        final_num_ctx, ctx_source = get_agent_num_ctx("aifred", state, model_choice)
        if ctx_source == "manual":
            if llm_options is None:
                llm_options = {}
            llm_options['num_ctx'] = final_num_ctx
            log_message(f"🔧 Manual Context: {format_number(final_num_ctx)} (per-agent setting)")
        else:
            log_message(f"🎯 Context: {format_number(final_num_ctx)} ({ctx_source})")
    else:
        # Fallback if no state available
        enable_vram_limit = True
        final_num_ctx, vram_debug_msgs = await calculate_dynamic_num_ctx(
            llm_client, model_choice, messages, llm_options,
            enable_vram_limit=enable_vram_limit
        )
        for msg in vram_debug_msgs:
            yield {"type": "debug", "message": msg}

    # Show both: actual input and context limit
    yield {"type": "debug", "message": f"📊 Input Context: ~{format_number(input_tokens)} tok"}
    if llm_options and llm_options.get('num_ctx'):
        log_message(f"🎯 Cache-Hit Context Window: {format_number(final_num_ctx)} tok (manual)")
        yield {"type": "debug", "message": f"🪟 Context Limit: {format_number(final_num_ctx)} tok (manual)"}
    else:
        log_message(f"🎯 Cache-Hit Context Window: {format_number(final_num_ctx)} tok (dynamic, ~{format_number(input_tokens)} tok needed)")
        yield {"type": "debug", "message": f"🪟 Context Limit: {format_number(final_num_ctx)} tok"}

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
            llm_options=llm_options,
            automatik_num_ctx=automatik_num_ctx
        )
        final_temperature = get_temperature_for_intent(followup_intent)
        temp_label = get_temperature_label(followup_intent)
        log_message(f"🌡️ Cache-Hit Temperature: {final_temperature} (Intent: {followup_intent})")
        yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (auto, {temp_label})"}

    # Console: LLM starts (with MoE/Dense architecture + calibration info)
    from ..gpu_utils import is_moe_model
    is_moe = is_moe_model(model_choice)
    arch_label = "MoE" if is_moe else "Dense"
    from ..model_vram_cache import get_llamacpp_calibration_info
    _cal = get_llamacpp_calibration_info(model_choice)
    if _cal and _cal["mode"] == "hybrid":
        arch_label += f", hybrid ngl={_cal['ngl']}"
    yield {"type": "debug", "message": f"🎩 AIfred-LLM starting: {model_choice} ({arch_label}, cache data)"}

    # Show LLM generation phase
    yield {"type": "progress", "phase": "llm"}

    # Build LLM options (include enable_thinking from user settings)
    # Note: num_predict intentionally omitted - Ollama generates until EOS or num_ctx full
    cache_llm_options = {
        'temperature': final_temperature,  # Adaptive or manual temperature!
        'num_ctx': final_num_ctx  # Dynamically calculated or user-specified
    }

    # Add enable_thinking if provided in llm_options (user toggle)
    if llm_options and 'enable_thinking' in llm_options:
        cache_llm_options['enable_thinking'] = llm_options['enable_thinking']

    # Stream response using centralized utility
    final_answer = ""
    metrics = {}
    llm_time = 0.0
    tokens_per_sec = 0.0
    tokens_generated = 0
    tokens_prompt = 0
    ttft = None

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
            tokens_generated = metrics.get("tokens_generated", 0)
            tokens_prompt = metrics.get("tokens_prompt", 0)
            ttft = chunk.get("ttft")

    total_time = agent_timer.elapsed()

    # Strip thinking blocks and update llm_history BEFORE calculating history_tokens
    final_answer_clean = strip_thinking_blocks(final_answer) if final_answer else ""
    if final_answer_clean:
        llm_history.append({"role": "assistant", "content": f"[AIFRED]: {final_answer_clean}"})

    # History tokens now reflect the current conversation state (incl. AI response)
    from ..context_manager import estimate_tokens_from_llm_history
    history_tokens = estimate_tokens_from_llm_history(llm_history)

    # Centralized metadata (PP speed, debug log, chat bubble) - same as all other paths
    source_label = f"Session Cache ({model_choice})"
    metadata_dict, metadata_display, debug_msg = build_inference_metadata(
        ttft=ttft,
        inference_time=llm_time,
        tokens_generated=tokens_generated,
        tokens_per_sec=tokens_per_sec,
        source=source_label,
        backend_metrics=metrics,
        tokens_prompt=tokens_prompt,
        history_tokens=history_tokens,
        backend_type=backend_type,
    )
    yield {"type": "debug", "message": debug_msg}
    metadata_dict["sources_count"] = len(cached_sources)

    # Format <think> tags as collapsible (if present)
    final_answer_formatted = format_thinking_process(final_answer, model_name=model_choice, inference_time=llm_time, tokens_per_sec=tokens_per_sec)

    # Add AI response to chat_history (UI display)
    history.append({
        "role": "assistant",
        "content": f"{final_answer_formatted}\n\n{metadata_display}",
        "agent": "aifred",
        "agent_display_name": "AIfred",
        "agent_emoji": "\U0001f3a9",
        "mode": "session_cache",
        "round_num": 0,
        "metadata": metadata_dict,
        "timestamp": datetime.datetime.now().isoformat()
    })

    log_message(f"✅ Cache-based response done in {format_number(total_time, 1)}s")

    # Clear progress before final result
    yield {"type": "progress", "clear": True}

    # Separator after cache hit (log file + debug console)
    console_separator()
    yield {"type": "debug", "message": CONSOLE_SEPARATOR}

    # Extract used_sources from cached sources (for UI display)
    used_sources = [
        {
            "url": src.get("url", ""),
            "word_count": src.get("word_count", 0)
        }
        for src in cached_sources
        if src.get("url")
    ]

    # Final result - unified Dict format
    yield {
        "type": "result",
        "data": {
            "response_clean": final_answer_clean,
            "response_html": f"{final_answer_formatted}\n\n{metadata_display}",
            "history": history,
            "inference_time": total_time,
            "tokens_per_sec": tokens_per_sec,
            "ttft": ttft,
            "model_choice": model_choice,
            "failed_sources": [],  # Cache hits have no failed sources
            "used_sources": used_sources,  # Successfully scraped URLs from cache
            "cache_hit": True,
        }
    }
