import asyncio
import json
import sys
import time as time_module
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from loguru import logger
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .config import CORS_ORIGINS, ENV, GITEA_ADMIN_PASS, GITEA_ADMIN_USER, GITEA_ENABLED, GITEA_TOKEN, GITEA_URL, GITEA_WEBHOOK_SECRET, OLLAMA_HOST, OLLAMA_MODEL, PIPER_VOICE, STT_HOST, TTS_ENGINE, TTS_HOST, WAKEWORD_ENABLED, WAKEWORD_HOST, WEATHER_LAT, WEATHER_LON, WHISPER_MODEL

logger.remove()
logger.add(sys.stderr, level="INFO" if ENV != "production" else "WARNING")
logger.add("logs/diva.log", rotation="10 MB", retention="7 days", level="INFO")
from .llm import chat_once
from .models import (
    ChatRequest,
    ChatResponse,
    ConversationEntry,
    DeviceConfig,
    DeviceHeartbeatRequest,
    DeviceInfo,
    FleetActionRequest,
    FlashJobAction,
    FlashJobCreateRequest,
    FlashJobInfo,
    HealthResponse,
    LogEntry,
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
    add_device_log,
    create_flash_job,
    event_log,
    find_device_by_gitea_repo,
    get_device_logs,
    mark_event,
    register_device,
    state,
    update_flash_job,
    update_gitea_build_status,
)
from .tools import get_pending_reminder
from .tts import synthesize_wav
from .auth import AuthMiddleware, create_session_token, verify_request
from . import db

_FALLBACK_STT = "I'm sorry, I couldn't understand that audio. Please try again."
_FALLBACK_LLM = "I apologize, I'm having trouble thinking right now. Could you try rephrasing?"
_FALLBACK_EMPTY = "I didn't catch anything. Please hold the button and speak clearly."

_weather_cache: dict | None = None
_weather_cache_ts: float = 0.0
_weather_cache_ttl = 120

REQUEST_COUNT = Counter("diva_requests_total", "Total requests", ["method", "endpoint"])
VOICE_COUNT = Counter("diva_voice_total", "Voice pipeline calls", ["stage", "status"])
LATENCY = Histogram("diva_latency_seconds", "Request latency", ["endpoint"], buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0])

