"""
Context Builder - Build context and generate LLM response

Handles:
- Context building from scraped sources
- Integration of old research metadata
- Message construction with history
- LLM inference and response generation
- Cache saving
"""

import time
import re
from typing import Dict, List, Optional, AsyncIterator

from ..agent_tools import build_context
# Cache system removed - will be replaced with Vector DB
from ..prompt_loader import get_system_rag_prompt
from ..context_manager import calculate_dynamic_num_ctx, estimate_tokens, strip_thinking_blocks
from ..message_builder import build_messages_from_llm_history
from ..formatting import format_thinking_process, build_debug_accordion, format_metadata, format_number
from ..logging_utils import log_message
from ..config import (
    CHARS_PER_TOKEN,
    TTL_HOURS,
    DYNAMIC_NUM_PREDICT_SAFETY_MARGIN,
    DYNAMIC_NUM_PREDICT_MINIMUM
)
from ..vector_cache import format_ttl_hours
from ..intent_detector import get_temperature_for_intent, get_temperature_label
from .context_utils import get_rag_context_budget
from ..streaming_utils import stream_llm_response, log_llm_completion


async def build_and_generate_response(
    user_text: str,
    scraped_results: List[Dict],
    tool_results: List[Dict],
    failed_sources: List[Dict],
    history: List[tuple],
    llm_history: List[Dict[str, str]],
    session_id: Optional[str],
    mode: str,
    model_choice: str,
    automatik_model: str,
    query_reasoning: Optional[str],
    query_opt_time: float,
    llm_client,
    automatik_llm_client,
    llm_options: Optional[Dict],
    temperature_mode: str,
    temperature: float,
    agent_start: float,
    stt_time: float,
    state=None,  # AIState object (REQUIRED for per-agent num_ctx lookup)
    user_name: Optional[str] = None,
    detected_intent: Optional[str] = None,
    detected_language: Optional[str] = None
) -> AsyncIterator[Dict]:
    """
    Build context and generate LLM response

    Args:
        user_text: User's question
        scraped_results: Successfully scraped sources
        tool_results: All tool results (including failed)
        failed_sources: Failed scraping attempts (for cache storage)
        history: Chat history
        session_id: Session ID for caching
        mode: Research mode ('quick' or 'deep')
        model_choice: Main LLM model name
        automatik_model: Automatik LLM model name (for debug accordion)
        query_reasoning: Query optimization reasoning (for debug accordion)
        query_opt_time: Query optimization time (for debug accordion)
        llm_client: Main LLM client
        automatik_llm_client: Automatik LLM client (for cache metadata generation)
        llm_options: LLM options (num_ctx override, etc.)
        temperature_mode: 'manual' or 'auto'
        temperature: Temperature value (if manual)
        agent_start: Start time for timing
        stt_time: STT processing time (if applicable)
        detected_intent: Pre-detected intent (FAKTISCH/KREATIV/GEMISCHT) - avoids duplicate detection
        detected_language: Pre-detected language ("de" or "en") - avoids regex detection

    Yields:
        Dict: Debug messages, content chunks, final result
    """
    # Filter: Only successfully scraped sources
    scraped_only = [r for r in tool_results if 'word_count' in r and r['word_count'] > 0]

    # DEBUG logging (can be removed in production)
    for i, result in enumerate(tool_results, 1):
        if result.get('success'):
            log_message(f"  Source {i}: {result.get('word_count', 0)} words from {result.get('url', 'N/A')[:50]}")

    if scraped_only:
        for i, src in enumerate(scraped_only[:3], 1):
            content_preview = src.get('content', '')[:200].replace('\n', ' ')
            log_message(f"  📄 Source {i} Preview: {content_preview}...")

    # ============================================================
    # VRAM-AWARE Context Building (via context_utils.py)
    # Calculate max available context BEFORE build_context() runs
    # ============================================================
    max_rag_tokens, actual_reserve, max_ctx = await get_rag_context_budget(
        llm_client=llm_client,
        model_choice=model_choice,
        history=history,
        user_text=user_text,
        state=state
    )

    # 6. Build context with dynamic limit
    context = build_context(user_text, scraped_only, max_context_tokens=max_rag_tokens)

    # Estimate tokens
    est_tokens = len(context) // CHARS_PER_TOKEN
    log_message(f"📊 Context built: ~{format_number(est_tokens)} tok")

    # Show context preview
    if len(context) > 800:
        preview = context[:800] + "..."
        log_message(f"📝 Context Preview (first 800 chars):\n{preview}")

    # Use pre-detected language from LLM intent detection, or fallback to UI language setting
    if detected_language:
        detected_user_language = detected_language
    elif state and hasattr(state, 'ui_language'):
        detected_user_language = state.ui_language
    else:
        detected_user_language = "de"  # Final fallback: German

    # System prompt with personality (if enabled)
    system_prompt = get_system_rag_prompt(
        context=context,
        user_text=user_text,
        lang=detected_user_language
    )

    yield {"type": "debug", "message": "✅ System prompt created"}

    # Build messages using central function (handles [AIFRED]: stripping + personality reminder)
    # This ensures consistency with all other LLM calls in the codebase
    from ..prompt_loader import set_language
    set_language(detected_user_language)  # Set language for personality reminder

    messages = build_messages_from_llm_history(
        llm_history=llm_history,
        current_user_text=user_text,
        perspective=None  # AIfred speaking - standard mode
    )

    # Insert RAG system prompt as first message
    messages.insert(0, {"role": "system", "content": system_prompt})

    # DEBUG: Show message sizes
    for i, msg in enumerate(messages):
        role = msg['role']
        content_len = len(msg['content'])
        log_message(f"  Message {i+1} ({role}): {content_len} chars")

    # Count actual input tokens (using real tokenizer)
    input_tokens = estimate_tokens(messages, model_name=model_choice)

    # Dynamic num_ctx calculation using centralized function
    from .context_utils import get_agent_num_ctx
    if state:
        final_num_ctx, ctx_source = get_agent_num_ctx("aifred", state, model_choice, fallback=4096)
        if ctx_source == "manual":
            if llm_options is None:
                llm_options = {}
            llm_options['num_ctx'] = final_num_ctx
            log_message(f"🔧 Manual num_ctx: {format_number(final_num_ctx)} (per-agent setting)")
            yield {"type": "debug", "message": f"🔧 Manual num_ctx: {format_number(final_num_ctx)} (per-agent setting)"}
        else:
            log_message(f"🎯 Auto num_ctx: {format_number(final_num_ctx)} ({ctx_source})")
            yield {"type": "debug", "message": f"🎯 Auto num_ctx: {format_number(final_num_ctx)} ({ctx_source})"}
    else:
        # Fallback if no state available
        enable_vram_limit = True
        final_num_ctx, vram_debug_msgs = await calculate_dynamic_num_ctx(
            llm_client, model_choice, messages, llm_options,
            enable_vram_limit=enable_vram_limit
        )
        for msg in vram_debug_msgs:
            yield {"type": "debug", "message": msg}

    # Get model max context for compact display
    model_limit, _ = await llm_client.get_model_context_limit(model_choice)

    # Show compact context info (like Automatik-LLM)
    log_message(f"📊 AIfred-LLM: {format_number(input_tokens)} / {format_number(final_num_ctx)} tok [INFERENCE num_ctx={final_num_ctx}]")
    yield {"type": "debug", "message": f"📊 AIfred-LLM: {format_number(input_tokens)} / {format_number(final_num_ctx)} tok [num_ctx={final_num_ctx}]"}

    # VRAM Warning: Check if VRAM change detected AND content doesn't fit
    vram_warning = llm_options.get('_vram_warning') if llm_options else None
    if vram_warning and input_tokens > final_num_ctx:
        # Content doesn't fit AND more VRAM available → Show orange blocking warning
        vram_diff = vram_warning["vram_diff"]
        potential_tokens = vram_warning.get("potential_tokens")

        warning_msg = (
            f"⚠️ VRAM change detected: {vram_diff:+.0f}MB additional memory available!\n\n"
            f"💡 **Recommendation:** Go to **Control Panel → vLLM Restart** to use the "
            f"extended context window"
        )

        if potential_tokens:
            warning_msg += (
                f" ({format_number(vram_warning['current_tokens'])} → "
                f"~{format_number(potential_tokens)} Tokens)."
            )
        else:
            warning_msg += "."

        log_message(warning_msg)
        yield {"type": "debug", "message": warning_msg}

    # SAFEGUARD: Check if input already exceeds context limit
    if input_tokens > final_num_ctx:
        error_msg = (
            f"❌ Input too large: {format_number(input_tokens)} Tokens > "
            f"Context limit {format_number(final_num_ctx)} Tokens\n"
            f"   Please shorten your request or enable 'Manual Context' with a higher value."
        )
        # Only yield - UI will handle logging via add_debug() which calls log_message()
        yield {"type": "debug", "message": error_msg}

        # Reset UI progress state before returning error
        yield {"type": "progress", "phase": "idle"}
        yield {"type": "progress", "step": "ready"}

        yield {"type": "error", "message": error_msg}
        return

    # Temperature decision: Manual Override or Auto (reuse pre-detected intent)
    if temperature_mode == 'manual':
        final_temperature = temperature
        yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (manual)"}
    else:
        # Auto: Reuse detected_intent from state.py (no duplicate LLM call)
        final_temperature = get_temperature_for_intent(detected_intent)
        temp_label = get_temperature_label(detected_intent)
        log_message(f"🌡️ RAG Temperature: {final_temperature} (Intent: {detected_intent})")
        yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (auto, {temp_label})"}

    # LLM Inference
    yield {"type": "debug", "message": f"🎩 AIfred-LLM starting: {model_choice}"}
    yield {"type": "progress", "phase": "llm"}

    # Calculate dynamic num_predict: Available output space after input tokens
    available_output = max(
        DYNAMIC_NUM_PREDICT_MINIMUM,
        final_num_ctx - input_tokens - DYNAMIC_NUM_PREDICT_SAFETY_MARGIN
    )

    log_message(f"🧮 Dynamic num_predict: {format_number(available_output)} tokens (num_ctx: {format_number(final_num_ctx)}, input: {format_number(input_tokens)}, margin: {DYNAMIC_NUM_PREDICT_SAFETY_MARGIN})")

    # Build LLM options (include enable_thinking from user settings)
    research_llm_options = {
        'temperature': final_temperature,
        'num_ctx': final_num_ctx,
        'num_predict': available_output  # Dynamic: Full available output space
    }

    # Add enable_thinking if provided in llm_options (user toggle)
    if llm_options and 'enable_thinking' in llm_options:
        research_llm_options['enable_thinking'] = llm_options['enable_thinking']

    # Stream response using centralized utility
    ai_text = ""
    metrics = {}
    inference_time = 0.0
    tokens_per_sec = 0.0
    ttft = None

    async for chunk in stream_llm_response(
        llm_client, model_choice, messages, research_llm_options,
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
            ai_text = chunk["text"]
            metrics = chunk["metrics"]
            inference_time = chunk["inference_time"]
            tokens_per_sec = metrics.get("tokens_per_second", 0)
            ttft = chunk.get("ttft")

    # Log completion
    yield log_llm_completion(inference_time, metrics)

    # Extract volatility tag from LLM response
    volatility = "DAILY"  # Default fallback (safer than PERMANENT to avoid cache bloat)
    volatility_match = re.search(r'<volatility>(.*?)</volatility>', ai_text, re.IGNORECASE | re.DOTALL)

    if volatility_match:
        extracted = volatility_match.group(1).strip().upper()
        if extracted in TTL_HOURS:
            volatility = extracted
            log_message(f"✅ AIfred-LLM Volatility: {volatility}")
            yield {"type": "debug", "message": f"✅ Volatility: {volatility}"}
        else:
            log_message(f"⚠️ Unknown volatility '{extracted}', fallback to DAILY")
            yield {"type": "debug", "message": "⚠️ Unknown volatility, fallback to DAILY"}
    else:
        log_message("⚠️ No volatility tag found, fallback to DAILY")
        yield {"type": "debug", "message": "⚠️ No volatility tag, fallback to DAILY"}

    # Remove volatility tag from answer before displaying to user
    ai_text = re.sub(r'<volatility>.*?</volatility>', '', ai_text, flags=re.IGNORECASE | re.DOTALL).strip()

    # Create clean version without <think> block for cache storage
    # The thinking process is unnecessary overhead in the cache
    ai_text_for_cache = re.sub(r'<think>.*?</think>', '', ai_text, flags=re.IGNORECASE | re.DOTALL).strip()

    # Separator after LLM response block (end of unit)
    from ..logging_utils import console_separator, CONSOLE_SEPARATOR
    console_separator()
    yield {"type": "debug", "message": CONSOLE_SEPARATOR}

    # Format thinking process
    thinking_html = format_thinking_process(ai_text, model_name=model_choice, inference_time=inference_time, tokens_per_sec=tokens_per_sec)

    # Build debug accordion with query reasoning
    ai_response_complete = build_debug_accordion(
        query_reasoning=query_reasoning,
        ai_text=ai_text,
        automatik_model=automatik_model,
        main_model=model_choice,
        query_time=query_opt_time,
        final_time=inference_time
    )

    # Update history
    total_time = time.time() - agent_start
    ttft_str = f"TTFT: {format_number(ttft, 2)}s    " if ttft is not None else ""
    metadata = format_metadata(f"{ttft_str}Inference: {format_number(inference_time, 1)}s    {format_number(tokens_per_sec, 1)} tok/s    Source: Web Research ({model_choice})")

    if stt_time > 0:
        user_metadata = format_metadata(f"STT: {format_number(stt_time, 1)}s    Agent: {mode}    {len(scraped_only)} sources")
        user_with_time = f"{user_text}  \n{user_metadata}"
    else:
        user_metadata = format_metadata(f"Agent: {mode}    {len(scraped_only)} sources")
        user_with_time = f"{user_text}  \n{user_metadata}"

    # Add to histories (parallel: chat_history + llm_history)
    history.append((user_with_time, f"{thinking_html}\n\n{metadata}"))
    # llm_history: ai_text is raw LLM output, strip thinking blocks
    ai_text_clean = strip_thinking_blocks(ai_text) if ai_text else ""
    if ai_text_clean:
        llm_history.append({"role": "assistant", "content": f"[AIFRED]: {ai_text_clean}"})

    log_message(f"✅ AI response generated ({len(ai_text)} chars, inference: {format_number(inference_time, 1)}s)")

    # ============================================================
    # Vector DB Auto-Learning: Save successful research to cache with TTL
    # ============================================================
    try:
        from ..vector_cache import get_cache

        # Main LLM already determined volatility via <volatility> tag
        # Save to cache with TTL-based expiry
        cache = get_cache()
        result = await cache.add(
            query=user_text,
            answer=ai_text_for_cache,  # Clean version without <think> block
            sources=scraped_only,
            failed_sources=failed_sources,  # URLs that couldn't be scraped
            metadata={
                'mode': mode,
                'volatility': volatility  # Main-LLM decision
            }
        )

        if result.get('success'):
            if result.get('duplicate'):
                log_message("⚠️ Vector Cache: Duplicate detected, skipped")
                yield {"type": "debug", "message": "⚠️ Cache duplicate - not saved"}
            else:
                ttl_hours = TTL_HOURS.get(volatility)
                if ttl_hours:
                    ttl_formatted = format_ttl_hours(ttl_hours)
                    log_message(f"💾 Vector Cache: Saved with {volatility} TTL ({ttl_formatted}, {result.get('total_entries')} entries)")
                    yield {"type": "debug", "message": f"💾 Saved to Cache (TTL: {ttl_formatted})"}
                else:
                    log_message(f"💾 Vector Cache: Saved as PERMANENT ({result.get('total_entries')} entries)")
                    yield {"type": "debug", "message": "💾 Saved to Cache (PERMANENT)"}
        else:
            log_message(f"⚠️ Vector Cache add failed: {result.get('error')}")

    except Exception as e:
        log_message(f"⚠️ Vector Cache auto-learning failed: {e}")

    # Subtle VRAM info (only when content fits)
    if vram_warning and input_tokens <= final_num_ctx:
        vram_diff = vram_warning["vram_diff"]
        potential_tokens = vram_warning.get("potential_tokens")

        info_msg = f"ℹ️ VRAM info: {vram_diff:+.0f}MB additional memory detected"

        if potential_tokens:
            info_msg += (
                f" (Context potential: {format_number(vram_warning['current_tokens'])} → "
                f"~{format_number(potential_tokens)} tokens). "
            )
        else:
            info_msg += ". "

        info_msg += "For extended capacity: Control Panel → vLLM Restart"

        log_message(info_msg)
        yield {"type": "debug", "message": info_msg}

    # Note: Separator already emitted after volatility detection (line ~310)
    # No second separator needed here - avoids double separator in Multi-Agent mode

    log_message(f"✅ Agent done: {format_number(total_time, 1)}s total, {len(ai_text)} chars")
    log_message("=" * 60)

    # Clear progress
    yield {"type": "progress", "clear": True}

    # Final result
    yield {"type": "result", "data": (ai_response_complete, history, inference_time)}
