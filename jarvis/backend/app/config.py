import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://OLLAMA_HOST_IP:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e2b")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "turbo")
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You are Jarvis: a concise, calm, confident, and action-oriented AI assistant "
    "for a technically proficient user in embedded systems, home lab automation, "
    "and Linux orchestration. Be concise (1-3 sentences). Start with action or "
    "confirmation. Use short confirmations like 'Understood.' or 'Working on it.' "
    "Provide production-ready code and commands.",
)
TTS_ENGINE = os.getenv("TTS_ENGINE", "piper")
PIPER_VOICE = os.getenv("PIPER_VOICE", "/voices/jarvis_voice.onnx")
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
