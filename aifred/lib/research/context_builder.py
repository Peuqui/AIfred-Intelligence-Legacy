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
from ..prompt_loader import load_prompt
from ..context_manager import calculate_dynamic_num_ctx, estimate_tokens
from ..message_builder import build_messages_from_history
from ..formatting import format_thinking_process, build_debug_accordion, format_metadata, format_number
from ..logging_utils import log_message
from ..config import (
    CHARS_PER_TOKEN,
    TTL_HOURS,
    DYNAMIC_NUM_PREDICT_SAFETY_MARGIN,
    DYNAMIC_NUM_PREDICT_MINIMUM
)
from ..vector_cache import format_ttl_hours
from ..intent_detector import detect_query_intent, get_temperature_for_intent, get_temperature_label
from .context_utils import get_rag_context_budget
from ..streaming_utils import stream_llm_response, log_llm_completion


async def build_and_generate_response(
    user_text: str,
    scraped_results: List[Dict],
    tool_results: List[Dict],
    failed_sources: List[Dict],
    history: List[tuple],
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
    num_ctx_mode: str = "auto_vram",
    num_ctx_manual: int = 16384
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

    Yields:
        Dict: Debug messages, content chunks, final result
    """
    # Filter: Only successfully scraped sources
    scraped_only = [r for r in tool_results if 'word_count' in r and r['word_count'] > 0]

    # DEBUG logging (can be removed in production)
    for i, result in enumerate(tool_results, 1):
        if result.get('success'):
            log_message(f"  Quelle {i}: {result.get('word_count', 0)} Wörter von {result.get('url', 'N/A')[:50]}")

    if scraped_only:
        for i, src in enumerate(scraped_only[:3], 1):
            content_preview = src.get('content', '')[:200].replace('\n', ' ')
            log_message(f"  📄 Quelle {i} Preview: {content_preview}...")

    # ============================================================
    # VRAM-AWARE Context Building (via context_utils.py)
    # Berechne max verfügbaren Context BEVOR build_context() läuft
    # ============================================================
    max_rag_tokens, actual_reserve, max_ctx = await get_rag_context_budget(
        llm_client=llm_client,
        model_choice=model_choice,
        num_ctx_mode=num_ctx_mode,
        num_ctx_manual=num_ctx_manual,
        history=history,
        user_text=user_text
    )

    # 6. Context mit dynamischem Limit bauen
    context = build_context(user_text, scraped_only, max_context_tokens=max_rag_tokens)

    # Estimate tokens
    est_tokens = len(context) // CHARS_PER_TOKEN
    log_message(f"📊 Context gebaut: ~{format_number(est_tokens)} tok")

    # Show context preview
    if len(context) > 800:
        preview = context[:800] + "..."
        log_message(f"📝 Context Preview (erste 800 Zeichen):\n{preview}")

    # Spracherkennung für User-Text
    from ..prompt_loader import detect_language
    detected_user_language = detect_language(user_text)

    # System prompt (timestamp injected automatically by load_prompt)
    system_prompt = load_prompt(
        'system_rag',
        lang=detected_user_language,
        user_text=user_text,
        context=context
    )

    yield {"type": "debug", "message": "✅ System-Prompt erstellt"}

    # Build messages with history
    messages = build_messages_from_history(history, user_text)

    # Insert system prompt as first message
    messages.insert(0, {"role": "system", "content": system_prompt})

    # DEBUG: Show message sizes
    for i, msg in enumerate(messages):
        role = msg['role']
        content_len = len(msg['content'])
        log_message(f"  Message {i+1} ({role}): {content_len} Zeichen")

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
        yield {"type": "debug", "message": f"🔧 Manual num_ctx: {format_number(num_ctx_manual)} (VRAM calculation skipped)"}
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

    # Get model max context for compact display
    model_limit, _ = await llm_client.get_model_context_limit(model_choice)

    # Show compact context info (like Automatik-LLM)
    yield {"type": "debug", "message": f"📊 Haupt-LLM: {format_number(input_tokens)} / {format_number(final_num_ctx)} tok (Model Max: {format_number(model_limit)} tok)"}

    # VRAM Warning: Check if VRAM change detected AND content doesn't fit
    vram_warning = llm_options.get('_vram_warning') if llm_options else None
    if vram_warning and input_tokens > final_num_ctx:
        # Content doesn't fit AND more VRAM available → Show orange blocking warning
        vram_diff = vram_warning["vram_diff"]
        potential_tokens = vram_warning.get("potential_tokens")

        warning_msg = (
            f"⚠️ VRAM-Änderung erkannt: {vram_diff:+.0f}MB zusätzlicher Speicher verfügbar!\n\n"
            f"💡 **Empfehlung:** Gehe zu **Systemsteuerung → vLLM Neustart**, um das "
            f"erweiterte Context-Fenster zu nutzen"
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
            f"❌ Eingabe zu groß: {format_number(input_tokens)} Tokens > "
            f"Context-Limit {format_number(final_num_ctx)} Tokens\n"
            f"   Bitte kürze deine Anfrage oder aktiviere 'Manual Context' mit höherem Wert."
        )
        # Only yield - UI will handle logging via add_debug() which calls log_message()
        yield {"type": "debug", "message": error_msg}

        # Reset UI progress state before returning error
        yield {"type": "progress", "phase": "idle"}
        yield {"type": "progress", "step": "ready"}

        yield {"type": "error", "message": error_msg}
        return

    # Temperature
    if temperature_mode == 'manual':
        final_temperature = temperature
        yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (manual)"}
    else:
        # Auto: Intent-Detection für RAG-Recherche (faktisch/gemischt/kreativ)
        rag_intent = await detect_query_intent(
            user_query=user_text,
            automatik_model=automatik_model,
            llm_client=automatik_llm_client,
            llm_options=llm_options
        )
        final_temperature = get_temperature_for_intent(rag_intent)
        temp_label = get_temperature_label(rag_intent)
        log_message(f"🌡️ RAG Temperature: {final_temperature} (Intent: {rag_intent})")
        yield {"type": "debug", "message": f"🌡️ Temperature: {final_temperature} (auto, {temp_label})"}

    # LLM Inference
    yield {"type": "debug", "message": f"🤖 Haupt-LLM startet: {model_choice}"}
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

    # Log completion
    yield log_llm_completion(inference_time, metrics)

    # Extract volatility tag from LLM response
    volatility = "DAILY"  # Default fallback (safer than PERMANENT to avoid cache bloat)
    volatility_match = re.search(r'<volatility>(.*?)</volatility>', ai_text, re.IGNORECASE | re.DOTALL)

    if volatility_match:
        extracted = volatility_match.group(1).strip().upper()
        if extracted in TTL_HOURS:
            volatility = extracted
            log_message(f"✅ Haupt-LLM Volatility: {volatility}")
            yield {"type": "debug", "message": f"✅ Volatility: {volatility}"}
        else:
            log_message(f"⚠️ Unbekannte Volatility '{extracted}', fallback zu DAILY")
            yield {"type": "debug", "message": "⚠️ Unbekannte Volatility, fallback zu DAILY"}
    else:
        log_message("⚠️ Kein Volatility-Tag gefunden, fallback zu DAILY")
        yield {"type": "debug", "message": "⚠️ Kein Volatility-Tag, fallback zu DAILY"}

    # Remove volatility tag from answer before displaying to user
    ai_text = re.sub(r'<volatility>.*?</volatility>', '', ai_text, flags=re.IGNORECASE | re.DOTALL).strip()

    # Create clean version without <think> block for cache storage
    # The thinking process is unnecessary overhead in the cache
    ai_text_for_cache = re.sub(r'<think>.*?</think>', '', ai_text, flags=re.IGNORECASE | re.DOTALL).strip()

    # Separator nach LLM-Antwort-Block (Ende der Einheit)
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
    metadata = format_metadata(f"Inferenz: {format_number(inference_time, 1)}s    {format_number(tokens_per_sec, 1)} tok/s    Quelle: Web-Recherche")

    if stt_time > 0:
        user_metadata = format_metadata(f"STT: {format_number(stt_time, 1)}s    Agent: {mode}    {len(scraped_only)} Quellen")
        user_with_time = f"{user_text}  \n{user_metadata}"
    else:
        user_metadata = format_metadata(f"Agent: {mode}    {len(scraped_only)} Quellen")
        user_with_time = f"{user_text}  \n{user_metadata}"

    history.append((user_with_time, thinking_html + "  \n" + metadata))

    log_message(f"✅ AI-Antwort generiert ({len(ai_text)} Zeichen, Inferenz: {format_number(inference_time, 1)}s)")

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
                'volatility': volatility  # Haupt-LLM decision
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

    # Dezente VRAM-Info (nur wenn Content gepasst hat)
    if vram_warning and input_tokens <= final_num_ctx:
        vram_diff = vram_warning["vram_diff"]
        potential_tokens = vram_warning.get("potential_tokens")

        info_msg = f"ℹ️ VRAM-Info: {vram_diff:+.0f}MB zusätzlicher Speicher erkannt"

        if potential_tokens:
            info_msg += (
                f" (Context-Potential: {format_number(vram_warning['current_tokens'])} → "
                f"~{format_number(potential_tokens)} Tokens). "
            )
        else:
            info_msg += ". "

        info_msg += "Für erweiterte Kapazität: Systemsteuerung → vLLM Neustart"

        log_message(info_msg)
        yield {"type": "debug", "message": info_msg}

    # Separator nach Cache-Decision-Block (Ende der Einheit)
    from ..logging_utils import console_separator, CONSOLE_SEPARATOR
    console_separator()
    yield {"type": "debug", "message": CONSOLE_SEPARATOR}

    log_message(f"✅ Agent fertig: {format_number(total_time, 1)}s gesamt, {len(ai_text)} Zeichen")
    log_message("=" * 60)

    # Clear progress
    yield {"type": "progress", "clear": True}

    # Final result
    yield {"type": "result", "data": (ai_response_complete, history, inference_time)}
