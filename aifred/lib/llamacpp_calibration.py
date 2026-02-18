"""
llama.cpp Context & NGL Calibration via llama-swap

Two-phase calibration:
1. GPU-only: Binary search for max -c with -ngl 99 (all layers on GPU)
2. Hybrid: If GPU-only yields too little context, reduce -ngl to offload
   layers to CPU, freeing VRAM for KV cache (more context, slower inference)

Results are cached in model_vram_cache.json and written back to the
llama-swap YAML config (both -c and -ngl).
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
    MAX_SWAP_INCREASE_MB,
    MIN_FREE_RAM_MB,
    MIN_USEFUL_CONTEXT_TOKENS,
    VRAM_SAFETY_MARGIN,
)
from .formatting import format_number
from .gguf_utils import (
    extract_quantization_from_filename,
    get_gguf_layer_count,
    get_gguf_native_context,
)
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

    Uses regex on raw file content to preserve YAML formatting
    (PyYAML's dump() destroys quoting style and line breaks).
    """
    if not config_path.exists():
        logger.error(f"llama-swap config not found: {config_path}")
        return False

    # Check if model exists and if value already matches
    config = parse_llamaswap_config(config_path)
    model_info = config.get(model_id)
    if not model_info:
        logger.error(f"Model {model_id} not found in llama-swap config")
        return False

    if model_info["current_context"] == new_context:
        logger.info(f"llama-swap config already up to date: {model_id} -c {new_context}")
        return True

    content = config_path.read_text(encoding='utf-8')
    new_content = _replace_context_in_model_block(content, model_id, new_context)

    if new_content == content:
        logger.error(f"Could not replace -c value for {model_id} in config")
        return False

    config_path.write_text(new_content, encoding='utf-8')
    logger.info(f"Updated llama-swap config: {model_id} → -c {new_context}")
    return True


def _replace_context_in_model_block(content: str, model_id: str, new_context: int) -> str:
    """Replace -c value in a specific model's cmd block, preserving formatting."""
    lines = content.split('\n')
    in_model_block = False
    result_lines = []

    for line in lines:
        # Detect start of target model block (e.g., "  qwen3-30b-a3b:")
        if re.match(rf'^\s+{re.escape(model_id)}\s*:', line):
            in_model_block = True
        # Detect start of next model block (any other model key at same indent)
        elif in_model_block and re.match(r'^\s+\w', line) and not line.strip().startswith(('cmd:', 'ttl:', '-')):
            in_model_block = False

        if in_model_block:
            line = re.sub(r'-c\s+\d+', f'-c {new_context}', line)

        result_lines.append(line)

    return '\n'.join(result_lines)


def update_llamaswap_ngl(
    config_path: Path,
    model_id: str,
    new_ngl: int
) -> bool:
    """
    Update the -ngl value in llama-swap YAML for a specific model.

    Uses regex on raw file content to preserve YAML formatting.
    """
    if not config_path.exists():
        logger.error(f"llama-swap config not found: {config_path}")
        return False

    config = parse_llamaswap_config(config_path)
    model_info = config.get(model_id)
    if not model_info:
        logger.error(f"Model {model_id} not found in llama-swap config")
        return False

    if model_info["ngl"] == new_ngl:
        logger.info(f"llama-swap config already up to date: {model_id} -ngl {new_ngl}")
        return True

    content = config_path.read_text(encoding='utf-8')
    new_content = _replace_ngl_in_model_block(content, model_id, new_ngl)

    if new_content == content:
        logger.error(f"Could not replace -ngl value for {model_id} in config")
        return False

    config_path.write_text(new_content, encoding='utf-8')
    logger.info(f"Updated llama-swap config: {model_id} → -ngl {new_ngl}")
    return True


