import asyncio
import json
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from .config import OLLAMA_MODEL, PIPER_VOICE, TTS_ENGINE, WEATHER_LAT, WEATHER_LON, WHISPER_MODEL
from .llm import chat_once
from .models import (
    ChatRequest,
    ChatResponse,
    ConversationEntry,
    DeviceHeartbeatRequest,
    DeviceInfo,
    FlashJobAction,
    FlashJobCreateRequest,
    FlashJobInfo,
    HealthResponse,
    TranscribeResponse,
)
from .speech import transcribe_audio_bytes
from .state import (
    FLASH_APPROVED,
    FLASH_DONE,
    FLASH_FAILED,
    FLASH_PENDING,
    FLASH_REJECTED,
    FLASH_RUNNING,
    add_conversation_entry,
    create_flash_job,
    event_log,
    mark_event,
    register_device,
    state,
    update_flash_job,
)
from .tools import get_pending_reminder
from .tts import synthesize_wav

_FALLBACK_STT = "I'm sorry, I couldn't understand that audio. Please try again."
_FALLBACK_LLM = "I apologize, I'm having trouble thinking right now. Could you try rephrasing?"
_FALLBACK_EMPTY = "I didn't catch anything. Please hold the button and speak clearly."

app = FastAPI(title="Jarvis API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
# Device management
# ---------------------------------------------------------------------------

@app.post("/devices/heartbeat")
async def device_heartbeat(req: DeviceHeartbeatRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    dev = register_device(req.device_id, client_ip, req.name)
    mark_event(f"device:heartbeat:{req.device_id}")
    return {"ok": True, "device": dev}


@app.get("/devices", response_model=list[DeviceInfo])
async def list_devices():
    now = __import__("time").time()
    result = []
    for dev in state.devices.values():
        d = DeviceInfo(**dev)
        if now - d.last_seen > 120:
            d.online = False
        result.append(d)
    return result


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

@app.get("/conversation", response_model=list[ConversationEntry])
async def get_conversation():
    return [ConversationEntry(**e) for e in state.conversation]


# ---------------------------------------------------------------------------
# Weather proxy
# ---------------------------------------------------------------------------

@app.get("/weather", include_in_schema=False)
async def weather():
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": WEATHER_LAT,
                    "longitude": WEATHER_LON,
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "forecast_days": 4,
                    "timezone": "auto",
                },
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
    pending = sum(1 for j in state.flash_jobs.values() if j["status"] == FLASH_PENDING)
    return HealthResponse(
        status="ok",
        model=OLLAMA_MODEL,
        whisper=WHISPER_MODEL,
        tts=f"{TTS_ENGINE}:{PIPER_VOICE}",
        devices=len(state.devices),
        flash_jobs_pending=pending,
    )


# ---------------------------------------------------------------------------
# Flash / OTA firmware management
# ---------------------------------------------------------------------------

@app.post("/flash/jobs", response_model=FlashJobInfo)
async def create_flash(req: FlashJobCreateRequest):
    dev = state.devices.get(req.device_id)
    if not dev:
        raise HTTPException(status_code=404, detail=f"Device {req.device_id} not found")
    job = create_flash_job(
        device_id=req.device_id,
        device_name=req.device_name or dev.get("name", "ESP32"),
        source=req.firmware_code and "llm" or "upload",
        firmware_binary=req.firmware_binary,
        firmware_code=req.firmware_code,
        description=req.description,
    )
    return FlashJobInfo(**job)


@app.get("/flash/jobs", response_model=list[FlashJobInfo])
async def list_flash_jobs(status: str | None = None):
    jobs = list(state.flash_jobs.values())
    if status:
        jobs = [j for j in jobs if j["status"] == status]
    jobs.sort(key=lambda j: j["created_at"], reverse=True)
    return [FlashJobInfo(**j) for j in jobs]


async def _dispatch_ota(job: dict) -> str:
    dev = state.devices.get(job["device_id"])
    if not dev:
        raise ValueError("Device no longer registered")

    ota_url = f"http://{dev['ip']}/ota"
    payload = job.get("firmware_binary") or job.get("firmware_code") or ""

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            ota_url,
            content=payload,
            headers={"Content-Type": "application/octet-stream"},
        )
        resp.raise_for_status()
        return resp.text


