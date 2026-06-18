import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Ollama (remote LLM host)
# ---------------------------------------------------------------------------
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://BIG_MACHINE_IP:11434")
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
# Function calling / tool use
# Set to "false" to disable tool dispatch and use plain LLM responses.
# ---------------------------------------------------------------------------
FUNCTION_CALLING_ENABLED = os.getenv("FUNCTION_CALLING_ENABLED", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Remote STT microservice (big machine port 8001)
# ---------------------------------------------------------------------------
STT_HOST = os.getenv("STT_HOST", "http://BIG_MACHINE_IP:8001")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "faster-whisper-large-v3")

# ---------------------------------------------------------------------------
# Remote TTS microservice (big machine port 8002)
# ---------------------------------------------------------------------------
TTS_HOST = os.getenv("TTS_HOST", "http://BIG_MACHINE_IP:8002")
TTS_ENGINE = os.getenv("TTS_ENGINE", "kokoro")
PIPER_VOICE = os.getenv("PIPER_VOICE", os.getenv("KOKORO_VOICE", "bm_george"))

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# ---------------------------------------------------------------------------
# Dashboard weather widget (Open-Meteo, no API key required)
# ---------------------------------------------------------------------------
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "40.7128"))   # default: New York City
WEATHER_LON = float(os.getenv("WEATHER_LON", "-74.0060"))
