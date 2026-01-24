"""
Audio Processing Module - TTS and STT functionality

This module handles Text-to-Speech (Edge TTS, Piper TTS) and Speech-to-Text
(Whisper) operations, including text cleanup for TTS.
"""

import os
import re
import time  # Keep for timestamp (used in filenames)
import subprocess
import asyncio
import atexit
import edge_tts
from .config import PIPER_MODEL_PATH, PROJECT_ROOT, DATA_DIR
from .logging_utils import log_message
from .timer import Timer


# Determine platform-specific Piper binary path
if os.name == 'nt':  # Windows
    PIPER_BIN = PROJECT_ROOT / "venv" / "Scripts" / "piper.exe"
else:  # Linux/Mac
    PIPER_BIN = PROJECT_ROOT / "venv" / "bin" / "piper"

# TTS Audio output directory (temporary chunks, 24h cleanup)
# Located in data/ directory which is excluded from hot-reload
# Served via /_upload/ endpoint
TTS_AUDIO_DIR = DATA_DIR / "tts_audio"
TTS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Session audio directory (permanent, deleted with session)
# Structure: data/audio/{session_id}/
SESSION_AUDIO_DIR = DATA_DIR / "audio"
SESSION_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Current agent for filename prefixing (set by state before TTS calls)
_current_tts_agent: str = "aifred"

# Streaming content hint tracking - ensures hints are only spoken once per block
# Reset when regular text is detected, so next occurrence gets announced again
_table_hint_announced: bool = False
_formula_hint_announced: bool = False
_code_hint_announced: bool = False


def reset_content_hint_flags() -> None:
    """Reset all content hint flags (for new streaming session or after regular text)."""
    global _table_hint_announced, _formula_hint_announced, _code_hint_announced
    _table_hint_announced = False
    _formula_hint_announced = False
    _code_hint_announced = False


def set_tts_agent(agent_name: str) -> None:
    """Set current agent name for TTS filename prefixing."""
    global _current_tts_agent
    _current_tts_agent = agent_name.lower()


def _generate_tts_filename(extension: str = "wav") -> str:
    """
    Generate TTS audio filename with agent prefix.

    Format: audio_{agent}_{timestamp_ms}.{ext}
    Example: audio_aifred_1737489600123.wav

    Args:
        extension: File extension (wav, mp3)

    Returns:
        Filename string
    """
    global _current_tts_agent
    agent = _current_tts_agent or "aifred"
    timestamp = int(time.time() * 1000)
    return f"audio_{agent}_{timestamp}.{extension}"


def concatenate_wav_files(wav_urls: list[str], delete_originals: bool = True) -> str | None:
    """
    Concatenate multiple WAV files into a single WAV file using ffmpeg.

    Uses ffmpeg because XTTS generates IEEE Float WAV files which Python's
    wave module cannot read (only supports PCM format).

    Args:
        wav_urls: List of WAV URLs (format: /_upload/tts_audio/filename.wav)
        delete_originals: If True, delete the original chunk files after concatenation

    Returns:
        URL of the combined WAV file, or None on error
    """
    if not wav_urls:
        return None

    if len(wav_urls) == 1:
        # Only one file, no concatenation needed
        return wav_urls[0]

    # Convert URLs to file paths
    file_paths: list[str] = []
    for url in wav_urls:
        # URL format: /_upload/tts_audio/filename.wav
        # File path: TTS_AUDIO_DIR / filename.wav
        if "/_upload/tts_audio/" in url:
            filename = url.split("/_upload/tts_audio/")[-1]
            file_path = str(TTS_AUDIO_DIR / filename)
            if os.path.exists(file_path):
                file_paths.append(file_path)
            else:
                log_message(f"⚠️ WAV concat: File not found: {file_path}")

    if len(file_paths) < 2:
        # Not enough files to concatenate
        return wav_urls[0] if wav_urls else None

    # Generate output filename
    output_filename = _generate_tts_filename("wav").replace(".wav", "_combined.wav")
    output_path = str(TTS_AUDIO_DIR / output_filename)

    try:
        # Use ffmpeg concat filter to join WAV files
        # This handles IEEE Float format that Python's wave module can't read
        # Format: ffmpeg -i file1.wav -i file2.wav -filter_complex "[0:a][1:a]concat=n=2:v=0:a=1" out.wav

        # Build input arguments
        input_args = []
        for fp in file_paths:
            input_args.extend(["-i", fp])

        # Build filter string: [0:a][1:a][2:a]...concat=n=N:v=0:a=1
        filter_inputs = "".join(f"[{i}:a]" for i in range(len(file_paths)))
        filter_str = f"{filter_inputs}concat=n={len(file_paths)}:v=0:a=1"

        cmd = [
            "ffmpeg", "-y",  # Overwrite output
            *input_args,
            "-filter_complex", filter_str,
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=30)

        if result.returncode == 0 and os.path.exists(output_path):
            log_message(f"✅ WAV concat: {len(file_paths)} files → {output_filename}")

            # Delete original chunk files if requested
            if delete_originals:
                for file_path in file_paths:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass  # Ignore deletion errors

            return f"/_upload/tts_audio/{output_filename}"
        else:
            error_msg = result.stderr.decode()[:200] if result.stderr else "Unknown error"
            log_message(f"❌ WAV concat ffmpeg error: {error_msg}")
            return wav_urls[0] if wav_urls else None

    except Exception as e:
        log_message(f"❌ WAV concat error: {e}")
        # Return first URL as fallback
        return wav_urls[0] if wav_urls else None


def save_audio_to_session(wav_urls: list[str], session_id: str) -> str | None:
    """
    Save TTS audio to session directory for permanent storage.

    For single audio files: copies to session directory
    For multiple chunks: concatenates and saves to session directory

    Audio in session directory is NOT subject to 24h cleanup.
    It's deleted when the session is deleted.

    Args:
        wav_urls: List of WAV URLs (format: /_upload/tts_audio/filename.wav)
        session_id: Session ID for directory structure

    Returns:
        URL of the session audio file (/_upload/audio/{session_id}/filename.wav)
        or None on error
    """
    import shutil

    if not wav_urls or not session_id:
        return None

    # Ensure session audio directory exists
    session_audio_dir = SESSION_AUDIO_DIR / session_id
    session_audio_dir.mkdir(parents=True, exist_ok=True)

    # Generate output filename
    output_filename = _generate_tts_filename("wav")

    if len(wav_urls) == 1:
        # Single file: copy to session directory
        url = wav_urls[0]
        if "/_upload/tts_audio/" in url:
            filename = url.split("/_upload/tts_audio/")[-1]
            source_path = TTS_AUDIO_DIR / filename
            if source_path.exists():
                dest_path = session_audio_dir / output_filename
                shutil.copy2(str(source_path), str(dest_path))
                log_message(f"📁 Audio copied to session: {output_filename}")
                return f"/_upload/audio/{session_id}/{output_filename}"
            else:
                log_message(f"⚠️ Audio file not found: {source_path}")
                return None
        return None

    # Multiple files: concatenate to session directory
    file_paths: list[str] = []
    for url in wav_urls:
        if "/_upload/tts_audio/" in url:
            filename = url.split("/_upload/tts_audio/")[-1]
            file_path = str(TTS_AUDIO_DIR / filename)
            if os.path.exists(file_path):
                file_paths.append(file_path)
            else:
                log_message(f"⚠️ WAV concat: File not found: {file_path}")

    if len(file_paths) < 2:
        # Not enough files, fall back to single file handling
        if file_paths:
            dest_path = session_audio_dir / output_filename
            shutil.copy2(file_paths[0], str(dest_path))
            log_message(f"📁 Audio copied to session: {output_filename}")
            return f"/_upload/audio/{session_id}/{output_filename}"
        return wav_urls[0] if wav_urls else None

    # Concatenate using ffmpeg
    output_path = str(session_audio_dir / output_filename)

    try:
        # Build ffmpeg command
        input_args = []
        for fp in file_paths:
            input_args.extend(["-i", fp])

        filter_inputs = "".join(f"[{i}:a]" for i in range(len(file_paths)))
        filter_str = f"{filter_inputs}concat=n={len(file_paths)}:v=0:a=1"

        cmd = [
            "ffmpeg", "-y",
            *input_args,
            "-filter_complex", filter_str,
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=30)

        if result.returncode == 0 and os.path.exists(output_path):
            log_message(f"✅ Session audio: {len(file_paths)} chunks → {output_filename}")
            return f"/_upload/audio/{session_id}/{output_filename}"
        else:
            error_msg = result.stderr.decode()[:200] if result.stderr else "Unknown error"
            log_message(f"❌ Session audio ffmpeg error: {error_msg}")
            return wav_urls[0] if wav_urls else None

    except Exception as e:
        log_message(f"❌ Session audio error: {e}")
        return wav_urls[0] if wav_urls else None


