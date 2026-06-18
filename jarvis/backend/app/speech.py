import io
import tempfile
import wave

from faster_whisper import WhisperModel

from .config import WHISPER_COMPUTE_TYPE, WHISPER_DEVICE, WHISPER_MODEL

# Load once at startup — stays resident in RAM
_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        print(f"[speech] Loading {WHISPER_MODEL} on {WHISPER_DEVICE} ({WHISPER_COMPUTE_TYPE})...")
        _model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        print("[speech] Whisper model ready.")
    return _model


def transcribe_audio_bytes(audio_bytes: bytes) -> tuple[str, str | None]:
    """
    Accept raw PCM or WAV bytes from the ESP32.
    Wraps bare PCM in a WAV container if no RIFF header is detected.
    Returns (transcript, detected_language).
    """
    if audio_bytes[:4] != b"RIFF":
        audio_bytes = _pcm_to_wav(audio_bytes)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        model = _get_model()
        segments, info = model.transcribe(
            tmp.name,
            beam_size=5,                   # better accuracy vs beam_size=1
            language=None,                 # auto-detect
            vad_filter=True,               # skip silence chunks
            vad_parameters={"min_silence_duration_ms": 300},
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text, getattr(info, "language", None)


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
