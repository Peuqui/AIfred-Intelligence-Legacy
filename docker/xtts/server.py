"""
Coqui XTTS v2 HTTP Server for AIfred.

Provides a simple REST API for text-to-speech generation using XTTS v2.
Supports multilingual code-switching (DE/EN mixed text) automatically.

XTTS v2 is a voice cloning model - it requires a reference audio to clone.
We provide built-in speaker embeddings from the model's speaker library,
plus support for custom voice cloning from WAV files.

**Smart Device Selection:**
Automatically detects available VRAM and decides GPU vs CPU:
- If CUDA available AND >= VRAM_THRESHOLD free: use GPU
- Otherwise: use CPU (slower but doesn't compete with Ollama)

Usage:
    POST /tts
    {
        "text": "Das ist quite interessant",
        "language": "de",
        "speaker": "Claribel Dervla"  // or custom voice name
    }
    Returns: WAV audio file

    POST /voices/clone (multipart/form-data)
    - audio: WAV file (6-10 seconds of speech, mono, 22-24kHz)
    - name: Voice name to save as
    Returns: {"success": true, "voice": "name"}
"""

import os
import tempfile
import logging
from pathlib import Path
from flask import Flask, request, send_file, jsonify, render_template_string

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ============================================================
# VRAM Configuration
# ============================================================
# Minimum free VRAM required to use GPU (in GB)
# XTTS needs ~1.5-2GB, we require a bit more headroom
VRAM_THRESHOLD_GB = float(os.environ.get("XTTS_VRAM_THRESHOLD", "2.0"))

# Force CPU mode (override auto-detection)
FORCE_CPU = os.environ.get("XTTS_FORCE_CPU", "").lower() in ("1", "true", "yes")

# Lazy loading - model loaded on first request
_model_name = "tts_models/multilingual/multi-dataset/xtts_v2"
_config = None
_synthesizer = None
_speaker_embeddings = None  # Pre-loaded speaker embeddings (built-in)
_custom_voices = {}  # Custom cloned voices
_device = None  # "cuda" or "cpu" - set on model load

# Paths
CUSTOM_VOICES_DIR = Path("/app/custom_voices")  # Persistent storage for embeddings
REFERENCE_AUDIO_DIR = Path("/app/voices")  # Reference WAV files (mounted from host)

# Default speaker from XTTS speaker library
DEFAULT_SPEAKER = "Claribel Dervla"

# XTTS has a hard limit of 400 tokens (~250-350 characters depending on language)
# We use a conservative limit to stay safely within the token limit
MAX_CHUNK_CHARS = int(os.environ.get("XTTS_MAX_CHUNK_CHARS", "250"))

# ============================================================
# Inference Parameters (configurable via environment variables)
# ============================================================
# These can be tuned to reduce hallucinations/repetitions
# See: https://github.com/coqui-ai/TTS/discussions/4146
#
# Lower temperature = more stable, less creative
# Higher repetition_penalty = prevents repeating
# Lower top_k/top_p = more deterministic output

XTTS_TEMPERATURE = float(os.environ.get("XTTS_TEMPERATURE", "0.65"))
XTTS_REPETITION_PENALTY = float(os.environ.get("XTTS_REPETITION_PENALTY", "15.0"))
XTTS_LENGTH_PENALTY = float(os.environ.get("XTTS_LENGTH_PENALTY", "1.0"))
XTTS_TOP_K = int(os.environ.get("XTTS_TOP_K", "30"))
XTTS_TOP_P = float(os.environ.get("XTTS_TOP_P", "0.75"))

logger.info(f"XTTS Inference Parameters: temperature={XTTS_TEMPERATURE}, "
            f"repetition_penalty={XTTS_REPETITION_PENALTY}, length_penalty={XTTS_LENGTH_PENALTY}, "
            f"top_k={XTTS_TOP_K}, top_p={XTTS_TOP_P}")