def cleanup_session_audio(session_id: str) -> int:
    """
    Delete all audio files for a session.

    Called when session is deleted.
    Removes the audio directory under data/audio/{session_id}/.

    Args:
        session_id: Session identifier

    Returns:
        Number of files deleted
    """
    import shutil

    audio_dir = SESSION_AUDIO_DIR / session_id
    if not audio_dir.exists():
        return 0

    # Count files before deletion
    files = list(audio_dir.glob("*"))
    count = len(files)

    try:
        shutil.rmtree(audio_dir)
        log_message(f"🗑️ Deleted {count} audio file(s) for session {session_id[:8]}...")
    except OSError as e:
        log_message(f"⚠️ Could not delete session audio: {e}")
        return 0

    return count


def load_audio_url_as_base64(audio_url: str) -> str | None:
    """
    Load audio from URL and return as Base64 data URI.

    Converts internal URLs (/_upload/audio/...) to filesystem paths
    and returns the audio as a data: URI for HTML embedding.

    Args:
        audio_url: Internal audio URL (e.g., /_upload/audio/{session_id}/file.wav)

    Returns:
        Data URI string (data:audio/wav;base64,...) or None if failed
    """
    import base64
    import re

    # Extract path part after /_upload/audio/
    match = re.search(r'/_upload/audio/(.+)$', audio_url)
    if not match:
        log_message(f"⚠️ Invalid audio URL format: {audio_url}")
        return None

    relative_path = match.group(1)
    file_path = SESSION_AUDIO_DIR / relative_path

    if not file_path.exists():
        log_message(f"⚠️ Audio file not found: {file_path}")
        return None

    try:
        # Determine MIME type from extension
        suffix = file_path.suffix.lower()
        mime_types = {
            '.wav': 'audio/wav',
            '.mp3': 'audio/mpeg',
            '.ogg': 'audio/ogg',
            '.m4a': 'audio/mp4',
            '.flac': 'audio/flac',
        }
        mime_type = mime_types.get(suffix, 'audio/wav')

        with open(file_path, 'rb') as f:
            audio_bytes = f.read()

        base64_data = base64.b64encode(audio_bytes).decode('utf-8')
        return f"data:{mime_type};base64,{base64_data}"
    except Exception as e:
        log_message(f"⚠️ Failed to load audio: {e}")
        return None


def apply_audio_adjustments(input_file: str, pitch: float = 1.0, speed: float = 1.0) -> str | None:
    """
    Apply pitch and/or speed adjustment to audio file using ffmpeg.

    Pitch adjustment: asetrate + aresample (changes pitch without tempo)
    Speed adjustment: atempo filter (changes tempo without pitch)

    Args:
        input_file: Path to input audio file (wav or mp3)
        pitch: Pitch factor (0.8 = 20% lower, 1.0 = unchanged, 1.2 = 20% higher)
        speed: Speed factor (0.8 = 20% slower, 1.0 = unchanged, 1.2 = 20% faster)

    Returns:
        Path to adjusted file, or original file if no adjustment needed or on error
    """
    # Skip if both are 1.0 (no change needed)
    needs_pitch = abs(pitch - 1.0) >= 0.01
    needs_speed = abs(speed - 1.0) >= 0.01

    if not needs_pitch and not needs_speed:
        return input_file

    try:
        # Check if ffmpeg is available
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            log_message("⚠️ Audio: ffmpeg not available, skipping adjustments")
            return input_file
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        log_message("⚠️ Audio: ffmpeg not installed, skipping adjustments")
        return input_file

    try:
        # Determine output format based on input
        input_ext = os.path.splitext(input_file)[1].lower()
        output_file = input_file.replace(input_ext, f"_adjusted{input_ext}")

        # Get original sample rate (default 22050 for Piper, 24000 for XTTS)
        sample_rate = 24000  # Default for XTTS
        try:
            probe_result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate",
                 "-of", "default=noprint_wrappers=1:nokey=1", input_file],
                capture_output=True,
                text=True,
                timeout=5
            )
            if probe_result.returncode == 0 and probe_result.stdout.strip():
                sample_rate = int(probe_result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError, OSError):
            pass  # Use default

        # Build filter chain
        filters = []

        # Pitch adjustment: asetrate + aresample
        if needs_pitch:
            new_rate = int(sample_rate * pitch)
            filters.append(f"asetrate={new_rate}")
            filters.append(f"aresample={sample_rate}")

        # Speed adjustment: atempo (limited to 0.5-2.0 range per filter)
        if needs_speed:
            # atempo only supports 0.5 to 2.0, chain multiple for extreme values
            remaining_speed = speed
            while remaining_speed > 2.0:
                filters.append("atempo=2.0")
                remaining_speed /= 2.0
            while remaining_speed < 0.5:
                filters.append("atempo=0.5")
                remaining_speed /= 0.5
            if abs(remaining_speed - 1.0) >= 0.01:
                filters.append(f"atempo={remaining_speed}")

        filter_chain = ",".join(filters)

        adjustments = []
        if needs_pitch:
            adjustments.append(f"pitch={pitch}x")
        if needs_speed:
            adjustments.append(f"speed={speed}x")
        log_message(f"🎵 Audio: Applying {', '.join(adjustments)}")

        ffmpeg_result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", input_file,
                "-af", filter_chain,
                output_file
            ],
            capture_output=True,
            timeout=30
        )

        if ffmpeg_result.returncode == 0 and os.path.exists(output_file):
            # Replace original file with adjusted version
            os.replace(output_file, input_file)
            log_message("✅ Audio: Applied adjustments successfully")
            return input_file
        else:
            error_msg = ffmpeg_result.stderr.decode() if ffmpeg_result.stderr else "Unknown error"
            log_message(f"⚠️ Audio: ffmpeg failed: {error_msg[:200]}")
            return input_file

    except Exception as e:
        log_message(f"⚠️ Audio: Error during adjustment: {e}")
        return input_file


def apply_pitch_adjustment(input_file: str, pitch: float) -> str | None:
    """Legacy wrapper for pitch-only adjustment."""
    return apply_audio_adjustments(input_file, pitch=pitch, speed=1.0)


