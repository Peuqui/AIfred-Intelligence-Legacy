#!/usr/bin/env python3
"""
MOSS-TTS-Realtime WebSocket Server for AIfred.

Provides real-time streaming TTS with multi-turn context awareness.
Uses MOSS-TTS-Realtime model with KV-cache for dialogue consistency.

Key Features:
- WebSocket streaming for low-latency audio generation
- Multi-turn context via KV-cache reuse
- Session-based dialogue management
- Text-delta to audio-frame streaming

Usage:
    WebSocket ws://localhost:5056/stream

    Client sends:
    {
        "session_id": "uuid",
        "text_delta": "Hello ",
        "turn": 0,
        "is_end": false,
        "reference_audio": "aifred.wav"  // optional
    }

    Server sends:
    {
        "type": "audio_frame",
        "data": [base64 audio data],
        "sample_rate": 24000
    }
"""

import asyncio
import base64
import importlib.util
import json
import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Dict, Optional

import torch
import torchaudio
import websockets
from flask import Flask, request, jsonify, send_file
from transformers import AutoModel, AutoTokenizer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# Configuration
# ============================================================
MODEL_NAME = os.environ.get("MOSS_REALTIME_MODEL", "OpenMOSS-Team/MOSS-TTS-Realtime")
CODEC_NAME = os.environ.get("MOSS_CODEC", "OpenMOSS-Team/MOSS-Audio-Tokenizer")
VRAM_THRESHOLD_GB = float(os.environ.get("MOSS_VRAM_THRESHOLD", "12.0"))
FORCE_CPU = os.environ.get("MOSS_FORCE_CPU", "").lower() in ("1", "true", "yes")
CODEC_SAMPLE_RATE = 24000

# Inference parameters (from MOSS-TTS-Realtime docs)
TEMPERATURE = float(os.environ.get("MOSS_TEMPERATURE", "0.8"))
TOP_P = float(os.environ.get("MOSS_TOP_P", "0.6"))
TOP_K = int(os.environ.get("MOSS_TOP_K", "30"))
REPETITION_PENALTY = float(os.environ.get("MOSS_REPETITION_PENALTY", "1.1"))
REPETITION_WINDOW = int(os.environ.get("MOSS_REPETITION_WINDOW", "50"))

# Paths
VOICES_DIR = Path("/app/voices")

# Model state (lazy loaded)
_model = None
_tokenizer = None
_codec = None
_device = None

# Session storage (session_id -> inferencer)
_sessions: Dict[str, "MossTTSRealtimeInference"] = {}

logger.info(f"MOSS-TTS-Realtime Config: temp={TEMPERATURE}, top_p={TOP_P}, "
            f"top_k={TOP_K}, rep_penalty={REPETITION_PENALTY}")


# ============================================================
# Device Selection
# ============================================================

def check_system_vram() -> dict:
    """Check available VRAM via nvidia-smi."""
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
    """Select GPU or CPU based on available VRAM."""
    if FORCE_CPU:
        logger.info("FORCE_CPU enabled - using CPU")
        return "cpu"

    vram_info = check_system_vram()
    if not vram_info.get("available"):
        logger.info(f"No GPU available ({vram_info.get('reason', 'unknown')}) - using CPU")
        return "cpu"

    gpus = vram_info.get("gpus", [])
    if not gpus:
        logger.info("No GPUs found - using CPU")
        return "cpu"

    gpu = gpus[0]
    free_gb = gpu["free_gb"]
    logger.info(f"GPU 0 ({gpu['name']}): {free_gb:.2f} GB free / {gpu['total_mb']/1024:.1f} GB total")

    if free_gb >= VRAM_THRESHOLD_GB:
        logger.info(f"Sufficient VRAM ({free_gb:.2f} GB >= {VRAM_THRESHOLD_GB} GB) - using GPU")
        return "cuda"
    else:
        logger.info(f"Insufficient VRAM ({free_gb:.2f} GB < {VRAM_THRESHOLD_GB} GB) - using CPU")
        return "cpu"


def resolve_attn_implementation() -> str:
    """Choose best attention implementation for current hardware."""
    if (
        _device == "cuda"
        and importlib.util.find_spec("flash_attn") is not None
        and torch.cuda.is_available()
    ):
        major, _ = torch.cuda.get_device_capability()
        if major >= 8:
            return "flash_attention_2"
    if _device == "cuda":
        return "sdpa"
    return "eager"


def resolve_dtype():
    """Choose best dtype for current hardware."""
    if _device != "cuda":
        return torch.float32

    major, _ = torch.cuda.get_device_capability()
    if major >= 8:
        logger.info(f"GPU CC {major}.x - using bfloat16")
        return torch.bfloat16
    else:
        logger.info(f"GPU CC {major}.x - using float16 (no bfloat16 support)")
        return torch.float16


