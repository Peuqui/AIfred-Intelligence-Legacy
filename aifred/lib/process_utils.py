"""
Process Utilities - Unified process management for AIfred backends

Provides common functions for:
- Stopping processes by pattern (pgrep/pkill)
- GPU memory cleanup
- Service management (systemctl)

This module reduces code duplication across state.py and vllm_manager.py.
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
        pattern: Process pattern for pgrep/pkill (e.g., "vllm serve")
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

    except subprocess.CalledProcessError as e:
        log_message(f"Error stopping process '{pattern}': {e}")
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
    except subprocess.CalledProcessError as e:
        log_message(f"Error restarting service '{service_name}': {e}")
        return False


# Process patterns for AIfred backends (centralized constants)
PROCESS_PATTERNS = {
    "vllm": "vllm serve",
    "tabbyapi": "tabbyapi",
}


async def stop_backend_process(backend_type: str, wait_for_vram: bool = True) -> bool:
    """
    Stop a backend process by backend type.

    Convenience wrapper using PROCESS_PATTERNS.

    Args:
        backend_type: Backend identifier ("vllm", "tabbyapi")
        wait_for_vram: Wait for GPU memory release

    Returns:
        True if process was stopped
    """
    pattern = PROCESS_PATTERNS.get(backend_type)
    if not pattern:
        log_message(f"Unknown backend type: {backend_type}")
        return False

    return await stop_process(pattern, wait_for_vram=wait_for_vram)


# ============================================================
# Docker Container Management
# ============================================================

def restart_docker_container(
    compose_file: str,
    service_name: str,
    env_vars: dict[str, str] | None = None
) -> tuple[bool, str]:
    """
    Restart a Docker container with optional environment variable changes.

    Uses docker compose down + up to ensure env vars are reloaded.
    If env_vars is provided, writes them to .env file before restart.

    Args:
        compose_file: Path to docker-compose.yml
        service_name: Name of the service to restart (e.g., "xtts")
        env_vars: Optional dict of environment variables to write to .env

    Returns:
        tuple[bool, str]: (success, message)
    """
    from pathlib import Path

    compose_path = Path(compose_file)
    if not compose_path.exists():
        return False, f"docker-compose.yml not found: {compose_file}"

    compose_dir = compose_path.parent

    # Write .env file if env_vars provided
    if env_vars:
        env_file = compose_dir / ".env"
        try:
            with open(env_file, "w") as f:
                for key, value in env_vars.items():
                    f.write(f"{key}={value}\n")
            log_message(f"Wrote .env: {env_vars}")
        except (OSError, subprocess.CalledProcessError) as e:
            return False, f"Failed to write .env: {e}"

    # Stop container
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "down"],
            capture_output=True,
            text=True,
            cwd=str(compose_dir)
        )
        if result.returncode != 0:
            return False, f"docker compose down failed: {result.stderr}"
        log_message(f"Docker container '{service_name}' stopped")
    except OSError as e:
        return False, f"docker compose down error: {e}"

    # Start container
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "up", "-d"],
            capture_output=True,
            text=True,
            cwd=str(compose_dir)
        )
        if result.returncode != 0:
            return False, f"docker compose up failed: {result.stderr}"
        log_message(f"Docker container '{service_name}' started")
    except OSError as e:
        return False, f"docker compose up error: {e}"

    return True, f"Container '{service_name}' restarted successfully"


def set_xtts_cpu_mode(force_cpu: bool) -> tuple[bool, str]:
    """
    Set XTTS CPU mode and restart the container.

    Args:
        force_cpu: True = force CPU mode, False = auto-detect (prefer GPU)

    Returns:
        tuple[bool, str]: (success, message)
    """
    from .config import XTTS_DOCKER_COMPOSE_PATH

    env_vars = {"XTTS_FORCE_CPU": "1" if force_cpu else "0"}
    mode_str = "CPU" if force_cpu else "GPU (auto)"

    success, message = restart_docker_container(
        compose_file=XTTS_DOCKER_COMPOSE_PATH,
        service_name="xtts",
        env_vars=env_vars
    )

    if success:
        return True, f"XTTS Container neu gestartet im {mode_str}-Modus (Modell lädt...)"
    return False, message


def _detect_fastest_gpu(compose_dir: str) -> None:
    """Detect fastest GPU and write FASTEST_GPU_ID to .env in compose_dir.

    Picks the GPU with the most VRAM. Writes .env so docker-compose
    can use ${FASTEST_GPU_ID} for device_ids.
    """
    from pathlib import Path
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return
        # Parse: "0, 24576\n1, 49152\n..."  → pick highest VRAM
        best_id, best_vram = "0", 0
        for line in result.stdout.strip().split("\n"):
            parts = line.split(",")
            if len(parts) == 2:
                gpu_id = parts[0].strip()
                vram = int(parts[1].strip())
                if vram > best_vram:
                    best_id, best_vram = gpu_id, vram

        env_path = Path(compose_dir) / ".env"
        # Read existing .env content (preserve other vars)
        existing = {}
        if env_path.exists():
            for line in env_path.read_text().strip().split("\n"):
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip()
        existing["FASTEST_GPU_ID"] = best_id
        env_path.write_text("\n".join(f"{k}={v}" for k, v in existing.items()) + "\n")
    except (OSError, subprocess.TimeoutExpired):
        pass  # nvidia-smi not available, keep defaults


def _docker_compose_action(
    compose_file: str,
    action: str,
    service_label: str,
) -> tuple[bool, str]:
    """
    Run a docker compose action (up -d / down) on a compose file.

    Args:
        compose_file: Path to docker-compose.yml
        action: "up" or "down"
        service_label: Human-readable name for log messages (e.g. "XTTS")

    Returns:
        tuple[bool, str]: (success, message)
    """
    from pathlib import Path

    compose_path = Path(compose_file)
    if not compose_path.exists():
        return False, f"docker-compose.yml not found: {compose_file}"

    # Before starting: detect fastest GPU and write .env
    if action == "up":
        _detect_fastest_gpu(str(compose_path.parent))

    cmd = ["docker", "compose", "-f", str(compose_file)]
    if action == "up":
        cmd.extend(["up", "-d"])
    else:
        cmd.append("down")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(compose_path.parent),
        )
        if result.returncode != 0:
            return False, f"docker compose {action} failed: {result.stderr}"
        verb = "started" if action == "up" else "stopped"
        log_message(f"{service_label} container {verb}")
        return True, f"{service_label} container {verb}"
    except subprocess.CalledProcessError as e:
        return False, f"docker compose {action} error: {e}"


def start_xtts_container() -> tuple[bool, str]:
    """Start the XTTS Docker container."""
    from .config import XTTS_DOCKER_COMPOSE_PATH
    return _docker_compose_action(XTTS_DOCKER_COMPOSE_PATH, "up", "XTTS")


def stop_xtts_container() -> tuple[bool, str]:
    """Stop the XTTS Docker container to free VRAM."""
    from .config import XTTS_DOCKER_COMPOSE_PATH
    return _docker_compose_action(XTTS_DOCKER_COMPOSE_PATH, "down", "XTTS")


def ensure_xtts_ready(timeout: int = 60) -> tuple[bool, str]:
    """
    Ensure XTTS container is running and model is loaded.

    Starts container if needed and waits for model to load.
    This is a synchronous, blocking function - no async.

    Args:
        timeout: Max seconds to wait for model to load (default: 60)

    Returns:
        tuple[bool, str]: (success, message with device info or error)
    """
    import time
    import requests
    from .config import XTTS_SERVICE_URL

    # Step 1: Check if already running and model loaded
    try:
        r = requests.get(f"{XTTS_SERVICE_URL}/health", timeout=2)
        if r.ok and r.json().get("model_loaded"):
            device = r.json().get("device", "unknown")
            return True, f"XTTS already ready ({device})"
    except OSError:
        pass  # Container not running or not responding

    # Step 2: Start container
    success, msg = start_xtts_container()
    if not success:
        return False, msg

    # Step 3: Wait for model to load
    log_message("XTTS: Waiting for model to load...")
    for i in range(timeout):
        try:
            r = requests.get(f"{XTTS_SERVICE_URL}/health", timeout=2)
            if r.ok and r.json().get("model_loaded"):
                device = r.json().get("device", "unknown")
                log_message(f"XTTS: Model loaded on {device}")
                return True, f"XTTS ready ({device})"
        except (OSError, subprocess.CalledProcessError):
            pass
        time.sleep(1)

    return False, f"XTTS: Timeout after {timeout}s waiting for model"


def start_moss_container() -> tuple[bool, str]:
    """Start the MOSS-TTS Docker container."""
    from .config import MOSS_TTS_DOCKER_COMPOSE_PATH
    return _docker_compose_action(MOSS_TTS_DOCKER_COMPOSE_PATH, "up", "MOSS-TTS")


def stop_moss_container() -> tuple[bool, str]:
    """Stop the MOSS-TTS Docker container to free VRAM."""
    from .config import MOSS_TTS_DOCKER_COMPOSE_PATH
    return _docker_compose_action(MOSS_TTS_DOCKER_COMPOSE_PATH, "down", "MOSS-TTS")


def ensure_moss_ready(timeout: int = 120) -> tuple[bool, str, str]:
    """
    Ensure MOSS-TTS container is running and model is loaded.

    Starts container if needed and waits for model to load.
    Longer default timeout than XTTS because MOSS model is larger.

    Returns:
        Tuple of (success, message, device) where device is "cuda", "cpu", or "".
    """
    import time
    import requests
    from .config import MOSS_TTS_SERVICE_URL

    # Step 1: Check if already running and model loaded
    try:
        r = requests.get(f"{MOSS_TTS_SERVICE_URL}/health", timeout=2)
        if r.ok and r.json().get("model_loaded"):
            device = r.json().get("device", "unknown")
            return True, f"MOSS-TTS already ready ({device})", device
    except OSError:
        pass

    # Step 2: Start container
    success, msg = start_moss_container()
    if not success:
        return False, msg, ""

    # Step 3: Wait for model to load (MOSS is larger, needs more time)
    log_message("MOSS-TTS: Waiting for model to load...")
    for i in range(timeout):
        try:
            r = requests.get(f"{MOSS_TTS_SERVICE_URL}/health", timeout=2)
            if r.ok and r.json().get("model_loaded"):
                device = r.json().get("device", "unknown")
                log_message(f"MOSS-TTS: Model loaded on {device}")
                return True, f"MOSS-TTS ready ({device})", device
        except OSError:
            pass
        time.sleep(1)

    return False, f"MOSS-TTS: Timeout after {timeout}s waiting for model", ""