# ============================================================
# STREAMING TTS - Sentence Detection
# ============================================================

# Common abbreviations that should NOT be treated as sentence endings
# Pattern: word ending with period that is NOT a sentence end
ABBREVIATIONS_DE = {
    "z.b.", "z. b.", "d.h.", "d. h.", "u.a.", "u. a.", "o.ä.", "o. ä.",
    "bzw.", "ca.", "etc.", "evtl.", "ggf.", "inkl.", "max.", "min.",
    "nr.", "s.", "str.", "tel.", "usw.", "vgl.", "vs.", "z.t.",
    "dr.", "prof.", "hr.", "fr.", "ing.", "dipl.",  # Titles
    "jan.", "feb.", "mär.", "apr.", "jun.", "jul.", "aug.", "sep.", "okt.", "nov.", "dez.",  # Months
    "mo.", "di.", "mi.", "do.", "fr.", "sa.", "so.",  # Days
}

ABBREVIATIONS_EN = {
    "e.g.", "i.e.", "etc.", "vs.", "mr.", "mrs.", "ms.", "dr.", "prof.",
    "inc.", "ltd.", "corp.", "co.", "jr.", "sr.",
    "jan.", "feb.", "mar.", "apr.", "jun.", "jul.", "aug.", "sep.", "oct.", "nov.", "dec.",
    "mon.", "tue.", "wed.", "thu.", "fri.", "sat.", "sun.",
    "no.", "vol.", "ch.", "pg.", "pp.", "fig.", "approx.", "dept.",
}

# Combined set (lowercase)
ABBREVIATIONS = ABBREVIATIONS_DE | ABBREVIATIONS_EN


def extract_complete_sentences(buffer: str) -> tuple[list[str], str]:
    """
    Extract complete sentences from a text buffer.

    This function is designed for streaming TTS: it accumulates text tokens
    and returns sentences as soon as they are complete, keeping incomplete
    text in the buffer for the next call.

    Handles:
    - Standard sentence endings: . ! ?
    - German/English abbreviations (z.B., e.g., Dr., etc.)
    - Quotations and parentheses
    - Numbers with decimals (3.14, 1.5)
    - URLs (http://example.com)
    - Code blocks (```...```) - skipped entirely

    Args:
        buffer: Text accumulated so far

    Returns:
        Tuple of (list of complete sentences, remaining buffer)

    Example:
        >>> extract_complete_sentences("Hello world. This is a test")
        (['Hello world.'], ' This is a test')
        >>> extract_complete_sentences("Dr. Smith said hello. How are you?")
        (['Dr. Smith said hello.', 'How are you?'], '')
    """
    if not buffer or not buffer.strip():
        return [], buffer

    sentences = []
    remaining = buffer

    # Skip if we're in a code block (``` ... ```)
    if "```" in remaining:
        # Count occurrences - odd number means we're inside a code block
        if remaining.count("```") % 2 == 1:
            # Inside code block - don't extract sentences
            return [], buffer

    # ============================================================
    # IMPORTANT: Newline detection must happen BEFORE clean_text_for_tts()!
    #
    # clean_text_for_tts() uses .strip() which removes trailing newlines.
    # In streaming mode, the buffer might be "Heading text\n\n" (waiting for
    # next paragraph). If we clean first, the \n\n gets stripped and the
    # next chunk gets concatenated directly: "Heading textNext paragraph"
    #
    # Solution: First normalize newlines and detect paragraph breaks,
    # then clean each extracted sentence individually.
    # ============================================================

    # Normalize all newline formats to \n (LF) FIRST
    # Different systems use different line endings:
    # - Unix/Linux/macOS: \n (LF, ASCII 10)
    # - Windows: \r\n (CRLF, ASCII 13 + 10)
    # - Old Mac (pre-OS X): \r (CR, ASCII 13)
    # LLMs typically output \n, but API responses might vary
    remaining = remaining.replace('\r\n', '\n').replace('\r', '\n')

    # Regex pattern for sentence boundaries
    # Matches: . ! ? followed by:
    #   - Whitespace and uppercase letter (new sentence)
    #   - End of string (final sentence)
    #   - Quotation marks/parentheses then whitespace
    # Negative lookbehind for common abbreviations handled separately

    # Simple approach: find potential sentence ends and validate
    i = 0
    sentence_start = 0

    while i < len(remaining):
        char = remaining[i]

        # Check for paragraph break (double newline) - treat as sentence boundary
        # This handles headings without punctuation: "Ein Marmeladenbrot\n\nEin Text..."
        # The heading should be spoken separately, not concatenated with the next paragraph
        if char == '\n':
            # Check if this is a double newline (paragraph break)
            if i + 1 < len(remaining) and remaining[i + 1] == '\n':
                sentence = remaining[sentence_start:i].strip()
                if sentence and len(sentence) > 1:
                    # Clean the sentence (remove markdown, tables, etc.)
                    cleaned = clean_text_for_tts(sentence)
                    if cleaned and len(cleaned) > 1:
                        # Add period if sentence doesn't end with punctuation
                        # This ensures XTTS gets proper sentence boundaries
                        if cleaned[-1] not in '.!?:;':
                            cleaned += '.'
                        sentences.append(cleaned)
                # Skip past all the newlines (even if sentence was filtered/empty)
                next_content_start = i + 1
                while next_content_start < len(remaining) and remaining[next_content_start] in ' \t\n':
                    next_content_start += 1
                sentence_start = next_content_start
                i = next_content_start - 1  # -1 because loop will increment
            else:
                # Single newline - treat as sentence boundary if current line has no punctuation
                # This handles headings like "Ein Marmeladenbrot\nEin Text..."
                # where there's no blank line between heading and content
                sentence = remaining[sentence_start:i].strip()
                if sentence and len(sentence) > 1:
                    # If line doesn't end with punctuation, it's likely a heading
                    # Treat newline as sentence boundary and add period
                    if sentence[-1] not in '.!?:;':
                        # Clean the sentence (remove markdown, tables, etc.)
                        cleaned = clean_text_for_tts(sentence)
                        if cleaned and len(cleaned) > 1:
                            cleaned += '.'
                            sentences.append(cleaned)
                        # Always update sentence_start to skip past this content
                        # (even if it was a table row that got filtered out)
                        sentence_start = i + 1
                    # If it DOES end with punctuation, it was already extracted
                    # by the normal punctuation handling below

        # Check for colon followed by double newline (intro sentence before list/table)
        # "Hier nun die gewünschte Tabelle:\n\n| ..." → extract as sentence
        if char == ':':
            after_colon = remaining[i+1:i+3] if i+1 < len(remaining) else ""
            # Colon followed by newline(s) = sentence end (intro before list/table)
            if after_colon.startswith('\n\n') or after_colon.startswith('\n'):
                sentence = remaining[sentence_start:i+1].strip()
                if sentence and len(sentence) > 10:  # Minimum length to avoid false positives
                    # Clean the sentence (remove markdown, tables, etc.)
                    sentence = clean_text_for_tts(sentence)
                    if sentence and len(sentence) > 5:
                        sentences.append(sentence)
                    sentence_start = i + 1
                    # Skip the newlines
                    while i + 1 < len(remaining) and remaining[i + 1] in '\n\t ':
                        i += 1

        # Check for sentence-ending punctuation
        if char in '.!?':
            # ============================================================
            # STREAMING TABLE DETECTION: Don't extract inside table rows
            #
            # In streaming mode, table rows arrive piece by piece:
            #   "| Marmelade (z." → period here is NOT a sentence end!
            #
            # Check if we're currently inside a table row by looking at
            # the current line (from last newline to current position).
            # ============================================================
            current_line_start = remaining.rfind('\n', 0, i) + 1
            current_line = remaining[current_line_start:i+1]

            # If current line starts with | (table row), skip punctuation detection
            # Wait until the row is complete (newline handler will process it)
            if current_line.lstrip().startswith('|'):
                i += 1
                continue

            # Get context around this character
            before = remaining[max(0, i-10):i+1].lower()
            after = remaining[i+1:i+3] if i+1 < len(remaining) else ""

            # Check if this is a real sentence end
            is_sentence_end = False

            if char in '!?':
                # Exclamation and question marks are almost always sentence ends
                is_sentence_end = True
            elif char == '.':
                # Period needs more careful checking
                is_abbreviation = False

                # Check against known abbreviations
                for abbr in ABBREVIATIONS:
                    if before.endswith(abbr):
                        is_abbreviation = True
                        break

                # Check for decimal numbers (1.5, 3.14)
                if not is_abbreviation and i > 0 and i < len(remaining) - 1:
                    char_before = remaining[i-1]
                    char_after = remaining[i+1] if i+1 < len(remaining) else ""
                    if char_before.isdigit() and char_after.isdigit():
                        is_abbreviation = True  # It's a decimal number

                # Check for URLs
                if not is_abbreviation:
                    url_context = remaining[max(0, i-20):i+10].lower()
                    if "http" in url_context or "www." in url_context or ".com" in url_context:
                        is_abbreviation = True

                # Check for ellipsis (...)
                if not is_abbreviation and i >= 2:
                    if remaining[i-2:i+1] == "...":
                        # Ellipsis at end of sentence IS a sentence end
                        # But only if followed by space+uppercase or end
                        if after and after[0].isupper():
                            is_sentence_end = True
                        elif not after.strip():
                            is_sentence_end = True
                        is_abbreviation = True  # Don't double-check

                if not is_abbreviation:
                    # Real sentence end if followed by:
                    # - Whitespace (or end of string)
                    # - Whitespace + uppercase letter
                    # - Closing quote/paren then whitespace
                    if not after:
                        # End of buffer - might be complete sentence
                        is_sentence_end = True
                    elif after[0] in ' \n\t':
                        # Followed by whitespace
                        if len(after) > 1 and after[1].isupper():
                            is_sentence_end = True
                        elif len(after) == 1:
                            # Just whitespace at end - likely sentence end
                            is_sentence_end = True
                    elif after[0] in '"\')»"':
                        # Closing quote/paren - check what's after that
                        is_sentence_end = True

            if is_sentence_end:
                # Extract the sentence
                sentence = remaining[sentence_start:i+1].strip()

                # Handle closing quotes/parens that belong to the sentence
                j = i + 1
                while j < len(remaining) and remaining[j] in '"\')»"':
                    j += 1

                if j > i + 1:
                    sentence = remaining[sentence_start:j].strip()
                    i = j - 1

                if sentence and len(sentence) > 1:
                    # Clean the sentence (remove markdown, tables, etc.)
                    sentence = clean_text_for_tts(sentence)
                    if sentence and len(sentence) > 1:
                        sentences.append(sentence)

                sentence_start = i + 1

        i += 1

    # Whatever remains goes back to the buffer
    # IMPORTANT: Only strip LEADING whitespace, not trailing!
    # Trailing newlines are needed to detect paragraph breaks in the next call.
    # If we have "Heading\n\n" and strip(), the \n\n gets removed, and
    # the next chunk "Text" gets concatenated directly: "HeadingText"
    remaining = remaining[sentence_start:].lstrip()

    return sentences, remaining


