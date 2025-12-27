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

import time
from typing import TYPE_CHECKING, Any, AsyncGenerator

# Imports for the functions (same as original state.py methods)
from .llm_client import LLMClient
from .formatting import format_metadata, format_number, format_thinking_process
from .message_builder import build_messages_from_history
from .i18n import t
from .context_manager import (
    calculate_dynamic_num_ctx,
    estimate_tokens,
    strip_thinking_blocks,
    summarize_history_if_needed,
    _last_vram_limit_cache
)
from .prompt_loader import (
    detect_language,
    get_sokrates_system_minimal,
    get_sokrates_direct_prompt,
    get_sokrates_critic_prompt,
    get_sokrates_devils_advocate_prompt,
    get_sokrates_refinement_prompt,
    get_salomo_system_minimal,
    get_salomo_mediator_prompt,
    get_salomo_judge_prompt,
)
from .logging_utils import log_message, console_separator
from ..backends.base import LLMOptions

if TYPE_CHECKING:
    from ..state import AIState


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
    history_index: int,
    sokrates_marker: str,
) -> AsyncGenerator[None, None]:
    """
    Stream Sokrates response directly into chat_history.

    Similar to _stream_llm_with_ui but specifically for Sokrates:
    - Keeps the marker prefix during streaming (🏛️[Mode])
    - Updates chat_history[history_index] directly
    - No separate state variable needed
    """
    full_response = ""
    token_count = 0
    start_time = time.time()
    ttft = None
    first_token = False

    async for chunk in llm_client.chat_stream(model, messages, options):
        if chunk["type"] == "content":
            if not first_token:
                ttft = time.time() - start_time
                first_token = True

            full_response += chunk["text"]
            token_count += 1

            # Update chat_history directly with marker + current response
            if history_index < len(state.chat_history):
                state.chat_history[history_index] = ("", f"{sokrates_marker}{full_response}")

            yield  # UI Update

        elif chunk["type"] == "done":
            metrics = chunk.get("metrics", {})
            token_count = metrics.get("tokens_generated", token_count)

    # Calculate final metrics
    inference_time = time.time() - start_time
    tokens_per_sec = token_count / inference_time if inference_time > 0 else 0

    metadata = format_metadata(
        f"Inference: {format_number(inference_time, 1)}s    "
        f"{format_number(tokens_per_sec, 1)} tok/s    "
        f"Source: Sokrates ({model})"
    )

    # Store result for caller
    state._stream_result = {
        "text": full_response,
        "metadata": metadata,
        "metrics": {
            "time": inference_time,
            "tokens": token_count,
            "tok_per_sec": tokens_per_sec,
            "ttft": ttft
        }
    }

    # DUAL-HISTORY: Sync Sokrates response to llm_history
    # Agent-only entries become system messages with speaker label
    from .message_builder import clean_content_for_llm
    cleaned = clean_content_for_llm(full_response)
    if cleaned:
        state.llm_history.append({"role": "system", "content": f"[SOKRATES]: {cleaned}"})


async def _stream_alfred_refinement(
    state: 'AIState',
    llm_client: LLMClient,
    model: str,
    messages: list,
    options: LLMOptions,
    history_index: int,
    alfred_marker: str,
) -> AsyncGenerator[None, None]:
    """Stream AIfred's refined answer into chat_history (for auto_consensus)."""
    full_response = ""
    token_count = 0
    start_time = time.time()
    first_token = False

    async for chunk in llm_client.chat_stream(model, messages, options):
        if chunk["type"] == "content":
            if not first_token:
                first_token = True
            full_response += chunk["text"]
            token_count += 1

            # Update chat_history with current content
            if history_index < len(state.chat_history):
                state.chat_history[history_index] = ("", f"{alfred_marker}{full_response}")
            yield  # UI Update

        elif chunk["type"] == "done":
            metrics = chunk.get("metrics", {})
            token_count = metrics.get("tokens_generated", token_count)

    inference_time = time.time() - start_time
    tokens_per_sec = token_count / inference_time if inference_time > 0 else 0

    metadata = format_metadata(
        f"Inference: {format_number(inference_time, 1)}s    "
        f"{format_number(tokens_per_sec, 1)} tok/s    "
        f"Source: AIfred ({model})"
    )

    state._stream_result = {
        "text": full_response,
        "metadata": metadata,
        "metrics": {"time": inference_time, "tokens": token_count, "tok_per_sec": tokens_per_sec}
    }

    # DUAL-HISTORY: Sync AIfred refinement to llm_history
    # Agent-only entries become system messages with speaker label
    from .message_builder import clean_content_for_llm
    cleaned = clean_content_for_llm(full_response)
    if cleaned:
        state.llm_history.append({"role": "system", "content": f"[AIFRED]: {cleaned}"})


