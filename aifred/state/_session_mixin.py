"""Session mixin for AIfred state.

Handles session CRUD, title generation, session restore, and session list.
"""

from __future__ import annotations

from typing import Any, Dict, List

import reflex as rx


class SessionMixin(rx.State, mixin=True):
    """Mixin for session management - CRUD, titles, restore."""

    # ── State Variables ──────────────────────────────────────────────
    session_id: str = ""  # Session ID from cookie (32 hex chars)
    session_restored: bool = False  # True if chat history was loaded from session
    _session_initialized: bool = False  # Guard against multiple session restore callbacks

    available_sessions: List[Dict[str, Any]] = []  # List of sessions from list_sessions()
    current_session_title: str = ""  # Title of current session (for display)

    # ── Session CRUD ─────────────────────────────────────────────────

    def new_session(self):  # type: ignore[return]
        """Create a new empty session and switch to it."""
        from ..lib.session_storage import generate_session_id, create_empty_session
        from ..lib.logging_utils import log_message

        # Must be logged in to create session
        if not self.logged_in_user:  # type: ignore[attr-defined]
            self.add_debug("Not logged in")  # type: ignore[attr-defined]
            return

        # Note: No save here - sessions are auto-saved after each inference

        # Generate new device ID and create empty session file with owner
        new_id = generate_session_id()
        create_empty_session(new_id, owner=self.logged_in_user)  # type: ignore[attr-defined]

        # Switch to new device ID BEFORE clearing
        # (so clear_chat() cleans up the NEW session's directories)
        self.session_id = new_id
        self.current_session_title = ""

        # Reuse clear_chat() for state reset (avoids duplication)
        # silent=True: Avoid confusing "Chat cleared" message on new session creation
        self._clear_chat_internal(silent=True)  # type: ignore[attr-defined]

        # Refresh session list
        self.refresh_session_list()

        log_message(f"Created new session: {new_id[:8]}...")

        # Update session cookie for TTS SSE (so custom.js can open SSE on page reload)
        from ..lib.browser_storage import set_session_id_script
        return rx.call_script(set_session_id_script(new_id))

    def switch_session(self, session_id: str):  # type: ignore[return]
        """Switch to a different session.

        Loads the target session and updates state.
        Note: No save here - sessions are auto-saved after each inference.
        """
        from ..lib.session_storage import load_session
        from ..lib.logging_utils import log_message

        self.add_debug(f"switch_session called: {session_id[:8] if session_id else 'None'}...")  # type: ignore[attr-defined]

        # If already on this session but chat_history is empty, reload it
        # (can happen when session_id was set from cookie but data wasn't loaded)
        if session_id == self.session_id:
            if self._chat_sub().chat_history:
                self.add_debug("Already on this session, skipping")  # type: ignore[attr-defined]
                return
            else:
                self.add_debug("Same session but empty history, reloading...")  # type: ignore[attr-defined]

        # Load target session
        session = load_session(session_id)
        if session is None:
            self.add_debug(f"Session {session_id[:8]}... not found, switching to newest")  # type: ignore[attr-defined]
            # Session was deleted - switch to newest available or create new
            self.refresh_session_list()
            if self.available_sessions:
                newest = self.available_sessions[0]
                self._load_session_by_id(newest["session_id"])
            else:
                self.new_session()
            return

        # Update session_id and load session data
        self.session_id = session_id
        data = session.get("data", {})

        # Load debug messages first (so subsequent add_debug calls are preserved)
        saved_debug = data.get("debug_messages", [])

        # Load chat history
        chat_history = data.get("chat_history", [])
        ch = self._chat_sub()
        ch.chat_history = chat_history
        ch.llm_history = data.get("llm_history", [])

        # Normalize URLs to relative paths (fixes port-dependent image loading)
        self._normalize_upload_urls()  # type: ignore[attr-defined]

        # Restore debug messages and add load info
        self.debug_messages = saved_debug  # type: ignore[attr-defined]
        self.add_debug(f"Loaded {len(chat_history)} messages")  # type: ignore[attr-defined]

        # Update session title
        self.current_session_title = data.get("title", "")

        # Clear streaming state
        self._streaming_sub().current_ai_response = ""  # type: ignore[attr-defined]
        self.current_user_message = ""  # type: ignore[attr-defined]
        self._set_current_agent("")  # type: ignore[attr-defined]

        # Note: Don't refresh_session_list() here - it would re-sort by last_seen
        # and move the clicked session to a different position. The highlighting
        # is based on session_id which is already updated above.

        log_message(f"Switched to session: {session_id[:8]}...")
        self.add_debug(f"Switched to session: {self.current_session_title or session_id[:8]}...")  # type: ignore[attr-defined]

        # Update session cookie for TTS SSE (so custom.js can open SSE on page reload)
        from ..lib.browser_storage import set_session_id_script
        return rx.call_script(set_session_id_script(session_id))

    def delete_session(self, session_id: str):
        """Delete a session (cannot delete current session)."""
        from ..lib.session_storage import delete_session as storage_delete_session
        from ..lib.logging_utils import log_message

        # Cannot delete current session
        if session_id == self.session_id:
            self.add_debug("Cannot delete current session")  # type: ignore[attr-defined]
            return

        # Delete session
        if storage_delete_session(session_id):
            log_message(f"Deleted session: {session_id[:8]}...")
            self.add_debug("Session deleted")  # type: ignore[attr-defined]
            # Refresh list
            self.refresh_session_list()
        else:
            self.add_debug("Failed to delete session")  # type: ignore[attr-defined]

    # ── Session Load / Restore ───────────────────────────────────────

    def _load_session_by_id(self, session_id: str):
        """Load a specific session by ID (internal helper)."""
        from ..lib.session_storage import load_session, get_session_title
        from ..lib.context_manager import estimate_tokens_from_llm_history
        from ..lib.formatting import format_number
        from ..lib.config import HISTORY_COMPRESSION_TRIGGER

        self.session_id = session_id
        session = load_session(session_id)

        if session and session.get("data"):
            self._restore_session(session)
            self.session_restored = True

            # Update title
            title = get_session_title(session_id)
            self.current_session_title = title or ""

            # Show context utilization after session restore
            # Use llm_history for consistent token counting (same as during inference)
            _llm_hist = self._chat_sub().llm_history
            if _llm_hist:
                estimated_tokens = estimate_tokens_from_llm_history(_llm_hist)

                if self._min_agent_context_limit > 0:  # type: ignore[attr-defined]
                    utilization = (estimated_tokens / self._min_agent_context_limit) * 100  # type: ignore[attr-defined]
                    self.add_debug(f"   \u2514\u2500 History: {format_number(estimated_tokens)} / {format_number(self._min_agent_context_limit)} tok ({int(utilization)}%)")  # type: ignore[attr-defined]

                    # Warn if compression will trigger on next message
                    if utilization >= HISTORY_COMPRESSION_TRIGGER * 100:
                        self.add_debug(f"History compression will trigger on next message (>{int(HISTORY_COMPRESSION_TRIGGER * 100)}%)")  # type: ignore[attr-defined]
                else:
                    self.add_debug(f"   \u2514\u2500 History: {format_number(estimated_tokens)} tokens")  # type: ignore[attr-defined]
        else:
            self.session_restored = False

    def _restore_session(self, session: dict):
        """Stellt Chat-History aus gespeicherter Session wieder her.

        DUAL-HISTORY (v2.13.0+):
        - chat_history: UI-vollstaendig (Original-Messages erhalten)
        - llm_history: LLM-komprimiert (ready-to-use fuer LLM-Aufrufe)

        Args:
            session: Session-Dict mit "data" Feld
        """
        data = session.get("data", {})

        # Chat-History wiederherstellen (dict-based format)
        # PRE-MESSAGE Check in send_message() prueft automatisch ob Kompression noetig ist
        # WICHTIG: Auch leere Listen setzen (fuer API-Clear)!
        if "chat_history" in data:
            stored = data["chat_history"]
            # Check format: new dict-based or old tuple-based
            if stored and isinstance(stored[0], (list, tuple)):
                # Old tuple format - Clean Break, ignore old sessions
                self._chat_sub().chat_history = []
                self.add_debug("Old session format detected - starting fresh")  # type: ignore[attr-defined]
            else:
                # New dict format - use directly
                self._chat_sub().chat_history = stored if stored else []
                # Normalize URLs to relative paths (fixes port-dependent image loading)
                self._normalize_upload_urls()  # type: ignore[attr-defined]

        # DUAL-HISTORY (v2.13.0+): llm_history laden
        # WICHTIG: Auch leere Listen setzen (fuer API-Clear)!
        if "llm_history" in data:
            self._chat_sub().llm_history = data["llm_history"]
        else:
            # Keine llm_history -> leere Liste (alte Sessions werden nicht migriert)
            self._chat_sub().llm_history = []

        # DEBUG-PERSISTENCE (v2.14.0+): debug_messages wiederherstellen
        # Saved messages (from before restart) come first, then startup messages
        # This keeps chronological order: session messages < startup/login messages
        if "debug_messages" in data:
            if data["debug_messages"]:
                startup_messages = self.debug_messages.copy()  # type: ignore[attr-defined]
                self.debug_messages = data["debug_messages"] + startup_messages  # type: ignore[attr-defined]
            # Empty list = new/cleared session — keep startup messages as-is

        # Session title wiederherstellen
        self.current_session_title = data.get("title", "")

        # Note: Don't refresh_session_list() here - it's called once in on_load()
        # and only needs updating when new messages are sent (via _save_current_session)

    # ── Session Persistence ──────────────────────────────────────────

    def _save_current_session(self):
        """Speichert aktuelle Session auf Server.

        Wird nach jeder Chat-Aenderung aufgerufen (Auto-Save).
        Nur speichern wenn session_id vorhanden (Session initialisiert).
        DUAL-HISTORY (v2.13.0+): Speichert sowohl chat_history als auch llm_history.
        """
        if not self.session_id:
            return

        from ..lib.session_storage import update_chat_data
        from ..lib.config import DEBUG_LOG_MAX_ENTRIES

        # DEBUG-PERSISTENCE: Keep only last N entries
        debug_to_save = self.debug_messages[-DEBUG_LOG_MAX_ENTRIES:] if self.debug_messages else []  # type: ignore[attr-defined]

        update_chat_data(
            session_id=self.session_id,
            chat_history=self._chat_sub().chat_history,
            chat_summaries=None,  # Aktuell nicht persistiert
            llm_history=self._chat_sub().llm_history,
            debug_messages=debug_to_save,
            is_generating=self.is_generating,  # type: ignore[attr-defined]
            owner=self.logged_in_user  # type: ignore[attr-defined]
        )

    # ── Session List ─────────────────────────────────────────────────

    def refresh_session_list(self):  # type: ignore[return]
        """Refresh the list of available sessions for the session picker.

        Also synchronizes current session if it was modified externally
        (e.g., chat cleared in another tab/port).

        Additionally reconnects TTS SSE stream to ensure this device receives
        audio events (multi-device support - Last Writer Wins).
        """
        from ..lib.session_storage import list_sessions, get_session_title, load_session

        # Only show sessions owned by logged in user
        self.available_sessions = list_sessions(owner=self.logged_in_user)  # type: ignore[attr-defined]

        # Update current session title
        if self.session_id:
            title = get_session_title(self.session_id)
            self.current_session_title = title or ""

            # Sync check: Compare local state with server state
            # If message counts differ, reload session from server
            # SKIP during generation: local state is ahead of disk (user message
            # added before LLM call, session saved only after response).
            if not self.is_generating:  # type: ignore[attr-defined]
                session = load_session(self.session_id)
                if session and session.get("data"):
                    server_count = len(session["data"].get("chat_history", []))
                    local_count = len(self._chat_sub().chat_history)

                    if server_count != local_count:
                        self.add_debug(f"Session changed externally ({local_count} -> {server_count}), reloading...")  # type: ignore[attr-defined]
                        self._restore_session(session)
                        self.session_restored = True

        # Reconnect TTS SSE stream for this device (multi-device support)
        # When user clicks reload button, they signal "I want to work here now"
        # This ensures TTS audio plays on this device (Last Writer Wins)
        if self.session_id:
            return rx.call_script(f"if(window.startTtsStream) startTtsStream('{self.session_id}');")

    # ── Clear Chat (Internal) ────────────────────────────────────────

    def _clear_chat_internal(self, silent: bool = False):
        """Internal: Clear chat history, pending images, and temporary files.

        Args:
            silent: If True, don't show "Chat cleared" debug message.
                    Used by new_session() to avoid confusing startup messages.
        """
        from ..lib.logging_utils import CONSOLE_SEPARATOR

        ch = self._chat_sub()
        ch.chat_history = []
        ch.llm_history = []
        self._streaming_sub().current_ai_response = ""  # type: ignore[attr-defined]
        self.current_user_message = ""  # type: ignore[attr-defined]
        self.tts_audio_path = ""  # type: ignore[attr-defined]
        self.debug_messages = []  # type: ignore[attr-defined]
        self.pending_images = []  # type: ignore[attr-defined, var-annotated]
        self.image_upload_warning = ""  # type: ignore[attr-defined]

        # TTS Audio-Dateien aufraeumen
        from ..lib.audio_processing import cleanup_old_tts_audio
        try:
            cleanup_old_tts_audio(max_age_hours=0)  # 0 = alle loeschen
        except OSError as e:
            self.add_debug(f"TTS cleanup failed: {e}")  # type: ignore[attr-defined]

        # Session-Bilder aufraeumen (data/images/{session_id}/)
        if self.session_id:
            from ..lib.vision_utils import cleanup_session_images
            try:
                deleted = cleanup_session_images(self.session_id)
                if deleted > 0:
                    self.add_debug(f"{deleted} session image(s) deleted")  # type: ignore[attr-defined]
            except OSError as e:
                self.add_debug(f"Image cleanup failed: {e}")  # type: ignore[attr-defined]

        # Session-Audio aufraeumen (data/audio/{session_id}/)
        if self.session_id:
            from ..lib.audio_processing import cleanup_session_audio
            try:
                deleted = cleanup_session_audio(self.session_id)
                if deleted > 0:
                    self.add_debug(f"{deleted} session audio file(s) deleted")  # type: ignore[attr-defined]
            except OSError as e:
                self.add_debug(f"Audio cleanup failed: {e}")  # type: ignore[attr-defined]

        # Clear Web-Quellen State (Sources Collapsible)
        self.used_sources = []  # type: ignore[attr-defined, var-annotated]
        self.failed_sources = []  # type: ignore[attr-defined, var-annotated]
        self.all_sources = []  # type: ignore[attr-defined, var-annotated]

        # Clear Sokrates Multi-Agent state
        self.sokrates_critique = ""  # type: ignore[attr-defined]
        self.sokrates_pro_args = ""  # type: ignore[attr-defined]
        self.sokrates_contra_args = ""  # type: ignore[attr-defined]
        self.show_sokrates_panel = False  # type: ignore[attr-defined]
        self.debate_round = 0  # type: ignore[attr-defined]
        self.debate_user_interjection = ""  # type: ignore[attr-defined]
        self.debate_in_progress = False  # type: ignore[attr-defined]

        # Clear Research Cache for this session
        # Wichtig: Sonst koennen alte (englische) Recherche-Daten wieder verwendet werden!
        if self.session_id:
            from ..lib.cache_manager import delete_cached_research
            delete_cached_research(self.session_id)

        # Clear session title (new session has no title yet)
        self.current_session_title = ""

        # Clear title in session file too (so new title can be generated)
        if self.session_id:
            from ..lib.session_storage import update_session_title
            update_session_title(self.session_id, "")  # Empty title = will regenerate

        if not silent:
            self.add_debug("Chat cleared")  # type: ignore[attr-defined]
            # Separator after clear operation
            self.add_debug(CONSOLE_SEPARATOR)  # type: ignore[attr-defined]
            from ..lib.logging_utils import console_separator
            console_separator()  # Log-File

        # Session speichern (leerer Chat)
        self._save_current_session()

        # Refresh session list to show cleared title
        self.refresh_session_list()

    # ── Title Generation ─────────────────────────────────────────────

    async def _generate_session_title(self, title_model_override: str = ""):
        """Generate a chat title using LLM based on first Q&A pair.

        This is an async generator that yields for UI updates during title generation.
        Called at the END of send_message() flow (in finally block).
        Uses the Automatik model (same as Intent Detection and other Automatik tasks).

        Args:
            title_model_override: If set, use this model instead of _effective_automatik_id.
                Useful after Vision-Only inference where the vision model is still loaded.

        Only executes on first Q&A pair - skipped if title already exists.

        Yields:
            None - yields are for UI updates only
        """
        from ..lib.session_storage import get_session_title, update_session_title
        from ..lib.prompt_loader import load_prompt, get_language
        from ..lib.llm_client import LLMClient
        from ..lib.logging_utils import log_message, console_separator
        from ..lib.context_manager import strip_thinking_blocks

        # Skip if already has title
        if self.current_session_title:
            return

        existing_title = get_session_title(self.session_id)
        if existing_title:
            self.current_session_title = existing_title
            return

        # Need at least 2 messages (user + assistant)
        # Use llm_history - it's already cleaned (no think tags, no HTML)
        _llm_hist = self._chat_sub().llm_history
        if len(_llm_hist) < 2:
            return

        # Find first user message and first assistant response from llm_history
        first_user_msg = None
        first_ai_response = None

        for msg in _llm_hist:
            content = msg.get("content", "")
            if msg.get("role") == "user" and first_user_msg is None:
                first_user_msg = content
            elif msg.get("role") == "assistant" and first_ai_response is None:
                # llm_history has "[AIFRED]: " prefix - remove it
                if content.startswith("[AIFRED]: "):
                    content = content[10:]
                first_ai_response = content

            if first_user_msg and first_ai_response:
                break

        # Vision-Only: If no user text but AI response exists, use placeholder
        # This allows title generation for image-only uploads
        if not first_user_msg and first_ai_response:
            first_user_msg = "[Bildanalyse]"  # Placeholder for title generation

        if not first_user_msg or not first_ai_response:
            return

        # Clean up any remaining HTML/tags (llm_history should be clean, but just in case)
        import re
        first_user_msg = re.sub(r'<[^>]+>', '', first_user_msg).strip()
        first_ai_response = re.sub(r'<[^>]+>', '', first_ai_response).strip()

        # Truncate if too long (keep first ~500 chars each)
        if len(first_user_msg) > 500:
            first_user_msg = first_user_msg[:500] + "..."
        if len(first_ai_response) > 500:
            first_ai_response = first_ai_response[:500] + "..."

        # Track whether title was successfully generated (for finally block)
        _title_done = False

        try:
            # Show user that title is being generated (can take a few seconds)
            self.add_debug("Generating session title...")  # type: ignore[attr-defined]
            yield  # Update UI immediately to show "Generating..." message

            # Load prompt in detected language (from Intent Detection, fallback to UI language)
            prompt = load_prompt(
                "utility/chat_title",
                lang=self._last_detected_language or get_language(),  # type: ignore[attr-defined]
                user_message=first_user_msg,
                ai_response=first_ai_response
            )

            title_model = title_model_override or self._effective_automatik_id  # type: ignore[attr-defined]

            llm_client = LLMClient(
                backend_type=self.backend_type,  # type: ignore[attr-defined]
                base_url=self._get_backend_url(),  # type: ignore[attr-defined]
                provider=self.cloud_api_provider if self.backend_type == "cloud_api" else None  # type: ignore[attr-defined]
            )

            messages: list[dict[str, Any] | Any] = [{"role": "user", "content": prompt}]

            # num_ctx: Must match the currently loaded context to avoid Ollama reload.
            # Ollama uses model DEFAULT (not currently loaded ctx) when num_ctx is omitted.
            # -> omitting num_ctx after main inference would cause a full reload (5-28s penalty).
            if title_model_override == self.vision_model_id and self.vision_model_id:  # type: ignore[attr-defined]
                # Vision model override -> reuse vision context to avoid Ollama reload.
                # Use get_agent_num_ctx("vision", ...) so VRAM calibration is used when
                # manual mode is off (same context as VL inference).
                from ..lib.research.context_utils import get_agent_num_ctx
                title_num_ctx, _ = get_agent_num_ctx("vision", self, self.vision_model_id)  # type: ignore[attr-defined, arg-type]
            elif title_model == self.aifred_model_id and self.aifred_max_context:  # type: ignore[attr-defined]
                # Same model as main LLM -> reuse calibrated context, no reload
                title_num_ctx = self.aifred_max_context  # type: ignore[attr-defined]
            else:
                from ..lib.config import AUTOMATIK_LLM_NUM_CTX
                title_num_ctx = AUTOMATIK_LLM_NUM_CTX

            options = {
                "temperature": 0.3,  # Low temperature for consistent titles
                "num_predict": 300,  # Room for reasoning (~100-150 tok) + title (~10 tok)
                "enable_thinking": False,  # Respected by Qwen3; GPT-OSS ignores it but works via num_predict headroom
                "num_ctx": title_num_ctx,
            }

            # Timeout: Title generation runs AFTER is_generating=False.
            # Large models (120B+) need significant PP time even for short prompts.
            import asyncio
            response = await asyncio.wait_for(
                llm_client.chat(
                    model=title_model,
                    messages=messages,
                    options=options
                ),
                timeout=30.0
            )

            # Extract and clean title - strip thinking blocks first!
            title = response.text.strip()
            title = strip_thinking_blocks(title)  # Remove <think>...</think>
            # Remove quotes if present
            title = title.strip('"\'')
            # Remove trailing punctuation
            title = title.rstrip('.!?:')

            if title:
                update_session_title(self.session_id, title)
                self.current_session_title = title
                # Note: refresh_session_list() is called in send_message() finally block

                # Debug output with closing separator
                self.add_debug(f"Session title: {title}")  # type: ignore[attr-defined]
                console_separator()
                self.add_debug("────────────────────")  # type: ignore[attr-defined]
                _title_done = True
                yield  # Update UI to show generated title
            else:
                # LLM returned empty/thinking-only response
                log_message("Title generation: LLM returned empty title")
                self.add_debug("Session title: empty response")  # type: ignore[attr-defined]
                self.add_debug("────────────────────")  # type: ignore[attr-defined]
                _title_done = True

        except asyncio.TimeoutError:
            log_message("Title generation timed out (>30s) - skipping")
            self.add_debug("Session title: Timeout (>30s)")  # type: ignore[attr-defined]
            self.add_debug("────────────────────")  # type: ignore[attr-defined]
            _title_done = True
        except Exception as e:
            log_message(f"Title generation failed: {e}")
            self.add_debug(f"Session title failed: {e}")  # type: ignore[attr-defined]
            self.add_debug("────────────────────")  # type: ignore[attr-defined]
            _title_done = True
        finally:
            # Catch silent cancellations: GeneratorExit (aclose) and CancelledError
            # bypass except Exception. Log so user sees what happened.
            if not _title_done:
                log_message("Title generation cancelled (generator closed)")
                self.add_debug("Session title: cancelled")  # type: ignore[attr-defined]
                self.add_debug("────────────────────")  # type: ignore[attr-defined]
