# Jarvis Assistant (ESP32 + Ollama)

Local AI voice assistant stack for fast weekend testing.

## What this includes

- ESP32 client (`esp32/main.py`) for:
  - I2S microphone capture (INMP441)
  - backend chat request
  - TTS fetch + playback via I2S amp (MAX98357A)
- FastAPI backend (`backend/app`) for:
  - `/transcribe` (faster-whisper)
  - `/chat` (Ollama)
  - `/speak` (Piper)
  - `/health`
- Dockerized backend with auto-restart via compose
- Tuned Jarvis system prompt in `.env.example`

> Note: Full wake-word support requires additional tuning and host audio device access. This MVP is push-to-talk so you can test quickly this weekend.

## Recommended wiring (ESP32-C3 breadboard test)

### INMP441 -> ESP32-C3

- VDD -> 3.3V
- GND -> GND
- SCK -> GPIO4
- WS -> GPIO5
- SD -> GPIO6
- L/R -> GND (left)

### MAX98357A -> ESP32-C3

- VIN -> 5V (or 3.3V)
- GND -> GND
- BCLK -> GPIO7
- LRC -> GPIO8
- DIN -> GPIO10
- Speaker -> MAX98357A outputs

## Quick start (host machine)

1. Install Ollama and pull model:

```bash
ollama pull gemma4:e2b
```

2. Copy env file and edit values:

```bash
cd jarvis/backend
cp .env.example .env
# set PIPER_VOICE to your .onnx voice path
```

3. Start backend container:

```bash
cd ../..
docker compose -f jarvis/docker-compose.yml up --build -d
```

4. Flash/upload `jarvis/esp32/main.py` to your ESP32 MicroPython device and update:

- `WIFI_SSID`
- `WIFI_PASS`
- `BACKEND`

5. Press button to record -> transcribe -> chat -> speak.

## Endpoints

- `GET /health`
- `POST /transcribe` (multipart file field: `file`)
- `POST /chat` (`{"text":"..."}`)
- `POST /speak` (`{"text":"..."}`)

## Future improvements

- Add wake word (Porcupine or openwakeword)
- Streamed audio chunks
- Conversation memory persistence
- Skill router / tool calls
