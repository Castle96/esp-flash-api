from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

from .config import OLLAMA_MODEL, PIPER_VOICE, TTS_ENGINE, WHISPER_MODEL
from .llm import chat_once
from .models import ChatRequest, ChatResponse, HealthResponse, TranscribeResponse
from .speech import transcribe_audio_bytes
from .state import mark_event, state
from .tts import synthesize_wav

app = FastAPI(title="Jarvis API", version="1.0.0")


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
    """
    try:
        audio_bytes = await file.read()
        mark_event("voice:recv")

        # Step 1: speech -> text
        text, language = transcribe_audio_bytes(audio_bytes)
        mark_event(f"voice:transcribed:{language}")

        if not text.strip():
            raise HTTPException(status_code=422, detail="No speech detected")

        # Step 2: text -> LLM reply
        reply = chat_once(text, state.history)
        mark_event("voice:llm_ok")

        # Update conversation history (keep last 10 turns)
        state.history.extend([
            {"role": "user", "content": text},
            {"role": "assistant", "content": reply},
        ])
        if len(state.history) > 20:
            state.history = state.history[-20:]

        # Step 3: reply -> speech
        wav_bytes = synthesize_wav(reply)
        mark_event("voice:tts_ok")

        return Response(content=wav_bytes, media_type="audio/wav")

    except HTTPException:
        raise
    except Exception as e:
        mark_event(f"voice:error:{e}")
        raise HTTPException(status_code=500, detail=str(e))


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
