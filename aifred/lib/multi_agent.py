"""
Multi-Agent Debate System
AIfred (Main) + Sokrates (Critic)

Implements multi-agent debate patterns for improved answer quality:
- User-as-Judge: AIfred answers, Sokrates critiques, user decides
- Auto-Consensus: Iterative refinement until LGTM or max rounds
- Devil's Advocate: Pro and Contra arguments for balanced analysis

This module contains the core Multi-Agent logic extracted from state.py.
The functions work with async generators for streaming UI updates.
"""

import asyncio
from typing import TYPE_CHECKING, Any, AsyncGenerator, Optional

# Imports for the functions (same as original state.py methods)
from .llm_client import LLMClient, build_llm_options
from .timer import Timer
from .formatting import format_number, format_thinking_process, build_inference_metadata
from .message_builder import build_messages_from_llm_history
from .i18n import t
from .context_manager import (
    estimate_tokens,
    strip_thinking_blocks,
    summarize_history_if_needed,
    get_largest_compression_model,
    _last_vram_limit_cache
)
from .prompt_loader import (
    get_aifred_system_minimal,
    get_sokrates_system_minimal,
    get_sokrates_direct_prompt,
    get_sokrates_critic_prompt,
    get_sokrates_devils_advocate_prompt,
    get_sokrates_refinement_prompt,
    get_sokrates_tribunal_prompt,
    get_aifred_defense_prompt,
    get_salomo_system_minimal,
    get_salomo_direct_prompt,
    get_salomo_mediator_prompt,
    get_salomo_judge_prompt,
)
from .logging_utils import log_message, log_raw_messages, console_separator
from ..backends.base import LLMOptions

if TYPE_CHECKING:
    from ..state import AIState


# ============================================================
# RETRY HELPER FOR 500 ERRORS
# ============================================================

async def _chat_stream_with_retry(
    llm_client: LLMClient,
    model: str,
    messages: list,
    options: LLMOptions,
    agent_name: str,
    state: 'AIState',
    retry_delay: float = 2.0,
    max_retries: int = 1
) -> AsyncGenerator[dict, None]:
    """
    Wrapper around llm_client.chat_stream() with retry logic for 500 errors.

    On 500 error: Logs the error, waits retry_delay seconds, retries once.
    If still fails, re-raises the error.
    """
    attempt = 0
    last_error = None

    while attempt <= max_retries:
        try:
            async for chunk in llm_client.chat_stream(model, messages, options):
                yield chunk
            return  # Success - exit the retry loop
        except Exception as e:
            error_str = str(e)
            is_500_error = "500" in error_str and ("Internal Server Error" in error_str or "Server error" in error_str)

            if is_500_error and attempt < max_retries:
                # Log the error (visible in console and debug)
                log_message(f"⚠️ {agent_name}: 500 Error - retrying in {retry_delay}s...")
                state.add_debug(f"⚠️ {agent_name}: 500 Error (attempt {attempt + 1}/{max_retries + 1}) - {error_str}")

                # Wait and retry
                await asyncio.sleep(retry_delay)
                attempt += 1
                last_error = e
            else:
                # Not a 500 error or max retries reached - re-raise
                raise

    # Should not reach here, but if we do, raise the last error
    if last_error:
        raise last_error


def _estimate_prompt_tokens(prompt: str) -> int:
    """Estimate tokens in a prompt (3.5 chars/token for German/mixed text)."""
    return int(len(prompt) / 3.5) if prompt else 0


# ============================================================
# CONSENSUS VOTING HELPERS
# ============================================================

def count_lgtm_votes(alfred_text: str, sokrates_text: str, salomo_text: str) -> dict:
    """Count [LGTM] votes from all agents, ignoring if [WEITER] is present.

    [WEITER] overrides [LGTM] to handle negation cases like:
    "Das ist noch kein LGTM" -> Would otherwise false-positive on "LGTM"

    Returns:
        dict: {"alfred": bool, "sokrates": bool, "salomo": bool}
    """
    votes = {"alfred": False, "sokrates": False, "salomo": False}

    for name, text in [("alfred", alfred_text), ("sokrates", sokrates_text), ("salomo", salomo_text)]:
        content = strip_thinking_blocks(text).strip().upper()
        # [WEITER] overrides [LGTM] (for negation case)
        if "[WEITER]" in content:
            votes[name] = False
        elif "[LGTM]" in content:
            votes[name] = True

    return votes


def check_consensus(votes: dict, consensus_type: str) -> bool:
    """Check if consensus is reached based on type.

    Args:
        votes: dict with agent names as keys and bool votes as values
        consensus_type: "majority" (2/3) or "unanimous" (3/3)

    Returns:
        bool: True if consensus reached
    """
    lgtm_count = sum(votes.values())
    if consensus_type == "unanimous":
        return bool(lgtm_count == 3)  # All must agree
    else:  # majority
        return bool(lgtm_count >= 2)  # 2/3 is enough


def format_votes_debug(votes: dict, round_num: int) -> str:
    """Format votes for debug output.

    Args:
        votes: dict with agent names as keys and bool votes as values
        round_num: Current round number

    Returns:
        str: Formatted debug string
    """
    lgtm_count = sum(votes.values())
    alfred_vote = "✅" if votes.get("alfred", False) else "❌"
    sokrates_vote = "✅" if votes.get("sokrates", False) else "❌"
    salomo_vote = "✅" if votes.get("salomo", False) else "❌"

    return f"🗳️ Votes R{format_number(round_num)}: AIfred {alfred_vote}, Sokrates {sokrates_vote}, Salomo {salomo_vote} ({format_number(lgtm_count)}/3)"


def parse_pro_contra(analysis: str) -> tuple[str, str]:
    """Parse Pro and Contra sections from Sokrates' analysis.

    Standalone function that can be imported and used directly.
    """
    pro_args = ""
    contra_args = ""

    lower_analysis = analysis.lower()

    # Find Pro section
    pro_markers = ["## pro", "**pro", "pro:", "pro-argumente:", "pro arguments:"]
    contra_markers = ["## contra", "**contra", "contra:", "contra-argumente:", "contra arguments:"]

    pro_start = -1
    contra_start = -1

    for marker in pro_markers:
        idx = lower_analysis.find(marker)
        if idx != -1 and (pro_start == -1 or idx < pro_start):
            pro_start = idx

    for marker in contra_markers:
        idx = lower_analysis.find(marker)
        if idx != -1 and (contra_start == -1 or idx < contra_start):
            contra_start = idx

    if pro_start != -1 and contra_start != -1:
        if pro_start < contra_start:
            pro_args = analysis[pro_start:contra_start].strip()
            contra_args = analysis[contra_start:].strip()
        else:
            contra_args = analysis[contra_start:pro_start].strip()
            pro_args = analysis[pro_start:].strip()
    elif pro_start != -1:
        pro_args = analysis[pro_start:].strip()
    elif contra_start != -1:
        contra_args = analysis[contra_start:].strip()
    else:
        # No clear sections - return full analysis as pro
        pro_args = analysis.strip()

    return pro_args, contra_args


# ============================================================
# STREAMING HELPERS
# ============================================================

