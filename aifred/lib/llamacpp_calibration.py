"""
llama.cpp Context Calibration via llama-swap

Determines the maximum context window for each GGUF model by binary search:
start llama-server directly on a temp port with varying -c values,
check if it starts successfully (health endpoint), find the maximum.

Results are cached in model_vram_cache.json and written back to the
llama-swap YAML config.
"""

import asyncio
import logging
import re
import signal
import subprocess
from pathlib import Path
from typing import AsyncIterator, Dict, Optional

import httpx
import yaml

from .config import (
    CALIBRATION_MIN_CONTEXT,
    LLAMACPP_CALIBRATION_PORT,
    LLAMACPP_HEALTH_TIMEOUT,
    VRAM_SAFETY_MARGIN,
)
from .formatting import format_number
from .gguf_utils import extract_quantization_from_filename, get_gguf_native_context
from .gpu_utils import get_gpu_memory_info
from .model_vram_cache import add_llamacpp_calibration

logger = logging.getLogger(__name__)


def parse_llamaswap_config(config_path: Path) -> Dict[str, Dict]:
    """
    Parse llama-swap YAML config and extract per-model info.

    Returns:
        Dict mapping model_id to:
        - gguf_path: path to GGUF file (from --model flag)
        - llama_server_bin: path to llama-server binary
        - current_context: current -c value
        - ngl: current -ngl value
        - full_cmd: the complete cmd string
    """
    if not config_path.exists():
        logger.warning(f"llama-swap config not found: {config_path}")
        return {}

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    if not config or "models" not in config:
        return {}

    result: Dict[str, Dict] = {}

    for model_id, model_config in config["models"].items():
        cmd = model_config.get("cmd", "")
        if not cmd:
            continue

        # Extract llama-server binary (first part of cmd)
        parts = cmd.split()
        llama_server_bin = parts[0] if parts else ""

        # Extract --model path
        gguf_path = ""
        for i, part in enumerate(parts):
            if part == "--model" and i + 1 < len(parts):
                gguf_path = parts[i + 1]
                break

        # Extract -c (context) value
        current_context = 0
        for i, part in enumerate(parts):
            if part == "-c" and i + 1 < len(parts):
                try:
                    current_context = int(parts[i + 1])
                except ValueError:
                    pass
                break

        # Extract -ngl value
        ngl = 99
        for i, part in enumerate(parts):
            if part == "-ngl" and i + 1 < len(parts):
                try:
                    ngl = int(parts[i + 1])
                except ValueError:
                    pass
                break

        result[model_id] = {
            "gguf_path": gguf_path,
            "llama_server_bin": llama_server_bin,
            "current_context": current_context,
            "ngl": ngl,
            "full_cmd": cmd,
        }

    return result


def update_llamaswap_context(
    config_path: Path,
    model_id: str,
    new_context: int
) -> bool:
    """
    Update the -c value in llama-swap YAML for a specific model.

    Reads the YAML, replaces -c XXXX in the cmd string, writes back.
    """
    if not config_path.exists():
        logger.error(f"llama-swap config not found: {config_path}")
        return False

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    if not config or "models" not in config:
        return False

    if model_id not in config["models"]:
        logger.error(f"Model {model_id} not found in llama-swap config")
        return False

    cmd = config["models"][model_id].get("cmd", "")

    # Remove ALL -c XXXX occurrences, then append single clean value
    cmd_without_c = re.sub(r'\s*-c\s+\d+', '', cmd)
    new_cmd = f"{cmd_without_c} -c {new_context}"

    config["models"][model_id]["cmd"] = new_cmd

    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

    logger.info(f"Updated llama-swap config: {model_id} → -c {new_context}")
    return True


async def _start_llama_server(
    llama_server_bin: Path,
    gguf_path: Path,
    context: int,
    port: int,
    ngl: int = 99
) -> Optional[subprocess.Popen]:
    """Start a llama-server process for calibration testing."""
    cmd = [
        str(llama_server_bin),
        "--port", str(port),
        "--model", str(gguf_path),
        "-ngl", str(ngl),
        "-c", str(context),
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
        )
        return process
    except Exception as e:
        logger.error(f"Failed to start llama-server: {e}")
        return None


async def _wait_for_health(
    port: int,
    timeout: float,
    process: subprocess.Popen
) -> bool:
    """Wait for llama-server health endpoint to respond."""
    url = f"http://localhost:{port}/health"
    start = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start) < timeout:
        # Check if process crashed
        if process.poll() is not None:
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=2.0)
                if response.status_code == 200:
                    return True
        except (httpx.RequestError, httpx.TimeoutException):
            pass

        await asyncio.sleep(1.0)

    return False


def _kill_process(process: subprocess.Popen) -> None:
    """Kill a llama-server process and wait for cleanup."""
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def _estimate_upper_bound(
    free_vram_mb: int,
    model_size_gb: float,
    native_context: int
) -> int:
    """
    Estimate upper bound for context based on available VRAM.

    After model weights are loaded, remaining VRAM is for KV cache.
    Uses conservative MB/token ratio for Q4 quantized KV cache.
    """
    model_size_mb = model_size_gb * 1024
    available_for_context_mb = free_vram_mb - model_size_mb - VRAM_SAFETY_MARGIN

    if available_for_context_mb <= 0:
        return CALIBRATION_MIN_CONTEXT

    # Conservative ratio: 0.15 MB/token for Q4 KV cache (FP16 KV)
    mb_per_token = 0.15
    vram_estimated = int(available_for_context_mb / mb_per_token)

    # Cap at native context
    return min(vram_estimated, native_context)


