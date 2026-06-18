import subprocess
import tempfile
from pathlib import Path

from .config import TTS_ENGINE, PIPER_VOICE


def synthesize_wav(text: str) -> bytes:
    """
    Convert text to a WAV byte payload using the configured TTS engine.
    Returns raw WAV bytes ready to stream back to the ESP32.
    """
    if TTS_ENGINE == "piper":
        return _piper_synth(text)
    raise RuntimeError(f"Unsupported TTS engine: {TTS_ENGINE}")


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