def is_inside_think_block(text: str) -> bool:
    """
    Check if text ends inside an unclosed <think> block.

    Args:
        text: Text to check

    Returns:
        True if inside <think>...</think> block
    """
    # Count open and close tags
    open_count = text.lower().count("<think>")
    close_count = text.lower().count("</think>")
    return open_count > close_count


def strip_think_content_streaming(text: str) -> str:
    """
    Remove content inside <think> blocks for streaming TTS.

    Unlike strip_thinking_blocks(), this handles partial blocks
    that may span multiple streaming chunks.

    Args:
        text: Text that may contain <think> blocks

    Returns:
        Text with <think> content removed
    """
    # Remove complete <think>...</think> blocks
    result = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove any remaining <think> or </think> tags (partial blocks)
    result = re.sub(r'</?think>', '', result, flags=re.IGNORECASE)
    return result.strip()


def _edge_tts_sync(text: str, voice: str, rate: str, output_file: str) -> bool:
    """
    Synchronous Edge TTS wrapper - runs in separate event loop.

    This is needed because edge_tts uses aiohttp which can conflict with
    Reflex's event loop, causing crashes. Running in a fresh event loop
    in a thread avoids this issue.
    """

    async def _do_tts():
        tts = edge_tts.Communicate(text, voice, rate=rate)
        await tts.save(output_file)

    # Create fresh event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_do_tts())
        return True
    except Exception as e:
        log_message(f"❌ Edge TTS sync error: {type(e).__name__}: {e}")
        return False
    finally:
        loop.close()


