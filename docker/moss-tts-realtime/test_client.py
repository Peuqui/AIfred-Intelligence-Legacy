#!/usr/bin/env python3
"""
Test client for MOSS-TTS-Realtime WebSocket server.

Tests:
1. WebSocket connection
2. Text-delta streaming
3. Real-time audio response (measures latency)
4. Audio quality (saves output for manual testing)

Usage:
    python test_client.py
    python test_client.py --text "Custom test text"
"""

import asyncio
import base64
import json
import time
import sys
from pathlib import Path

try:
    import websockets
except ImportError:
    print("❌ websockets not installed. Run: pip install websockets")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("❌ numpy not installed. Run: pip install numpy")
    sys.exit(1)


# Configuration
WS_URL = "ws://localhost:5056/stream"
SAMPLE_RATE = 24000
OUTPUT_DIR = Path("test_output")


async def test_realtime_streaming(text: str = None, reference_audio: str = None):
    """
    Test MOSS-TTS-Realtime with streaming text input.

    Simulates LLM token-by-token streaming by splitting text into words
    and sending them with small delays.
    """
    if text is None:
        text = (
            "Dies ist ein Test des MOSS-TTS-Realtime Systems. "
            "Wir prüfen ob Audio-Frames bereits während der Texteingabe "
            "zurückgesendet werden, oder ob erst am Ende alles auf einmal kommt."
        )

    print(f"📝 Test text: {text[:80]}...")
    print(f"🔗 Connecting to {WS_URL}...")

    # Prepare output
    OUTPUT_DIR.mkdir(exist_ok=True)
    session_id = f"test_{int(time.time())}"
    audio_frames = []

    # Timing metrics
    start_time = time.time()
    first_audio_time = None
    text_send_times = []
    audio_receive_times = []

    try:
        async with websockets.connect(WS_URL, max_size=10 * 1024 * 1024) as ws:
            print("✅ WebSocket connected")

            # Split text into chunks (simulate LLM streaming)
            words = text.split()
            total_words = len(words)

            print(f"\n📤 Streaming {total_words} words to TTS...")

            # Send text word-by-word
            for i, word in enumerate(words):
                chunk = word + " "
                is_last = (i == total_words - 1)

                message = {
                    "session_id": session_id,
                    "text_delta": chunk,
                    "is_end": is_last,
                    "reference_audio": reference_audio
                }

                send_time = time.time()
                await ws.send(json.dumps(message))
                text_send_times.append((i, send_time - start_time))

                print(f"  📨 [{i+1}/{total_words}] Sent: '{chunk.strip()}'", end="")

                # Small delay to simulate token generation
                if not is_last:
                    await asyncio.sleep(0.05)  # 50ms between words
                    print()
                else:
                    print(" (END)")

            print(f"\n📥 Waiting for audio frames...")

            # Receive audio frames
            async for message in ws:
                receive_time = time.time()
                data = json.loads(message)

                if data["type"] == "audio_frame":
                    if first_audio_time is None:
                        first_audio_time = receive_time
                        ttfa = first_audio_time - start_time
                        print(f"\n🎵 First audio frame received!")
                        print(f"   ⏱️  Time-to-First-Audio: {ttfa:.2f}s")

                    # Decode audio
                    audio_bytes = base64.b64decode(data["data"])
                    audio_np = np.frombuffer(audio_bytes, dtype=np.float32)
                    audio_frames.append(audio_np)
                    audio_receive_times.append((len(audio_frames), receive_time - start_time))

                    print(f"  🔊 Audio frame {len(audio_frames)}: {len(audio_np)} samples")

                elif data["type"] == "end":
                    print(f"\n✅ Generation complete!")
                    print(f"   Turn: {data.get('turn', 'N/A')}")
                    break

                elif data["type"] == "error":
                    print(f"\n❌ Error: {data.get('message', 'Unknown')}")
                    return False

            # Final metrics
            end_time = time.time()
            total_time = end_time - start_time

            if audio_frames:
                # Concatenate all audio
                full_audio = np.concatenate(audio_frames)
                audio_duration = len(full_audio) / SAMPLE_RATE

                # Save to file
                output_path = OUTPUT_DIR / f"{session_id}.raw"
                full_audio.tofile(output_path)

                print(f"\n📊 Performance Metrics:")
                print(f"   Total time: {total_time:.2f}s")
                print(f"   Audio duration: {audio_duration:.2f}s")
                print(f"   Real-Time Factor (RTF): {total_time / audio_duration:.2f}x")
                print(f"   Time-to-First-Audio: {ttfa:.2f}s")
                print(f"   Audio frames received: {len(audio_frames)}")

                print(f"\n💾 Audio saved: {output_path}")
                print(f"   To play: ffplay -f f32le -ar {SAMPLE_RATE} -ac 1 {output_path}")

                # Check if truly streaming
                if first_audio_time and text_send_times:
                    last_text_time = text_send_times[-1][1]
                    if first_audio_time < start_time + last_text_time:
                        print(f"\n🚀 TRUE STREAMING: Audio started before all text was sent!")
                    else:
                        print(f"\n⚠️  BATCH MODE: Audio only after all text was sent")

                return True
            else:
                print("\n❌ No audio frames received")
                return False

    except websockets.exceptions.ConnectionRefused:
        print(f"❌ Connection refused. Is the server running on {WS_URL}?")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_simple_request(text: str = "Hallo, dies ist ein Test."):
    """Simple test with short text."""
    print("=" * 60)
    print("TEST: Simple short request")
    print("=" * 60)
    return await test_realtime_streaming(text)


