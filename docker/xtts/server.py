"""
Coqui XTTS v2 HTTP Server for AIfred.

Provides a simple REST API for text-to-speech generation using XTTS v2.
Supports multilingual code-switching (DE/EN mixed text) automatically.

XTTS v2 is a voice cloning model - it requires a reference audio to clone.
We provide built-in speaker embeddings from the model's speaker library,
plus support for custom voice cloning from WAV files.

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

# Lazy loading - model loaded on first request
_model_name = "tts_models/multilingual/multi-dataset/xtts_v2"
_config = None
_synthesizer = None
_speaker_embeddings = None  # Pre-loaded speaker embeddings (built-in)
_custom_voices = {}  # Custom cloned voices

# Paths
CUSTOM_VOICES_DIR = Path("/app/custom_voices")  # Persistent storage for embeddings
REFERENCE_AUDIO_DIR = Path("/app/voices")  # Reference WAV files (mounted from host)

# Default speaker from XTTS speaker library
DEFAULT_SPEAKER = "Claribel Dervla"


def get_synthesizer():
    """Load XTTS synthesizer on first request (lazy loading)."""
    global _synthesizer, _config, _speaker_embeddings
    if _synthesizer is None:
        logger.info("Loading XTTS v2 model (first request)...")
        import torch
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts
        from TTS.utils.manage import ModelManager

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
        _synthesizer.load_checkpoint(_config, checkpoint_dir=model_path, eval=True)
        _synthesizer.cuda()

        # Load speaker embeddings from the speaker library
        speaker_file = Path(model_path) / "speakers_xtts.pth"
        if speaker_file.exists():
            _speaker_embeddings = torch.load(speaker_file)
            logger.info(f"Loaded {len(_speaker_embeddings)} built-in speakers")
        else:
            _speaker_embeddings = {}
            logger.warning("No built-in speaker embeddings found!")

        # Load custom voices from persistent storage
        load_custom_voices()

        # Auto-generate embeddings from reference audio directory
        auto_generate_voice_embeddings()

        logger.info("XTTS v2 model loaded successfully")
    return _synthesizer


def load_custom_voices():
    """Load custom voice embeddings from persistent storage."""
    global _custom_voices
    import torch

    CUSTOM_VOICES_DIR.mkdir(parents=True, exist_ok=True)

    for pth_file in CUSTOM_VOICES_DIR.glob("*.pth"):
        voice_name = pth_file.stem
        try:
            _custom_voices[voice_name] = torch.load(pth_file)
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
        "custom_voices": len(_custom_voices)
    })


@app.route("/tts", methods=["POST"])
def tts():
    """
    Generate TTS audio from text.

    Request JSON:
        text (str): Text to synthesize
        language (str, optional): Language code (default: de)
        speaker (str, optional): Speaker name (default: Claribel Dervla)
            - Use "* name" for custom voices or just "name"

    Returns:
        WAV audio file
    """
    import torch
    import torchaudio

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

    logger.info(f"Generating TTS: '{text[:50]}...' with language {language}, speaker {speaker}")

    try:
        model = get_synthesizer()

        # Get speaker embedding
        speaker_data = get_speaker_embedding(speaker)
        if speaker_data is None:
            return jsonify({
                "error": f"Unknown speaker: {speaker}",
                "available_speakers": get_all_speakers()[:30]
            }), 400

        gpt_cond_latent = speaker_data["gpt_cond_latent"].cuda()
        speaker_embedding = speaker_data["speaker_embedding"].cuda()

        # Create temp file for output
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

        # Generate audio using inference method
        outputs = model.inference(
            text=text,
            language=language,
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            temperature=0.7,
        )

        # Get audio array
        audio = outputs["wav"]

        # Save to file (sample rate is 24kHz for XTTS)
        torchaudio.save(temp_path, torch.tensor(audio).unsqueeze(0), 24000)

        logger.info(f"Generated audio: {temp_path}")

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