async def _stream_sokrates_to_history(
    state: 'AIState',
    llm_client: LLMClient,
    model: str,
    messages: list,
    options: LLMOptions,
) -> AsyncGenerator[dict[str, Any] | None, None]:
    """
    Stream Sokrates response into current_ai_response (unified streaming).

    Performance-optimized: Does NOT update chat_history during streaming.
    Only updates state.current_ai_response which is shown in unified streaming_box.
    Caller is responsible for appending final result to chat_history.
    """
    full_response = ""
    token_count = 0
    timer = Timer()
    ttft = 0.0
    first_token = False

    # Set current agent for UI styling
    state.current_agent = "sokrates"
    state.current_ai_response = ""

    # Initialize streaming TTS for Sokrates
    if state.enable_tts and state.tts_autoplay and state.tts_streaming_enabled:
        state._init_streaming_tts(agent="sokrates")

    async for chunk in _chat_stream_with_retry(llm_client, model, messages, options, "Sokrates", state):
        if chunk["type"] == "content":
            if not first_token:
                ttft = timer.elapsed()
                log_message(f"⚡ Sokrates TTFT: {format_number(ttft, 2)}s")
                state.add_debug(f"⚡ TTFT: {format_number(ttft, 2)}s")
                first_token = True

            full_response += chunk["text"]
            token_count += 1

            state.stream_text_to_ui(chunk["text"])
            yield None

        elif chunk["type"] == "done":
            metrics = chunk.get("metrics", {})
            token_count = metrics.get("tokens_generated", token_count)

    # Finalize streaming TTS: send any remaining text in buffer
    audio_urls: list[str] = []
    if state.enable_tts and state.tts_autoplay and state.tts_streaming_enabled:
        audio_urls = await state._finalize_streaming_tts()

    # Centralized metadata (PP speed, debug log, chat bubble)
    inference_time = timer.elapsed()
    tokens_per_sec = token_count / inference_time if inference_time > 0 else 0

    metadata_dict, metadata_display, debug_msg = build_inference_metadata(
        ttft=ttft,
        inference_time=inference_time,
        tokens_generated=token_count,
        tokens_per_sec=tokens_per_sec,
        source=f"Sokrates ({model})",
        backend_metrics=metrics,
        tokens_prompt=metrics.get("tokens_prompt", 0),
        agent_label="Sokrates",
        response_chars=len(full_response),
    )
    state.add_debug(debug_msg)
    if audio_urls:
        log_message(f"🔊 Sokrates: {len(audio_urls)} audio URLs collected for message")

    # DUAL-HISTORY: Sync Sokrates response to llm_history (SSoT)
    state._sync_to_llm_history("sokrates", full_response)

    # Clear streaming state (cleanup)
    state.current_ai_response = ""
    state.current_agent = ""

    # RETURN result as final yield (dict = result, None = UI update)
    yield {
        "text": full_response,
        "metadata_display": metadata_display,
        "metadata_dict": metadata_dict,
        "audio_urls": audio_urls
    }


async def _stream_alfred_refinement(
    state: 'AIState',
    llm_client: LLMClient,
    model: str,
    messages: list,
    options: LLMOptions,
) -> AsyncGenerator[dict[str, Any] | None, None]:
    """
    Stream AIfred's refined answer into current_ai_response (unified streaming).

    Performance-optimized: Does NOT update chat_history during streaming.
    Only updates state.current_ai_response which is shown in unified streaming_box.
    Caller is responsible for appending final result to chat_history.
    """
    # Set current agent for UI styling
    state.current_agent = "aifred"
    state.current_ai_response = ""

    # Initialize streaming TTS for AIfred Refinement
    if state.enable_tts and state.tts_autoplay and state.tts_streaming_enabled:
        state._init_streaming_tts(agent="aifred")

    full_response = ""
    token_count = 0
    timer = Timer()
    ttft = 0.0
    first_token = False

    async for chunk in _chat_stream_with_retry(llm_client, model, messages, options, "AIfred Refinement", state):
        if chunk["type"] == "content":
            if not first_token:
                ttft = timer.elapsed()
                log_message(f"⚡ AIfred Refinement TTFT: {format_number(ttft, 2)}s")
                state.add_debug(f"⚡ TTFT: {format_number(ttft, 2)}s")
                first_token = True
            full_response += chunk["text"]
            token_count += 1

            state.stream_text_to_ui(chunk["text"])
            yield None

        elif chunk["type"] == "done":
            metrics = chunk.get("metrics", {})
            token_count = metrics.get("tokens_generated", token_count)

    # Finalize streaming TTS: send any remaining text in buffer
    audio_urls: list[str] = []
    if state.enable_tts and state.tts_autoplay and state.tts_streaming_enabled:
        audio_urls = await state._finalize_streaming_tts()

    # Centralized metadata (PP speed, debug log, chat bubble)
    inference_time = timer.elapsed()
    tokens_per_sec = token_count / inference_time if inference_time > 0 else 0

    metadata_dict, metadata_display, debug_msg = build_inference_metadata(
        ttft=ttft,
        inference_time=inference_time,
        tokens_generated=token_count,
        tokens_per_sec=tokens_per_sec,
        source=f"AIfred ({model})",
        backend_metrics=metrics,
        tokens_prompt=metrics.get("tokens_prompt", 0),
        agent_label="AIfred Refinement",
        response_chars=len(full_response),
    )
    state.add_debug(debug_msg)
    if audio_urls:
        log_message(f"🔊 AIfred Refinement: {len(audio_urls)} audio URLs collected for message")

    # DUAL-HISTORY: Sync AIfred refinement to llm_history (SSoT)
    state._sync_to_llm_history("aifred", full_response)

    # RETURN result as final yield (dict = result, None = UI update)
    yield {
        "text": full_response,
        "metadata_display": metadata_display,
        "metadata_dict": metadata_dict,
        "audio_urls": audio_urls
    }

    # Clear streaming state (cleanup)
    state.current_ai_response = ""
    state.current_agent = ""


async def _stream_salomo_to_history(
    state: 'AIState',
    llm_client: LLMClient,
    model: str,
    messages: list,
    options: LLMOptions,
) -> AsyncGenerator[dict[str, Any] | None, None]:
    """
    Stream Salomo response into current_ai_response (unified streaming).

    Performance-optimized: Does NOT update chat_history during streaming.
    Only updates state.current_ai_response which is shown in unified streaming_box.
    Caller is responsible for appending final result to chat_history.
    """
    full_response = ""
    token_count = 0
    timer = Timer()
    ttft = 0.0
    first_token = False

    # Set current agent for UI styling
    state.current_agent = "salomo"
    state.current_ai_response = ""

    # Initialize streaming TTS for Salomo
    if state.enable_tts and state.tts_autoplay and state.tts_streaming_enabled:
        state._init_streaming_tts(agent="salomo")

    async for chunk in _chat_stream_with_retry(llm_client, model, messages, options, "Salomo", state):
        if chunk["type"] == "content":
            if not first_token:
                ttft = timer.elapsed()
                log_message(f"⚡ Salomo TTFT: {format_number(ttft, 2)}s")
                state.add_debug(f"⚡ TTFT: {format_number(ttft, 2)}s")
                first_token = True

            full_response += chunk["text"]
            token_count += 1

            state.stream_text_to_ui(chunk["text"])
            yield None

        elif chunk["type"] == "done":
            metrics = chunk.get("metrics", {})
            token_count = metrics.get("tokens_generated", token_count)

    # Finalize streaming TTS: send any remaining text in buffer
    audio_urls: list[str] = []
    if state.enable_tts and state.tts_autoplay and state.tts_streaming_enabled:
        audio_urls = await state._finalize_streaming_tts()

    # Centralized metadata (PP speed, debug log, chat bubble)
    inference_time = timer.elapsed()
    tokens_per_sec = token_count / inference_time if inference_time > 0 else 0

    metadata_dict, metadata_display, debug_msg = build_inference_metadata(
        ttft=ttft,
        inference_time=inference_time,
        tokens_generated=token_count,
        tokens_per_sec=tokens_per_sec,
        source=f"Salomo ({model})",
        backend_metrics=metrics,
        tokens_prompt=metrics.get("tokens_prompt", 0),
        agent_label="Salomo",
        response_chars=len(full_response),
    )
    state.add_debug(debug_msg)
    if audio_urls:
        log_message(f"🔊 Salomo: {len(audio_urls)} audio URLs collected for message")

    # RETURN result as final yield (dict = result, None = UI update)
    yield {
        "text": full_response,
        "metadata_display": metadata_display,
        "metadata_dict": metadata_dict,
        "audio_urls": audio_urls
    }

    # DUAL-HISTORY: Sync Salomo response to llm_history (SSoT)
    state._sync_to_llm_history("salomo", full_response)

    # Clear streaming state (cleanup)
    state.current_ai_response = ""
    state.current_agent = ""


