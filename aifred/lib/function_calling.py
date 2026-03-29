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
import time
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
    tier: int = 0  # Security tier (0=readonly … 4=admin)

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
    _session_id: str = ""   # Audit context
    _source: str = ""       # Audit context (browser/email/discord/…)

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

        t0 = time.perf_counter()
        result_str = ""
        success = True
        try:
            result = tool.executor(**args)
            if asyncio.iscoroutine(result):
                result = await result
            result_str = json.dumps(result) if not isinstance(result, str) else result
            return result_str
        except Exception as e:
            success = False
            logger.error(f"Tool '{name}' failed: {e}")
            result_str = json.dumps({"error": str(e)})
            return result_str
        finally:
            try:
                from .security import audit_log
                audit_log(
                    session_id=self._session_id,
                    source=self._source,
                    tool_name=name,
                    tool_tier=tool.tier,
                    tool_args_preview=str(args)[:200],
                    result_preview=result_str[:200],
                    success=success,
                    duration_ms=(time.perf_counter() - t0) * 1000,
                )
            except Exception:
                pass  # Audit must never block tool execution