app = FastAPI(title="DIVA API", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    enabled=ENV == "production",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    start = time_module.time()
    response = await call_next(request)
    elapsed = time_module.time() - start

    path = request.url.path
    REQUEST_COUNT.labels(method=request.method, endpoint=path).inc()
    LATENCY.labels(endpoint=path).observe(elapsed)

    if elapsed > 1.0:
        logger.warning(f"{request.method} {path} took {elapsed:.2f}s")
    return response


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


_gitea_token = GITEA_TOKEN or ""
_gitea_token_lock = asyncio.Lock()


async def _gitea_ensure_token():
    global _gitea_token
    if _gitea_token:
        return _gitea_token
    async with _gitea_token_lock:
        if _gitea_token:
            return _gitea_token
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                login_resp = await c.post(
                    f"{GITEA_URL}/api/v1/users/{GITEA_ADMIN_USER}/tokens",
                    json={"name": "diva-webhook", "scopes": ["write:repository", "read:repository"]},
                    auth=(GITEA_ADMIN_USER, GITEA_ADMIN_PASS),
                )
                if login_resp.is_success:
                    _gitea_token = login_resp.json().get("sha1", "")
                    return _gitea_token
                list_resp = await c.get(
                    f"{GITEA_URL}/api/v1/users/{GITEA_ADMIN_USER}/tokens",
                    auth=(GITEA_ADMIN_USER, GITEA_ADMIN_PASS),
                )
                if list_resp.is_success:
                    tokens = list_resp.json()
                    for t in tokens:
                        if t.get("name") == "diva-webhook":
                            _gitea_token = t["sha1"]
                            return _gitea_token
                resp = await c.post(
                    f"{GITEA_URL}/api/v1/users/{GITEA_ADMIN_USER}/tokens",
                    json={"name": "diva-webhook"},
                )
                if resp.is_success:
                    _gitea_token = resp.json().get("sha1", "")
        except Exception as e:
            print(f"[gitea] Token acquisition failed: {e}")
    return _gitea_token


def _gitea_headers():
    return {"Authorization": f"token {_gitea_token}"} if _gitea_token else {}


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
    dev = register_device(req.device_id, client_ip, req.name, req.gitea_repo)
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


@app.get("/devices/{device_id}/config")
async def get_device_config(device_id: str):
    dev = state.devices.get(device_id)
    if not dev:
        raise HTTPException(404, "Device not found")
    return {
        "backend_url": None,
        "wakeword_sensitivity": 0.5,
        "led_brightness": 100,
    }


# ---------------------------------------------------------------------------
# Device logs
# ---------------------------------------------------------------------------

@app.post("/logs/{device_id}")
async def push_device_log(device_id: str, entry: LogEntry):
    add_device_log(device_id, entry.message, entry.level)
    return {"ok": True}


@app.get("/logs/{device_id}")
async def get_device_logs_json(device_id: str):
    return get_device_logs(device_id, limit=50)


@app.get("/logs/{device_id}/stream")
async def stream_device_logs(device_id: str, request: Request):
    async def generate():
        sent: float = 0.0
        while True:
            if await request.is_disconnected():
                break
            logs = get_device_logs(device_id, limit=50)
            new = [e for e in logs if e["ts"] > sent]
            for e in new:
                yield f"data: {json.dumps(e)}\n\n"
                sent = e["ts"]
            await asyncio.sleep(1.0)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

@app.get("/conversation", response_model=list[ConversationEntry])
async def get_conversation():
    return [ConversationEntry(**e) for e in db.get_conversation()]


# ---------------------------------------------------------------------------
# Weather proxy
# ---------------------------------------------------------------------------

@app.get("/weather", include_in_schema=False)
async def weather():
    global _weather_cache, _weather_cache_ts
    now = time_module.time()
    if _weather_cache and (now - _weather_cache_ts) < _weather_cache_ttl:
        return _weather_cache
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
            _weather_cache = resp.json()
            _weather_cache_ts = now
            return _weather_cache
        except Exception as exc:
            if _weather_cache:
                return _weather_cache
            raise HTTPException(status_code=502, detail=f"Weather fetch failed: {exc}")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/login")
@limiter.limit("10/minute")
async def login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    if username != GITEA_ADMIN_USER or password != GITEA_ADMIN_PASS:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token, expires_in = create_session_token(username)
    return {"token": token, "expires_in": expires_in, "token_type": "Bearer"}


@app.get("/auth/keys")
async def list_auth_keys(request: Request):
    if request.state.auth.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin only")
    return db.list_api_keys()


@app.post("/auth/keys")
@limiter.limit("10/minute")
async def create_auth_key(request: Request):
    if request.state.auth.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin only")
    body = await request.json()
    name = body.get("name", "unnamed")
    role = body.get("role", "admin")
    key = db.create_api_key(name, role)
    return {"key": key, "name": name, "role": role, "warning": "Save this key - it won't be shown again"}


@app.delete("/auth/keys/{key_id}")
async def delete_auth_key(key_id: int, request: Request):
    if request.state.auth.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin only")
    if db.delete_api_key(key_id):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="Key not found")


# ---------------------------------------------------------------------------
# Health (with dependency probing)
# ---------------------------------------------------------------------------

