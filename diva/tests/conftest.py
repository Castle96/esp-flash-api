import io
import wave
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_silent_wav(
    duration_s: float = 1.0,
    sample_rate: int = 16000,
    channels: int = 1,
    sampwidth: int = 2,
) -> bytes:
    """Generate a silent WAV file for use as a test fixture."""
    n_frames = int(sample_rate * duration_s)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00" * n_frames * channels * sampwidth)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def silent_wav() -> bytes:
    return make_silent_wav()


@pytest.fixture()
def client(monkeypatch):
    """
    FastAPI test client with STT, LLM, TTS, and wake word mocked out so tests run
    without any hardware, models, or network connections.

    All mocks patch the actual names used in app.main so that the route
    handlers resolve the mocked versions at call time.
    """
    import app.main as main_mod

    monkeypatch.setattr(
        main_mod, "transcribe_audio_bytes",
        lambda _: ("turn on the lab lights", "en")
    )
    monkeypatch.setattr(
        main_mod, "chat_once",
        lambda text, history=None: "Understood. Activating lab lights."
    )
    monkeypatch.setattr(
        main_mod, "synthesize_wav",
        lambda text: make_silent_wav()
    )
    async def mock_check_wakeword(audio_bytes):
        return {"detected": {}, "has_wake_word": True, "enabled": True}
    monkeypatch.setattr(main_mod, "_check_wakeword", mock_check_wakeword)

    from app.main import app
    return TestClient(app)
