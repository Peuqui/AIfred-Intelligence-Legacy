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
from .config import PIPER_MODEL_PATH, PROJECT_ROOT
from .logging_utils import log_message
from .timer import Timer


# Determine platform-specific Piper binary path
if os.name == 'nt':  # Windows
    PIPER_BIN = PROJECT_ROOT / "venv" / "Scripts" / "piper.exe"
else:  # Linux/Mac
    PIPER_BIN = PROJECT_ROOT / "venv" / "bin" / "piper"

# TTS Audio output directory
# IMPORTANT: Use uploaded_files/ instead of assets/ to avoid hot-reload!
# Reflex watches assets/ and restarts the server when files change.
# uploaded_files/ is served via /_upload/ endpoint and is NOT watched.
TTS_AUDIO_DIR = PROJECT_ROOT / "uploaded_files" / "tts_audio"
TTS_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def apply_pitch_adjustment(input_file: str, pitch: float) -> str | None:
    """
    Apply pitch adjustment to audio file using ffmpeg.

    The pitch adjustment works by changing the sample rate (asetrate) and then
    resampling back to the original rate (aresample). This changes pitch without
    changing tempo.

    Args:
        input_file: Path to input audio file (wav or mp3)
        pitch: Pitch factor (0.8 = 20% lower, 1.0 = unchanged, 1.2 = 20% higher)

    Returns:
        Path to pitch-adjusted file, or original file if pitch is 1.0 or on error
    """
    # Skip if pitch is 1.0 (no change needed)
    if abs(pitch - 1.0) < 0.01:
        return input_file

    try:
        # Check if ffmpeg is available
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        if result.returncode != 0:
            log_message("⚠️ Pitch: ffmpeg not available, skipping pitch adjustment")
            return input_file
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        log_message("⚠️ Pitch: ffmpeg not installed, skipping pitch adjustment")
        return input_file

    try:
        # Determine output format based on input
        input_ext = os.path.splitext(input_file)[1].lower()
        output_file = input_file.replace(input_ext, f"_pitch{input_ext}")

        # Get original sample rate (default 22050 for Piper, 24000 for Edge TTS)
        # We'll use ffprobe to detect it, or fall back to a reasonable default
        sample_rate = 22050  # Default for Piper
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

        # Apply pitch adjustment:
        # asetrate changes playback rate (affects both pitch and tempo)
        # aresample brings it back to original rate (restores tempo, keeps new pitch)
        new_rate = int(sample_rate * pitch)

        log_message(f"🎵 Pitch: Adjusting {pitch}x (sample rate {sample_rate} → {new_rate} → {sample_rate})")

        ffmpeg_result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", input_file,
                "-af", f"asetrate={new_rate},aresample={sample_rate}",
                output_file
            ],
            capture_output=True,
            timeout=30
        )

        if ffmpeg_result.returncode == 0 and os.path.exists(output_file):
            # Replace original file with pitch-adjusted version
            os.replace(output_file, input_file)
            log_message(f"✅ Pitch: Applied {pitch}x adjustment")
            return input_file
        else:
            error_msg = ffmpeg_result.stderr.decode() if ffmpeg_result.stderr else "Unknown error"
            log_message(f"⚠️ Pitch: ffmpeg failed: {error_msg[:200]}")
            return input_file

    except Exception as e:
        log_message(f"⚠️ Pitch: Error during adjustment: {e}")
        return input_file


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
        filename = f"audio_{int(time.time() * 1000)}.mp3"
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
    filename = f"audio_{int(time.time() * 1000)}.wav"
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
    filename = f"audio_{int(time.time() * 1000)}.wav"
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


