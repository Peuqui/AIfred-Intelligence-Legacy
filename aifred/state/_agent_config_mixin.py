"""Agent configuration mixin for AIfred state.

Handles per-agent personality, reasoning, thinking mode,
sampling parameters, speed mode, RoPE factors, multi-agent mode settings,
temperature configuration, and model selection for Sokrates/Salomo.
"""

from __future__ import annotations

from typing import List

import reflex as rx

from ..lib.config import (
    DEFAULT_MIN_P,
    DEFAULT_REPEAT_PENALTY,
    DEFAULT_TOP_K,
    DEFAULT_TOP_P,
    LLAMASERVER_DEFAULT_MIN_P,
    LLAMASERVER_DEFAULT_REPEAT_PENALTY,
    LLAMASERVER_DEFAULT_TEMPERATURE,
    LLAMASERVER_DEFAULT_TOP_K,
    LLAMASERVER_DEFAULT_TOP_P,
    SOKRATES_TEMPERATURE_OFFSET,
    SALOMO_TEMPERATURE_OFFSET,
    VISION_DEFAULT_TEMPERATURE,
    VISION_DEFAULT_TOP_K,
    VISION_DEFAULT_TOP_P,
    VISION_DEFAULT_MIN_P,
    VISION_DEFAULT_REPEAT_PENALTY,
)

# Agent names used throughout this mixin
_AGENTS = ("aifred", "sokrates", "salomo", "vision")

# Feature -> (emoji, prompt_loader setter name)
# Note: thinking has no prompt_loader sync — read directly from State at runtime.
_FEATURE_META: dict[str, tuple[str, str]] = {
    "personality": ("", "set_personality_enabled"),
    "reasoning": ("", "set_reasoning_enabled"),
    "thinking": ("", ""),
}

# Per-agent emoji for personality toggles
_PERSONALITY_EMOJI: dict[str, str] = {
    "aifred": "\U0001f3a9",      # top hat
    "sokrates": "\U0001f3db\ufe0f",  # classical building
    "salomo": "\U0001f451",      # crown
    "vision": "\U0001f4f7",      # camera
}

# Per-feature emoji (same for all agents)
_FEATURE_EMOJI: dict[str, str] = {
    "personality": "",   # filled per-agent from _PERSONALITY_EMOJI
    "reasoning": "\U0001f4ad",   # thought balloon
    "thinking": "\U0001f9e0",    # brain
}


