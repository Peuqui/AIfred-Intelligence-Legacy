"""Lightweight function calling infrastructure for AIfred agents.

Tools are callable functions that LLMs can invoke via OpenAI-compatible
function calling. A ToolKit bundles tools for a specific call and handles
execution of tool calls returned by the LLM.

Usage:
    toolkit = ToolKit([
        Tool(name="store_memory", description="...", parameters={...}, executor=my_func),
    ])
    # Pass toolkit.definitions to the API call as `tools` parameter
    # Use toolkit.execute(name, args) to run a tool call
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    """A single tool that an LLM can call."""

    name: str
    description: str
    parameters: dict[str, Any]
    executor: Callable[..., Any]

    @property
    def definition(self) -> dict[str, Any]:
        """OpenAI-compatible tool definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolKit:
    """A set of tools available for a specific LLM call.

    Created per-call with agent-specific executors (closures),
    so tools can access agent context without global state.
    """

    tools: list[Tool] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._by_name: dict[str, Tool] = {t.name: t for t in self.tools}

    @property
    def definitions(self) -> list[dict[str, Any]]:
        """OpenAI-compatible tool definitions for API call."""
        return [t.definition for t in self.tools]

    async def execute(self, name: str, arguments: str | dict[str, Any]) -> str:
        """Execute a tool by name. Arguments can be JSON string or dict."""
        tool = self._by_name.get(name)
        if not tool:
            return json.dumps({"error": f"Unknown tool: {name}"})

        args: dict[str, Any]
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                return json.dumps({"error": f"Invalid JSON arguments: {arguments}"})
        else:
            args = arguments

        try:
            result = tool.executor(**args)
            if asyncio.iscoroutine(result):
                result = await result
            return json.dumps(result) if not isinstance(result, str) else result
        except Exception as e:
            logger.error(f"Tool '{name}' failed: {e}")
            return json.dumps({"error": str(e)})
