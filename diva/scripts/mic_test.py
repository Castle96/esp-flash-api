#!/usr/bin/env python3
"""
Mic → full voice round-trip test.

Records from the default microphone, sends through the wake-word / STT / LLM / TTS
pipeline on the DIVA backend, and plays back the spoken answer.

Usage:
    python3 scripts/mic_test.py                   # 5s default
    python3 scripts/mic_test.py --duration 3      # custom duration
    python3 scripts/mic_test.py --no-wake         # skip wake-word check
    python3 scripts/mic_test.py --save /tmp/out.wav

Requirements (install on the test machine):
    pip install sounddevice soundfile httpx
"""

import argparse
import io
import sys
import tempfile
import wave

import httpx

HOST = "100.85.238.85:8000"
WAKE_URL = f"http://{HOST}/voice"
TRANSCRIBE_URL = f"http://{HOST}/transcribe"
SPEAK_URL = f"http://{HOST}/speak"

# ---------------------------------------------------------------------------

def record(duration: int, rate: int = 16000) -> bytes:
    import sounddevice as sd
    import soundfile as sf

    print(f"Recording {duration}s (Ctrl+C to stop early) ...", file=sys.stderr)
    audio = sd.rec(int(duration * rate), samplerate=rate, channels=1, dtype="int16")
    sd.wait()
    buf = io.BytesIO()
    sf.write(buf, audio, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def play(wav_bytes: bytes):
    import sounddevice as sd
    import soundfile as sf

    data, rate = sf.read(io.BytesIO(wav_bytes))
    print(f"Playing back {len(data) / rate:.1f}s response ...", file=sys.stderr)
    sd.play(data, rate)
    sd.wait()


def record_arecord(duration: int) -> bytes:
    import subprocess

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    subprocess.run(
        ["arecord", "-d", str(duration), "-f", "S16_LE", "-r", "16000", "-c", "1", path],
        check=True,
    )
    with open(path, "rb") as f:
        return f.read()


def record_ffmpeg(duration: int) -> bytes:
    import subprocess

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "alsa", "-i", "default",
            "-ar", "16000", "-ac", "1", "-sample_fmt", "s16",
            "-t", str(duration),
            "-f", "wav", "pipe:1",
        ],
        capture_output=True,
        check=True,
    )
    return result.stdout


# ---------------------------------------------------------------------------

def test_voice(audio: bytes, check_wake: bool):
    print("Sending to /voice ...", file=sys.stderr)
    resp = httpx.post(
        WAKE_URL,
        files={"file": ("audio.wav", audio, "audio/wav")},
        timeout=60,
    )
    resp.raise_for_status()

    if check_wake and resp.headers.get("x-wakeword") == "false":
        print("Wake word NOT detected — say 'Hey DIVA'", file=sys.stderr)
        sys.exit(1)

    print(f"Got {len(resp.content)} bytes response", file=sys.stderr)
    return resp.content


def test_transcribe(audio: bytes):
    print("Sending to /transcribe ...", file=sys.stderr)
    resp = httpx.post(
        TRANSCRIBE_URL,
        files={"file": ("audio.wav", audio, "audio/wav")},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"Transcribed: {data.get('text', '')!r}", file=sys.stderr)
    return data


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="DIVA microphone round-trip test")
    parser.add_argument("--duration", "-d", type=int, default=5, help="Recording length in seconds")
    parser.add_argument("--no-wake", action="store_true", help="Skip wake-word check")
    parser.add_argument("--save", "-s", type=str, help="Save the response WAV to a file")
    parser.add_argument("--transcribe-only", "-t", action="store_true", help="Only test STT, skip LLM+TTS")
    parser.add_argument(
        "--backend",
        choices=["sounddevice", "arecord", "ffmpeg"],
        default="sounddevice",
        help="Which tool to use for recording (default: sounddevice)",
    )
    args = parser.parse_args()

    # ---- Record ----
    backends = {
        "sounddevice": record,
        "arecord": record_arecord,
        "ffmpeg": record_ffmpeg,
    }
    recorder = backends[args.backend]
    audio = recorder(args.duration)

    # ---- Send ----
    if args.transcribe_only:
        test_transcribe(audio)
        return

    resp_audio = test_voice(audio, check_wake=not args.no_wake)

    # ---- Save/Play ----
    if args.save:
        with open(args.save, "wb") as f:
            f.write(resp_audio)
        print(f"Saved to {args.save}", file=sys.stderr)
    else:
        play(resp_audio)


if __name__ == "__main__":
    main()