# ============================================================
# Model Loading
# ============================================================

def load_models():
    """Load MOSS-TTS-Realtime model, tokenizer, and codec."""
    global _model, _tokenizer, _codec, _device

    _device = select_device()
    dtype = resolve_dtype()
    attn_impl = resolve_attn_implementation()

    logger.info(f"Loading MOSS-TTS-Realtime: {MODEL_NAME}")
    logger.info(f"Device: {_device}, dtype: {dtype}, attention: {attn_impl}")

    # Import MossTTSRealtime from cloned repo
    from moss_tts_realtime.mossttsrealtime.modeling_mossttsrealtime import MossTTSRealtime

    # Load model with custom class
    _model = MossTTSRealtime.from_pretrained(
        MODEL_NAME,
        attn_implementation=attn_impl,
        torch_dtype=dtype,
    ).to(_device)
    _model.eval()

    # Load tokenizer
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    # Load codec
    _codec = AutoModel.from_pretrained(
        CODEC_NAME,
        trust_remote_code=True
    ).eval().to(_device)

    logger.info(f"MOSS-TTS-Realtime loaded on {_device.upper()}")


def get_models():
    """Get models, loading if needed (lazy loading)."""
    if _model is None:
        load_models()
    return _model, _tokenizer, _codec


# ============================================================
# Session Management
# ============================================================

class StreamingSession:
    """Manages a multi-turn streaming TTS session with KV-cache."""

    def __init__(self, session_id: str, reference_audio: Optional[str] = None):
        # Import from MOSS-TTS repo
        import sys
        sys.path.insert(0, '/opt/moss-tts/moss_tts_realtime')
        from inferencer import MossTTSRealtimeInference

        self.session_id = session_id
        self.reference_audio = reference_audio
        self.turn = 0
        self.text_buffer = ""

        model, tokenizer, codec = get_models()

        self.inferencer = MossTTSRealtimeInference(
            model,
            tokenizer,
            max_length=5000,
            codec=codec,
            codec_sample_rate=CODEC_SAMPLE_RATE,
            codec_encode_kwargs={"chunk_duration": 8}
        )

        logger.info(f"Session created: {session_id}")

    def push_text(self, text_delta: str):
        """Push text delta and get audio frames."""
        self.text_buffer += text_delta
        # Return None - actual generation happens in drain()
        return None

    def generate_turn(self):
        """Generate audio for current turn (complete text)."""
        if not self.text_buffer.strip():
            return None

        # Build reference audio path if provided
        ref_audio_path = None
        if self.reference_audio:
            ref_path = VOICES_DIR / f"{self.reference_audio}.wav"
            if ref_path.exists():
                ref_audio_path = str(ref_path)

        # Generate with KV-cache
        reference_audio = [ref_audio_path] if ref_audio_path else None

        result = self.inferencer.generate(
            text=[self.text_buffer],
            reference_audio_path=reference_audio,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            top_k=TOP_K,
            repetition_penalty=REPETITION_PENALTY,
            repetition_window=REPETITION_WINDOW,
            device=_device,
        )

        # Extract audio frames
        audio_frames = []
        for i, generated_tokens in enumerate(result):
            output = torch.tensor(generated_tokens).to(_device)
            decode_result = _codec.decode(output.permute(1, 0), chunk_duration=8)
            wav = decode_result["audio"][0].cpu().detach()
            # Ensure 2D (channels, samples) or 1D (samples) - squeeze batch dim if present
            if wav.ndim == 3:
                wav = wav.squeeze(0)
            audio_frames.append(wav)

        # Reset buffer for next turn
        self.text_buffer = ""
        self.turn += 1

        return audio_frames


def get_or_create_session(session_id: str, reference_audio: Optional[str] = None) -> StreamingSession:
    """Get existing session or create new one."""
    if session_id not in _sessions:
        _sessions[session_id] = StreamingSession(session_id, reference_audio)
    return _sessions[session_id]


def cleanup_session(session_id: str):
    """Remove session and free resources."""
    if session_id in _sessions:
        del _sessions[session_id]
        logger.info(f"Session cleaned up: {session_id}")


# ============================================================
# WebSocket Handler
# ============================================================