async def _stream_salomo_to_history(
    state: 'AIState',
    llm_client: LLMClient,
    model: str,
    messages: list,
    options: LLMOptions,
    history_index: int,
    salomo_marker: str,
) -> AsyncGenerator[None, None]:
    """
    Stream Salomo response directly into chat_history.

    Similar to _stream_sokrates_to_history but for Salomo:
    - Keeps the marker prefix during streaming (👑[Mode])
    - Updates chat_history[history_index] directly
    """
    full_response = ""
    token_count = 0
    start_time = time.time()
    ttft = None
    first_token = False

    async for chunk in llm_client.chat_stream(model, messages, options):
        if chunk["type"] == "content":
            if not first_token:
                ttft = time.time() - start_time
                first_token = True

            full_response += chunk["text"]
            token_count += 1

            # Update chat_history directly with marker + current response
            if history_index < len(state.chat_history):
                state.chat_history[history_index] = ("", f"{salomo_marker}{full_response}")

            yield  # UI Update

        elif chunk["type"] == "done":
            metrics = chunk.get("metrics", {})
            token_count = metrics.get("tokens_generated", token_count)

    # Calculate final metrics
    inference_time = time.time() - start_time
    tokens_per_sec = token_count / inference_time if inference_time > 0 else 0

    metadata = format_metadata(
        f"Inference: {format_number(inference_time, 1)}s    "
        f"{format_number(tokens_per_sec, 1)} tok/s    "
        f"Source: Salomo ({model})"
    )

    # Store result for caller
    state._stream_result = {
        "text": full_response,
        "metadata": metadata,
        "metrics": {
            "time": inference_time,
            "tokens": token_count,
            "tok_per_sec": tokens_per_sec,
            "ttft": ttft
        }
    }

    # DUAL-HISTORY: Sync Salomo response to llm_history
    # Agent-only entries become system messages with speaker label
    from .message_builder import clean_content_for_llm
    cleaned = clean_content_for_llm(full_response)
    if cleaned:
        state.llm_history.append({"role": "system", "content": f"[SALOMO]: {cleaned}"})


