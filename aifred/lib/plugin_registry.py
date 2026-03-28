"""Plugin registry with auto-discovery for AIfred tool plugins.

Scans aifred/lib/plugins/ for modules exposing a `plugin` attribute
that satisfies the ToolPlugin protocol.
"""

import importlib
import logging
import pkgutil
from typing import Optional

from .plugin import ToolPlugin

logger = logging.getLogger(__name__)

_plugins: Optional[list[ToolPlugin]] = None


def discover_plugins() -> list[ToolPlugin]:
    """Scan aifred/lib/plugins/ and return all discovered ToolPlugin instances.

    Results are cached — the scan only happens once per process.
    """
    global _plugins
    if _plugins is not None:
        return _plugins

    import aifred.lib.plugins as plugins_pkg

    _plugins = []
    for _finder, module_name, _is_pkg in pkgutil.iter_modules(plugins_pkg.__path__):
        try:
            mod = importlib.import_module(f"aifred.lib.plugins.{module_name}")
        except Exception as e:
            logger.warning(f"Failed to import plugin {module_name}: {e}")
            continue

        plugin = getattr(mod, "plugin", None)
        if plugin is not None and isinstance(plugin, ToolPlugin):
            _plugins.append(plugin)
        else:
            logger.debug(f"Plugin module {module_name} has no valid 'plugin' attribute")

    logger.info(f"Discovered {len(_plugins)} tool plugins: {[p.name for p in _plugins]}")
    return _plugins
