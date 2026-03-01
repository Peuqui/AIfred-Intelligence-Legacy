"""Settings mixin for AIfred state.

Handles saving/loading settings.json, user profile, UI language,
and reset-to-defaults.
"""

from __future__ import annotations

import copy
import os
from typing import Any, Dict

import reflex as rx

from ..lib import TranslationManager, set_language
from ..lib.settings import SETTINGS_FILE, load_settings, save_settings


class SettingsMixin(rx.State, mixin=True):
    """Mixin for settings persistence and UI configuration."""

    # ── User Settings ─────────────────────────────────────────────
    ui_language: str = "de"  # "de" or "en" - for UI language
    user_name: str = ""  # User's name for personalized responses (optional)
    user_gender: str = "male"  # "male" or "female" - for proper salutation (Herr/Frau)

    # ── Settings File Tracking ────────────────────────────────────
    _last_settings_mtime: float = 0.0  # Last seen settings.json mtime (for multi-browser sync)

    # ================================================================
    # SETTINGS PERSISTENCE
    # ================================================================

    def _save_settings(self) -> None:
        """Save current settings to file (per-backend models)."""
        existing = load_settings() or {}
        backend_models = existing.get("backend_models", {})

        # Only update backend models if model IDs are validated against current backend.
        # Prevents saving stale IDs from a different backend during transitions
        # (e.g., backend_id already switched but model_ids not yet validated).
        if self.aifred_model_id and self.backend_id and self.available_models_dict:  # type: ignore[attr-defined, has-type]
            # model_id vars always contain base IDs (SSOT — speed suffix is computed)
            if self.aifred_model_id in self.available_models_dict:  # type: ignore[attr-defined, has-type]
                backend_models[self.backend_id] = {  # type: ignore[attr-defined, has-type]
                    "aifred_model": self.aifred_model_id,  # type: ignore[attr-defined, has-type]
                    "automatik_model": self.automatik_model_id,  # type: ignore[attr-defined, has-type]
                    "vision_model": self.vision_model_id,  # type: ignore[attr-defined, has-type]
                    "sokrates_model": self.sokrates_model_id,  # type: ignore[attr-defined, has-type]
                    "salomo_model": self.salomo_model_id,  # type: ignore[attr-defined, has-type]
                }

        # Only save self.backend_type if backend is fully initialized.
        # Prevents the class default "ollama" from overwriting the persisted
        # backend_type when _save_settings() fires during startup
        # (e.g., vision model auto-select, capabilities check).
        if self._backend_initialized:  # type: ignore[attr-defined, has-type]
            saved_backend_type = self.backend_type  # type: ignore[attr-defined, has-type]
        else:
            saved_backend_type = existing.get("backend_type", self.backend_type)  # type: ignore[attr-defined, has-type]

        settings: Dict[str, Any] = {
            "backend_type": saved_backend_type,
            "cloud_api_provider": self.cloud_api_provider,  # type: ignore[attr-defined, has-type]
            "research_mode": self.research_mode,  # type: ignore[attr-defined, has-type]
            "temperature": self.temperature,  # type: ignore[attr-defined, has-type]
            "temperature_mode": self.temperature_mode,  # type: ignore[attr-defined, has-type]
            "sokrates_temperature": self.sokrates_temperature,  # type: ignore[attr-defined, has-type]
            "sokrates_temperature_offset": self.sokrates_temperature_offset,  # type: ignore[attr-defined, has-type]
            "ui_language": self.ui_language,  # UI language (de/en)
            "user_name": self.user_name,  # User's name for personalized responses
            "user_gender": self.user_gender,  # Gender for salutation (male/female)
            "backend_models": backend_models,  # Merged: preserves all backends
            # Multi-Agent Settings
            "multi_agent_mode": self.multi_agent_mode,  # type: ignore[attr-defined, has-type]
            "max_debate_rounds": self.max_debate_rounds,  # type: ignore[attr-defined, has-type]
            "consensus_type": self.consensus_type,  # type: ignore[attr-defined, has-type]
            "sokrates_model": self.sokrates_model_id,  # type: ignore[attr-defined, has-type]
            "salomo_model": self.salomo_model_id,  # type: ignore[attr-defined, has-type]
            "salomo_temperature": self.salomo_temperature,  # type: ignore[attr-defined, has-type]
            "salomo_temperature_offset": self.salomo_temperature_offset,  # type: ignore[attr-defined, has-type]
            # vLLM YaRN Settings (only enable/disable, factor is calculated dynamically)
            "enable_yarn": self.enable_yarn,  # type: ignore[attr-defined, has-type]
            # NOTE: yarn_factor is NOT saved - always starts at 1.0, system calibrates maximum
            # NOTE: vllm_max_tokens and vllm_native_context are NEVER saved!
            # They are calculated dynamically on every vLLM startup based on VRAM
            # Vision LLM Context Settings (PERSISTENT)
            "vision_num_ctx_enabled": self.vision_num_ctx_enabled,  # type: ignore[attr-defined, has-type]
            "vision_num_ctx": self.vision_num_ctx,  # type: ignore[attr-defined, has-type]
            # Agent Personality & Reasoning Settings
            "aifred_personality": self.aifred_personality,  # type: ignore[attr-defined, has-type]
            "sokrates_personality": self.sokrates_personality,  # type: ignore[attr-defined, has-type]
            "salomo_personality": self.salomo_personality,  # type: ignore[attr-defined, has-type]
            "vision_personality": self.vision_personality,  # type: ignore[attr-defined, has-type]
            "aifred_reasoning": self.aifred_reasoning,  # type: ignore[attr-defined, has-type]
            "sokrates_reasoning": self.sokrates_reasoning,  # type: ignore[attr-defined, has-type]
            "salomo_reasoning": self.salomo_reasoning,  # type: ignore[attr-defined, has-type]
            "vision_reasoning": self.vision_reasoning,  # type: ignore[attr-defined, has-type]
            "aifred_thinking": self.aifred_thinking,  # type: ignore[attr-defined, has-type]
            "sokrates_thinking": self.sokrates_thinking,  # type: ignore[attr-defined, has-type]
            "salomo_thinking": self.salomo_thinking,  # type: ignore[attr-defined, has-type]
            "vision_thinking": self.vision_thinking,  # type: ignore[attr-defined, has-type]
            # Note: Sampling params (top_k, top_p, min_p, repeat_penalty) NOT saved
            # They reset to YAML defaults on restart. Temperature IS saved (see below).
            "aifred_speed_mode": self.aifred_speed_mode,  # type: ignore[attr-defined, has-type]
            "sokrates_speed_mode": self.sokrates_speed_mode,  # type: ignore[attr-defined, has-type]
            "salomo_speed_mode": self.salomo_speed_mode,  # type: ignore[attr-defined, has-type]
            # TTS/STT Settings
            "enable_tts": self.enable_tts,  # type: ignore[attr-defined, has-type]
            "voice": self.tts_voice,  # type: ignore[attr-defined, has-type]
            # Note: tts_speed removed - generation always at 1.0, tempo via tts_playback_rate
            "tts_engine": self.tts_engine,  # type: ignore[attr-defined, has-type]
            "xtts_force_cpu": self.xtts_force_cpu,  # type: ignore[attr-defined, has-type]
            "tts_autoplay": self.tts_autoplay,  # type: ignore[attr-defined, has-type]
            "tts_streaming_enabled": self.tts_streaming_enabled,  # type: ignore[attr-defined, has-type]
            "tts_playback_rate": self.tts_playback_rate,  # type: ignore[attr-defined, has-type]
            "tts_pitch": self.tts_pitch,  # type: ignore[attr-defined, has-type]
            "whisper_model": self.whisper_model_key,  # type: ignore[attr-defined, has-type]
            # whisper_device removed - now in config.py
            "show_transcription": self.show_transcription,  # type: ignore[attr-defined, has-type]
            # Language-specific TTS voices (user preferences per engine/language)
            "tts_voices_per_language": existing.get("tts_voices_per_language", {}),
            # Per-engine agent voice settings
            "tts_agent_voices_per_engine": existing.get("tts_agent_voices_per_engine", {}),
            # Per-engine TTS toggles (autoplay, streaming)
            "tts_toggles_per_engine": existing.get("tts_toggles_per_engine", {}),
            # UI Settings
            "auto_scroll": self.auto_refresh_enabled,  # type: ignore[attr-defined, has-type]
        }
        # Update tts_voices_per_language with current voice selection
        engine_key = self._get_engine_key()  # type: ignore[attr-defined, has-type]
        lang = self.ui_language
        if "tts_voices_per_language" not in settings:
            settings["tts_voices_per_language"] = {}
        if engine_key not in settings["tts_voices_per_language"]:
            settings["tts_voices_per_language"][engine_key] = {}
        settings["tts_voices_per_language"][engine_key][lang] = self.tts_voice  # type: ignore[attr-defined, has-type]

        # Update tts_agent_voices_per_engine with current agent voice settings
        if "tts_agent_voices_per_engine" not in settings:
            settings["tts_agent_voices_per_engine"] = {}
        settings["tts_agent_voices_per_engine"][engine_key] = copy.deepcopy(self.tts_agent_voices)  # type: ignore[attr-defined, has-type]

        # Update tts_toggles_per_engine with current TTS toggles
        if "tts_toggles_per_engine" not in settings:
            settings["tts_toggles_per_engine"] = {}
        settings["tts_toggles_per_engine"][engine_key] = {
            "autoplay": self.tts_autoplay,  # type: ignore[attr-defined, has-type]
            "streaming": self.tts_streaming_enabled,  # type: ignore[attr-defined, has-type]
        }
        save_settings(settings)

        # Update mtime tracker to prevent immediate reload by check_for_updates()
        try:
            self._last_settings_mtime = os.path.getmtime(SETTINGS_FILE)
        except OSError:
            pass

    def _reload_settings_from_file(self) -> None:
        """Reload settings from settings.json file.

        Called when API update flag is detected. Updates all UI-visible settings
        to reflect changes made via REST API.
        """
        settings = load_settings()
        if not settings:
            return

        # Core settings
        self.temperature = settings.get("temperature", self.temperature)  # type: ignore[attr-defined, has-type]
        self.temperature_mode = settings.get("temperature_mode", self.temperature_mode)  # type: ignore[attr-defined, has-type]
        # Research mode
        self.research_mode = settings.get("research_mode", self.research_mode)  # type: ignore[attr-defined, has-type]
        self.research_mode_display = TranslationManager.get_research_mode_display(  # type: ignore[attr-defined, has-type]
            self.research_mode, self.ui_language  # type: ignore[attr-defined, has-type, arg-type]
        )

        # Multi-Agent settings
        self.multi_agent_mode = settings.get("multi_agent_mode", self.multi_agent_mode)  # type: ignore[attr-defined, has-type]
        self.max_debate_rounds = settings.get("max_debate_rounds", self.max_debate_rounds)  # type: ignore[attr-defined, has-type]
        self.consensus_type = settings.get("consensus_type", self.consensus_type)  # type: ignore[attr-defined, has-type]

        # Model IDs - update both ID and display variables
        # AIfred model (top-level "model" field in settings.json)
        if "model" in settings:
            model_id = settings["model"]
            self.aifred_model_id = model_id  # type: ignore[attr-defined, has-type]
            # Update display name if we have the models dict
            if model_id in self.available_models_dict:  # type: ignore[attr-defined, has-type]
                self.aifred_model = self.available_models_dict[model_id]  # type: ignore[attr-defined, has-type]
            else:
                self.aifred_model = model_id  # type: ignore[attr-defined, has-type]

        # Sokrates model
        if "sokrates_model" in settings:
            model_id = settings["sokrates_model"]
            self.sokrates_model_id = model_id  # type: ignore[attr-defined, has-type]
            if model_id in self.available_models_dict:  # type: ignore[attr-defined, has-type]
                self.sokrates_model = self.available_models_dict[model_id]  # type: ignore[attr-defined, has-type]
            else:
                self.sokrates_model = model_id  # type: ignore[attr-defined, has-type]

        # Salomo model
        if "salomo_model" in settings:
            model_id = settings["salomo_model"]
            self.salomo_model_id = model_id  # type: ignore[attr-defined, has-type]
            if model_id in self.available_models_dict:  # type: ignore[attr-defined, has-type]
                self.salomo_model = self.available_models_dict[model_id]  # type: ignore[attr-defined, has-type]
            else:
                self.salomo_model = model_id  # type: ignore[attr-defined, has-type]

        # Automatik model (can be empty = same as AIfred)
        if "automatik_model" in settings:
            model_id = settings["automatik_model"]
            self.automatik_model_id = model_id  # type: ignore[attr-defined, has-type]
            if not model_id:
                self.automatik_model = ""  # type: ignore[attr-defined, has-type]
            elif model_id in self.available_models_dict:  # type: ignore[attr-defined, has-type]
                self.automatik_model = self.available_models_dict[model_id]  # type: ignore[attr-defined, has-type]
            else:
                self.automatik_model = model_id  # type: ignore[attr-defined, has-type]

        # Vision model
        if "vision_model" in settings:
            model_id = settings["vision_model"]
            self.vision_model_id = model_id  # type: ignore[attr-defined, has-type]
            if model_id in self.available_models_dict:  # type: ignore[attr-defined, has-type]
                self.vision_model = self.available_models_dict[model_id]  # type: ignore[attr-defined, has-type]
            else:
                self.vision_model = model_id  # type: ignore[attr-defined, has-type]

        # RoPE factors
        self.aifred_rope_factor = settings.get("aifred_rope_factor", self.aifred_rope_factor)  # type: ignore[attr-defined, has-type]
        self.sokrates_rope_factor = settings.get("sokrates_rope_factor", self.sokrates_rope_factor)  # type: ignore[attr-defined, has-type]
        self.salomo_rope_factor = settings.get("salomo_rope_factor", self.salomo_rope_factor)  # type: ignore[attr-defined, has-type]
        self.automatik_rope_factor = settings.get("automatik_rope_factor", self.automatik_rope_factor)  # type: ignore[attr-defined, has-type]
        self.vision_rope_factor = settings.get("vision_rope_factor", self.vision_rope_factor)  # type: ignore[attr-defined, has-type]

        # Personality toggles
        self.aifred_personality = settings.get("aifred_personality", self.aifred_personality)  # type: ignore[attr-defined, has-type]
        self.sokrates_personality = settings.get("sokrates_personality", self.sokrates_personality)  # type: ignore[attr-defined, has-type]
        self.salomo_personality = settings.get("salomo_personality", self.salomo_personality)  # type: ignore[attr-defined, has-type]
        self.vision_personality = settings.get("vision_personality", self.vision_personality)  # type: ignore[attr-defined, has-type]
        # Sync to prompt_loader
        from ..lib.prompt_loader import set_personality_enabled
        set_personality_enabled("aifred", self.aifred_personality)  # type: ignore[attr-defined, has-type, arg-type]
        set_personality_enabled("sokrates", self.sokrates_personality)  # type: ignore[attr-defined, has-type, arg-type]
        set_personality_enabled("salomo", self.salomo_personality)  # type: ignore[attr-defined, has-type, arg-type]
        set_personality_enabled("vision", self.vision_personality)  # type: ignore[attr-defined, has-type, arg-type]

        # TTS settings
        self.enable_tts = settings.get("enable_tts", self.enable_tts)  # type: ignore[attr-defined, has-type]
        self.tts_voice = settings.get("voice", self.tts_voice)  # type: ignore[attr-defined, has-type]
        saved_engine = settings.get("tts_engine", self.tts_engine)  # type: ignore[attr-defined, has-type]
        # Migrate old display-string format to key format
        if saved_engine and len(saved_engine) > 10:
            engine_map = {"XTTS": "xtts", "MOSS": "moss", "DashScope": "dashscope",
                          "Piper": "piper", "eSpeak": "espeak", "Edge": "edge"}
            for name, key in engine_map.items():
                if name in saved_engine:
                    saved_engine = key
                    break
        self.tts_engine = saved_engine  # type: ignore[attr-defined, has-type]
        self.xtts_force_cpu = settings.get("xtts_force_cpu", self.xtts_force_cpu)  # type: ignore[attr-defined, has-type]
        self.tts_autoplay = settings.get("tts_autoplay", self.tts_autoplay)  # type: ignore[attr-defined, has-type]
        self.tts_streaming_enabled = settings.get("tts_streaming_enabled", self.tts_streaming_enabled)  # type: ignore[attr-defined, has-type]

        # UI language
        new_ui_lang = settings.get("ui_language", self.ui_language)
        if new_ui_lang != self.ui_language and new_ui_lang in ["de", "en"]:
            self.ui_language = new_ui_lang
            from ..lib.formatting import set_ui_locale
            set_ui_locale(new_ui_lang)
            set_language(new_ui_lang)  # Sync prompt language

        # User name
        self.user_name = settings.get("user_name", self.user_name)
        from ..lib.prompt_loader import set_user_name
        set_user_name(self.user_name)

    # ================================================================
    # UI LANGUAGE
    # ================================================================

    def set_ui_language(self, lang: str) -> None:
        """Set UI language and switch TTS voice to matching language."""
        if lang in ["de", "en"]:
            self.ui_language = lang
            # Update global locale for number formatting
            from ..lib.formatting import set_ui_locale
            set_ui_locale(lang)
            # Update prompt language for LLM responses
            set_language(lang)
            # Update research_mode_display to match new language
            self.research_mode_display = TranslationManager.get_research_mode_display(  # type: ignore[attr-defined, has-type]
                self.research_mode, lang  # type: ignore[attr-defined, has-type, arg-type]
            )
            self.add_debug(f"\U0001f310 UI Language changed to: {lang}")  # type: ignore[attr-defined, has-type]

            # Auto-switch TTS voice to matching language
            self._switch_tts_voice_for_language(lang)  # type: ignore[attr-defined, has-type]

            # Save to settings
            self._save_settings()
        else:
            self.add_debug(f"\u274c Invalid language: {lang}. Use 'de' or 'en'")  # type: ignore[attr-defined, has-type]

    # ================================================================
    # USER PROFILE
    # ================================================================

    def set_user_name(self, name: str) -> None:
        """Set user name (called on every keystroke)."""
        self.user_name = name

    def save_user_name(self, name: str) -> None:
        """Save user name when input loses focus."""
        self.user_name = name.strip()
        # Sync to prompt_loader for automatic injection into system prompts
        from ..lib.prompt_loader import set_user_name
        set_user_name(self.user_name)
        if self.user_name:
            self.add_debug(f"\U0001f464 User name: {self.user_name}")  # type: ignore[attr-defined, has-type]
        self._save_settings()

    def set_user_gender(self, gender: str | list[str]) -> None:
        """Set user gender for salutation (male/female)."""
        # Reflex segmented_control can return str or list[str]
        if isinstance(gender, list):
            gender = gender[0] if gender else "male"
        self.user_gender = gender
        from ..lib.prompt_loader import set_user_gender
        set_user_gender(gender)
        self.add_debug(f"\U0001f464 Gender: {'\u2642 male' if gender == 'male' else '\u2640 female'}")  # type: ignore[attr-defined, has-type]
        self._save_settings()

    # ================================================================
    # RESET TO DEFAULTS
    # ================================================================

    async def load_default_settings(self):
        """Load default settings from config.py and apply them to state."""
        from ..lib.settings import reset_to_defaults

        self.add_debug("\U0001f4be Loading default settings from config.py...")  # type: ignore[attr-defined, has-type]
        yield  # Update UI immediately

        if reset_to_defaults():
            self.add_debug("\u2705 Default settings saved to file")  # type: ignore[attr-defined, has-type]
            yield

            # Reload settings from file (all values MUST be present after reset_to_defaults())
            saved_settings = load_settings()
            if saved_settings:
                # Update state with loaded settings (only attributes that exist in state)
                # No fallbacks needed - reset_to_defaults() ensures all values are present
                self.backend_type = saved_settings["backend_type"]  # type: ignore[attr-defined, has-type]
                self.backend_id = self.backend_type  # type: ignore[attr-defined, has-type]
                self.current_backend_label = self.available_backends_dict.get(  # type: ignore[attr-defined, has-type]
                    self.backend_id, self.backend_id  # type: ignore[attr-defined, has-type]
                )
                self.research_mode = saved_settings["research_mode"]  # type: ignore[attr-defined, has-type]

                # Update research_mode_display to match loaded research_mode
                self.research_mode_display = TranslationManager.get_research_mode_display(  # type: ignore[attr-defined, has-type]
                    self.research_mode, self.ui_language  # type: ignore[attr-defined, has-type]
                )

                self.temperature = saved_settings["temperature"]  # type: ignore[attr-defined, has-type]
                self.temperature_mode = saved_settings["temperature_mode"]  # type: ignore[attr-defined, has-type]
                self.enable_tts = saved_settings["enable_tts"]  # type: ignore[attr-defined, has-type]
                self.enable_yarn = saved_settings["enable_yarn"]  # type: ignore[attr-defined, has-type]
                self.yarn_factor = saved_settings["yarn_factor"]  # type: ignore[attr-defined, has-type]

                # IMPORTANT: Set model names from defaults (prevents fallback to available_models[0])
                # The "model" and "automatik_model" keys come from get_default_settings()
                self.aifred_model = saved_settings.get("model", self.aifred_model)  # type: ignore[attr-defined, has-type]
                self.automatik_model = saved_settings.get("automatik_model", self.automatik_model)  # type: ignore[attr-defined, has-type]

                self.add_debug("\U0001f504 Settings reloaded from file")  # type: ignore[attr-defined, has-type]
                yield

                # Reinitialize backend with new settings
                await self.initialize_backend()  # type: ignore[attr-defined, has-type]
                self.add_debug("\u2705 All settings applied successfully")  # type: ignore[attr-defined, has-type]
                yield
            else:
                self.add_debug("\u26a0\ufe0f Failed to reload settings from file")  # type: ignore[attr-defined, has-type]
                yield
        else:
            self.add_debug("\u274c Failed to load default settings")  # type: ignore[attr-defined, has-type]
            yield  # Update UI even on error

    # ================================================================
    # TRANSLATION HELPER
    # ================================================================

    def get_text(self, key: str) -> str:
        """Get translated text based on current UI language."""
        return TranslationManager.get_text(key, self.ui_language)