def _save_calibration(
    model_id: str,
    max_context: int,
    native_context: int,
    gguf_path: Path,
    quantization: str,
    model_size_gb: float,
) -> None:
    """Save calibration result to VRAM cache."""
    gpu_info = get_gpu_memory_info()
    gpu_model = gpu_info.get("gpu_model", "Unknown") if gpu_info else "Unknown"
    add_llamacpp_calibration(
        model_id=model_id,
        max_context=max_context,
        native_context=native_context,
        gguf_path=str(gguf_path),
        quantization=quantization,
        gpu_model=gpu_model,
        model_size_gb=model_size_gb,
    )


async def calibrate_llamacpp_model(
    model_id: str,
    gguf_path: Path,
    llama_server_bin: Path,
    port: int = LLAMACPP_CALIBRATION_PORT,
    ngl: int = 99
) -> AsyncIterator[str]:
    """
    Binary search calibration for a llama.cpp model.

    Algorithm matches Ollama calibration workflow:
    1. Upper bound = native_context (not VRAM estimate)
    2. Try native_context first (often fits for small models)
    3. If too large, binary search to 512-token precision
    4. VRAM estimate used as optimization hint only

    Async generator that yields progress messages.
    Final yield: "__RESULT__:{context}" or "__RESULT__:0:error"
    """
    # Step 1: Read GGUF metadata
    yield f"Reading GGUF metadata: {gguf_path.name}"

    native_context = get_gguf_native_context(gguf_path)
    if not native_context:
        yield "Could not read native context from GGUF metadata"
        yield "__RESULT__:0:error"
        return

    model_size_gb = gguf_path.stat().st_size / (1024 ** 3)
    quantization = extract_quantization_from_filename(gguf_path.name)

    yield (
        f"Model: {model_id} ({format_number(model_size_gb, 1)} GB, {quantization}), "
        f"native context: {format_number(native_context)}"
    )

    # Step 2: Check VRAM
    from aifred.backends.ollama import wait_for_vram_stable

    yield "Waiting for VRAM to stabilize..."
    stabilized, wait_time, free_vram = await wait_for_vram_stable(max_wait_seconds=15.0)
    yield f"Free VRAM: {format_number(free_vram)} MB"

    if free_vram < 1000:
        yield "Not enough VRAM (<1 GB free)"
        yield "__RESULT__:0:error"
        return

    # Step 3: Calculate search bounds
    # Upper bound = native_context (like Ollama), NOT VRAM estimate
    # VRAM estimate is only used as optimization hint
    vram_estimate = _estimate_upper_bound(free_vram, model_size_gb, native_context)
    low = CALIBRATION_MIN_CONTEXT
    high = native_context  # Absolute maximum = native context

    yield (
        f"Native context: {format_number(native_context)} | "
        f"VRAM estimate: {format_number(vram_estimate)}"
    )

    # Step 4: Try native_context first (like Ollama tries max_target first)
    iteration = 0
    iteration += 1
    yield f"[{iteration}] Testing native max: {format_number(native_context)}..."
    process = await _start_llama_server(
        llama_server_bin, gguf_path, native_context, port, ngl
    )
    if process:
        healthy = await _wait_for_health(port, LLAMACPP_HEALTH_TIMEOUT, process)
        _kill_process(process)
        await asyncio.sleep(1.0)

        if healthy:
            yield f"✓ Native context {format_number(native_context)} fits!"
            result = native_context
            _save_calibration(
                model_id, result, native_context,
                gguf_path, quantization, model_size_gb
            )
            yield f"__RESULT__:{result}"
            return
        else:
            yield f"✗ {format_number(native_context)} too large"

    # Step 5: Try VRAM estimate as optimization (skip to good range)
    if vram_estimate < native_context and vram_estimate > low:
        iteration += 1
        yield f"[{iteration}] Testing VRAM estimate: {format_number(vram_estimate)}..."
        process = await _start_llama_server(
            llama_server_bin, gguf_path, vram_estimate, port, ngl
        )
        if process:
            healthy = await _wait_for_health(port, LLAMACPP_HEALTH_TIMEOUT, process)
            _kill_process(process)
            await asyncio.sleep(1.0)

            if healthy:
                yield f"✓ {format_number(vram_estimate)} fits"
                # VRAM estimate fits → search ABOVE it for true maximum
                low = vram_estimate
                result = vram_estimate
            else:
                yield f"✗ {format_number(vram_estimate)} too large"
                high = vram_estimate
                result = low
        else:
            high = vram_estimate
            result = low
    else:
        result = low

    yield (
        f"Binary search: {format_number(low)} → {format_number(high)} "
        f"(precision: 512 tokens)"
    )

    # Step 6: Binary search (like Ollama: 512-token precision)
    while high - low > 512:
        iteration += 1
        mid = (low + high) // 2

        yield f"[{iteration}] Testing {format_number(mid)} (range: {format_number(low)}-{format_number(high)})..."

        process = await _start_llama_server(llama_server_bin, gguf_path, mid, port, ngl)
        if not process:
            yield "✗ Failed to start llama-server"
            high = mid
            continue

        healthy = await _wait_for_health(port, LLAMACPP_HEALTH_TIMEOUT, process)
        _kill_process(process)
        await asyncio.sleep(1.0)  # Let VRAM settle

        if healthy:
            result = mid
            low = mid
            yield f"✓ {format_number(mid)} fits"
        else:
            high = mid
            yield f"✗ {format_number(mid)} too large"

    # Step 7: Save result
    _save_calibration(
        model_id, result, native_context,
        gguf_path, quantization, model_size_gb
    )

    yield (
        f"Calibration complete: {format_number(result)} tokens "
        f"(native: {format_number(native_context)}, "
        f"{iteration} iterations)"
    )
    yield f"__RESULT__:{result}"