def normalize_text_for_tts(text: str) -> str:
    """
    Minimal XTTS-specific text normalization.

    This function handles ONLY what's necessary for clean XTTS output:
    - Convert laughter emojis to "hahaha" (sounds natural)
    - Remove other emojis (unpronounceable)
    - Remove special characters that cause "quirzel" sounds
    - Ensure proper punctuation for natural pauses (prevents hallucinations)
    - Replace colons with periods (colons cause rushed speech)

    Content filtering (Markdown, code blocks, tables, <think> tags, etc.)
    is the responsibility of the client (e.g., AIfred's clean_text_for_tts).

    Based on community findings:
    - https://github.com/coqui-ai/TTS/discussions/4146
    - https://huggingface.co/coqui/XTTS-v2/discussions/104

    Args:
        text: Text input (should already be content-filtered by client)

    Returns:
        Normalized text suitable for XTTS synthesis
    """
    import re

    if not text or not text.strip():
        return text

    text = text.strip()

    # ============================================================
    # Phase 1: Emoji handling
    # ============================================================

    # Convert laughter emojis to "hahaha" (tested, sounds natural)
    laughter_emojis = ['😂', '🤣', '😆', '😄', '😅', '😁', '🙂', '😊']
    for emoji in laughter_emojis:
        text = text.replace(emoji, ' hahaha ')

    # Remove all other emojis (unpronounceable)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"  # enclosed characters
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols extended
        "\U00002600-\U000026FF"  # misc symbols
        "\U00002700-\U000027BF"  # dingbats
        "]+",
        flags=re.UNICODE
    )
    text = emoji_pattern.sub('', text)

    # ============================================================
    # Phase 2: Remove characters that cause "quirzel" sounds
    # ============================================================

    # Keep basic punctuation and letters (including German/European chars)
    # Allow: letters, numbers, basic punctuation, spaces
    text = re.sub(r'[^\w\s.,!?;:\-\'\"()\[\]äöüÄÖÜßàáâãèéêëìíîïòóôõùúûýÿñçÀÁÂÃÈÉÊËÌÍÎÏÒÓÔÕÙÚÛÝŸÑÇ\n]', ' ', text)

    # Clean up multiple spaces
    text = re.sub(r'  +', ' ', text)

    # ============================================================
    # Phase 3: Ensure proper punctuation for natural pauses
    # ============================================================

    # Replace colons with periods for better pauses in speech
    # Preserves time formats (19:20) and URLs (https://)
    # Regex: Replace : only if NOT between digits and NOT before //
    text = re.sub(r'(?<!\d):(?!\d|//)', '.', text)

    # Process lines - add punctuation where missing
    lines = text.split('\n')
    normalized_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            normalized_lines.append('')
            continue

        # Add period if line ends without sentence-ending punctuation
        # This prevents XTTS hallucinations
        if not re.search(r'[.!?]["\'\)\]»"]*$', line):
            line = line + '.'
            logger.debug(f"Added '.' to line: '{line}'")

        normalized_lines.append(line)

    result = '\n'.join(normalized_lines)

    # Final check: ensure text ends with proper punctuation
    if result and not re.search(r'[.!?]["\'\)\]»"]*$', result):
        result = result + '.'

    return result.strip()


def split_text_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """
    Split text into chunks that fit within XTTS token limit.

    XTTS has a hard limit of 400 tokens per generation.
    We split by sentences first, then by clauses if needed.

    Args:
        text: The text to split
        max_chars: Maximum characters per chunk (default: 250, conservative for token limit)

    Returns:
        List of text chunks
    """
    import re

    # If text is already short enough, return as-is
    if len(text) <= max_chars:
        return [text]

    chunks = []

    # First, split by sentence-ending punctuation
    # Match: . ! ? followed by space or end of string
    # Also handle German quotation marks: »« „"
    raw_sentences = re.split(r'(?<=[.!?])\s+', text)

    # Post-process: Merge ordinal numbers (22. Januar) that were incorrectly split
    sentences = []
    i = 0
    while i < len(raw_sentences):
        sentence = raw_sentences[i]

        # Check if sentence ends with ordinal number (1-3 digits + period)
        # and next sentence starts with uppercase word (month, noun, etc.)
        if i + 1 < len(raw_sentences) and re.search(r'\d{1,3}\.$', sentence):
            next_sentence = raw_sentences[i + 1]
            # Common German month names and continuation patterns
            if re.match(r'^[A-ZÄÖÜ]', next_sentence):
                # Likely an ordinal number continuation - merge them
                sentence = sentence + ' ' + next_sentence
                i += 1  # Skip next sentence since we merged it
                logger.debug(f"Merged ordinal: '{sentence}'")

        sentences.append(sentence)
        i += 1

    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # If this sentence alone is too long, split by comma/semicolon
        if len(sentence) > max_chars:
            # Save current chunk if any
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""

            # Split long sentence by clauses (comma, semicolon, colon, dash)
            clauses = re.split(r'(?<=[,;:\-–—])\s+', sentence)

            for clause in clauses:
                clause = clause.strip()
                if not clause:
                    continue

                # If even a clause is too long, force-split by words
                if len(clause) > max_chars:
                    words = clause.split()
                    temp_chunk = ""
                    for word in words:
                        if len(temp_chunk) + len(word) + 1 <= max_chars:
                            temp_chunk = f"{temp_chunk} {word}".strip()
                        else:
                            if temp_chunk:
                                chunks.append(temp_chunk)
                            temp_chunk = word
                    if temp_chunk:
                        # Don't append yet, might combine with next clause
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = temp_chunk
                else:
                    # Clause fits, try to combine
                    if len(current_chunk) + len(clause) + 1 <= max_chars:
                        current_chunk = f"{current_chunk} {clause}".strip()
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = clause
        else:
            # Sentence fits within limit
            if len(current_chunk) + len(sentence) + 1 <= max_chars:
                current_chunk = f"{current_chunk} {sentence}".strip()
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk.strip())

    # Filter out empty chunks
    chunks = [c for c in chunks if c.strip()]

    logger.info(f"Split text ({len(text)} chars) into {len(chunks)} chunks")
    for i, chunk in enumerate(chunks):
        logger.debug(f"  Chunk {i+1}: {len(chunk)} chars - '{chunk[:50]}...'")

    return chunks


