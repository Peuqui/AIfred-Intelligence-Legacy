"""
Settings Persistence

Saves and loads user settings from ~/.config/aifred/settings.json
Falls back to config.py defaults if no settings file exists.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


SETTINGS_DIR = Path.home() / ".config" / "aifred"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"


def load_settings() -> Optional[Dict[str, Any]]:
    """
    Load settings from file

    Returns:
        Dict with settings or None if file doesn't exist
    """
    if not SETTINGS_FILE.exists():
        return None

    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            data: Dict[str, Any] = json.load(f)
            return data
    except Exception as e:
        print(f"⚠️ Failed to load settings: {e}")
        return None


def save_settings(settings: Dict[str, Any]) -> bool:
    """
    Save settings to file

    Args:
        settings: Dict with settings to save

    Returns:
        True if successful, False otherwise
    """
    try:
        # Create directory if it doesn't exist
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

        print(f"✅ Settings saved to {SETTINGS_FILE}")
        return True

    except Exception as e:
        print(f"❌ Failed to save settings: {e}")
        return False


def get_default_settings() -> Dict[str, Any]:
    """
    Get default settings from config.py DEFAULT_SETTINGS

    Returns:
        Dict with default settings from config.py
    """
    from .config import DEFAULT_SETTINGS, BACKEND_DEFAULT_MODELS

    # Merge DEFAULT_SETTINGS with backend-specific models
    defaults = DEFAULT_SETTINGS.copy()
    defaults["backend_models"] = BACKEND_DEFAULT_MODELS
    defaults["backend_type"] = "ollama"
    # vLLM YaRN & Context Settings (0 = auto-detect on first run)
    defaults["enable_yarn"] = False
    defaults["yarn_factor"] = 1.0
    defaults["vllm_max_tokens"] = 0
    defaults["vllm_native_context"] = 0

    return defaults


def reset_to_defaults() -> bool:
    """
    Reset all settings to defaults from config.py

    Returns:
        True if successful, False otherwise
    """
    defaults = get_default_settings()
    return save_settings(defaults)