async def _check_compression_if_needed(
    state: 'AIState',
    llm_client: LLMClient,
    context_limit: int
) -> AsyncGenerator[None, None]:
    """
    Check if history compression is needed during multi-agent debate.

    NOTE: Main PRE-MESSAGE check runs in send_message() BEFORE multi-agent starts.
    This function handles compression DURING long debates where the debate itself
    might push context usage above threshold.

    Compression triggers at 70% of context_limit (HISTORY_COMPRESSION_TRIGGER).
    """
    try:
        # Run compression check (yields events if compression happens) - DUAL-HISTORY
        async for event in summarize_history_if_needed(
            history=state.chat_history,
            llm_client=llm_client,
            model_name=state.automatik_model_id,  # Pure model ID (not display name!)
            context_limit=context_limit,
            llm_history=state.llm_history
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
    history_index: int
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
        history_index: Index in chat_history where response should be placed
    """
    try:
        from .message_builder import clean_content_for_llm

        # Create LLM client
        llm_client = LLMClient(
            backend_type=state.backend_type,
            base_url=state.backend_url
        )

        # Determine Sokrates model
        sokrates_model = state.sokrates_model_id if state.sokrates_model_id else state.selected_model_id
        sokrates_display = state.sokrates_model if state.sokrates_model else state.selected_model
        state.add_debug(f"🏛️ Sokrates-LLM: {sokrates_display}")

        # Calculate context limit
        sokrates_num_ctx, sokrates_vram_msgs = await calculate_dynamic_num_ctx(
            llm_client, sokrates_model, [], None,
            enable_vram_limit=True
        )
        for msg in sokrates_vram_msgs:
            state.add_debug(f"   {msg}")

        # Detect language for response
        detected_lang = detect_language(user_query)

        # Load system prompt from file (no hardcoded prompts!)
        system_prompt = get_sokrates_direct_prompt(lang=detected_lang)

        # Build messages from chat history
        messages: list[dict[str, Any]] = build_messages_from_history(state.chat_history[:-1], user_query)

        # Prepend system message
        messages.insert(0, {"role": "system", "content": system_prompt})

        # Calculate Sokrates temperature based on mode
        if state.temperature_mode == "manual":
            sokrates_direct_temp = state.sokrates_temperature
        else:
            # Auto mode: AIfred's temperature + offset (capped at 1.0)
            sokrates_direct_temp = min(1.0, state.temperature + state.sokrates_temperature_offset)

        # Debug: Show context and temperature
        state.add_debug(f"📊 Context limit: {format_number(sokrates_num_ctx/1000, 3)}k")
        state.add_debug(f"🌡️ Temperature: {format_number(sokrates_direct_temp, 1)}")

        # LLM options
        sokrates_options = LLMOptions(
            temperature=sokrates_direct_temp,
            enable_thinking=state.enable_thinking,
            num_ctx=sokrates_num_ctx
        )

        # Get original user message from history (to preserve it)
        original_user_msg, _ = state.chat_history[history_index]

        # Keep user message in history with empty AI response (no AIfred panel)
        state.chat_history[history_index] = (original_user_msg, "")

        # Add Sokrates response entry with empty user (triggers Sokrates panel styling)
        sokrates_marker = "🏛️[Direkte Antwort]" if detected_lang == "de" else "🏛️[Direct Response]"
        state.chat_history.append(("", sokrates_marker))
        sokrates_index = len(state.chat_history) - 1
        yield  # Show placeholder

        # Streaming response
        full_response = ""
        token_count = 0
        start_time = time.time()
        first_token = False

        async for chunk in llm_client.chat_stream(sokrates_model, messages, sokrates_options):
            chunk_type = chunk.get("type", "")

            if chunk_type == "content":
                if not first_token:
                    ttft = time.time() - start_time
                    # Guard against negative TTFT (can happen with WSL2 time sync issues)
                    if ttft < 0:
                        log_message(f"⚠️ Negative TTFT detected: {ttft:.3f}s - possible WSL2 time sync issue")
                        ttft = 0.0
                    state.add_debug(f"⚡ TTFT: {ttft:.2f}s")
                    first_token = True

                content = chunk.get("text", "")  # Key is "text", not "content"
                full_response += content
                token_count += 1

                # Update Sokrates entry (empty user = renders as Sokrates panel)
                state.chat_history[sokrates_index] = ("", f"{sokrates_marker}{full_response}")
                yield

            elif chunk_type == "thinking":
                # Handle thinking chunks (Qwen3 thinking mode)
                thinking_content = chunk.get("text", "")  # Also "text" for thinking
                if thinking_content:
                    full_response += f"<think>{thinking_content}</think>"

            elif chunk_type == "done":
                metrics = chunk.get("metrics", {})
                token_count = metrics.get("tokens_generated", token_count)

        # Calculate final metrics
        inference_time = time.time() - start_time
        tokens_per_sec = token_count / inference_time if inference_time > 0 else 0

        # Format thinking blocks if present
        formatted_response = format_thinking_process(
            full_response,
            model_name=f"Sokrates ({sokrates_model})",
            inference_time=inference_time
        )

        # Build metadata
        metadata = format_metadata(
            f"Inference: {format_number(inference_time, 1)}s    "
            f"{format_number(tokens_per_sec, 1)} tok/s    "
            f"Source: Sokrates ({sokrates_model})"
        )

        # Final update: Sokrates in separate entry (empty user = Sokrates panel)
        final_content = f"{sokrates_marker}{formatted_response}\n\n{metadata}"
        state.chat_history[sokrates_index] = ("", final_content)

        # DUAL-HISTORY: Sync Sokrates direct response to llm_history
        cleaned = clean_content_for_llm(full_response)
        if cleaned:
            state.llm_history.append({"role": "system", "content": f"[SOKRATES]: {cleaned}"})

        # Remove the waiting message from user entry, keep only user question
        # Since Sokrates answered, no AIfred response needed
        state.chat_history[history_index] = (original_user_msg, "")

        state.add_debug(f"🏛️ Sokrates: {len(full_response)} chars, {tokens_per_sec:.1f} tok/s")

        # Separator nach Sokrates Direct Response
        console_separator()  # Log-File
        state.add_debug("────────────────────")  # Debug-Console

        await llm_client.close()
        yield

    except Exception as e:
        state.add_debug(f"❌ Sokrates Direct Response Error: {e}")
        # Put error message in Sokrates panel (empty user = Sokrates styling)
        try:
            original_user_msg, _ = state.chat_history[history_index]
            # Keep user message, clear AI response
            state.chat_history[history_index] = (original_user_msg, "")
        except (IndexError, ValueError):
            pass
        # Add error as Sokrates panel entry
        state.chat_history.append(("", f"🏛️[Error] {str(e)}"))
        yield


# ============================================================
# SOKRATES ANALYSIS
# ============================================================

async def run_sokrates_analysis(
    state: 'AIState',
    user_query: str,
    alfred_answer: str
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
    """
    state.debate_in_progress = True
    state.sokrates_critique = ""  # Clear previous
    state.debate_round = 0
    yield  # Update UI

    try:
        # Create LLM client
        llm_client = LLMClient(
            backend_type=state.backend_type,
            base_url=state.backend_url
        )

        # Determine models
        sokrates_model = state.sokrates_model_id if state.sokrates_model_id else state.selected_model_id
        sokrates_display = state.sokrates_model if state.sokrates_model else state.selected_model
        alfred_model = state.selected_model_id
        state.add_debug(f"🏛️ Sokrates-LLM: {sokrates_display}")

        # Mode labels for display (i18n)
        mode_labels = {
            "user_judge": t("multi_agent_user_judge", lang=state.ui_language),
            "auto_consensus": t("multi_agent_auto_consensus", lang=state.ui_language),
            "devils_advocate": t("multi_agent_devils_advocate", lang=state.ui_language)
        }
        mode_label = mode_labels.get(state.multi_agent_mode, state.multi_agent_mode)

        # Get context limits for both models (respect manual mode for each)
        if state.num_ctx_mode == "manual":
            # Manual mode: Use separate values for AIfred and Sokrates
            main_llm_ctx = state.num_ctx_manual if state.num_ctx_manual else 4096
            sokrates_num_ctx = state.num_ctx_manual_sokrates if state.num_ctx_manual_sokrates else 4096
            state.add_debug(f"🔧 Manual num_ctx: AIfred={main_llm_ctx:,}, Sokrates={sokrates_num_ctx:,}")
        else:
            # Auto mode: Get AIfred's limit FIRST (before Sokrates calculation could overwrite)
            # Try aifred_limit first, fall back to general limit
            aifred_cached = _last_vram_limit_cache.get("aifred_limit", 0)
            if aifred_cached == 0:
                aifred_cached = _last_vram_limit_cache.get("limit", 0)
            main_llm_ctx = aifred_cached if aifred_cached > 0 else 32768
            if aifred_cached == 0:
                state.add_debug("⚠️ No cached AIfred VRAM limit found, using fallback 32K")

            # THEN calculate VRAM limit for Sokrates model
            sokrates_num_ctx, sokrates_vram_msgs = await calculate_dynamic_num_ctx(
                llm_client, sokrates_model, [], None,
                enable_vram_limit=True
            )
            for vram_msg in sokrates_vram_msgs:
                state.add_debug(f"   {vram_msg}")  # Indent to show it's for Sokrates

        # Store separate limits for each agent
        _last_vram_limit_cache["aifred_limit"] = main_llm_ctx
        _last_vram_limit_cache["sokrates_limit"] = sokrates_num_ctx

        # Update global limit with MINIMUM of both (for history compression)
        min_ctx = min(sokrates_num_ctx, main_llm_ctx)
        _last_vram_limit_cache["limit"] = min_ctx
        state.add_debug(
            f"📊 Context limits: AIfred={format_number(main_llm_ctx/1000, 3)}k, "
            f"Sokrates={format_number(sokrates_num_ctx/1000, 3)}k, "
            f"Compression={format_number(min_ctx/1000, 3)}k"
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
        sokrates_options = LLMOptions(
            temperature=sokrates_temp,
            enable_thinking=state.enable_thinking,  # Use global thinking toggle
            num_ctx=sokrates_num_ctx
        )
        alfred_options = LLMOptions(
            temperature=alfred_temp,
            enable_thinking=state.enable_thinking,  # Use global thinking toggle
            num_ctx=main_llm_ctx
        )

        # Track current answer (may be refined in auto_consensus)
        current_answer = alfred_answer
        consensus_reached = False
        max_rounds = state.max_debate_rounds if state.multi_agent_mode == "auto_consensus" else 1

        for round_num in range(1, max_rounds + 1):
            state.debate_round = round_num

            # === SOKRATES CRITIQUE ===
            # Get system prompts: minimal (base personality) + mode-specific
            sokrates_minimal = get_sokrates_system_minimal()
            if state.multi_agent_mode == "devils_advocate":
                mode_prompt = get_sokrates_devils_advocate_prompt()
            else:
                # Critic prompt for all other modes (Sokrates never says LGTM)
                # round_num prevents hallucinating "progress" in round 1
                mode_prompt = get_sokrates_critic_prompt(round_num=round_num)

            # Combine: minimal first, then mode-specific
            system_prompt = f"{sokrates_minimal}\n\n{mode_prompt}"

            # Build messages with Sokrates' perspective
            # - Sokrates sees his own earlier responses as 'assistant'
            # - AIfred's responses and User messages become 'user' with labels
            # - No "Sokrates?" activation needed - perspective handles role assignment
            history_messages: list[dict[str, str]] = build_messages_from_history(
                state.chat_history,
                perspective="sokrates"
            )

            # Build final message list: Sokrates system prompt + history
            sokrates_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
            for msg in history_messages:
                # Keep all messages except non-summary system messages
                if msg["role"] != "system" or "Compressed:" in msg.get("content", ""):
                    sokrates_messages.append(msg)

            # PRE-SOKRATES: Check if compression needed before Sokrates call
            async for _ in _check_compression_if_needed(state, llm_client, min_ctx):
                yield

            # Add placeholder for Sokrates
            # Minimal marker for UI detection (🏛️), mode info stored in metadata
            round_suffix = f" R{round_num}" if max_rounds > 1 else ""
            sokrates_marker = f"🏛️[{mode_label}{round_suffix}]"  # Marker for UI parsing
            state.chat_history.append(("", sokrates_marker))
            sokrates_index = len(state.chat_history) - 1
            yield  # Show placeholder

            # Estimate tokens in messages (using proper tokenizer estimation)
            sokrates_msg_tokens = estimate_tokens(sokrates_messages, model_name=sokrates_model)
            sokrates_ctx = sokrates_options.num_ctx if sokrates_options and sokrates_options.num_ctx else 8192
            state.add_debug(
                f"📊 Sokrates R{round_num}: {format_number(sokrates_msg_tokens)} / "
                f"{format_number(sokrates_ctx)} tokens"
            )

            # Stream Sokrates response
            async for _ in _stream_sokrates_to_history(
                state=state,
                llm_client=llm_client,
                model=sokrates_model,
                messages=sokrates_messages,
                options=sokrates_options,
                history_index=sokrates_index,
                sokrates_marker=sokrates_marker
            ):
                yield  # Forward UI updates

            # Get Sokrates result
            result = state._stream_result
            sokrates_response_text = result["text"]
            metadata = result["metadata"]
            metrics = result["metrics"]

            state.add_debug(
                f"🏛️ Sokrates R{round_num}: {len(sokrates_response_text)} chars, "
                f"{metrics['tok_per_sec']:.1f} tok/s"
            )

            # Format <think> tags as collapsible (if present)
            formatted_sokrates = format_thinking_process(
                sokrates_response_text,
                model_name=f"Sokrates ({sokrates_model})",
                inference_time=metrics.get("time", 0)
            )

            # Final update with metadata
            # Format: "🏛️[Mode]Content\n\nMetadata" - UI parses mode from bracket
            final_content = f"{sokrates_marker}{formatted_sokrates}\n\n{metadata}"
            state.chat_history[sokrates_index] = ("", final_content)
            state.sokrates_critique = sokrates_response_text  # Keep raw text for logic checks
            yield

            # NOTE: PRE-CHECK before Sokrates already handles compression (line ~635)
            # No POST-CHECK needed here

            # Parse Pro/Contra for devils_advocate
            if state.multi_agent_mode == "devils_advocate":
                state.sokrates_pro_args, state.sokrates_contra_args = parse_pro_contra(sokrates_response_text)
                break  # Devils advocate is always one round

            # For user_judge: only one round (user decides)
            if state.multi_agent_mode == "user_judge":
                break

            # === AUTO-CONSENSUS (TRIALOG): Salomo synthesizes and decides ===
            if state.multi_agent_mode == "auto_consensus":
                # Determine Salomo model
                salomo_model = state.salomo_model_id if state.salomo_model_id else state.selected_model_id
                salomo_display = state.salomo_model if state.salomo_model else state.selected_model

                if round_num == 1:
                    state.add_debug(f"👑 Salomo-LLM: {salomo_display}")

                # Calculate Salomo context
                if state.num_ctx_mode == "manual":
                    salomo_num_ctx = state.num_ctx_manual_salomo if hasattr(state, 'num_ctx_manual_salomo') else 4096
                else:
                    salomo_num_ctx, _ = await calculate_dynamic_num_ctx(
                        llm_client, salomo_model, [], None,
                        enable_vram_limit=True
                    )

                # salomo_temp already calculated above (before the loop)
                salomo_options = LLMOptions(
                    temperature=salomo_temp,
                    enable_thinking=state.enable_thinking,
                    num_ctx=salomo_num_ctx
                )

                # Build Salomo's messages: system + history
                salomo_minimal = get_salomo_system_minimal()
                mediator_prompt = get_salomo_mediator_prompt(round_num=round_num)
                salomo_system = f"{salomo_minimal}\n\n{mediator_prompt}"

                # Build messages with observer perspective (sees everything neutrally)
                salomo_messages: list[dict[str, str]] = build_messages_from_history(
                    state.chat_history,
                    perspective="observer"  # Neutral perspective
                )
                salomo_messages.insert(0, {"role": "system", "content": salomo_system})

                # PRE-SALOMO: Check if compression needed before Salomo call
                async for _ in _check_compression_if_needed(state, llm_client, min_ctx):
                    yield

                # Add placeholder for Salomo
                salomo_marker = f"👑[{t('salomo_synthesis_label', lang=state.ui_language).rstrip(':')} R{round_num}]"
                state.chat_history.append(("", salomo_marker))
                salomo_index = len(state.chat_history) - 1
                yield

                # Stream Salomo response
                async for _ in _stream_salomo_to_history(
                    state=state,
                    llm_client=llm_client,
                    model=salomo_model,
                    messages=salomo_messages,
                    options=salomo_options,
                    history_index=salomo_index,
                    salomo_marker=salomo_marker
                ):
                    yield

                # Get Salomo result
                salomo_result = state._stream_result
                salomo_response_text = salomo_result["text"]
                salomo_metadata = salomo_result["metadata"]
                salomo_metrics = salomo_result["metrics"]

                state.add_debug(
                    f"👑 Salomo R{round_num}: {len(salomo_response_text)} chars, "
                    f"{salomo_metrics['tok_per_sec']:.1f} tok/s"
                )

                # Format <think> tags as collapsible
                formatted_salomo = format_thinking_process(
                    salomo_response_text,
                    model_name=f"Salomo ({salomo_model})",
                    inference_time=salomo_metrics.get("time", 0)
                )

                # Final update with metadata
                final_salomo = f"{salomo_marker}{formatted_salomo}\n\n{salomo_metadata}"
                state.chat_history[salomo_index] = ("", final_salomo)
                state.salomo_synthesis = salomo_response_text
                yield

                # NOTE: PRE-CHECK before next agent handles compression
                # No POST-CHECK needed here

                # Check for LGTM from Salomo (not Sokrates!)
                salomo_content = strip_thinking_blocks(salomo_response_text).strip()
                if "LGTM" in salomo_content.upper():
                    state.add_debug(f"✅ Consensus reached in round {round_num} (Salomo: LGTM)")
                    consensus_reached = True
                    break

                # If no LGTM and more rounds available: AIfred refines based on Salomo's feedback
                if round_num < max_rounds:
                    # PRE-AIFRED: Check if compression needed before AIfred refinement
                    async for _ in _check_compression_if_needed(state, llm_client, min_ctx):
                        yield

                    # Build refinement prompt using Salomo's synthesis (not Sokrates' critique)
                    refinement_prompt = get_sokrates_refinement_prompt(
                        critique=salomo_response_text,  # Use Salomo's synthesis as guidance
                        user_interjection=""
                    )

                    # Build messages with AIfred's perspective
                    alfred_messages: list[dict[str, str]] = build_messages_from_history(
                        state.chat_history,
                        current_user_text=refinement_prompt,
                        perspective="aifred"
                    )

                    # Estimate tokens
                    alfred_msg_tokens = estimate_tokens(alfred_messages, model_name=state.selected_model_id)
                    alfred_ctx = alfred_options.num_ctx if alfred_options and alfred_options.num_ctx else 32768
                    state.add_debug(
                        f"📊 AIfred R{round_num + 1}: {format_number(alfred_msg_tokens)} / "
                        f"{format_number(alfred_ctx)} tokens"
                    )

                    # Add placeholder for AIfred refinement
                    alfred_marker = f"🎩[Refinement R{round_num + 1}]"
                    state.chat_history.append(("", alfred_marker))
                    alfred_index = len(state.chat_history) - 1
                    yield

                    # Stream AIfred refinement
                    async for _ in _stream_alfred_refinement(
                        state=state,
                        llm_client=llm_client,
                        model=alfred_model,
                        messages=alfred_messages,
                        options=alfred_options,
                        history_index=alfred_index,
                        alfred_marker=alfred_marker
                    ):
                        yield

                    # Get refined answer
                    alfred_result = state._stream_result
                    current_answer = alfred_result["text"]
                    alfred_metadata = alfred_result["metadata"]
                    alfred_metrics = alfred_result.get("metrics", {})

                    # Format <think> tags as collapsible
                    formatted_alfred = format_thinking_process(
                        current_answer,
                        model_name=f"AIfred ({alfred_model})",
                        inference_time=alfred_metrics.get("time", 0)
                    )

                    # Update history with metadata
                    final_alfred = f"{alfred_marker}{formatted_alfred}\n\n{alfred_metadata}"
                    state.chat_history[alfred_index] = ("", final_alfred)

                    state.add_debug(
                        f"🎩 AIfred R{round_num + 1}: {len(current_answer)} chars, "
                        f"{alfred_metrics.get('tok_per_sec', 0):.1f} tok/s"
                    )
                    yield

                    # NOTE: PRE-CHECK before next iteration handles compression
                    # No POST-CHECK needed here

        # End of debate
        if state.multi_agent_mode == "auto_consensus":
            if consensus_reached:
                state.add_debug(f"🎯 Debate finished: consensus after {state.debate_round} rounds")
            else:
                state.add_debug(f"⚠️ Debate finished: max {max_rounds} rounds without consensus")

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
    alfred_answer: str
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
    """
    state.debate_in_progress = True
    state.sokrates_critique = ""
    state.salomo_synthesis = ""
    state.debate_round = 0
    yield

    try:
        # Create LLM client
        llm_client = LLMClient(
            backend_type=state.backend_type,
            base_url=state.backend_url
        )

        # Determine models
        sokrates_model = state.sokrates_model_id if state.sokrates_model_id else state.selected_model_id
        sokrates_display = state.sokrates_model if state.sokrates_model else state.selected_model
        salomo_model = state.salomo_model_id if state.salomo_model_id else state.selected_model_id
        salomo_display = state.salomo_model if state.salomo_model else state.selected_model
        alfred_model = state.selected_model_id

        state.add_debug("⚖️ Tribunal mode started")
        state.add_debug(f"🏛️ Sokrates LLM: {sokrates_display}")
        state.add_debug(f"👑 Salomo LLM: {salomo_display}")

        # Get context limits
        if state.num_ctx_mode == "manual":
            main_llm_ctx = state.num_ctx_manual if state.num_ctx_manual else 4096
            sokrates_num_ctx = state.num_ctx_manual_sokrates if state.num_ctx_manual_sokrates else 4096
            salomo_num_ctx = state.num_ctx_manual_salomo if state.num_ctx_manual_salomo else 4096
            state.add_debug(f"🔧 Manual num_ctx: AIfred={main_llm_ctx:,}, Sokrates={sokrates_num_ctx:,}, Salomo={salomo_num_ctx:,}")
        else:
            aifred_cached = _last_vram_limit_cache.get("aifred_limit", 0)
            if aifred_cached == 0:
                aifred_cached = _last_vram_limit_cache.get("limit", 0)
            main_llm_ctx = aifred_cached if aifred_cached > 0 else 32768

            sokrates_num_ctx, _ = await calculate_dynamic_num_ctx(
                llm_client, sokrates_model, [], None, enable_vram_limit=True
            )
            salomo_num_ctx, _ = await calculate_dynamic_num_ctx(
                llm_client, salomo_model, [], None, enable_vram_limit=True
            )

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

        sokrates_options = LLMOptions(
            temperature=sokrates_temp,
            enable_thinking=state.enable_thinking,
            num_ctx=sokrates_num_ctx
        )
        alfred_options = LLMOptions(
            temperature=alfred_temp,
            enable_thinking=state.enable_thinking,
            num_ctx=main_llm_ctx
        )
        salomo_options = LLMOptions(
            temperature=salomo_temp,
            enable_thinking=state.enable_thinking,
            num_ctx=salomo_num_ctx
        )

        # Debug: Show context limits and temperatures
        state.add_debug(
            f"📊 Context limits: AIfred={format_number(main_llm_ctx/1000, 3)}k, "
            f"Sokrates={format_number(sokrates_num_ctx/1000, 3)}k, "
            f"Salomo={format_number(salomo_num_ctx/1000, 3)}k, "
            f"Compression={format_number(min_ctx/1000, 3)}k"
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

            # PRE-SOKRATES: Check if compression needed before Sokrates call
            async for _ in _check_compression_if_needed(state, llm_client, min_ctx):
                yield

            # --- SOKRATES CRITIQUE ---
            sokrates_minimal = get_sokrates_system_minimal()
            mode_prompt = get_sokrates_critic_prompt(round_num=round_num)
            system_prompt = f"{sokrates_minimal}\n\n{mode_prompt}"

            history_messages = build_messages_from_history(
                state.chat_history,
                perspective="sokrates"
            )
            sokrates_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
            for msg in history_messages:
                if msg["role"] != "system" or "Compressed:" in msg.get("content", ""):
                    sokrates_messages.append(msg)

            sokrates_marker = f"🏛️[Tribunal R{round_num}]"
            state.chat_history.append(("", sokrates_marker))
            sokrates_index = len(state.chat_history) - 1
            yield

            async for _ in _stream_sokrates_to_history(
                state=state,
                llm_client=llm_client,
                model=sokrates_model,
                messages=sokrates_messages,
                options=sokrates_options,
                history_index=sokrates_index,
                sokrates_marker=sokrates_marker
            ):
                yield

            result = state._stream_result
            sokrates_response_text = result["text"]
            metadata = result["metadata"]
            metrics = result["metrics"]

            state.add_debug(
                f"🏛️ Sokrates R{round_num}: {len(sokrates_response_text)} chars, "
                f"{metrics['tok_per_sec']:.1f} tok/s"
            )

            formatted_sokrates = format_thinking_process(
                sokrates_response_text,
                model_name=f"Sokrates ({sokrates_model})",
                inference_time=metrics.get("time", 0)
            )
            final_content = f"{sokrates_marker}{formatted_sokrates}\n\n{metadata}"
            state.chat_history[sokrates_index] = ("", final_content)
            state.sokrates_critique = sokrates_response_text
            yield

            # NOTE: PRE-CHECK before next agent handles compression
            # No POST-CHECK needed here

            # --- AIFRED RESPONSE (if not last round) ---
            if round_num < max_rounds:
                # PRE-AIFRED: Check if compression needed before AIfred refinement
                async for _ in _check_compression_if_needed(state, llm_client, min_ctx):
                    yield

                refinement_prompt = get_sokrates_refinement_prompt(
                    critique=sokrates_response_text,
                    user_interjection=""
                )

                alfred_messages: list[dict[str, str]] = build_messages_from_history(
                    state.chat_history,
                    current_user_text=refinement_prompt,
                    perspective="aifred"
                )

                alfred_marker = f"🎩[Tribunal R{round_num + 1}]"
                state.chat_history.append(("", alfred_marker))
                alfred_index = len(state.chat_history) - 1
                yield

                async for _ in _stream_alfred_refinement(
                    state=state,
                    llm_client=llm_client,
                    model=alfred_model,
                    messages=alfred_messages,
                    options=alfred_options,
                    history_index=alfred_index,
                    alfred_marker=alfred_marker
                ):
                    yield

                alfred_result = state._stream_result
                current_answer = alfred_result["text"]
                alfred_metadata = alfred_result["metadata"]
                alfred_metrics = alfred_result.get("metrics", {})

                formatted_alfred = format_thinking_process(
                    current_answer,
                    model_name=f"AIfred ({alfred_model})",
                    inference_time=alfred_metrics.get("time", 0)
                )
                final_alfred = f"{alfred_marker}{formatted_alfred}\n\n{alfred_metadata}"
                state.chat_history[alfred_index] = ("", final_alfred)

                state.add_debug(
                    f"🎩 AIfred R{round_num + 1}: {len(current_answer)} chars, "
                    f"{alfred_metrics.get('tok_per_sec', 0):.1f} tok/s"
                )
                yield

                # NOTE: PRE-CHECK in next iteration handles compression
                # No POST-CHECK needed here

        # === JUDGMENT PHASE: Salomo delivers final verdict ===
        # PRE-SALOMO: Check if compression needed before Salomo verdict
        async for _ in _check_compression_if_needed(state, llm_client, min_ctx):
            yield

        state.add_debug("👑 Salomo rendering verdict...")

        salomo_minimal = get_salomo_system_minimal()
        judge_prompt = get_salomo_judge_prompt()
        salomo_system = f"{salomo_minimal}\n\n{judge_prompt}"

        salomo_messages: list[dict[str, str]] = build_messages_from_history(
            state.chat_history,
            perspective="observer"
        )
        salomo_messages.insert(0, {"role": "system", "content": salomo_system})

        salomo_marker = f"👑[{t('salomo_verdict_label', lang=state.ui_language).rstrip(':')}]"
        state.chat_history.append(("", salomo_marker))
        salomo_index = len(state.chat_history) - 1
        yield

        async for _ in _stream_salomo_to_history(
            state=state,
            llm_client=llm_client,
            model=salomo_model,
            messages=salomo_messages,
            options=salomo_options,
            history_index=salomo_index,
            salomo_marker=salomo_marker
        ):
            yield

        salomo_result = state._stream_result
        salomo_response_text = salomo_result["text"]
        salomo_metadata = salomo_result["metadata"]
        salomo_metrics = salomo_result["metrics"]

        state.add_debug(
            f"👑 Salomo Verdict: {len(salomo_response_text)} chars, "
            f"{salomo_metrics['tok_per_sec']:.1f} tok/s"
        )

        formatted_salomo = format_thinking_process(
            salomo_response_text,
            model_name=f"Salomo ({salomo_model})",
            inference_time=salomo_metrics.get("time", 0)
        )
        final_salomo = f"{salomo_marker}{formatted_salomo}\n\n{salomo_metadata}"
        state.chat_history[salomo_index] = ("", final_salomo)
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
