"""
llama.cpp Context & NGL Calibration via llama-swap

Projection-based calibration using llama-fit-params for exact VRAM estimation:
1. GPU-only: VRAM projection (0.3s each) → calculate max context → verify with server
2. Speed: Tensor-split optimization for multi-GPU setups
3. Hybrid: If GPU-only yields too little context, reduce -ngl to offload
   layers to CPU, freeing VRAM for KV cache (more context, slower inference)

Results are cached in model_vram_cache.json and written back to the
llama-swap YAML config (both -c and -ngl).
"""

import asyncio
import logging
import re
import shlex
import signal
import os
import subprocess
import tempfile
from pathlib import Path
from typing import AsyncIterator, Dict, Optional

import httpx
import yaml

from .config import (
    CALIBRATION_MIN_CONTEXT,
    KV_QUANT_CONTEXT_THRESHOLD,
    LLAMACPP_CALIBRATION_PORT,
    LLAMACPP_HEALTH_TIMEOUT,
    LLAMACPP_VRAM_SAFETY_MARGIN,
    MIN_FREE_RAM_MB,
    MIN_USEFUL_CONTEXT_TOKENS,
)
from .formatting import format_number
from .logging_utils import log_message
from .gguf_utils import (
    extract_quantization_from_filename,
    get_gguf_layer_count,
    get_gguf_native_context,
)
from .gpu_utils import get_all_gpus_memory_info
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

    if not config or not config.get("models"):
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

        # Extract -ctk (KV cache key quantization)
        kv_cache_quant = ""
        for i, part in enumerate(parts):
            if part == "-ctk" and i + 1 < len(parts):
                kv_cache_quant = parts[i + 1]
                break

        result[model_id] = {
            "gguf_path": gguf_path,
            "llama_server_bin": llama_server_bin,
            "current_context": current_context,
            "ngl": ngl,
            "kv_cache_quant": kv_cache_quant,
            "full_cmd": cmd,
        }

    return result


def parse_sampling_from_cmd(cmd: str) -> Dict[str, float]:
    """
    Extract sampling parameters from a llama-server cmd string.

    Returns only explicitly set values. Missing params = not in dict.
    Mapping: --temp → temperature, --top-k → top_k, --top-p → top_p, etc.
    """
    flag_map = {
        "--temp": "temperature",
        "--top-k": "top_k",
        "--top-p": "top_p",
        "--min-p": "min_p",
        "--repeat-penalty": "repeat_penalty",
    }
    parts = cmd.split()
    result: Dict[str, float] = {}
    for i, part in enumerate(parts):
        if part in flag_map and i + 1 < len(parts):
            try:
                result[flag_map[part]] = float(parts[i + 1])
            except ValueError:
                pass
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


def _replace_flash_attn_in_model_block(content: str, model_id: str, enabled: bool) -> str:
    """Set --flash-attn on/off in a specific model's cmd block, preserving formatting."""
    new_val = "on" if enabled else "off"
    lines = content.split('\n')
    in_model_block = False
    result_lines = []

    for line in lines:
        if re.match(rf'^\s+{re.escape(model_id)}\s*:', line):
            in_model_block = True
        elif in_model_block and re.match(r'^\s+\w', line) and not line.strip().startswith(('cmd:', 'ttl:', '-')):
            in_model_block = False

        if in_model_block:
            line = re.sub(r'--flash-attn\s+\w+', f'--flash-attn {new_val}', line)

        result_lines.append(line)

    return '\n'.join(result_lines)


def update_llamaswap_flash_attn(
    config_path: Path,
    model_id: str,
    enabled: bool = False,
) -> bool:
    """
    Update --flash-attn flag in llama-swap YAML for a specific model.

    Uses regex on raw file content to preserve YAML formatting.
    Called with enabled=False when architecture incompatibility is detected during calibration.
    """
    if not config_path.exists():
        logger.error(f"llama-swap config not found: {config_path}")
        return False

    content = config_path.read_text(encoding='utf-8')
    new_content = _replace_flash_attn_in_model_block(content, model_id, enabled)

    if new_content == content:
        logger.warning(f"--flash-attn flag not found for {model_id} in llama-swap config")
        return False

    config_path.write_text(new_content, encoding='utf-8')
    logger.info(f"Updated llama-swap config: {model_id} → --flash-attn {'on' if enabled else 'off'}")
    return True


def update_llamaswap_kv_cache_quant(
    config_path: Path,
    model_id: str,
    kv_quant: str,
) -> bool:
    """Update or insert -ctk/-ctv quantization in llama-swap YAML for a specific model.

    Replaces existing -ctk/-ctv values or inserts them before --port if absent.
    Returns True if the config was modified.
    """
    if not config_path.exists():
        logger.error(f"llama-swap config not found: {config_path}")
        return False

    content = config_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    in_model_block = False
    changed = False
    result_lines = []

    for line in lines:
        if re.match(rf'^\s+{re.escape(model_id)}\s*:', line):
            in_model_block = True
        elif in_model_block and re.match(r'^\s+\w', line) and not line.strip().startswith(('cmd:', 'ttl:', '-')):
            in_model_block = False

        if in_model_block and 'cmd:' in line:
            if '-ctk ' in line:
                line = re.sub(r'-ctk\s+\S+', f'-ctk {kv_quant}', line)
                changed = True
            else:
                line = line.replace(' --port', f' -ctk {kv_quant} --port')
                changed = True
            if '-ctv ' in line:
                line = re.sub(r'-ctv\s+\S+', f'-ctv {kv_quant}', line)
            else:
                line = line.replace(' --port', f' -ctv {kv_quant} --port')

        result_lines.append(line)

    if not changed:
        return False

    config_path.write_text('\n'.join(result_lines), encoding='utf-8')
    logger.info(f"Updated llama-swap config: {model_id} → KV cache {kv_quant}")
    return True


