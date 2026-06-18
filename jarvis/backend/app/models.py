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