async def _check_compression_if_needed(
    state: 'AIState',
    llm_client: LLMClient,
    agent_context_limit: int,
    system_prompt_tokens: int = 0
) -> AsyncGenerator[None, None]:
    """
    Check if history compression is needed during multi-agent debate.

    NOTE: Main PRE-MESSAGE check runs in send_message() BEFORE multi-agent starts.
    This function handles compression DURING long debates where the debate itself
    might push context usage above threshold.

    Compression triggers at 70% of agent_context_limit (HISTORY_COMPRESSION_TRIGGER).

    IMPORTANT (v2.14.4+): Use the CURRENT AGENT's context limit, not min_ctx!
    Each agent (AIfred, Sokrates, Salomo) may have different context windows.
    Compression should trigger based on the NEXT agent's limit to prevent overflow.

    Args:
        state: AIState instance
        llm_client: LLM client for compression
        agent_context_limit: Context window limit OF THE NEXT AGENT (not min_ctx!)
        system_prompt_tokens: Estimated tokens for current agent's system prompt (v2.14.0+)
    """
    try:
        # Select largest model for compression (AIfred/Sokrates/Salomo)
        compression_model = get_largest_compression_model(
            aifred_model=state.aifred_model_id,
            sokrates_model=state.sokrates_model_id,
            salomo_model=state.salomo_model_id
        )

        # Run compression check (yields events if compression happens) - DUAL-HISTORY
        async for event in summarize_history_if_needed(
            history=state.chat_history,
            llm_client=llm_client,
            model_name=compression_model,  # Use largest available model for quality
            context_limit=agent_context_limit,  # Use agent-specific limit, not min_ctx!
            llm_history=state.llm_history,
            system_prompt_tokens=system_prompt_tokens
        ):
            if event["type"] == "history_update":
                # DUAL-HISTORY: Update both histories
                state.chat_history = event["chat_history"]
                if event.get("llm_history") is not None:
                    state.llm_history = event["llm_history"]
                state.add_debug(f"✅ History compressed: {len(state.chat_history)} UI / {len(state.llm_history)} LLM messages")
                yield
            elif event["type"] == "debug":
                state.add_debug(event["message"])
                yield
            elif event["type"] == "progress":
                state.is_compressing = True
                yield

        state.is_compressing = False

    except Exception as e:
        state.add_debug(f"⚠️ Compression check failed: {e}")
        state.is_compressing = False


# ============================================================
# SOKRATES DIRECT RESPONSE (when user addresses Sokrates directly)
# ============================================================

async def run_sokrates_direct_response(
    state: 'AIState',
    user_query: str,
    detected_lang: Optional[str] = None
) -> AsyncGenerator[None, None]:
    """
    Sokrates responds directly to user (without AIfred's answer first).

    This is called when user directly addresses Sokrates:
    - "Sokrates, warum denkst du..."
    - "@Sokrates erkläre mir..."
    - "Hey Sokrates, ..."

    Args:
        state: The AIState object for accessing chat_history, add_debug, etc.
        user_query: The user's question (with or without addressing prefix)
        detected_lang: Language detected by LLM intent detection ("de" or "en")
                      Defaults to UI-Language if not provided.
    """
    # Fallback to UI language if not provided
    if detected_lang is None:
        from .prompt_loader import get_language
        detected_lang = get_language()
    try:
        # Create LLM client
        llm_client = LLMClient(
            backend_type=state.backend_type,
            base_url=state.backend_url
        )

        # Determine Sokrates model
        sokrates_model = state.sokrates_model_id if state.sokrates_model_id else state.aifred_model_id
        sokrates_display = state.sokrates_model if state.sokrates_model else state.aifred_model
        state.add_debug(f"🏛️ Sokrates-LLM: {sokrates_display}")

        # Calculate context limit (uses SINGLE SOURCE OF TRUTH with XTTS reservation)
        from .research.context_utils import get_agent_num_ctx
        sokrates_num_ctx, ctx_source = get_agent_num_ctx("sokrates", state, sokrates_model)
        state.add_debug(f"   🎯 Context: {sokrates_num_ctx:,} ({ctx_source})")

        # Load system prompt from file (no hardcoded prompts!)
        # detected_lang comes from LLM-based intent detection (passed from state.py)
        system_prompt = get_sokrates_direct_prompt(lang=detected_lang)

        # Build messages from LLM history with Sokrates perspective
        # Sokrates sees his own messages as 'assistant', others as 'user'
        messages: list[dict[str, Any]] = build_messages_from_llm_history(
            state.llm_history[:-1],
            user_query,
            perspective="sokrates",
            detected_language=detected_lang
        )

        # Prepend system message
        messages.insert(0, {"role": "system", "content": system_prompt})

        # Calculate Sokrates temperature based on mode
        if state.temperature_mode == "manual":
            sokrates_direct_temp = state.sokrates_temperature
        else:
            # Auto mode: AIfred's temperature + offset (capped at 1.0)
            sokrates_direct_temp = min(1.0, state.temperature + state.sokrates_temperature_offset)

        # Debug: Show context and temperature
        state.add_debug(f"📊 Context: {format_number(sokrates_num_ctx/1000, 3)}k")
        state.add_debug(f"🌡️ Temperature: {format_number(sokrates_direct_temp, 1)}")

        # LLM options - use per-agent reasoning toggle for enable_thinking
        sokrates_options = build_llm_options(state, "sokrates", sokrates_direct_temp, sokrates_num_ctx)

        # Set current agent for unified streaming UI
        state.current_agent = "sokrates"
        state.current_ai_response = ""

        # Initialize streaming TTS for Sokrates direct response
        if state.enable_tts and state.tts_autoplay and state.tts_streaming_enabled:
            state._init_streaming_tts(agent="sokrates")

        # Streaming response
        full_response = ""
        token_count = 0
        timer = Timer()
        first_token = False
        sokrates_ttft = 0.0

        async for chunk in llm_client.chat_stream(sokrates_model, messages, sokrates_options):  # type: ignore[arg-type]
            chunk_type = chunk.get("type", "")

            if chunk_type == "content":
                if not first_token:
                    ttft = timer.elapsed()
                    log_message(f"⚡ Sokrates TTFT: {format_number(ttft, 2)}s")
                    state.add_debug(f"⚡ TTFT: {format_number(ttft, 2)}s")
                    first_token = True
                    sokrates_ttft = ttft  # Save for metadata

                content = chunk.get("text", "")  # Key is "text", not "content"
                full_response += content
                token_count += 1

                # REAL-TIME streaming to UI (includes TTS chunk processing)
                state.stream_text_to_ui(content)
                yield

            elif chunk_type == "thinking":
                # Handle thinking chunks (Qwen3 thinking mode)
                thinking_content = chunk.get("text", "")  # Also "text" for thinking
                if thinking_content:
                    full_response += f"<think>{thinking_content}</think>"

            elif chunk_type == "done":
                metrics = chunk.get("metrics", {})
                token_count = metrics.get("tokens_generated", token_count)

        # Finalize streaming TTS: send any remaining text in buffer
        audio_urls: list[str] = []
        if state.enable_tts and state.tts_autoplay and state.tts_streaming_enabled:
            audio_urls = await state._finalize_streaming_tts()

        # Centralized metadata (PP speed, debug log, chat bubble)
        inference_time = timer.elapsed()
        tokens_per_sec = token_count / inference_time if inference_time > 0 else 0

        metadata_dict, metadata_display, debug_msg = build_inference_metadata(
            ttft=sokrates_ttft,
            inference_time=inference_time,
            tokens_generated=token_count,
            tokens_per_sec=tokens_per_sec,
            source=f"Sokrates ({sokrates_model})",
            backend_metrics=metrics,
            tokens_prompt=metrics.get("tokens_prompt", 0),
            agent_label="Sokrates",
            response_chars=len(full_response),
        )
        state.add_debug(debug_msg)
        if audio_urls:
            log_message(f"🔊 Sokrates Direct: {len(audio_urls)} audio URLs collected for message")

        # Sync to llm_history with RAW content (SSoT — before formatting removes code context)
        state._sync_to_llm_history("sokrates", full_response)

        # Format thinking blocks as collapsibles for UI display
        formatted_response = format_thinking_process(
            full_response,
            model_name=f"Sokrates ({sokrates_model})",
            inference_time=inference_time
        )

        # Use centralized panel management (Dict-based chat_history - no index manipulation)
        panel_meta = {**metadata_dict, "audio_urls": audio_urls}
        state.add_agent_panel(
            agent="sokrates",
            content=formatted_response,
            mode="direct",
            metadata=panel_meta,
            sync_llm_history=False  # Already synced above with raw content
        )

        # Clear streaming state (cleanup)
        state.current_ai_response = ""
        state.current_agent = ""

        # INCREMENTAL SAVE: Persist after response to survive browser refresh
        state._save_current_session()

        # Separator nach Sokrates Direct Response
        console_separator()  # Log-File
        state.add_debug("────────────────────")  # Debug-Console

        await llm_client.close()
        yield

    except Exception as e:
        state.add_debug(f"❌ Sokrates Direct Response Error: {e}")
        # Add error as Sokrates panel entry (Dict-based - simply append)
        state.add_agent_panel(
            agent="sokrates",
            content=f"Error: {str(e)}",
            mode="error"
        )
        yield


