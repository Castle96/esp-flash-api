import io
import os
import wave

import httpx
from dotenv import load_dotenv

load_dotenv()

STT_HOST = os.getenv("STT_HOST", "http://BIG_MACHINE_IP:8001")


def transcribe_audio_bytes(audio_bytes: bytes) -> tuple[str, str | None]:
    """
    Forward audio to the remote STT microservice on the big machine.
    Wraps bare PCM in a WAV container if no RIFF header is present.
    Returns (transcript, detected_language).
    """
    if audio_bytes[:4] != b"RIFF":
        audio_bytes = _pcm_to_wav(audio_bytes)

    resp = httpx.post(
        f"{STT_HOST}/transcribe",
        files={"file": ("audio.wav", audio_bytes, "audio/wav")},
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("text", ""), data.get("language")


def _pcm_to_wav(
    pcm: bytes,
    sample_rate: int = 16000,
    channels: int = 1,
    sampwidth: int = 2,
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()
