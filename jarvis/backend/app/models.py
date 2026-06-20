from pydantic import BaseModel


class ChatRequest(BaseModel):
    text: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str | None = None


class TranscribeResponse(BaseModel):
    text: str
    language: str | None = None


class HealthResponse(BaseModel):
    status: str
    model: str
    whisper: str
    tts: str
    devices: int
    flash_jobs_pending: int


class DeviceHeartbeatRequest(BaseModel):
    device_id: str
    name: str = "ESP32-C3"


class DeviceInfo(BaseModel):
    id: str
    name: str
    ip: str
    last_seen: float
    first_seen: float
    online: bool = True


class ConversationEntry(BaseModel):
    role: str
    content: str
    ts: float


class FlashJobCreateRequest(BaseModel):
    device_id: str
    device_name: str = ""
    description: str = ""
    firmware_binary: str | None = None
    firmware_code: str | None = None


class FlashJobAction(BaseModel):
    job_id: str


class FlashJobInfo(BaseModel):
    id: str
    device_id: str
    device_name: str
    source: str
    status: str
    description: str
    firmware_binary: str | None = None
    firmware_code: str | None = None
    created_at: float
    updated_at: float
    error: str | None = None