async def generate_speech_edge(text, voice, rate="+0%"):
    """
    Edge TTS - Cloud-based Text-to-Speech

    Args:
        text: Text to synthesize
        voice: Voice name (e.g. "de-DE-KatjaNeural")
        rate: Speed adjustment (e.g. "+25%" for 25% faster)

    Returns:
        str: Path to generated MP3 file (relative URL for Reflex frontend), or None on error
    """
    import concurrent.futures

    try:
        # Edge TTS rate format: +X% or -X% (e.g., "+25%" for 25% faster)
        log_message(f"🎤 Edge TTS: voice={voice}, rate={rate}, text_length={len(text)}")

        # Validate inputs
        if not text or len(text.strip()) < 1:
            log_message("⚠️ Edge TTS: Empty text, skipping")
            return None

        # Save to uploaded_files/tts_audio/ (served via /_upload/)
        filename = _generate_tts_filename("mp3")
        output_file = str(TTS_AUDIO_DIR / filename)

        # Run Edge TTS in separate thread with its own event loop
        # This avoids conflicts with Reflex's event loop
        log_message(f"🔄 Edge TTS: Starting in thread → {output_file}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_edge_tts_sync, text, voice, rate, output_file)
            success = future.result(timeout=30)  # 30 second timeout

        if not success:
            log_message("❌ Edge TTS: Thread execution failed")
            return None

        # Verify file was created
        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            log_message(f"✅ Edge TTS: Audio saved → {output_file} ({file_size} bytes)")

            if file_size < 100:
                log_message(f"⚠️ Edge TTS: File suspiciously small ({file_size} bytes)")
                return None

            # Return relative URL - browser uses current host/port automatically
            return f"/_upload/tts_audio/{filename}"
        else:
            log_message(f"❌ Edge TTS: File not created at {output_file}")
            return None

    except concurrent.futures.TimeoutError:
        log_message("❌ Edge TTS: Timeout after 30 seconds")
        return None
    except Exception as e:
        log_message(f"❌ Edge TTS Exception: {type(e).__name__}: {e}")
        import traceback
        log_message(f"Edge TTS Traceback: {traceback.format_exc()}")
        return None


def generate_speech_piper(text, speed=1.0, voice_choice="Deutsch (Thorsten)"):
    """
    Piper TTS - Local, fast Text-to-Speech

    Args:
        text: Text to synthesize
        speed: Speed multiplier (1.0 = normal, 1.25 = 25% faster)
        voice_choice: Voice display name (e.g., "Deutsch (Thorsten)")

    Returns:
        str: Path to generated WAV file (relative URL for Reflex frontend), or None on error
    """
    from .config import PIPER_VOICES, PROJECT_ROOT

    # Save to uploaded_files/tts_audio/ (served via /_upload/)
    filename = _generate_tts_filename("wav")
    output_file = str(TTS_AUDIO_DIR / filename)

    try:
        # Get model path from PIPER_VOICES config
        voice_config = PIPER_VOICES.get(voice_choice)
        if voice_config:
            model_filename, _ = voice_config
            model_path = PROJECT_ROOT / "piper_models" / model_filename
        else:
            # Fallback to default Thorsten model
            model_path = PIPER_MODEL_PATH
            log_message(f"⚠️ Piper: Voice '{voice_choice}' not found, using default")

        # Call Piper via subprocess
        # length_scale: higher = slower (1.0 = normal, 0.8 = 1.25x faster, 0.5 = 2x faster)
        length_scale = 1.0 / speed
        log_message(f"🎤 Piper TTS: voice={voice_choice}, speed={speed}, length_scale={length_scale}")

        result = subprocess.run(
            [PIPER_BIN, "--model", str(model_path), "--output_file", output_file, "--length_scale", str(length_scale)],
            input=text.encode('utf-8'),
            capture_output=True,
            timeout=30
        )

        if result.returncode == 0 and os.path.exists(output_file):
            log_message(f"✅ Piper TTS: Audio saved → {output_file} ({os.path.getsize(output_file)} bytes)")
            # Return relative URL - browser uses current host/port automatically
            return f"/_upload/tts_audio/{filename}"
        else:
            log_message(f"❌ Piper TTS Error: {result.stderr.decode()}")
            return None

    except Exception as e:
        log_message(f"❌ Piper TTS Exception: {e}")
        return None


def generate_speech_espeak(text, speed=1.0, voice_choice="Deutsch (Roboter)"):
    """
    eSpeak TTS - Local, robotic Text-to-Speech

    Args:
        text: Text to synthesize
        speed: Speed multiplier (1.0 = normal, 1.25 = 25% faster)
        voice_choice: Voice display name (e.g., "Deutsch (Roboter)")

    Returns:
        str: Path to generated WAV file (relative URL for Reflex frontend), or None on error
    """
    from .config import ESPEAK_VOICES

    # Save to uploaded_files/tts_audio/ (served via /_upload/)
    filename = _generate_tts_filename("wav")
    output_file = str(TTS_AUDIO_DIR / filename)

    try:
        # Get voice from ESPEAK_VOICES config
        voice_config = ESPEAK_VOICES.get(voice_choice)
        if voice_config:
            voice_lang, _ = voice_config
        else:
            voice_lang = "de"
            log_message(f"⚠️ eSpeak: Voice '{voice_choice}' not found, using 'de'")

        # eSpeak speed: words per minute (default ~175, range 80-500)
        # speed 1.0 = 175 wpm, 1.25 = 220 wpm, 2.0 = 350 wpm
        wpm = int(175 * speed)
        log_message(f"🎤 eSpeak TTS: voice={voice_lang}, speed={speed}, wpm={wpm}")

        # Try espeak-ng first, fallback to espeak
        espeak_cmd = "espeak"  # Default
        try:
            result_check = subprocess.run(
                ["espeak-ng", "--version"],
                capture_output=True,
                timeout=5
            )
            if result_check.returncode == 0:
                espeak_cmd = "espeak-ng"
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            pass  # Stick with espeak

        log_message(f"🔊 eSpeak: Using command '{espeak_cmd}'")

        result = subprocess.run(
            [espeak_cmd, "-v", voice_lang, "-s", str(wpm), "-w", output_file, text],
            capture_output=True,
            timeout=30
        )

        if result.returncode == 0 and os.path.exists(output_file):
            log_message(f"✅ eSpeak TTS: Audio saved → {output_file} ({os.path.getsize(output_file)} bytes)")
            # Return relative URL - browser uses current host/port automatically
            return f"/_upload/tts_audio/{filename}"
        else:
            error_msg = result.stderr.decode() if result.stderr else "Unknown error"
            log_message(f"❌ eSpeak TTS Error: {error_msg}")
            return None

    except FileNotFoundError:
        log_message("❌ eSpeak TTS: espeak/espeak-ng not installed. Run: sudo apt install espeak-ng")
        return None
    except Exception as e:
        log_message(f"❌ eSpeak TTS Exception: {e}")
        return None


def generate_speech_xtts(text: str, speed: float = 1.0, voice_choice: str = "Claribel Dervla", language: str = "de") -> str | None:
    """
    XTTS v2 TTS - Local voice cloning TTS via Docker service.

    XTTS v2 supports voice cloning from reference audio and multilingual
    text generation. The voice character is preserved across languages.

    Args:
        text: Text to synthesize
        speed: Speed multiplier (currently unused - XTTS generates at fixed rate)
        voice_choice: Voice name (built-in speaker or custom cloned voice)
                     Custom voices are prefixed with "★ " in the UI
        language: Language code for text (de, en, es, fr, etc.)

    Returns:
        str: Path to generated WAV file (relative URL for Reflex frontend), or None on error

    Note:
        Requires XTTS Docker service running: cd docker/xtts && docker-compose up -d
    """
    import requests
    from .config import XTTS_SERVICE_URL

    # Save to data/tts_audio/ (served via /_upload/)
    filename = _generate_tts_filename("wav")
    output_file = str(TTS_AUDIO_DIR / filename)

    try:
        # Remove "★ " prefix if present (UI marker for custom voices)
        speaker = voice_choice
        if speaker.startswith("★ "):
            speaker = speaker[2:]

        log_message(f"🎤 XTTS v2: speaker={speaker}, language={language}, text_length={len(text)}")

        # Call XTTS Docker service
        # No timeout - XTTS runs async and may take long on CPU (10+ min for long texts)
        response = requests.post(
            f"{XTTS_SERVICE_URL}/tts",
            json={"text": text, "speaker": speaker, "language": language},
            timeout=None
        )

        if response.status_code == 200:
            # Save audio to file
            with open(output_file, "wb") as f:
                f.write(response.content)

            file_size = os.path.getsize(output_file)
            log_message(f"✅ XTTS v2: Audio saved → {output_file} ({file_size} bytes)")

            if file_size < 100:
                log_message(f"⚠️ XTTS v2: File suspiciously small ({file_size} bytes)")
                return None

            # Return relative URL - browser uses current host/port automatically
            return f"/_upload/tts_audio/{filename}"
        else:
            error_msg = response.text[:200] if response.text else f"HTTP {response.status_code}"
            log_message(f"❌ XTTS v2 Error: {error_msg}")
            return None

    except requests.exceptions.ConnectionError:
        log_message("❌ XTTS v2: Service not running. Start with: cd docker/xtts && docker-compose up -d")
        return None
    except Exception as e:
        log_message(f"❌ XTTS v2 Exception: {e}")
        return None


def clean_text_for_tts(text):
    """
    Prepare text for TTS output: Remove elements that sound bad when read aloud.

    This function handles CONTENT FILTERING only. TTS-specific normalization
    (punctuation, special characters) is handled by the XTTS server's
    normalize_text_for_tts() function.

    Removes:
    - <think> tags (raw LLM thinking)
    - <details>/<summary> blocks (collapsible UI elements)
    - HTML/XML tags (all generic tags like <br>, <span>, etc.)
    - Code blocks (``` ... ```) and inline code (`...`)
    - Markdown tables (| ... |) → replaced with spoken hint
    - LaTeX formulas ($...$ and $$...$$)
    - Emojis (keeps laughter emojis for XTTS to convert to "hahaha")
    - Markdown formatting (**, *, #, etc.)
    - URLs, timing metadata
    - Markdown links [text](url) → keeps text, removes URL
    - Blockquotes (> text)

    NOTE: Punctuation is NOT added here - XTTS server handles that to prevent
    issues with partial text in streaming mode.

    Args:
        text: Raw text from AI response

    Returns:
        str: Cleaned text suitable for TTS
    """
    # Remove <think> tags and content (raw thinking from LLM)
    # Note: llm_history should be clean, but this handles edge cases
    # Use IGNORECASE to catch <Think>, <THINK>, etc.
    clean_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
    # Also remove partial/unclosed think tags (streaming edge case)
    clean_text = re.sub(r'</?think>', '', clean_text, flags=re.IGNORECASE)

    # Remove <details>/<summary> blocks (collapsible UI elements) - entire blocks
    clean_text = re.sub(r'<details>.*?</details>', '', clean_text, flags=re.DOTALL | re.IGNORECASE).strip()

    # Remove ALL HTML/XML tags but keep content between them
    # Catches <br>, <span>, <div>, <p>, <b>, <i>, <u>, <strong>, <em>, etc.
    # Also catches self-closing tags like <br/>, <hr/>
    clean_text = re.sub(r'<[^>]+/?>', '', clean_text)

    # Replace code blocks (``` ... ```) with spoken hint - code sounds terrible when read aloud
    # Use .*? (non-greedy) to match content including backticks inside code
    # Use GLOBAL flag to persist across multiple calls (streaming chunks)
    def replace_code_block(m):
        global _code_hint_announced
        if not _code_hint_announced:
            _code_hint_announced = True
            return '\nHier steht Code.\n'
        return '\n'
    clean_text = re.sub(r'```.*?```', replace_code_block, clean_text, flags=re.DOTALL).strip()

    # Replace markdown tables with spoken hint
    # Tables are unreadable as speech: "pipe Name pipe Age pipe newline pipe dash dash..."
    # Instead of just removing, add a spoken cue so listener knows a table was shown
    #
    # Handle THREE cases:
    # 1. Complete table rows: starts AND ends with | (e.g., "| Name | Age |")
    # 2. Partial table rows in streaming: starts with | but incomplete (e.g., "| Marmelade (z.")
    # 3. Multi-line table blocks in non-streaming mode
    #
    # IMPORTANT for streaming: Table cells come in piece by piece, so we must detect
    # PARTIAL table content, not just complete rows!

    stripped = clean_text.strip()

    # Detect if this is multi-line content (Re-Synth mode) vs single-line (streaming mode)
    # Multi-line content should use table block replacement, not early returns
    is_multiline = '\n' in stripped

    # Checks 1-4 are for STREAMING mode only (single-line sentences)
    # In Re-Synth mode (multi-line), we skip these and use table_block_pattern below
    global _table_hint_announced, _formula_hint_announced, _code_hint_announced

    if not is_multiline:
        # Check for table content (4 patterns)
        is_table = (
            re.match(r'^\s*\|.*\|\s*$', stripped) or  # Complete table line
            stripped.startswith('|') or  # Partial table row
            stripped.count('|') >= 2 or  # Multiple pipes
            re.match(r'^\s*\|[-:\s|]+\|\s*$', stripped)  # Separator row
        )

        if is_table:
            if not _table_hint_announced:
                _table_hint_announced = True
                return "Hier wird eine Tabelle angezeigt."
            return ""

        # Check for inline formula ($...$)
        if re.search(r'\$[^$]+\$', stripped):
            if not _formula_hint_announced:
                _formula_hint_announced = True
                return "Hier steht eine Formel."
            return ""

        # Check for inline code (`...`)
        if re.search(r'`[^`]+`', stripped):
            if not _code_hint_announced:
                _code_hint_announced = True
                return "Hier steht Code."
            return ""

        # Regular text detected - reset all flags for next block
        # Only reset if there's actual readable content (words), not just:
        # - Empty strings (from filtered decorative lines ═══)
        # - Pure punctuation or formatting remnants
        # - Our own hint texts (they pass through clean_text_for_tts twice!)
        # This prevents false resets between table rows
        CONTENT_HINT_TEXTS = {
            "Hier wird eine Tabelle angezeigt.",
            "Hier steht eine Formel.",
            "Hier steht Code.",
        }
        if (stripped and
            stripped not in CONTENT_HINT_TEXTS and
            re.search(r'[a-zA-ZäöüÄÖÜß]{2,}', stripped)):
            reset_content_hint_flags()

    # Multi-line: replace table blocks with hint (Re-Synth / non-streaming full response)
    # Use GLOBAL flag to persist across multiple calls (streaming chunks)
    table_block_pattern = re.compile(r'(\|[^\n]+\|\n?)+', flags=re.MULTILINE)
    if table_block_pattern.search(clean_text):
        def replace_table(m):
            global _table_hint_announced
            if not _table_hint_announced:
                _table_hint_announced = True
                return '\nHier wird eine Tabelle angezeigt.\n'
            return '\n'
        clean_text = table_block_pattern.sub(replace_table, clean_text)

    # Clean up multiple empty lines left by table replacement
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text).strip()

    # Replace LaTeX formulas with spoken hint - both inline ($...$) and block ($$...$$)
    # Formulas like "$E = mc^2$" sound like "dollar E equals m c caret 2 dollar"
    # Use GLOBAL flag to persist across multiple calls (streaming chunks)
    def replace_formula(m):
        global _formula_hint_announced
        if not _formula_hint_announced:
            _formula_hint_announced = True
            return ' Hier steht eine Formel. '
        return ' '
    clean_text = re.sub(r'\$\$[^$]+\$\$', replace_formula, clean_text, flags=re.DOTALL)  # Block formulas
    clean_text = re.sub(r'\$[^$]+\$', replace_formula, clean_text)  # Inline formulas

    # Remove markdown links [text](url) → keep "text", remove URL
    clean_text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean_text)

    # Remove markdown images ![alt](url) → remove entirely
    clean_text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', clean_text)

    # Remove blockquotes (> at start of line) but keep the text
    clean_text = re.sub(r'^>\s*', '', clean_text, flags=re.MULTILINE)

    # Note: Multi-Agent consensus tags ([LGTM], [WEITER]) are translated to natural
    # language in add_agent_panel() BEFORE they reach chat_history. TTS speaks
    # what the user sees in the UI - no duplicate translation needed here.

    # Remove Multi-Agent round labels - these are UI markers prepended to messages
    # e.g., "[Auto-Konsens: Synthese R1]", "[Tribunal: Kritische Prüfung R2]"
    clean_text = re.sub(r'\[(Auto-Konsens|Tribunal|Devils? Advocate|Auto-Consensus):[^\]]+R\d+\]', '', clean_text, flags=re.IGNORECASE)

    # Remove most emojis, but KEEP laughter emojis for XTTS to convert to "hahaha"
    # Laughter emojis: 😂🤣😆😄😅😁🙂😊 (handled by XTTS server.py)
    # First, remove all emojis EXCEPT laughter ones
    emoji_pattern = re.compile(
        "["
        "\U0001F300-\U0001F5FF"  # Symbols & Pictographs (incl. clock faces 🕐-🕧)
        "\U0001F680-\U0001F6FF"  # Transport & Maps
        "\U0001F700-\U0001F77F"  # Alchemy Symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols & Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols & Pictographs Extended-A
        "\U0001F1E0-\U0001F1FF"  # Flags
        "\U00002600-\U000027BF"  # Misc Symbols (☀️⭐)
        "\U0000FE00-\U0000FE0F"  # Variation Selectors
        "\U0001F018-\U0001F270"  # Additional symbols
        "\U0000238C-\U00002454"  # Misc Technical
        "\u200d"                  # Zero Width Joiner
        "\ufe0f"                  # Variation Selector
        "\u3030"                  # Wavy Dash
        "]+",
        flags=re.UNICODE
    )
    clean_text = emoji_pattern.sub(r'', clean_text).strip()

    # Remove non-laughter emoticons (U+1F600-1F64F) but keep 😂🤣😆😄😅😁🙂😊
    # These are: U+1F602, U+1F923, U+1F606, U+1F604, U+1F605, U+1F601, U+1F642, U+1F60A
    laughter_emojis = {'😂', '🤣', '😆', '😄', '😅', '😁', '🙂', '😊'}
    # Remove other emoticons one by one (safer than regex for this range)
    for codepoint in range(0x1F600, 0x1F650):
        char = chr(codepoint)
        if char not in laughter_emojis:
            clean_text = clean_text.replace(char, '')

    # Replace decorative separator lines with pause (cause crackling in Piper TTS)
    # Unicode box-drawing characters: ─ (U+2500), ═ (U+2550), │ (U+2502), etc.
    # Replace with newline to create a natural pause in speech
    clean_text = re.sub(r'[─━═┄┅┈┉╌╍]+', '\n', clean_text)  # Horizontal lines → pause
    clean_text = re.sub(r'[│┃║┆┇┊┋╎╏]+', '', clean_text)   # Vertical lines → remove
    clean_text = re.sub(r'[-]{3,}', '\n', clean_text)  # ASCII dashes (---) → pause
    clean_text = re.sub(r'[=]{3,}', '\n', clean_text)  # ASCII equals (===) → pause
    clean_text = re.sub(r'[_]{3,}', '\n', clean_text)  # ASCII underscores (___) → pause

    # Remove markdown formatting and special characters
    clean_text = re.sub(r'\*\*', '', clean_text)  # Bold **text**
    clean_text = re.sub(r'\*', '', clean_text)    # Italic *text* or bullet points
    # Replace inline code with hint (if no code block hint was given already)
    # Uses same GLOBAL flag as code blocks to avoid duplicate hints
    def replace_inline_code(m):
        global _code_hint_announced
        if not _code_hint_announced:
            _code_hint_announced = True
            return ' Hier steht Code. '
        return ''
    clean_text = re.sub(r'`[^`]+`', replace_inline_code, clean_text)
    clean_text = re.sub(r'`', '', clean_text)     # Stray backticks
    clean_text = re.sub(r'#+\s', '', clean_text)  # Markdown Headers ### Text

    # Remove list markers but keep text
    clean_text = re.sub(r'^[-*+]\s+', '', clean_text, flags=re.MULTILINE)  # Bullet points
    clean_text = re.sub(r'^\d+\.\s+', '', clean_text, flags=re.MULTILINE)  # Numbered lists

    # Remove URLs (http://, https://, www.)
    clean_text = re.sub(r'https?://\S+', '', clean_text)  # http:// and https://
    clean_text = re.sub(r'www\.\S+', '', clean_text)      # www.example.com

    # Remove timing information in parentheses (TTS should not read these!)
    # Examples: "(STT: 2.5s)", "(Inference: 1.3s)", "(Agent: 45.2s, Quick, 5 sources)",
    #           "(Cache-Hit: 2.5s = LLM 2.3s)", "(Decision: 2.5s, Inference: 1.3s)"
    #           "( TTFT: 0,32s  Inference: 6,6s  133,4 tok/s  Source: Training data )"
    clean_text = re.sub(r'\s*\([^)]*\b(STT|TTFT|Inference|Inferenz|Agent|Cache-Hit|Decision|Entscheidung|TTS|tok/s|Source)[^)]*\)', '', clean_text)

    # Remove any remaining parentheses with numbers/timing patterns
    # Catches edge cases like "(2.5s)" or "(123 tok/s)" that might slip through
    clean_text = re.sub(r'\s*\(\s*[\d,\.]+\s*(s|ms|tok/s)?\s*\)', '', clean_text)

    # Remove problematic Unicode characters that Piper can't handle
    # Zero-width characters, non-breaking spaces, etc.
    clean_text = re.sub(r'[\u200b\u200c\u200d\u2060\ufeff]', '', clean_text)  # Zero-width chars
    clean_text = re.sub(r'\u00a0', ' ', clean_text)  # Non-breaking space → normal space

    # Convert dashes to punctuation BEFORE the general filter removes them
    # Gedankenstriche (EN DASH, EM DASH) mark pauses - convert to comma for natural TTS pause
    # Without this, "Text – mehr Text" becomes "Text mehr Text" (no pause, words run together)
    clean_text = clean_text.replace('–', ',')  # EN DASH (U+2013) → comma
    clean_text = clean_text.replace('—', ',')  # EM DASH (U+2014) → comma
    clean_text = clean_text.replace('‒', ',')  # FIGURE DASH (U+2012) → comma
    clean_text = clean_text.replace('―', ',')  # HORIZONTAL BAR (U+2015) → comma

    # Remove other special characters that cause "quirzel" sounds in TTS
    # Keep basic punctuation and letters (including German/French/Spanish chars)
    # This catches arrows (→←↑↓), math symbols (±×÷), etc.
    clean_text = re.sub(r'[^\w\s.,!?;:\-\'\"()\[\]äöüÄÖÜßàáâãèéêëìíîïòóôõùúûýÿñçÀÁÂÃÈÉÊËÌÍÎÏÒÓÔÕÙÚÛÝŸÑÇ\n]', ' ', clean_text)

    # Clean up multiple spaces
    clean_text = re.sub(r'  +', ' ', clean_text)

    # Clean up trailing whitespace and excessive newlines (Piper crackling fix)
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)  # Max 2 newlines
    clean_text = clean_text.strip()  # Remove leading/trailing whitespace

    # NOTE: Punctuation is handled by XTTS server's normalize_text_for_tts()
    # This avoids issues with partial text in streaming mode where "S" became "S."

    return clean_text


