"""
Own Knowledge Handler - Zentrale Funktion für LLM-Antworten ohne Web-Recherche.

Diese Funktion wird aufgerufen von:
- state.py: research_mode == "none"
- state.py: research_mode in ["quick", "deep"] wenn LLM web=false entscheidet
- conversation_handler.py: Automatik-Modus wenn LLM web=false entscheidet

Yields Dict-Messages die vom Aufrufer geroutet werden:
- {"type": "debug", "message": str}
- {"type": "content", "text": str}
- {"type": "progress", ...}
- {"type": "result", "data": {...}}
"""

import time
from typing import AsyncIterator, Dict, List, Optional, Any

from .llm_client import LLMClient
from .formatting import format_number, format_thinking_process
from .prompt_loader import get_aifred_direct_prompt, get_aifred_system_minimal
from .context_manager import estimate_tokens, calculate_dynamic_num_ctx, strip_thinking_blocks
from .model_vram_cache import get_ollama_calibration, get_rope_factor_for_model
from .intent_detector import get_temperature_for_intent, get_temperature_label
from .logging_utils import log_message
from .message_builder import inject_rag_context
from .research.context_utils import get_agent_num_ctx

# Import backend types
from ..backends import LLMOptions


async def handle_own_knowledge(
    user_text: str,
    model_choice: str,
    llm_history: List[Dict[str, str]],
    detected_intent: str,
    detected_language: str,
    temperature_mode: str,
    temperature: float,
    backend_type: str,
    backend_url: Optional[str],
    enable_thinking: bool,
    state: Optional[Any] = None,
    use_direct_prompt: bool = False,
    multimodal_content: Optional[List[Dict]] = None,
    rag_context: Optional[str] = None,
    vision_json_context: Optional[Dict] = None,
    stt_time: float = 0.0,
    cloud_provider_label: Optional[str] = None,
    num_ctx_manual_enabled: bool = False,
    num_ctx_manual_value: Optional[int] = None,
) -> AsyncIterator[Dict]:
    """
    Generiert eine LLM-Antwort basierend auf eigenem Wissen (ohne Web-Recherche).

    Args:
        user_text: Die User-Nachricht
        model_choice: Model ID (z.B. "qwen3:4b")
        llm_history: LLM History (Liste von {"role": ..., "content": ...})
        detected_intent: Intent für Temperature-Bestimmung (z.B. "FAKTISCH")
        detected_language: Sprache für Prompts ("de" oder "en")
        temperature_mode: "auto" oder "manual"
        temperature: Temperature-Wert (nur bei manual relevant)
        backend_type: Backend-Typ ("ollama", "vllm", "tabbyapi", "koboldcpp", "cloud_api")
        backend_url: Backend-URL
        enable_thinking: Thinking Mode aktiviert?
        state: AIState Objekt für num_ctx Lookup (optional)
        use_direct_prompt: True wenn User AIfred direkt angesprochen hat
        multimodal_content: Multimodal Content für Bilder (optional)
        rag_context: RAG-Kontext zum Injizieren (optional)
        vision_json_context: Vision JSON Kontext (optional)
        stt_time: Speech-to-Text Zeit für Metadata (optional)
        cloud_provider_label: Cloud Provider Label für Debug-Ausgabe (optional)
        num_ctx_manual_enabled: Manuelles num_ctx aktiviert?
        num_ctx_manual_value: Manueller num_ctx Wert

    Yields:
        Dict mit type und payload:
        - {"type": "debug", "message": str}
        - {"type": "content", "text": str}
        - {"type": "progress", "phase": str} oder {"type": "progress", "clear": True}
        - {"type": "result", "data": {...}} - Finale Ergebnisse
    """
    yield {"type": "debug", "message": "🧠 Own knowledge (no web search)"}
    yield {"type": "progress", "phase": "llm"}

    # Build messages using centralized function (v2.16.0+)
    # Uses perspective="aifred" to correctly assign roles for all agents
    from .message_builder import build_messages_from_llm_history

    if multimodal_content is not None:
        # Multimodal: Build without user text, then append multimodal content
        messages = build_messages_from_llm_history(
            llm_history,
            perspective="aifred",
            detected_language=detected_language
        )
        messages.append({"role": "user", "content": multimodal_content})
        log_message("📷 Multimodal content injected into user message")
    else:
        # Standard: Include user text directly
        messages = build_messages_from_llm_history(
            llm_history,
            current_user_text=user_text,
            perspective="aifred",
            detected_language=detected_language
        )

    # Inject system prompt (direct or minimal based on addressing)
    if use_direct_prompt:
        system_prompt = get_aifred_direct_prompt(lang=detected_language)
    else:
        system_prompt = get_aifred_system_minimal(lang=detected_language)
    messages.insert(0, {"role": "system", "content": system_prompt})

    # Inject RAG context if available
    if rag_context:
        inject_rag_context(messages, rag_context)
        log_message(f"💡 RAG context injected into system prompt ({len(rag_context)} chars)")
        yield {"type": "debug", "message": f"💡 RAG context injected ({len(rag_context)} chars)"}

    # Inject Vision JSON context if available
    if vision_json_context:
        from .rag_context_builder import inject_vision_json_context
        inject_vision_json_context(messages, vision_json_context)
        log_message(f"📷 Vision JSON injected ({len(str(vision_json_context))} chars)")

    # Create LLM client
    llm_client = LLMClient(backend_type=backend_type, base_url=backend_url)

    try:
        # Temperature decision
        if temperature_mode == 'manual':
            final_temperature = temperature
            yield {"type": "debug", "message": f"🌡️ Temperature: {format_number(final_temperature, 1)} (manual)"}
        else:
            final_temperature = get_temperature_for_intent(detected_intent)
            temp_label = get_temperature_label(detected_intent)
            yield {"type": "debug", "message": f"🌡️ Temperature: {format_number(final_temperature, 1)} (auto, {temp_label})"}

        # Calculate num_ctx
        if num_ctx_manual_enabled and num_ctx_manual_value:
            final_num_ctx = num_ctx_manual_value
            yield {"type": "debug", "message": f"🔧 num_ctx: {final_num_ctx:,} (manual)"}
        elif state:
            # Use centralized function with state
            final_num_ctx, ctx_source = get_agent_num_ctx("aifred", state, model_choice)
            yield {"type": "debug", "message": f"🎯 num_ctx: {format_number(final_num_ctx)} ({ctx_source})"}
        else:
            # Calculate from VRAM cache
            rope_factor = get_rope_factor_for_model(model_choice)
            final_num_ctx = get_ollama_calibration(model_choice, rope_factor)
            if final_num_ctx:
                yield {"type": "debug", "message": f"🎯 num_ctx: {final_num_ctx:,} (from VRAM cache)"}
            else:
                # Dynamic calculation
                final_num_ctx, _ = await calculate_dynamic_num_ctx(
                    llm_client, model_choice, [], None,
                    enable_vram_limit=True
                )
                yield {"type": "debug", "message": f"🎯 num_ctx: {final_num_ctx:,} (calculated)"}

        # Count input tokens
        input_tokens = estimate_tokens(messages, model_name=model_choice)

        # Get model context limit for display
        model_limit, _ = await llm_client.get_model_context_limit(model_choice)

        # Show context info
        yield {"type": "debug", "message": f"📊 AIfred: {format_number(input_tokens)} / {format_number(final_num_ctx)} tokens (max: {format_number(model_limit)})"}

        # Build LLM options
        llm_options = LLMOptions(
            temperature=final_temperature,
            num_ctx=final_num_ctx,
            enable_thinking=enable_thinking
        )

        # Console: LLM starts
        if backend_type == "cloud_api" and cloud_provider_label:
            backend_label = f"☁️ {cloud_provider_label}"
        else:
            backend_label = backend_type.capitalize()
        yield {"type": "debug", "message": f"🎩 AIfred-LLM starting: {model_choice} [{backend_label}]"}

        # Log RAW messages for debugging (v2.16.0+)
        from .logging_utils import log_raw_messages
        log_raw_messages("AIfred (Own Knowledge)", messages, estimate_tokens)

        # Stream response
        log_message(f"🔬 DEBUG: Starting inference at {time.time()}")
        inference_start = time.time()
        full_response = ""
        ttft = None
        first_token_received = False
        tokens_generated = 0
        tokens_prompt = 0

        async for chunk in llm_client.chat_stream(
            model=model_choice,
            messages=messages,
            options=llm_options
        ):
            if chunk["type"] == "content":
                # Measure TTFT
                if not first_token_received:
                    ttft = time.time() - inference_start
                    first_token_received = True
                    yield {"type": "debug", "message": f"⚡ TTFT: {format_number(ttft, 2)}s"}

                # Stream content
                full_response += chunk["text"]
                yield {"type": "content", "text": chunk["text"]}

            elif chunk["type"] == "done":
                metrics = chunk.get("metrics", {})
                tokens_generated = metrics.get("tokens_generated", 0)
                tokens_prompt = metrics.get("tokens_prompt", 0)

        inference_time = time.time() - inference_start

        # Console: LLM finished
        tokens_per_sec = tokens_generated / inference_time if inference_time > 0 else 0
        if backend_type == "cloud_api" and tokens_prompt > 0:
            total_tokens = tokens_prompt + tokens_generated
            yield {"type": "debug", "message": f"✅ AIfred-LLM done ({format_number(inference_time, 1)}s, {format_number(tokens_generated)} out / {format_number(total_tokens)} total, {format_number(tokens_per_sec, 1)} tok/s)"}
        else:
            yield {"type": "debug", "message": f"✅ AIfred-LLM done ({format_number(inference_time, 1)}s, {format_number(tokens_generated)} tokens, {format_number(tokens_per_sec, 1)} tok/s)"}

        # Format thinking tags
        thinking_html = format_thinking_process(
            full_response,
            model_name=model_choice,
            inference_time=inference_time,
            tokens_per_sec=tokens_per_sec
        )

        # Strip thinking blocks for clean response
        response_clean = strip_thinking_blocks(full_response) if full_response else ""

        # Clear progress
        yield {"type": "progress", "clear": True}

        # Yield final result with all data needed by caller
        yield {
            "type": "result",
            "data": {
                "response_raw": full_response,
                "response_clean": response_clean,
                "response_html": thinking_html,
                "inference_time": inference_time,
                "tokens_per_sec": tokens_per_sec,
                "tokens_generated": tokens_generated,
                "ttft": ttft,
                "model_choice": model_choice,
                "stt_time": stt_time,
                "rag_context": rag_context,
                "final_temperature": final_temperature,
            }
        }

    finally:
        await llm_client.close()
