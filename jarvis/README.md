# Jarvis Assistant (ESP32 + Multi-Pi Inference Cluster)

Local AI voice assistant. No cloud. Works across Raspberry Pi nodes.

## Architecture

```
ESP32-C3  (audio edge)
  INMP441 mic -> I2S record
  button press -> POST /voice -> Pi
  receive WAV  <- Pi
  MAX98357A amp -> speaker

Raspberry Pi 4 (4GB)  (API gateway, port 8000)
  Receives audio from ESP32
  -> POST audio   to STT node :8001  (STT)
  -> POST text    to LLM node :11434 (Ollama)
  -> POST reply   to TTS node :8002  (TTS)
  <- Returns WAV to ESP32
  Zero inference load on gateway node

Pi 5 (8GB)  (LLM node)
  :11434  Ollama        gemma4 (quantized variant recommended)

Pi 4 (4GB)  (STT node)
  :8001   STT service   Systran/faster-whisper-small  (int8 CPU)

Pi 4 (4GB)  (TTS node)
  :8002   TTS service   hexgrad/Kokoro-82M  bm_george voice

Pi 4 (4GB) spare / failover node
  Optional hot-standby for STT or TTS, or automation workloads.
```

## Recommended role mapping (your hardware)

| Node | Hardware | Role | Services |
|------|----------|------|----------|
| Node A | Raspberry Pi 5 (8GB) | LLM | Ollama (`gemma4`) on `:11434` |
| Node B | Raspberry Pi 4 (4GB) | Gateway | Jarvis backend on `:8000` |
| Node C | Raspberry Pi 4 (4GB) | STT | STT service on `:8001` |
| Node D | Raspberry Pi 4 (4GB) | TTS / spare failover | TTS service on `:8002` |

Gateway env example for this layout:

```env
OLLAMA_HOST=http://NODE_A_IP:11434
OLLAMA_MODEL=gemma4
STT_HOST=http://NODE_C_IP:8001
TTS_HOST=http://NODE_D_IP:8002
```

## Models

| Role | Model | Node recommendation |
|------|-------|---------------------|
| LLM | `gemma4` (quantized Ollama tag) | Pi 5 (8GB) |
| STT | `Systran/faster-whisper-small` | Pi 4 (4GB) |
| TTS | `hexgrad/Kokoro-82M` | Pi 4 (4GB) |
| Optional STT upgrade | `Systran/faster-whisper-medium` | Pi 5 (8GB) if STT moved there |

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

### 1. LLM node (Pi 5) - pull Ollama model
```bash
ollama pull gemma4
```

### 2. STT node (Pi 4) - start STT service
```bash
cd jarvis/services
cp stt/.env.example stt/.env
docker compose up --build -d stt
```

### 3. TTS node (Pi 4) - start TTS service
```bash
cd jarvis/services
cp tts/.env.example tts/.env
docker compose up --build -d tts
```

### 4. Gateway node (Pi 4) - start gateway
```bash
cd jarvis/backend
cp .env.example .env
# Set OLLAMA_HOST, STT_HOST, and TTS_HOST in .env
docker compose -f ../docker-compose.yml up --build -d
```

### 5. Run mock tests (no hardware needed)
```bash
make test
```

### 6. Smoke test all services
```bash
STT_HOST=x.x.x.x TTS_HOST=x.x.x.x make smoke
```

### 7. Flash ESP32
Edit `jarvis/esp32/main.py`:
```python
WIFI_SSID = "your_ssid"
WIFI_PASS = "your_password"
BACKEND   = "http://PI_LAN_IP:8000"
```
Flash: `mpremote cp jarvis/esp32/main.py :main.py`

## Pi topology deployment helpers

Use Make targets with explicit remote hosts:

```bash
make up-stt STT_MACHINE=user@STT_PI_IP
make up-tts TTS_MACHINE=user@TTS_PI_IP
make up-pi
```

Or bring all service layers up in one command:

```bash
make up-all STT_MACHINE=user@STT_PI_IP TTS_MACHINE=user@TTS_PI_IP
```

## GPU upgrade day

On the upgraded inference node, edit `services/stt/.env` and `services/tts/.env`:

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

Gateway and ESP32 firmware need zero changes.

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

### STT service (port 8001, STT node)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Model + device status |
| POST | `/transcribe` | Audio -> transcript |

### TTS service (port 8002, TTS node)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Engine + voice status |
| POST | `/speak` | Text -> WAV |