# ============================================================
# SALOMO DIRECT RESPONSE
# ============================================================

async def run_salomo_direct_response(
    state: 'AIState',
    user_query: str,
    detected_lang: Optional[str] = None
) -> AsyncGenerator[None, None]:
    """
    Salomo responds directly to user (without AIfred or Sokrates first).

    This is called when user directly addresses Salomo:
    - "Salomo, urteile du..."
    - "@Salomo was meinst du..."
    - "Hey Salomo, ..."

    Args:
        state: The AIState object for accessing chat_history, add_debug, etc.
        user_query: The user's question (with or without addressing prefix)
        detected_lang: Language detected by LLM intent detection ("de" or "en")
                      Defaults to UI-Language if not provided.
    """
    # Fallback to UI language if not provided
    if detected_lang is None:
        from .prompt_loader import get_language
        detected_lang = get_language()

    try:
        # Create LLM client
        llm_client = LLMClient(
            backend_type=state.backend_type,
            base_url=state.backend_url
        )

        # Determine Salomo model
        salomo_model = state.salomo_model_id if state.salomo_model_id else state.aifred_model_id
        salomo_display = state.salomo_model if state.salomo_model else state.aifred_model
        state.add_debug(f"👑 Salomo-LLM: {salomo_display}")

        # Calculate context limit (uses SINGLE SOURCE OF TRUTH with XTTS reservation)
        from .research.context_utils import get_agent_num_ctx
        salomo_num_ctx, ctx_source = get_agent_num_ctx("salomo", state, salomo_model)
        state.add_debug(f"   🎯 Context: {salomo_num_ctx:,} ({ctx_source})")

        # Load system prompt from file (no hardcoded prompts!)
        # detected_lang comes from LLM-based intent detection (passed from state.py)
        system_prompt = get_salomo_direct_prompt(lang=detected_lang)

        # Build messages from LLM history with Salomo perspective
        # Salomo sees his own messages as 'assistant', others as 'user'
        messages: list[dict[str, Any]] = build_messages_from_llm_history(
            state.llm_history[:-1],
            user_query,
            perspective="salomo",
            detected_language=detected_lang
        )

        # Prepend system message
        messages.insert(0, {"role": "system", "content": system_prompt})

        # Calculate Salomo temperature based on mode
        if state.temperature_mode == "manual":
            salomo_direct_temp = state.salomo_temperature
        else:
            # Auto mode: AIfred's temperature + offset (capped at 1.0)
            salomo_direct_temp = min(1.0, state.temperature + state.salomo_temperature_offset)

        # Debug: Show context and temperature
        state.add_debug(f"📊 Context: {format_number(salomo_num_ctx/1000, 3)}k")
        state.add_debug(f"🌡️ Temperature: {format_number(salomo_direct_temp, 1)}")

        # LLM options - use per-agent reasoning toggle for enable_thinking
        salomo_options = build_llm_options(state, "salomo", salomo_direct_temp, salomo_num_ctx)

        # Set current agent for unified streaming UI
        state.current_agent = "salomo"
        state.current_ai_response = ""

        # Initialize streaming TTS for Salomo direct response
        if state.enable_tts and state.tts_autoplay and state.tts_streaming_enabled:
            state._init_streaming_tts(agent="salomo")

        # Streaming response
        full_response = ""
        token_count = 0
        timer = Timer()
        first_token = False
        salomo_ttft = 0.0

        async for chunk in llm_client.chat_stream(salomo_model, messages, salomo_options):  # type: ignore[arg-type]
            chunk_type = chunk.get("type", "")

            if chunk_type == "content":
                if not first_token:
                    ttft = timer.elapsed()
                    log_message(f"⚡ Salomo TTFT: {format_number(ttft, 2)}s")
                    state.add_debug(f"⚡ TTFT: {format_number(ttft, 2)}s")
                    first_token = True
                    salomo_ttft = ttft  # Save for metadata

                content = chunk.get("text", "")  # Key is "text", not "content"
                full_response += content
                token_count += 1

                # REAL-TIME streaming to UI (includes TTS chunk processing)
                state.stream_text_to_ui(content)
                yield

            elif chunk_type == "thinking":
                # Handle thinking chunks (Qwen3 thinking mode)
                thinking_content = chunk.get("text", "")  # Also "text" for thinking
                if thinking_content:
                    full_response += f"<think>{thinking_content}</think>"

            elif chunk_type == "done":
                metrics = chunk.get("metrics", {})
                token_count = metrics.get("tokens_generated", token_count)

        # Finalize streaming TTS: send any remaining text in buffer
        audio_urls: list[str] = []
        if state.enable_tts and state.tts_autoplay and state.tts_streaming_enabled:
            audio_urls = await state._finalize_streaming_tts()

        # Centralized metadata (PP speed, debug log, chat bubble)
        inference_time = timer.elapsed()
        tokens_per_sec = token_count / inference_time if inference_time > 0 else 0

        metadata_dict, metadata_display, debug_msg = build_inference_metadata(
            ttft=salomo_ttft,
            inference_time=inference_time,
            tokens_generated=token_count,
            tokens_per_sec=tokens_per_sec,
            source=f"Salomo ({salomo_model})",
            backend_metrics=metrics,
            tokens_prompt=metrics.get("tokens_prompt", 0),
            agent_label="Salomo",
            response_chars=len(full_response),
        )
        state.add_debug(debug_msg)
        if audio_urls:
            log_message(f"🔊 Salomo Direct: {len(audio_urls)} audio URLs collected for message")

        # Sync to llm_history with RAW content (SSoT — before formatting removes code context)
        state._sync_to_llm_history("salomo", full_response)

        # Format thinking blocks as collapsibles for UI display
        formatted_response = format_thinking_process(
            full_response,
            model_name=f"Salomo ({salomo_model})",
            inference_time=inference_time
        )

        # Use centralized panel management (Dict-based chat_history - no index manipulation)
        panel_meta = {**metadata_dict, "audio_urls": audio_urls}
        state.add_agent_panel(
            agent="salomo",
            content=formatted_response,
            mode="direct",
            metadata=panel_meta,
            sync_llm_history=False  # Already synced above with raw content
        )

        # Clear streaming state (cleanup)
        state.current_ai_response = ""
        state.current_agent = ""

        # INCREMENTAL SAVE: Persist after response to survive browser refresh
        state._save_current_session()

        # Separator nach Salomo Direct Response
        console_separator()  # Log-File
        state.add_debug("────────────────────")  # Debug-Console

        await llm_client.close()
        yield

    except Exception as e:
        state.add_debug(f"❌ Salomo Direct Response Error: {e}")
        # Add error as Salomo panel entry (Dict-based - simply append)
        state.add_agent_panel(
            agent="salomo",
            content=f"Error: {str(e)}",
            mode="error"
        )
        yield


# ============================================================
# SOKRATES ANALYSIS
# ============================================================

