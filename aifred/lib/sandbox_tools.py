"""Sandbox code execution tool for LLM function calling.

Provides a single `execute_code` tool that runs Python in a sandboxed subprocess.
"""

import json
from pathlib import Path
from typing import Optional

from .function_calling import Tool
from .logging_utils import log_message


def _load_tool_description() -> str:
    """Load tool description from prompt file."""
    path = Path(__file__).parent.parent.parent / "prompts" / "shared" / "execute_code_tool.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return "Execute Python code in a sandboxed environment."


def get_sandbox_tools(session_id: Optional[str] = None) -> list[Tool]:
    """Create sandbox tools for LLM function calling.

    Args:
        session_id: Session ID for output file organization and cleanup.
    """

    async def _execute_code(code: str, description: str = "") -> str:
        """Tool executor: run Python code in sandbox, return results."""
        from .sandbox import execute_sandboxed_code

        if not code or not code.strip():
            return json.dumps({"error": "No code provided"})

        log_message(f"🔧 execute_code: {description or '(no description)'}")

        result = await execute_sandboxed_code(code, session_id=session_id or "")

        # Format output for LLM
        parts: list[str] = []

        if result.timed_out:
            parts.append("⏰ TIMEOUT: Execution exceeded time limit.")

        if result.stdout:
            parts.append(f"STDOUT:\n{result.stdout}")

        if result.stderr:
            parts.append(f"STDERR:\n{result.stderr}")

        if result.html_url:
            parts.append(f"SANDBOX_HTML_URL: {result.html_url}")
            parts.append("The interactive visualization is automatically embedded in the chat. Do NOT try to display it again. Just describe what was created.")

        if result.images:
            for img_url in result.images:
                parts.append(f"SANDBOX_IMAGE_URL: {img_url}")
            parts.append("The plot image is automatically displayed in the chat. Do NOT try to show it again or generate base64. Just describe the result.")

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