def clean_text_for_tts(text):
    """
    Prepare text for TTS output: Remove elements that sound bad when read aloud.

    Removes:
    - <think> tags (raw LLM thinking)
    - <details> blocks (collapsible UI elements)
    - Code blocks (``` ... ```) and inline code (`...`)
    - Markdown tables (| ... |)
    - LaTeX formulas ($...$ and $$...$$)
    - Emojis, markdown formatting, URLs
    - Timing metadata (Inference: X.Xs, etc.)

    Args:
        text: Raw text from AI response

    Returns:
        str: Cleaned text suitable for TTS
    """
    # Remove <think> tags and content (raw thinking from LLM)
    clean_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # Remove <details> blocks (collapsible UI elements like thinking process, HTML preview)
    # These contain debug info that should NOT be read aloud
    clean_text = re.sub(r'<details[^>]*>.*?</details>', '', clean_text, flags=re.DOTALL).strip()

    # Remove code blocks (``` ... ```) - code sounds terrible when read aloud
    clean_text = re.sub(r'```[^`]*```', '', clean_text, flags=re.DOTALL).strip()

    # Remove markdown tables (lines starting with |)
    # Tables are unreadable as speech: "pipe Name pipe Age pipe newline pipe dash dash..."
    clean_text = re.sub(r'^\|.*\|$', '', clean_text, flags=re.MULTILINE).strip()
    # Clean up multiple empty lines left by table removal
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text).strip()

    # Remove LaTeX formulas - both inline ($...$) and block ($$...$$)
    # Formulas like "$E = mc^2$" sound like "dollar E equals m c caret 2 dollar"
    clean_text = re.sub(r'\$\$[^$]+\$\$', '', clean_text, flags=re.DOTALL).strip()  # Block formulas
    clean_text = re.sub(r'\$[^$]+\$', '', clean_text).strip()  # Inline formulas

    # Remove ALL emojis (comprehensive Unicode ranges)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
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
    clean_text = re.sub(r'`[^`]+`', '', clean_text)  # Inline code `variable` - remove entirely
    clean_text = re.sub(r'`', '', clean_text)     # Stray backticks
    clean_text = re.sub(r'#+\s', '', clean_text)  # Markdown Headers ### Text

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

    # Clean up trailing whitespace and excessive newlines (Piper crackling fix)
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)  # Max 2 newlines
    clean_text = clean_text.strip()  # Remove leading/trailing whitespace

    # Ensure text ends with proper punctuation (fixes Piper "PFFT/HÖ" artifacts)
    # Piper needs a clear sentence ending, otherwise it produces artifacts
    if clean_text and clean_text[-1] not in '.!?:;':
        clean_text += '.'

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


async def generate_tts(text, voice_choice, speed_choice, tts_engine, pitch: float = 1.0):
    """
    Generate TTS audio from text (Edge, Piper or eSpeak).

    Args:
        text: Text for TTS (already cleaned)
        voice_choice: Voice display name (e.g. "Deutsch (Katja)" for Edge, "Deutsch (Thorsten)" for Piper)
        speed_choice: Speed multiplier (e.g. 1.25)
        tts_engine: Engine name (e.g. "Edge TTS (Cloud, best quality)")
        pitch: Pitch factor (0.8 = 20% lower, 1.0 = unchanged, 1.2 = 20% higher)

    Returns:
        str: Path to generated audio file, or None
    """
    from .config import EDGE_TTS_VOICES, PIPER_VOICES, ESPEAK_VOICES

    try:
        audio_url = None

        if "Piper" in tts_engine:
            # Piper TTS (local) - synchronous subprocess call
            # Use Piper-specific voice, fallback to first available if not found
            if voice_choice not in PIPER_VOICES:
                voice_choice = list(PIPER_VOICES.keys())[0] if PIPER_VOICES else "Deutsch (Thorsten)"
                log_message(f"⚠️ TTS: Voice not available for Piper, using: {voice_choice}")
            audio_url = generate_speech_piper(text, speed_choice, voice_choice)
        elif "eSpeak" in tts_engine:
            # eSpeak TTS (local, robotic) - synchronous subprocess call
            if voice_choice not in ESPEAK_VOICES:
                voice_choice = list(ESPEAK_VOICES.keys())[0] if ESPEAK_VOICES else "Deutsch (Roboter)"
                log_message(f"⚠️ TTS: Voice not available for eSpeak, using: {voice_choice}")
            audio_url = generate_speech_espeak(text, speed_choice, voice_choice)
        else:
            # Edge TTS (Cloud) - async API call
            rate = f"+{int((speed_choice - 1.0) * 100)}%"
            # Use Edge-specific voice, fallback if not found
            voice_id = EDGE_TTS_VOICES.get(voice_choice, "de-DE-KatjaNeural")
            audio_url = await generate_speech_edge(text, voice_id, rate)

        # Apply pitch adjustment if needed (works for all engines via ffmpeg)
        if audio_url and abs(pitch - 1.0) >= 0.01:
            # Extract local file path from URL
            # URL format: http://host:port/_upload/tts_audio/filename.ext
            filename = audio_url.split("/")[-1]
            local_path = str(TTS_AUDIO_DIR / filename)
            apply_pitch_adjustment(local_path, pitch)
            # URL stays the same, file was modified in-place

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
