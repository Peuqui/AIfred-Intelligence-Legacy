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
from .message_builder import build_messages_from_llm_history
from .i18n import t
from .context_manager import (
    calculate_dynamic_num_ctx,
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
    get_salomo_system_minimal,
    get_salomo_direct_prompt,
    get_salomo_mediator_prompt,
    get_salomo_judge_prompt,
)
from .logging_utils import log_message, console_separator
from .config import DEBUG_LOG_RAW_MESSAGES
from ..backends.base import LLMOptions


def _log_raw_messages(agent_name: str, round_num: int, messages: list) -> None:
    """
    Log RAW messages sent to an LLM (debug.log only).

    Only logs when DEBUG_LOG_RAW_MESSAGES is True in config.py.
    Useful for debugging prompt injection and agent confusion issues.
    """
    if not DEBUG_LOG_RAW_MESSAGES:
        return

    log_message(f"📤 [RAW] {agent_name} R{round_num} - {len(messages)} messages:")
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        preview = content[:200].replace("\n", "\\n") if content else ""
        log_message(f"   [{i}] role={role}, len={len(content)}: {preview}...")

if TYPE_CHECKING:
    from ..state import AIState


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
        return lgtm_count == 3  # All must agree
    else:  # majority
        return lgtm_count >= 2  # 2/3 is enough


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
    ttft = 0.0
    first_token = False

    async for chunk in llm_client.chat_stream(model, messages, options):
        if chunk["type"] == "content":
            if not first_token:
                ttft = time.time() - start_time
                log_message(f"⚡ Sokrates TTFT: {format_number(ttft, 2)}s")
                state.add_debug(f"⚡ TTFT: {format_number(ttft, 2)}s")
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

    # Log completion metrics (include chars for complete info)
    log_message(f"✅ Sokrates done ({format_number(inference_time, 1)}s, {token_count} tok, {format_number(tokens_per_sec, 1)} tok/s, {len(full_response)} chars)")
    state.add_debug(f"✅ Sokrates done ({format_number(inference_time, 1)}s, {token_count} tok, {format_number(tokens_per_sec, 1)} tok/s, {len(full_response)} chars)")

    metadata = format_metadata(
        f"TTFT: {format_number(ttft, 2)}s    "
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
    # Agent responses are assistant messages with speaker label (NOT system!)
    cleaned = strip_thinking_blocks(full_response)
    if cleaned:
        state.llm_history.append({"role": "assistant", "content": f"[SOKRATES]: {cleaned}"})


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
    ttft = 0.0
    first_token = False

    async for chunk in llm_client.chat_stream(model, messages, options):
        if chunk["type"] == "content":
            if not first_token:
                ttft = time.time() - start_time
                log_message(f"⚡ AIfred Refinement TTFT: {format_number(ttft, 2)}s")
                state.add_debug(f"⚡ TTFT: {format_number(ttft, 2)}s")
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

    # Log completion metrics (include chars for complete info)
    log_message(f"✅ AIfred Refinement done ({format_number(inference_time, 1)}s, {token_count} tok, {format_number(tokens_per_sec, 1)} tok/s, {len(full_response)} chars)")
    state.add_debug(f"✅ AIfred Refinement done ({format_number(inference_time, 1)}s, {token_count} tok, {format_number(tokens_per_sec, 1)} tok/s, {len(full_response)} chars)")

    metadata = format_metadata(
        f"TTFT: {format_number(ttft, 2)}s    "
        f"Inference: {format_number(inference_time, 1)}s    "
        f"{format_number(tokens_per_sec, 1)} tok/s    "
        f"Source: AIfred ({model})"
    )

    state._stream_result = {
        "text": full_response,
        "metadata": metadata,
        "metrics": {"time": inference_time, "tokens": token_count, "tok_per_sec": tokens_per_sec, "ttft": ttft}
    }

    # DUAL-HISTORY: Sync AIfred refinement to llm_history
    # Agent responses are assistant messages with speaker label (NOT system!)
    cleaned = strip_thinking_blocks(full_response)
    if cleaned:
        state.llm_history.append({"role": "assistant", "content": f"[AIFRED]: {cleaned}"})


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
    ttft = 0.0
    first_token = False

    async for chunk in llm_client.chat_stream(model, messages, options):
        if chunk["type"] == "content":
            if not first_token:
                ttft = time.time() - start_time
                log_message(f"⚡ Salomo TTFT: {format_number(ttft, 2)}s")
                state.add_debug(f"⚡ TTFT: {format_number(ttft, 2)}s")
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

    # Log completion metrics (include chars for complete info)
    log_message(f"✅ Salomo done ({format_number(inference_time, 1)}s, {token_count} tok, {format_number(tokens_per_sec, 1)} tok/s, {len(full_response)} chars)")
    state.add_debug(f"✅ Salomo done ({format_number(inference_time, 1)}s, {token_count} tok, {format_number(tokens_per_sec, 1)} tok/s, {len(full_response)} chars)")

    metadata = format_metadata(
        f"TTFT: {format_number(ttft, 2)}s    "
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
    # Agent responses are assistant messages with speaker label (NOT system!)
    cleaned = strip_thinking_blocks(full_response)
    if cleaned:
        state.llm_history.append({"role": "assistant", "content": f"[SALOMO]: {cleaned}"})


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
    history_index: int,
    detected_lang: str = "en"
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
        detected_lang: Language detected by LLM intent detection ("de" or "en")
    """
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

        # Calculate context limit
        sokrates_num_ctx, sokrates_vram_msgs = await calculate_dynamic_num_ctx(
            llm_client, sokrates_model, [], None,
            enable_vram_limit=True
        )
        for msg in sokrates_vram_msgs:
            state.add_debug(f"   {msg}")

        # Load system prompt from file (no hardcoded prompts!)
        # detected_lang comes from LLM-based intent detection (passed from state.py)
        system_prompt = get_sokrates_direct_prompt(lang=detected_lang)

        # Build messages from LLM history with Sokrates perspective
        # Sokrates sees his own messages as 'assistant', others as 'user'
        messages: list[dict[str, Any]] = build_messages_from_llm_history(
            state.llm_history[:-1],
            user_query,
            perspective="sokrates"
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
        sokrates_ttft = 0.0

        async for chunk in llm_client.chat_stream(sokrates_model, messages, sokrates_options):
            chunk_type = chunk.get("type", "")

            if chunk_type == "content":
                if not first_token:
                    ttft = time.time() - start_time
                    # Guard against negative TTFT (can happen with WSL2 time sync issues)
                    if ttft < 0:
                        log_message(f"⚠️ Negative TTFT detected: {format_number(ttft, 3)}s - possible WSL2 time sync issue")
                        ttft = 0.0
                    log_message(f"⚡ Sokrates TTFT: {format_number(ttft, 2)}s")
                    state.add_debug(f"⚡ TTFT: {format_number(ttft, 2)}s")
                    first_token = True
                    sokrates_ttft = ttft  # Save for metadata

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

        # Log completion metrics (include chars for complete info)
        log_message(f"✅ Sokrates done ({format_number(inference_time, 1)}s, {token_count} tok, {format_number(tokens_per_sec, 1)} tok/s, {len(full_response)} chars)")
        state.add_debug(f"✅ Sokrates done ({format_number(inference_time, 1)}s, {token_count} tok, {format_number(tokens_per_sec, 1)} tok/s, {len(full_response)} chars)")

        # Format thinking blocks if present
        formatted_response = format_thinking_process(
            full_response,
            model_name=f"Sokrates ({sokrates_model})",
            inference_time=inference_time
        )

        # Build metadata (with TTFT like AIfred)
        metadata = format_metadata(
            f"TTFT: {format_number(sokrates_ttft, 2)}s    "
            f"Inference: {format_number(inference_time, 1)}s    "
            f"{format_number(tokens_per_sec, 1)} tok/s    "
            f"Source: Sokrates ({sokrates_model})"
        )

        # Final update: Sokrates in separate entry (empty user = Sokrates panel)
        final_content = f"{sokrates_marker}{formatted_response}\n\n{metadata}"
        state.chat_history[sokrates_index] = ("", final_content)

        # DUAL-HISTORY: Sync Sokrates direct response to llm_history
        # Agent responses are assistant messages with speaker label (NOT system!)
        cleaned = strip_thinking_blocks(full_response)
        if cleaned:
            state.llm_history.append({"role": "assistant", "content": f"[SOKRATES]: {cleaned}"})

        # Remove the waiting message from user entry, keep only user question
        # Since Sokrates answered, no AIfred response needed
        state.chat_history[history_index] = (original_user_msg, "")

        # INCREMENTAL SAVE: Persist after response to survive browser refresh
        state._save_current_session()

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
# SALOMO DIRECT RESPONSE
# ============================================================

async def run_salomo_direct_response(
    state: 'AIState',
    user_query: str,
    history_index: int,
    detected_lang: str = "en"
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
        history_index: Index in chat_history where response should be placed
        detected_lang: Language detected by LLM intent detection ("de" or "en")
    """
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

        # Calculate context limit
        salomo_num_ctx, salomo_vram_msgs = await calculate_dynamic_num_ctx(
            llm_client, salomo_model, [], None,
            enable_vram_limit=True
        )
        for msg in salomo_vram_msgs:
            state.add_debug(f"   {msg}")

        # Load system prompt from file (no hardcoded prompts!)
        # detected_lang comes from LLM-based intent detection (passed from state.py)
        system_prompt = get_salomo_direct_prompt(lang=detected_lang)

        # Build messages from LLM history with Salomo perspective
        # Salomo sees his own messages as 'assistant', others as 'user'
        messages: list[dict[str, Any]] = build_messages_from_llm_history(
            state.llm_history[:-1],
            user_query,
            perspective="salomo"
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
        state.add_debug(f"📊 Context limit: {format_number(salomo_num_ctx/1000, 3)}k")
        state.add_debug(f"🌡️ Temperature: {format_number(salomo_direct_temp, 1)}")

        # LLM options
        salomo_options = LLMOptions(
            temperature=salomo_direct_temp,
            enable_thinking=state.enable_thinking,
            num_ctx=salomo_num_ctx
        )

        # Get original user message from history (to preserve it)
        original_user_msg, _ = state.chat_history[history_index]

        # Keep user message in history with empty AI response (no AIfred panel)
        state.chat_history[history_index] = (original_user_msg, "")

        # Add Salomo response entry with empty user (triggers Salomo panel styling)
        salomo_marker = "👑[Direkte Antwort]" if detected_lang == "de" else "👑[Direct Response]"
        state.chat_history.append(("", salomo_marker))
        salomo_index = len(state.chat_history) - 1
        yield  # Show placeholder

        # Streaming response
        full_response = ""
        token_count = 0
        start_time = time.time()
        first_token = False
        salomo_ttft = 0.0

        async for chunk in llm_client.chat_stream(salomo_model, messages, salomo_options):
            chunk_type = chunk.get("type", "")

            if chunk_type == "content":
                if not first_token:
                    ttft = time.time() - start_time
                    # Guard against negative TTFT (can happen with WSL2 time sync issues)
                    if ttft < 0:
                        log_message(f"⚠️ Negative TTFT detected: {format_number(ttft, 3)}s - possible WSL2 time sync issue")
                        ttft = 0.0
                    log_message(f"⚡ Salomo TTFT: {format_number(ttft, 2)}s")
                    state.add_debug(f"⚡ TTFT: {format_number(ttft, 2)}s")
                    first_token = True
                    salomo_ttft = ttft  # Save for metadata

                content = chunk.get("text", "")  # Key is "text", not "content"
                full_response += content
                token_count += 1

                # Update Salomo entry (empty user = renders as Salomo panel)
                state.chat_history[salomo_index] = ("", f"{salomo_marker}{full_response}")
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

        # Log completion metrics (include chars for complete info)
        log_message(f"✅ Salomo done ({format_number(inference_time, 1)}s, {token_count} tok, {format_number(tokens_per_sec, 1)} tok/s, {len(full_response)} chars)")
        state.add_debug(f"✅ Salomo done ({format_number(inference_time, 1)}s, {token_count} tok, {format_number(tokens_per_sec, 1)} tok/s, {len(full_response)} chars)")

        # Format thinking blocks if present
        formatted_response = format_thinking_process(
            full_response,
            model_name=f"Salomo ({salomo_model})",
            inference_time=inference_time
        )

        # Build metadata (with TTFT like AIfred)
        metadata = format_metadata(
            f"TTFT: {format_number(salomo_ttft, 2)}s    "
            f"Inference: {format_number(inference_time, 1)}s    "
            f"{format_number(tokens_per_sec, 1)} tok/s    "
            f"Source: Salomo ({salomo_model})"
        )

        # Final update: Salomo in separate entry (empty user = Salomo panel)
        final_content = f"{salomo_marker}{formatted_response}\n\n{metadata}"
        state.chat_history[salomo_index] = ("", final_content)

        # DUAL-HISTORY: Sync Salomo direct response to llm_history
        # Agent responses are assistant messages with speaker label (NOT system!)
        cleaned = strip_thinking_blocks(full_response)
        if cleaned:
            state.llm_history.append({"role": "assistant", "content": f"[SALOMO]: {cleaned}"})

        # Remove the waiting message from user entry, keep only user question
        # Since Salomo answered, no AIfred response needed
        state.chat_history[history_index] = (original_user_msg, "")

        # INCREMENTAL SAVE: Persist after response to survive browser refresh
        state._save_current_session()

        # Separator nach Salomo Direct Response
        console_separator()  # Log-File
        state.add_debug("────────────────────")  # Debug-Console

        await llm_client.close()
        yield

    except Exception as e:
        state.add_debug(f"❌ Salomo Direct Response Error: {e}")
        # Put error message in Salomo panel (empty user = Salomo styling)
        try:
            original_user_msg, _ = state.chat_history[history_index]
            # Keep user message, clear AI response
            state.chat_history[history_index] = (original_user_msg, "")
        except (IndexError, ValueError):
            pass
        # Add error as Salomo panel entry
        state.chat_history.append(("", f"👑[Error] {str(e)}"))
        yield


# ============================================================
# SOKRATES ANALYSIS
# ============================================================

async def run_sokrates_analysis(
    state: 'AIState',
    user_query: str,
    alfred_answer: str,
    detected_lang: str = "en"
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
    """
    state.debate_in_progress = True
    state.sokrates_critique = ""  # Clear previous
    state.debate_round = 0
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
        # AIfred context
        if getattr(state, 'num_ctx_manual_aifred_enabled', False):
            main_llm_ctx = state.num_ctx_manual if state.num_ctx_manual else 4096
            state.add_debug(f"🔧 AIfred num_ctx: {main_llm_ctx:,} (manual)")
        else:
            # Auto mode: Get AIfred's limit from cache
            aifred_cached = _last_vram_limit_cache.get("aifred_limit", 0)
            if aifred_cached == 0:
                aifred_cached = _last_vram_limit_cache.get("limit", 0)
            main_llm_ctx = aifred_cached if aifred_cached > 0 else 32768
            if aifred_cached == 0:
                state.add_debug("⚠️ No cached AIfred VRAM limit found, using fallback 32K")

        # Import VRAM cache functions (used for all agents in auto mode)
        from .model_vram_cache import get_ollama_calibration, get_rope_factor_for_model

        # Sokrates context - read from VRAM cache
        if getattr(state, 'num_ctx_manual_sokrates_enabled', False):
            sokrates_num_ctx = state.num_ctx_manual_sokrates if state.num_ctx_manual_sokrates else 4096
            state.add_debug(f"🔧 Sokrates num_ctx: {sokrates_num_ctx:,} (manual)")
        else:
            # Read from VRAM cache (already calibrated)
            rope_factor = get_rope_factor_for_model(sokrates_model)
            sokrates_num_ctx = get_ollama_calibration(sokrates_model, rope_factor)
            if sokrates_num_ctx:
                state.add_debug(f"   🎯 Calibrated: {sokrates_num_ctx:,} tok (from VRAM cache)")
            else:
                sokrates_num_ctx = 32768  # Fallback if not calibrated
                state.add_debug("⚠️ Sokrates model not calibrated, using fallback 32K")

        # Salomo context - read from VRAM cache
        salomo_model = state.salomo_model_id if state.salomo_model_id else state.aifred_model_id
        if getattr(state, 'num_ctx_manual_salomo_enabled', False):
            salomo_num_ctx = state.num_ctx_manual_salomo if hasattr(state, 'num_ctx_manual_salomo') else 4096
            state.add_debug(f"🔧 Salomo num_ctx: {salomo_num_ctx:,} (manual)")
        else:
            # Read from VRAM cache (already calibrated)
            rope_factor = get_rope_factor_for_model(salomo_model)
            salomo_num_ctx = get_ollama_calibration(salomo_model, rope_factor)
            if not salomo_num_ctx:
                salomo_num_ctx = 32768  # Fallback if not calibrated

        # Store separate limits for each agent
        _last_vram_limit_cache["aifred_limit"] = main_llm_ctx
        _last_vram_limit_cache["sokrates_limit"] = sokrates_num_ctx
        _last_vram_limit_cache["salomo_limit"] = salomo_num_ctx

        # Update global limit with MINIMUM of all (for history compression)
        min_ctx = min(sokrates_num_ctx, main_llm_ctx, salomo_num_ctx)
        _last_vram_limit_cache["limit"] = min_ctx
        state.add_debug(
            f"📊 Context limits: AIfred={format_number(main_llm_ctx/1000, 3)}k, "
            f"Sokrates={format_number(sokrates_num_ctx/1000, 3)}k, "
            f"Salomo={format_number(salomo_num_ctx/1000, 3)}k, "
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
            sokrates_minimal = get_sokrates_system_minimal(lang=detected_lang)
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
                perspective="sokrates"
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

            # DEBUG: Log RAW messages sent to Sokrates (controlled by DEBUG_LOG_RAW_MESSAGES)
            _log_raw_messages("Sokrates", round_num, sokrates_messages)

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

                # Calculate Salomo context (respect per-LLM manual toggle)
                if getattr(state, 'num_ctx_manual_salomo_enabled', False):
                    salomo_num_ctx = state.num_ctx_manual_salomo if hasattr(state, 'num_ctx_manual_salomo') else 4096
                    if round_num == 1:
                        state.add_debug(f"🔧 Salomo num_ctx: {salomo_num_ctx:,} (manual)")
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
                salomo_minimal = get_salomo_system_minimal(lang=detected_lang)
                mediator_prompt = get_salomo_mediator_prompt(round_num=round_num, lang=detected_lang)
                salomo_system = f"{salomo_minimal}\n\n{mediator_prompt}"

                # Build messages with observer perspective (sees everything neutrally)
                # Use llm_history (compressed) instead of chat_history (full UI)
                salomo_messages: list[dict[str, str]] = build_messages_from_llm_history(
                    state.llm_history,
                    perspective="observer"  # Neutral perspective
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
                _log_raw_messages("Salomo", round_num, salomo_messages)

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
                        lang=detected_lang
                    )

                    # PRE-AIFRED: Check if compression needed before AIfred refinement
                    # Include AIfred system prompt + refinement prompt in token calculation (v2.14.1+)
                    # IMPORTANT (v2.14.4+): Use AIFRED's context limit, not min_ctx!
                    aifred_system_prompt = get_aifred_system_minimal(lang=detected_lang)
                    aifred_prompt_tokens = _estimate_prompt_tokens(aifred_system_prompt) + _estimate_prompt_tokens(refinement_prompt)
                    async for _ in _check_compression_if_needed(state, llm_client, main_llm_ctx, aifred_prompt_tokens):
                        yield

                    # Build messages with AIfred's perspective
                    # Use llm_history (compressed) instead of chat_history (full UI)
                    history_messages: list[dict[str, str]] = build_messages_from_llm_history(
                        state.llm_history,
                        current_user_text=refinement_prompt,
                        perspective="aifred"
                    )

                    # Build final message list: AIfred system prompt + history
                    # (Same pattern as Sokrates - agent needs system prompt for identity)
                    alfred_messages: list[dict[str, str]] = [{"role": "system", "content": aifred_system_prompt}]
                    for msg in history_messages:
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

                    # Add placeholder for AIfred refinement
                    alfred_marker = f"🎩[Refinement R{round_num + 1}]"
                    state.chat_history.append(("", alfred_marker))
                    alfred_index = len(state.chat_history) - 1
                    yield

                    # DEBUG: Log RAW messages sent to AIfred (controlled by DEBUG_LOG_RAW_MESSAGES)
                    _log_raw_messages("AIfred", round_num + 1, alfred_messages)

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
    detected_lang: str = "en"
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
    """
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

        # Get context limits (respect per-LLM manual toggles)
        # AIfred context
        if getattr(state, 'num_ctx_manual_aifred_enabled', False):
            main_llm_ctx = state.num_ctx_manual if state.num_ctx_manual else 4096
            state.add_debug(f"🔧 AIfred num_ctx: {main_llm_ctx:,} (manual)")
        else:
            aifred_cached = _last_vram_limit_cache.get("aifred_limit", 0)
            if aifred_cached == 0:
                aifred_cached = _last_vram_limit_cache.get("limit", 0)
            main_llm_ctx = aifred_cached if aifred_cached > 0 else 32768

        # Sokrates context
        if getattr(state, 'num_ctx_manual_sokrates_enabled', False):
            sokrates_num_ctx = state.num_ctx_manual_sokrates if state.num_ctx_manual_sokrates else 4096
            state.add_debug(f"🔧 Sokrates num_ctx: {sokrates_num_ctx:,} (manual)")
        else:
            sokrates_num_ctx, _ = await calculate_dynamic_num_ctx(
                llm_client, sokrates_model, [], None, enable_vram_limit=True
            )

        # Salomo context
        if getattr(state, 'num_ctx_manual_salomo_enabled', False):
            salomo_num_ctx = state.num_ctx_manual_salomo if state.num_ctx_manual_salomo else 4096
            state.add_debug(f"🔧 Salomo num_ctx: {salomo_num_ctx:,} (manual)")
        else:
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

            # --- SOKRATES CRITIQUE ---
            sokrates_minimal = get_sokrates_system_minimal(lang=detected_lang)
            mode_prompt = get_sokrates_critic_prompt(round_num=round_num, lang=detected_lang)
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

            formatted_sokrates = format_thinking_process(
                sokrates_response_text,
                model_name=f"Sokrates ({sokrates_model})",
                inference_time=metrics.get("time", 0)
            )
            final_content = f"{sokrates_marker}{formatted_sokrates}\n\n{metadata}"
            state.chat_history[sokrates_index] = ("", final_content)
            state.sokrates_critique = sokrates_response_text
            yield

            # INCREMENTAL SAVE: Persist after each agent response to survive browser refresh
            state._save_current_session()

            # NOTE: PRE-CHECK before next agent handles compression
            # No POST-CHECK needed here

            # --- AIFRED RESPONSE (if not last round) ---
            if round_num < max_rounds:
                # Build refinement prompt FIRST (needed for accurate token estimation)
                # IMPORTANT: Clean <think> tags from Sokrates' response before embedding in prompt!
                cleaned_sokrates_text = strip_thinking_blocks(sokrates_response_text)
                refinement_prompt = get_sokrates_refinement_prompt(
                    critique=cleaned_sokrates_text,
                    user_interjection="",
                    lang=detected_lang
                )

                # PRE-AIFRED: Check if compression needed before AIfred refinement
                # Include AIfred system prompt + refinement prompt in token calculation (v2.14.1+)
                # IMPORTANT (v2.14.4+): Use AIFRED's context limit, not min_ctx!
                aifred_system_prompt = get_aifred_system_minimal(lang=detected_lang)
                aifred_prompt_tokens = _estimate_prompt_tokens(aifred_system_prompt) + _estimate_prompt_tokens(refinement_prompt)
                async for _ in _check_compression_if_needed(state, llm_client, main_llm_ctx, aifred_prompt_tokens):
                    yield

                # Use llm_history (compressed) instead of chat_history (full UI)
                history_messages: list[dict[str, str]] = build_messages_from_llm_history(
                    state.llm_history,
                    current_user_text=refinement_prompt,
                    perspective="aifred"
                )

                # Build final message list: AIfred system prompt + history
                # (Same pattern as Sokrates - agent needs system prompt for identity)
                alfred_messages: list[dict[str, str]] = [{"role": "system", "content": aifred_system_prompt}]
                for msg in history_messages:
                    # Keep all messages except non-summary system messages
                    if msg["role"] != "system" or "Compressed:" in msg.get("content", ""):
                        alfred_messages.append(msg)

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
                yield

                # INCREMENTAL SAVE: Persist after each agent response to survive browser refresh
                state._save_current_session()

                # NOTE: PRE-CHECK in next iteration handles compression
                # No POST-CHECK needed here

        # === JUDGMENT PHASE: Salomo delivers final verdict ===
        state.add_debug("👑 Salomo rendering verdict...")

        salomo_minimal = get_salomo_system_minimal(lang=detected_lang)
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
            perspective="observer"
        )
        salomo_messages.insert(0, {"role": "system", "content": salomo_system})

        # Estimate tokens for Salomo verdict (consistent with other agent debug output)
        salomo_msg_tokens = estimate_tokens(salomo_messages, model_name=salomo_model)
        state.add_debug(
            f"📊 Salomo Verdict: {format_number(salomo_msg_tokens)} / "
            f"{format_number(salomo_num_ctx)} tokens"
        )

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
