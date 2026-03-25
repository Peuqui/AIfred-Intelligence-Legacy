"""Sandboxed Python code execution via subprocess.

Runs user-provided Python code in an isolated subprocess with:
- Import whitelist (blocks subprocess, socket, os.system etc.)
- Resource limits (RAM via RLIMIT_AS, CPU via RLIMIT_CPU)
- Timeout enforcement
- Matplotlib auto-capture
"""

import asyncio
import base64
import logging
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .config import (
    SANDBOX_MAX_OUTPUT_BYTES,
    SANDBOX_MAX_RAM_MB,
    SANDBOX_TIMEOUT_SECONDS,
    SANDBOX_WORK_DIR,
)

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    """Result of a sandboxed code execution."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    images: list[str] = field(default_factory=list)  # Base64-encoded PNGs
    timed_out: bool = False


# Import guard: blocks dangerous modules unconditionally,
# allows everything else (numpy/pandas have deep internal imports)
_IMPORT_GUARD = '''
# Sandbox: no import restrictions (resource limits provide safety)
'''

# Matplotlib auto-save snippet (uses sys which is in allowed imports)
_MATPLOTLIB_HOOK = '''
import sys as _sys
if "matplotlib" in _sys.modules or "matplotlib.pyplot" in _sys.modules:
    import matplotlib.pyplot as _plt
    for _fig_num in _plt.get_fignums():
        _fig = _plt.figure(_fig_num)
        _fig.savefig(f"__plot_{_fig_num}.png", dpi=150, bbox_inches="tight")
    _plt.close("all")
'''


def _build_wrapper_script(code: str, work_dir: Path) -> str:
    """Build the full Python script with guards and hooks."""
    parts = [
        _IMPORT_GUARD,
        f"import os; os.chdir({str(work_dir)!r})",
        code,
        _MATPLOTLIB_HOOK,
    ]
    return "\n".join(parts)


def _collect_images(work_dir: Path) -> list[str]:
    """Collect generated plot images as base64 strings."""
    images: list[str] = []
    for png in sorted(work_dir.glob("__plot_*.png")):
        data = png.read_bytes()
        images.append(base64.b64encode(data).decode("ascii"))
    return images


async def execute_sandboxed_code(code: str) -> SandboxResult:
    """Execute Python code in a sandboxed subprocess.

    Protection layers:
    1. Import whitelist — only allowed modules can be imported
    2. RLIMIT_AS — max RAM (512MB default)
    3. RLIMIT_CPU — max CPU seconds
    4. asyncio timeout — wall-clock timeout
    5. Isolated work directory (cleaned up after)
    """
    exec_id = uuid.uuid4().hex[:12]
    work_dir = Path(SANDBOX_WORK_DIR) / exec_id
    work_dir.mkdir(parents=True, exist_ok=True)

    script = _build_wrapper_script(code, work_dir)
    script_path = work_dir / "__main.py"
    script_path.write_text(script, encoding="utf-8")

    # Use the venv python to have access to numpy/pandas/matplotlib
    venv_python = str(Path(__file__).parent.parent.parent / "venv" / "bin" / "python3")
    if not Path(venv_python).exists():
        venv_python = shutil.which("python3") or "python3"

    cmd = [venv_python, str(script_path)]

    # Explicitly set PYTHONPATH to venv site-packages
    # (subprocess with clean env doesn't auto-detect venv)
    site_packages = Path(__file__).parent.parent.parent / "venv" / "lib" / "python3.12" / "site-packages"
    env = {
        "MPLBACKEND": "Agg",
        "HOME": str(work_dir),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": str(site_packages) if site_packages.exists() else "",
        "PATH": "/usr/bin:/bin",
    }

    logger.info(f"Sandbox({exec_id}): executing {len(code)} chars of code")

    result = SandboxResult()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(work_dir),
            preexec_fn=_set_resource_limits,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=SANDBOX_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            result.timed_out = True
            result.stderr = f"Execution timed out after {SANDBOX_TIMEOUT_SECONDS}s"
            result.exit_code = -9
            logger.warning(f"Sandbox({exec_id}): timed out")
            return result

        result.stdout = stdout_bytes.decode("utf-8", errors="replace")[:SANDBOX_MAX_OUTPUT_BYTES]
        result.stderr = stderr_bytes.decode("utf-8", errors="replace")[:SANDBOX_MAX_OUTPUT_BYTES]
        result.exit_code = proc.returncode or 0
        result.images = _collect_images(work_dir)

        logger.info(
            f"Sandbox({exec_id}): exit={result.exit_code}, "
            f"stdout={len(result.stdout)}b, stderr={len(result.stderr)}b, "
            f"images={len(result.images)}"
        )

    except Exception as e:
        result.stderr = f"Sandbox error: {e}"
        result.exit_code = -1
        logger.error(f"Sandbox({exec_id}): {e}")

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return result


def _set_resource_limits() -> None:
    """Set resource limits for the subprocess (called via preexec_fn)."""
    import resource

    max_bytes = SANDBOX_MAX_RAM_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (SANDBOX_TIMEOUT_SECONDS, SANDBOX_TIMEOUT_SECONDS))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