async def handle_stream(websocket):
    """Handle WebSocket streaming connection."""
    session_id = None

    try:
        async for message in websocket:
            data = json.loads(message)

            # Extract message fields
            session_id = data.get("session_id") or str(uuid.uuid4())
            text_delta = data.get("text_delta", "")
            is_end = data.get("is_end", False)
            reference_audio = data.get("reference_audio")

            # Get or create session
            session = get_or_create_session(session_id, reference_audio)

            # Accumulate text
            if text_delta:
                session.push_text(text_delta)

            # Generate audio when turn ends
            if is_end:
                logger.info(f"Session {session_id}: Generating turn {session.turn}")
                audio_frames = session.generate_turn()

                if audio_frames:
                    for wav in audio_frames:
                        # Convert to bytes
                        wav_bytes = wav.numpy().tobytes()
                        b64_audio = base64.b64encode(wav_bytes).decode("utf-8")

                        # Send audio frame
                        await websocket.send(json.dumps({
                            "type": "audio_frame",
                            "data": b64_audio,
                            "sample_rate": CODEC_SAMPLE_RATE,
                            "session_id": session_id,
                            "turn": session.turn - 1
                        }))

                # Send end marker
                await websocket.send(json.dumps({
                    "type": "end",
                    "session_id": session_id,
                    "turn": session.turn
                }))

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Connection closed: {session_id}")
    except Exception as e:
        logger.error(f"Error in stream handler: {e}")
        import traceback
        traceback.print_exc()
        await websocket.send(json.dumps({
            "type": "error",
            "message": str(e)
        }))
    finally:
        if session_id:
            cleanup_session(session_id)


# ============================================================
# HTTP API (Flask) for AIfred Integration
# ============================================================

app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "device": str(_device) if _device else "not loaded",
        "model_loaded": _model is not None,
    })


@app.route("/status", methods=["GET"])
def status():
    """Detailed status endpoint with GPU/VRAM info."""
    vram_info = check_system_vram()

    status_data = {
        "status": "ready" if _model is not None else "loading",
        "device": str(_device) if _device else "not loaded",
        "model": MODEL_NAME,
        "codec": CODEC_NAME,
        "sample_rate": CODEC_SAMPLE_RATE,
        "active_sessions": len(_sessions),
    }

    if vram_info.get("available") and vram_info.get("gpus"):
        gpu = vram_info["gpus"][0]
        status_data["gpu"] = {
            "name": gpu["name"],
            "free_mb": gpu["free_mb"],
            "total_mb": gpu["total_mb"],
        }

    return jsonify(status_data)


@app.route("/voices", methods=["GET"])
def get_voices():
    """List available voices."""
    voices = []
    if VOICES_DIR.exists():
        for wav_file in VOICES_DIR.glob("*.wav"):
            voices.append(wav_file.stem)
    return jsonify({"voices": voices})


@app.route("/tts", methods=["POST"])
def tts_endpoint():
    """
    TTS generation endpoint (HTTP, non-streaming).

    Expects JSON:
    {
        "text": "Text to synthesize",
        "speaker": "AIfred",  // optional, voice name (without .wav)
        "language": "de"      // optional, language code
    }

    Returns: OGG/Opus audio file
    """
    data = request.get_json()

    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400

    text = data["text"]
    speaker = data.get("speaker", None)

    try:
        # Generate audio using the session mechanism
        session_id = str(uuid.uuid4())
        session = StreamingSession(session_id, reference_audio=speaker)

        # Push complete text
        session.push_text(text)

        # Generate
        audio_frames = session.generate_turn()

        # Cleanup
        cleanup_session(session_id)

        if not audio_frames:
            return jsonify({"error": "No audio generated"}), 500

        # Concatenate frames
        import numpy as np
        full_audio = torch.cat(audio_frames, dim=-1)

        # Ensure 2D tensor for torchaudio.save (channels x samples)
        if full_audio.ndim == 1:
            full_audio = full_audio.unsqueeze(0)  # Add channel dimension

        # Save to temporary WAV file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            wav_path = tmp_wav.name

        torchaudio.save(wav_path, full_audio, CODEC_SAMPLE_RATE)

        # Convert to OGG/Opus (like XTTS)
        ogg_path = wav_path.replace(".wav", ".ogg")
        import subprocess
        subprocess.run([
            "ffmpeg", "-i", wav_path, "-c:a", "libopus", "-b:a", "48k",
            "-y", ogg_path
        ], capture_output=True, check=True)

        # Clean up WAV
        os.unlink(wav_path)

        # Send OGG file
        return send_file(ogg_path, mimetype="audio/ogg", as_attachment=True,
                        download_name="output.ogg")

    except Exception as e:
        logger.error(f"TTS generation error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def run_flask():
    """Run Flask app in a separate thread."""
    app.run(host="0.0.0.0", port=5056, debug=False, use_reloader=False)


# ============================================================
# Main Server
# ============================================================

async def main():
    """Start both HTTP and WebSocket servers."""
    # Pre-load models at startup
    logger.info("Pre-loading models...")
    get_models()
    logger.info("Models loaded and ready")

    # Start Flask HTTP server in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("HTTP API server running on http://0.0.0.0:5056")

    # Start WebSocket server
    server = await websockets.serve(
        handle_stream,
        "0.0.0.0",
        5057,
        max_size=10 * 1024 * 1024,  # 10MB max message size
    )

    logger.info("WebSocket server running on ws://0.0.0.0:5057")
    logger.info("MOSS-TTS-Realtime ready!")

    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
