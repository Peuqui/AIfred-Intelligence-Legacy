"""Chat mixin for AIfred state.

Handles message sending, AI response streaming, agent panel display,
and chat clearing.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, Dict, List

import reflex as rx

from ..lib import log_message
from ..lib.config import DEBUG_MESSAGES_MAX
from ..lib.context_manager import strip_thinking_blocks


class ChatMixin(rx.State, mixin=True):
    """Mixin for chat message sending and AI response streaming."""

    # ── State Variables ──────────────────────────────────────────────
    current_user_input: str = ""
    current_user_message: str = ""  # The message currently being processed
    # current_ai_response lives on StreamingState (separate React context)
    current_agent: str = ""  # Current streaming agent ID
    current_agent_display_name: str = ""  # Display name for streaming UI
    current_agent_emoji: str = ""  # Emoji for streaming UI
    is_generating: bool = False
    is_compressing: bool = False  # Shows if history compression is running

    # Debug Console
    debug_messages: List[str] = []
    auto_refresh_enabled: bool = True  # For Debug Console + Chat History + AI Response Area

    # Processing Progress (Automatik, Scraping, LLM)
    progress_active: bool = False
    progress_phase: str = ""  # "automatik", "scraping", "llm"
    progress_current: int = 0
    progress_total: int = 0
    progress_failed: int = 0  # Number of failed URLs

    # ── Debug / Progress ─────────────────────────────────────────────

    def add_debug(self, message: str) -> None:
        """Add message to debug console."""
        import datetime as _dt

        timestamp = _dt.datetime.now().strftime("%H:%M:%S")
        formatted_msg = f"{timestamp} | {message}"

        # Add to Reflex State
        self.debug_messages.append(formatted_msg)

        # Also add to lib console (for agent_core logging)
        log_message(message)

        # Keep only last N messages (configurable in config.py)
        if len(self.debug_messages) > DEBUG_MESSAGES_MAX:
            self.debug_messages = self.debug_messages[-DEBUG_MESSAGES_MAX:]

    def set_progress(self, phase: str, current: int = 0, total: int = 0, failed: int = 0) -> None:
        """Update processing progress."""
        self.progress_active = True
        self.progress_phase = phase
        self.progress_current = current
        self.progress_total = total
        self.progress_failed = failed

    def clear_progress(self) -> None:
        """Clear processing progress."""
        self.progress_active = False
        self.progress_phase = ""
        self.progress_current = 0
        self.progress_total = 0
        self.progress_failed = 0

    # ── Agent Panel Helpers ──────────────────────────────────────────

    def _get_mode_label(self, mode: str, round_num: int | None) -> str:
        """Generate mode label based on mode and UI language.

        Args:
            mode: Mode identifier (e.g., "auto_consensus", "tribunal", "direct")
            round_num: Optional round number for multi-round debates

        Returns:
            Localized label string (e.g., "Auto-Konsens", "Tribunal", "Direkte Antwort")
        """
        from ..lib.i18n import t

        # Mode label mapping (without round number)
        mode_labels = {
            "auto_consensus": t("auto_consensus_label", lang=self.ui_language).rstrip(":"),  # type: ignore[attr-defined]
            "tribunal": "Tribunal",  # Same in both languages
            "direct": t("direct_response_label", lang=self.ui_language).rstrip(":"),  # type: ignore[attr-defined]
            "refinement": t("refinement_label", lang=self.ui_language).rstrip(":"),  # type: ignore[attr-defined]
            "synthesis": t("salomo_synthesis_label", lang=self.ui_language).rstrip(":"),  # type: ignore[attr-defined]
            "verdict": t("salomo_verdict_label", lang=self.ui_language).rstrip(":"),  # type: ignore[attr-defined]
            "critical_review": t("critical_review_label", lang=self.ui_language).rstrip(":"),  # type: ignore[attr-defined]
            "advocatus_diaboli": t("advocatus_diaboli_label", lang=self.ui_language).rstrip(":"),  # type: ignore[attr-defined]
            "error": "Error",  # Same in both languages
            "standard": "",  # No label for standard mode
        }

        return mode_labels.get(mode, "")

    def _set_current_agent(self, agent_id: str) -> None:
        """Set current streaming agent with display info for UI."""
        from ..lib.agent_config import get_agent_config
        self.current_agent = agent_id
        if agent_id:
            cfg = get_agent_config(agent_id)
            self.current_agent_display_name = cfg.display_name if cfg else agent_id.capitalize()
            self.current_agent_emoji = cfg.emoji if cfg else "\U0001f916"
        else:
            self.current_agent_display_name = ""
            self.current_agent_emoji = ""

    def _build_marker(self, agent: str, mode: str, round_num: int | None) -> str:
        """Build marker string for agent panels.

        Args:
            agent: Agent identifier ("aifred", "sokrates", "salomo")
            mode: Mode identifier (e.g., "refinement", "critical_review", "verdict")
            round_num: Optional round number

        Returns:
            Formatted marker like "<span style='...'>Auto-Konsens: Überarbeitung R2</span>\\n\\n"
            (includes multi_agent_mode prefix if active, no emoji - already shown left of bubble)
        """
        label = self._get_mode_label(mode, round_num)

        if not label:
            return ""  # No marker for standard mode

        # Prepend multi-agent mode prefix (e.g., "Auto-Konsens:", "Tribunal:")
        # Skip for "standard" mode, when mode already includes the prefix,
        # or when mode equals multi_agent_mode (prevents "[Critical Review: Critical Review R1]")
        mode_prefix = ""
        if self.multi_agent_mode != "standard" and mode not in ["auto_consensus", "tribunal", "devils_advocate"] and mode != self.multi_agent_mode:  # type: ignore[attr-defined]
            # Get localized multi-agent mode label
            multi_mode_label = self._get_mode_label(self.multi_agent_mode, None)  # type: ignore[attr-defined]
            if multi_mode_label:
                mode_prefix = f"{multi_mode_label}: "

        # Add round suffix if present
        round_suffix = f" R{round_num}" if round_num else ""

        # Format with HTML span for styling (no emoji - already in UI)
        # Color: rgba(255, 255, 255, 1.0) = 100% opacity white (fully opaque)
        # Style: italic, smaller font
        # Spacing: 2 newlines after (converted to <br><br> in HTML export)
        return f"<span style='color: rgba(255, 255, 255, 0.6); font-style: italic; font-size: 12px;'>[{mode_prefix}{label}{round_suffix}]</span>\n\n"

    def _format_panel_metadata(self, metadata: dict | None) -> str:
        """Format metadata footer for agent panels.

        Args:
            metadata: Dict with keys like ttft, inference_time, tokens_per_sec, source

        Returns:
            Formatted metadata string like "*( TTFT: 0,41s    Inference: 9,1s )*"
        """
        if not metadata:
            return ""

        from ..lib.formatting import format_metadata, format_number

        # Split into speed metrics (no wrap) and info (wrap allowed before)
        perf_parts: list[str] = []
        info_parts: list[str] = []

        # TTFT (Time To First Token)
        if "ttft" in metadata and metadata["ttft"]:
            perf_parts.append(f"TTFT:\u00A0{format_number(metadata['ttft'], 2)}s")

        # PP speed (prompt processing)
        prompt_per_sec = metadata.get("prompt_per_sec", 0)
        if prompt_per_sec:
            perf_parts.append(f"PP:\u00A0{format_number(prompt_per_sec, 1)}\u00A0tok/s")

        # Tokens per second (generation)
        if "tokens_per_sec" in metadata and metadata["tokens_per_sec"]:
            perf_parts.append(f"{format_number(metadata['tokens_per_sec'], 1)}\u00A0tok/s")

        # Inference time
        if "inference_time" in metadata and metadata["inference_time"]:
            perf_parts.append(f"Inference:\u00A0{format_number(metadata['inference_time'], 1)}s")

        # Source (with backend label if available)
        if "source" in metadata and metadata["source"]:
            source = metadata["source"]
            backend = metadata.get("backend_type", "")
            source_display = f"{source}\u00A0[{backend}]" if backend else source
            # Replace all spaces within source so it stays as one unbreakable unit
            info_parts.append(f"Source:\u00A0{source_display.replace(' ', chr(0xA0))}")

        if not perf_parts and not info_parts:
            return ""

        # Within groups: "    " → non-breaking spaces (no wrap)
        # Between groups: 3 nbsp + regular space → allows line break on mobile
        groups: list[str] = []
        if perf_parts:
            groups.append("    ".join(perf_parts))
        if info_parts:
            groups.append("    ".join(info_parts))
        metadata_text = "\u00A0\u00A0\u00A0 ".join(groups)
        return format_metadata(metadata_text)

    # ── LLM History Sync ─────────────────────────────────────────────

    def _sync_to_llm_history(self, agent: str, content: str) -> None:
        """Sync agent response to llm_history with speaker label.

        Strips only thinking blocks (<think>, Harmony analysis).
        Code tags (<python>, <code>, etc.) are preserved because they
        provide important context for the LLM.

        IMPORTANT: Callers should pass RAW content (before format_thinking_process),
        not formatted content with <details> collapsibles. If the caller already
        formats before calling add_agent_panel(), use sync_llm_history=False and
        sync manually with raw content.

        Args:
            agent: Agent identifier ("aifred", "sokrates", "salomo")
            content: Agent response content (should be RAW, not formatted)
        """
        label = agent.upper()
        clean_content = strip_thinking_blocks(content)

        if clean_content:
            self._chat_sub().llm_history.append({
                "role": "assistant",
                "content": f"[{label}]: {clean_content}"
            })

    # ── Central Agent Panel ──────────────────────────────────────────

    def add_agent_panel(
        self,
        agent: str,  # "aifred", "sokrates", "salomo"
        content: str,
        mode: str = "standard",
        round_num: int | None = None,
        metadata: dict | None = None,
        sync_llm_history: bool = True,
        generate_tts: bool | None = None,
    ) -> None:
        """Add an agent response as a new message to chat_history.

        This is the ONLY function that should be used to add agent panels to chat_history.
        It handles:
        - Emoji marker generation
        - Mode labeling (Auto-Consensus, Tribunal, etc.)
        - Round numbering (R1, R2, ...)
        - Metadata formatting (TTFT, Inference time, tok/s, Source)
        - LLM history synchronization
        - Session persistence
        - TTS generation (queued for sequential playback)

        With the new dict-based chat_history, each message is standalone.
        No more replace_last logic - just append new messages.

        Args:
            agent: Agent identifier ("aifred", "sokrates", "salomo")
            content: Agent response content (WITHOUT marker, WITHOUT metadata)
            mode: Mode identifier (e.g., "auto_consensus", "tribunal", "direct", "standard")
            round_num: Round number for multi-round debates (None/0 = no round, 1+ = round number)
            metadata: Optional dict with TTFT, inference_time, tokens_per_sec, source
            sync_llm_history: If True, syncs to llm_history (set False if caller already did)
            generate_tts: If True, generate TTS and add to queue. If None, uses self.enable_tts.
                         If False, skip TTS. For multi-agent modes, this enables per-response TTS.
        """
        import asyncio

        from ..lib.i18n import t
        from ..lib.prompt_loader import get_language

        # 1. Build marker (emoji + mode label + round number)
        marker = self._build_marker(agent, mode, round_num if round_num and round_num > 0 else None)

        # 2. Format metadata footer
        meta_footer = self._format_panel_metadata(metadata)

        # 3. Translate consensus tags to natural language for UI display
        # These are trigger words for the Multi-Agent system, already parsed by count_lgtm_votes()
        # Now we make them human-readable in the UI (and TTS will speak what's displayed)
        # Uses detected language (from Intent Detection) for correct localization
        lang = self._last_detected_language or get_language()  # type: ignore[attr-defined, has-type]
        content = re.sub(r'\[LGTM\]', t("consensus_agreed", lang=lang), content, flags=re.IGNORECASE)
        content = re.sub(r'\[WEITER\]', t("consensus_continue", lang=lang), content, flags=re.IGNORECASE)

        # 4. Remove thinking blocks from content before storing (for History/Token estimation)
        clean_content = strip_thinking_blocks(content)

        # 5. Assemble final content for display
        if marker:
            final_content = f"{marker}{clean_content}\n\n{meta_footer}"
        else:
            # Standard mode: no marker, just content + metadata
            final_content = f"{clean_content}\n\n{meta_footer}" if meta_footer else clean_content

        # 5. Create new message entry (dict-based format)
        # Include audio URLs if streaming TTS generated them
        msg_metadata = metadata.copy() if metadata else {}
        if self._pending_audio_urls:  # type: ignore[attr-defined, has-type]
            msg_metadata["audio_urls"] = self._pending_audio_urls.copy()  # type: ignore[attr-defined, has-type]
            log_message(f"🔊 add_agent_panel: Stored {len(self._pending_audio_urls)} audio URLs in message metadata")  # type: ignore[attr-defined, has-type]
            self._pending_audio_urls: list[str] = []  # type: ignore[attr-defined, var-annotated]

        # Store agent's playback rate for HTML export (browser speed setting, per-agent)
        # Always set when audio_urls are present, regardless of source
        audio_urls = msg_metadata.get("audio_urls", [])
        if audio_urls:
            msg_metadata["playback_rate"] = self.tts_agent_voices[agent]["speed"]  # type: ignore[attr-defined]
        # Resolve agent display info for UI rendering
        from ..lib.agent_config import get_agent_config
        agent_cfg = get_agent_config(agent)
        agent_display_name = agent_cfg.display_name if agent_cfg else agent.capitalize()
        agent_emoji = agent_cfg.emoji if agent_cfg else "\U0001f916"

        new_message: Dict[str, Any] = {
            "role": "assistant",
            "content": final_content,
            "agent": agent,
            "agent_display_name": agent_display_name,
            "agent_emoji": agent_emoji,
            "mode": mode,
            "round_num": round_num,
            "metadata": msg_metadata,
            "timestamp": datetime.now().isoformat(),
            "used_sources": [],
            "failed_sources": [],
            "has_audio": bool(audio_urls),
            "audio_urls_json": json.dumps(audio_urls) if audio_urls else "[]",
        }

        # 5. Append to chat_history (no more replace_last!)
        self._chat_sub().chat_history.append(new_message)

        # 6. Sync to llm_history (with speaker label)
        # Note: Some callers (streaming functions) already sync to llm_history,
        # so they should pass sync_llm_history=False to avoid duplicates
        if sync_llm_history:
            self._sync_to_llm_history(agent, content)

        # 7. Save session (async, non-blocking)
        self._save_current_session()  # type: ignore[attr-defined]

        # 8. Generate TTS and add to queue (if enabled)
        # Determine if TTS should be generated
        # SKIP if streaming TTS is enabled - text was already sent sentence-by-sentence
        should_generate_tts = generate_tts if generate_tts is not None else self.enable_tts  # type: ignore[attr-defined]
        if should_generate_tts and not self.tts_streaming_enabled:  # type: ignore[attr-defined]
            # Check per-agent TTS enabled setting
            agent_tts_enabled = self.tts_agent_voices.get(agent, {}).get("enabled", True)  # type: ignore[attr-defined]
            if agent_tts_enabled:
                # Schedule TTS generation as background task
                # This runs async without blocking add_agent_panel()
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(self._queue_tts_for_agent(content, agent))  # type: ignore[attr-defined]
                except RuntimeError:
                    # No running loop - this shouldn't happen in normal operation
                    # but we handle it gracefully
                    self.add_debug(f"⚠️ TTS: No event loop for {agent}")

    # ── Multi-Agent Dispatch ─────────────────────────────────────────

    async def _maybe_run_multi_agent(
        self,
        user_msg: str,
        ai_text: str,
        detected_language: str,
        skip_analysis: bool,
    ) -> AsyncGenerator[None, None]:
        """Run Multi-Agent analysis if activated and not skipped.

        Args:
            user_msg: The user message
            ai_text: The AI response (AIfred R1)
            detected_language: Language ("de" or "en")
            skip_analysis: True to skip Multi-Agent (e.g. user addressed AIfred directly)

        Yields:
            Nothing directly, but updates state via run_tribunal/run_sokrates_analysis
        """
        from ..lib.multi_agent import run_sokrates_analysis, run_tribunal

        # Skip if standard mode, no AI text, or explicitly skipped
        if self.multi_agent_mode == "standard" or not ai_text or skip_analysis:  # type: ignore[attr-defined]
            return

        # Generate TTS for AIfred's initial response BEFORE Multi-Agent starts
        # This ensures AIfred's voice is heard first, then Sokrates/Salomo follow
        # (Sokrates/Salomo TTS is generated via add_agent_panel() in multi_agent.py)
        # SKIP if streaming TTS is enabled - text was already sent sentence-by-sentence
        if self.enable_tts and not self.tts_streaming_enabled:  # type: ignore[attr-defined]
            agent_tts_enabled = self.tts_agent_voices.get("aifred", {}).get("enabled", True)  # type: ignore[attr-defined]
            if agent_tts_enabled:
                # Wait for TTS to complete so we can update message metadata with audio URL
                await self._queue_tts_for_agent(ai_text, agent="aifred")  # type: ignore[attr-defined]
                yield  # Update UI with audio button (chat_history was reassigned in _queue_tts_for_agent)

        if self.multi_agent_mode == "tribunal":  # type: ignore[attr-defined]
            self.add_debug("⚖️ Multi-Agent: Tribunal startet...")
            yield
            async for _ in run_tribunal(self, user_msg, ai_text, detected_language):  # type: ignore[arg-type]
                yield
        else:
            self.add_debug("🏛️ Multi-Agent: Sokrates-Analyse startet...")
            yield
            async for _ in run_sokrates_analysis(self, user_msg, ai_text, detected_language):  # type: ignore[arg-type]
                yield

    # ── VL Inference Helper ──────────────────────────────────────────

    async def _run_vl_inference(
        self,
        user_msg: str,
        content_parts: list[dict],
        detected_intent: str,
        detected_language: str,
        vision_prompt_key: str = "task_qa",
    ) -> AsyncGenerator[None, None]:
        """Run VL inference via handle_own_knowledge and process results.

        Shared by VL Direct, VL Shortcut, and VL Follow-up paths.
        Handles streaming, history update, cleanup, title generation and session save.

        For llamacpp: prefers the -speed variant (single GPU, faster) unless
        the base variant is already running (avoid unnecessary model swap).
        """
        from ..lib.own_knowledge_handler import handle_own_knowledge

        # Determine effective vision model: use speed variant when toggle is on
        effective_vision_id = self.vision_model_id  # type: ignore[attr-defined]
        if (
            self.backend_type == "llamacpp"
            and self.vision_model_id  # type: ignore[attr-defined]
            and self.vision_speed_mode  # type: ignore[attr-defined]
            and self.vision_has_speed_variant  # type: ignore[attr-defined]
        ):
            effective_vision_id = f"{self.vision_model_id}-speed"  # type: ignore[attr-defined]
            self.add_debug(f"⚡ VL Speed: {effective_vision_id}")  # type: ignore[attr-defined]
            yield

        self._set_current_agent("aifred")
        yield

        result_data = None
        async for item in handle_own_knowledge(
            user_text=user_msg,
            model_choice=effective_vision_id,
            history=self._chat_sub().chat_history,
            llm_history=self._chat_sub().llm_history[:-1],
            detected_intent=detected_intent,
            detected_language=detected_language,
            temperature_mode="manual",
            temperature=self.vision_temperature,  # type: ignore[attr-defined]
            backend_type=self.backend_type,  # type: ignore[attr-defined]
            backend_url=self.backend_url,  # type: ignore[attr-defined]
            enable_thinking=self.vision_thinking,  # type: ignore[attr-defined]
            state=self,
            multimodal_content=content_parts,
            vision_prompt_key=vision_prompt_key,
            provider=self.cloud_api_provider if self.backend_type == "cloud_api" else None,  # type: ignore[attr-defined]
            agent="vision",
        ):
            if item["type"] == "debug":
                self.add_debug(item["message"])
                yield
            elif item["type"] == "content":
                if self.stream_text_to_ui(item["text"]):  # type: ignore[attr-defined]
                    yield
            elif item["type"] == "progress":
                if item.get("clear", False):
                    self.clear_progress()  # type: ignore[attr-defined]
                else:
                    self.set_progress(  # type: ignore[attr-defined]
                        phase=item.get("phase", ""),
                        current=item.get("current", 0),
                        total=item.get("total", 0),
                    )
                yield
            elif item["type"] == "result":
                # Flush remaining buffer to state
                if self.flush_stream_to_ui():  # type: ignore[attr-defined]
                    yield
                result_data = item["data"]

        # Separator after VL inference (consistent with all other inference paths)
        from ..lib.logging_utils import console_separator, CONSOLE_SEPARATOR
        console_separator()
        self.add_debug(CONSOLE_SEPARATOR)  # type: ignore[attr-defined]
        yield

        if result_data:
            # handle_own_knowledge() got llm_history[:-1] (N-1 entries) and appended
            # the AI response → returned slice has N entries when successful.
            # llm_history still has N entries (prior + user_msg from line 511).
            # Length equality means exactly one AI entry was added → append it.
            ch = self._chat_sub()
            returned_llm = result_data["llm_history"]
            if (len(returned_llm) == len(ch.llm_history)
                    and returned_llm[-1].get("role") == "assistant"):
                ch.llm_history = list(ch.llm_history) + [returned_llm[-1]]
            self._chat_sub().chat_history = result_data["history"]

        self._streaming_sub().current_ai_response = ""  # type: ignore[attr-defined]
        self.current_user_message = ""
        self.is_generating = False
        yield

        async for _ in self._generate_session_title(title_model_override=effective_vision_id):  # type: ignore[attr-defined]
            yield
        self._save_current_session()  # type: ignore[attr-defined]
        self.refresh_session_list()  # type: ignore[attr-defined]
        yield

    # ── Main Send Message ────────────────────────────────────────────

    async def send_message(self, text: str = "") -> AsyncGenerator[None, None]:  # type: ignore[misc]
        """Send message to LLM with optional web research.

        Args:
            text: User text from UI (via call_script callback).
                  Empty when called programmatically — reads from current_user_input.
        """
        # Must be logged in to send messages
        if not self.logged_in_user:  # type: ignore[attr-defined]
            self.add_debug("⚠️ Please log in first")
            return

        # If no text but images present, use default prompt
        has_pending_images = len(self.pending_images) > 0  # type: ignore[attr-defined]
        # Text from call_script callback (UI click) or current_user_input (injection/transcription)
        user_text = (text or self.current_user_input).strip()

        if not user_text and not has_pending_images:
            return  # Nothing to send

        # Leerer user_text ist erlaubt für reine OCR-Extraktion (ohne Interpretation)

        if self.is_generating:
            self.add_debug("⚠️ Already generating, please wait...")
            return

        # Ensure backend is initialized (should already be done by on_load)
        await self._ensure_backend_initialized()  # type: ignore[attr-defined]

        # ============================================================
        # PHASE 1: Spinner + textarea clear — yield IMMEDIATELY
        # ============================================================
        # Minimal state for instant UI feedback (spinner + correct agent indicator)
        # Textarea is already cleared client-side by the call_script in on_click
        self.is_generating = True
        self._set_current_agent("")
        self._streaming_sub().current_ai_response = ""  # type: ignore[attr-defined]
        yield  # Spinner visible immediately

        # ============================================================
        # PHASE 2: Build and add user message to chat
        # ============================================================
        user_msg = user_text
        self.current_user_input = ""  # Clear state (for injection/transcription path)
        self.current_user_message = user_msg
        self.used_sources: list[dict[str, Any]] = []  # type: ignore[attr-defined, var-annotated]
        self.failed_sources: list[dict[str, str]] = []  # type: ignore[attr-defined, var-annotated]
        self.all_sources: list[dict[str, Any]] = []  # type: ignore[attr-defined, var-annotated]
        self.clear_tts_queue()  # type: ignore[attr-defined]

        display_user_msg = user_msg
        if has_pending_images:
            # Generate clickable image thumbnails as HTML
            image_html_parts: list[str] = []
            for img in self.pending_images:  # type: ignore[attr-defined]
                url = img.get('url', '')
                if url:
                    image_html_parts.append(
                        f'<a href="{url}" target="_blank" rel="noopener noreferrer">'
                        f'<img src="{url}" style="width:50px;height:50px;object-fit:cover;'
                        f'border-radius:4px;cursor:pointer;margin-right:4px;"></a>'
                    )
            image_html = "".join(image_html_parts)

            if not user_msg or user_msg.strip() == "":
                # Image-only upload
                if len(self.pending_images) == 1:  # type: ignore[attr-defined]
                    display_user_msg = f"{image_html}\n\n📷 {self.pending_images[0].get('name', 'Image')}"  # type: ignore[attr-defined]
                else:
                    img_names = ", ".join([img.get("name", "unknown") for img in self.pending_images])  # type: ignore[attr-defined]
                    display_user_msg = f"{image_html}\n\n📷 {len(self.pending_images)} images: {img_names}"  # type: ignore[attr-defined]
            else:
                # Text + images
                display_user_msg = f"{image_html}\n\n{user_msg}" if image_html else user_msg

        self._chat_sub().chat_history.append({
            "role": "user",
            "content": display_user_msg,
            "agent": "",
            "mode": "",
            "round_num": 0,
            "metadata": {
                "images": [{"name": img.get("name", ""), "url": img.get("url", "")} for img in self.pending_images] if has_pending_images else []  # type: ignore[attr-defined]
            },
            "timestamp": datetime.now().isoformat(),
            "used_sources": [],
            "failed_sources": [],
            "has_audio": False,
            "audio_urls_json": "[]",
        })
        self._chat_sub().llm_history.append({"role": "user", "content": user_msg})
        self.add_debug("📨 User request received")

        # ============================================================
        # PHASE 3: TTS streaming init
        # ============================================================
        if self.enable_tts and self.tts_autoplay and self.tts_streaming_enabled:  # type: ignore[attr-defined]
            self._init_streaming_tts(agent="aifred")  # type: ignore[attr-defined]
            from ..lib.api import tts_queue_clear
            tts_queue_clear(self.session_id)  # type: ignore[attr-defined]
            yield rx.call_script(f"if(window.startTtsStream) startTtsStream('{self.session_id}');")  # type: ignore[attr-defined]
        else:
            yield  # Push user message bubble to browser

        # ============================================================
        # PHASE 4: vLLM model loading (AFTER user message is visible)
        # ============================================================
        if self.backend_type == "vllm":  # type: ignore[attr-defined]
            from . import _global_backend_state
            mgr = _global_backend_state.get("vllm_manager")
            if not (mgr and mgr.is_running()) and self.aifred_model_id:  # type: ignore[attr-defined]
                self.add_debug(f"🚀 Starting vLLM with {self.aifred_model_id}...")  # type: ignore[attr-defined]
                yield  # Show debug message while loading
            await self._ensure_vllm_model()  # type: ignore[attr-defined]

        # TTS: Ensure Docker container is running BEFORE Ollama loads models (reserves VRAM)
        # This runs on every message, not just at startup - handles container restart scenarios
        if self.enable_tts and self.tts_engine == "xtts" and not self.xtts_force_cpu:  # type: ignore[attr-defined]
            from ..lib.process_utils import ensure_xtts_ready

            self.add_debug("🔊 XTTS: Checking container...")
            yield  # Show debug message
            success, msg = ensure_xtts_ready(timeout=60)
            if success:
                self.add_debug(f"✅ {msg}")
            else:
                self.add_debug(f"⚠️ {msg}")
            yield  # Update UI
        elif self.enable_tts and self.tts_engine == "moss":  # type: ignore[attr-defined]
            from ..lib.process_utils import ensure_moss_ready

            self.add_debug("🔊 MOSS-TTS: Checking container...")
            yield
            success, msg, device = ensure_moss_ready(timeout=120)
            self.moss_tts_device = device if success else ""  # type: ignore[attr-defined]
            if success:
                self.add_debug(f"✅ {msg}")
            else:
                self.add_debug(f"⚠️ {msg}")
            yield

        try:
            # ============================================================
            # MAIN TRY BLOCK: Covers ALL stages from LLM client creation
            # through inference. Ensures is_generating is ALWAYS reset in finally,
            # even if intent detection hangs, compression fails, or the generator
            # is cancelled by WebSocket disconnect (GeneratorExit).
            # ============================================================
            ai_text = ""  # Must be initialized here — used in finally block

            # ============================================================
            # VISION FAST PATH: Images present → VL model handles everything
            # Skip Intent Detection, Automatik and AIfred entirely.
            # VL model receives: AIfred system prompt + user text + image(s).
            # ============================================================
            if has_pending_images:
                import copy
                local_images = copy.deepcopy(self.pending_images)  # type: ignore[attr-defined]
                self.clear_pending_images()  # type: ignore[attr-defined]

                # Use UI language (no Intent Detection)
                from ..lib.prompt_loader import get_language
                detected_language = get_language()
                self._last_detected_language = detected_language  # type: ignore[attr-defined]

                # Cold start warning for llama.cpp
                if self.backend_type == "llamacpp":  # type: ignore[attr-defined]
                    try:
                        import httpx
                        swap_base = self.backend_url.rstrip("/").removesuffix("/v1")  # type: ignore[attr-defined]
                        async with httpx.AsyncClient(timeout=5.0) as _http:
                            resp = await _http.get(f"{swap_base}/running")
                            running = [m.get("model") for m in resp.json().get("running", [])]
                            _eff_vl = self._effective_model_id("vision")  # type: ignore[attr-defined]
                            if _eff_vl not in running:
                                self.add_debug(f"🔄 VL Model Cold Start ({_eff_vl}) — loading...")  # type: ignore[attr-defined]
                                yield
                    except Exception:
                        pass

                img_count = len(local_images)
                self.add_debug(f"📷 VL Direct ({img_count} image(s)) → {self.vision_model}")  # type: ignore[attr-defined]
                yield

                # Build multimodal content (images + text) for handle_own_knowledge()
                from ..lib.vision_utils import load_image_as_base64
                from pathlib import Path

                content_parts: list[dict] = []

                # Qwen3-VL respects /no_think prefix (Ollama ignores API think param for VL)
                if not self.vision_thinking:  # type: ignore[attr-defined]
                    content_parts.append({"type": "text", "text": "/no_think"})

                # Images first (VL models handle it best this way)
                for img in local_images:
                    img_path = Path(img["path"])
                    base64_data = load_image_as_base64(img_path)
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"},
                    })

                # User text after images (fallback description if empty)
                # Task-adaptive prompt: user text → Q&A, no text → OCR
                has_user_text = bool(user_msg.strip())
                prompt_text = user_msg.strip() if has_user_text else (
                    "Beschreibe und analysiere dieses Bild." if detected_language == "de"
                    else "Describe and analyze this image."
                )
                content_parts.append({"type": "text", "text": prompt_text})
                vision_prompt_key = "task_qa" if has_user_text else "task"

                async for _ in self._run_vl_inference(
                    user_msg, content_parts, "GEMISCHT", detected_language, vision_prompt_key,
                ):
                    yield
                return  # Vision fast path complete

            # Create LLM client once - used for ALL LLM operations
            from ..lib.llm_client import LLMClient
            llm_client = LLMClient(
                backend_type=self.backend_type,  # type: ignore[attr-defined]
                base_url=self.backend_url,  # type: ignore[attr-defined]
            )

            # ============================================================
            # VL SHORTCUT: If VL model is still loaded AND images in history,
            # do relevance check with VL model directly → avoid double swap.
            # Only for llamacpp (model swapping), only when user has text input.
            # ============================================================
            if (not has_pending_images
                    and user_msg.strip()
                    and self.backend_type == "llamacpp"  # type: ignore[attr-defined]
                    and self.vision_model_id):  # type: ignore[attr-defined]
                from ..lib.vision_utils import (
                    collect_image_context_from_history,
                    build_image_context_string,
                    build_recent_context_string,
                    resolve_image_path_by_index,
                    load_image_as_base64,
                )
                _vl_image_list = collect_image_context_from_history(self._chat_sub().chat_history)

                if _vl_image_list:
                    # Check if VL model is currently loaded
                    _vl_model_loaded = False
                    try:
                        import httpx
                        _swap_base = self.backend_url.rstrip("/").removesuffix("/v1")  # type: ignore[attr-defined]
                        async with httpx.AsyncClient(timeout=5.0) as _http:
                            _resp = await _http.get(f"{_swap_base}/running")
                            _running = [m.get("model") for m in _resp.json().get("running", [])]
                            _eff_vl = self._effective_model_id("vision")  # type: ignore[attr-defined]
                            _vl_model_loaded = _eff_vl in _running
                    except Exception:
                        pass

                    if _vl_model_loaded:
                        log_message("📷 VL Shortcut: VL model still loaded, checking relevance directly")
                        _vl_ctx_str = build_image_context_string(_vl_image_list)
                        _vl_recent_ctx = build_recent_context_string(self._chat_sub().chat_history)

                        from ..lib.intent_detector import detect_vl_relevance
                        _vl_idx = await detect_vl_relevance(
                            user_query=user_msg,
                            image_context=_vl_ctx_str,
                            automatik_model=_eff_vl,
                            llm_client=llm_client,
                            recent_context=_vl_recent_ctx,
                        )

                        if _vl_idx is not None:
                            _vl_path = resolve_image_path_by_index(_vl_image_list, _vl_idx)
                            if _vl_path:
                                self.add_debug(f"📷 VL Follow-up (shortcut): Image {_vl_idx} → {_vl_path.name}")
                                yield

                                # Use UI language (no Intent Detection needed)
                                from ..lib.prompt_loader import get_language
                                detected_language = get_language()
                                self._last_detected_language = detected_language  # type: ignore[attr-defined]

                                # Build multimodal content
                                content_parts_sc: list[dict] = []
                                if not self.vision_thinking:  # type: ignore[attr-defined]
                                    content_parts_sc.append({"type": "text", "text": "/no_think"})

                                base64_data = load_image_as_base64(_vl_path)
                                content_parts_sc.append({
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"},
                                })
                                content_parts_sc.append({"type": "text", "text": user_msg})

                                async for _ in self._run_vl_inference(
                                    user_msg, content_parts_sc, "FAKTISCH", detected_language,
                                ):
                                    yield
                                return  # VL shortcut complete — no Automatik swap needed

                        # VL model loaded but question not image-related → normal flow
                        log_message("📷 VL Shortcut: NONE — proceeding to normal flow")

            # ============================================================
            # AUTOMATIK NUM_CTX CALCULATION (once, used for all Automatik calls)
            # ============================================================
            # When Automatik = AIfred (same model): don't set num_ctx → no model reload
            # When different models: use AUTOMATIK_LLM_NUM_CTX from config.py
            from ..lib.config import AUTOMATIK_LLM_NUM_CTX
            from ..lib.formatting import format_number
            effective_auto = self._effective_automatik_id  # type: ignore[attr-defined]
            if effective_auto == self._effective_model_id("aifred"):  # type: ignore[attr-defined]
                # Same model: MUST send same num_ctx as preload to prevent Ollama reload!
                # Ollama uses MODEL DEFAULT (not currently loaded context) when num_ctx is omitted.
                # Omitting num_ctx causes Ollama to reload with default → then main inference
                # sends calibrated num_ctx → Ollama reloads AGAIN. Two unnecessary reloads!
                auto_num_ctx: int | None = self.aifred_max_context if self.aifred_max_context else None  # type: ignore[attr-defined]
                log_message(f"🔧 Automatik = AIfred ({effective_auto}) → num_ctx={auto_num_ctx} (match preload)")

                # Warning if AIfred context is below recommended Automatik threshold
                effective_ctx = self.aifred_max_context or 0  # type: ignore[attr-defined]
                if effective_ctx > 0 and effective_ctx < AUTOMATIK_LLM_NUM_CTX:
                    self.add_debug(
                        f"⚠️ Automatik Context ({format_number(effective_ctx)}) < recommended ({format_number(AUTOMATIK_LLM_NUM_CTX)}) - Automatik tasks may be less reliable"
                    )
                    log_message(f"⚠️ Automatik Context warning: {effective_ctx} < {AUTOMATIK_LLM_NUM_CTX}")
            else:
                # Different model: use config constant
                auto_num_ctx = AUTOMATIK_LLM_NUM_CTX
                log_message(f"🔧 Automatik ≠ AIfred → Context: {auto_num_ctx}")

            # ============================================================
            # VL AUTOMATIK OVERRIDE: VL model loaded → use for Automatik
            # Avoids unnecessary model switch: VL→Automatik→AIfred
            # Instead: VL handles Automatik → then only 1 switch to AIfred
            # (or 0 switches if VL = AIfred)
            # Only for llamacpp (model swapping) and Automatik research mode.
            # ============================================================
            _eff_vl_id = self._effective_model_id("vision")  # type: ignore[attr-defined]
            if (self.backend_type == "llamacpp"  # type: ignore[attr-defined]
                    and _eff_vl_id
                    and self.research_mode == "automatik"  # type: ignore[attr-defined]
                    and effective_auto != _eff_vl_id):
                try:
                    import httpx
                    _swap_base = self.backend_url.rstrip("/").removesuffix("/v1")  # type: ignore[attr-defined]
                    async with httpx.AsyncClient(timeout=5.0) as _http:
                        _resp = await _http.get(f"{_swap_base}/running")
                        _running = [m.get("model") for m in _resp.json().get("running", [])]
                        if _eff_vl_id in _running:
                            effective_auto = _eff_vl_id
                            auto_num_ctx = None  # Let llama-swap use model's configured context
                            self.add_debug(f"📷 VL Automatik: {effective_auto} already loaded → using for decision")
                            log_message(f"📷 VL Automatik Override: {effective_auto} (saves model switch)")
                            yield
                except Exception:
                    pass

            # ============================================================
            # COLD START DETECTION (llama.cpp only)
            # llama-swap loads models on-demand — first request triggers cold start.
            # Check /running BEFORE the first LLM call so the user knows why it's slow.
            # ============================================================
            if self.backend_type == "llamacpp":  # type: ignore[attr-defined]
                try:
                    import httpx
                    swap_base = self.backend_url.rstrip("/").removesuffix("/v1")  # type: ignore[attr-defined]
                    async with httpx.AsyncClient(timeout=5.0) as http_client:
                        resp = await http_client.get(f"{swap_base}/running")
                        running_models = [m.get("model") for m in resp.json().get("running", [])]
                        if effective_auto not in running_models:
                            # Extract model details from llama-swap config
                            details = ""
                            try:
                                from ..lib.llamacpp_calibration import parse_llamaswap_config
                                from ..lib.config import LLAMASWAP_CONFIG_PATH
                                model_info = parse_llamaswap_config(LLAMASWAP_CONFIG_PATH).get(effective_auto, {})
                                parts: list[str] = []
                                if model_info.get("current_context"):
                                    parts.append(f"Context: {format_number(model_info['current_context'])}")
                                if model_info.get("kv_cache_quant"):
                                    parts.append(f"KV-Cache: {model_info['kv_cache_quant']}")
                                if parts:
                                    details = f" ({', '.join(parts)})"
                            except Exception:
                                pass
                            self.add_debug(f"🔄 Model Cold Start ({effective_auto}){details} — loading into VRAM, this may take a while")
                            log_message(f"🔄 Cold Start: {effective_auto}{details}")
                            yield
                except Exception:
                    pass  # Can't check — proceed normally, don't show false warnings

            # ============================================================
            # INTENT + ADDRESSEE + LANGUAGE DETECTION (first LLM call)
            # ============================================================
            # Must run BEFORE compression check to get detected_language
            from ..lib.intent_detector import detect_query_intent_and_addressee

            # If user_msg is empty (image-only) or URL-only, skip Intent Detection and use UI language
            _msg_stripped = user_msg.strip()
            _is_url_only = bool(_msg_stripped) and bool(re.match(r'^https?://\S+$', _msg_stripped))
            if not _msg_stripped or _is_url_only:
                from ..lib.prompt_loader import get_language
                detected_intent = "FAKTISCH"
                addressed_to = None
                detected_language = get_language()
                intent_raw = ""
                _reason = "URL-only" if _is_url_only else "image-only"
                self.add_debug(f"🎯 Intent: {detected_intent} ({_reason}), Lang: {detected_language.upper()} (UI)")
                self._last_detected_language = detected_language  # type: ignore[attr-defined]
            else:
                detected_intent, addressed_to, detected_language, intent_raw = await detect_query_intent_and_addressee(
                    user_msg,
                    effective_auto,
                    llm_client,
                    automatik_num_ctx=auto_num_ctx,
                )
                # Log Intent Detection result to UI debug console (always visible)
                addressee_display = addressed_to.capitalize() if addressed_to else "–"
                self.add_debug(f"🎯 Intent: {detected_intent}, Addressee: {addressee_display}, Lang: {detected_language.upper()}")
                self._last_detected_language = detected_language  # type: ignore[attr-defined]

            # ============================================================
            # PRE-MESSAGE: History Compression Check
            # ============================================================
            # Check BEFORE adding new message - handles session restore, model changes, etc.

            if self._chat_sub().chat_history:
                from ..lib.context_manager import summarize_history_if_needed, get_largest_compression_model
                from ..lib.research.context_utils import get_agent_num_ctx

                # Determine effective context limit using per-agent settings
                # Uses get_agent_num_ctx() which is the SINGLE SOURCE OF TRUTH
                context_limits: list[int] = []

                # AIfred context
                aifred_ctx, _ = get_agent_num_ctx("aifred", self, self._effective_model_id("aifred"))  # type: ignore[attr-defined, arg-type]
                context_limits.append(aifred_ctx)

                # Multi-agent contexts (if not standard mode)
                if self.multi_agent_mode != "standard":  # type: ignore[attr-defined]
                    if self.sokrates_model_id:  # type: ignore[attr-defined]
                        sokrates_ctx, _ = get_agent_num_ctx("sokrates", self, self._effective_model_id("sokrates"))  # type: ignore[attr-defined, arg-type]
                        context_limits.append(sokrates_ctx)
                    if self.salomo_model_id:  # type: ignore[attr-defined]
                        salomo_ctx, _ = get_agent_num_ctx("salomo", self, self._effective_model_id("salomo"))  # type: ignore[attr-defined, arg-type]
                        context_limits.append(salomo_ctx)

                # Use minimum of all agent limits
                context_limit = min(context_limits) if context_limits else 4096

                # Get system prompt tokens from cache (v2.14.0+)
                # Cache is populated at startup in on_load()
                from ..lib.prompt_loader import get_max_system_prompt_tokens
                system_prompt_tokens = get_max_system_prompt_tokens(self.multi_agent_mode, detected_language)  # type: ignore[attr-defined]

                # Select largest model for compression (AIfred/Sokrates/Salomo)
                compression_model = get_largest_compression_model(
                    aifred_model=self._effective_model_id("aifred"),  # type: ignore[attr-defined]
                    sokrates_model=self._effective_model_id("sokrates"),  # type: ignore[attr-defined]
                    salomo_model=self._effective_model_id("salomo"),  # type: ignore[attr-defined]
                )

                # Check and compress if needed (DUAL-HISTORY)
                async for event in summarize_history_if_needed(
                    history=self._chat_sub().chat_history,
                    llm_client=llm_client,
                    model_name=compression_model,  # Use largest available model for quality
                    context_limit=context_limit,
                    llm_history=self._chat_sub().llm_history,
                    system_prompt_tokens=system_prompt_tokens,
                    detected_language=detected_language,  # From Intent Detection
                ):
                    if event["type"] == "history_update":
                        # DUAL-HISTORY: Update both histories
                        self._chat_sub().chat_history = event["chat_history"]
                        if event.get("llm_history") is not None:
                            self._chat_sub().llm_history = event["llm_history"]
                        _ch = self._chat_sub()
                        self.add_debug(f"✅ Pre-Message Compression: {len(_ch.chat_history)} UI / {len(_ch.llm_history)} LLM messages")
                        yield
                    elif event["type"] == "debug":
                        self.add_debug(event["message"])
                        yield

            # NOTE: User message was already added to chat_history at the start of send_message()
            # (before XTTS check) so user sees their message immediately

            # ============================================================
            # VL FOLLOW-UP PATH: No new images, but images in history?
            # Check if the follow-up question relates to a previous image.
            # ============================================================
            if not has_pending_images:
                from ..lib.vision_utils import (
                    collect_image_context_from_history,
                    build_image_context_string,
                    build_recent_context_string,
                    resolve_image_path_by_index,
                    load_image_as_base64,
                )

                image_list = collect_image_context_from_history(self._chat_sub().chat_history)

                if image_list:
                    image_context_str = build_image_context_string(image_list)
                    recent_ctx = build_recent_context_string(self._chat_sub().chat_history)

                    from ..lib.intent_detector import detect_vl_relevance
                    vl_image_idx = await detect_vl_relevance(
                        user_query=user_msg,
                        image_context=image_context_str,
                        automatik_model=effective_auto,
                        llm_client=llm_client,
                        automatik_num_ctx=auto_num_ctx,
                        recent_context=recent_ctx,
                    )

                    if vl_image_idx is not None:
                        image_path = resolve_image_path_by_index(image_list, vl_image_idx)

                        if image_path:
                            self.add_debug(f"📷 VL Follow-up: Image {vl_image_idx} → {image_path.name}")
                            yield

                            # Cold start check for VL model
                            if self.backend_type == "llamacpp":  # type: ignore[attr-defined]
                                try:
                                    import httpx
                                    swap_base = self.backend_url.rstrip("/").removesuffix("/v1")  # type: ignore[attr-defined]
                                    async with httpx.AsyncClient(timeout=5.0) as _http:
                                        resp = await _http.get(f"{swap_base}/running")
                                        running = [m.get("model") for m in resp.json().get("running", [])]
                                        _eff_vl = self._effective_model_id("vision")  # type: ignore[attr-defined]
                                        if _eff_vl not in running:
                                            self.add_debug(f"🔄 VL Model Cold Start ({_eff_vl}) — loading...")  # type: ignore[attr-defined]
                                            yield
                                except Exception:
                                    pass

                            # Build multimodal content
                            content_parts = []

                            if not self.vision_thinking:  # type: ignore[attr-defined]
                                content_parts.append({"type": "text", "text": "/no_think"})

                            base64_data = load_image_as_base64(image_path)
                            content_parts.append({
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_data}"},
                            })
                            content_parts.append({"type": "text", "text": user_msg})

                            async for _ in self._run_vl_inference(
                                user_msg, content_parts, detected_intent, detected_language,
                            ):
                                yield
                            return  # VL follow-up complete

            # ============================================================
            # DIALOG ROUTING (uses intent/addressee from above)
            # ============================================================

            # Track if Sokrates should be skipped (AIfred direct addressing)
            skip_sokrates_analysis = False

            # Active agent override: if user selected a non-AIfred agent via toggle,
            # treat it as direct addressing (skip addressee detection)
            if not addressed_to and self.active_agent != "aifred":  # type: ignore[attr-defined]
                addressed_to = self.active_agent  # type: ignore[attr-defined]

            if addressed_to and addressed_to != "aifred":
                # User directly addresses a non-AIfred agent → that agent responds
                from ..lib.multi_agent import run_generic_agent_direct_response
                from ..lib.agent_config import get_agent_config
                agent_config = get_agent_config(addressed_to)
                agent_label = agent_config.display_name if agent_config else addressed_to.capitalize()
                agent_emoji = agent_config.emoji if agent_config else "🤖"
                self.add_debug(f"{agent_emoji} Direct addressing: {agent_label}")
                yield
                async for _ in run_generic_agent_direct_response(self, addressed_to, user_msg, detected_language):  # type: ignore[arg-type]
                    yield
                self._streaming_sub().current_ai_response = ""  # type: ignore[attr-defined]
                self.current_user_message = ""
                self.is_generating = False
                self._save_current_session()  # type: ignore[attr-defined]
                yield
                return

            elif addressed_to == "aifred":
                # User directly addresses AIfred → Skip Sokrates analysis
                self.add_debug("🎩 Direct addressing: AIfred")
                yield
                skip_sokrates_analysis = True

            # ============================================================
            # UNIFIED CHAT HANDLER (Single Source of Truth)
            # All modes (automatik, quick, deep, none) use chat_interactive_mode()
            # ============================================================

            from ..lib.conversation_handler import chat_interactive_mode

            llm_options = {
                'enable_thinking': self.aifred_thinking,  # type: ignore[attr-defined]
                'top_k': self.aifred_top_k,  # type: ignore[attr-defined]
                'top_p': self.aifred_top_p,  # type: ignore[attr-defined]
                'min_p': self.aifred_min_p,  # type: ignore[attr-defined]
                'repeat_penalty': self.aifred_repeat_penalty,  # type: ignore[attr-defined]
            }
            result_data = None

            # Single unified call - research_mode determines the path internally
            async for item in chat_interactive_mode(
                user_text=user_msg,
                stt_time=0.0,
                model_choice=self._effective_model_id("aifred"),  # type: ignore[attr-defined]
                automatik_model=effective_auto,
                history=self._chat_sub().chat_history,
                llm_history=self._chat_sub().llm_history,
                session_id=self.session_id,  # type: ignore[attr-defined]
                temperature_mode=self.temperature_mode,  # type: ignore[attr-defined]
                temperature=self.temperature,  # type: ignore[attr-defined]
                llm_options=llm_options,
                backend_type=self.backend_type,  # type: ignore[attr-defined]
                backend_url=self.backend_url,  # type: ignore[attr-defined]
                state=self,
                pending_images=None,  # images handled by VL fast path above
                user_name=self.user_name,  # type: ignore[attr-defined]
                detected_intent=detected_intent,
                detected_language=detected_language,
                cloud_provider_label=self.cloud_api_provider_label if self.backend_type == "cloud_api" else None,  # type: ignore[attr-defined]
                research_mode=self.research_mode,  # type: ignore[attr-defined]
                automatik_num_ctx=auto_num_ctx,
            ):
                # Route messages based on type
                if item["type"] == "debug":
                    self.add_debug(item["message"])
                    yield

                elif item["type"] == "content":
                    if not self.current_agent:
                        self._set_current_agent("aifred")
                    if self.stream_text_to_ui(item["text"]):  # type: ignore[attr-defined]
                        yield

                elif item["type"] == "result":
                    # Flush remaining buffer to state
                    if self.flush_stream_to_ui():  # type: ignore[attr-defined]
                        yield
                    result_data = item["data"]
                    ai_text = result_data["response_clean"]
                    updated_history = result_data["history"]

                    # Extract sources
                    failed_sources = result_data.get("failed_sources", [])
                    used_sources = result_data.get("used_sources", [])

                    # Embed sources in last message for persistence
                    if updated_history:
                        import json as json_module
                        last_msg = updated_history[-1]
                        if last_msg.get("role") == "assistant":
                            if "metadata" not in last_msg:
                                last_msg["metadata"] = {}

                            all_failed: list[dict[str, Any]] = []
                            if failed_sources or self._pending_failed_sources:  # type: ignore[attr-defined, has-type]
                                all_failed = (self._pending_failed_sources or []) + (failed_sources or [])  # type: ignore[attr-defined, has-type]
                                if all_failed:
                                    failed_markup = f"<!--FAILED_SOURCES:{json_module.dumps(all_failed)}-->\n"
                                    last_msg["content"] = failed_markup + last_msg.get("content", "")
                                    last_msg["metadata"]["failed_sources"] = all_failed

                            if used_sources:
                                used_markup = f"<!--USED_SOURCES:{json_module.dumps(used_sources)}-->\n"
                                last_msg["content"] = used_markup + last_msg.get("content", "")
                                last_msg["metadata"]["used_sources"] = used_sources

                            last_msg["used_sources"] = used_sources or []
                            last_msg["failed_sources"] = all_failed or []

                    # Update State for UI
                    self.used_sources = used_sources or []  # type: ignore[attr-defined]
                    self.failed_sources = all_failed  # type: ignore[attr-defined]
                    self._pending_failed_sources: list[dict[str, str]] = []  # type: ignore[attr-defined, var-annotated]
                    self._pending_used_sources: list[dict[str, Any]] = []  # type: ignore[attr-defined, var-annotated]

                    # Combine sources for UI display
                    combined: list[dict[str, Any]] = []
                    for src in (used_sources or []):
                        combined.append({
                            "url": src.get("url", ""),
                            "word_count": src.get("word_count", 0),
                            "rank_index": src.get("rank_index", 999),
                            "success": True,
                        })
                    for src in all_failed:
                        combined.append({
                            "url": src.get("url", ""),
                            "error": src.get("error", "Unknown"),
                            "rank_index": src.get("rank_index", 999),
                            "success": False,
                        })
                    self.all_sources = sorted(combined, key=lambda x: x.get("rank_index", 999))  # type: ignore[attr-defined]

                    # Update history
                    self._chat_sub().chat_history = updated_history
                    if "llm_history" in result_data:
                        self._chat_sub().llm_history = result_data["llm_history"]

                    self._streaming_sub().current_ai_response = ""  # type: ignore[attr-defined]
                    self.current_user_message = ""
                    yield

                    # Finalize streaming TTS
                    if self.enable_tts and self.tts_autoplay and self.tts_streaming_enabled:  # type: ignore[attr-defined]
                        audio_urls = await self._finalize_streaming_tts()  # type: ignore[attr-defined]
                        _ch = self._chat_sub()
                        if audio_urls and _ch.chat_history:
                            for i in range(len(_ch.chat_history) - 1, -1, -1):
                                if _ch.chat_history[i].get("role") == "assistant":
                                    if "metadata" not in _ch.chat_history[i]:
                                        _ch.chat_history[i]["metadata"] = {}
                                    _ch.chat_history[i]["metadata"]["audio_urls"] = audio_urls
                                    _ch.chat_history[i]["has_audio"] = True
                                    _ch.chat_history[i]["audio_urls_json"] = json.dumps(audio_urls)
                                    log_message(f"🔊 TTS: Added {len(audio_urls)} audio URLs to message metadata")
                                    break
                            _ch.chat_history = list(_ch.chat_history)
                            yield

                    # Multi-Agent analysis
                    async for _ in self._maybe_run_multi_agent(
                        user_msg, ai_text, detected_language, skip_sokrates_analysis,
                    ):
                        yield

                    self.is_generating = False
                    yield

                elif item["type"] == "progress":
                    if item.get("clear", False):
                        self.clear_progress()
                    else:
                        self.set_progress(
                            phase=item.get("phase", ""),
                            current=item.get("current", 0),
                            total=item.get("total", 0),
                            failed=item.get("failed", 0),
                        )

                elif item["type"] == "history_update":
                    self._chat_sub().chat_history = item["data"]
                    self.add_debug(f"📊 History updated: {len(item['data'])} messages")

                elif item["type"] == "failed_sources":
                    self.failed_sources = item["data"]  # type: ignore[attr-defined]
                    self._pending_failed_sources = item["data"]  # type: ignore[attr-defined]
                    from ..lib.i18n import t
                    self.add_debug(f"⚠️ {t('sources_unavailable', count=len(item['data']))}")

                elif item["type"] == "error":
                    self.add_debug(f"❌ Error: {item.get('message', 'Unknown error')}")
                    self.is_generating = False
                    self.clear_progress()
                    self.current_user_message = ""
                    self._streaming_sub().current_ai_response = ""  # type: ignore[attr-defined]

                yield

            # Final cleanup — flush remaining stream buffer and clear state
            self._js_chunk_buffer = ""  # type: ignore[attr-defined]
            self._streaming_sub().current_ai_response = ""  # type: ignore[attr-defined]
            yield

        except Exception as e:
            error_msg = f"Error: {e!s}"
            self._js_chunk_buffer = ""  # type: ignore[attr-defined]
            self._streaming_sub().current_ai_response = error_msg  # type: ignore[attr-defined]

            # APPEND error as separate panel
            # Note: User panel was already created above with user_msg/display_user_msg
            self.add_agent_panel(
                agent="aifred",
                content=error_msg,
                mode="error",
                round_num=None,
                metadata=None,  # No metrics for errors
                sync_llm_history=True,  # Sync error to llm_history
            )

            self.add_debug(f"❌ Generation failed: {e}")
            from ..backends.base import BackendConnectionError
            if not isinstance(e, BackendConnectionError):
                import traceback
                self.add_debug(f"Traceback: {traceback.format_exc()}")

        finally:
            self.is_generating = False
            yield  # Let React update is_generating=False (button re-enables via Reflex binding)
            # NOTE: TTS polling stops automatically via data-polling attribute (MutationObserver)
            # Clear pending images after sending
            if len(self.pending_images) > 0:  # type: ignore[attr-defined]
                self.clear_pending_images()  # type: ignore[attr-defined]

            # TTS: Generate audio for AI response if enabled (BEFORE title generation for faster feedback)
            # IMPORTANT: Only for Standard mode! Multi-Agent modes generate TTS via add_agent_panel()
            # which adds to tts_audio_queue. This prevents duplicate TTS generation.
            # SKIP if streaming TTS is enabled - text was already sent sentence-by-sentence
            if self.enable_tts and self.multi_agent_mode == "standard" and not self.tts_streaming_enabled:  # type: ignore[attr-defined]
                try:
                    self.add_debug("🔊 TTS: Starting TTS generation...")
                    # Get AI response from llm_history (clean text without HTML formatting)
                    # Format: {"role": "assistant", "content": "[AGENT]: text"}
                    _ch = self._chat_sub()
                    if len(_ch.llm_history) > 0:
                        last_msg = _ch.llm_history[-1]
                        if last_msg.get("role") == "assistant":
                            ai_response = last_msg.get("content", "")
                            # Extract agent from label prefix like "[AIFRED]: " or "[SOKRATES]: "
                            tts_agent = "aifred"  # Default
                            agent_match = re.match(r'^\[(AIFRED|SOKRATES|SALOMO)\]:\s*', ai_response)
                            if agent_match:
                                tts_agent = agent_match.group(1).lower()
                                ai_response = ai_response[agent_match.end():]
                            if ai_response and ai_response.strip():
                                # Generate TTS and wait for completion
                                # This allows audio URL to be added to message metadata
                                await self._generate_tts_for_response(ai_response, agent=tts_agent)  # type: ignore[attr-defined]
                                yield  # Update UI with audio button
                            else:
                                from ..lib.logging_utils import console_separator
                                self.add_debug("⚠️ TTS: Enabled but no AI response to convert")
                                console_separator()
                                self.add_debug("────────────────────")
                        else:
                            from ..lib.logging_utils import console_separator
                            self.add_debug("⚠️ TTS: Last message is not from assistant")
                            console_separator()
                            self.add_debug("────────────────────")
                    else:
                        from ..lib.logging_utils import console_separator
                        self.add_debug("⚠️ TTS: Enabled but LLM history is empty")
                        console_separator()
                        self.add_debug("────────────────────")
                except (RuntimeError, FileNotFoundError, ValueError) as tts_error:
                    self.add_debug(f"⚠️ TTS generation failed: {tts_error}")
                    log_message(f"❌ TTS error in finally block: {tts_error}")

            # Generate session title at end of flow (uses small Automatik model)
            # Only runs on first Q&A pair, skipped if title already exists
            # Skip if no AI response was generated (e.g. RPC connection error)
            if ai_text:
                async for _ in self._generate_session_title():  # type: ignore[attr-defined]
                    yield  # Forward UI updates from title generation

            # Auto-Save: Session nach jeder Chat-Nachricht speichern
            # IMPORTANT: Save BEFORE refresh so message_count is up-to-date
            self._save_current_session()  # type: ignore[attr-defined]

            # Refresh session list to update sorting (last_seen changed) and message count
            self.refresh_session_list()  # type: ignore[attr-defined]
            yield

            # Final cleanup: Clear streaming state
            self._set_current_agent("")
            self._streaming_sub().current_ai_response = ""  # type: ignore[attr-defined]

    # ── Clear Chat ───────────────────────────────────────────────────

    def clear_chat(self) -> None:
        """UI Event Handler: Clear chat history (shows debug message)."""
        if not self.logged_in_user:  # type: ignore[attr-defined]
            self.add_debug("⚠️ Bitte zuerst anmelden")
            return
        self._clear_chat_internal(silent=False)  # type: ignore[attr-defined]

    # ── Save Session Memory ──────────────────────────────────────────

    async def save_session_memory(self) -> None:
        """Generate a session summary and store it for all participating agents."""
        import re
        import reflex as rx
        from ..lib.agent_memory import get_agent_memory

        if not self.logged_in_user:  # type: ignore[attr-defined]
            return

        history = self._chat_sub().chat_history  # type: ignore[attr-defined]
        if len(history) < 2:
            yield rx.toast.info("Not enough messages to summarize", duration=3000, position="top-center")
            return

        memory = get_agent_memory()
        if not memory:
            yield rx.toast.error("Agent memory unavailable", duration=3000, position="top-center")
            return

        # Collect all agents that participated in this conversation
        participating_agents: set[str] = set()
        for msg in history:
            if msg.get("role") == "assistant":
                agent = msg.get("agent", "")
                if agent and agent != "vision":
                    participating_agents.add(agent)
        # Always include aifred as default
        if not participating_agents:
            participating_agents.add("aifred")

        # Build conversation text for summarization
        conv_lines = []
        for msg in history:
            role = msg.get("role", "user")
            agent = msg.get("agent_display_name", msg.get("agent", ""))
            content = msg.get("content", "")
            clean = re.sub(r'<[^>]+>', '', content).strip()
            if role == "user":
                conv_lines.append(f"User: {clean}")
            else:
                speaker = agent or "Assistant"
                conv_lines.append(f"{speaker}: {clean}")

        conversation_text = "\n".join(conv_lines)

        # Limit to ~4000 chars to keep LLM call fast
        if len(conversation_text) > 4000:
            conversation_text = conversation_text[-4000:]

        # Generate summary via LLM
        from ..lib.llm_client import LLMClient
        llm_client = LLMClient(
            backend_type=self.backend_type,  # type: ignore[attr-defined]
            base_url=self.backend_url,  # type: ignore[attr-defined]
        )
        model = self._effective_model_id("aifred")  # type: ignore[attr-defined]

        summary_prompt = (
            "Summarize this conversation in 4-5 sentences. "
            "Focus on the key topics, decisions, insights, and user preferences. "
            "Write in the same language as the conversation.\n\n"
            f"{conversation_text}"
        )

        from ..lib.agent_config import get_agent_config
        agent_names = []
        for aid in participating_agents:
            cfg = get_agent_config(aid)
            agent_names.append(cfg.display_name if cfg else aid.capitalize())

        self.add_debug(f"📌 Generating session summary ({len(history)} messages) for: {', '.join(agent_names)}")  # type: ignore[attr-defined]
        yield

        try:
            summary = ""
            async for chunk in llm_client.chat_stream(
                model=model,
                messages=[{"role": "user", "content": summary_prompt}],
                options={
                    "temperature": 0.3,
                    "max_tokens": 300,
                    "top_k": 40, "top_p": 0.95, "min_p": 0.05,
                    "repeat_penalty": 1.0,
                    "enable_thinking": False,
                },
            ):
                if chunk.get("type") == "content":
                    summary += chunk.get("text", "")

            summary = summary.strip()
            if not summary:
                yield rx.toast.error("Failed to generate summary", duration=3000, position="top-center")
                return

            # Store/update per agent — check duplicates individually
            sid = self.session_id  # type: ignore[attr-defined]
            stored_count = 0
            updated_count = 0
            for aid in participating_agents:
                if sid and memory.find_by_session(aid, sid):
                    memory.update_by_session(aid, sid, summary)
                    updated_count += 1
                else:
                    await memory.store(
                        agent_id=aid,
                        content=summary,
                        memory_type="session_summary",
                        summary=summary[:120],
                        session_id=sid,
                    )
                    stored_count += 1

            parts = []
            if stored_count:
                parts.append(f"{stored_count} pinned")
            if updated_count:
                parts.append(f"{updated_count} updated")
            status = ", ".join(parts)
            self.add_debug(f"📌 Session memory: {status} — {summary[:100]}...")  # type: ignore[attr-defined]
            yield rx.toast.success(f"Session memory: {status}", duration=3000, position="top-center")

        except Exception as e:
            self.add_debug(f"❌ Session pin failed: {e}")  # type: ignore[attr-defined]
            yield rx.toast.error(f"Error: {e}", duration=3000, position="top-center")
