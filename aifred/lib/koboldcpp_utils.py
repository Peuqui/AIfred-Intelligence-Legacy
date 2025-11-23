"""
KoboldCPP/llama.cpp Error Parsing Utilities

Parses error messages from KoboldCPP/llama.cpp to extract VRAM limits and context constraints.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_koboldcpp_max_context_from_error(error_output: str) -> Optional[int]:
    """
    Parse maximum possible context from KoboldCPP/llama.cpp error message.

    KoboldCPP (llama.cpp) error messages contain patterns like:
    - "CUDA error: out of memory"
    - "failed to allocate CUDA memory"
    - "llama_kv_cache_init: CUDA0 max size exceeded"
    - "error: context size X exceeds available VRAM"

    Unlike vLLM, llama.cpp does NOT provide explicit token limits in errors.
    Instead, we need to:
    1. Detect OOM/CUDA errors
    2. Return None (signal to use fallback strategy)
    3. Caller should reduce context and retry

    Args:
        error_output: KoboldCPP stderr/stdout output containing error message

    Returns:
        Maximum context in tokens if found, None otherwise

    Example error patterns (llama.cpp):
        - "CUDA error 2 at llama.cpp:123: out of memory"
        - "ggml_cuda_op_mul_mat: CUDA error: out of memory"
        - "error: failed to allocate CUDA memory of size X bytes"
        - "llama_kv_cache_init: failed to allocate X bytes"
    """
    # Pattern 1: CUDA OOM errors (most common)
    cuda_oom_patterns = [
        r'CUDA\s+error.*out\s+of\s+memory',
        r'failed\s+to\s+allocate\s+CUDA\s+memory',
        r'ggml_cuda.*out\s+of\s+memory',
        r'CUDA_ERROR_OUT_OF_MEMORY',
    ]

    for pattern in cuda_oom_patterns:
        if re.search(pattern, error_output, re.IGNORECASE):
            logger.info("Detected CUDA OOM error in KoboldCPP output")
            # llama.cpp doesn't tell us the max - return None to signal OOM
            return None

    # Pattern 2: KV cache allocation errors
    kv_cache_patterns = [
        r'llama_kv_cache_init.*failed',
        r'kv_cache.*error',
        r'failed\s+to\s+initialize\s+KV\s+cache',
    ]

    for pattern in kv_cache_patterns:
        if re.search(pattern, error_output, re.IGNORECASE):
            logger.info("Detected KV cache allocation error in KoboldCPP output")
            return None

    # Pattern 3: Generic memory allocation failures
    memory_patterns = [
        r'failed\s+to\s+allocate.*bytes',
        r'allocation.*failed',
        r'insufficient\s+memory',
    ]

    for pattern in memory_patterns:
        if re.search(pattern, error_output, re.IGNORECASE):
            logger.info("Detected memory allocation error in KoboldCPP output")
            return None

    # Pattern 4: Explicit context size errors (rare, but possible in custom builds)
    # "error: context size 200000 exceeds maximum 131072"
    match = re.search(r'context\s+size\s+\d+\s+exceeds\s+maximum\s+(\d+)', error_output, re.IGNORECASE)
    if match:
        max_context = int(match.group(1))
        logger.info(f"Parsed explicit max context from KoboldCPP error: {max_context:,} tokens")
        return max_context

    # No recognizable error pattern
    logger.warning("Could not parse context limit from KoboldCPP error")
    logger.debug(f"Error output (first 500 chars): {error_output[:500]}")
    return None


def is_koboldcpp_oom_error(error_output: str) -> bool:
    """
    Check if error output indicates OOM/CUDA memory error

    Args:
        error_output: KoboldCPP stderr/stdout output

    Returns:
        True if OOM detected, False otherwise
    """
    oom_indicators = [
        r'CUDA\s+error.*out\s+of\s+memory',
        r'failed\s+to\s+allocate\s+CUDA\s+memory',
        r'ggml_cuda.*out\s+of\s+memory',
        r'CUDA_ERROR_OUT_OF_MEMORY',
        r'llama_kv_cache_init.*failed',
        r'failed\s+to\s+allocate.*bytes',
    ]

    for pattern in oom_indicators:
        if re.search(pattern, error_output, re.IGNORECASE):
            return True

    return False


def extract_vram_usage_from_koboldcpp(output: str) -> Optional[int]:
    """
    Extract VRAM usage from KoboldCPP output

    KoboldCPP (llama.cpp) outputs VRAM stats like:
    - "llm_load_tensors: VRAM used: 12.34 GB"
    - "total VRAM used: 15678 MB"

    Args:
        output: KoboldCPP stdout output

    Returns:
        VRAM usage in MB if found, None otherwise
    """
    # Pattern 1: "VRAM used: X.XX GB"
    match = re.search(r'VRAM\s+used:?\s+([\d.]+)\s*GB', output, re.IGNORECASE)
    if match:
        vram_gb = float(match.group(1))
        vram_mb = int(vram_gb * 1024)
        logger.info(f"Extracted VRAM usage from KoboldCPP: {vram_mb:,}MB ({vram_gb:.2f}GB)")
        return vram_mb

    # Pattern 2: "VRAM used: X MB"
    match = re.search(r'VRAM\s+used:?\s+([\d]+)\s*MB', output, re.IGNORECASE)
    if match:
        vram_mb = int(match.group(1))
        logger.info(f"Extracted VRAM usage from KoboldCPP: {vram_mb:,}MB")
        return vram_mb

    # Pattern 3: "total VRAM: X MB"
    match = re.search(r'total\s+VRAM:?\s+([\d]+)\s*MB', output, re.IGNORECASE)
    if match:
        vram_mb = int(match.group(1))
        logger.info(f"Extracted total VRAM from KoboldCPP: {vram_mb:,}MB")
        return vram_mb

    return None
