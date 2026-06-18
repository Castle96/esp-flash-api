import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Ollama (remote LLM host)
# ---------------------------------------------------------------------------
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://OLLAMA_HOST_IP:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:27b")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are Jarvis: a concise, calm, confident, and action-oriented AI assistant "
    "for a technically proficient user in embedded systems, home lab automation, "
    "and Linux orchestration. Be concise (1-3 sentences). Start with action or "
    "confirmation. Use short confirmations like 'Understood.' or 'Working on it.' "
    "Provide production-ready code and commands.",
)

# ---------------------------------------------------------------------------
# Speech-to-text (faster-whisper)
# ---------------------------------------------------------------------------
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "Systran/faster-whisper-large-v3")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------
TTS_ENGINE = os.getenv("TTS_ENGINE", "kokoro")          # kokoro | xtts | piper

# Kokoro (CPU-native ONNX, default)
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "bm_george")   # British male, authoritative
KOKORO_SPEED = float(os.getenv("KOKORO_SPEED", "1.0"))

# XTTS v2 (GPU, voice cloning - swap in when GPU arrives)
XTTS_VOICE_REF = os.getenv("XTTS_VOICE_REF", "/voices/jarvis_reference.wav")

# Piper (legacy fallback)
PIPER_VOICE = os.getenv("PIPER_VOICE", "/voices/jarvis_voice.onnx")

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