def _replace_ngl_in_model_block(content: str, model_id: str, new_ngl: int) -> str:
    """Replace -ngl value in a specific model's cmd block, preserving formatting."""
    lines = content.split('\n')
    in_model_block = False
    result_lines = []

    for line in lines:
        if re.match(rf'^\s+{re.escape(model_id)}\s*:', line):
            in_model_block = True
        elif in_model_block and re.match(r'^\s+\w', line) and not line.strip().startswith(('cmd:', 'ttl:', '-')):
            in_model_block = False

        if in_model_block:
            line = re.sub(r'-ngl\s+\d+', f'-ngl {new_ngl}', line)

        result_lines.append(line)

    return '\n'.join(result_lines)


async def _start_llama_server(
    full_cmd: str,
    context: int,
    port: int,
    ngl: Optional[int] = None,
) -> Optional[subprocess.Popen]:
    """Start a llama-server process using original llama-swap cmd.

    Replaces -c and --port/${PORT} in the original command,
    preserving all GPU flags (tensor-split, flash-attn, mlock etc.).
    Injects -np 1 and -fit off for stable calibration on Pascal GPUs.

    Args:
        ngl: If set, replaces -ngl value in cmd (for hybrid calibration)
    """
    import shlex

    # Replace ${PORT} placeholder and --port value
    cmd_str = full_cmd.replace("${PORT}", str(port))

    # Replace -c value with test context
    cmd_str = re.sub(r'(-c\s+)\d+', rf'\g<1>{context}', cmd_str)

    # Replace -ngl value for hybrid calibration
    if ngl is not None:
        cmd_str = re.sub(r'(-ngl\s+)\d+', rf'\g<1>{ngl}', cmd_str)

    # Inject calibration-safe flags if not already present
    # -np 1: single slot (auto defaults to 4, wastes VRAM)
    # -fit off: fitting routine crashes on Pascal with tight VRAM
    if '-np ' not in cmd_str:
        cmd_str = cmd_str.replace(' --port', ' -np 1 --port')
    if '-fit ' not in cmd_str:
        cmd_str = cmd_str.replace(' --port', ' -fit off --port')

    args = shlex.split(cmd_str)

    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
        )
        return process
    except Exception as e:
        logger.error(f"Failed to start llama-server: {e}")
        return None


async def _wait_for_ready(
    port: int,
    timeout: float,
    process: subprocess.Popen
) -> bool:
    """Wait for llama-server to be ready (health endpoint)."""
    url = f"http://localhost:{port}/health"
    start = asyncio.get_event_loop().time()

    while (asyncio.get_event_loop().time() - start) < timeout:
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