def cleanup_old_tts_audio(max_age_hours: int = 24) -> int:
    """
    Delete old TTS audio files from uploaded_files/tts_audio/.

    Args:
        max_age_hours: Maximum age in hours (default: 24)

    Returns:
        int: Number of deleted files
    """
    import time

    if not TTS_AUDIO_DIR.exists():
        return 0

    max_age_seconds = max_age_hours * 3600
    current_time = time.time()
    deleted = 0

    try:
        for file_path in TTS_AUDIO_DIR.glob("audio_*"):
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                if file_age > max_age_seconds:
                    file_path.unlink()
                    deleted += 1
                    log_message(f"🗑️ Deleted old TTS audio: {file_path.name} (age: {file_age / 3600:.1f}h)")

        if deleted > 0:
            log_message(f"🧹 TTS Audio Cleanup: {deleted} old files deleted")

    except Exception as e:
        log_message(f"❌ TTS cleanup error: {e}")

    return deleted


def transcribe_audio(audio_path, whisper_model, language="de"):
    """
    Transcribe audio to text with Whisper.

    Args:
        audio_path: Path to audio file
        whisper_model: Loaded WhisperModel object
        language: Language code ("de" or "en")

    Returns:
        tuple: (transcribed_text, time_in_seconds)
    """
    if audio_path is None or audio_path == "":
        return "", 0.0

    timer = Timer()
    # Use specified language for better accuracy
    segments, _ = whisper_model.transcribe(audio_path, language=language)
    stt_time = timer.elapsed()

    user_text = " ".join([s.text for s in segments])
    log_message(f"✅ STT Transcription: {user_text[:100]}{'...' if len(user_text) > 100 else ''} (Time: {stt_time:.1f}s)")

    return user_text, stt_time