def _remove_llamaswap_kv_cache_quant(config_path: Path, model_id: str) -> bool:
    """Remove -ctk/-ctv flags from llama-swap YAML for a specific model.

    Used when calibration determines f16 KV is optimal (no quantization needed).
    """
    if not config_path.exists():
        return False

    content = config_path.read_text(encoding='utf-8')
    lines = content.split('\n')
    in_model_block = False
    changed = False
    result_lines = []

    for line in lines:
        if re.match(rf'^\s+{re.escape(model_id)}\s*:', line):
            in_model_block = True
        elif in_model_block and re.match(r'^\s+\w', line) and not line.strip().startswith(('cmd:', 'ttl:', '-')):
            in_model_block = False

        if in_model_block:
            new_line = re.sub(r'\s*-ctk\s+\S+', '', line)
            new_line = re.sub(r'\s*-ctv\s+\S+', '', new_line)
            if new_line != line:
                changed = True
            line = new_line

        result_lines.append(line)

    if not changed:
        return False

    config_path.write_text('\n'.join(result_lines), encoding='utf-8')
    logger.info(f"Removed KV cache quant from llama-swap config: {model_id}")
    return True


def _read_server_log(process: subprocess.Popen) -> str:
    """Read output from the server's log file (replaces stdout pipe reading)."""
    log_path = getattr(process, '_server_log', None)
    if not log_path:
        return ""
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except OSError:
        return ""



def _parse_memory_breakdown(
    log_path: str,
) -> Optional[Dict[str, Dict[str, int]]]:
    """Parse llama_memory_breakdown_print from server exit log.

    This line is printed when llama-server exits and gives physical VRAM totals:
        llama_memory_breakdown_print: |   - CUDA0 (RTX 3090 Ti) | 24563 = 1886 + (18233 = 17524 +     408 +     300) +        4444 |
    Format: | GPU_NAME | total = free + (self = model + context + compute) + unaccounted |

    Returns dict per GPU: {"CUDA0": {"total": 24563, "free": 1886, "self": 18233}}
    Returns None if breakdown not found (server didn't exit cleanly, old llama.cpp build).
    """
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError:
        return None

    result: Dict[str, Dict[str, int]] = {}
    # Match CUDA GPU lines from breakdown:
    #   |   - CUDA0 (RTX 3090 Ti) | 24563 = 1886 + (18233 = 17524 + ...
    for match in re.finditer(
        r'llama_memory_breakdown_print:\s*\|\s+-\s+(CUDA\d+)\s+\([^)]+\)\s*\|\s*'
        r'(\d+)\s*=\s*(\d+)\s*\+\s*\(\s*(\d+)',
        content,
    ):
        gpu_id = match.group(1)
        result[gpu_id] = {
            "total": int(match.group(2)),
            "free": int(match.group(3)),
            "self": int(match.group(4)),
        }

    return result if result else None


def _measure_process_ram_mb(pid: int) -> Optional[int]:
    """Read physical RAM usage (VmRSS) from /proc/<pid>/status.

    Returns RSS in MB, or None if unreadable.
    """
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    # Format: "VmRSS:   21045632 kB"
                    kb = int(line.split()[1])
                    return kb // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _check_vram_physical_fit(log_path: str) -> Optional[tuple[bool, str]]:
    """Check if enough physical VRAM remains free after allocation.

    Parses llama_memory_breakdown_print (written at server exit).
    Checks that free VRAM >= LLAMACPP_VRAM_SAFETY_MARGIN per GPU.

    On Ampere+ GPUs, CUDA VMM can silently swap to system RAM when physical
    VRAM is exhausted — self <= total passes but inference slows down 7x.
    Checking 'free' catches this: if free < safety margin, unaccounted memory
    (CUDA runtime, display, driver ~4 GB) is being displaced via VMM.

    Returns:
        (fits, detail_msg) — fits=True if all GPUs have free >= LLAMACPP_VRAM_SAFETY_MARGIN,
        fits=False if free VRAM too low.
        None if breakdown unavailable (old build, unclean exit).
    """
    breakdown = _parse_memory_breakdown(log_path)
    if not breakdown:
        return None

    for gpu_id, info in breakdown.items():
        if info["free"] < LLAMACPP_VRAM_SAFETY_MARGIN:
            return (
                False,
                f"{gpu_id}: {info['free']} MB free < {LLAMACPP_VRAM_SAFETY_MARGIN} MB minimum "
                f"(self={info['self']} MB, total={info['total']} MB)",
            )
    return (True, "")


def _get_fit_params_binary(full_cmd: str) -> Path:
    """Derive llama-fit-params binary path from llama-server command.

    Both binaries are built in the same CMake build directory.
    """
    server_bin = shlex.split(full_cmd)[0]
    return Path(server_bin).parent / "llama-fit-params"


# GPU-relevant flags that affect VRAM projection.
# These must be forwarded to llama-fit-params for accurate results.
_GPU_FLAGS = {
    "-ngl", "--flash-attn", "-ctk", "-ctv",
    "-ts", "--tensor-split", "-sm", "--split-mode",
    "-np", "-ub", "-b",
}


def _build_fit_params_cmd(
    full_cmd: str, gguf_path: Path, context: int, ngl: Optional[int] = None,
) -> list[str]:
    """Build llama-fit-params command from llama-server command.

    Extracts only GPU-relevant flags (that affect VRAM usage).
    Omits port, threads, mlock, fit — fit-params runs its own fitting.

    Args:
        ngl: If set, overrides -ngl from full_cmd.
    """
    fit_bin = str(_get_fit_params_binary(full_cmd))
    cmd = [fit_bin, "--model", str(gguf_path), "-c", str(context)]

    parts = shlex.split(full_cmd)
    i = 1  # skip binary path
    while i < len(parts):
        if parts[i] in _GPU_FLAGS and i + 1 < len(parts):
            if ngl is not None and parts[i] == "-ngl":
                i += 2
                continue
            cmd.extend([parts[i], parts[i + 1]])
            i += 2
        else:
            i += 1

    if ngl is not None:
        cmd.extend(["-ngl", str(ngl)])

    return cmd


