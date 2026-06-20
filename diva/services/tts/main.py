"""
DIVA TTS Microservice
Runs on the big machine (port 8002).

Engines:
  kokoro  - hexgrad/Kokoro-82M via kokoro-onnx  (CPU-native, default)
  xtts    - coqui/XTTS-v2 via TTS library        (GPU, voice cloning)

Voices (kokoro):
  bm_george  British male, authoritative  <- default / recommended for DIVA
  bm_lewis   British male, calm
  am_adam    American male, deep
  am_michael American male, neutral
  af_bella   American female, warm
  af_sarah   American female, neutral
  bf_emma    British female, crisp
"""

import io
import os
import tempfile
import wave
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

load_dotenv()

TTS_ENGINE    = os.getenv("TTS_ENGINE",    "kokoro")
KOKORO_VOICE  = os.getenv("KOKORO_VOICE",  "bm_george")
KOKORO_SPEED  = float(os.getenv("KOKORO_SPEED",  "1.0"))
XTTS_VOICE_REF = os.getenv("XTTS_VOICE_REF", "/voices/diva_reference.wav")

_kokoro_model = None
_xtts_model   = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _kokoro_model, _xtts_model
    if TTS_ENGINE == "kokoro":
        from kokoro_onnx import Kokoro  # type: ignore
        print(f"[tts] Loading Kokoro-82M (voice={KOKORO_VOICE})...")
        _kokoro_model = Kokoro("kokoro-v1.0.onnx", "voices.bin")
        print("[tts] Kokoro ready.")
    elif TTS_ENGINE == "xtts":
        from TTS.api import TTS  # type: ignore
        print("[tts] Loading XTTS-v2...")
        _xtts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        print("[tts] XTTS-v2 ready.")
    yield


app = FastAPI(title="DIVA TTS Service", version="1.0.0", lifespan=lifespan)


class SpeakRequest(BaseModel):
    text: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": TTS_ENGINE,
        "voice": KOKORO_VOICE if TTS_ENGINE == "kokoro" else XTTS_VOICE_REF,
    }


@app.post("/speak")
def speak(request: SpeakRequest):
    """
    Accept a text string, return WAV audio bytes.
    """
    try:
        if TTS_ENGINE == "kokoro":
            wav_bytes = _kokoro_synth(request.text)
        elif TTS_ENGINE == "xtts":
            wav_bytes = _xtts_synth(request.text)
        else:
            raise RuntimeError(f"Unknown TTS_ENGINE: {TTS_ENGINE}")

        return Response(content=wav_bytes, media_type="audio/wav")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _kokoro_synth(text: str) -> bytes:
    import numpy as np  # type: ignore
    samples, sample_rate = _kokoro_model.create(
        text,
        voice=KOKORO_VOICE,
        speed=KOKORO_SPEED,
        lang="en-us",
    )
    pcm = (np.array(samples) * 32767).astype(np.int16).tobytes()
    return _pcm_to_wav(pcm, sample_rate)


def _xtts_synth(text: str) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "speech.wav"
        _xtts_model.tts_to_file(
            text=text,
            speaker_wav=XTTS_VOICE_REF,
            language="en",
            file_path=str(out),
        )
        return out.read_bytes()


def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, sampwidth: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()
