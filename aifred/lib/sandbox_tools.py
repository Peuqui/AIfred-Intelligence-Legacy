"""Sandbox code execution tool for LLM function calling.

Provides a single `execute_code` tool that runs Python in a bwrap sandbox.
"""

import json
import logging
from pathlib import Path

from .function_calling import Tool

logger = logging.getLogger(__name__)


def _load_tool_description() -> str:
    """Load tool description from prompt file."""
    path = Path(__file__).parent.parent.parent / "prompts" / "shared" / "execute_code_tool.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return "Execute Python code in a sandboxed environment."


def get_sandbox_tools() -> list[Tool]:
    """Create sandbox tools for LLM function calling."""

    async def _execute_code(code: str, description: str = "") -> str:
        """Tool executor: run Python code in sandbox, return results."""
        from .sandbox import execute_sandboxed_code

        if not code or not code.strip():
            return json.dumps({"error": "No code provided"})

        logger.info(f"execute_code tool called: {description or '(no description)'}")

        result = await execute_sandboxed_code(code)

        # Format output for LLM
        parts: list[str] = []

        if result.timed_out:
            parts.append("⏰ TIMEOUT: Execution exceeded time limit.")

        if result.stdout:
            parts.append(f"STDOUT:\n{result.stdout}")

        if result.stderr:
            # Filter out import guard noise from stderr
            stderr = result.stderr
            parts.append(f"STDERR:\n{stderr}")

        if result.images:
            parts.append(f"PLOTS: {len(result.images)} image(s) generated")
            # Images are base64 — include first image inline for LLM context
            for i, img_b64 in enumerate(result.images, 1):
                parts.append(f"[Plot {i}: base64 PNG, {len(img_b64)} chars]")

        if result.exit_code != 0 and not result.timed_out:
            parts.append(f"EXIT CODE: {result.exit_code}")

        if not parts:
            parts.append("Code executed successfully (no output).")

        return "\n\n".join(parts)

    return [
        Tool(
            name="execute_code",
            description=_load_tool_description(),
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description of what the code does (for logging)",
                    },
                },
                "required": ["code"],
            },
            executor=_execute_code,
        ),
    ]
