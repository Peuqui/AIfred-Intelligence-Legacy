"""
Audio Processing Module - TTS and STT functionality

This module handles Text-to-Speech (Edge TTS, Piper TTS) and Speech-to-Text
(Whisper) operations, including text cleanup for TTS.
"""

import os
import re
import time
import subprocess
import asyncio
import atexit
import edge_tts
from .config import VOICES, PIPER_MODEL_PATH, PROJECT_ROOT
from .logging_utils import log_message


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


def _edge_tts_sync(text: str, voice: str, rate: str, output_file: str) -> bool:
    """
    Synchronous Edge TTS wrapper - runs in separate event loop.

    This is needed because edge_tts uses aiohttp which can conflict with
    Reflex's event loop, causing crashes. Running in a fresh event loop
    in a thread avoids this issue.
    """
    import asyncio

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
        # Edge TTS rate Format: +X% oder -X% (z.B. "+25%" für 25% schneller)
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

            # Return FULL URL with backend host (frontend doesn't serve /_upload/)
            from .config import BACKEND_API_URL
            return f"{BACKEND_API_URL}/_upload/tts_audio/{filename}"
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

        # Piper via subprocess aufrufen
        # length_scale: höher = langsamer (1.0 = normal, 0.8 = 1.25x schneller, 0.5 = 2x schneller)
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
            # Return FULL URL with backend host (frontend doesn't serve /_upload/)
            from .config import BACKEND_API_URL
            return f"{BACKEND_API_URL}/_upload/tts_audio/{filename}"
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
            # Return FULL URL with backend host (frontend doesn't serve /_upload/)
            from .config import BACKEND_API_URL
            return f"{BACKEND_API_URL}/_upload/tts_audio/{filename}"
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
    Bereitet Text für TTS-Ausgabe vor: Entfernt <think> Tags, Emojis,
    Markdown, URLs und andere störende Elemente.

    Args:
        text: Roh-Text von AI-Antwort

    Returns:
        str: Bereinigter Text für TTS
    """
    # Entferne <think> Tags und Inhalt
    clean_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # Entferne ALLE Emojis (umfassende Unicode-Bereiche)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Symbole & Piktogramme (inkl. Uhrzeiten 🕐-🕧)
        "\U0001F680-\U0001F6FF"  # Transport & Karten
        "\U0001F700-\U0001F77F"  # Alchemie Symbole
        "\U0001F780-\U0001F7FF"  # Geometrische Formen Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols & Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols & Pictographs Extended-A
        "\U0001F1E0-\U0001F1FF"  # Flaggen
        "\U00002600-\U000027BF"  # Misc Symbole (☀️⭐)
        "\U0000FE00-\U0000FE0F"  # Variation Selectors
        "\U0001F018-\U0001F270"  # Weitere Symbole
        "\U0000238C-\U00002454"  # Misc Technical
        "\u200d"                  # Zero Width Joiner
        "\ufe0f"                  # Variation Selector
        "\u3030"                  # Wavy Dash
        "]+",
        flags=re.UNICODE
    )
    clean_text = emoji_pattern.sub(r'', clean_text).strip()

    # Entferne Markdown-Formatierung und Sonderzeichen
    clean_text = re.sub(r'\*\*', '', clean_text)  # Bold **text**
    clean_text = re.sub(r'\*', '', clean_text)    # Italic *text* oder Bullet-Points
    clean_text = re.sub(r'`', '', clean_text)     # Code `text`
    clean_text = re.sub(r'#+\s', '', clean_text)  # Markdown Headers ### Text

    # Entferne URLs (http://, https://, www.)
    clean_text = re.sub(r'https?://\S+', '', clean_text)  # http:// und https://
    clean_text = re.sub(r'www\.\S+', '', clean_text)      # www.beispiel.de

    # Entferne Timing-Informationen in Klammern (TTS soll diese nicht vorlesen!)
    # Beispiele: "(STT: 2.5s)", "(Inferenz: 1.3s)", "(Agent: 45.2s, Schnell, 5 Quellen)",
    #            "(Cache-Hit: 2.5s = LLM 2.3s)", "(Entscheidung: 2.5s, Inferenz: 1.3s)"
    clean_text = re.sub(r'\s*\([^)]*\b(STT|Inferenz|Agent|Cache-Hit|Entscheidung|TTS)[^)]*\)', '', clean_text)

    return clean_text


def cleanup_old_tts_audio(max_age_hours: int = 24) -> int:
    """
    Löscht alte TTS-Audio-Dateien aus uploaded_files/tts_audio/.

    Args:
        max_age_hours: Maximales Alter in Stunden (default: 24)

    Returns:
        int: Anzahl gelöschter Dateien
    """
    import time
    from pathlib import Path

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
    Transkribiert Audio zu Text mit Whisper.

    Args:
        audio_path: Pfad zur Audio-Datei
        whisper_model: Geladenes WhisperModel Objekt
        language: Language code ("de" or "en")

    Returns:
        tuple: (transkribierter_text, zeit_in_sekunden)
    """
    if audio_path is None or audio_path == "":
        return "", 0.0

    start_time = time.time()
    # Use specified language for better accuracy
    segments, _ = whisper_model.transcribe(audio_path, language=language)
    stt_time = time.time() - start_time

    user_text = " ".join([s.text for s in segments])
    log_message(f"✅ STT Transkription: {user_text[:100]}{'...' if len(user_text) > 100 else ''} (Time: {stt_time:.1f}s)")

    return user_text, stt_time


async def generate_tts(text, voice_choice, speed_choice, tts_engine):
    """
    Generiert TTS-Audio aus Text (Edge, Piper oder eSpeak).

    Args:
        text: Text für TTS (bereits bereinigt)
        voice_choice: Voice display name (z.B. "Deutsch (Katja)" für Edge, "Deutsch (Thorsten)" für Piper)
        speed_choice: Speed multiplier (z.B. 1.25)
        tts_engine: Engine name (z.B. "Edge TTS (Cloud, beste Qualität)")

    Returns:
        str: Pfad zur generierten Audio-Datei, oder None
    """
    from .config import EDGE_TTS_VOICES, PIPER_VOICES, ESPEAK_VOICES

    try:
        if "Piper" in tts_engine:
            # Piper TTS (lokal) - synchronous subprocess call
            # Use Piper-specific voice, fallback to first available if not found
            if voice_choice not in PIPER_VOICES:
                voice_choice = list(PIPER_VOICES.keys())[0] if PIPER_VOICES else "Deutsch (Thorsten)"
                log_message(f"⚠️ TTS: Voice not available for Piper, using: {voice_choice}")
            return generate_speech_piper(text, speed_choice, voice_choice)
        elif "eSpeak" in tts_engine:
            # eSpeak TTS (lokal, roboterhaft) - synchronous subprocess call
            if voice_choice not in ESPEAK_VOICES:
                voice_choice = list(ESPEAK_VOICES.keys())[0] if ESPEAK_VOICES else "Deutsch (Roboter)"
                log_message(f"⚠️ TTS: Voice not available for eSpeak, using: {voice_choice}")
            return generate_speech_espeak(text, speed_choice, voice_choice)
        else:
            # Edge TTS (Cloud) - async API call
            rate = f"+{int((speed_choice - 1.0) * 100)}%"
            # Use Edge-specific voice, fallback if not found
            voice_id = EDGE_TTS_VOICES.get(voice_choice, "de-DE-KatjaNeural")
            return await generate_speech_edge(text, voice_id, rate)
    except Exception as e:
        log_message(f"❌ TTS Fehler: {e}")
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