def _calculate_max_context_per_gpu(
    per_gpu_low: dict[str, dict[str, int]],
    per_gpu_high: dict[str, dict[str, int]],
    ctx_low: int,
    ctx_high: int,
) -> tuple[int, float]:
    """Calculate maximum context from per-GPU VRAM projections (multi-GPU aware).

    For each GPU independently:
      gpu_rate = (used_high - used_low) / (ctx_high - ctx_low)
      max_ctx  = ctx_low + (free_at_ctx_low - SAFETY_MARGIN) / gpu_rate

    The bottleneck GPU (lowest max_ctx) determines the overall limit.
    This avoids the overestimate of combined VRAM calculations where
    a larger GPU masks the bottleneck of a smaller one.

    Returns:
        (max_context, combined_rate) where combined_rate is total MiB per token.
    """
    gpu_limits: list[tuple[str, int, int]] = []  # (gpu_id, max_ctx, free_at_low)
    combined_rate = 0.0

    for gpu_id in sorted(per_gpu_low):
        if gpu_id not in per_gpu_high:
            continue

        free_low = per_gpu_low[gpu_id]["free"]
        used_low = per_gpu_low[gpu_id]["used"]
        used_high = per_gpu_high[gpu_id]["used"]

        gpu_rate = (used_high - used_low) / (ctx_high - ctx_low)
        combined_rate += gpu_rate

        if gpu_rate <= 0:
            gpu_limits.append((gpu_id, CALIBRATION_MIN_CONTEXT, free_low))
            continue

        headroom = free_low - LLAMACPP_VRAM_SAFETY_MARGIN
        if headroom <= 0:
            gpu_limits.append((gpu_id, CALIBRATION_MIN_CONTEXT, free_low))
            continue

        gpu_max = ctx_low + int(headroom / gpu_rate)
        gpu_limits.append((gpu_id, max(gpu_max, CALIBRATION_MIN_CONTEXT), free_low))

    if not gpu_limits:
        return CALIBRATION_MIN_CONTEXT, combined_rate

    # Bottleneck GPU determines overall max
    bottleneck_id, max_ctx, _ = min(gpu_limits, key=lambda x: x[1])
    for gpu_id, gpu_max, free_low in gpu_limits:
        marker = " ← bottleneck" if gpu_id == bottleneck_id else ""
        logger.info(
            f"Per-GPU projection: {gpu_id}: max ~{gpu_max} tokens "
            f"(free={free_low} MiB, margin={LLAMACPP_VRAM_SAFETY_MARGIN} MiB){marker}"
        )

    return max_ctx, combined_rate


def _fit_params_per_gpu_projection(
    full_cmd: str, gguf_path: Path, context: int, ngl: int,
) -> dict[str, dict[str, int]]:
    """Get per-GPU VRAM projections from llama-fit-params.

    Runs fit-params (~0.5s) and parses per-GPU memory lines like:
        CUDA0 (Quadro RTX 8000):  45355 total,  43710 used,   1478 free vs. target of   1024

    Returns: {"CUDA0": {"total": 45355, "used": 43710, "free": 1478}, ...}
    Raises RuntimeError if no GPU projections found in output.
    """
    cmd = _build_fit_params_cmd(full_cmd, gguf_path, context, ngl=ngl)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    output = result.stdout + result.stderr

    per_gpu: dict[str, dict[str, int]] = {}
    for match in re.finditer(
        r'(CUDA\d+)\s+\([^)]+\)\s*:\s*(\d+)\s+total\s*,\s*(\d+)\s+used\s*,\s*(-?\d+)\s+free',
        output,
    ):
        per_gpu[match.group(1)] = {
            "total": int(match.group(2)),
            "used": int(match.group(3)),
            "free": int(match.group(4)),
        }

    if not per_gpu:
        raise RuntimeError(
            f"llama-fit-params: no per-GPU projections in output:\n{output[:500]}"
        )
    return per_gpu