async def test_long_streaming(text: str = None):
    """Test with longer text to see streaming behavior."""
    print("=" * 60)
    print("TEST: Long text streaming")
    print("=" * 60)

    if text is None:
        text = (
            "MOSS-TTS-Realtime ist ein kontextbewusstes Multi-Turn-Streaming-TTS-System "
            "das für Echtzeit-Sprachagenten entwickelt wurde. Es unterstützt gesprochene "
            "Interaktionen indem es die Sprachgenerierung sowohl auf textuellem als auch "
            "auf akustischem Verlauf aus vorherigen Dialogrunden konditioniert. Durch die "
            "enge Integration von Multi-Turn-Kontextmodellierung mit Streaming-Synthese mit "
            "niedriger Latenz generiert MOSS-TTS-Realtime inkrementelle Audio-Antworten die "
            "Stimmkonsistenz und Diskurskohärenz bewahren."
        )

    return await test_realtime_streaming(text)


async def main():
    """Run all tests."""
    import argparse
    parser = argparse.ArgumentParser(description="Test MOSS-TTS-Realtime WebSocket server")
    parser.add_argument("--text", help="Custom test text")
    parser.add_argument("--reference", help="Reference audio for voice cloning (e.g., 'aifred')")
    parser.add_argument("--simple", action="store_true", help="Run only simple test")
    args = parser.parse_args()

    tests = []

    if args.text:
        # Custom text test
        tests.append(("Custom Text", test_realtime_streaming(args.text, args.reference)))
    elif args.simple:
        # Simple test only
        tests.append(("Simple", test_simple_request()))
    else:
        # Full test suite
        tests.append(("Simple", test_simple_request()))
        tests.append(("Long Streaming", test_long_streaming()))

    # Run tests
    results = []
    for name, test_coro in tests:
        print(f"\n{'=' * 60}")
        print(f"Running: {name}")
        print(f"{'=' * 60}\n")
        result = await test_coro
        results.append((name, result))

        if len(tests) > 1:
            await asyncio.sleep(2)  # Pause between tests

    # Summary
    print(f"\n{'=' * 60}")
    print("TEST SUMMARY")
    print(f"{'=' * 60}")
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    all_passed = all(r for _, r in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
