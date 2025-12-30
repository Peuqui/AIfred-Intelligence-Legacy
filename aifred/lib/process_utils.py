"""
Process Utilities - Unified process management for AIfred backends

Provides common functions for:
- Stopping processes by pattern (pgrep/pkill)
- GPU memory cleanup
- Service management (systemctl)

This module reduces code duplication across state.py, vllm_manager.py,
and koboldcpp_manager.py.
"""

import subprocess
import asyncio
from .logging_utils import log_message


async def stop_process(
    pattern: str,
    wait_for_vram: bool = True,
    wait_seconds: float = 2.0
) -> bool:
    """
    Stop a process by pattern and optionally wait for VRAM release.

    Uses pgrep to check if process exists, pkill to terminate.

    Args:
        pattern: Process pattern for pgrep/pkill (e.g., "vllm serve", "koboldcpp")
        wait_for_vram: Wait for GPU memory to be freed after stopping
        wait_seconds: Seconds to wait for VRAM release (default: 2.0)

    Returns:
        True if process was running and stopped, False if not running
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            # Process is running - kill it
            subprocess.run(["pkill", "-f", pattern])
            log_message(f"Stopped process: {pattern}")

            if wait_for_vram:
                await asyncio.sleep(wait_seconds)
                log_message(f"Waited {wait_seconds}s for VRAM release")

            return True
        else:
            # Process not running
            return False

    except Exception as e:
        log_message(f"Error stopping process '{pattern}': {e}")
        return False


def stop_process_sync(pattern: str) -> bool:
    """
    Synchronous version of stop_process (no VRAM wait).

    Use this in non-async contexts where waiting isn't needed.

    Args:
        pattern: Process pattern for pgrep/pkill

    Returns:
        True if process was stopped, False if not running
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            subprocess.run(["pkill", "-f", pattern])
            log_message(f"Stopped process: {pattern}")
            return True
        return False

    except Exception as e:
        log_message(f"Error stopping process '{pattern}': {e}")
        return False


def is_process_running(pattern: str) -> bool:
    """
    Check if a process matching the pattern is running.

    Args:
        pattern: Process pattern for pgrep

    Returns:
        True if process is running
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False


def cleanup_gpu_memory():
    """
    Force GPU memory cleanup using gc.collect() and torch.cuda.empty_cache().

    Safe to call even if torch/CUDA is not available.
    """
    import gc
    gc.collect()

    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            log_message("GPU memory cache cleared")
    except ImportError:
        pass  # torch not installed


def restart_service(service_name: str, check: bool = False) -> bool:
    """
    Restart a systemd service.

    Args:
        service_name: Service name (e.g., "ollama", "aifred-intelligence")
        check: If True, raise exception on failure

    Returns:
        True if successful
    """
    try:
        subprocess.run(
            ["systemctl", "restart", service_name],
            check=check
        )
        log_message(f"Service '{service_name}' restarted")
        return True
    except subprocess.CalledProcessError as e:
        log_message(f"Failed to restart service '{service_name}': {e}")
        return False
    except Exception as e:
        log_message(f"Error restarting service '{service_name}': {e}")
        return False


# Process patterns for AIfred backends (centralized constants)
PROCESS_PATTERNS = {
    "vllm": "vllm serve",
    "tabbyapi": "tabbyapi",
    "koboldcpp": "koboldcpp",
}


async def stop_backend_process(backend_type: str, wait_for_vram: bool = True) -> bool:
    """
    Stop a backend process by backend type.

    Convenience wrapper using PROCESS_PATTERNS.

    Args:
        backend_type: Backend identifier ("vllm", "tabbyapi", "koboldcpp")
        wait_for_vram: Wait for GPU memory release

    Returns:
        True if process was stopped
    """
    pattern = PROCESS_PATTERNS.get(backend_type)
    if not pattern:
        log_message(f"Unknown backend type: {backend_type}")
        return False

    return await stop_process(pattern, wait_for_vram=wait_for_vram)
