import os

import httpx
from dotenv import load_dotenv

load_dotenv()

TTS_HOST = os.getenv("TTS_HOST", "http://BIG_MACHINE_IP:8002")


def synthesize_wav(text: str) -> bytes:
    """
    Forward text to the remote TTS microservice on the big machine.
    Returns raw WAV bytes.
    """
    resp = httpx.post(
        f"{TTS_HOST}/speak",
        json={"text": text},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.content
