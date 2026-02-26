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

from typing import AsyncIterator, Dict, List, Optional, Any, cast

from .llm_client import LLMClient, build_llm_options, MessageType
from .timer import Timer
from .formatting import format_number, format_thinking_process, build_inference_metadata
from .prompt_loader import get_aifred_direct_prompt, get_aifred_system_minimal
from .context_manager import estimate_tokens, strip_thinking_blocks
from .intent_detector import get_temperature_for_intent, get_temperature_label
from .logging_utils import log_message
from .message_builder import inject_rag_context
from .research.context_utils import get_agent_num_ctx



async def handle_own_knowledge(
    user_text: str,
    model_choice: str,
    history: List,  # chat_history - will be updated and returned in result
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
    provider: Optional[str] = None,
    agent: str = "aifred",
    vision_prompt_key: str = "task",
) -> AsyncIterator[Dict]:
    """
    Generiert eine LLM-Antwort basierend auf eigenem Wissen (ohne Web-Recherche).

    Args:
        user_text: Die User-Nachricht
        model_choice: Model ID (z.B. "qwen3:4b")
        history: Chat History (wird aktualisiert und im Result zurückgegeben)
        llm_history: LLM History (Liste von {"role": ..., "content": ...})
        detected_intent: Intent für Temperature-Bestimmung (z.B. "FAKTISCH")
        detected_language: Sprache für Prompts ("de" oder "en")
        temperature_mode: "auto" oder "manual"
        temperature: Temperature-Wert (nur bei manual relevant)
        backend_type: Backend-Typ ("ollama", "vllm", "tabbyapi", "llamacpp", "cloud_api")
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

    messages: list[dict[str, Any]]
    if multimodal_content is not None:
        # Multimodal: Build without user text, then append multimodal content
        messages = list(build_messages_from_llm_history(
            llm_history,
            perspective="aifred",
            detected_language=detected_language
        ))
        messages.append({"role": "user", "content": multimodal_content})
        log_message("📷 Multimodal content injected into user message")
    else:
        # Standard: Include user text directly
        messages = list(build_messages_from_llm_history(
            llm_history,
            current_user_text=user_text,
            perspective="aifred",
            detected_language=detected_language
        ))

    # Inject system prompt (agent-aware: vision uses own prompt stack with toggles)
    if agent == "vision":
        from .prompt_loader import get_agent_system_prompt
        system_prompt = get_agent_system_prompt("vision", vision_prompt_key, lang=detected_language)
    elif use_direct_prompt:
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
        from .message_builder import inject_vision_json_context
        inject_vision_json_context(messages, vision_json_context)
        log_message(f"📷 Vision JSON injected ({len(str(vision_json_context))} chars)")

    # Create LLM client
    llm_client = LLMClient(backend_type=backend_type, base_url=backend_url, provider=provider)

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
            yield {"type": "debug", "message": f"🔧 Context: {final_num_ctx:,} (manual)"}
        else:
            # Use centralized SSOT: get_agent_num_ctx handles vision_num_ctx_enabled,
            # VRAM calibration cache, XTTS reservation and backend-specific logic.
            assert state is not None, "state required for num_ctx lookup"
            final_num_ctx, ctx_source = get_agent_num_ctx(agent, state, model_choice)
            yield {"type": "debug", "message": f"🎯 Context: {format_number(final_num_ctx)} ({ctx_source})"}

        # Count input tokens
        input_tokens = estimate_tokens(messages, model_name=model_choice)

        # Get native context limit for display (local read, no API call!)
        from .research.context_utils import get_model_native_context
        model_limit = get_model_native_context(model_choice, backend_type)

        # Show context info
        agent_label = agent.upper()
        yield {"type": "debug", "message": f"📊 {agent_label}: {format_number(input_tokens)} / {format_number(final_num_ctx)} tokens (max: {format_number(model_limit)})"}

        # Build LLM options via central builder (all sampling params from state).
        # VL ("vision" agent) uses AIfred's sampling params — no separate vision params in state.
        llm_agent = "aifred" if agent == "vision" else agent
        llm_options = build_llm_options(state, llm_agent, final_temperature, final_num_ctx)  # type: ignore[arg-type]
        # Override thinking for vision: build_llm_options uses llm_agent="aifred"
        # for sampling, but thinking must come from the actual agent's toggle.
        llm_options.enable_thinking = enable_thinking

        # Console: LLM starts (with MoE/Dense architecture info)
        from .gpu_utils import is_moe_model
        is_moe = is_moe_model(model_choice) if backend_type in ("ollama", "llamacpp") else False
        arch_label = "MoE" if is_moe else "Dense"
        yield {"type": "debug", "message": f"🎩 {agent_label}-LLM starting: {model_choice} ({arch_label})"}

        # Log RAW messages for debugging (v2.16.0+)
        from .logging_utils import log_raw_messages
        log_raw_messages(f"{agent_label} (Own Knowledge)", messages, estimate_tokens)

        # Stream response
        timer = Timer()
        log_message("🔬 DEBUG: Starting inference")
        full_response = ""
        ttft = None
        first_token_received = False
        tokens_generated = 0
        tokens_prompt = 0
        metrics: dict = {}

        async for chunk in llm_client.chat_stream(
            model=model_choice,
            messages=cast(list[MessageType], messages),
            options=llm_options
        ):
            if chunk["type"] == "content":
                # Measure TTFT
                if not first_token_received:
                    ttft = timer.elapsed()
                    first_token_received = True
                    yield {"type": "debug", "message": f"⚡ TTFT: {format_number(ttft, 2)}s"}

                # Stream content
                full_response += chunk["text"]
                yield {"type": "content", "text": chunk["text"]}

            elif chunk["type"] == "done":
                metrics = chunk.get("metrics", {})
                tokens_generated = metrics.get("tokens_generated", 0)
                tokens_prompt = metrics.get("tokens_prompt", 0)

        inference_time = timer.elapsed()
        tokens_per_sec = tokens_generated / inference_time if inference_time > 0 else 0

        # Strip thinking blocks and format for display
        response_clean = strip_thinking_blocks(full_response) if full_response else ""
        thinking_html = format_thinking_process(
            full_response,
            model_name=model_choice,
            inference_time=inference_time,
            tokens_per_sec=tokens_per_sec
        )

        # Update llm_history BEFORE calculating history_tokens
        # so "History: X tok" reflects the current conversation state (incl. AI response)
        if response_clean:
            llm_history.append({"role": "assistant", "content": f"[AIFRED]: {response_clean}"})

        # Centralized metadata (PP speed, debug log, chat bubble)
        from .context_manager import estimate_tokens_from_llm_history
        history_tokens = estimate_tokens_from_llm_history(llm_history)
        source_label = f"VL ({model_choice})" if agent == "vision" else f"Own Knowledge ({model_choice})"

        metadata_dict, metadata_display, debug_msg = build_inference_metadata(
            ttft=ttft,
            inference_time=inference_time,
            tokens_generated=tokens_generated,
            tokens_per_sec=tokens_per_sec,
            source=source_label,
            backend_metrics=metrics,
            tokens_prompt=tokens_prompt,
            history_tokens=history_tokens,
            backend_type=backend_type,
        )
        yield {"type": "debug", "message": debug_msg}

        # Update chat_history (UI display with thinking + metadata)
        import datetime
        ai_with_source = f"{thinking_html}\n\n{metadata_display}"

        history.append({
            "role": "assistant",
            "content": ai_with_source,
            "agent": "aifred",
            "mode": "own_knowledge",
            "round_num": 0,
            "metadata": metadata_dict,
            "timestamp": datetime.datetime.now().isoformat()
        })

        # Clear progress
        yield {"type": "progress", "clear": True}

        # Final result - unified Dict format
        yield {
            "type": "result",
            "data": {
                "response_clean": response_clean,
                "response_html": thinking_html,
                "history": history,
                "llm_history": llm_history,  # Include updated llm_history
                "inference_time": inference_time,
                "tokens_per_sec": tokens_per_sec,
                "ttft": ttft,
                "model_choice": model_choice,
                "failed_sources": [],
            }
        }

    finally:
        await llm_client.close()