async def generate_tts(text, voice_choice, speed_choice, tts_engine, pitch: float = 1.0, agent: str = "aifred"):
    """
    Generate TTS audio from text (Edge, XTTS, Piper or eSpeak).

    Args:
        text: Text for TTS (already cleaned)
        voice_choice: Voice display name (e.g. "Deutsch (Katja)" for Edge, "★ aifred" for XTTS custom)
        speed_choice: Speed multiplier (e.g. 1.25)
        tts_engine: Engine name (e.g. "Edge TTS (Cloud, best quality)")
        pitch: Pitch factor (0.8 = 20% lower, 1.0 = unchanged, 1.2 = 20% higher)
        agent: Agent name for filename prefix (e.g. "sokrates", "aifred")

    Returns:
        str: Path to generated audio file, or None
    """
    from .config import EDGE_TTS_VOICES, PIPER_VOICES, ESPEAK_VOICES

    # Set agent for filename generation BEFORE any TTS call
    # This ensures correct filename even with parallel create_task calls
    set_tts_agent(agent)

    try:
        audio_url = None
        loop = asyncio.get_running_loop()

        if "XTTS" in tts_engine:
            # XTTS v2 (local via Docker) - voice cloning TTS
            # Supports custom voices (★ prefix) and built-in speakers
            # Speed is applied via ffmpeg post-processing (XTTS generates at fixed rate)
            # Run in thread pool to avoid blocking event loop during HTTP call
            audio_url = await loop.run_in_executor(
                None, generate_speech_xtts, text, 1.0, voice_choice, "de"
            )
        elif "Piper" in tts_engine:
            # Piper TTS (local) - synchronous subprocess call
            # Use Piper-specific voice, fallback to first available if not found
            if voice_choice not in PIPER_VOICES:
                voice_choice = list(PIPER_VOICES.keys())[0] if PIPER_VOICES else "Deutsch (Thorsten)"
                log_message(f"⚠️ TTS: Voice not available for Piper, using: {voice_choice}")
            # Run in thread pool to avoid blocking event loop
            audio_url = await loop.run_in_executor(
                None, generate_speech_piper, text, speed_choice, voice_choice
            )
        elif "eSpeak" in tts_engine:
            # eSpeak TTS (local, robotic) - synchronous subprocess call
            if voice_choice not in ESPEAK_VOICES:
                voice_choice = list(ESPEAK_VOICES.keys())[0] if ESPEAK_VOICES else "Deutsch (Roboter)"
                log_message(f"⚠️ TTS: Voice not available for eSpeak, using: {voice_choice}")
            # Run in thread pool to avoid blocking event loop
            audio_url = await loop.run_in_executor(
                None, generate_speech_espeak, text, speed_choice, voice_choice
            )
        else:
            # Edge TTS (Cloud) - async API call (already non-blocking)
            rate = f"+{int((speed_choice - 1.0) * 100)}%"
            # Use Edge-specific voice, fallback if not found
            voice_id = EDGE_TTS_VOICES.get(voice_choice, "de-DE-KatjaNeural")
            audio_url = await generate_speech_edge(text, voice_id, rate)

        # Apply pitch adjustment if needed (works for all engines via ffmpeg)
        # Note: Speed is handled by browser playback rate (faster, no delay)
        if audio_url and abs(pitch - 1.0) >= 0.01:
            filename = audio_url.split("/")[-1]
            local_path = str(TTS_AUDIO_DIR / filename)
            await loop.run_in_executor(
                None, apply_audio_adjustments, local_path, pitch, 1.0
            )

        return audio_url

    except Exception as e:
        log_message(f"❌ TTS Error: {e}")
        import traceback
        log_message(f"Traceback: {traceback.format_exc()}")
        return None


