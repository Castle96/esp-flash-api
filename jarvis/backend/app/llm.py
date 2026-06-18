import httpx

from .config import OLLAMA_HOST, OLLAMA_MODEL, SYSTEM_PROMPT


def chat_once(text: str, history: list[dict] | None = None) -> str:
    """
    Send a prompt to the remote Ollama instance and return the reply text.
    Uses a direct HTTP call so the Pi never needs the ollama Python package.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": text})

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }

    resp = httpx.post(
        f"{OLLAMA_HOST}/api/chat",
        json=payload,
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]
