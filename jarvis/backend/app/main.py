import asyncio
import json
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from .config import OLLAMA_MODEL, PIPER_VOICE, TTS_ENGINE, WEATHER_LAT, WEATHER_LON, WHISPER_MODEL
from .llm import chat_once
from .models import ChatRequest, ChatResponse, HealthResponse, TranscribeResponse
from .speech import transcribe_audio_bytes
from .state import event_log, mark_event, state
from .tools import get_pending_reminder
from .tts import synthesize_wav

# ---------------------------------------------------------------------------
# Canned fallback responses for each pipeline stage failure.
# The user always receives spoken audio, never silence or a raw error.
# ---------------------------------------------------------------------------
_FALLBACK_STT  = "I'm sorry, I couldn't understand that audio. Please try again."
_FALLBACK_LLM  = "I apologize, I'm having trouble thinking right now. Could you try rephrasing?"
_FALLBACK_EMPTY = "I didn't catch anything. Please hold the button and speak clearly."

app = FastAPI(title="Jarvis API", version="1.0.0")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    return HTMLResponse((Path(__file__).parent / "static" / "index.html").read_text())


# ---------------------------------------------------------------------------
# Server-Sent Events — live pipeline activity stream
# ---------------------------------------------------------------------------

@app.get("/events", include_in_schema=False)
async def sse_events(request: Request):
    async def generate():
        last_ts: float = 0.0
        while True:
            if await request.is_disconnected():
                break
            snapshot = list(event_log)
            new = [e for e in snapshot if e["ts"] > last_ts]
            for evt in sorted(new, key=lambda x: x["ts"]):
                yield f"data: {json.dumps(evt)}\n\n"
                last_ts = evt["ts"]
            await asyncio.sleep(0.5)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Weather proxy — calls Open-Meteo (free, no API key)
# ---------------------------------------------------------------------------

@app.get("/weather", include_in_schema=False)
async def weather():
    try:
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": WEATHER_LAT,
                "longitude": WEATHER_LON,
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "forecast_days": 4,
                "timezone": "auto",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Weather fetch failed: {exc}")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        model=OLLAMA_MODEL,
        whisper=WHISPER_MODEL,
        tts=f"{TTS_ENGINE}:{PIPER_VOICE}",
    )


# ---------------------------------------------------------------------------
# Single-shot voice endpoint (ESP32 primary path)
# Audio in -> STT -> Ollama -> TTS -> WAV out
# ---------------------------------------------------------------------------

@app.post("/voice")
async def voice(file: UploadFile = File(...)):
    """
    Primary ESP32 endpoint.
    Accepts raw PCM or WAV audio, returns a WAV audio reply.
    Each pipeline stage fails gracefully with a canned spoken response
    so the user always receives audio rather than an error code.
    """
    audio_bytes = await file.read()
    mark_event("voice:recv")

    # Deliver any pending reminder first, prepended to the assistant reply.
    pending_reminder = get_pending_reminder()

    # -----------------------------------------------------------------------
    # Step 1: speech -> text
    # -----------------------------------------------------------------------
    try:
        text, language = transcribe_audio_bytes(audio_bytes)
        mark_event(f"voice:transcribed:{language}")
    except Exception as exc:
        mark_event(f"voice:stt_error:{exc}")
        # If STT is completely unavailable, speak the fallback and return.
        try:
            wav_bytes = synthesize_wav(_FALLBACK_STT)
            return Response(content=wav_bytes, media_type="audio/wav")
        except Exception:
            raise HTTPException(status_code=503, detail="STT service unavailable")

    if not text.strip():
        # No speech detected — deliver a pending reminder if one exists,
        # otherwise speak the empty-audio fallback.
        reply = pending_reminder or _FALLBACK_EMPTY
        try:
            wav_bytes = synthesize_wav(reply)
            return Response(content=wav_bytes, media_type="audio/wav")
        except Exception:
            raise HTTPException(status_code=422, detail="No speech detected")

    # -----------------------------------------------------------------------
    # Step 2: text -> LLM reply
    # -----------------------------------------------------------------------
    try:
        reply = chat_once(text, state.history)
        mark_event("voice:llm_ok")
    except Exception as exc:
        mark_event(f"voice:llm_error:{exc}")
        reply = _FALLBACK_LLM

    # Prepend any pending reminder to the spoken reply.
    if pending_reminder:
        reply = f"Reminder: {pending_reminder}. {reply}"

    # Update conversation history (keep last 20 messages / 10 turns).
    state.history.extend([
        {"role": "user", "content": text},
        {"role": "assistant", "content": reply},
    ])
    if len(state.history) > 20:
        state.history = state.history[-20:]

    # -----------------------------------------------------------------------
    # Step 3: reply -> speech
    # -----------------------------------------------------------------------
    try:
        wav_bytes = synthesize_wav(reply)
        mark_event("voice:tts_ok")
    except Exception as exc:
        mark_event(f"voice:tts_error:{exc}")
        raise HTTPException(status_code=503, detail=f"TTS service unavailable: {exc}")

    return Response(content=wav_bytes, media_type="audio/wav")


# ---------------------------------------------------------------------------
# Debug / diagnostic endpoints
# ---------------------------------------------------------------------------

@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...)):
    """Debug: audio in -> transcript only."""
    try:
        audio_bytes = await file.read()
        text, language = transcribe_audio_bytes(audio_bytes)
        return TranscribeResponse(text=text, language=language)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Debug: text in -> LLM reply only."""
    try:
        reply = chat_once(request.text, state.history)
        state.history.extend([
            {"role": "user", "content": request.text},
            {"role": "assistant", "content": reply},
        ])
        if len(state.history) > 20:
            state.history = state.history[-20:]
        return ChatResponse(reply=reply, session_id=request.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/speak")
async def speak(request: ChatRequest):
    """Debug: text in -> WAV audio out."""
    try:
        wav_bytes = synthesize_wav(request.text)
        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/history")
async def clear_history():
    """Clear conversation history."""
    state.history.clear()
    return {"ok": True}
