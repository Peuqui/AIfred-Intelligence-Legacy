"""
Central Timer utility for duration measurements.

Uses time.monotonic() instead of time.time() to avoid issues with:
- NTP synchronization jumps
- System time changes
- WSL2 time drift

Usage:
    from .timer import Timer

    timer = Timer()
    # ... do work ...
    elapsed = timer.elapsed()      # seconds as float
    elapsed_ms = timer.elapsed_ms() # milliseconds as float
"""

import time


class Timer:
    """Timer class using monotonic clock for reliable duration measurement."""

    __slots__ = ("_start",)

    def __init__(self):
        """Start the timer immediately on creation."""
        self._start = time.monotonic()

    def elapsed(self) -> float:
        """Return elapsed time in seconds since timer creation."""
        return time.monotonic() - self._start

    def elapsed_ms(self) -> float:
        """Return elapsed time in milliseconds since timer creation."""
        return self.elapsed() * 1000
