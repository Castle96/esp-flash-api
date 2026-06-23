# Architecture

```mermaid
graph TB
    subgraph "ESP32-C3 Fleet"
        ESP32["ESP32-C3<br/>INMP441 I2S mic<br/>MAX98357A I2S speaker"]
        ESP32_OTA["ESP32-C3<br/>OTA lite<br/>(no audio HW)"]
    end

    subgraph "Pi 5 — arceus (8GB)"
        GATEWAY["DIVA Gateway<br/>FastAPI :8000"]
        DB[("SQLite<br/>diva.db")]
        DASH["Dashboard SPA<br/>Catppuccin Mocha"]
        SSE["SSE Event Stream"]
        GATEWAY --> DB
        GATEWAY --> DASH
        GATEWAY --> SSE
    end

    subgraph "x86_64 — stargame (62GB)"
        STT["STT Service :8001<br/>faster-whisper-large-v3"]
        TTS["TTS Service :8002<br/>Kokoro-82M"]
        WW["WakeWord :8003<br/>openWakeWord"]
        OLLAMA["Ollama :11434<br/>gemma4:e4b"]
    end

    subgraph "Gitea :30529"
        GITEA["Gitea<br/>Firmware repos"]
        ACTIONS["Gitea Actions<br/>CI builds"]
    end

    ESP32 -- "PCM audio (16kHz 16-bit)" --> GATEWAY
    ESP32_OTA -- "POST /devices/heartbeat" --> GATEWAY
    GATEWAY -- "POST /voice" --> ESP32
    GATEWAY_OTA -- "POST /ota" --> ESP32_OTA

    GATEWAY -- "STT: /transcribe" --> STT
    GATEWAY -- "LLM: /api/chat" --> OLLAMA
    GATEWAY -- "TTS: /speak" --> TTS
    GATEWAY -- "WakeWord: /detect" --> WW

    GATEWAY -- "webhooks / flash jobs" --> GITEA
    GITEA -- "build status" --> GATEWAY

    Browser["Browser"] -- "HTTP / SSE" --> GATEWAY
```

## Voice Pipeline

```mermaid
sequenceDiagram
    participant ESP32 as ESP32-C3
    participant GW as Pi Gateway
    participant STT as STT (stargame)
    participant LLM as Ollama (stargame)
    participant TTS as TTS (stargame)

    ESP32->>GW: POST /voice (PCM audio)
    Note over GW: Optional wake word check
    
    GW->>STT: POST /transcribe
    STT-->>GW: {text, language}
    
    GW->>LLM: POST /api/chat
    Note over LLM: Tool calling loop<br/>(devices, flash, reminders)
    LLM-->>GW: {response}
    
    GW->>TTS: POST /speak
    TTS-->>GW: WAV audio
    
    GW-->>ESP32: WAV response
    Note over ESP32: Play PCM on I2S speaker
```

## Deployment Topology

| Machine | Role | Specs | Services |
|---------|------|-------|----------|
| **arceus** | DIVA Gateway | Pi 5, 8GB RAM | FastAPI gateway, SQLite, Dashboard SPA |
| **stargame** | Inference node | x86_64, 62GB RAM | STT (:8001), TTS (:8002), WakeWord (:8003), Ollama (:11434) |
| **stargame** | Code hosting | (same machine) | Gitea (:30529), Gitea Actions |
