"""Audio Manager — central audio output control for AIfred.

Manages audio playback (files, TTS, streams) through a single point.
Supports local playback (aplay/mpv) and future remote outputs (Pucks).

Architecture:
    Tool: audio_play ──┐
    TTS Output ────────┤→ Audio Manager → Output Layer (local/remote/browser)
    Wake Word ─────────┘   (singleton)     ↑ can interrupt
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

from .logging_utils import log_message

logger = logging.getLogger(__name__)


class AudioManager:
    """Central audio playback manager. Singleton via module-level instance."""

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._active_file: str = ""

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        return self._process is not None and self._process.poll() is None

    def play(self, file_path: str) -> bool:
        """Play an audio file. Stops any currently playing audio first.

        Supports WAV, MP3, OGG, FLAC via aplay (WAV) or ffplay (other).
        Returns True if playback started successfully.
        """
        path = Path(file_path)
        if not path.exists():
            log_message(f"Audio Manager: file not found: {file_path}", "error")
            return False

        # Stop current playback
        self.stop()

        suffix = path.suffix.lower()

        try:
            if suffix == ".wav":
                self._process = subprocess.Popen(
                    ["aplay", "-q", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                # ffplay for MP3, OGG, FLAC, etc.
                self._process = subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            self._active_file = str(path)
            log_message(f"Audio Manager: playing {path.name}")
            return True

        except FileNotFoundError as exc:
            log_message(f"Audio Manager: player not found: {exc}", "error")
            return False
        except Exception as exc:
            log_message(f"Audio Manager: playback failed: {exc}", "error")
            return False

    def stop(self) -> bool:
        """Stop current playback immediately. Returns True if something was stopped."""
        if not self.is_playing:
            return False

        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()

        log_message(f"Audio Manager: stopped {Path(self._active_file).name}")
        self._process = None
        self._active_file = ""
        return True

    def status(self) -> dict[str, object]:
        """Get current playback status."""
        return {
            "playing": self.is_playing,
            "file": self._active_file if self.is_playing else "",
        }


# Singleton
audio_manager = AudioManager()
