"""Unified plugin registry — discovers channels and tools from subdirectories.

Scans:
- aifred/plugins/channels/ → BaseChannel instances
- aifred/plugins/tools/    → ToolPlugin instances
- aifred/plugins/disabled/ → stored but not loaded

Plugins can be enabled/disabled by moving files between their
subdirectory and disabled/.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import shutil
import sys
from pathlib import Path
from typing import Optional

from .plugin_base import BaseChannel, ToolPlugin

logger = logging.getLogger(__name__)


def _plugins_root() -> Path:
    return Path(__file__).parent.parent / "plugins"


def _disabled_dir() -> Path:
    d = _plugins_root() / "disabled"
    d.mkdir(exist_ok=True)
    return d


# ============================================================
# CHANNEL REGISTRY
# ============================================================

_channels: dict[str, BaseChannel] = {}
_channels_discovered = False


def _discover_channels() -> None:
    """Import all modules in plugins/channels/ and collect BaseChannel instances."""
    global _channels_discovered
    if _channels_discovered:
        return
    _channels_discovered = True

    from .logging_utils import log_message

    channels_dir = _plugins_root() / "channels"
    if not channels_dir.exists():
        return

    # Ensure channels subpackage is importable
    channels_init = channels_dir / "__init__.py"
    if not channels_init.exists():
        channels_init.touch()

    for module_info in pkgutil.iter_modules([str(channels_dir)]):
        if module_info.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f".channels.{module_info.name}", package="aifred.plugins")
            # Look for a module-level instance of BaseChannel
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if isinstance(obj, BaseChannel) and obj.name not in _channels:
                    _channels[obj.name] = obj
                    log_message(f"Plugin Registry: channel '{obj.name}' registered")
        except Exception as exc:
            log_message(f"Plugin Registry: failed to load channel '{module_info.name}': {exc}", "error")


def get_channel(name: str) -> BaseChannel | None:
    _discover_channels()
    return _channels.get(name)


def all_channels() -> dict[str, BaseChannel]:
    _discover_channels()
    return dict(_channels)


# ============================================================
# TOOL PLUGIN REGISTRY
# ============================================================

_tools: Optional[list[ToolPlugin]] = None


def discover_tools() -> list[ToolPlugin]:
    """Scan plugins/tools/ and return all ToolPlugin instances. Cached."""
    global _tools
    if _tools is not None:
        return _tools

    from .logging_utils import log_message

    tools_dir = _plugins_root() / "tools"
    if not tools_dir.exists():
        _tools = []
        return _tools

    # Ensure tools subpackage is importable
    tools_init = tools_dir / "__init__.py"
    if not tools_init.exists():
        tools_init.touch()

    _tools = []
    for module_info in pkgutil.iter_modules([str(tools_dir)]):
        if module_info.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f".tools.{module_info.name}", package="aifred.plugins")
        except Exception as e:
            log_message(f"Plugin Registry: failed to load tool '{module_info.name}': {e}", "error")
            continue

        plugin = getattr(mod, "plugin", None)
        if plugin is not None and isinstance(plugin, ToolPlugin):
            _tools.append(plugin)

    log_message(f"Plugin Registry: {len(_tools)} tool plugins: {[p.name for p in _tools]}")
    return _tools


# ============================================================
# RELOAD (after enable/disable)
# ============================================================

def reload_all() -> None:
    """Clear all caches and re-discover. Called after moving plugin files."""
    global _tools, _channels, _channels_discovered

    # Clear tool cache + stale modules
    stale = [k for k in sys.modules if k.startswith("aifred.plugins.tools.") or k.startswith("aifred.plugins.channels.")]
    for k in stale:
        del sys.modules[k]

    _tools = None
    _channels.clear()
    _channels_discovered = False

    # Re-discover
    discover_tools()
    _discover_channels()


# ============================================================
# LIST / ENABLE / DISABLE (for Plugin Manager UI)
# ============================================================

def list_all_plugins() -> list[dict[str, str]]:
    """List all plugins (enabled + disabled) with status.

    Returns: [{"name": "epim", "file": "epim.py", "type": "tool", "enabled": "1"}, ...]
    """
    root = _plugins_root()
    disabled = _disabled_dir()
    result: list[dict[str, str]] = []

    def _display(stem: str) -> str:
        return stem.replace("_", " ").title()

    # Enabled channels
    channels_dir = root / "channels"
    if channels_dir.exists():
        for f in sorted(channels_dir.glob("*.py")):
            if f.name.startswith("_"):
                continue
            result.append({"name": f.stem, "display": _display(f.stem), "file": f.name, "type": "channel", "enabled": "1"})

    # Enabled tools
    tools_dir = root / "tools"
    if tools_dir.exists():
        for f in sorted(tools_dir.glob("*.py")):
            if f.name.startswith("_"):
                continue
            result.append({"name": f.stem, "display": _display(f.stem), "file": f.name, "type": "tool", "enabled": "1"})

    # Disabled (both types — filename encodes origin via prefix)
    for f in sorted(disabled.glob("*.py")):
        if f.name.startswith("_"):
            continue
        # Determine type from prefix: channel_ or tool_
        if f.name.startswith("channel_"):
            ptype = "channel"
            pname = f.stem.removeprefix("channel_")
        elif f.name.startswith("tool_"):
            ptype = "tool"
            pname = f.stem.removeprefix("tool_")
        else:
            ptype = "tool"
            pname = f.stem
        result.append({"name": pname, "display": _display(pname), "file": f.name, "type": ptype, "enabled": ""})

    result.sort(key=lambda p: p["name"])
    return result


def disable_plugin(name: str, plugin_type: str) -> bool:
    """Move a plugin to disabled/. Prefixes filename with type."""
    if plugin_type == "channel":
        src = _plugins_root() / "channels" / f"{name}.py"
        dst_name = f"channel_{name}.py"
    else:
        src = _plugins_root() / "tools" / f"{name}.py"
        dst_name = f"tool_{name}.py"

    if not src.exists():
        return False

    dst = _disabled_dir() / dst_name
    shutil.move(str(src), str(dst))
    reload_all()
    return True


def enable_plugin(name: str, plugin_type: str) -> bool:
    """Move a plugin back from disabled/ to its subdirectory."""
    if plugin_type == "channel":
        src = _disabled_dir() / f"channel_{name}.py"
        dst = _plugins_root() / "channels" / f"{name}.py"
    else:
        src = _disabled_dir() / f"tool_{name}.py"
        dst = _plugins_root() / "tools" / f"{name}.py"

    if not src.exists():
        return False

    shutil.move(str(src), str(dst))
    reload_all()
    return True