def _find_max_ngl_for_context(
    full_cmd: str,
    gguf_path: Path,
    context: int,
    total_layers: int,
) -> tuple[int, dict[str, dict[str, int]]]:
    """Binary search for highest NGL where all GPUs have free >= safety margin.

    Uses fit-params projections (~0.5s per iteration, ~6 iterations = ~3s).
    Returns (best_ngl, per_gpu_info) or (0, {}) if nothing fits.
    """
    ngl_low = 1
    ngl_high = total_layers
    best_ngl = 0
    best_info: dict[str, dict[str, int]] = {}

    while ngl_low <= ngl_high:
        ngl_mid = (ngl_low + ngl_high) // 2
        try:
            per_gpu = _fit_params_per_gpu_projection(
                full_cmd, gguf_path, context, ngl_mid,
            )
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            ngl_high = ngl_mid - 1
            continue

        min_free = min(info["free"] for info in per_gpu.values())
        if min_free >= LLAMACPP_VRAM_SAFETY_MARGIN:
            best_ngl = ngl_mid
            best_info = per_gpu
            ngl_low = ngl_mid + 1
        else:
            ngl_high = ngl_mid - 1

    return best_ngl, best_info


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
        # Write stdout to tempfile (parseable for VRAM info, readable after crash)
        fd, log_path = tempfile.mkstemp(suffix='.log', prefix='llama_')
        process = subprocess.Popen(
            args,
            stdout=fd,
            stderr=subprocess.STDOUT,  # merge stderr into stdout — llama-server logs to stdout
            preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
        )
        os.close(fd)  # Popen has dup'd the fd
        process._server_log = log_path  # type: ignore[attr-defined]
        return process
    except Exception as e:
        logger.error(f"Failed to start llama-server: {e}")
        if 'fd' in locals():
            try:
                os.close(fd)
            except OSError:
                pass
        if 'log_path' in locals():
            try:
                os.unlink(log_path)
            except OSError:
                pass
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
            return False  # Process died — caller handles logging

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
    timeout: float = 120.0,
) -> bool:
    """Test actual inference — health check alone is insufficient.

    On tight VRAM, the server starts and passes health checks but crashes
    on the first real request due to additional CUDA kernel allocations.
    Timeout is generous (120s) because thinking models reason before responding.
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
                # Verify we got actual content back (thinking models use reasoning_content)
                choices = data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    if msg.get("content") or msg.get("reasoning_content"):
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


def _kill_process(process: subprocess.Popen, keep_log: bool = False) -> None:
    """Kill a llama-server process and wait for cleanup.

    Args:
        keep_log: If True, preserve the server log file for breakdown parsing.
                  Caller must call _cleanup_server_log() after reading the log.
    """
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    if not keep_log:
        _cleanup_server_log(process)


def _cleanup_server_log(process: subprocess.Popen) -> None:
    """Remove the server's temporary log file."""
    log_path = getattr(process, '_server_log', None)
    if log_path:
        try:
            os.unlink(log_path)
        except OSError:
            pass


async def _start_and_verify(
    full_cmd: str,
    context: int,
    port: int,
    ngl: Optional[int] = None,
) -> Optional[subprocess.Popen]:
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
            # Read log before killing (kill cleans up the tempfile)
            output = _read_server_log(process)
            _kill_process(process)
            if output.strip():
                logger.error(f"llama-server failed to start. output:\n{output[:2000]}")
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


async def _test_context_physical(
    full_cmd: str, context: int, port: int,
) -> tuple[bool, str]:
    """Test if a context size fits in physical VRAM.

    Starts server, verifies health, measures free VRAM via pynvml (nvidia-smi).
    Checks the MINIMUM free VRAM across ALL GPUs (multi-GPU tensor-split).
    Breakdown from server exit is logged for diagnostics but not used for
    the decision (breakdown 'free' is always 0 — it measures llama.cpp's
    internal allocator, not GPU-wide free VRAM).

    Returns:
        (fits, detail) — fits=True if server starts AND min free VRAM >= LLAMACPP_VRAM_SAFETY_MARGIN.
    """
    process = await _start_and_verify(full_cmd, context, port)
    if not process:
        log_message(
            f"VRAM ctx={format_number(context)}: OOM (server failed to start)",
            category="stats",
        )
        return (False, "OOM")

    # pynvml = GPU-wide free VRAM per GPU (multi-GPU: check ALL GPUs)
    all_gpus = get_all_gpus_memory_info()
    if all_gpus and all_gpus["per_gpu"]:
        min_free_gpu = min(all_gpus["per_gpu"], key=lambda g: g["free_mb"])
        min_free_mb = min_free_gpu["free_mb"]
        per_gpu_detail = ", ".join(
            f"GPU{g['index']}: {g['free_mb']} MB free"
            for g in all_gpus["per_gpu"]
        )
        log_message(
            f"VRAM ctx={format_number(context)}: pynvml {per_gpu_detail}",
            category="stats",
        )
    else:
        min_free_mb = None
        log_message(
            f"VRAM ctx={format_number(context)}: pynvml unavailable",
            category="stats",
        )

    # Kill server, keep log for breakdown diagnostics
    _kill_process(process, keep_log=True)
    await asyncio.sleep(1.5)

    # Breakdown: only for diagnostics (free is always 0, self = model allocation)
    log_path = getattr(process, '_server_log', None)
    if log_path:
        breakdown = _parse_memory_breakdown(log_path)
        if breakdown:
            for gpu_id, info in breakdown.items():
                log_message(
                    f"VRAM ctx={format_number(context)}: "
                    f"breakdown {gpu_id}: self={info['self']} MB, "
                    f"unaccounted={info['total'] - info['free'] - info['self']} MB",
                    category="stats",
                )
        _cleanup_server_log(process)
    else:
        _cleanup_server_log(process)

    # Decision: min free VRAM across ALL GPUs vs safety margin
    if min_free_mb is not None and min_free_mb < LLAMACPP_VRAM_SAFETY_MARGIN:
        worst_gpu = f"GPU{min_free_gpu['index']}" if all_gpus else "GPU?"
        log_message(
            f"VRAM ctx={format_number(context)}: FAIL — "
            f"{worst_gpu}: {min_free_mb} MB free < {LLAMACPP_VRAM_SAFETY_MARGIN} MB margin",
            category="stats",
        )
        return (
            False,
            f"{worst_gpu}: {min_free_mb} MB free < {LLAMACPP_VRAM_SAFETY_MARGIN} MB minimum",
        )
    detail = f"min {min_free_mb} MB free" if min_free_mb is not None else "VRAM unknown"
    log_message(
        f"VRAM ctx={format_number(context)}: OK — {detail}",
        category="stats",
    )
    return (True, detail)


async def _binary_search_context(
    full_cmd: str,
    port: int,
    low: int,
    high: int,
    precision: int = 512,
) -> AsyncIterator[str | int]:
    """Binary search for max fitting context between low and high.

    Yields status strings during search. Final yield is the integer result
    (best fitting context found, or 0 if nothing fits).
    """
    result = 0
    iteration = 0

    while high - low > precision:
        mid = (low + high) // 2
        iteration += 1
        yield f"[{iteration}] Testing {format_number(mid)}..."
        mid_fits, mid_detail = await _test_context_physical(full_cmd, mid, port)
        if mid_fits:
            low = mid
            result = mid
            yield f"✓ {format_number(mid)} fits"
        else:
            high = mid
            if "VMM" in mid_detail:
                yield f"✗ {format_number(mid)} VMM overallocation"
            else:
                yield f"✗ {format_number(mid)} too large"

    yield result


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


