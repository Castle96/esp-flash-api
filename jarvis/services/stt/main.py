"""
Jarvis STT Microservice
Runs on the big machine (port 8001).
Model: Systran/faster-whisper-large-v3
CPU:  WHISPER_DEVICE=cpu  WHISPER_COMPUTE_TYPE=int8
GPU:  WHISPER_DEVICE=cuda WHISPER_COMPUTE_TYPE=float16
"""

import io
import os
import tempfile
import wave
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel

load_dotenv()

WHISPER_MODEL        = os.getenv("WHISPER_MODEL",        "Systran/faster-whisper-large-v3")
WHISPER_DEVICE       = os.getenv("WHISPER_DEVICE",       "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

_model: WhisperModel | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model
    print(f"[stt] Loading {WHISPER_MODEL} on {WHISPER_DEVICE} ({WHISPER_COMPUTE_TYPE})...")
    _model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    print("[stt] Model ready.")
    yield


app = FastAPI(title="Jarvis STT Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": WHISPER_MODEL,
        "device": WHISPER_DEVICE,
        "compute_type": WHISPER_COMPUTE_TYPE,
    }


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Accept raw PCM or WAV audio bytes.
    Returns: { "text": "...", "language": "en" }
    """
    try:
        audio_bytes = await file.read()

        # Wrap bare PCM in a WAV container if needed
        if audio_bytes[:4] != b"RIFF":
            audio_bytes = _pcm_to_wav(audio_bytes)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            segments, info = _model.transcribe(
                tmp.name,
                beam_size=5,
                language=None,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()

        return JSONResponse({"text": text, "language": getattr(info, "language", None)})

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _pcm_to_wav(pcm: bytes, sample_rate: int = 16000, channels: int = 1, sampwidth: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()
