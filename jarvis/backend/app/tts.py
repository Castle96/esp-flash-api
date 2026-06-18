from __future__ import annotations

import io
import subprocess
import tempfile
import wave
from pathlib import Path

from .config import (
    KOKORO_SPEED,
    KOKORO_VOICE,
    PIPER_VOICE,
    TTS_ENGINE,
    XTTS_VOICE_REF,
)


def synthesize_wav(text: str) -> bytes:
    """
    Dispatch to the configured TTS engine and return raw WAV bytes.
    Engines:
        kokoro  — hexgrad/Kokoro-82M via kokoro-onnx (CPU-native, default)
        xtts    — coqui/XTTS-v2 via TTS library (GPU, voice cloning)
        piper   — rhasspy/piper (legacy fallback)
    """
    if TTS_ENGINE == "kokoro":
        return _kokoro_synth(text)
    if TTS_ENGINE == "xtts":
        return _xtts_synth(text)
    if TTS_ENGINE == "piper":
        return _piper_synth(text)
    raise RuntimeError(f"Unknown TTS_ENGINE: {TTS_ENGINE}")


# ---------------------------------------------------------------------------
# Kokoro — hexgrad/Kokoro-82M (ONNX, CPU-native)
# Default engine. Install: pip install kokoro-onnx
# Voices: af_bella, af_sarah, am_adam, am_michael,
#         bf_emma, bm_george, bm_lewis
# ---------------------------------------------------------------------------

def _kokoro_synth(text: str) -> bytes:
    from kokoro_onnx import Kokoro  # type: ignore

    # Model is cached after first load
    if not hasattr(_kokoro_synth, "_model"):
        print("[tts] Loading Kokoro-82M...")
        _kokoro_synth._model = Kokoro("kokoro-v0_19.onnx", "voices.bin")  # type: ignore
        print("[tts] Kokoro ready.")

    samples, sample_rate = _kokoro_synth._model.create(  # type: ignore
        text,
        voice=KOKORO_VOICE,
        speed=KOKORO_SPEED,
        lang="en-us",
    )
    return _pcm_samples_to_wav(samples, sample_rate)


# ---------------------------------------------------------------------------
# XTTS v2 — coqui/XTTS-v2 (GPU, zero-shot voice cloning)
# Swap in when GPU arrives. Install: pip install TTS
# Set XTTS_VOICE_REF to a 3-6s WAV clip of the target voice.
# ---------------------------------------------------------------------------

def _xtts_synth(text: str) -> bytes:
    from TTS.api import TTS  # type: ignore

    if not hasattr(_xtts_synth, "_model"):
        print("[tts] Loading XTTS-v2...")
        _xtts_synth._model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")  # type: ignore
        print("[tts] XTTS-v2 ready.")

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "speech.wav"
        _xtts_synth._model.tts_to_file(  # type: ignore
            text=text,
            speaker_wav=XTTS_VOICE_REF,
            language="en",
            file_path=str(out),
        )
        return out.read_bytes()


# ---------------------------------------------------------------------------
# Piper — legacy fallback
# ---------------------------------------------------------------------------

def _piper_synth(text: str) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "speech.wav"
        subprocess.run(
            ["piper", "--model", PIPER_VOICE, "--output_file", str(out)],
            input=text.encode("utf-8"),
            check=True,
            capture_output=True,
        )
        return out.read_bytes()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pcm_samples_to_wav(samples, sample_rate: int) -> bytes:
    """
    Convert a numpy float32 array (or list) of PCM samples to WAV bytes.
    Kokoro returns float32 in [-1, 1]; we convert to int16 for the WAV.
    """
    import numpy as np  # type: ignore

    pcm = (np.array(samples) * 32767).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)          # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()
