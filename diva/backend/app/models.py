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
    wakeword: bool = False
    gitea_url: str | None = None


class DeviceHeartbeatRequest(BaseModel):
    device_id: str
    name: str = "ESP32-C3"
    gitea_repo: str | None = None


class DeviceInfo(BaseModel):
    id: str
    name: str
    ip: str
    last_seen: float
    first_seen: float
    online: bool = True
    gitea_repo: str | None = None


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


class LogEntry(BaseModel):
    device_id: str
    message: str
    level: str = "info"
    ts: float = 0.0


class FleetActionRequest(BaseModel):
    device_ids: list[str]
    action: str  # "reboot" | "flash" | "ota_config"


class DeviceConfig(BaseModel):
    wifi_ssid: str | None = None
    wifi_password: str | None = None
    led_brightness: int | None = None
    wakeword_sensitivity: float | None = None
    backend_url: str | None = None
