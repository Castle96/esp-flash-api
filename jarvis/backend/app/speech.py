import io
import tempfile
import wave

from faster_whisper import WhisperModel

from .config import WHISPER_MODEL

# Load once at startup - model lives in memory on the Pi
_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _model


def transcribe_audio_bytes(audio_bytes: bytes) -> tuple[str, str | None]:
    """
    Accept raw PCM or WAV bytes from the ESP32.
    If the bytes do not start with the RIFF header, wrap them in a
    minimal 16-bit 16kHz mono WAV container before transcribing.
    """
    if audio_bytes[:4] != b"RIFF":
        audio_bytes = _pcm_to_wav(audio_bytes)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        model = _get_model()
        segments, info = model.transcribe(tmp.name, beam_size=1)
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
