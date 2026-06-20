"""
DIVA Wake Word Detection Microservice
Runs on the big machine (port 8003).
Uses openWakeWord for real-time wake word detection.
Supports built-in models + custom wake words via embedding comparison.
"""

import io
import json
import os
import wave
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from openwakeword.model import Model

load_dotenv()

WAKEWORD_MODELS = os.getenv("WAKEWORD_MODELS", "alexa,hey_jarvis").split(",")
CUSTOM_DIR = Path(os.getenv("CUSTOM_WAKEWORD_DIR", "/data/custom_wakewords"))
CONFIDENCE_THRESHOLD = float(os.getenv("WAKEWORD_THRESHOLD", "0.5"))

CUSTOM_DIR.mkdir(parents=True, exist_ok=True)

_oww: Model | None = None
_custom_embeddings: dict[str, np.ndarray] = {}
_custom_labels: dict[str, str] = {}


def _load_custom_embeddings():
    for f in CUSTOM_DIR.glob("*.npy"):
        name = f.stem
        label_file = CUSTOM_DIR / f"{name}_label.txt"
        label = label_file.read_text().strip() if label_file.exists() else name
        embedding = np.load(f)
        _custom_embeddings[name] = embedding
        _custom_labels[name] = label
        print(f"[wakeword] Loaded custom wake word: {label} ({name})")


def _pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _audio_to_float(audio_bytes: bytes, rate: int = 16000) -> np.ndarray:
    if audio_bytes[:4] == b"RIFF":
        with wave.open(io.BytesIO(audio_bytes)) as wf:
            raw = wf.readframes(wf.getnframes())
    else:
        raw = audio_bytes
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _oww
    print(f"[wakeword] Loading models: {WAKEWORD_MODELS}")
    _oww = Model(wakeword_models=[m.strip() for m in WAKEWORD_MODELS if m.strip()])
    print(f"[wakeword] Built-in wake words: {list(_oww.class_mapping.keys())}")
    _load_custom_embeddings()
    print(f"[wakeword] Custom wake words: {list(_custom_embeddings.keys())}")
    yield


app = FastAPI(title="DIVA Wake Word Service", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "builtin_wake_words": list(_oww.class_mapping.keys()) if _oww else [],
        "custom_wake_words": list(_custom_embeddings.keys()),
        "threshold": CONFIDENCE_THRESHOLD,
    }


@app.post("/detect")
async def detect(file: UploadFile = File(...)):
    if _oww is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    audio_bytes = await file.read()
    audio_float = _audio_to_float(audio_bytes)

    if len(audio_float) == 0:
        raise HTTPException(status_code=400, detail="Empty audio")

    CHUNK = 1280
    detected = {}

    for start in range(0, len(audio_float), CHUNK):
        chunk = audio_float[start : start + CHUNK]
        if len(chunk) < CHUNK:
            padded = np.zeros(CHUNK, dtype=np.float32)
            padded[: len(chunk)] = chunk
            chunk = padded
        prediction = _oww.predict(chunk)

        for name, score in prediction.items():
            if score > CONFIDENCE_THRESHOLD:
                if name not in detected or score > detected[name]:
                    detected[name] = float(score)

    if _custom_embeddings:
        embedding = _oww.embed(audio_float)
        for name, ref_emb in _custom_embeddings.items():
            sim = float(np.dot(embedding, ref_emb) / (
                np.linalg.norm(embedding) * np.linalg.norm(ref_emb) + 1e-8
            ))
            if sim > CONFIDENCE_THRESHOLD:
                label = _custom_labels.get(name, name)
                if label not in detected or sim > detected[label]:
                    detected[label] = sim

    return {
        "detected": detected,
        "threshold": CONFIDENCE_THRESHOLD,
        "has_wake_word": len(detected) > 0,
    }


@app.post("/custom/{name}/train")
async def train_custom(name: str, file: UploadFile = File(...)):
    if _oww is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    audio_bytes = await file.read()
    audio_float = _audio_to_float(audio_bytes)

    if len(audio_float) < 8000:
        raise HTTPException(
            status_code=400,
            detail="Audio too short. Need at least 0.5s at 16kHz.",
        )

    embedding = _oww.embed(audio_float)
    np.save(CUSTOM_DIR / f"{name}.npy", embedding)
    (CUSTOM_DIR / f"{name}_label.txt").write_text(name)

    _custom_embeddings[name] = embedding
    _custom_labels[name] = name

    return {
        "status": "trained",
        "name": name,
        "embedding_dim": embedding.shape[0],
    }


@app.post("/custom/{name}")
async def detect_custom(name: str, file: UploadFile = File(...)):
    if name not in _custom_embeddings:
        raise HTTPException(status_code=404, detail=f"Custom wake word '{name}' not trained")

    audio_bytes = await file.read()
    audio_float = _audio_to_float(audio_bytes)
    embedding = _oww.embed(audio_float)
    ref_emb = _custom_embeddings[name]
    sim = float(np.dot(embedding, ref_emb) / (
        np.linalg.norm(embedding) * np.linalg.norm(ref_emb) + 1e-8
    ))

    return {
        "name": name,
        "similarity": sim,
        "detected": sim > CONFIDENCE_THRESHOLD,
        "threshold": CONFIDENCE_THRESHOLD,
    }


@app.get("/custom")
async def list_custom():
    return {
        "custom_wake_words": [
            {"name": k, "label": _custom_labels.get(k, k)}
            for k in _custom_embeddings
        ]
    }