@app.post("/flash/jobs/{job_id}/approve")
async def approve_flash(job_id: str):
    job = state.flash_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Flash job not found")
    if job["status"] != FLASH_PENDING:
        raise HTTPException(status_code=400, detail=f"Job is {job['status']}, not pending_review")

    update_flash_job(job_id, FLASH_RUNNING)
    mark_event(f"flash:approved:{job_id}")

    try:
        result = await _dispatch_ota(job)
        update_flash_job(job_id, FLASH_DONE)
        mark_event(f"flash:done:{job_id}")
        return {"ok": True, "status": FLASH_DONE, "detail": result}
    except Exception as exc:
        update_flash_job(job_id, FLASH_FAILED, str(exc))
        mark_event(f"flash:failed:{job_id}")
        raise HTTPException(status_code=502, detail=f"OTA flash failed: {exc}")


@app.post("/flash/jobs/{job_id}/reject")
async def reject_flash(job_id: str):
    job = state.flash_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Flash job not found")
    if job["status"] != FLASH_PENDING:
        raise HTTPException(status_code=400, detail=f"Job is {job['status']}, cannot reject")
    update_flash_job(job_id, FLASH_REJECTED)
    mark_event(f"flash:rejected:{job_id}")
    return {"ok": True, "status": FLASH_REJECTED}


@app.post("/flash/jobs/{job_id}/cancel")
async def cancel_flash(job_id: str):
    job = state.flash_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Flash job not found")
    if job["status"] not in (FLASH_PENDING, FLASH_RUNNING):
        raise HTTPException(status_code=400, detail=f"Job is {job['status']}, cannot cancel")
    update_flash_job(job_id, FLASH_REJECTED)
    mark_event(f"flash:cancelled:{job_id}")
    return {"ok": True, "status": FLASH_REJECTED}


# ---------------------------------------------------------------------------
# Single-shot voice endpoint (ESP32 primary path)
# ---------------------------------------------------------------------------

@app.post("/voice")
async def voice(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    mark_event("voice:recv")

    pending_reminder = get_pending_reminder()
    loop = asyncio.get_running_loop()

    try:
        text, language = await loop.run_in_executor(None, transcribe_audio_bytes, audio_bytes)
        mark_event(f"voice:transcribed:{language}")
    except Exception as exc:
        mark_event(f"voice:stt_error:{exc}")
        try:
            wav_bytes = await loop.run_in_executor(None, synthesize_wav, _FALLBACK_STT)
            return Response(content=wav_bytes, media_type="audio/wav")
        except Exception:
            raise HTTPException(status_code=503, detail="STT service unavailable")

    if not text.strip():
        reply = pending_reminder or _FALLBACK_EMPTY
        try:
            wav_bytes = await loop.run_in_executor(None, synthesize_wav, reply)
            return Response(content=wav_bytes, media_type="audio/wav")
        except Exception:
            raise HTTPException(status_code=422, detail="No speech detected")

    try:
        reply = await loop.run_in_executor(None, chat_once, text, state.history)
        mark_event("voice:llm_ok")
    except Exception as exc:
        mark_event(f"voice:llm_error:{exc}")
        reply = _FALLBACK_LLM

    if pending_reminder:
        reply = f"Reminder: {pending_reminder}. {reply}"

    state.history.extend([
        {"role": "user", "content": text},
        {"role": "assistant", "content": reply},
    ])
    if len(state.history) > 20:
        state.history = state.history[-20:]

    add_conversation_entry("user", text)
    add_conversation_entry("assistant", reply)

    try:
        wav_bytes = await loop.run_in_executor(None, synthesize_wav, reply)
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
    try:
        audio_bytes = await file.read()
        loop = asyncio.get_running_loop()
        text, language = await loop.run_in_executor(None, transcribe_audio_bytes, audio_bytes)
        return TranscribeResponse(text=text, language=language)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, chat_once, request.text, state.history)
        state.history.extend([
            {"role": "user", "content": request.text},
            {"role": "assistant", "content": reply},
        ])
        if len(state.history) > 20:
            state.history = state.history[-20:]
        add_conversation_entry("user", request.text)
        add_conversation_entry("assistant", reply)
        return ChatResponse(reply=reply, session_id=request.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/speak")
async def speak(request: ChatRequest):
    try:
        loop = asyncio.get_running_loop()
        wav_bytes = await loop.run_in_executor(None, synthesize_wav, request.text)
        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/history")
async def clear_history():
    state.history.clear()
    state.conversation.clear()
    return {"ok": True}
