# MOSS-TTS-Realtime WebSocket Service

Real-time streaming TTS for AIfred with multi-turn context awareness.

## Features

- **Real-time Streaming**: Token-level streaming for instant audio feedback
- **Multi-Turn Context**: KV-cache reuse for consistent dialogue
- **WebSocket API**: Bidirectional streaming for LLM integration
- **Session Management**: Persistent context across conversation turns
- **Zero-Shot Voice Cloning**: Reference audio for custom voices
- **Smart Device Selection**: Auto GPU/CPU based on VRAM

## Quick Start

```bash
cd docker/moss-tts-realtime
docker compose up -d
```

First start downloads model (~3-4 GB) and may take 5-10 minutes.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MOSS_REALTIME_MODEL` | `OpenMOSS-Team/MOSS-TTS-Realtime` | Model repo |
| `MOSS_CODEC` | `OpenMOSS-Team/MOSS-Audio-Tokenizer` | Audio codec |
| `MOSS_VRAM_THRESHOLD` | `12.0` | Min VRAM (GB) for GPU mode |
| `MOSS_FORCE_CPU` | `0` | Force CPU mode (1/true) |
| `CUDA_VISIBLE_DEVICES` | - | GPU index (e.g., `1` for second GPU) |
| `MOSS_TEMPERATURE` | `0.8` | Sampling temperature |
| `MOSS_TOP_P` | `0.6` | Nucleus sampling threshold |
| `MOSS_TOP_K` | `30` | Top-K sampling |
| `MOSS_REPETITION_PENALTY` | `1.1` | Repetition penalty |
| `MOSS_REPETITION_WINDOW` | `50` | Repetition window size |

### Multi-GPU Setup (Mini: 2x P40)

Pin MOSS-TTS-Realtime to second GPU:

```yaml
environment:
  - CUDA_VISIBLE_DEVICES=1  # Use GPU 1 for TTS
```

LLM (Ollama/vLLM) runs on GPU 0, TTS on GPU 1.

## WebSocket API

### Endpoint

```
ws://localhost:5056/stream
```

### Client → Server Messages

```json
{
  "session_id": "uuid-or-user-id",
  "text_delta": "Hello ",
  "is_end": false,
  "reference_audio": "aifred"  // optional, WAV file in voices/
}
```

**Fields:**
- `session_id`: Unique session ID (creates new session if not exists)
- `text_delta`: Incremental text chunk (can be tokens or sentences)
- `is_end`: `true` when turn is complete (triggers audio generation)
- `reference_audio`: Voice name (e.g., `"aifred"` → `voices/aifred.wav`)

### Server → Client Messages

**Audio Frame:**
```json
{
  "type": "audio_frame",
  "data": "base64-encoded-audio",
  "sample_rate": 24000,
  "session_id": "uuid",
  "turn": 0
}
```

**End Marker:**
```json
{
  "type": "end",
  "session_id": "uuid",
  "turn": 1
}
```

**Error:**
```json
{
  "type": "error",
  "message": "Error description"
}
```

## Usage Example

### Python Client

```python
import asyncio
import json
import websockets

async def stream_tts():
    uri = "ws://localhost:5056/stream"
    async with websockets.connect(uri) as ws:
        # Start turn
        await ws.send(json.dumps({
            "session_id": "user-123",
            "text_delta": "Hello, ",
            "is_end": False,
            "reference_audio": "aifred"
        }))

        # Continue turn
        await ws.send(json.dumps({
            "session_id": "user-123",
            "text_delta": "how are you?",
            "is_end": True  # Trigger generation
        }))

        # Receive audio frames
        async for message in ws:
            data = json.loads(message)
            if data["type"] == "audio_frame":
                # Decode and play audio
                audio_bytes = base64.b64decode(data["data"])
                # ... play audio
            elif data["type"] == "end":
                break

asyncio.run(stream_tts())
```

### Integration with LLM Streaming

```python
async def llm_with_tts_streaming():
    # LLM stream (e.g., from Ollama)
    async for token in llm_stream():
        # Send token to TTS
        await tts_ws.send(json.dumps({
            "session_id": session_id,
            "text_delta": token,
            "is_end": False
        }))

    # End turn
    await tts_ws.send(json.dumps({
        "session_id": session_id,
        "text_delta": "",
        "is_end": True
    }))

    # Receive and play audio
    async for msg in tts_ws:
        if msg["type"] == "audio_frame":
            play_audio(msg["data"])
```

## Custom Voices

Add WAV files to `voices/` directory:

```bash
# Copy reference audio (6-10s clean speech)
cp aifred.wav docker/moss-tts-realtime/voices/

# Restart container
docker compose restart
```

Reference in API:
```json
{
  "reference_audio": "aifred"  // matches aifred.wav
}
```

## Performance

### Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| VRAM | 12 GB | 16+ GB |
| GPU | Pascal (P40) | Ampere+ (3090, 4090) |
| RAM | 16 GB | 32+ GB |

### Benchmarks

| GPU | VRAM Used | Latency (first token) |
|-----|-----------|----------------------|
| RTX 3090 Ti | ~11.5 GB | ~200-500ms |
| Tesla P40 | ~11.5 GB | ~500-1000ms |

## Troubleshooting

### Container won't start

```bash
# Check logs
docker logs aifred-moss-tts-realtime

# Check GPU availability
nvidia-smi

# Force CPU mode (slower but works without GPU)
# In docker-compose.yml:
# - MOSS_FORCE_CPU=1
```

### Out of Memory (OOM)

- Reduce VRAM threshold: `MOSS_VRAM_THRESHOLD=10.0`
- Pin to dedicated GPU: `CUDA_VISIBLE_DEVICES=1`
- Unload other models before starting TTS

### Slow generation

- Check GPU usage: `nvidia-smi`
- Verify flash-attention is being used (Ampere+ GPUs)
- Use `SDPA` backend for Pascal/Turing GPUs

## Architecture Notes

**Why WebSocket instead of HTTP?**
- Bidirectional streaming (text deltas → audio frames)
- Lower latency (no request overhead per chunk)
- Persistent connection for multi-turn context

**KV-Cache Benefits:**
- Maintains voice consistency across turns
- Preserves dialogue context
- Faster generation for subsequent turns

**Session Management:**
- One session per user/conversation
- Automatic cleanup on disconnect
- Stateless server (sessions in memory)

## License

MOSS-TTS-Realtime is released under Apache 2.0 license.