async def _probe_service(url: str, timeout: float = 5.0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            resp = await c.get(f"{url}/health")
            if resp.is_success:
                return {"status": "ok"}
            return {"status": "error", "detail": f"HTTP {resp.status_code}"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


@app.get("/health", response_model=HealthResponse)
async def health(deps: bool = False):
    pending = 0
    for j in db.get_flash_jobs():
        if j["status"] == FLASH_PENDING:
            pending += 1
    devices = db.get_all_devices()

    result = HealthResponse(
        status="ok",
        model=OLLAMA_MODEL,
        whisper=WHISPER_MODEL,
        tts=f"{TTS_ENGINE}:{PIPER_VOICE}",
        devices=len(devices),
        flash_jobs_pending=pending,
        wakeword=WAKEWORD_ENABLED,
        gitea_url=GITEA_URL if GITEA_ENABLED else None,
    )

    if deps:
        deps_status = {
            "ollama": await _probe_service(OLLAMA_HOST.replace("/api/chat", "")),
            "stt": await _probe_service(STT_HOST),
            "tts": await _probe_service(TTS_HOST),
        }
        if WAKEWORD_ENABLED:
            deps_status["wakeword"] = await _probe_service(WAKEWORD_HOST)
        if GITEA_ENABLED:
            try:
                async with httpx.AsyncClient(timeout=5.0) as c:
                    resp = await c.get(f"{GITEA_URL}/api/v1/version")
                    deps_status["gitea"] = {"status": "ok" if resp.is_success else "error"}
            except Exception as exc:
                deps_status["gitea"] = {"status": "error", "detail": str(exc)}
        result.dependencies = deps_status
        all_ok = all(d["status"] == "ok" for d in deps_status.values())
        if not all_ok:
            result.status = "degraded"

    return result


# ---------------------------------------------------------------------------
# Flash / OTA firmware management
# ---------------------------------------------------------------------------

@app.post("/flash/jobs", response_model=FlashJobInfo)
@limiter.limit("10/minute")
async def create_flash(request: Request, req: FlashJobCreateRequest):
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
@limiter.limit("10/minute")
async def approve_flash(request: Request, job_id: str):
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
@limiter.limit("10/minute")
async def reject_flash(request: Request, job_id: str):
    job = state.flash_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Flash job not found")
    if job["status"] != FLASH_PENDING:
        raise HTTPException(status_code=400, detail=f"Job is {job['status']}, cannot reject")
    update_flash_job(job_id, FLASH_REJECTED)
    mark_event(f"flash:rejected:{job_id}")
    return {"ok": True, "status": FLASH_REJECTED}


@app.post("/flash/jobs/{job_id}/cancel")
@limiter.limit("10/minute")
async def cancel_flash(request: Request, job_id: str):
    job = state.flash_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Flash job not found")
    if job["status"] not in (FLASH_PENDING, FLASH_RUNNING):
        raise HTTPException(status_code=400, detail=f"Job is {job['status']}, cannot cancel")
    update_flash_job(job_id, FLASH_REJECTED)
    mark_event(f"flash:cancelled:{job_id}")
    return {"ok": True, "status": FLASH_REJECTED}


# ---------------------------------------------------------------------------
# Fleet actions
# ---------------------------------------------------------------------------

@app.post("/fleet/action")
@limiter.limit("10/minute")
async def fleet_action(request: Request, req: FleetActionRequest):
    if req.action == "reboot":
        return await _fleet_reboot(req.device_ids)
    elif req.action == "flash_approve":
        return await _fleet_flash_approve(req.device_ids)
    return {"ok": False, "error": f"Unknown action: {req.action}"}


async def _fleet_reboot(device_ids: list[str]):
    results = {}
    for did in device_ids:
        dev = state.devices.get(did)
        if not dev:
            results[did] = {"ok": False, "error": "not_found"}
            continue
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.post(f"http://{dev['ip']}/reboot")
                resp.raise_for_status()
                results[did] = {"ok": True}
                mark_event(f"device:reboot:{did}")
        except Exception as e:
            results[did] = {"ok": False, "error": str(e)}
    return {"ok": True, "results": results}


async def _fleet_flash_approve(device_ids: list[str]):
    approved = [jid for jid, j in state.flash_jobs.items() if j["device_id"] in device_ids and j["status"] == FLASH_PENDING]
    results = {}
    for jid in approved:
        try:
            resp = await approve_flash(jid)
            results[jid] = resp
        except HTTPException as e:
            results[jid] = {"ok": False, "detail": e.detail}
    return {"ok": True, "approved": len(approved), "results": results}


# ---------------------------------------------------------------------------
# Wake word detection
# ---------------------------------------------------------------------------

def _normalize_audio(audio_bytes: bytes) -> bytes:
    if audio_bytes[:4] != b"RIFF":
        return _pcm_to_wav(audio_bytes)
    return audio_bytes


def _pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    import io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


async def _check_wakeword(audio_bytes: bytes) -> dict:
    if not WAKEWORD_ENABLED:
        return {"detected": {}, "has_wake_word": False, "enabled": False}
    try:
        wav = _normalize_audio(audio_bytes)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{WAKEWORD_HOST}/detect",
                files={"file": ("audio.wav", wav, "audio/wav")},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        mark_event(f"voice:wakeword_error:{exc}")
        return {"detected": {}, "has_wake_word": False, "enabled": True, "error": str(exc)}


@app.get("/wakeword/status")
async def wakeword_status():
    if not WAKEWORD_ENABLED:
        return {"enabled": False, "status": "disabled"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{WAKEWORD_HOST}/health")
            resp.raise_for_status()
            data = resp.json()
            return {"enabled": True, "status": "ok", **data}
    except Exception as exc:
        return {"enabled": True, "status": "error", "detail": str(exc)}


@app.get("/wakeword/custom")
async def list_custom_wakewords():
    if not WAKEWORD_ENABLED:
        return {"custom_wake_words": []}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{WAKEWORD_HOST}/custom")
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        return {"custom_wake_words": [], "error": str(exc)}


@app.post("/wakeword/detect")
async def wakeword_detect(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    result = await _check_wakeword(audio_bytes)
    if result.get("enabled", True):
        if result.get("has_wake_word"):
            mark_event(f"voice:wakeword:detected")
    return result


@app.post("/wakeword/train/{name}")
@limiter.limit("5/minute")
async def train_wakeword(request: Request, name: str, file: UploadFile = File(...)):
    if not WAKEWORD_ENABLED:
        raise HTTPException(status_code=400, detail="Wake word detection is disabled")
    audio_bytes = await file.read()
    wav = _normalize_audio(audio_bytes)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{WAKEWORD_HOST}/custom/{name}/train",
            files={"file": ("audio.wav", wav, "audio/wav")},
        )
        resp.raise_for_status()
        return resp.json()


@app.delete("/wakeword/custom/{name}")
async def delete_custom_wakeword(name: str):
    if not WAKEWORD_ENABLED:
        raise HTTPException(status_code=400, detail="Wake word detection is disabled")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.delete(f"{WAKEWORD_HOST}/custom/{name}")
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail="Wake word not found")
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Single-shot voice endpoint (ESP32 primary path)
# ---------------------------------------------------------------------------

@app.post("/voice")
@limiter.limit("10/minute")
async def voice(request: Request, file: UploadFile = File(...)):
    audio_bytes = await file.read()
    mark_event("voice:recv")

    if WAKEWORD_ENABLED:
        wake = await _check_wakeword(audio_bytes)
        if not wake.get("has_wake_word"):
            mark_event("voice:wakeword:not_detected")
            return Response(
                content=b"",
                media_type="audio/wav",
                headers={"X-Wakeword": "false"},
            )
        mark_event("voice:wakeword:detected")

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
@limiter.limit("20/minute")
async def transcribe(request: Request, file: UploadFile = File(...)):
    try:
        audio_bytes = await file.read()
        loop = asyncio.get_running_loop()
        text, language = await loop.run_in_executor(None, transcribe_audio_bytes, audio_bytes)
        return TranscribeResponse(text=text, language=language)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(request: Request, body: ChatRequest):
    try:
        loop = asyncio.get_running_loop()
        reply = await loop.run_in_executor(None, chat_once, body.text, state.history)
        state.history.extend([
            {"role": "user", "content": body.text},
            {"role": "assistant", "content": reply},
        ])
        if len(state.history) > 20:
            state.history = state.history[-20:]
        add_conversation_entry("user", body.text)
        add_conversation_entry("assistant", reply)
        return ChatResponse(reply=reply, session_id=body.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/speak")
@limiter.limit("30/minute")
async def speak(request: Request, body: ChatRequest):
    try:
        loop = asyncio.get_running_loop()
        wav_bytes = await loop.run_in_executor(None, synthesize_wav, body.text)
        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Gitea integration
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def _gitea_startup():
    """On boot, acquire token and log available repos."""
    if not GITEA_ENABLED:
        return

    await _gitea_ensure_token()
    headers = _gitea_headers()
    async with httpx.AsyncClient(timeout=10.0) as c:
        try:
            resp = await c.get(f"{GITEA_URL}/api/v1/repos/search", params={"limit": 5}, headers=headers)
            if resp.is_success:
                data = resp.json()
                repos = [r["full_name"] for r in data.get("data", [])]
                print(f"[gitea] Found {len(repos)} repos: {repos}")
                if _gitea_token:
                    print(f"[gitea] Token acquired: {_gitea_token[:8]}...")
        except Exception as e:
            print(f"[gitea] Startup check failed: {e}")


@app.get("/gitea/status")
async def gitea_status():
    if not GITEA_ENABLED:
        return {"enabled": False, "url": None}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{GITEA_URL}/api/v1/version", headers=_gitea_headers())
            resp.raise_for_status()
            data = resp.json()
            return {
                "enabled": True,
                "url": GITEA_URL,
                "version": data.get("version", "unknown"),
            }
    except Exception as exc:
        return {"enabled": True, "url": GITEA_URL, "version": None, "error": str(exc)}


@app.get("/gitea/repos")
async def gitea_repos():
    if not GITEA_ENABLED:
        return {"repos": []}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{GITEA_URL}/api/v1/repos/search", params={"limit": 50}, headers=_gitea_headers())
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        return {"repos": [], "error": str(exc)}


@app.post("/gitea/webhook")
async def gitea_webhook(request: Request):
    if not GITEA_ENABLED:
        raise HTTPException(400, "Gitea integration disabled")

    signature = request.headers.get("X-Gitea-Signature", "")
    body_bytes = await request.body()
    if GITEA_WEBHOOK_SECRET and signature:
        import hashlib, hmac
        expected = hmac.new(GITEA_WEBHOOK_SECRET.encode(), body_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(401, "Invalid webhook signature")
    body = json.loads(body_bytes)

    event = request.headers.get("X-Gitea-Event", "push")

    if event == "push":
        ref = body.get("ref", "")
        if not ref.startswith("refs/heads/"):
            return {"ok": True, "ignored": f"Not a branch push: {ref}"}

        repo_full = body.get("repository", {}).get("full_name", "")
        branch = ref.replace("refs/heads/", "")
        default_branch = body.get("repository", {}).get("default_branch", "main")

        if branch != default_branch:
            return {"ok": True, "ignored": f"Push to {branch}, not default ({default_branch})"}

        await _gitea_ensure_token()

        dev = find_device_by_gitea_repo(repo_full)
        if not dev:
            return {"ok": True, "ignored": f"No device matched for repo {repo_full}"}

        # Get raw file content from Gitea for the main.py (or detect entry point)
        firmware_code = await _fetch_repo_firmware(repo_full, branch)
        if not firmware_code:
            return {"ok": True, "ignored": "No firmware entry point found in repo"}

        commit_msg = ""
        commits = body.get("commits", [])
        if commits:
            commit_msg = commits[-1].get("message", "").split("\n")[0]

        job = create_flash_job(
            device_id=dev["id"],
            device_name=dev.get("name", "ESP32"),
            source="gitea_push",
            firmware_code=firmware_code,
            description=f"[{repo_full}] {commit_msg}".strip(),
        )
        mark_event(f"gitea:push:{dev['id']}:{repo_full}")
        return {"ok": True, "job_id": job["id"], "device_id": dev["id"]}

    elif event == "workflow_run":
        repo_full = body.get("repository", {}).get("full_name", "")
        workflow = body.get("workflow_run", {})
        status = workflow.get("status", "unknown")
        conclusion = workflow.get("conclusion", "")
        sha = workflow.get("head_sha", "")
        run_url = workflow.get("html_url", "")

        build_status = conclusion if conclusion else status
        update_gitea_build_status(repo_full, build_status, sha, run_url)
        mark_event(f"gitea:build:{repo_full}:{build_status}")
        return {"ok": True, "status": build_status}

    return {"ok": True, "event": event, "ignored": "unhandled event type"}


async def _fetch_repo_firmware(repo_full: str, branch: str) -> str | None:
    """Try to fetch main.py or boot.py from a Gitea repo."""
    candidates = ["main.py", "boot.py", "firmware/main.py", "src/main.py"]
    for path in candidates:
        url = f"{GITEA_URL}/api/v1/repos/{repo_full}/raw/{path}?ref={branch}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.get(url, headers=_gitea_headers())
                if resp.is_success:
                    return resp.text
        except Exception:
            continue
    return None


@app.get("/gitea/actions/{repo_full:path}")
async def gitea_actions_status(repo_full: str):
    """Fetch latest Actions run status for a repo."""
    if not GITEA_ENABLED:
        return {"status": "disabled"}
    await _gitea_ensure_token()
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            url = f"{GITEA_URL}/api/v1/repos/{repo_full}/actions/runs?limit=1"
            resp = await c.get(url, headers=_gitea_headers())
            if not resp.is_success:
                return {"status": "unknown"}
            data = resp.json()
            runs = data.get("workflow_runs", [])
            if runs:
                r = runs[0]
                return {
                    "status": r.get("conclusion", r.get("status", "unknown")),
                    "sha": r.get("head_sha", "")[:8],
                    "run_url": r.get("html_url", ""),
                    "ts": r.get("run_started_at", ""),
                }
            return {"status": "no_runs"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@app.post("/gitea/webhook/setup")
async def gitea_setup_webhook(request: Request):
    """Register this backend as a webhook in Gitea for all repos."""
    if not GITEA_ENABLED:
        raise HTTPException(400, "Gitea integration disabled")
    await _gitea_ensure_token()
    if not _gitea_token:
        raise HTTPException(401, "No Gitea token available. Set GITEA_TOKEN in .env or ensure admin credentials are correct.")
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            # Get all repos
            repos_resp = await c.get(
                f"{GITEA_URL}/api/v1/repos/search", params={"limit": 50},
                headers=_gitea_headers(),
            )
            if not repos_resp.is_success:
                raise HTTPException(502, "Failed to list Gitea repos")
            repos = repos_resp.json().get("data", [])

            hook_url = str(request.base_url).rstrip("/") + "/gitea/webhook"
            results = []
            for repo in repos:
                full_name = repo["full_name"]
                # Check if hook already exists
                hooks_resp = await c.get(
                    f"{GITEA_URL}/api/v1/repos/{full_name}/hooks",
                    headers=_gitea_headers(),
                )
                if hooks_resp.is_success:
                    existing = [h for h in hooks_resp.json() if h.get("config", {}).get("url") == hook_url]
                    if existing:
                        results.append({"repo": full_name, "status": "already_exists"})
                        continue

                hook_payload = {
                    "type": "gitea",
                    "config": {
                        "url": hook_url,
                        "content_type": "json",
                        "secret": GITEA_WEBHOOK_SECRET,
                    },
                    "events": ["push", "workflow_run"],
                    "active": True,
                }
                create_resp = await c.post(
                    f"{GITEA_URL}/api/v1/repos/{full_name}/hooks",
                    json=hook_payload,
                    headers=_gitea_headers(),
                )
                results.append({
                    "repo": full_name,
                    "status": "created" if create_resp.is_success else "failed",
                    "detail": create_resp.text[:200] if not create_resp.is_success else "",
                })
            return {"ok": True, "results": results}
    except Exception as exc:
        raise HTTPException(502, f"Webhook setup failed: {exc}")


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@app.delete("/history")
async def clear_history():
    state.history.clear()
    db.clear_conversation()
    return {"ok": True}