def _inject_kv_quant(cmd: str, kv_quant: str) -> str:
    """Set -ctk/-ctv quantization in a llama-server command string.

    Replaces existing -ctk/-ctv values or inserts them before --port.
    Use kv_quant="" or "f16" to remove -ctk/-ctv (restore f16 default).
    """
    if not kv_quant or kv_quant == "f16":
        # Remove -ctk/-ctv to restore f16 default
        cmd = re.sub(r'\s*-ctk\s+\S+', '', cmd)
        cmd = re.sub(r'\s*-ctv\s+\S+', '', cmd)
        return cmd

    if '-ctk ' in cmd:
        cmd = re.sub(r'-ctk\s+\S+', f'-ctk {kv_quant}', cmd)
    else:
        cmd = cmd.replace(' --port', f' -ctk {kv_quant} --port')

    if '-ctv ' in cmd:
        cmd = re.sub(r'-ctv\s+\S+', f'-ctv {kv_quant}', cmd)
    else:
        cmd = cmd.replace(' --port', f' -ctv {kv_quant} --port')

    return cmd


def _has_tensor_split(full_cmd: str) -> bool:
    """Return True if the cmd uses multi-GPU tensor split."""
    return bool(re.search(r'(--tensor-split|-ts)\s+[\d.,]+', full_cmd))


