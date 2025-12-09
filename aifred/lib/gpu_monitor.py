"""
GPU Monitor - Utility functions for GPU/VRAM calculations.

This module extracts pure helper functions from state.py that don't require
State access and can be used for GPU-related calculations.

Extracted from state.py (Phase 3.3 Refactoring):
- round_to_nominal_vram(): Round raw VRAM to marketing specs
"""

import math
from typing import List


# Common GPU VRAM sizes in GB (marketing specs)
NOMINAL_VRAM_SIZES: List[int] = [4, 6, 8, 10, 11, 12, 16, 20, 24, 32, 40, 48, 64, 80]


def round_to_nominal_vram(vram_mb: int) -> int:
    """
    Round VRAM to nearest marketing spec (nominal size).

    nvidia-smi reports slightly less VRAM than the marketing spec due to
    firmware overhead. This function rounds up to the expected nominal size.

    Args:
        vram_mb: VRAM in MiB as reported by nvidia-smi

    Returns:
        Nominal VRAM size in GB (e.g., 8, 12, 24, 48)

    Examples:
        >>> round_to_nominal_vram(23040)  # RTX 3090/4090
        24
        >>> round_to_nominal_vram(11264)  # RTX 2080 Ti
        12
        >>> round_to_nominal_vram(8192)   # RTX 3070
        8
        >>> round_to_nominal_vram(45000)  # Tesla A40
        48
    """
    vram_gb = vram_mb / 1024

    # Find closest size that's >= actual VRAM
    for size in NOMINAL_VRAM_SIZES:
        if vram_gb <= size:
            return size

    # Fallback: round up to nearest GB (for future larger GPUs)
    return math.ceil(vram_gb)
