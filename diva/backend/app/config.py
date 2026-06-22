import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Production settings
# ---------------------------------------------------------------------------
ENV = os.getenv("ENV", "development")
DEBUG = ENV != "production"

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false").lower() == "true"
JWT_SECRET = os.getenv("JWT_SECRET", os.urandom(32).hex())
GITEA_WEBHOOK_SECRET = os.getenv("GITEA_WEBHOOK_SECRET", os.urandom(16).hex())

# ---------------------------------------------------------------------------
# Ollama (remote LLM host)
# ---------------------------------------------------------------------------
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://BIG_MACHINE_IP:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:27b")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are DIVA: a concise, calm, confident, and action-oriented AI assistant "
    "for a technically proficient user in embedded systems, home lab automation, "
    "and Linux orchestration. Be concise (1-3 sentences). Start with action or "
    "confirmation. Use short confirmations like 'Understood.' or 'Working on it.' "
    "Provide production-ready code and commands.",
)

# ---------------------------------------------------------------------------
# Function calling / tool use
# ---------------------------------------------------------------------------
FUNCTION_CALLING_ENABLED = os.getenv("FUNCTION_CALLING_ENABLED", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Remote STT microservice
# ---------------------------------------------------------------------------
STT_HOST = os.getenv("STT_HOST", "http://BIG_MACHINE_IP:8001")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "faster-whisper-large-v3")

# ---------------------------------------------------------------------------
# Remote TTS microservice
# ---------------------------------------------------------------------------
TTS_HOST = os.getenv("TTS_HOST", "http://BIG_MACHINE_IP:8002")
TTS_ENGINE = os.getenv("TTS_ENGINE", "kokoro")
PIPER_VOICE = os.getenv("PIPER_VOICE", os.getenv("KOKORO_VOICE", "bm_george"))
TTS_LANGUAGE = os.getenv("TTS_LANGUAGE", "en-us")

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# ---------------------------------------------------------------------------
# Dashboard weather widget (Open-Meteo, no API key required)
# ---------------------------------------------------------------------------
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "40.7128"))
WEATHER_LON = float(os.getenv("WEATHER_LON", "-74.0060"))

# ---------------------------------------------------------------------------
# Remote wake word microservice
# ---------------------------------------------------------------------------
WAKEWORD_HOST = os.getenv("WAKEWORD_HOST", "http://BIG_MACHINE_IP:8003")
WAKEWORD_ENABLED = os.getenv("WAKEWORD_ENABLED", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Gitea server
# ---------------------------------------------------------------------------
GITEA_URL = os.getenv("GITEA_URL", "http://100.120.207.67:30529")
GITEA_ENABLED = os.getenv("GITEA_ENABLED", "true").lower() == "true"
GITEA_TOKEN = os.getenv("GITEA_TOKEN", "")
GITEA_ADMIN_USER = os.getenv("GITEA_ADMIN_USER", "admin")
GITEA_ADMIN_PASS = os.getenv("GITEA_ADMIN_PASS", "")