class AgentConfigMixin(rx.State, mixin=True):
    """Mixin for per-agent configuration and sampling parameters."""

    # ── Per-Agent Personality Toggles ─────────────────────────────
    aifred_personality: bool = True
    sokrates_personality: bool = True
    salomo_personality: bool = True
    vision_personality: bool = True

    # ── Per-Agent Reasoning Toggles ───────────────────────────────
    aifred_reasoning: bool = True
    sokrates_reasoning: bool = True
    salomo_reasoning: bool = True
    vision_reasoning: bool = False

    # ── Per-Agent Thinking Toggles (enable_thinking to backend) ───
    aifred_thinking: bool = True
    sokrates_thinking: bool = True
    salomo_thinking: bool = True
    vision_thinking: bool = True

    # ── Per-Agent Sampling Parameters ─────────────────────────────
    aifred_top_k: int = DEFAULT_TOP_K
    aifred_top_p: float = DEFAULT_TOP_P
    aifred_min_p: float = DEFAULT_MIN_P
    aifred_repeat_penalty: float = DEFAULT_REPEAT_PENALTY
    sokrates_top_k: int = DEFAULT_TOP_K
    sokrates_top_p: float = DEFAULT_TOP_P
    sokrates_min_p: float = DEFAULT_MIN_P
    sokrates_repeat_penalty: float = DEFAULT_REPEAT_PENALTY
    salomo_top_k: int = DEFAULT_TOP_K
    salomo_top_p: float = DEFAULT_TOP_P
    salomo_min_p: float = DEFAULT_MIN_P
    salomo_repeat_penalty: float = DEFAULT_REPEAT_PENALTY
    vision_top_k: int = VISION_DEFAULT_TOP_K
    vision_top_p: float = VISION_DEFAULT_TOP_P
    vision_min_p: float = VISION_DEFAULT_MIN_P
    vision_repeat_penalty: float = VISION_DEFAULT_REPEAT_PENALTY
    sampling_reset_key: int = 0  # UI key counter to force re-mount on reset

    # ── Per-Agent Speed Mode (llamacpp only) ──────────────────────
    aifred_speed_mode: bool = False
    sokrates_speed_mode: bool = False
    salomo_speed_mode: bool = False
    vision_speed_mode: bool = False
    aifred_has_speed_variant: bool = False
    sokrates_has_speed_variant: bool = False
    salomo_has_speed_variant: bool = False
    vision_has_speed_variant: bool = False

    # ── Per-Agent RoPE Scaling Factors ────────────────────────────
    aifred_rope_factor: float = 1.0
    automatik_rope_factor: float = 1.0
    sokrates_rope_factor: float = 1.0
    salomo_rope_factor: float = 1.0
    vision_rope_factor: float = 1.0

    # ── Per-Agent Model Metadata ──────────────────────────────────
    aifred_max_context: int = 0
    aifred_is_hybrid: bool = False
    aifred_supports_thinking: bool | None = None
    sokrates_max_context: int = 0
    sokrates_is_hybrid: bool = False
    sokrates_supports_thinking: bool | None = None
    salomo_max_context: int = 0
    salomo_is_hybrid: bool = False
    salomo_supports_thinking: bool | None = None
    vision_max_context: int = 0
    vision_is_hybrid: bool = False
    vision_supports_thinking: bool | None = None

    # ── Temperature Settings ──────────────────────────────────────
    sokrates_temperature: float = 0.5
    sokrates_temperature_offset: float = SOKRATES_TEMPERATURE_OFFSET
    salomo_temperature: float = 0.5
    salomo_temperature_offset: float = SALOMO_TEMPERATURE_OFFSET
    vision_temperature: float = VISION_DEFAULT_TEMPERATURE

    # ── Multi-Agent Settings (PERSISTENT) ─────────────────────────
    multi_agent_mode: str = "standard"
    max_debate_rounds: int = 3
    consensus_type: str = "majority"
    sokrates_model: str = ""
    sokrates_model_id: str = ""
    salomo_model: str = ""
    salomo_model_id: str = ""

    # ── Multi-Agent Runtime State ─────────────────────────────────
    sokrates_critique: str = ""
    sokrates_pro_args: str = ""
    sokrates_contra_args: str = ""
    show_sokrates_panel: bool = False
    salomo_synthesis: str = ""
    show_salomo_panel: bool = False
    debate_round: int = 0
    debate_user_interjection: str = ""
    debate_in_progress: bool = False

    # ================================================================
    # GENERIC HELPERS (deduplicated triple-agent pattern)
    # ================================================================

    def _toggle_agent_feature(self, agent: str, feature: str) -> None:
        """Toggle a boolean per-agent feature and persist + sync to prompt_loader.

        Works for personality, reasoning, and thinking.
        """
        attr = f"{agent}_{feature}"
        new_val = not getattr(self, attr)
        setattr(self, attr, new_val)

        # Emoji for debug message
        if feature == "personality":
            emoji = _PERSONALITY_EMOJI[agent]
        else:
            emoji = _FEATURE_EMOJI[feature]

        status = "ON" if new_val else "OFF"
        self.add_debug(f"{emoji} {agent.capitalize()} {feature}: {status}")  # type: ignore[attr-defined]

        # Save all three values for this feature at once
        save_method = f"_save_{feature}_settings"
        getattr(self, save_method)()

        # Sync to prompt_loader (if setter exists — thinking has none)
        setter_name = _FEATURE_META[feature][1]
        if setter_name:
            from ..lib import prompt_loader
            getattr(prompt_loader, setter_name)(agent, new_val)

    # ── Personality Toggles ───────────────────────────────────────

    def toggle_aifred_personality(self, _value: bool | None = None) -> None:
        """Toggle AIfred Butler personality style on/off."""
        self._toggle_agent_feature("aifred", "personality")

    def toggle_sokrates_personality(self, _value: bool | None = None) -> None:
        """Toggle Sokrates philosophical personality style on/off."""
        self._toggle_agent_feature("sokrates", "personality")

    def toggle_salomo_personality(self, _value: bool | None = None) -> None:
        """Toggle Salomo judge personality style on/off."""
        self._toggle_agent_feature("salomo", "personality")

    def toggle_vision_personality(self, _value: bool | None = None) -> None:
        """Toggle Vision agent personality style on/off."""
        self._toggle_agent_feature("vision", "personality")

    def _save_personality_settings(self) -> None:
        """Save personality toggle states to settings.json."""
        from ..lib.settings import load_settings, save_settings
        settings = load_settings() or {}
        settings["aifred_personality"] = self.aifred_personality
        settings["sokrates_personality"] = self.sokrates_personality
        settings["salomo_personality"] = self.salomo_personality
        settings["vision_personality"] = self.vision_personality
        save_settings(settings)

    # ── Reasoning Toggles ─────────────────────────────────────────

    def toggle_aifred_reasoning(self, _value: bool | None = None) -> None:
        """Toggle AIfred chain-of-thought reasoning on/off."""
        self._toggle_agent_feature("aifred", "reasoning")

    def toggle_sokrates_reasoning(self, _value: bool | None = None) -> None:
        """Toggle Sokrates chain-of-thought reasoning on/off."""
        self._toggle_agent_feature("sokrates", "reasoning")

    def toggle_salomo_reasoning(self, _value: bool | None = None) -> None:
        """Toggle Salomo chain-of-thought reasoning on/off."""
        self._toggle_agent_feature("salomo", "reasoning")

    def toggle_vision_reasoning(self, _value: bool | None = None) -> None:
        """Toggle Vision agent chain-of-thought reasoning on/off."""
        self._toggle_agent_feature("vision", "reasoning")

    def _save_reasoning_settings(self) -> None:
        """Save reasoning toggle states to settings.json."""
        from ..lib.settings import load_settings, save_settings
        settings = load_settings() or {}
        settings["aifred_reasoning"] = self.aifred_reasoning
        settings["sokrates_reasoning"] = self.sokrates_reasoning
        settings["salomo_reasoning"] = self.salomo_reasoning
        settings["vision_reasoning"] = self.vision_reasoning
        save_settings(settings)

    # ── Thinking Toggles ──────────────────────────────────────────

    def toggle_aifred_thinking(self, _value: bool | None = None) -> None:
        """Toggle AIfred model thinking (enable_thinking to backend) on/off."""
        self._toggle_agent_feature("aifred", "thinking")

    def toggle_sokrates_thinking(self, _value: bool | None = None) -> None:
        """Toggle Sokrates model thinking on/off."""
        self._toggle_agent_feature("sokrates", "thinking")

    def toggle_salomo_thinking(self, _value: bool | None = None) -> None:
        """Toggle Salomo model thinking on/off."""
        self._toggle_agent_feature("salomo", "thinking")

    def toggle_vision_thinking(self, _value: bool | None = None) -> None:
        """Toggle Vision agent model thinking on/off."""
        self._toggle_agent_feature("vision", "thinking")

    def _save_thinking_settings(self) -> None:
        """Save thinking toggle states to settings.json."""
        from ..lib.settings import load_settings, save_settings
        settings = load_settings() or {}
        settings["aifred_thinking"] = self.aifred_thinking
        settings["sokrates_thinking"] = self.sokrates_thinking
        settings["salomo_thinking"] = self.salomo_thinking
        settings["vision_thinking"] = self.vision_thinking
        save_settings(settings)

    # ================================================================
    # SAMPLING PARAMETERS
    # ================================================================

    def set_aifred_sampling(self, param: str, value: str) -> None:
        """Set AIfred sampling parameter from UI input."""
        self._set_agent_sampling("aifred", param, value)

    def set_sokrates_sampling(self, param: str, value: str) -> None:
        """Set Sokrates sampling parameter from UI input."""
        self._set_agent_sampling("sokrates", param, value)

    def set_salomo_sampling(self, param: str, value: str) -> None:
        """Set Salomo sampling parameter from UI input."""
        self._set_agent_sampling("salomo", param, value)

    def set_vision_sampling(self, param: str, value: str) -> None:
        """Set Vision sampling parameter from UI input."""
        self._set_agent_sampling("vision", param, value)

    def _set_agent_sampling(self, agent: str, param: str, value: str) -> None:
        """Set a sampling parameter for an agent and save to settings."""
        try:
            if param == "top_k":
                int_val = int(float(value))
                setattr(self, f"{agent}_top_k", max(0, min(200, int_val)))
            elif param == "top_p":
                float_val = float(value)
                setattr(self, f"{agent}_top_p", max(0.0, min(1.0, float_val)))
            elif param == "min_p":
                float_val = float(value)
                setattr(self, f"{agent}_min_p", max(0.0, min(1.0, float_val)))
            elif param == "repeat_penalty":
                float_val = float(value)
                setattr(self, f"{agent}_repeat_penalty", max(1.0, min(2.0, float_val)))
            final_val = getattr(self, f"{agent}_{param}")
            self.add_debug(f"\U0001f3b2 {agent.capitalize()} {param}={final_val}")  # type: ignore[attr-defined]
            self._save_settings()  # type: ignore[attr-defined]
        except (ValueError, TypeError):
            pass

    def reset_aifred_sampling(self) -> None:
        """Reset AIfred sampling to model defaults."""
        self._reset_agent_sampling("aifred")

    def reset_sokrates_sampling(self) -> None:
        """Reset Sokrates sampling to model defaults."""
        self._reset_agent_sampling("sokrates")

    def reset_salomo_sampling(self) -> None:
        """Reset Salomo sampling to model defaults."""
        self._reset_agent_sampling("salomo")

    def reset_vision_sampling(self) -> None:
        """Reset Vision sampling to vision-specific defaults."""
        self._reset_agent_sampling("vision")

    def _reset_agent_sampling(self, agent: str, include_temperature: bool = True) -> None:
        """Reset sampling parameters for an agent to model/backend defaults.

        Args:
            agent: "aifred", "sokrates", "salomo", or "vision"
            include_temperature: If True, reset temperature too (model change / reset button).
                If False, keep current temperature (app restart -- temperature is persisted).
        """
        if agent == "vision":
            defaults: dict[str, float] = {
                "temperature": VISION_DEFAULT_TEMPERATURE,
                "top_k": VISION_DEFAULT_TOP_K,
                "top_p": VISION_DEFAULT_TOP_P,
                "min_p": VISION_DEFAULT_MIN_P,
                "repeat_penalty": VISION_DEFAULT_REPEAT_PENALTY,
            }
        else:
            defaults = {
                "temperature": LLAMASERVER_DEFAULT_TEMPERATURE,
                "top_k": DEFAULT_TOP_K,
                "top_p": DEFAULT_TOP_P,
                "min_p": DEFAULT_MIN_P,
                "repeat_penalty": DEFAULT_REPEAT_PENALTY,
            }

        if self.backend_type == "llamacpp":  # type: ignore[attr-defined]
            # Try to get model-specific values from llama-swap YAML
            # Sokrates/Salomo with empty model_id inherit from AIfred
            model_id = getattr(self, f"{agent}_model_id", "") or self.aifred_model_id  # type: ignore[attr-defined]
            if model_id:
                from ..lib.llamacpp_calibration import parse_llamaswap_config, parse_sampling_from_cmd
                from ..lib.config import LLAMASWAP_CONFIG_PATH
                config = parse_llamaswap_config(LLAMASWAP_CONFIG_PATH)
                if model_id in config:
                    yaml_sampling = parse_sampling_from_cmd(config[model_id]["full_cmd"])
                    defaults = {
                        "temperature": yaml_sampling.get("temperature", LLAMASERVER_DEFAULT_TEMPERATURE),
                        "top_k": yaml_sampling.get("top_k", LLAMASERVER_DEFAULT_TOP_K),
                        "top_p": yaml_sampling.get("top_p", LLAMASERVER_DEFAULT_TOP_P),
                        "min_p": yaml_sampling.get("min_p", LLAMASERVER_DEFAULT_MIN_P),
                        "repeat_penalty": yaml_sampling.get("repeat_penalty", LLAMASERVER_DEFAULT_REPEAT_PENALTY),
                    }

        if include_temperature:
            if agent == "aifred":
                self.temperature = defaults["temperature"]  # type: ignore[attr-defined]
            else:
                setattr(self, f"{agent}_temperature", defaults["temperature"])
        setattr(self, f"{agent}_top_k", int(defaults["top_k"]))
        setattr(self, f"{agent}_top_p", defaults["top_p"])
        setattr(self, f"{agent}_min_p", defaults["min_p"])
        setattr(self, f"{agent}_repeat_penalty", defaults["repeat_penalty"])

        # Debug log
        temp_info = f"temp={defaults['temperature']}, " if include_temperature else ""
        self.add_debug(  # type: ignore[attr-defined]
            f"\U0001f3b2 {agent.capitalize()} sampling reset: "
            f"{temp_info}top_k={int(defaults['top_k'])}, "
            f"top_p={defaults['top_p']}, min_p={defaults['min_p']}, "
            f"rep={defaults['repeat_penalty']}"
        )

        # Increment key to force UI re-mount of input fields
        self.sampling_reset_key += 1

    # ================================================================
    # SPEED MODE — SINGLE SOURCE OF TRUTH
    # ================================================================

    def _effective_model_id(self, agent: str) -> str:
        """Return model ID with -speed suffix when speed mode is active.

        This is the SINGLE SOURCE OF TRUTH for speed-suffix resolution.
        The *_model_id state vars always contain the base ID.
        All code that sends model IDs to the backend must use this method.
        """
        base_id: str = getattr(self, f"{agent}_model_id")
        speed_on: bool = getattr(self, f"{agent}_speed_mode")
        has_speed: bool = getattr(self, f"{agent}_has_speed_variant")
        if speed_on and has_speed and base_id:
            return f"{base_id}-speed"
        return base_id

    # ================================================================
    # SPEED MODE TOGGLES (llamacpp only)
    # ================================================================

    def toggle_aifred_speed_mode(self, _value: bool | None = None) -> None:
        """Toggle AIfred between speed variant (aggressive split, 32K ctx) and context variant."""
        self.aifred_speed_mode = not self.aifred_speed_mode
        self.add_debug(f"\U0001f500 AIfred mode: {self._speed_mode_debug_str(self.aifred_speed_mode, self.aifred_model_id, self.aifred_max_context)}")  # type: ignore[attr-defined]
        self._save_settings()  # type: ignore[attr-defined]

    def toggle_sokrates_speed_mode(self, _value: bool | None = None) -> None:
        """Toggle Sokrates between speed variant and context variant."""
        self.sokrates_speed_mode = not self.sokrates_speed_mode
        base_id = self.sokrates_model_id or self.aifred_model_id  # type: ignore[attr-defined]
        self.add_debug(f"\U0001f500 Sokrates mode: {self._speed_mode_debug_str(self.sokrates_speed_mode, base_id, self.sokrates_max_context)}")  # type: ignore[attr-defined]
        self._save_settings()  # type: ignore[attr-defined]

    def toggle_salomo_speed_mode(self, _value: bool | None = None) -> None:
        """Toggle Salomo between speed variant and context variant."""
        self.salomo_speed_mode = not self.salomo_speed_mode
        base_id = self.salomo_model_id or self.aifred_model_id  # type: ignore[attr-defined]
        self.add_debug(f"\U0001f500 Salomo mode: {self._speed_mode_debug_str(self.salomo_speed_mode, base_id, self.salomo_max_context)}")  # type: ignore[attr-defined]
        self._save_settings()  # type: ignore[attr-defined]

    def toggle_vision_speed_mode(self, _value: bool | None = None) -> None:
        """Toggle Vision between speed variant and context variant."""
        self.vision_speed_mode = not self.vision_speed_mode
        base_id = self.vision_model_id  # type: ignore[attr-defined]
        # Vision has no max_context state var — pass 0 (debug str reads from cache)
        self.add_debug(f"\U0001f500 Vision mode: {self._speed_mode_debug_str(self.vision_speed_mode, base_id, 0)}")  # type: ignore[attr-defined]
        self._save_settings()  # type: ignore[attr-defined]

    def _speed_mode_debug_str(self, speed_on: bool, base_model_id: str, max_ctx: int) -> str:
        """Build debug string for speed mode toggle showing tensor-split and context."""
        from ..lib.model_vram_cache import get_llamacpp_speed_split
        from ..lib.formatting import format_number
        from ..lib.config import MIN_USEFUL_CONTEXT_TOKENS
        if speed_on:
            cuda0, rest, speed_ctx = get_llamacpp_speed_split(base_model_id)
            split_str = f" ({cuda0}:{rest} tensor-split)" if cuda0 > 0 else ""
            ctx = format_number(speed_ctx if speed_ctx > 0 else MIN_USEFUL_CONTEXT_TOKENS)
            return f"\u26a1 speed \u2014 {ctx} tok{split_str}"
        else:
            ctx = format_number(max_ctx) if max_ctx else "n/a"
            return f"\U0001f4d6 context \u2014 {ctx} tok"

    # ================================================================
    # ROPE FACTOR SETTERS
    # ================================================================

    def set_aifred_rope_factor(self, value: str) -> None:
        """Set RoPE scaling factor for AIfred-LLM."""
        # Convert UI string to float
        factor = float(value.replace("x", ""))
        self.aifred_rope_factor = factor
        self.add_debug(f"\U0001f39a\ufe0f AIfred RoPE Factor: {value}")  # type: ignore[attr-defined]

        # Save to VRAM cache (per-model setting)
        if self.aifred_model_id:  # type: ignore[attr-defined]
            from ..lib.model_vram_cache import set_rope_factor_for_model, get_ollama_calibrated_max_context, get_rope_factor_for_model, get_llamacpp_calibration
            from ..lib.formatting import format_number
            set_rope_factor_for_model(self.aifred_model_id, factor)  # type: ignore[attr-defined]

            # Helper for context limit display (merge GB and ctx into one bracket)
            def format_model_with_ctx(model_display: str, model_id: str) -> str:
                if not model_id:
                    return model_display
                # Backend-aware calibration lookup
                if self.backend_type == "llamacpp":  # type: ignore[attr-defined]
                    ctx = get_llamacpp_calibration(model_id)
                else:
                    ctx = get_ollama_calibrated_max_context(model_id, get_rope_factor_for_model(model_id))
                if ctx:
                    if model_display.endswith(")"):
                        return model_display[:-1] + f", {format_number(ctx)} ctx)"
                    return f"{model_display} ({format_number(ctx)} ctx)"
                else:
                    if model_display.endswith(")"):
                        return model_display[:-1] + ", ctx not calibrated)"
                    return f"{model_display} (ctx not calibrated)"

            # Re-display all agent models with updated context limits
            self.add_debug(f"   AIfred: {format_model_with_ctx(self.aifred_model, self.aifred_model_id)}")  # type: ignore[attr-defined]
            if self.multi_agent_mode != "standard":
                if self.sokrates_model_id:
                    self.add_debug(f"   Sokrates: {format_model_with_ctx(self.sokrates_model, self.sokrates_model_id)}")  # type: ignore[attr-defined]
                if self.salomo_model_id:
                    self.add_debug(f"   Salomo: {format_model_with_ctx(self.salomo_model, self.salomo_model_id)}")  # type: ignore[attr-defined]

            # Update cached min context limit
            context_limits: list[int] = []
            for model_id in [self.aifred_model_id, self.sokrates_model_id, self.salomo_model_id]:  # type: ignore[attr-defined]
                if model_id:
                    if self.backend_type == "llamacpp":  # type: ignore[attr-defined]
                        ctx = get_llamacpp_calibration(model_id)
                    else:
                        ctx = get_ollama_calibrated_max_context(model_id, get_rope_factor_for_model(model_id))
                    if ctx:
                        context_limits.append(ctx)
            self._min_agent_context_limit = min(context_limits) if context_limits else 0  # type: ignore[attr-defined]

            # Show history utilization and warn if compression will trigger
            self._log_history_utilization(self._min_agent_context_limit)  # type: ignore[attr-defined]

            # Warn if no calibration exists for this mode
            if factor >= 2.0:
                extended_ctx = get_ollama_calibrated_max_context(self.aifred_model_id, rope_factor=2.0)  # type: ignore[attr-defined]
                if extended_ctx is None:
                    self.add_debug("\u26a0\ufe0f No RoPE 2x calibration found - please calibrate first!")  # type: ignore[attr-defined]
            else:
                native_ctx = get_ollama_calibrated_max_context(self.aifred_model_id, rope_factor=1.0)  # type: ignore[attr-defined]
                if native_ctx is None:
                    self.add_debug("\u26a0\ufe0f No native calibration found - please calibrate first!")  # type: ignore[attr-defined]

    def set_automatik_rope_factor(self, value: str) -> None:
        """Set RoPE scaling factor for Automatik-LLM."""
        factor = float(value.replace("x", ""))
        self.automatik_rope_factor = factor
        effective_auto = self._effective_automatik_id  # type: ignore[attr-defined]
        if effective_auto:
            from ..lib.model_vram_cache import set_rope_factor_for_model
            set_rope_factor_for_model(effective_auto, factor)

    def _set_secondary_agent_rope_factor(self, agent: str, value: str) -> None:
        """Set RoPE factor for Sokrates or Salomo."""
        factor = float(value.replace("x", ""))
        setattr(self, f"{agent}_rope_factor", factor)
        model_id = getattr(self, f"{agent}_model_id")
        if model_id:
            from ..lib.model_vram_cache import set_rope_factor_for_model
            set_rope_factor_for_model(model_id, factor)

    def set_sokrates_rope_factor(self, value: str) -> None:
        """Set RoPE scaling factor for Sokrates-LLM."""
        self._set_secondary_agent_rope_factor("sokrates", value)

    def set_salomo_rope_factor(self, value: str) -> None:
        """Set RoPE scaling factor for Salomo-LLM."""
        self._set_secondary_agent_rope_factor("salomo", value)

    def set_vision_rope_factor(self, value: str) -> None:
        """Set RoPE scaling factor for Vision-LLM."""
        factor = float(value.replace("x", ""))
        self.vision_rope_factor = factor
        if self.vision_model_id:  # type: ignore[attr-defined]
            from ..lib.model_vram_cache import set_rope_factor_for_model
            set_rope_factor_for_model(self.vision_model_id, factor)  # type: ignore[attr-defined]

    # ================================================================
    # ROPE FACTOR DISPLAY (computed vars)
    # ================================================================

    @rx.var
    def rope_factor_display(self) -> str:
        """Display value for AIfred RoPE factor select (e.g., '1.0x', '2.0x')."""
        return f"{self.aifred_rope_factor}x"

    @rx.var
    def automatik_rope_display(self) -> str:
        """Display value for Automatik RoPE factor select."""
        return f"{self.automatik_rope_factor}x"

    @rx.var
    def sokrates_rope_display(self) -> str:
        """Display value for Sokrates RoPE factor select."""
        return f"{self.sokrates_rope_factor}x"

    @rx.var
    def salomo_rope_display(self) -> str:
        """Display value for Salomo RoPE factor select."""
        return f"{self.salomo_rope_factor}x"

    @rx.var
    def vision_rope_display(self) -> str:
        """Display value for Vision RoPE factor select."""
        return f"{self.vision_rope_factor}x"

    # ================================================================
    # TEMPERATURE SETTINGS
    # ================================================================

    def set_sokrates_temperature(self, temp: list[float]) -> None:
        """Set Sokrates temperature (from slider which returns list[float])."""
        self.sokrates_temperature = temp[0] if isinstance(temp, list) else temp
        self._save_settings()  # type: ignore[attr-defined]

    def set_sokrates_temperature_offset(self, offset: list[float]) -> None:
        """Set Sokrates temperature offset for Auto mode (from slider which returns list[float])."""
        self.sokrates_temperature_offset = offset[0] if isinstance(offset, list) else offset
        self._save_settings()  # type: ignore[attr-defined]
        self.add_debug(f"\U0001f321\ufe0f Sokrates Offset: +{self.sokrates_temperature_offset:.1f}")  # type: ignore[attr-defined]

    def set_salomo_temperature(self, temp: list[float]) -> None:
        """Set Salomo temperature for Manual mode (from slider which returns list[float])."""
        self.salomo_temperature = temp[0] if isinstance(temp, list) else temp
        self._save_settings()  # type: ignore[attr-defined]

    def set_salomo_temperature_offset(self, offset: list[float]) -> None:
        """Set Salomo temperature offset for Auto mode (from slider which returns list[float])."""
        self.salomo_temperature_offset = offset[0] if isinstance(offset, list) else offset
        self._save_settings()  # type: ignore[attr-defined]
        self.add_debug(f"\U0001f321\ufe0f Salomo Offset: +{self.salomo_temperature_offset:.1f}")  # type: ignore[attr-defined]

    def set_aifred_temperature_input(self, value: str) -> None:
        """Set AIfred temperature from text input field."""
        try:
            self.temperature = max(0.0, min(2.0, float(value)))  # type: ignore[attr-defined]
            self.add_debug(f"\U0001f321\ufe0f AIfred temperature={self.temperature}")  # type: ignore[attr-defined]
            self._save_settings()  # type: ignore[attr-defined]
        except (ValueError, TypeError):
            pass

    def set_sokrates_temperature_input(self, value: str) -> None:
        """Set Sokrates temperature from text input field."""
        try:
            self.sokrates_temperature = max(0.0, min(2.0, float(value)))
            self.add_debug(f"\U0001f321\ufe0f Sokrates temperature={self.sokrates_temperature}")  # type: ignore[attr-defined]
            self._save_settings()  # type: ignore[attr-defined]
        except (ValueError, TypeError):
            pass

    def set_salomo_temperature_input(self, value: str) -> None:
        """Set Salomo temperature from text input field."""
        try:
            self.salomo_temperature = max(0.0, min(2.0, float(value)))
            self.add_debug(f"\U0001f321\ufe0f Salomo temperature={self.salomo_temperature}")  # type: ignore[attr-defined]
            self._save_settings()  # type: ignore[attr-defined]
        except (ValueError, TypeError):
            pass

    def set_vision_temperature_input(self, value: str) -> None:
        """Set Vision temperature from text input field."""
        try:
            self.vision_temperature = max(0.0, min(2.0, float(value)))
            self.add_debug(f"\U0001f321\ufe0f Vision temperature={self.vision_temperature}")  # type: ignore[attr-defined]
            self._save_settings()  # type: ignore[attr-defined]
        except (ValueError, TypeError):
            pass

    # ================================================================
    # MULTI-AGENT MODE SETTINGS
    # ================================================================

    def set_multi_agent_mode(self, mode: str) -> None:
        """Set multi-agent discussion mode."""
        self.multi_agent_mode = mode
        # Reset Sokrates panel when switching modes
        self.show_sokrates_panel = False
        self.sokrates_critique = ""
        self.sokrates_pro_args = ""
        self.sokrates_contra_args = ""
        self.debate_round = 0
        self._save_settings()  # type: ignore[attr-defined]

        mode_labels = {
            "standard": "Standard",
            "critical_review": "Critical Review",
            "auto_consensus": "Auto-Consensus",
            "tribunal": "Tribunal",
        }
        self.add_debug(f"\U0001f916 Discussion mode: {mode_labels.get(mode, mode)}")  # type: ignore[attr-defined]

    def set_max_debate_rounds(self, value: list[float]) -> None:
        """Set maximum debate rounds (from slider)."""
        self.max_debate_rounds = int(value[0])
        self._save_settings()  # type: ignore[attr-defined]
        self.add_debug(f"\U0001f504 Max debate rounds: {self.max_debate_rounds}")  # type: ignore[attr-defined]

    def increase_debate_rounds(self) -> None:
        """Increase max debate rounds by 1 (max 10)."""
        if self.max_debate_rounds < 10:
            self.max_debate_rounds += 1
            self._save_settings()  # type: ignore[attr-defined]
            self.add_debug(f"\U0001f504 Max debate rounds: {self.max_debate_rounds}")  # type: ignore[attr-defined]

    def decrease_debate_rounds(self) -> None:
        """Decrease max debate rounds by 1 (min 1)."""
        if self.max_debate_rounds > 1:
            self.max_debate_rounds -= 1
            self._save_settings()  # type: ignore[attr-defined]
            self.add_debug(f"\U0001f504 Max debate rounds: {self.max_debate_rounds}")  # type: ignore[attr-defined]

    def set_consensus_type(self, consensus_type: str | list[str]) -> None:
        """Set consensus type for auto_consensus mode ('majority' or 'unanimous')."""
        # Handle both str and list[str] from segmented_control
        if isinstance(consensus_type, list):
            consensus_type = consensus_type[0] if consensus_type else "majority"
        self.consensus_type = consensus_type
        self._save_settings()  # type: ignore[attr-defined]
        type_label = "2/3 majority" if consensus_type == "majority" else "3/3 unanimous"
        self.add_debug(f"\U0001f5f3\ufe0f Consensus type: {type_label}")  # type: ignore[attr-defined]

    def toggle_consensus_type(self, checked: bool) -> None:
        """Toggle consensus type between majority (off) and unanimous (on)."""
        self.consensus_type = "unanimous" if checked else "majority"
        self._save_settings()  # type: ignore[attr-defined]
        type_label = "3/3 unanimous" if checked else "2/3 majority"
        self.add_debug(f"\U0001f5f3\ufe0f Consensus type: {type_label}")  # type: ignore[attr-defined]

    @rx.var
    def is_unanimous_consensus(self) -> bool:
        """Check if consensus type is unanimous (for toggle state)."""
        return self.consensus_type == "unanimous"

    @rx.var(deps=["consensus_type", "ui_language"], auto_deps=False)
    def consensus_toggle_tooltip(self) -> str:
        """Get tooltip text for consensus toggle based on current state and language."""
        from ..lib.i18n import t
        if self.consensus_type == "unanimous":
            return t("consensus_toggle_tooltip_on", lang=self.ui_language)  # type: ignore[attr-defined]
        return t("consensus_toggle_tooltip_off", lang=self.ui_language)  # type: ignore[attr-defined]

    @rx.var(deps=["ui_language"], auto_deps=False)
    def speed_switch_tooltip(self) -> str:
        """Localized tooltip for the Ctx/Speed switch."""
        from ..lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"  # type: ignore[attr-defined]
        return t("speed_switch_tooltip", lang=lang)

    @rx.var(deps=["ui_language"], auto_deps=False)
    def multi_agent_mode_options(self) -> List[List[str]]:
        """Get localized multi-agent mode options as [key, label] pairs for dropdown."""
        from ..lib import TranslationManager
        return [
            ["standard", TranslationManager.get_text("multi_agent_standard", self.ui_language)],  # type: ignore[attr-defined]
            ["critical_review", TranslationManager.get_text("multi_agent_critical_review", self.ui_language)],  # type: ignore[attr-defined]
            ["auto_consensus", TranslationManager.get_text("multi_agent_auto_consensus", self.ui_language)],  # type: ignore[attr-defined]
            ["tribunal", TranslationManager.get_text("multi_agent_tribunal", self.ui_language)],  # type: ignore[attr-defined]
        ]

    @rx.var(deps=["ui_language", "multi_agent_mode"], auto_deps=False)
    def multi_agent_mode_info(self) -> str:
        """Get localized description for the currently selected multi-agent mode."""
        from ..lib import TranslationManager
        info_key = f"multi_agent_info_{self.multi_agent_mode}"
        return TranslationManager.get_text(info_key, self.ui_language)  # type: ignore[attr-defined]

    # ================================================================
    # MULTI-AGENT RUNTIME STATE MANAGEMENT
    # ================================================================

    def queue_user_interjection(self, text: str) -> None:
        """Queue user input during active debate."""
        if self.debate_in_progress and text.strip():
            self.debate_user_interjection = text.strip()
            self.add_debug(f"\U0001f4ac User interjection queued: {text[:50]}...")  # type: ignore[attr-defined]

    def get_and_clear_user_interjection(self) -> str:
        """Get queued user interjection and clear it (called by orchestrator)."""
        interjection = self.debate_user_interjection
        self.debate_user_interjection = ""
        return interjection

    def reset_sokrates_state(self) -> None:
        """Reset all Sokrates-related runtime state."""
        self.sokrates_critique = ""
        self.sokrates_pro_args = ""
        self.sokrates_contra_args = ""
        self.show_sokrates_panel = False
        self.debate_round = 0
        self.debate_user_interjection = ""
        self.debate_in_progress = False

    def reset_salomo_state(self) -> None:
        """Reset all Salomo-related runtime state."""
        self.salomo_synthesis = ""
        self.show_salomo_panel = False

    def reset_multi_agent_state(self) -> None:
        """Reset all multi-agent runtime state (Sokrates + Salomo)."""
        self.reset_sokrates_state()
        self.reset_salomo_state()

    # ================================================================
    # SOKRATES / SALOMO MODEL SELECTION
    # ================================================================

    @rx.var
    def sokrates_model_label(self) -> str:
        """Get display label for Sokrates model."""
        if not self.sokrates_model_id:
            return ""  # Empty = use Main-LLM
        return self.available_models_dict.get(self.sokrates_model_id, self.sokrates_model_id)  # type: ignore[attr-defined, no-any-return]

    @rx.var(deps=["available_models", "ui_language"], auto_deps=False)
    def sokrates_available_models(self) -> list[str]:
        """Model list with localized '(wie AIfred-LLM)' as first selectable option."""
        from ..lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"  # type: ignore[attr-defined]
        return [t("sokrates_llm_same", lang=lang)] + list(self.available_models)  # type: ignore[attr-defined]

    @rx.var(deps=["available_models", "ui_language"], auto_deps=False)
    def salomo_available_models(self) -> list[str]:
        """Model list with localized '(wie AIfred-LLM)' as first selectable option."""
        from ..lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"  # type: ignore[attr-defined]
        return [t("sokrates_llm_same", lang=lang)] + list(self.available_models)  # type: ignore[attr-defined]

    @rx.var(deps=["sokrates_model", "ui_language"], auto_deps=False)
    def sokrates_model_select_value(self) -> str:
        """Maps empty string (auto) to the localized sentinel label for the select."""
        from ..lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"  # type: ignore[attr-defined]
        return t("sokrates_llm_same", lang=lang) if self.sokrates_model == "" else self.sokrates_model

    @rx.var(deps=["salomo_model", "ui_language"], auto_deps=False)
    def salomo_model_select_value(self) -> str:
        """Maps empty string (auto) to the localized sentinel label for the select."""
        from ..lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"  # type: ignore[attr-defined]
        return t("sokrates_llm_same", lang=lang) if self.salomo_model == "" else self.salomo_model

    def set_sokrates_model(self, model: str) -> None:
        """Set Sokrates LLM model for multi-agent debate."""
        from ..lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"  # type: ignore[attr-defined]
        if model == t("sokrates_llm_same", lang=lang):
            model = ""
        self.sokrates_model = model
        self.sokrates_model_id = self._resolve_model_id(model)  # type: ignore[attr-defined]

        if not self.sokrates_model_id:
            # "(wie AIfred-LLM)" selected -- clear speed variant
            self.sokrates_has_speed_variant = False
            self.sokrates_speed_mode = False

        # Load all model parameters from cache
        if self.backend_id == "ollama" and self.sokrates_model_id:  # type: ignore[attr-defined]
            from ..lib.model_vram_cache import get_model_parameters
            params = get_model_parameters(self.sokrates_model_id)
            self.sokrates_rope_factor = params["rope_factor"]
            self.sokrates_max_context = params["max_context"]
            self.sokrates_is_hybrid = params["is_hybrid"]
            self.sokrates_supports_thinking = params["supports_thinking"]
        elif self.backend_type == "llamacpp" and self.sokrates_model_id:  # type: ignore[attr-defined]
            from ..lib.model_vram_cache import (
                get_llamacpp_calibration,
                get_thinking_support_for_model,
                get_llamacpp_speed_split,
            )
            self.sokrates_rope_factor = 1.0
            self.sokrates_max_context = get_llamacpp_calibration(self.sokrates_model_id) or 0
            self.sokrates_is_hybrid = False
            self.sokrates_supports_thinking = get_thinking_support_for_model(self.sokrates_model_id)
            self.sokrates_has_speed_variant = get_llamacpp_speed_split(self.sokrates_model_id)[0] > 0
            if not self.sokrates_has_speed_variant:
                self.sokrates_speed_mode = False

        # Reset sampling params to model defaults
        self._reset_agent_sampling("sokrates")

        self._save_settings()  # type: ignore[attr-defined]
        if model:
            self.add_debug(f"\U0001f9e0 Sokrates-LLM: {model}")  # type: ignore[attr-defined]
            self._show_model_calibration_info(self.sokrates_model_id)  # type: ignore[attr-defined]
        else:
            self.add_debug("\U0001f9e0 Sokrates-LLM: (same as Main-LLM)")  # type: ignore[attr-defined]

    def set_salomo_model(self, model: str) -> None:
        """Set Salomo LLM model for multi-agent debate."""
        from ..lib.i18n import t
        lang = self.ui_language if self.ui_language != "auto" else "de"  # type: ignore[attr-defined]
        if model == t("sokrates_llm_same", lang=lang):
            model = ""
        self.salomo_model = model
        self.salomo_model_id = self._resolve_model_id(model)  # type: ignore[attr-defined]

        if not self.salomo_model_id:
            # "(wie AIfred-LLM)" selected -- clear speed variant
            self.salomo_has_speed_variant = False
            self.salomo_speed_mode = False

        # Load all model parameters from cache
        if self.backend_id == "ollama" and self.salomo_model_id:  # type: ignore[attr-defined]
            from ..lib.model_vram_cache import get_model_parameters
            params = get_model_parameters(self.salomo_model_id)
            self.salomo_rope_factor = params["rope_factor"]
            self.salomo_max_context = params["max_context"]
            self.salomo_is_hybrid = params["is_hybrid"]
            self.salomo_supports_thinking = params["supports_thinking"]
        elif self.backend_type == "llamacpp" and self.salomo_model_id:  # type: ignore[attr-defined]
            from ..lib.model_vram_cache import (
                get_llamacpp_calibration,
                get_thinking_support_for_model,
                get_llamacpp_speed_split,
            )
            self.salomo_rope_factor = 1.0
            self.salomo_max_context = get_llamacpp_calibration(self.salomo_model_id) or 0
            self.salomo_is_hybrid = False
            self.salomo_supports_thinking = get_thinking_support_for_model(self.salomo_model_id)
            self.salomo_has_speed_variant = get_llamacpp_speed_split(self.salomo_model_id)[0] > 0
            if not self.salomo_has_speed_variant:
                self.salomo_speed_mode = False

        # Reset sampling params to model defaults
        self._reset_agent_sampling("salomo")

        self._save_settings()  # type: ignore[attr-defined]
        if model:
            self.add_debug(f"\U0001f451 Salomo-LLM: {model}")  # type: ignore[attr-defined]
            self._show_model_calibration_info(self.salomo_model_id)  # type: ignore[attr-defined]
        else:
            self.add_debug("\U0001f451 Salomo-LLM: (same as Main-LLM)")  # type: ignore[attr-defined]

    # ================================================================
    # AGENT EDITOR STATE & HANDLERS
    # ================================================================

    # Editor modal visibility
    agent_editor_open: bool = False

    # Editor view mode: "list" or "edit"
    agent_editor_mode: str = "list"

    # Agent list for UI rendering (serializable dicts)
    agent_list: List[dict] = []

    # Currently editing agent (empty = creating new)
    editor_agent_id: str = ""
    editor_display_name: str = ""
    editor_emoji: str = ""
    editor_description: str = ""
    editor_role: str = "custom"

    # Prompt layer editor state
    editor_prompt_tab: str = "identity"
    editor_prompt_content: str = ""
    # Available prompt keys for current agent (for tab rendering)
    editor_prompt_keys: List[str] = []

    # New agent creation fields
    editor_new_agent_id: str = ""

    # Delete confirmation
    editor_delete_confirm: str = ""

    def open_agent_editor(self) -> None:
        """Open the agent editor modal and load agent list."""
        self._refresh_agent_list()
        self.agent_editor_mode = "list"
        self.agent_editor_open = True
        self.editor_agent_id = ""
        self.editor_delete_confirm = ""

    def close_agent_editor(self) -> None:
        """Close the agent editor modal."""
        self.agent_editor_open = False
        self.agent_editor_mode = "list"
        self.editor_agent_id = ""
        self.editor_delete_confirm = ""

    def back_to_agent_list(self) -> None:
        """Go back to agent list from edit view."""
        self.agent_editor_mode = "list"
        self.editor_agent_id = ""
        self._refresh_agent_list()

    def _refresh_agent_list(self) -> None:
        """Refresh the agent list from config for UI rendering."""
        from ..lib.agent_config import load_agents_raw
        raw = load_agents_raw()
        self.agent_list = [
            {"id": aid, **adata}
            for aid, adata in raw.items()
        ]

    def edit_agent(self, agent_id: str) -> None:
        """Open edit view for a specific agent."""
        from ..lib.agent_config import get_agent_config
        config = get_agent_config(agent_id)
        if config is None:
            return

        self.editor_agent_id = agent_id
        self.editor_display_name = config.display_name
        self.editor_emoji = config.emoji
        self.editor_description = config.description
        self.editor_role = config.role
        self.editor_prompt_tab = "identity"
        self.editor_prompt_keys = list(config.prompts.keys())
        self.editor_delete_confirm = ""
        self.agent_editor_mode = "edit"

        # Load the identity prompt content
        self._load_editor_prompt("identity")

    def _load_editor_prompt(self, prompt_key: str) -> None:
        """Load a prompt file's content into the editor."""
        from ..lib.agent_config import get_agent_config
        from ..lib.prompt_loader import PROMPTS_DIR, get_language

        config = get_agent_config(self.editor_agent_id)
        if config is None:
            return

        prompt_path = config.prompts.get(prompt_key, "")
        if not prompt_path:
            self.editor_prompt_content = ""
            return

        lang = get_language()
        full_path = PROMPTS_DIR / lang / prompt_path
        if full_path.exists():
            self.editor_prompt_content = full_path.read_text(encoding="utf-8")
        else:
            self.editor_prompt_content = ""

    def set_editor_prompt_tab(self, tab: str) -> None:
        """Switch prompt layer tab and load content."""
        self.editor_prompt_tab = tab
        self._load_editor_prompt(tab)

    def set_editor_prompt_content(self, content: str) -> None:
        """Update prompt content in editor (live typing)."""
        self.editor_prompt_content = content

    def set_editor_display_name(self, value: str) -> None:
        """Update editor display name field."""
        self.editor_display_name = value

    def set_editor_emoji(self, value: str) -> None:
        """Update editor emoji field."""
        self.editor_emoji = value

    def set_editor_description(self, value: str) -> None:
        """Update editor description field."""
        self.editor_description = value

    def set_editor_role(self, value: str) -> None:
        """Update editor role field."""
        self.editor_role = value

    def set_editor_new_agent_id(self, value: str) -> None:
        """Update new agent ID field."""
        self.editor_new_agent_id = value

    def save_agent_editor(self) -> None:
        """Save the current editor state to agent config and prompt files."""
        from ..lib.agent_config import update_agent, create_agent, get_agent_config
        from ..lib.prompt_loader import PROMPTS_DIR, get_language, register_agent_toggles

        if self.editor_agent_id:
            # Update existing agent metadata
            update_agent(self.editor_agent_id, {
                "display_name": self.editor_display_name,
                "emoji": self.editor_emoji,
                "description": self.editor_description,
                "role": self.editor_role,
            })

            # Save current prompt tab content to file
            config = get_agent_config(self.editor_agent_id)
            if config:
                prompt_path = config.prompts.get(self.editor_prompt_tab, "")
                if prompt_path:
                    lang = get_language()
                    full_path = PROMPTS_DIR / lang / prompt_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.write_text(self.editor_prompt_content, encoding="utf-8")

            self.add_debug(  # type: ignore[attr-defined]
                f"\u2705 Agent '{self.editor_display_name}' saved"
            )
        else:
            # Create new agent
            agent_id = self.editor_new_agent_id.strip().lower().replace(" ", "_")
            if not agent_id:
                self.add_debug("\u26a0\ufe0f Agent-ID is required")  # type: ignore[attr-defined]
                return

            new_config = create_agent(
                agent_id=agent_id,
                display_name=self.editor_display_name,
                emoji=self.editor_emoji,
                description=self.editor_description,
                role=self.editor_role,
            )
            register_agent_toggles(agent_id, new_config.toggles)
            self.add_debug(  # type: ignore[attr-defined]
                f"\u2705 Agent '{self.editor_display_name}' created"
            )
            # Switch to editing the newly created agent
            self.editor_agent_id = agent_id
            self.editor_prompt_keys = list(new_config.prompts.keys())
            self._load_editor_prompt("identity")

        self._refresh_agent_list()

    def delete_agent_editor(self, agent_id: str) -> None:
        """Delete an agent (with confirmation)."""
        if self.editor_delete_confirm != agent_id:
            # First click: ask for confirmation
            self.editor_delete_confirm = agent_id
            return

        # Second click: actually delete
        from ..lib.agent_config import delete_agent
        from ..lib.prompt_loader import unregister_agent_toggles

        try:
            delete_agent(agent_id)
            unregister_agent_toggles(agent_id)
            self.add_debug(f"\U0001f5d1\ufe0f Agent '{agent_id}' deleted")  # type: ignore[attr-defined]
        except ValueError as e:
            self.add_debug(f"\u26a0\ufe0f {e}")  # type: ignore[attr-defined]

        self.editor_delete_confirm = ""
        if self.editor_agent_id == agent_id:
            self.editor_agent_id = ""
        self._refresh_agent_list()

    def reset_editor_prompt(self) -> None:
        """Reset current prompt tab to the file on disk (discard unsaved changes)."""
        self._load_editor_prompt(self.editor_prompt_tab)

    def start_new_agent(self) -> None:
        """Switch editor to 'create new agent' mode."""
        self.editor_agent_id = ""
        self.editor_display_name = ""
        self.editor_emoji = "\U0001f916"
        self.editor_description = ""
        self.editor_role = "custom"
        self.editor_new_agent_id = ""
        self.editor_prompt_tab = "identity"
        self.editor_prompt_content = ""
        self.editor_prompt_keys = []
        self.agent_editor_mode = "edit"
