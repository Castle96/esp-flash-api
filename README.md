# esp-flash-api / DIVA

**Device Integrated Voice Agent** — A local AI voice assistant for ESP32 fleet management. No cloud required.

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11-blue?style=flat-square">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square">
  <img src="https://img.shields.io/badge/tests-10/10-passing-brightgreen?style=flat-square">
  <img src="https://img.shields.io/badge/ESP32-C3-orange?style=flat-square">
  <img src="https://img.shields.io/badge/voice-gemma4-purple?style=flat-square">
</p>

---

## What it does

DIVA lets you control and flash ESP32 devices by voice, through a dashboard, or via Gitea CI/CD webhooks — all running on your own hardware with zero cloud dependencies.

```
"Hey DIVA, flash device-3 with the new firmware from the lab branch"
  └─ STT → LLM generates code → creates flash job → human approves → OTA push
```

## Architecture

```
┌─────────────┐     ┌──────────────────────┐     ┌─────────────────────────────┐
│  ESP32-C3   │────▶│  Pi 5 Gateway        │────▶│  x86_64 Inference Node      │
│  fleet      │     │  :8000               │     │                              │
│  (audio)    │     │  FastAPI + SQLite    │     │  STT (faster-whisper) :8001  │
│             │     │  Dashboard SPA       │     │  TTS (Kokoro-82M)   :8002   │
│  OTA lite   │◀────│  SSE event stream    │     │  WakeWord           :8003   │
└─────────────┘     └──────────────────────┘     │  Ollama (gemma4)   :11434  │
                                                  └─────────────────────────────┘
                                                              │
                                                  ┌───────────┴───────────┐
                                                  │  Gitea :30529         │
                                                  │  Firmware repos       │
                                                  │  CI Actions           │
                                                  └───────────────────────┘
```

See [docs/architecture.md](docs/architecture.md) for full Mermaid diagrams.

## Dashboard

Single-page app with Catppuccin Mocha theme — pipeline visualization, device fleet, flash queue, conversation log, weather, wake word training, and Gitea panel. All real-time via SSE.

![Dashboard](https://img.shields.io/badge/dashboard-SPA-8A2BE2?style=flat-square)

## Quick start

```bash
# 1. Clone
git clone http://100.120.207.67:30529/Castle96/esp-flash-api.git
cd esp-flash-api/diva

# 2. Configure
cp backend/.env.example backend/.env
# Edit backend/.env with your machine IPs

# 3. Run tests (no hardware required)
make test

# 4. Deploy to Pi (arceus)
make up-pi

# 5. Deploy voice services to big machine (stargame)
make up-voice

# 6. Deploy everything
make up-all

# 7. Smoke test
make smoke
```

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Gateway status |
| `POST` | `/voice` | Audio in → WAV reply (full pipeline) |
| `POST` | `/transcribe` | Audio → text |
| `POST` | `/chat` | Text → LLM reply |
| `POST` | `/speak` | Text → WAV |
| `POST` | `/devices/heartbeat` | Device registration |
| `GET` | `/devices` | Device list |
| `POST` | `/flash/jobs` | Create flash job |
| `POST` | `/flash/jobs/{id}/approve` | Approve & dispatch OTA |
| `POST` | `/gitea/webhook/setup` | Install Gitea webhooks |
| `GET` | `/gitea/actions/{repo}` | Build status |
| `POST` | `/wakeword/train/{name}` | Train custom wake word |

Full reference: [docs/api.md](docs/api.md) | Swagger UI at `http://<gateway>:8000/docs`

## Services

| Service | Tech | Port | Runs on |
|---------|------|------|---------|
| **Gateway** | FastAPI + SQLite | 8000 | Pi 5 (arceus) |
| **STT** | faster-whisper-large-v3 | 8001 | x86_64 (stargame) |
| **TTS** | Kokoro-82M (ONNX) | 8002 | x86_64 (stargame) |
| **WakeWord** | openWakeWord | 8003 | x86_64 (stargame) |
| **LLM** | Ollama + gemma4:e4b | 11434 | x86_64 (stargame) |
| **Code Host** | Gitea | 30529 | x86_64 (stargame) |

## Voice Pipeline

```
ESP32 button press
  → PCM audio (16kHz, 16-bit, mono)
  → [optional wake word check]
  → STT (faster-whisper)
  → LLM (gemma4) with tool calling
      └─ list_devices, flash_firmware, set_reminder, get_system_status
  → TTS (Kokoro)
  → WAV reply → ESP32 I2S speaker
```

Tool-calling allows the LLM to interact with the system — listing devices, scheduling reminders, generating firmware, and creating flash jobs that require human approval.

## Key Features

| Feature | Details |
|---------|---------|
| **No cloud** | Everything runs on local hardware (Pi 5 + x86_64) |
| **Voice control** | Push-to-talk from ESP32, or desktop mic test script |
| **OTA flashing** | LLM generates firmware → human approves → OTA push |
| **Fleet management** | Dashboard with device status, logs, SSE streaming |
| **CI/CD integration** | Gitea webhooks auto-create flash jobs on push |
| **Wake word** | Built-in (alexa, hey_jarvis) + custom training via UI |
| **Auth** | JWT sessions + API keys, optional toggle |
| **Prometheus metrics** | Request counts, latencies per pipeline stage |
| **Weather widget** | 4-day forecast from Open-Meteo (no API key needed) |

## Hardware

### ESP32-C3 (full client)
- INMP441 I2S microphone
- MAX98357A I2S speaker + 3W 4Ω speaker
- Push-to-talk button, status LED
- OTA update server on port 8080

### ESP32-C3 (OTA lite)
- Same heartbeat + OTA logic, no audio hardware needed

## Testing

```bash
make test              # 10 mocked tests, no hardware
make smoke             # curls all services (must be running)
make mic-test-arecord  # record 5s → /voice → playback
```

## Project Structure

```
diva/
├── backend/          # FastAPI gateway + dashboard SPA
│   └── app/
│       ├── main.py       # All API routes
│       ├── config.py     # Environment config
│       ├── models.py     # Pydantic schemas
│       ├── db.py         # SQLite layer (10 tables)
│       ├── auth.py       # JWT + API key auth
│       ├── llm.py        # Ollama HTTP client
│       ├── speech.py     # STT HTTP client
│       ├── tts.py        # TTS HTTP client
│       ├── tools.py      # LLM function-calling tools
│       ├── state.py      # In-memory state + DB cache
│       └── static/
│           └── index.html # Dashboard (2085 lines, SPA)
├── services/         # STT, TTS, WakeWord microservices
├── esp32/            # MicroPython firmware
├── scripts/          # Desktop mic test
├── tests/            # pytest suite (all mocked)
├── Makefile          # Deploy, test, smoke
└── docker-compose.yml
```

## License

MIT
