# Jarvis Assistant (ESP32 + Raspberry Pi + Ollama)

Local AI voice assistant. No cloud. No GPU required yet.

## Architecture

```
ESP32-C3  (audio edge)
  INMP441 mic -> I2S record
  button press -> POST /voice -> Pi
  receive WAV  <- Pi
  MAX98357A amp -> speaker

Raspberry Pi  (API gateway, port 8000)
  Receives audio from ESP32
  -> POST audio   to big machine :8001  (STT)
  -> POST text    to big machine :11434 (LLM via Ollama)
  -> POST reply   to big machine :8002  (TTS)
  <- Returns WAV to ESP32
  Zero inference load on Pi

Big machine  (64GB RAM, 6TB, all inference)
  :11434  Ollama        gemma3:27b
  :8001   STT service   Systran/faster-whisper-large-v3  (int8 CPU)
  :8002   TTS service   hexgrad/Kokoro-82M  bm_george voice
```

## Models

| Role | Model | Notes |
|------|-------|-------|
| LLM (now) | `gemma3:27b` | ~18GB RAM, excellent quality |
| LLM (GPU later) | `llama3.3:70b` | ~42GB RAM, best in class |
| STT (now) | `Systran/faster-whisper-large-v3` | int8 CPU, ~6GB RAM |
| STT (GPU later) | same model | float16 CUDA, <1s latency |
| TTS (now) | `hexgrad/Kokoro-82M` | ONNX CPU, `bm_george` voice |
| TTS (GPU later) | `coqui/XTTS-v2` | voice cloning, ~250ms on CUDA |

## Kokoro voices

| Voice ID | Style |
|----------|-------|
| `bm_george` | British male, authoritative (default) |
| `bm_lewis` | British male, calm |
| `am_adam` | American male, deep |
| `am_michael` | American male, neutral |
| `af_bella` | American female, warm |
| `af_sarah` | American female, neutral |
| `bf_emma` | British female, crisp |

## ESP32-C3 wiring

### INMP441 mic
| Pin | GPIO |
|-----|------|
| SCK | 4 |
| WS | 5 |
| SD | 6 |
| VDD | 3.3V |
| GND | GND |
| L/R | GND |

### MAX98357A amp
| Pin | GPIO |
|-----|------|
| BCLK | 7 |
| LRC | 8 |
| DIN | 10 |
| VIN | 5V |
| GND | GND |

## Quick start

### 1. Big machine - pull Ollama model
```bash
ollama pull gemma3:27b
```

### 2. Big machine - start STT and TTS services
```bash
cd jarvis/services
cp stt/.env.example stt/.env
cp tts/.env.example tts/.env
docker compose up --build -d
```

### 3. Pi - start gateway
```bash
cd jarvis/backend
cp .env.example .env
# Set BIG_MACHINE_IP in .env
docker compose -f ../docker-compose.yml up --build -d
```

### 4. Run mock tests (no hardware needed)
```bash
make test
```

### 5. Smoke test all services
```bash
BIG_MACHINE_IP=x.x.x.x make smoke
```

### 6. Flash ESP32
Edit `jarvis/esp32/main.py`:
```python
WIFI_SSID = "your_ssid"
WIFI_PASS = "your_password"
BACKEND   = "http://PI_LAN_IP:8000"
```
Flash: `mpremote cp jarvis/esp32/main.py :main.py`

## GPU upgrade day

On the big machine, edit `services/stt/.env` and `services/tts/.env`:

```env
# stt/.env
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16

# tts/.env
TTS_ENGINE=xtts
XTTS_VOICE_REF=/voices/jarvis_reference.wav
```

Also update `services/tts/requirements.txt` - uncomment `TTS>=0.22.0`.

Then:
```bash
docker compose -f jarvis/services/docker-compose.yml up --build -d
```

Pi gateway and ESP32 firmware need zero changes.

## API reference

### Pi gateway (port 8000)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Gateway status |
| POST | `/voice` | Audio in -> WAV reply (ESP32 primary path) |
| POST | `/transcribe` | Audio -> transcript |
| POST | `/chat` | Text -> LLM reply |
| POST | `/speak` | Text -> WAV |
| DELETE | `/history` | Clear conversation history |

### STT service (port 8001, big machine)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Model + device status |
| POST | `/transcribe` | Audio -> transcript |

### TTS service (port 8002, big machine)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Engine + voice status |
| POST | `/speak` | Text -> WAV |