# ============================================================
# CLEANUP: Delete old TTS audio files on app startup/shutdown
# ============================================================

@atexit.register
def _cleanup_tts_on_exit():
    """Cleanup old TTS audio files on app exit"""
    try:
        cleanup_old_tts_audio(max_age_hours=24)
    except Exception:
        pass

# Run cleanup on module import (app startup)
try:
    cleanup_old_tts_audio(max_age_hours=24)
except Exception:
    pass


# ============================================================
# WHISPER STT MODEL MANAGEMENT
# ============================================================
# Module-level Whisper model (shared across all sessions for efficiency)
_whisper_model = None


def unload_whisper_model():
    """Unload Whisper model from memory (free GPU/RAM)"""
    global _whisper_model
    if _whisper_model is not None:
        _whisper_model = None
        from .process_utils import cleanup_gpu_memory
        cleanup_gpu_memory()
        log_message("🗑️ Whisper: Model unloaded from memory")
    else:
        log_message("⚠️ Whisper: No model loaded")


def initialize_whisper_model(model_name: str = "small"):
    """
    Initialize Whisper STT model (module-level, shared across sessions)

    Args:
        model_name: Whisper model size (tiny, base, small, medium, large)

    Returns:
        WhisperModel instance or None on failure
    """
    global _whisper_model

    if _whisper_model is not None:
        log_message(f"✅ Whisper: Model already loaded ({model_name})")
        return _whisper_model

    try:
        from faster_whisper import WhisperModel
        from .config import WHISPER_MODELS, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE

        # Extract model ID from display name (e.g., "small (466MB, ...)" -> "small")
        model_id = WHISPER_MODELS.get(model_name, model_name)

        log_message(f"🎤 Whisper: Loading model '{model_id}'...")

        # Use device and compute type from config.py
        # Default: CPU to preserve GPU VRAM for LLM inference
        device = WHISPER_DEVICE
        compute_type = WHISPER_COMPUTE_TYPE

        _whisper_model = WhisperModel(model_id, device=device, compute_type=compute_type)

        log_message(f"✅ Whisper: Model '{model_id}' loaded on {device} ({compute_type})")
        return _whisper_model

    except ImportError as e:
        log_message(f"❌ Whisper: faster-whisper not installed: {e}")
        log_message("   Install with: pip install faster-whisper")
        return None

    except Exception as e:
        log_message(f"❌ Whisper: Failed to load model: {e}")
        return None


def get_whisper_model():
    """Get the currently loaded Whisper model (or None if not loaded)"""
    global _whisper_model
    return _whisper_model
