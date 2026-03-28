"""Unified AIfred Plugin System.

All plugins live here:
- plugins/channels/  → Message channel plugins (email, discord, ...)
- plugins/tools/     → LLM tool plugins (research, EPIM, sandbox, ...)
- plugins/disabled/  → Disabled plugins (moved here by Plugin Manager)

Usage:
    from aifred.plugins.registry import all_channels, discover_tools, get_channel
    from aifred.plugins.base import BaseChannel, ToolPlugin, PluginContext
"""