def _parse_tensor_split_n(cmd: str) -> int:
    """Extract the fast-GPU part N from --tensor-split N,1 in cmd.

    Returns the integer part of the first value (e.g. "2,1" → 2, "11,1" → 11).
    Returns 0 if no tensor-split found.
    """
    match = re.search(r'(?:--tensor-split|-ts)\s+([\d.]+)', cmd)
    if not match:
        return 0
    return int(float(match.group(1)))


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
    Probe + binary search for the most aggressive tensor-split ratio at target_context.

    Probes slightly above the original split ratio to detect whether there's
    any headroom. No headroom = 1-2 tests, headroom = binary search upward.

    Algorithm:
    1. Parse original split N from cmd (e.g. 2 from "2,1")
    2. Test N+2 — if fail, test N+1 — if fail, no speed variant possible
    3. If N+2 succeeds, test 99:1 (best case), then binary search [N+2, 99]

    Yields progress messages.
    Final: "__SPEED__:{N}" where N is the best ratio, or "__SPEED__:0" on failure.
    """
    original_n = _parse_tensor_split_n(full_cmd)
    if original_n <= 0:
        yield "Speed calibration: cannot parse original tensor-split ratio"
        yield "__SPEED__:0"
        return

    yield (
        f"Speed calibration: bottom-up from {original_n}:1 "
        f"at ctx={format_number(target_context)}"
    )

    iteration = 0

    # Step 1: Probe original+2 — quick check for headroom
    probe_n = original_n + 2
    iteration += 1
    cmd_probe = _replace_tensor_split(full_cmd, probe_n, 1)
    yield f"[{iteration}] Testing split {probe_n}:1 (probe)..."
    fits = await _calibration_test(cmd_probe, target_context, port)

    if not fits:
        yield f"✗ {probe_n}:1 failed"
        # Step 2: Try original+1 — last chance for any improvement
        fallback_n = original_n + 1
        iteration += 1
        cmd_fallback = _replace_tensor_split(full_cmd, fallback_n, 1)
        yield f"[{iteration}] Testing split {fallback_n}:1..."
        fits = await _calibration_test(cmd_fallback, target_context, port)
        if fits:
            yield f"✓ {fallback_n}:1 fits — small improvement over {original_n}:1"
            yield f"Speed split found: {fallback_n}:1 ({iteration} iterations)"
            yield f"__SPEED__:{fallback_n}"
        else:
            yield f"✗ {fallback_n}:1 failed — no speed variant possible"
            yield "__SPEED__:0"
        return

    yield f"✓ {probe_n}:1 fits — binary search for maximum"

    # Step 3: Binary search [probe_n, 48] for maximum split
    best_n = probe_n
    split_low = probe_n
    split_high = 48

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

    yield f"Speed split found: {best_n}:1 ({iteration} iterations)"
    yield f"__SPEED__:{best_n}"



async def _calibrate_hybrid(
    model_id: str,
    gguf_path: Path,
    full_cmd: str,
    native_context: int,
    model_size_gb: float,
    total_layers: int,
) -> AsyncIterator[str]:
    """
    Hybrid NGL+context calibration using fit-params per-GPU VRAM projection.

    Uses per-GPU projections from llama-fit-params (~0.5s each) instead of
    actual server starts (~30-60s each), reducing calibration from minutes to seconds.

    Algorithm:
    1. Build descending context targets (native → 128K → 64K → 32K → 16K)
    2. For each target: binary search NGL via fit-params per-GPU projection (~3s)
    3. Check RAM feasibility for CPU layers
    4. Binary search context upward via fit-params (~3s)
    5. Yield: "__HYBRID__:{context}:{ngl}" — caller handles server verification
    """
    from .gpu_utils import get_free_ram_mb

    yield f"Hybrid calibration: {total_layers} layers, fit-params projection"

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
    context_targets.append(16384)
    seen: set[int] = set()
    unique_targets: list[int] = []
    for c in context_targets:
        if c not in seen:
            seen.add(c)
            unique_targets.append(c)
    context_targets = unique_targets

    best_ngl: Optional[int] = None
    best_ctx: Optional[int] = None

    for target_ctx in context_targets:
        yield f"Searching NGL for ctx={format_number(target_ctx)} via fit-params..."

        ngl, per_gpu = _find_max_ngl_for_context(
            full_cmd, gguf_path, target_ctx, total_layers,
        )

        if ngl < 1:
            yield f"  Skip ctx={format_number(target_ctx)}: no NGL fits in VRAM"
            continue

        # Check RAM feasibility (CPU layers consume host RAM)
        cpu_layers = total_layers - ngl
        vram_per_layer = model_size_gb * 1024 / total_layers
        ram_for_cpu_layers = cpu_layers * vram_per_layer
        free_ram = get_free_ram_mb()

        if free_ram and (free_ram - ram_for_cpu_layers) < MIN_FREE_RAM_MB:
            yield (
                f"  Skip ctx={format_number(target_ctx)}, ngl={ngl}: "
                f"not enough RAM for {cpu_layers} CPU layers "
                f"({format_number(int(ram_for_cpu_layers))} MB needed, "
                f"{format_number(free_ram)} MB free)"
            )
            continue

        min_free = min(info["free"] for info in per_gpu.values())
        gpu_detail = ", ".join(
            f"{gpu}: {info['free']} MB free"
            for gpu, info in sorted(per_gpu.items())
        )
        yield (
            f"  Found ngl={ngl} ({cpu_layers} CPU layers), "
            f"min free: {min_free} MB ({gpu_detail})"
        )
        best_ngl = ngl
        best_ctx = target_ctx
        break

    if best_ngl is None or best_ctx is None:
        yield "Hybrid calibration failed: no working (ngl, context) combination found"
        return

    # Phase 2: Binary search context upward via fit-params
    if best_ctx < native_context:
        yield (
            f"NGL={best_ngl} found. Binary searching context upward "
            f"from {format_number(best_ctx)} via fit-params..."
        )
        ctx_low = best_ctx
        ctx_high = native_context
        iteration = 0

        while ctx_high - ctx_low > 512:
            ctx_mid = (ctx_low + ctx_high) // 2
            iteration += 1
            try:
                per_gpu = _fit_params_per_gpu_projection(
                    full_cmd, gguf_path, ctx_mid, best_ngl,
                )
                min_free = min(info["free"] for info in per_gpu.values())
                if min_free >= LLAMACPP_VRAM_SAFETY_MARGIN:
                    ctx_low = ctx_mid
                    best_ctx = ctx_mid
                    yield f"  [{iteration}] ctx={format_number(ctx_mid)}: fits ({min_free} MB free)"
                else:
                    ctx_high = ctx_mid
                    yield f"  [{iteration}] ctx={format_number(ctx_mid)}: too tight ({min_free} MB free)"
            except (RuntimeError, OSError, subprocess.TimeoutExpired):
                ctx_high = ctx_mid
                yield f"  [{iteration}] ctx={format_number(ctx_mid)}: projection failed"

    cpu_layers = total_layers - best_ngl
    yield (
        f"Hybrid calibration complete: ngl={best_ngl}, "
        f"ctx={format_number(best_ctx)} tokens "
        f"({cpu_layers} layers on CPU)"
    )
    yield f"__HYBRID__:{best_ctx}:{best_ngl}"


async def calibrate_llamacpp_model(
    model_id: str,
    gguf_path: Path,
    full_cmd: str,
    port: int = LLAMACPP_CALIBRATION_PORT,
    config_path: Optional[Path] = None,
) -> AsyncIterator[str]:
    """
    Projection-based calibration for a llama.cpp model.

    Phase 1 (GPU-only): VRAM projection via llama-fit-params → verify with server
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

    gpu_info = get_all_gpus_memory_info()
    total_vram_mb = gpu_info["total_mb"] if gpu_info else 0
    model_size_mb = model_size_gb * 1024
    vram_ratio = model_size_mb / total_vram_mb if total_vram_mb > 0 else 0
    total_vram_gb = total_vram_mb / 1024

    yield (
        f"Model: {model_id} ({format_number(model_size_gb, 1)} GB), "
        f"native context: {format_number(native_context)} "
        f"(model = {vram_ratio:.0%} of {format_number(total_vram_gb, 1)} GB VRAM)"
    )

    # Strip any existing -ctk/-ctv from cmd — Phase 1 starts with f16 KV
    # and the fallback chain will inject quantization only if needed.
    full_cmd = _inject_kv_quant(full_cmd, "f16")

    # Step 2: Check VRAM
    from aifred.backends.ollama import wait_for_vram_stable

    yield "Waiting for VRAM to stabilize..."
    stabilized, wait_time, free_vram = await wait_for_vram_stable(max_wait_seconds=15.0)
    yield f"Free VRAM: {format_number(free_vram)} MB"

    if free_vram < 1000:
        yield "Not enough VRAM (<1 GB free)"
        yield "__RESULT__:0:0:error"
        return

    # Helper: test thinking on running server (or start new one), yield result
    async def _finish_calibration(
        ctx: int, ngl: int, mode: str,
        process: Optional[subprocess.Popen] = None,
    ):
        """Test thinking on server, measure VRAM, save calibration, emit result.

        If process is provided, reuses the already-running server (avoids reload).
        Otherwise starts a new server for the thinking test.
        VRAM is parsed from llama_memory_breakdown_print (written at server exit).
        """
        # Reuse existing server or start a new one
        if not process:
            process = await _start_and_verify(full_cmd, ctx, port, ngl=ngl if ngl != 99 else None)

        vram_per_gpu: Optional[Dict[str, int]] = None
        ram_cpu_mb: Optional[int] = None
        thinks = False
        if process:
            yield "Testing reasoning capability..."
            thinks = await test_thinking_on_port(port)
            # Measure CPU RAM before killing (VmRSS from /proc)
            ram_cpu_mb = _measure_process_ram_mb(process.pid)
            if ram_cpu_mb and ram_cpu_mb > 0:
                yield f"RAM (CPU): {format_number(ram_cpu_mb)} MB"
            # Kill but keep log for breakdown parsing
            _kill_process(process, keep_log=True)
            await asyncio.sleep(1.5)
            # Parse VRAM from breakdown (physical allocation per GPU)
            log_path = getattr(process, '_server_log', None)
            if log_path:
                breakdown = _parse_memory_breakdown(log_path)
                if breakdown:
                    # Use 'self' from breakdown (actual allocation, not virtual)
                    vram_per_gpu = {gpu: info["self"] for gpu, info in breakdown.items()}
                    total_mb = sum(vram_per_gpu.values())
                    if len(vram_per_gpu) > 1:
                        parts = ", ".join(
                            f"{gpu}: {format_number(mb)} MB"
                            for gpu, mb in sorted(vram_per_gpu.items())
                        )
                        yield f"VRAM (model): {format_number(total_mb)} MB ({parts})"
                    else:
                        yield f"VRAM (model): {format_number(total_mb)} MB"
                _cleanup_server_log(process)

        all_gpus = get_all_gpus_memory_info()
        gpu_model = ", ".join(all_gpus["gpu_models"]) if all_gpus and all_gpus.get("gpu_models") else "Unknown"
        add_llamacpp_calibration(
            model_id=model_id, max_context=ctx, native_context=native_context,
            gguf_path=str(gguf_path), quantization=quantization, gpu_model=gpu_model,
            model_size_gb=model_size_gb, ngl=ngl, mode=mode,
            vram_per_gpu=vram_per_gpu, ram_cpu_mb=ram_cpu_mb,
        )
        yield f"__RESULT__:{ctx}:{ngl}:{mode}:{'thinks' if thinks else 'nothink'}"

    # === Small model: native context ≤ calibration minimum ===
    # These models always fit in GPU memory — startup failure is NOT an OOM issue.
    # Most likely cause: --flash-attn incompatibility (Deepseek-OCR, Mamba, etc.)
    if native_context <= CALIBRATION_MIN_CONTEXT:
        yield (
            f"Small model: native context {format_number(native_context)} ≤ "
            f"calibration minimum {format_number(CALIBRATION_MIN_CONTEXT)} — testing directly"
        )
        process = await _start_and_verify(full_cmd, native_context, port)

        if process is None and '--flash-attn on' in full_cmd:
            yield "Startup failed — retrying without --flash-attn (not all architectures support it)"
            cmd_no_fa = full_cmd.replace('--flash-attn on', '--flash-attn off')
            process = await _start_and_verify(cmd_no_fa, native_context, port)
            if process:
                yield "✓ Architecture incompatible with --flash-attn — updating llama-swap config"
                if config_path:
                    update_llamaswap_flash_attn(config_path, model_id)
                # Use flash-attn-free cmd for the thinking test (closure picks this up)
                full_cmd = cmd_no_fa

        if process:
            yield f"✓ {format_number(native_context)} tokens confirmed"
            async for msg in _finish_calibration(native_context, 99, "gpu", process=process):
                yield msg
        else:
            yield (
                "Model failed to start — see llama-server logs "
                "(incompatible architecture, CUDA version, or corrupted GGUF?)"
            )
            yield "__RESULT__:0:0:error"
        return

    # === Skip GPU-only for oversized models ===
    # Model weights alone exceed total VRAM → GPU-only is impossible,
    # jump straight to hybrid calibration (saves minutes of pointless OOM attempts)
    if vram_ratio > 1.0:
        oversized_msg = (
            f"Oversized model: {format_number(model_size_gb, 1)} GB > "
            f"{format_number(total_vram_gb, 1)} GB VRAM ({vram_ratio:.0%})"
        )
        yield oversized_msg
        yield "GPU-only phase skipped — hybrid calibration (GPU + CPU offload) required"

        total_layers = get_gguf_layer_count(gguf_path)
        if not total_layers:
            yield "Cannot read layer count from GGUF — hybrid mode unavailable"
            yield "__RESULT__:0:0:error"
            return

        hybrid_ctx = None
        hybrid_ngl = None
        async for hybrid_msg in _calibrate_hybrid(
            model_id=model_id,
            gguf_path=gguf_path,
            full_cmd=full_cmd,
            native_context=native_context,
            model_size_gb=model_size_gb,
            total_layers=total_layers,
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

        yield "Calibration failed: no working configuration found — check llama-server logs"
        yield "__RESULT__:0:0:error"
        return

    # === PHASE 1: GPU-only calibration (ngl=99) with KV fallback chain ===
    # Strategy: f16 KV first (best quality). If context drops below 64k,
    # try q8_0, then q4_0 to reclaim VRAM for more context.
    # Force ngl=99 for Phase 1 — the cmd may have a lower ngl from previous
    # hybrid calibration, but Phase 1 always tests all layers on GPU.
    phase1_cmd = re.sub(r'(-ngl\s+)\d+', r'\g<1>99', full_cmd)
    kv_levels = ["f16", "q8_0", "q4_0"]
    best_result = 0
    best_kv = "f16"

    for kv_level in kv_levels:
        if kv_level != "f16" and best_result >= KV_QUANT_CONTEXT_THRESHOLD:
            # f16 already yields enough context — no need to quantize KV
            break

        test_cmd = _inject_kv_quant(phase1_cmd, kv_level)
        yield f"Phase 1: GPU-only (ngl=99, KV={kv_level})"

        # Per-GPU VRAM projection for this KV level (ngl=99 forced for Phase 1)
        try:
            per_gpu_low = _fit_params_per_gpu_projection(
                test_cmd, gguf_path, CALIBRATION_MIN_CONTEXT, ngl=99,
            )
            per_gpu_high = _fit_params_per_gpu_projection(
                test_cmd, gguf_path, native_context, ngl=99,
            )
            kv_max, rate = _calculate_max_context_per_gpu(
                per_gpu_low, per_gpu_high, CALIBRATION_MIN_CONTEXT, native_context,
            )
            kv_max = min(kv_max, native_context)
            yield (
                f"Projection (KV={kv_level}): {format_number(rate, 4)} MiB/tok, "
                f"max ~{format_number(kv_max)} tokens"
            )
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            yield f"VRAM projection failed for KV={kv_level} — skipping"
            continue

        # Test projection estimate, then refine in a narrow window.
        # The per-GPU projection is typically within ~5% of the physical limit,
        # so searching [projection, native_context] wastes time on OOM tests.
        # Instead: search ±15% around the projection to fine-tune quickly.
        test_ctx = kv_max
        search_margin = max(test_ctx // 7, 4096)  # ~15% of projection, min 4K
        label = "native" if test_ctx == native_context else "projected"
        yield f"[1] Testing {label}: {format_number(test_ctx)}..."

        fits, detail = await _test_context_physical(test_cmd, test_ctx, port)
        result = 0

        if fits:
            yield f"✓ {format_number(test_ctx)} fits"
            result = test_ctx

            # Narrow binary search upward (projection + margin, capped at native)
            search_high = min(test_ctx + search_margin, native_context)
            if result < search_high:
                async for item in _binary_search_context(
                    test_cmd, port, result, search_high,
                ):
                    if isinstance(item, int):
                        if item > result:
                            result = item
                    else:
                        yield item
                if result > test_ctx:
                    yield (
                        f"Optimum: {format_number(result)} tokens "
                        f"(+{format_number(result - test_ctx)} vs projection)"
                    )
        else:
            if "VMM" in detail:
                yield f"✗ {format_number(test_ctx)} VMM overallocation — searching downward"
            else:
                yield f"✗ {format_number(test_ctx)} too large — searching downward"

            # Narrow binary search downward (projection - margin)
            search_low = max(test_ctx - search_margin, CALIBRATION_MIN_CONTEXT)
            async for item in _binary_search_context(
                test_cmd, port, search_low, test_ctx,
            ):
                if isinstance(item, int):
                    result = item
                else:
                    yield item

            # Fallback: if narrow window found nothing, widen to full range
            if not result and search_low > CALIBRATION_MIN_CONTEXT:
                yield f"Narrow search failed — widening to [{format_number(CALIBRATION_MIN_CONTEXT)}, {format_number(search_low)}]"
                async for item in _binary_search_context(
                    test_cmd, port, CALIBRATION_MIN_CONTEXT, search_low,
                ):
                    if isinstance(item, int):
                        result = item
                    else:
                        yield item

            if result:
                yield (
                    f"Optimum: {format_number(result)} tokens "
                    f"({format_number(test_ctx - result)} below projection)"
                )

        if result > best_result:
            best_result = result
            best_kv = kv_level

        # Good enough with this KV level — stop trying lower quality
        if best_result >= KV_QUANT_CONTEXT_THRESHOLD:
            break

        if kv_level != kv_levels[-1] and best_result < KV_QUANT_CONTEXT_THRESHOLD:
            yield (
                f"KV={kv_level}: {format_number(best_result)} tokens "
                f"< {format_number(KV_QUANT_CONTEXT_THRESHOLD)} threshold — "
                f"trying lower KV quality"
            )
            await wait_for_vram_stable(max_wait_seconds=10.0)

    # GPU-only success with useful context → finish
    if best_result >= MIN_USEFUL_CONTEXT_TOKENS:
        # Apply the winning KV level to the cmd for speed calibration and finish
        full_cmd = _inject_kv_quant(full_cmd, best_kv)
        if best_kv != "f16" and config_path:
            update_llamaswap_kv_cache_quant(config_path, model_id, best_kv)
            yield f"KV-Cache quantization set to {best_kv} in llama-swap config"
        elif best_kv == "f16" and config_path:
            # Remove any stale -ctk/-ctv from config
            _remove_llamaswap_kv_cache_quant(config_path, model_id)

        if _has_tensor_split(full_cmd):
            yield "Phase 2: Speed variant calibration (tensor-split optimization)"
            async for msg in _calibrate_speed_split(full_cmd, port, MIN_USEFUL_CONTEXT_TOKENS):
                yield msg
        async for msg in _finish_calibration(best_result, 99, "gpu"):
            yield msg
        return

    # === PHASE 3: Hybrid calibration (GPU-only context insufficient) ===
    yield (
        f"GPU-only context ({format_number(best_result)}) < "
        f"minimum useful ({format_number(MIN_USEFUL_CONTEXT_TOKENS)})"
    )

    total_layers = get_gguf_layer_count(gguf_path)
    if not total_layers:
        yield "Cannot read layer count from GGUF — hybrid mode unavailable"
        yield "__RESULT__:0:0:error"
        return

    yield f"Phase 3: Hybrid calibration (fallback, {total_layers} layers)"

    # Wait for VRAM to stabilize after GPU-only tests
    await wait_for_vram_stable(max_wait_seconds=10.0)

    hybrid_ctx = None
    hybrid_ngl = None
    async for hybrid_msg in _calibrate_hybrid(
        model_id=model_id,
        gguf_path=gguf_path,
        full_cmd=full_cmd,
        native_context=native_context,
        model_size_gb=model_size_gb,
        total_layers=total_layers,
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

    yield "Calibration failed: no working configuration found — check llama-server logs"
    yield "__RESULT__:0:0:error"