async def _test_inference(
    port: int,
    process: subprocess.Popen,
    timeout: float = 30.0,
) -> bool:
    """Test actual inference — health check alone is insufficient.

    On tight VRAM, the server starts and passes health checks but crashes
    on the first real request due to additional CUDA kernel allocations.
    """
    url = f"http://localhost:{port}/v1/chat/completions"
    payload = {
        "model": "test",
        "messages": [{"role": "user", "content": "say ok"}],
        "max_tokens": 2,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                # Verify we got actual content back
                choices = data.get("choices", [])
                if choices and choices[0].get("message", {}).get("content"):
                    return True
        return False
    except Exception:
        # Process may have crashed during inference
        return False


async def test_thinking_on_port(port: int) -> bool:
    """Test reasoning capability directly against a running llama-server.

    Used during calibration to avoid reloading the model through llama-swap.
    Checks if the model produces reasoning_content (OpenAI-compatible thinking).
    """
    url = f"http://localhost:{port}/v1/chat/completions"
    payload = {
        "model": "test",
        "messages": [{"role": "user", "content": "What is 2+3? Think step by step."}],
        "max_tokens": 200,
        "temperature": 0.6,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=30.0)
            if response.status_code != 200:
                return False
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                return False
            msg = choices[0].get("message", {})
            content = msg.get("content", "")
            reasoning = msg.get("reasoning_content", "")
            return bool(reasoning) or "<think>" in content
    except Exception:
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


async def _start_and_verify(
    full_cmd: str,
    context: int,
    port: int,
    ngl: Optional[int] = None,
) -> Optional[asyncio.subprocess.Process]:
    """Start server, verify it works via health check + inference, return process.

    Returns the running process on success (caller must kill it), or None on failure.
    Health check alone is insufficient: on tight VRAM, the server starts OK but
    crashes on the first real inference request due to additional CUDA kernel
    allocations. This function tests actual inference to confirm the context fits.
    """
    process = await _start_llama_server(full_cmd, context, port, ngl=ngl)
    if not process:
        return None

    try:
        ready = await _wait_for_ready(port, LLAMACPP_HEALTH_TIMEOUT, process)
        if not ready:
            _kill_process(process)
            await asyncio.sleep(1.5)
            return None

        if not await _test_inference(port, process):
            _kill_process(process)
            await asyncio.sleep(1.5)
            return None

        return process
    except BaseException:
        # GeneratorExit (async generator abandoned, e.g. double-click calibrate) or
        # CancelledError: process is orphaned if not cleaned up here — it would hold VRAM.
        _kill_process(process)
        raise


async def _calibration_test(
    full_cmd: str,
    context: int,
    port: int,
    ngl: Optional[int] = None,
) -> bool:
    """Full calibration test: start → verify → cleanup. Returns True if context fits."""
    process = await _start_and_verify(full_cmd, context, port, ngl=ngl)
    if not process:
        return False
    _kill_process(process)
    await asyncio.sleep(1.5)
    return True


def _get_model_block_bounds(content: str, model_id: str) -> tuple[int, int]:
    """Return (start_line, end_line) for a model's YAML block (end is exclusive).

    Returns (-1, -1) if model not found.
    """
    lines = content.split('\n')
    start = -1
    model_indent = 0

    for i, line in enumerate(lines):
        m = re.match(rf'^(\s+){re.escape(model_id)}\s*:', line)
        if m:
            start = i
            model_indent = len(m.group(1))
            break

    if start < 0:
        return -1, -1

    # End: next non-blank, non-comment line at same (or less) indentation
    for i in range(start + 1, len(lines)):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        current_indent = len(line) - len(line.lstrip())
        if current_indent <= model_indent:
            return start, i

    return start, len(lines)


def add_llamaswap_speed_variant(
    config_path: Path,
    model_id: str,
    speed_split_n: int,
    speed_context: int,
) -> bool:
    """
    Add (or update) a -speed variant YAML entry in the llama-swap config.

    Copies the existing model_id block, renames it to model_id-speed,
    and replaces tensor-split and -c with speed values.
    Preserves all other YAML formatting from the original block.

    Args:
        speed_split_n: Fast-GPU part of N:1 split (e.g. 10 → "10,1")
        speed_context: Context size for speed variant (typically MIN_USEFUL_CONTEXT_TOKENS)
    """
    if not config_path.exists():
        logger.error(f"llama-swap config not found: {config_path}")
        return False

    content = config_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    # Find original model block
    orig_start, orig_end = _get_model_block_bounds(content, model_id)
    if orig_start < 0:
        logger.error(f"Model {model_id} not found in llama-swap config")
        return False

    orig_block_lines = lines[orig_start:orig_end]

    # Trim trailing blank lines and section comments so they don't get duplicated
    while orig_block_lines and (
        not orig_block_lines[-1].strip()
        or orig_block_lines[-1].strip().startswith('#')
    ):
        orig_block_lines.pop()

    # Build speed block by modifying the original block's text
    speed_model_id = f"{model_id}-speed"
    speed_block_text = '\n'.join(orig_block_lines)

    # Rename: replace only the model key (first occurrence)
    speed_block_text = re.sub(
        rf'^(\s+){re.escape(model_id)}\s*:',
        rf'\g<1>{speed_model_id}:',
        speed_block_text,
        count=1,
        flags=re.MULTILINE,
    )

    # Replace tensor-split and context in cmd
    speed_block_text = _replace_tensor_split(speed_block_text, speed_split_n, 1)
    speed_block_text = re.sub(r'-c\s+\d+', f'-c {speed_context}', speed_block_text)

    speed_block_lines = speed_block_text.split('\n')

    # Check if speed variant already exists — update it in-place
    speed_start, speed_end = _get_model_block_bounds(content, speed_model_id)
    if speed_start >= 0:
        new_lines = lines[:speed_start] + speed_block_lines + lines[speed_end:]
        config_path.write_text('\n'.join(new_lines), encoding='utf-8')
        logger.info(f"Updated speed variant in llama-swap config: {speed_model_id}")
    else:
        # Insert right after the original block
        new_lines = lines[:orig_end] + speed_block_lines + lines[orig_end:]
        config_path.write_text('\n'.join(new_lines), encoding='utf-8')
        logger.info(f"Added speed variant to llama-swap config: {speed_model_id}")

    return True


def _has_tensor_split(full_cmd: str) -> bool:
    """Return True if the cmd uses multi-GPU tensor split."""
    return bool(re.search(r'(--tensor-split|-ts)\s+[\d.,]+', full_cmd))


def _replace_tensor_split(cmd: str, fast_n: int, slow_n: int = 1) -> str:
    """Replace the tensor-split ratio in cmd with fast_n:slow_n."""
    new_val = f"{fast_n},{slow_n}"
    cmd = re.sub(r'(--tensor-split\s+)[\d.,]+', rf'\g<1>{new_val}', cmd)
    cmd = re.sub(r'(-ts\s+)[\d.,]+', rf'\g<1>{new_val}', cmd)
    return cmd


async def _calibrate_speed_split(
    full_cmd: str,
    port: int,
    target_context: int,
) -> AsyncIterator[str]:
    """
    Binary search for the most aggressive tensor-split ratio at target_context.

    Searches N from 99 downward (N:1 split), finds the highest N where the model
    loads successfully at target_context tokens. Starts from 99 (most aggressive),
    mirroring how context calibration starts from native_context.

    Yields progress messages.
    Final: "__SPEED__:{N}" where N is the best ratio, or "__SPEED__:0" on failure.
    """
    yield f"Speed calibration: binary search tensor-split at ctx={format_number(target_context)}"

    iteration = 0

    # Test 99:1 first — best case, avoids unnecessary search
    iteration += 1
    cmd_99 = _replace_tensor_split(full_cmd, 99, 1)
    yield f"[{iteration}] Testing split 99:1..."
    fits = await _calibration_test(cmd_99, target_context, port)
    if fits:
        yield "✓ 99:1 fits — best possible split"
        yield "__SPEED__:99"
        return

    yield "✗ 99:1 failed, binary search..."

    # Binary search [2, 98] — find highest N:1 that still loads
    split_low = 2
    split_high = 98
    best_n = 0

    while split_high - split_low > 1:
        iteration += 1
        split_mid = (split_low + split_high) // 2
        cmd_mid = _replace_tensor_split(full_cmd, split_mid, 1)
        yield f"[{iteration}] Testing split {split_mid}:1..."

        fits = await _calibration_test(cmd_mid, target_context, port)
        if fits:
            best_n = split_mid
            split_low = split_mid
            yield f"✓ {split_mid}:1 fits"
        else:
            split_high = split_mid
            yield f"✗ {split_mid}:1 failed"

    # Binary search leaves split_low untested when all higher values fail — check it explicitly
    if best_n == 0:
        iteration += 1
        cmd_low = _replace_tensor_split(full_cmd, split_low, 1)
        yield f"[{iteration}] Testing split {split_low}:1 (lower bound)..."
        fits = await _calibration_test(cmd_low, target_context, port)
        if fits:
            best_n = split_low
            yield f"✓ {split_low}:1 fits"
        else:
            yield f"✗ {split_low}:1 failed"

    if best_n > 0:
        yield f"Speed split found: {best_n}:1 ({iteration} iterations)"
        yield f"__SPEED__:{best_n}"
    else:
        yield "Speed calibration failed: no tensor-split above 1:1 works at speed context"
        yield "__SPEED__:0"


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

    # Conservative ratio based on P40 benchmarks (2026-02-17):
    # Q8 KV + FA: ~0.08 MiB/token (4B: 0.075, 30B: 0.050)
    # FP16 KV: ~0.14 MiB/token (4B: 0.141, 30B: 0.094)
    # Use 0.08 as default (Q8 KV is now standard in llama-swap config)
    mb_per_token = 0.08
    vram_estimated = int(available_for_context_mb / mb_per_token)

    # Cap at native context
    return min(vram_estimated, native_context)


def _estimate_ngl_for_context(
    total_layers: int,
    model_size_gb: float,
    free_vram_mb: int,
    target_context: int,
    mb_per_token: float = 0.08,
) -> int:
    """
    Estimate NGL (GPU layers) needed to fit target_context in VRAM.

    Calculates how many layers can stay on GPU while leaving enough
    VRAM for KV cache at the target context size.

    Formula:
        vram_for_kv = target_context * mb_per_token
        vram_for_weights = free_vram - vram_for_kv - safety_margin
        ngl = vram_for_weights / vram_per_layer
    """
    model_size_mb = model_size_gb * 1024
    vram_per_layer = model_size_mb / total_layers
    vram_for_kv = target_context * mb_per_token
    vram_for_weights = free_vram_mb - vram_for_kv - VRAM_SAFETY_MARGIN

    if vram_for_weights <= 0:
        return 1

    ngl = int(vram_for_weights / vram_per_layer)
    return max(1, min(ngl, total_layers))


async def _calibrate_hybrid(
    model_id: str,
    gguf_path: Path,
    full_cmd: str,
    native_context: int,
    model_size_gb: float,
    quantization: str,
    total_layers: int,
    free_vram_mb: int,
    port: int,
) -> AsyncIterator[str]:
    """
    Hybrid NGL+context calibration for oversized models.

    Algorithm:
    1. Build descending list of context targets (native → 128K → 64K → 32K)
    2. For each target: estimate NGL via VRAM formula, verify empirically
    3. Once a working (ngl, context) pair is found: binary search context upward
    4. Monitor RAM+swap throughout (CPU layers consume RAM)
    5. Final yield: "__RESULT__:{context}:{ngl}:hybrid" or "__RESULT__:0:0:error"
    """
    from .gpu_utils import get_free_ram_mb, get_swap_used_mb

    yield f"Hybrid calibration: {total_layers} layers, {format_number(model_size_gb, 1)} GB model"

    # Build descending context targets
    context_targets = []
    if native_context > 131072:
        context_targets.append(native_context)
        context_targets.append(131072)
    elif native_context > 65536:
        context_targets.append(native_context)
        context_targets.append(65536)
    else:
        context_targets.append(native_context)
    if native_context > 32768:
        context_targets.append(32768)
    # Absolute minimum
    context_targets.append(16384)
    # Deduplicate while preserving order
    seen: set[int] = set()
    context_targets = [c for c in context_targets if not (c in seen or seen.add(c))]

    best_ngl: Optional[int] = None
    best_ctx: Optional[int] = None
    iteration = 0

    for target_ctx in context_targets:
        estimated_ngl = _estimate_ngl_for_context(
            total_layers, model_size_gb, free_vram_mb, target_ctx
        )

        # Check RAM feasibility (CPU layers need RAM)
        cpu_layers = total_layers - estimated_ngl
        vram_per_layer = model_size_gb * 1024 / total_layers
        ram_for_cpu_layers = cpu_layers * vram_per_layer
        free_ram = get_free_ram_mb()

        if free_ram and (free_ram - ram_for_cpu_layers) < MIN_FREE_RAM_MB:
            yield (
                f"Skip ctx={format_number(target_ctx)}: "
                f"not enough RAM for {cpu_layers} CPU layers "
                f"({format_number(int(ram_for_cpu_layers))} MB needed, "
                f"{format_number(free_ram)} MB free)"
            )
            continue

        if estimated_ngl < 1:
            yield f"Skip ctx={format_number(target_ctx)}: would need ngl<1"
            continue

        iteration += 1
        yield (
            f"[{iteration}] Testing ngl={estimated_ngl} "
            f"({cpu_layers} CPU layers), ctx={format_number(target_ctx)}..."
        )

        swap_before = get_swap_used_mb()
        fits = await _calibration_test(full_cmd, target_ctx, port, ngl=estimated_ngl)

        if fits:
            # Check RAM and swap after load
            ram_after = get_free_ram_mb()
            swap_after = get_swap_used_mb()
            swap_increase = 0
            if swap_before is not None and swap_after is not None:
                swap_increase = max(0, swap_after - swap_before)

            ram_ok = ram_after is not None and ram_after >= MIN_FREE_RAM_MB
            swap_ok = swap_increase <= MAX_SWAP_INCREASE_MB

            if ram_ok and swap_ok:
                best_ngl = estimated_ngl
                best_ctx = target_ctx
                ram_str = format_number(ram_after) if ram_after else "N/A"
                yield (
                    f"✓ ngl={estimated_ngl}, ctx={format_number(target_ctx)} fits "
                    f"({ram_str} MB free, +{format_number(swap_increase)} MB swap)"
                )
                break
            elif not swap_ok:
                yield (
                    f"✗ ngl={estimated_ngl}, ctx={format_number(target_ctx)} "
                    f"causes swapping (+{format_number(swap_increase)} MB)"
                )
            else:
                ram_str = format_number(ram_after) if ram_after else "N/A"
                yield (
                    f"✗ ngl={estimated_ngl}, ctx={format_number(target_ctx)} "
                    f"RAM insufficient ({ram_str} MB < {format_number(MIN_FREE_RAM_MB)} MB)"
                )
        else:
            yield f"✗ ngl={estimated_ngl}, ctx={format_number(target_ctx)} failed to start"

            # NGL estimate was too aggressive → binary search NGL downward
            yield f"Binary searching NGL for ctx={format_number(target_ctx)}..."
            ngl_low = 1
            ngl_high = estimated_ngl
            ngl_result = 0

            while ngl_high - ngl_low > 2:
                ngl_mid = (ngl_low + ngl_high) // 2
                iteration += 1
                cpu_mid = total_layers - ngl_mid
                yield f"[{iteration}] Testing ngl={ngl_mid} ({cpu_mid} CPU layers)..."

                swap_before = get_swap_used_mb()
                fits = await _calibration_test(full_cmd, target_ctx, port, ngl=ngl_mid)

                if fits:
                    ram_after = get_free_ram_mb()
                    swap_after = get_swap_used_mb()
                    swap_increase = 0
                    if swap_before is not None and swap_after is not None:
                        swap_increase = max(0, swap_after - swap_before)

                    ram_ok = ram_after is not None and ram_after >= MIN_FREE_RAM_MB
                    swap_ok = swap_increase <= MAX_SWAP_INCREASE_MB

                    if ram_ok and swap_ok:
                        ngl_result = ngl_mid
                        ngl_low = ngl_mid
                        yield f"✓ ngl={ngl_mid} fits"
                    else:
                        ngl_high = ngl_mid
                        yield f"✗ ngl={ngl_mid} memory issues"
                else:
                    ngl_high = ngl_mid
                    yield f"✗ ngl={ngl_mid} failed"

            if ngl_result > 0:
                best_ngl = ngl_result
                best_ctx = target_ctx
                break

    if best_ngl is None or best_ctx is None:
        yield "Hybrid calibration failed: no working (ngl, context) combination found"
        yield "__RESULT__:0:0:error"
        return

    # Phase 2: Binary search context upward at the found NGL
    yield (
        f"NGL={best_ngl} found. Binary searching context upward "
        f"from {format_number(best_ctx)}..."
    )

    ctx_low = best_ctx
    ctx_high = native_context

    while ctx_high - ctx_low > 512:
        ctx_mid = (ctx_low + ctx_high) // 2
        iteration += 1
        yield f"[{iteration}] Testing ctx={format_number(ctx_mid)} at ngl={best_ngl}..."

        swap_before = get_swap_used_mb()
        fits = await _calibration_test(full_cmd, ctx_mid, port, ngl=best_ngl)

        if fits:
            ram_after = get_free_ram_mb()
            swap_after = get_swap_used_mb()
            swap_increase = 0
            if swap_before is not None and swap_after is not None:
                swap_increase = max(0, swap_after - swap_before)

            ram_ok = ram_after is not None and ram_after >= MIN_FREE_RAM_MB
            swap_ok = swap_increase <= MAX_SWAP_INCREASE_MB

            if ram_ok and swap_ok:
                ctx_low = ctx_mid
                best_ctx = ctx_mid
                yield f"✓ ctx={format_number(ctx_mid)} fits"
            else:
                ctx_high = ctx_mid
                yield f"✗ ctx={format_number(ctx_mid)} memory issues"
        else:
            ctx_high = ctx_mid
            yield f"✗ ctx={format_number(ctx_mid)} too large"

    yield (
        f"Hybrid calibration complete: ngl={best_ngl}, "
        f"ctx={format_number(best_ctx)} tokens "
        f"({total_layers - best_ngl} layers on CPU, {iteration} iterations)"
    )
    # Signal result to caller (not __RESULT__ — caller handles _finish_calibration)
    yield f"__HYBRID__:{best_ctx}:{best_ngl}"


def _save_calibration(
    model_id: str,
    max_context: int,
    native_context: int,
    gguf_path: Path,
    quantization: str,
    model_size_gb: float,
    ngl: int = 99,
    mode: str = "gpu",
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
        ngl=ngl,
        mode=mode,
    )


async def calibrate_llamacpp_model(
    model_id: str,
    gguf_path: Path,
    full_cmd: str,
    port: int = LLAMACPP_CALIBRATION_PORT,
) -> AsyncIterator[str]:
    """
    Two-phase calibration for a llama.cpp model.

    Phase 1 (GPU-only): Binary search for max -c with ngl=99
    Phase 2 (Speed): Tensor-split optimization for multi-GPU (if Phase 1 succeeds)
    Phase 3 (Hybrid): CPU-offload fallback if GPU-only context < MIN_USEFUL_CONTEXT

    Async generator that yields progress messages.
    Final yield format: "__RESULT__:{context}:{ngl}:{mode}"
      mode: "gpu" or "hybrid"
      Example: "__RESULT__:222960:99:gpu" or "__RESULT__:131072:28:hybrid"
    Error: "__RESULT__:0:0:error"
    """
    # Step 1: Read GGUF metadata
    yield f"Reading GGUF metadata: {gguf_path.name}"

    native_context = get_gguf_native_context(gguf_path)
    if not native_context:
        yield "Could not read native context from GGUF metadata"
        yield "__RESULT__:0:0:error"
        return

    from .gguf_utils import get_gguf_total_size
    model_size_gb = get_gguf_total_size(gguf_path) / (1024 ** 3)
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
        yield "__RESULT__:0:0:error"
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

    # Helper: test thinking on running server (or start new one), yield result
    async def _finish_calibration(
        ctx: int, ngl: int, mode: str,
        process: Optional[asyncio.subprocess.Process] = None,
    ):
        """Test thinking on server, save calibration, emit result.

        If process is provided, reuses the already-running server (avoids reload).
        Otherwise starts a new server for the thinking test.
        """
        _save_calibration(
            model_id, ctx, native_context,
            gguf_path, quantization, model_size_gb,
            ngl=ngl, mode=mode
        )
        # Reuse existing server or start a new one
        if not process:
            process = await _start_and_verify(full_cmd, ctx, port, ngl=ngl if ngl != 99 else None)
        thinks = False
        if process:
            yield "Testing reasoning capability..."
            thinks = await test_thinking_on_port(port)
            _kill_process(process)
            await asyncio.sleep(1.5)
        yield f"__RESULT__:{ctx}:{ngl}:{mode}:{'thinks' if thinks else 'nothink'}"

    # === PHASE 1: GPU-only calibration (ngl=99) ===
    yield "Phase 1: GPU-only calibration (ngl=99)"

    # Step 4: Try native_context first (like Ollama tries max_target first)
    iteration = 0
    iteration += 1
    yield f"[{iteration}] Testing native max: {format_number(native_context)}..."
    process = await _start_and_verify(full_cmd, native_context, port)
    if process:
        yield f"✓ Native context {format_number(native_context)} fits!"
        if _has_tensor_split(full_cmd):
            # Speed calibration starts its own server on the same port — kill first
            _kill_process(process)
            await asyncio.sleep(1.5)
            process = None
            yield "Phase 2: Speed variant calibration (tensor-split optimization)"
            async for msg in _calibrate_speed_split(full_cmd, port, MIN_USEFUL_CONTEXT_TOKENS):
                yield msg
        # process=None here → _finish_calibration starts a fresh server for thinking test
        async for msg in _finish_calibration(native_context, 99, "gpu", process=process):
            yield msg
        return
    else:
        yield f"✗ {format_number(native_context)} too large"

    # Step 5: Try VRAM estimate as optimization (skip to good range)
    if vram_estimate < native_context and vram_estimate > low:
        iteration += 1
        yield f"[{iteration}] Testing VRAM estimate: {format_number(vram_estimate)}..."
        fits = await _calibration_test(full_cmd, vram_estimate, port)
        if fits:
            yield f"✓ {format_number(vram_estimate)} fits"
            low = vram_estimate
            result = vram_estimate
        else:
            yield f"✗ {format_number(vram_estimate)} too large"
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

        fits = await _calibration_test(full_cmd, mid, port)
        if fits:
            result = mid
            low = mid
            yield f"✓ {format_number(mid)} fits"
        else:
            high = mid
            yield f"✗ {format_number(mid)} too large"

    # === PHASE 3: Hybrid calibration (fallback if GPU-only context too small) ===
    if result < MIN_USEFUL_CONTEXT_TOKENS:
        yield (
            f"GPU-only context ({format_number(result)}) < "
            f"minimum useful ({format_number(MIN_USEFUL_CONTEXT_TOKENS)})"
        )

        total_layers = get_gguf_layer_count(gguf_path)
        if not total_layers:
            yield "Cannot read layer count from GGUF — hybrid mode unavailable"
        else:
            yield f"Phase 3: Hybrid calibration (fallback, {total_layers} layers)"

            # Re-measure VRAM (should be free after GPU-only tests)
            stabilized, wait_time, free_vram = await wait_for_vram_stable(
                max_wait_seconds=10.0
            )

            hybrid_ctx = None
            hybrid_ngl = None
            async for hybrid_msg in _calibrate_hybrid(
                model_id=model_id,
                gguf_path=gguf_path,
                full_cmd=full_cmd,
                native_context=native_context,
                model_size_gb=model_size_gb,
                quantization=quantization,
                total_layers=total_layers,
                free_vram_mb=free_vram,
                port=port,
            ):
                if hybrid_msg.startswith("__HYBRID__:"):
                    parts = hybrid_msg.split(":")
                    hybrid_ctx = int(parts[1])
                    hybrid_ngl = int(parts[2])
                else:
                    yield hybrid_msg

            if hybrid_ctx and hybrid_ngl:
                async for msg in _finish_calibration(hybrid_ctx, hybrid_ngl, "hybrid"):
                    yield msg
                return

    # === PHASE 2: Speed variant calibration (multi-GPU only) ===
    if _has_tensor_split(full_cmd):
        yield "Phase 2: Speed variant calibration (tensor-split optimization)"
        async for msg in _calibrate_speed_split(full_cmd, port, MIN_USEFUL_CONTEXT_TOKENS):
            yield msg

    # Step 7: Final test with thinking check
    yield (
        f"Calibration complete: {format_number(result)} tokens "
        f"(native: {format_number(native_context)}, "
        f"{iteration} iterations)"
    )
    async for msg in _finish_calibration(result, 99, "gpu"):
        yield msg