async def run_sokrates_analysis(
    state: 'AIState',
    user_query: str,
    alfred_answer: str,
    detected_lang: Optional[str] = None
) -> AsyncGenerator[None, None]:
    """
    Run Sokrates analysis based on current multi_agent_mode

    This is called after AIfred's response is complete.
    Uses streaming for real-time output and collects metadata.
    Yields to update UI during analysis.

    For auto_consensus mode: Iterates until Sokrates says LGTM or max_rounds reached.

    Args:
        state: The AIState object for accessing chat_history, add_debug, etc.
        user_query: The original user question
        alfred_answer: AIfred's answer to critique
        detected_lang: Language detected by LLM intent detection ("de" or "en")
                      Defaults to UI-Language if not provided.
    """
    # Fallback to UI language if not provided
    if detected_lang is None:
        from .prompt_loader import get_language
        detected_lang = get_language()

    state.debate_in_progress = True
    state.sokrates_critique = ""  # Clear previous
    state.debate_round = 0

    # DEBUG: Log entry to verify function is called
    state.add_debug(f"🔍 run_sokrates_analysis START: mode={state.multi_agent_mode}, alfred_answer_len={len(alfred_answer)}")
    yield  # Update UI

    # detected_lang comes from LLM-based intent detection (passed from state.py)

    try:
        # Create LLM client
        llm_client = LLMClient(
            backend_type=state.backend_type,
            base_url=state.backend_url
        )

        # Determine models
        sokrates_model = state.sokrates_model_id if state.sokrates_model_id else state.aifred_model_id
        sokrates_display = state.sokrates_model if state.sokrates_model else state.aifred_model
        alfred_model = state.aifred_model_id
        state.add_debug(f"🏛️ Sokrates-LLM: {sokrates_display}")

        # Mode labels for display (i18n)
        mode_labels = {
            "critical_review": t("multi_agent_critical_review", lang=state.ui_language),
            "auto_consensus": t("multi_agent_auto_consensus", lang=state.ui_language),
            "devils_advocate": t("multi_agent_devils_advocate", lang=state.ui_language)
        }
        mode_label = mode_labels.get(state.multi_agent_mode, state.multi_agent_mode)

        # Get context limits for both models (respect per-LLM manual toggles)
        # Use centralized get_agent_num_ctx() for consistent context determination
        from .research.context_utils import get_agent_num_ctx

        # AIfred context
        alfred_model = state.aifred_model_id
        main_llm_ctx, aifred_source = get_agent_num_ctx("aifred", state, alfred_model, fallback=32768)
        state.add_debug(f"🎯 AIfred: {format_number(main_llm_ctx)} tok ({aifred_source})")

        # Sokrates context
        sokrates_num_ctx, sokrates_source = get_agent_num_ctx("sokrates", state, sokrates_model, fallback=32768)
        state.add_debug(f"🎯 Sokrates: {format_number(sokrates_num_ctx)} tok ({sokrates_source})")

        # Salomo context
        salomo_model = state.salomo_model_id if state.salomo_model_id else state.aifred_model_id
        salomo_num_ctx, salomo_source = get_agent_num_ctx("salomo", state, salomo_model, fallback=32768)
        state.add_debug(f"🎯 Salomo: {format_number(salomo_num_ctx)} tok ({salomo_source})")

        # Store separate limits for each agent
        _last_vram_limit_cache["aifred_limit"] = main_llm_ctx
        _last_vram_limit_cache["sokrates_limit"] = sokrates_num_ctx
        _last_vram_limit_cache["salomo_limit"] = salomo_num_ctx

        # Update global limit with MINIMUM of all (for history compression)
        min_ctx = min(sokrates_num_ctx, main_llm_ctx, salomo_num_ctx)
        _last_vram_limit_cache["limit"] = min_ctx
        state.add_debug(
            f"📊 Context limits: AIfred={format_number(main_llm_ctx)} tok, "
            f"Sokrates={format_number(sokrates_num_ctx)} tok, "
            f"Salomo={format_number(salomo_num_ctx)} tok, "
            f"Compression={format_number(min_ctx)} tok"
        )

        # Calculate temperatures based on mode
        if state.temperature_mode == "manual":
            alfred_temp = state.temperature
            sokrates_temp = state.sokrates_temperature
            salomo_temp = state.salomo_temperature
        else:
            # Auto mode: Use intent-based temperature from main flow
            # For Multi-Agent, use moderate defaults since Intent Detection ran earlier
            alfred_temp = state.temperature  # Already set by Intent Detection or manual
            sokrates_temp = min(1.0, alfred_temp + state.sokrates_temperature_offset)
            salomo_temp = min(1.0, alfred_temp + state.salomo_temperature_offset)

        state.add_debug(
            f"🌡️ Temps: AIfred={format_number(alfred_temp, 1)}, "
            f"Sokrates={format_number(sokrates_temp, 1)}, "
            f"Salomo={format_number(salomo_temp, 1)}"
        )

        # LLM options with calculated context and temperatures
        # Use per-agent reasoning toggle for enable_thinking
        sokrates_options = build_llm_options(state, "sokrates", sokrates_temp, sokrates_num_ctx)
        alfred_options = build_llm_options(state, "aifred", alfred_temp, main_llm_ctx)

        # Track current answer (may be refined in auto_consensus)
        current_answer = alfred_answer
        consensus_reached = False
        max_rounds = state.max_debate_rounds if state.multi_agent_mode == "auto_consensus" else 1

        for round_num in range(1, max_rounds + 1):
            state.debate_round = round_num

            # === SOKRATES CRITIQUE ===
            # Get system prompts: minimal (base personality) + mode-specific
            sokrates_minimal = get_sokrates_system_minimal(lang=detected_lang, multi_agent=True)
            if state.multi_agent_mode == "devils_advocate":
                mode_prompt = get_sokrates_devils_advocate_prompt(lang=detected_lang)
            else:
                # Critic prompt for all other modes (Sokrates never says LGTM)
                # round_num prevents hallucinating "progress" in round 1
                mode_prompt = get_sokrates_critic_prompt(round_num=round_num, lang=detected_lang)

            # Combine: minimal first, then mode-specific
            system_prompt = f"{sokrates_minimal}\n\n{mode_prompt}"

            # Build messages with Sokrates' perspective
            # - Sokrates sees his own earlier responses as 'assistant'
            # - AIfred's responses and User messages become 'user' with labels
            # - No "Sokrates?" activation needed - perspective handles role assignment
            # Use llm_history (compressed) instead of chat_history (full UI)
            history_messages: list[dict[str, str]] = build_messages_from_llm_history(
                state.llm_history,
                perspective="sokrates",
                detected_language=detected_lang
            )

            # Build final message list: Sokrates system prompt + history
            sokrates_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
            for msg in history_messages:
                # Keep all messages except non-summary system messages
                if msg["role"] != "system" or "Compressed:" in msg.get("content", ""):
                    sokrates_messages.append(msg)

            # PRE-SOKRATES: Check if compression needed before Sokrates call
            # Include Sokrates system prompt in token calculation (v2.14.0+)
            # IMPORTANT (v2.14.4+): Use SOKRATES' context limit, not min_ctx!
            sokrates_prompt_tokens = _estimate_prompt_tokens(system_prompt)
            async for _ in _check_compression_if_needed(state, llm_client, sokrates_num_ctx, sokrates_prompt_tokens):
                yield

            # Estimate tokens in messages (using proper tokenizer estimation)
            sokrates_msg_tokens = estimate_tokens(sokrates_messages, model_name=sokrates_model)
            sokrates_ctx = sokrates_options.num_ctx if sokrates_options and sokrates_options.num_ctx else 8192
            state.add_debug(
                f"📊 Sokrates R{round_num}: {format_number(sokrates_msg_tokens)} / "
                f"{format_number(sokrates_ctx)} tokens"
            )

            # DEBUG: Log RAW messages sent to Sokrates (controlled by DEBUG_LOG_RAW_MESSAGES)
            log_raw_messages(f"Sokrates R{round_num}", sokrates_messages)

            # Stream Sokrates response (unified streaming box shows content)
            result = None
            async for item in _stream_sokrates_to_history(
                state=state,
                llm_client=llm_client,
                model=sokrates_model,
                messages=sokrates_messages,
                options=sokrates_options,
            ):
                if isinstance(item, dict):
                    # Last yield is the result
                    result = item
                else:
                    yield  # Forward UI updates

            # Extract Sokrates result from final yield
            if result is None:
                state.add_debug("❌ Sokrates stream returned no result")
                break
            sokrates_response_text = result["text"]
            metadata_display = result["metadata_display"]
            metadata_dict = result["metadata_dict"]
            audio_urls = result.get("audio_urls", [])

            # Format <think> tags as collapsible (if present)
            formatted_sokrates = format_thinking_process(
                sokrates_response_text,
                model_name=f"Sokrates ({sokrates_model})",
                inference_time=metadata_dict.get("inference_time", 0)
            )

            # Add Sokrates critique panel (centralized)
            # Note: _stream_sokrates_to_history already synced to llm_history (Line 259)
            # Mode: Use specific mode for devils_advocate, else generic critical_review
            sokrates_mode = "advocatus_diaboli" if state.multi_agent_mode == "devils_advocate" else "critical_review"
            panel_meta = {**metadata_dict, "audio_urls": audio_urls}
            state.add_agent_panel(
                agent="sokrates",
                content=formatted_sokrates,
                mode=sokrates_mode,
                round_num=round_num,  # Always show round number for consistency
                metadata=panel_meta,
                sync_llm_history=False  # Already done by _stream_sokrates_to_history
            )
            state.sokrates_critique = sokrates_response_text  # Keep raw text for logic checks
            yield

            # INCREMENTAL SAVE: Persist after each agent response to survive browser refresh
            state._save_current_session()

            # NOTE: PRE-CHECK before Sokrates already handles compression (line ~635)
            # No POST-CHECK needed here

            # Parse Pro/Contra for devils_advocate
            if state.multi_agent_mode == "devils_advocate":
                state.sokrates_pro_args, state.sokrates_contra_args = parse_pro_contra(sokrates_response_text)
                break  # Devils advocate is always one round

            # For critical_review: only one round (user decides)
            if state.multi_agent_mode == "critical_review":
                break

            # === AUTO-CONSENSUS (TRIALOG): Salomo synthesizes and decides ===
            if state.multi_agent_mode == "auto_consensus":
                # Determine Salomo model
                salomo_model = state.salomo_model_id if state.salomo_model_id else state.aifred_model_id
                salomo_display = state.salomo_model if state.salomo_model else state.aifred_model

                if round_num == 1:
                    state.add_debug(f"👑 Salomo-LLM: {salomo_display}")

                # Calculate Salomo context using centralized function
                from .research.context_utils import get_agent_num_ctx
                salomo_num_ctx, salomo_source = get_agent_num_ctx("salomo", state, salomo_model, fallback=32768)
                if round_num == 1:
                    state.add_debug(f"🎯 Salomo: {format_number(salomo_num_ctx)} tok ({salomo_source})")

                # salomo_temp already calculated above (before the loop)
                salomo_options = build_llm_options(state, "salomo", salomo_temp, salomo_num_ctx)

                # Build Salomo's messages: system + history
                salomo_minimal = get_salomo_system_minimal(lang=detected_lang, multi_agent=True)
                mediator_prompt = get_salomo_mediator_prompt(round_num=round_num, lang=detected_lang)
                salomo_system = f"{salomo_minimal}\n\n{mediator_prompt}"

                # Build messages with observer perspective (sees everything neutrally)
                # Use llm_history (compressed) instead of chat_history (full UI)
                salomo_messages: list[dict[str, str]] = build_messages_from_llm_history(
                    state.llm_history,
                    perspective="observer",  # Neutral perspective
                    detected_language=detected_lang
                )
                salomo_messages.insert(0, {"role": "system", "content": salomo_system})

                # PRE-SALOMO: Check if compression needed before Salomo call
                # Include Salomo system prompt in token calculation (v2.14.0+)
                # IMPORTANT (v2.14.4+): Use SALOMO's context limit, not min_ctx!
                salomo_prompt_tokens = _estimate_prompt_tokens(salomo_system)
                async for _ in _check_compression_if_needed(state, llm_client, salomo_num_ctx, salomo_prompt_tokens):
                    yield

                # Estimate tokens for Salomo (consistent with Sokrates debug output)
                salomo_msg_tokens = estimate_tokens(salomo_messages, model_name=salomo_model)
                state.add_debug(
                    f"📊 Salomo R{round_num}: {format_number(salomo_msg_tokens)} / "
                    f"{format_number(salomo_num_ctx)} tokens"
                )

                # DEBUG: Log RAW messages sent to Salomo (controlled by DEBUG_LOG_RAW_MESSAGES)
                log_raw_messages(f"Salomo R{round_num}", salomo_messages)

                # Stream Salomo response (unified streaming box shows content)
                salomo_result = None
                async for item in _stream_salomo_to_history(
                    state=state,
                    llm_client=llm_client,
                    model=salomo_model,
                    messages=salomo_messages,
                    options=salomo_options,
                ):
                    if isinstance(item, dict):
                        salomo_result = item
                    else:
                        yield

                # Extract Salomo result from final yield
                if salomo_result is None:
                    state.add_debug("❌ Salomo stream returned no result")
                    break
                salomo_response_text = salomo_result["text"]
                salomo_metadata_dict = salomo_result["metadata_dict"]
                salomo_audio_urls = salomo_result.get("audio_urls", [])

                # Format <think> tags as collapsible
                formatted_salomo = format_thinking_process(
                    salomo_response_text,
                    model_name=f"Salomo ({salomo_model})",
                    inference_time=salomo_metadata_dict.get("inference_time", 0)
                )

                # Add Salomo synthesis panel (centralized)
                # Note: _stream_salomo_to_history already synced to llm_history
                salomo_panel_meta = {**salomo_metadata_dict, "audio_urls": salomo_audio_urls}
                state.add_agent_panel(
                    agent="salomo",
                    content=formatted_salomo,
                    mode="synthesis",  # Uses salomo_synthesis_label via _get_mode_label
                    round_num=round_num,
                    metadata=salomo_panel_meta,
                    sync_llm_history=False  # Already done by _stream_salomo_to_history
                )
                state.salomo_synthesis = salomo_response_text
                yield

                # INCREMENTAL SAVE: Persist after each agent response to survive browser refresh
                state._save_current_session()

                # NOTE: PRE-CHECK before next agent handles compression
                # No POST-CHECK needed here

                # === NEW: 3-Agent Consensus Voting ===
                # Count votes from all three agents (AIfred, Sokrates, Salomo)
                votes = count_lgtm_votes(
                    alfred_text=current_answer,
                    sokrates_text=sokrates_response_text,
                    salomo_text=salomo_response_text
                )

                # Debug: Show vote status
                state.add_debug(format_votes_debug(votes, round_num))

                # Check consensus based on user's configured consensus_type
                if check_consensus(votes, state.consensus_type):
                    lgtm_count = sum(votes.values())
                    type_label = "unanimous" if state.consensus_type == "unanimous" else "majority"
                    state.add_debug(f"✅ Consensus reached in round {format_number(round_num)} ({format_number(lgtm_count)}/3 votes, {type_label})")
                    consensus_reached = True
                    break

                # If no consensus and more rounds available: AIfred refines based on Salomo's feedback
                if round_num < max_rounds:
                    # Build refinement prompt FIRST (needed for accurate token estimation)
                    # IMPORTANT: Clean <think> tags from Salomo's response before embedding in prompt!
                    cleaned_salomo_text = strip_thinking_blocks(salomo_response_text)
                    refinement_prompt = get_sokrates_refinement_prompt(
                        critique=cleaned_salomo_text,  # Use Salomo's synthesis as guidance (cleaned)
                        user_interjection="",
                        lang=detected_lang,
                        round_num=round_num + 1  # AIfred refinement is R{n+1} after Salomo R{n}
                    )

                    # PRE-AIFRED: Check if compression needed before AIfred refinement
                    # Include AIfred system prompt + refinement prompt in token calculation (v2.14.1+)
                    # IMPORTANT (v2.14.4+): Use AIFRED's context limit, not min_ctx!
                    aifred_system_prompt = get_aifred_system_minimal(lang=detected_lang, multi_agent=True)
                    aifred_prompt_tokens = _estimate_prompt_tokens(aifred_system_prompt) + _estimate_prompt_tokens(refinement_prompt)
                    async for _ in _check_compression_if_needed(state, llm_client, main_llm_ctx, aifred_prompt_tokens):
                        yield

                    # Build messages with AIfred's perspective
                    # Use llm_history (compressed) instead of chat_history (full UI)
                    aifred_history_messages: list[dict[str, str]] = build_messages_from_llm_history(
                        state.llm_history,
                        current_user_text=refinement_prompt,
                        perspective="aifred",
                        detected_language=detected_lang
                    )

                    # Build final message list: AIfred system prompt + history
                    # (Same pattern as Sokrates - agent needs system prompt for identity)
                    alfred_messages: list[dict[str, str]] = [{"role": "system", "content": aifred_system_prompt}]
                    for msg in aifred_history_messages:
                        # Keep all messages except non-summary system messages
                        if msg["role"] != "system" or "Compressed:" in msg.get("content", ""):
                            alfred_messages.append(msg)

                    # Estimate tokens
                    alfred_msg_tokens = estimate_tokens(alfred_messages, model_name=state.aifred_model_id)
                    alfred_ctx = alfred_options.num_ctx if alfred_options and alfred_options.num_ctx else 32768
                    state.add_debug(
                        f"📊 AIfred R{round_num + 1}: {format_number(alfred_msg_tokens)} / "
                        f"{format_number(alfred_ctx)} tokens"
                    )

                    # DEBUG: Log RAW messages sent to AIfred (controlled by DEBUG_LOG_RAW_MESSAGES)
                    log_raw_messages(f"AIfred R{round_num + 1}", alfred_messages)

                    # Stream AIfred refinement (unified streaming box shows content)
                    alfred_result = None
                    async for item in _stream_alfred_refinement(
                        state=state,
                        llm_client=llm_client,
                        model=alfred_model,
                        messages=alfred_messages,
                        options=alfred_options,
                    ):
                        if isinstance(item, dict):
                            alfred_result = item
                        else:
                            yield

                    # Extract refined answer from final yield
                    if alfred_result is None:
                        state.add_debug("❌ AIfred refinement stream returned no result")
                        break
                    current_answer = alfred_result["text"]
                    alfred_metadata_dict = alfred_result.get("metadata_dict", {})
                    alfred_audio_urls = alfred_result.get("audio_urls", [])

                    # Format <think> tags as collapsible
                    formatted_alfred = format_thinking_process(
                        current_answer,
                        model_name=f"AIfred ({alfred_model})",
                        inference_time=alfred_metadata_dict.get("inference_time", 0)
                    )

                    # Add Alfred refinement panel (centralized)
                    # Note: _stream_alfred_refinement already synced to llm_history
                    # IMPORTANT: AIfred Refinement happens AFTER Salomo R{n}, so it's part of R{n+1}
                    alfred_panel_meta = {**alfred_metadata_dict, "audio_urls": alfred_audio_urls}
                    state.add_agent_panel(
                        agent="aifred",
                        content=formatted_alfred,
                        mode="refinement",
                        round_num=round_num + 1,
                        metadata=alfred_panel_meta,
                        sync_llm_history=False  # Already done by _stream_alfred_refinement
                    )
                    yield

                    # INCREMENTAL SAVE: Persist after each agent response to survive browser refresh
                    state._save_current_session()

                    # NOTE: PRE-CHECK before next iteration handles compression
                    # No POST-CHECK needed here

        # End of debate
        if state.multi_agent_mode == "auto_consensus":
            if consensus_reached:
                state.add_debug(f"🎯 Debate finished: consensus after {format_number(state.debate_round)} rounds")
            else:
                state.add_debug(f"⚠️ No consensus after {format_number(max_rounds)} rounds")
                # Show final votes for debugging
                if 'votes' in locals():
                    state.add_debug(format_votes_debug(votes, state.debate_round))

        await llm_client.close()

        # Persist to session storage
        state._save_current_session()

        # Separator nach Sokrates Analysis (Ende des Multi-Agent Dialogs)
        console_separator()  # Log-File
        state.add_debug("────────────────────")  # Debug-Console

    except Exception as e:
        state.add_debug(f"❌ Sokrates Error: {e}")

    finally:
        state.debate_in_progress = False

    yield  # Final UI update