def concatenate_audio_arrays(audio_arrays: list, sample_rate: int = 24000) -> "np.ndarray":
    """
    Concatenate multiple audio arrays into one.

    Adds a small pause between chunks for natural speech.

    Args:
        audio_arrays: List of numpy arrays containing audio samples
        sample_rate: Sample rate (default: 24000 for XTTS)

    Returns:
        Single numpy array with all audio concatenated
    """
    import numpy as np

    if not audio_arrays:
        return np.array([], dtype=np.float32)

    if len(audio_arrays) == 1:
        return audio_arrays[0]

    # Add a small pause between chunks (100ms silence)
    pause_samples = int(sample_rate * 0.1)  # 100ms
    pause = np.zeros(pause_samples, dtype=np.float32)

    result = []
    for i, audio in enumerate(audio_arrays):
        result.append(audio)
        # Add pause between chunks (but not after the last one)
        if i < len(audio_arrays) - 1:
            result.append(pause)

    return np.concatenate(result)


def get_gpu_memory_info() -> dict:
    """Get GPU memory information using nvidia-smi or torch."""
    import torch

    if not torch.cuda.is_available():
        return {"available": False, "reason": "CUDA not available"}

    try:
        # Get memory info from torch
        device_id = 0
        total = torch.cuda.get_device_properties(device_id).total_memory
        allocated = torch.cuda.memory_allocated(device_id)
        reserved = torch.cuda.memory_reserved(device_id)

        # Free = total - reserved (reserved includes allocated + cached)
        free = total - reserved

        return {
            "available": True,
            "device_name": torch.cuda.get_device_name(device_id),
            "total_gb": round(total / (1024**3), 2),
            "allocated_gb": round(allocated / (1024**3), 2),
            "reserved_gb": round(reserved / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


def check_system_vram() -> dict:
    """
    Check available VRAM across all GPUs using nvidia-smi.
    This gives us the real system-wide free VRAM, not just PyTorch's view.
    """
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode != 0:
            return {"available": False, "reason": "nvidia-smi failed"}

        gpus = []
        for line in result.stdout.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                gpus.append({
                    "index": int(parts[0]),
                    "name": parts[1],
                    "total_mb": int(parts[2]),
                    "used_mb": int(parts[3]),
                    "free_mb": int(parts[4]),
                    "free_gb": round(int(parts[4]) / 1024, 2),
                })

        return {"available": True, "gpus": gpus}
    except Exception as e:
        return {"available": False, "reason": str(e)}


def select_device() -> str:
    """
    Intelligently select GPU or CPU based on available VRAM.

    Returns "cuda" or "cpu"
    """
    if FORCE_CPU:
        logger.info("🔧 FORCE_CPU enabled - using CPU")
        return "cpu"

    # Check system VRAM via nvidia-smi (more accurate than torch)
    vram_info = check_system_vram()

    if not vram_info.get("available"):
        logger.info(f"🔧 No GPU available ({vram_info.get('reason', 'unknown')}) - using CPU")
        return "cpu"

    # Find GPU with most free VRAM (in case of multi-GPU)
    gpus = vram_info.get("gpus", [])
    if not gpus:
        logger.info("🔧 No GPUs found - using CPU")
        return "cpu"

    # Use GPU 0 (as configured in docker-compose)
    gpu = gpus[0]
    free_gb = gpu["free_gb"]

    logger.info(f"🔍 GPU 0 ({gpu['name']}): {free_gb:.2f} GB free / {gpu['total_mb']/1024:.1f} GB total")

    if free_gb >= VRAM_THRESHOLD_GB:
        logger.info(f"✅ Sufficient VRAM ({free_gb:.2f} GB >= {VRAM_THRESHOLD_GB} GB) - using GPU")
        return "cuda"
    else:
        logger.info(f"⚠️ Insufficient VRAM ({free_gb:.2f} GB < {VRAM_THRESHOLD_GB} GB) - using CPU")
        return "cpu"


def get_synthesizer():
    """Load XTTS synthesizer on first request (lazy loading)."""
    global _synthesizer, _config, _speaker_embeddings, _device
    if _synthesizer is None:
        logger.info("Loading XTTS v2 model (first request)...")
        import torch
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts
        from TTS.utils.manage import ModelManager

        # Select device based on available VRAM
        _device = select_device()
        logger.info(f"🎯 Selected device: {_device.upper()}")

        # Get model path
        manager = ModelManager()
        model_path, _, _ = manager.download_model(_model_name)

        logger.info(f"Model path: {model_path}")

        # Config is in the model directory
        config_path = Path(model_path) / "config.json"

        # Load config
        _config = XttsConfig()
        _config.load_json(str(config_path))

        # Load model
        _synthesizer = Xtts.init_from_config(_config)

        # Load checkpoint with appropriate device
        if _device == "cuda":
            _synthesizer.load_checkpoint(_config, checkpoint_dir=model_path, eval=True, use_deepspeed=False)
            _synthesizer.cuda()
        else:
            # CPU mode - load without CUDA
            _synthesizer.load_checkpoint(_config, checkpoint_dir=model_path, eval=True, use_deepspeed=False)
            _synthesizer.cpu()

        # Load speaker embeddings from the speaker library
        speaker_file = Path(model_path) / "speakers_xtts.pth"
        if speaker_file.exists():
            _speaker_embeddings = torch.load(speaker_file, map_location=_device)
            logger.info(f"Loaded {len(_speaker_embeddings)} built-in speakers")
        else:
            _speaker_embeddings = {}
            logger.warning("No built-in speaker embeddings found!")

        # Load custom voices from persistent storage
        load_custom_voices()

        # Auto-generate embeddings from reference audio directory
        auto_generate_voice_embeddings()

        logger.info(f"✅ XTTS v2 model loaded successfully on {_device.upper()}")
    return _synthesizer


def load_custom_voices():
    """Load custom voice embeddings from persistent storage."""
    global _custom_voices
    import torch

    CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)

    for pth_file in CUSTOM_VOICES_DIR.glob("*.pth"):
        voice_name = pth_file.stem
        try:
            # Load to the selected device
            _custom_voices[voice_name] = torch.load(pth_file, map_location=_device)
            logger.info(f"Loaded custom voice: {voice_name}")
        except Exception as e:
            logger.error(f"Failed to load custom voice {voice_name}: {e}")

    logger.info(f"Loaded {len(_custom_voices)} custom voices")


def auto_generate_voice_embeddings():
    """Generate embeddings for WAV files in the reference audio directory."""
    global _custom_voices
    import torch

    if not REFERENCE_AUDIO_DIR.exists():
        logger.info(f"Reference audio directory not found: {REFERENCE_AUDIO_DIR}")
        return

    for wav_file in REFERENCE_AUDIO_DIR.glob("*.wav"):
        voice_name = wav_file.stem
        embedding_file = CUSTOM_VOICES_DIR / f"{voice_name}.pth"

        # Skip if embedding already exists
        if voice_name in _custom_voices:
            continue

        logger.info(f"Generating embedding for: {voice_name}")
        try:
            # Generate embedding from WAV file
            gpt_cond_latent, speaker_embedding = _synthesizer.get_conditioning_latents(
                audio_path=[str(wav_file)]
            )

            # Save embedding
            voice_data = {
                "gpt_cond_latent": gpt_cond_latent,
                "speaker_embedding": speaker_embedding
            }
            torch.save(voice_data, embedding_file)
            _custom_voices[voice_name] = voice_data
            logger.info(f"Generated and saved embedding for: {voice_name}")

        except Exception as e:
            logger.error(f"Failed to generate embedding for {voice_name}: {e}")


def get_speaker_embedding(speaker_name: str):
    """Get speaker embedding by name (built-in or custom)."""
    # Check custom voices first
    if speaker_name in _custom_voices:
        return _custom_voices[speaker_name]

    # Check built-in speakers
    if _speaker_embeddings and speaker_name in _speaker_embeddings:
        return _speaker_embeddings[speaker_name]

    return None


def get_all_speakers() -> list:
    """Get list of all available speakers (built-in + custom)."""
    speakers = []

    # Custom voices first (marked with *)
    speakers.extend([f"* {name}" for name in sorted(_custom_voices.keys())])

    # Built-in speakers
    if _speaker_embeddings:
        speakers.extend(sorted(_speaker_embeddings.keys()))

    return speakers


# ============================================================
# WEB UI
# ============================================================
WEB_UI_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>XTTS v2 - Voice Cloning TTS</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #1a1a2e;
            color: #eee;
        }
        h1 { color: #00d4ff; margin-bottom: 5px; }
        .subtitle { color: #888; margin-bottom: 30px; }
        .section {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .section h2 { color: #00d4ff; margin-top: 0; font-size: 1.2em; }
        label { display: block; margin-bottom: 5px; color: #aaa; }
        textarea, select, input[type="text"] {
            width: 100%;
            padding: 12px;
            border: 1px solid #333;
            border-radius: 5px;
            background: #0f0f23;
            color: #fff;
            font-size: 14px;
            margin-bottom: 15px;
        }
        textarea { min-height: 120px; resize: vertical; }
        select { cursor: pointer; }
        .row { display: flex; gap: 15px; }
        .row > div { flex: 1; }
        button {
            background: linear-gradient(135deg, #00d4ff, #0099cc);
            color: #000;
            border: none;
            padding: 12px 30px;
            border-radius: 5px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.1s, box-shadow 0.1s;
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(0,212,255,0.3); }
        button:disabled { background: #444; color: #888; cursor: not-allowed; transform: none; }
        .status {
            margin-top: 15px;
            padding: 10px;
            border-radius: 5px;
            display: none;
        }
        .status.loading { display: block; background: #1e3a5f; color: #00d4ff; }
        .status.success { display: block; background: #1e3f2e; color: #4caf50; }
        .status.error { display: block; background: #3f1e1e; color: #f44336; }
        audio {
            width: 100%;
            margin-top: 15px;
            border-radius: 5px;
        }
        .info {
            background: #0f0f23;
            padding: 15px;
            border-radius: 5px;
            font-size: 13px;
            color: #888;
        }
        .info code { color: #00d4ff; background: #1a1a2e; padding: 2px 6px; border-radius: 3px; }
        .custom-voice { color: #ffd700; }
        .clone-section { border-top: 1px solid #333; padding-top: 20px; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>XTTS v2</h1>
    <p class="subtitle">Voice Cloning Text-to-Speech</p>

    <div class="section">
        <h2>Text-to-Speech</h2>
        <label for="text">Text</label>
        <textarea id="text" placeholder="Guten Tag, ich bin AIfred. How may I assist you today?"></textarea>

        <div class="row">
            <div>
                <label for="voice">Stimme / Voice</label>
                <select id="voice"></select>
            </div>
            <div>
                <label for="language">Sprache / Language</label>
                <select id="language">
                    <option value="de">Deutsch</option>
                    <option value="en">English</option>
                    <option value="fr">Français</option>
                    <option value="es">Español</option>
                    <option value="it">Italiano</option>
                    <option value="pt">Português</option>
                    <option value="pl">Polski</option>
                    <option value="nl">Nederlands</option>
                    <option value="ru">Русский</option>
                    <option value="tr">Türkçe</option>
                    <option value="cs">Čeština</option>
                    <option value="ar">العربية</option>
                    <option value="zh-cn">中文</option>
                    <option value="ja">日本語</option>
                    <option value="ko">한국어</option>
                    <option value="hu">Magyar</option>
                </select>
            </div>
        </div>

        <button onclick="generateTTS()" id="generateBtn">Generate Audio</button>

        <div id="status" class="status"></div>
        <audio id="audioPlayer" controls style="display:none;"></audio>
    </div>

    <div class="section">
        <h2>Voice Cloning</h2>
        <p style="color:#888; margin-bottom:15px;">Upload a WAV file (6-10 seconds of clear speech, mono, 22-24kHz) to clone a voice.</p>

        <div class="row">
            <div>
                <label for="cloneName">Voice Name</label>
                <input type="text" id="cloneName" placeholder="e.g. my_voice">
            </div>
            <div>
                <label for="cloneFile">Audio File (WAV)</label>
                <input type="file" id="cloneFile" accept=".wav,audio/wav" style="padding:8px;">
            </div>
        </div>

        <button onclick="cloneVoice()" id="cloneBtn">Clone Voice</button>
        <div id="cloneStatus" class="status"></div>
    </div>

    <div class="info">
        <strong>API Endpoints:</strong><br>
        <code>GET /voices</code> - List all voices<br>
        <code>GET /languages</code> - List supported languages<br>
        <code>POST /tts</code> - Generate speech (JSON: text, speaker, language)<br>
        <code>POST /voices/clone</code> - Clone voice (multipart: audio, name)<br>
        <code>DELETE /voices/&lt;name&gt;</code> - Delete custom voice
    </div>

    <script>
        // Load voices on page load (with cache-busting and loading indicator)
        async function loadVoices() {
            const select = document.getElementById('voice');

            // Show loading state
            select.innerHTML = '<option disabled>Loading voices...</option>';

            try {
                // Add timestamp to prevent browser caching
                const res = await fetch('/voices?t=' + Date.now());
                const data = await res.json();
                select.innerHTML = '';

                // Custom voices first
                if (data.custom && data.custom.length > 0) {
                    const optgroup = document.createElement('optgroup');
                    optgroup.label = '★ Custom Voices';
                    data.custom.forEach(v => {
                        const opt = document.createElement('option');
                        opt.value = v;
                        opt.textContent = '★ ' + v;
                        opt.className = 'custom-voice';
                        optgroup.appendChild(opt);
                    });
                    select.appendChild(optgroup);
                }

                // Built-in voices
                if (data.builtin && data.builtin.length > 0) {
                    const optgroup = document.createElement('optgroup');
                    optgroup.label = 'Built-in Voices (' + data.builtin.length + ')';
                    data.builtin.forEach(v => {
                        const opt = document.createElement('option');
                        opt.value = v;
                        opt.textContent = v;
                        optgroup.appendChild(opt);
                    });
                    select.appendChild(optgroup);
                }

                // Select default or first custom
                if (data.custom && data.custom.length > 0) {
                    select.value = data.custom[0];
                } else if (data.default) {
                    select.value = data.default;
                }

                // If no voices loaded, show error
                if ((!data.custom || data.custom.length === 0) && (!data.builtin || data.builtin.length === 0)) {
                    select.innerHTML = '<option disabled>No voices available - model may still be loading</option>';
                }
            } catch (e) {
                console.error('Failed to load voices:', e);
                select.innerHTML = '<option disabled>Error loading voices</option>';
            }
        }

        async function generateTTS() {
            const text = document.getElementById('text').value.trim();
            const voice = document.getElementById('voice').value;
            const language = document.getElementById('language').value;
            const status = document.getElementById('status');
            const audio = document.getElementById('audioPlayer');
            const btn = document.getElementById('generateBtn');

            if (!text) {
                status.className = 'status error';
                status.textContent = 'Please enter some text.';
                return;
            }

            btn.disabled = true;
            status.className = 'status loading';
            status.textContent = 'Generating audio...';
            audio.style.display = 'none';

            try {
                const startTime = Date.now();
                const res = await fetch('/tts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text, speaker: voice, language })
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.error || 'TTS generation failed');
                }

                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const duration = ((Date.now() - startTime) / 1000).toFixed(1);

                audio.src = url;
                audio.style.display = 'block';
                audio.play();

                status.className = 'status success';
                status.textContent = `Generated in ${duration}s`;
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            } finally {
                btn.disabled = false;
            }
        }

        async function cloneVoice() {
            const name = document.getElementById('cloneName').value.trim();
            const fileInput = document.getElementById('cloneFile');
            const status = document.getElementById('cloneStatus');
            const btn = document.getElementById('cloneBtn');

            if (!name) {
                status.className = 'status error';
                status.textContent = 'Please enter a voice name.';
                return;
            }
            if (!fileInput.files.length) {
                status.className = 'status error';
                status.textContent = 'Please select a WAV file.';
                return;
            }

            btn.disabled = true;
            status.className = 'status loading';
            status.textContent = 'Cloning voice...';

            try {
                const formData = new FormData();
                formData.append('name', name);
                formData.append('audio', fileInput.files[0]);

                const res = await fetch('/voices/clone', {
                    method: 'POST',
                    body: formData
                });

                const data = await res.json();
                if (!res.ok) throw new Error(data.error || 'Cloning failed');

                status.className = 'status success';
                status.textContent = `Voice "${name}" cloned successfully!`;

                // Reload voices
                await loadVoices();

                // Clear inputs
                document.getElementById('cloneName').value = '';
                fileInput.value = '';
            } catch (e) {
                status.className = 'status error';
                status.textContent = 'Error: ' + e.message;
            } finally {
                btn.disabled = false;
            }
        }

        // Allow Ctrl+Enter to generate
        document.getElementById('text').addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'Enter') generateTTS();
        });

        // Load voices on start
        loadVoices();
    </script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    """Web UI for testing XTTS."""
    return render_template_string(WEB_UI_HTML)


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "model_loaded": _synthesizer is not None,
        "model": _model_name,
        "device": _device or "not loaded",
        "custom_voices": len(_custom_voices)
    })


@app.route("/status", methods=["GET"])
def status():
    """
    Detailed status endpoint with GPU/VRAM information.

    Returns system info, device selection, and memory stats.
    """
    vram_info = check_system_vram()
    torch_info = get_gpu_memory_info()

    return jsonify({
        "model_loaded": _synthesizer is not None,
        "device": _device or "not loaded yet",
        "force_cpu": FORCE_CPU,
        "vram_threshold_gb": VRAM_THRESHOLD_GB,
        "system_vram": vram_info,
        "torch_memory": torch_info,
        "custom_voices": len(_custom_voices),
        "builtin_speakers": len(_speaker_embeddings) if _speaker_embeddings else 0,
        "inference_params": {
            "temperature": XTTS_TEMPERATURE,
            "repetition_penalty": XTTS_REPETITION_PENALTY,
            "length_penalty": XTTS_LENGTH_PENALTY,
            "top_k": XTTS_TOP_K,
            "top_p": XTTS_TOP_P,
            "max_chunk_chars": MAX_CHUNK_CHARS,
        },
    })


@app.route("/tts", methods=["POST"])
def tts():
    """
    Generate TTS audio from text.

    Automatically handles long texts by splitting into chunks and concatenating.
    XTTS has a 400 token limit (~250 chars), so texts are split at sentence
    boundaries when needed.

    Request JSON:
        text (str): Text to synthesize (any length)
        language (str, optional): Language code (default: de)
        speaker (str, optional): Speaker name (default: Claribel Dervla)
            - Use "* name" for custom voices or just "name"

    Returns:
        WAV audio file
    """
    import torch
    import torchaudio
    import numpy as np

    # Parse request
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data.get("text", "")
    language = data.get("language", "de")
    speaker = data.get("speaker", DEFAULT_SPEAKER)

    # Remove "* " prefix if present (UI marker for custom voices)
    if speaker.startswith("* "):
        speaker = speaker[2:]

    if not text.strip():
        return jsonify({"error": "Empty text"}), 400

    # Validate language
    supported_languages = ["de", "en", "es", "fr", "it", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh-cn", "ja", "hu", "ko"]
    if language not in supported_languages:
        return jsonify({"error": f"Unsupported language: {language}. Supported: {supported_languages}"}), 400

    # Normalize text to prevent hallucinations (ensure proper punctuation)
    original_text = text
    text = normalize_text_for_tts(text)
    if text != original_text:
        logger.info(f"Text normalized for TTS (added punctuation)")

    logger.info(f"Generating TTS: '{text[:50]}...' ({len(text)} chars) with language {language}, speaker {speaker}")

    try:
        model = get_synthesizer()

        # Get speaker embedding
        speaker_data = get_speaker_embedding(speaker)
        if speaker_data is None:
            return jsonify({
                "error": f"Unknown speaker: {speaker}",
                "available_speakers": get_all_speakers()[:30]
            }), 400

        # Move embeddings to the selected device
        if _device == "cuda":
            gpt_cond_latent = speaker_data["gpt_cond_latent"].cuda()
            speaker_embedding = speaker_data["speaker_embedding"].cuda()
        else:
            gpt_cond_latent = speaker_data["gpt_cond_latent"].cpu()
            speaker_embedding = speaker_data["speaker_embedding"].cpu()

        # Split text into chunks to avoid 400 token limit
        chunks = split_text_into_chunks(text)

        # Generate audio for each chunk
        audio_arrays = []
        for i, chunk in enumerate(chunks):
            logger.info(f"  Generating chunk {i+1}/{len(chunks)}: '{chunk[:40]}...' ({len(chunk)} chars)")

            # XTTS inference with configurable parameters (via environment variables)
            # See: https://github.com/coqui-ai/TTS/discussions/4146
            outputs = model.inference(
                text=chunk,
                language=language,
                gpt_cond_latent=gpt_cond_latent,
                speaker_embedding=speaker_embedding,
                temperature=XTTS_TEMPERATURE,
                repetition_penalty=XTTS_REPETITION_PENALTY,
                length_penalty=XTTS_LENGTH_PENALTY,
                top_k=XTTS_TOP_K,
                top_p=XTTS_TOP_P,
            )

            audio_arrays.append(outputs["wav"])

        # Concatenate all audio chunks
        if len(audio_arrays) > 1:
            logger.info(f"Concatenating {len(audio_arrays)} audio chunks")
            final_audio = concatenate_audio_arrays(audio_arrays)
        else:
            final_audio = audio_arrays[0]

        # Create temp file for output
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        # Save to file (sample rate is 24kHz for XTTS)
        torchaudio.save(temp_path, torch.tensor(final_audio).unsqueeze(0), 24000)

        logger.info(f"Generated audio: {temp_path} ({len(chunks)} chunks)")

        # Send file and schedule cleanup
        response = send_file(
            temp_path,
            mimetype="audio/wav",
            as_attachment=True,
            download_name="xtts_tts.wav"
        )

        # Cleanup after response
        @response.call_on_close
        def cleanup():
            try:
                os.unlink(temp_path)
            except Exception:
                pass

        return response

    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/voices/clone", methods=["POST"])
def clone_voice():
    """
    Clone a voice from a WAV file.

    Form data:
        audio: WAV file (6-10 seconds of clear speech, mono, 22-24kHz)
        name: Name for the cloned voice

    Returns:
        {"success": true, "voice": "name"}
    """
    import torch

    if "audio" not in request.files:
        return jsonify({"error": "Missing 'audio' file"}), 400

    if "name" not in request.form:
        return jsonify({"error": "Missing 'name' field"}), 400

    audio_file = request.files["audio"]
    voice_name = request.form["name"].strip()

    if not voice_name:
        return jsonify({"error": "Empty voice name"}), 400

    # Sanitize voice name
    voice_name = "".join(c for c in voice_name if c.isalnum() or c in "_ -").strip()
    if not voice_name:
        return jsonify({"error": "Invalid voice name"}), 400

    logger.info(f"Cloning voice: {voice_name}")

    try:
        # Ensure model is loaded
        model = get_synthesizer()

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            audio_file.save(f.name)
            temp_audio_path = f.name

        # Generate embedding
        gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
            audio_path=[temp_audio_path]
        )

        # Clean up temp file
        os.unlink(temp_audio_path)

        # Save embedding
        CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)
        embedding_file = CUSTOM_VOICES_DIR / f"{voice_name}.pth"

        voice_data = {
            "gpt_cond_latent": gpt_cond_latent,
            "speaker_embedding": speaker_embedding
        }
        torch.save(voice_data, embedding_file)

        # Add to in-memory cache
        _custom_voices[voice_name] = voice_data

        logger.info(f"Successfully cloned voice: {voice_name}")

        return jsonify({
            "success": True,
            "voice": voice_name,
            "message": f"Voice '{voice_name}' cloned successfully"
        })

    except Exception as e:
        logger.error(f"Voice cloning failed: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/voices", methods=["GET"])
def list_voices():
    """List all available voices (built-in + custom)."""
    # Ensure model is loaded
    get_synthesizer()

    custom = sorted(_custom_voices.keys())
    builtin = sorted(_speaker_embeddings.keys()) if _speaker_embeddings else []

    return jsonify({
        "custom": custom,
        "builtin": builtin,
        "all": get_all_speakers(),
        "default": DEFAULT_SPEAKER
    })


@app.route("/voices/<name>", methods=["DELETE"])
def delete_voice(name: str):
    """Delete a custom voice."""
    if name not in _custom_voices:
        return jsonify({"error": f"Custom voice not found: {name}"}), 404

    try:
        # Remove from disk
        embedding_file = CUSTOM_VOICES_DIR / f"{name}.pth"
        if embedding_file.exists():
            embedding_file.unlink()

        # Remove from memory
        del _custom_voices[name]

        logger.info(f"Deleted custom voice: {name}")

        return jsonify({
            "success": True,
            "message": f"Voice '{name}' deleted"
        })

    except Exception as e:
        logger.error(f"Failed to delete voice: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/speakers", methods=["GET"])
def list_speakers():
    """List available speakers (legacy endpoint, use /voices instead)."""
    # Ensure model is loaded
    get_synthesizer()

    return jsonify({
        "speakers": get_all_speakers(),
        "default": DEFAULT_SPEAKER
    })


@app.route("/languages", methods=["GET"])
def list_languages():
    """List available languages."""
    languages = {
        "de": "German",
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "it": "Italian",
        "pt": "Portuguese",
        "pl": "Polish",
        "tr": "Turkish",
        "ru": "Russian",
        "nl": "Dutch",
        "cs": "Czech",
        "ar": "Arabic",
        "zh-cn": "Chinese",
        "ja": "Japanese",
        "hu": "Hungarian",
        "ko": "Korean",
    }
    return jsonify(languages)


if __name__ == "__main__":
    # Development server
    app.run(host="0.0.0.0", port=5051, debug=False)