# ============================================================
# TRIBUNAL MODE (AIfred vs Sokrates, Salomo judges at end)
# ============================================================

async def run_tribunal(
    state: 'AIState',
    user_query: str,
    alfred_answer: str,
    detected_lang: Optional[str] = None
) -> AsyncGenerator[None, None]:
    """
    Run Tribunal mode: AIfred and Sokrates debate, Salomo judges at end.

    This is a separate mode from auto_consensus:
    - AIfred and Sokrates alternate for max_debate_rounds
    - Salomo only speaks at the very end with a final verdict
    - No LGTM during debate - Salomo delivers a definitive judgment

    Args:
        state: The AIState object
        user_query: The original user question
        alfred_answer: AIfred's initial answer
        detected_lang: Language detected by LLM intent detection ("de" or "en")
                      Defaults to UI-Language if not provided.
    """
    # Fallback to UI language if not provided
    if detected_lang is None:
        from .prompt_loader import get_language
        detected_lang = get_language()

    state.debate_in_progress = True
    state.sokrates_critique = ""
    state.salomo_synthesis = ""
    state.debate_round = 0
    yield

    # detected_lang comes from LLM-based intent detection (passed from state.py)

    try:
        # Create LLM client
        llm_client = LLMClient(
            backend_type=state.backend_type,
            base_url=state.backend_url
        )

        # Determine models
        sokrates_model = state.sokrates_model_id if state.sokrates_model_id else state.aifred_model_id
        sokrates_display = state.sokrates_model if state.sokrates_model else state.aifred_model
        salomo_model = state.salomo_model_id if state.salomo_model_id else state.aifred_model_id
        salomo_display = state.salomo_model if state.salomo_model else state.aifred_model
        alfred_model = state.aifred_model_id

        state.add_debug("⚖️ Tribunal mode started")
        state.add_debug(f"🏛️ Sokrates-LLM: {sokrates_display}")
        state.add_debug(f"👑 Salomo-LLM: {salomo_display}")

        # Get context limits using centralized function (respect per-LLM manual toggles)
        from .research.context_utils import get_agent_num_ctx

        # AIfred context
        main_llm_ctx, aifred_source = get_agent_num_ctx("aifred", state, alfred_model, fallback=32768)
        state.add_debug(f"🎯 AIfred: {format_number(main_llm_ctx)} tok ({aifred_source})")

        # Sokrates context
        sokrates_num_ctx, sokrates_source = get_agent_num_ctx("sokrates", state, sokrates_model, fallback=32768)
        state.add_debug(f"🎯 Sokrates: {format_number(sokrates_num_ctx)} tok ({sokrates_source})")

        # Salomo context
        salomo_num_ctx, salomo_source = get_agent_num_ctx("salomo", state, salomo_model, fallback=32768)
        state.add_debug(f"🎯 Salomo: {format_number(salomo_num_ctx)} tok ({salomo_source})")

        min_ctx = min(sokrates_num_ctx, main_llm_ctx, salomo_num_ctx)

        # Update global cache for history compression (same as standard multi-agent)
        _last_vram_limit_cache["aifred_limit"] = main_llm_ctx
        _last_vram_limit_cache["sokrates_limit"] = sokrates_num_ctx
        _last_vram_limit_cache["limit"] = min_ctx

        # Calculate temperatures
        if state.temperature_mode == "manual":
            alfred_temp = state.temperature
            sokrates_temp = state.sokrates_temperature
            salomo_temp = state.salomo_temperature
        else:
            alfred_temp = state.temperature
            sokrates_temp = min(1.0, alfred_temp + state.sokrates_temperature_offset)
            salomo_temp = min(1.0, alfred_temp + state.salomo_temperature_offset)

        # Use per-agent reasoning toggle for enable_thinking
        sokrates_options = build_llm_options(state, "sokrates", sokrates_temp, sokrates_num_ctx)
        alfred_options = build_llm_options(state, "aifred", alfred_temp, main_llm_ctx)
        salomo_options = build_llm_options(state, "salomo", salomo_temp, salomo_num_ctx)

        # Debug: Show context limits and temperatures
        state.add_debug(
            f"📊 Context limits: AIfred={format_number(main_llm_ctx)} tok, "
            f"Sokrates={format_number(sokrates_num_ctx)} tok, "
            f"Salomo={format_number(salomo_num_ctx)} tok, "
            f"Compression={format_number(min_ctx)} tok"
        )
        state.add_debug(
            f"🌡️ Temps: AIfred={format_number(alfred_temp, 1)}, "
            f"Sokrates={format_number(sokrates_temp, 1)}, "
            f"Salomo={format_number(salomo_temp, 1)}"
        )

        max_rounds = state.max_debate_rounds
        current_answer = alfred_answer

        # === DEBATE PHASE: AIfred vs Sokrates ===
        for round_num in range(1, max_rounds + 1):
            state.debate_round = round_num

            # --- SOKRATES ATTACK (Tribunal: adversarial, not coaching) ---
            sokrates_minimal = get_sokrates_system_minimal(lang=detected_lang, multi_agent=True)
            mode_prompt = get_sokrates_tribunal_prompt(round_num=round_num, lang=detected_lang)
            system_prompt = f"{sokrates_minimal}\n\n{mode_prompt}"

            # PRE-SOKRATES: Check if compression needed before Sokrates call
            # Include Sokrates system prompt in token calculation (v2.14.0+)
            # IMPORTANT (v2.14.4+): Use SOKRATES' context limit, not min_ctx!
            sokrates_prompt_tokens = _estimate_prompt_tokens(system_prompt)
            async for _ in _check_compression_if_needed(state, llm_client, sokrates_num_ctx, sokrates_prompt_tokens):
                yield

            # Use llm_history (compressed) instead of chat_history (full UI)
            history_messages = build_messages_from_llm_history(
                state.llm_history,
                perspective="sokrates",
                detected_language=detected_lang
            )
            sokrates_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
            for msg in history_messages:
                if msg["role"] != "system" or "Compressed:" in msg.get("content", ""):
                    sokrates_messages.append(msg)

            result = None
            async for item in _stream_sokrates_to_history(
                state=state,
                llm_client=llm_client,
                model=sokrates_model,
                messages=sokrates_messages,
                options=sokrates_options,
            ):
                if isinstance(item, dict):
                    result = item
                else:
                    yield

            # Extract Sokrates result from final yield
            if result is None:
                state.add_debug("❌ Sokrates stream returned no result")
                break
            sokrates_response_text = result["text"]
            metadata_dict = result["metadata_dict"]
            audio_urls = result.get("audio_urls", [])

            formatted_sokrates = format_thinking_process(
                sokrates_response_text,
                model_name=f"Sokrates ({sokrates_model})",
                inference_time=metadata_dict.get("inference_time", 0)
            )
            # Add Sokrates tribunal panel (centralized)
            # Note: _stream_sokrates_to_history already synced to llm_history
            panel_meta = {**metadata_dict, "audio_urls": audio_urls}
            state.add_agent_panel(
                agent="sokrates",
                content=formatted_sokrates,
                mode="tribunal",
                round_num=round_num,
                metadata=panel_meta,
                sync_llm_history=False  # Already done by _stream_sokrates_to_history
            )
            state.sokrates_critique = sokrates_response_text
            yield

            # INCREMENTAL SAVE: Persist after each agent response to survive browser refresh
            state._save_current_session()

            # NOTE: PRE-CHECK before next agent handles compression
            # No POST-CHECK needed here

            # --- AIFRED DEFENSE (Tribunal: may defend or revise) ---
            if round_num < max_rounds:
                # Build defense prompt FIRST (needed for accurate token estimation)
                # IMPORTANT: Clean <think> tags from Sokrates' response before embedding in prompt!
                cleaned_sokrates_text = strip_thinking_blocks(sokrates_response_text)
                refinement_prompt = get_aifred_defense_prompt(
                    critique=cleaned_sokrates_text,
                    user_interjection="",
                    lang=detected_lang,
                    round_num=round_num + 1  # AIfred response is R{n+1} after Sokrates R{n}
                )

                # PRE-AIFRED: Check if compression needed before AIfred refinement
                # Include AIfred system prompt + refinement prompt in token calculation (v2.14.1+)
                # IMPORTANT (v2.14.4+): Use AIFRED's context limit, not min_ctx!
                aifred_system_prompt = get_aifred_system_minimal(lang=detected_lang, multi_agent=True)
                aifred_prompt_tokens = _estimate_prompt_tokens(aifred_system_prompt) + _estimate_prompt_tokens(refinement_prompt)
                async for _ in _check_compression_if_needed(state, llm_client, main_llm_ctx, aifred_prompt_tokens):
                    yield

                # Use llm_history (compressed) instead of chat_history (full UI)
                aifred_history_messages: list[dict[str, str]] = build_messages_from_llm_history(
                    state.llm_history,
                    current_user_text=refinement_prompt,
                    perspective="aifred",
                    detected_language=detected_lang
                )

                # Build final message list: AIfred system prompt + history
                # (Same pattern as Sokrates - agent needs system prompt for identity)
                alfred_messages: list[dict[str, str]] = [{"role": "system", "content": aifred_system_prompt}]
                for msg in aifred_history_messages:
                    # Keep all messages except non-summary system messages
                    if msg["role"] != "system" or "Compressed:" in msg.get("content", ""):
                        alfred_messages.append(msg)

                alfred_result = None
                async for item in _stream_alfred_refinement(
                    state=state,
                    llm_client=llm_client,
                    model=alfred_model,
                    messages=alfred_messages,
                    options=alfred_options,
                ):
                    if isinstance(item, dict):
                        alfred_result = item
                    else:
                        yield

                # Extract Alfred result from final yield
                if alfred_result is None:
                    state.add_debug("❌ AIfred stream returned no result")
                    break
                current_answer = alfred_result["text"]
                alfred_metadata_dict = alfred_result.get("metadata_dict", {})
                alfred_audio_urls = alfred_result.get("audio_urls", [])

                formatted_alfred = format_thinking_process(
                    current_answer,
                    model_name=f"AIfred ({alfred_model})",
                    inference_time=alfred_metadata_dict.get("inference_time", 0)
                )

                # Add Alfred tribunal panel (centralized)
                # Note: _stream_alfred_refinement already synced to llm_history
                # IMPORTANT: AIfred responds AFTER Sokrates R{n}, so it's part of R{n+1}
                alfred_panel_meta = {**alfred_metadata_dict, "audio_urls": alfred_audio_urls}
                state.add_agent_panel(
                    agent="aifred",
                    content=formatted_alfred,
                    mode="tribunal",
                    round_num=round_num + 1,
                    metadata=alfred_panel_meta,
                    sync_llm_history=False  # Already done by _stream_alfred_refinement
                )
                yield

                # INCREMENTAL SAVE: Persist after each agent response to survive browser refresh
                state._save_current_session()

                # NOTE: PRE-CHECK in next iteration handles compression
                # No POST-CHECK needed here

        # === JUDGMENT PHASE: Salomo delivers final verdict ===
        state.add_debug("👑 Salomo rendering verdict...")

        salomo_minimal = get_salomo_system_minimal(lang=detected_lang, multi_agent=True)
        judge_prompt = get_salomo_judge_prompt(lang=detected_lang)
        salomo_system = f"{salomo_minimal}\n\n{judge_prompt}"

        # PRE-SALOMO: Check if compression needed before Salomo verdict
        # Include Salomo system prompt in token calculation (v2.14.0+)
        # IMPORTANT (v2.14.4+): Use SALOMO's context limit, not min_ctx!
        salomo_prompt_tokens = _estimate_prompt_tokens(salomo_system)
        async for _ in _check_compression_if_needed(state, llm_client, salomo_num_ctx, salomo_prompt_tokens):
            yield

        # Use llm_history (compressed) instead of chat_history (full UI)
        salomo_messages: list[dict[str, str]] = build_messages_from_llm_history(
            state.llm_history,
            perspective="observer",
            detected_language=detected_lang
        )
        salomo_messages.insert(0, {"role": "system", "content": salomo_system})

        # Estimate tokens for Salomo verdict (consistent with other agent debug output)
        salomo_msg_tokens = estimate_tokens(salomo_messages, model_name=salomo_model)
        state.add_debug(
            f"📊 Salomo Verdict: {format_number(salomo_msg_tokens)} / "
            f"{format_number(salomo_num_ctx)} tokens"
        )

        salomo_result = None
        async for item in _stream_salomo_to_history(
            state=state,
            llm_client=llm_client,
            model=salomo_model,
            messages=salomo_messages,
            options=salomo_options,
        ):
            if isinstance(item, dict):
                salomo_result = item
            else:
                yield

        # Extract Salomo result from final yield
        if salomo_result is None:
            raise RuntimeError("Salomo verdict stream returned no result")
        salomo_response_text = salomo_result["text"]
        salomo_metadata_dict = salomo_result["metadata_dict"]
        salomo_audio_urls = salomo_result.get("audio_urls", [])

        state.add_debug(
            f"👑 Salomo Verdict: {len(salomo_response_text)} chars, "
            f"{format_number(salomo_metadata_dict.get('tokens_per_sec', 0), 1)} tok/s"
        )

        formatted_salomo = format_thinking_process(
            salomo_response_text,
            model_name=f"Salomo ({salomo_model})",
            inference_time=salomo_metadata_dict.get("inference_time", 0)
        )
        # Add Salomo verdict panel (centralized)
        # Note: _stream_salomo_to_history already synced to llm_history
        salomo_panel_meta = {**salomo_metadata_dict, "audio_urls": salomo_audio_urls}
        state.add_agent_panel(
            agent="salomo",
            content=formatted_salomo,
            mode="verdict",  # Uses salomo_verdict_label via _get_mode_label
            round_num=max_rounds,  # Verdict belongs to final debate round
            metadata=salomo_panel_meta,
            sync_llm_history=False  # Already done by _stream_salomo_to_history
        )
        state.salomo_synthesis = salomo_response_text
        yield

        state.add_debug(f"⚖️ Tribunal completed after {max_rounds} rounds + verdict")

        await llm_client.close()
        state._save_current_session()

        console_separator()
        state.add_debug("────────────────────")

    except Exception as e:
        state.add_debug(f"❌ Tribunal Error: {e}")

    finally:
        state.debate_in_progress = False

    yield
