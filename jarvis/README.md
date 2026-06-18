# Jarvis Assistant (ESP32 + Raspberry Pi + Ollama)

Local AI voice assistant stack. No cloud. No GPU required (yet).

## Architecture

```
ESP32-C3 (audio edge)
  INMP441 mic -> I2S capture
  button press -> record PCM
  POST /voice -> Raspberry Pi API
  receive WAV <- Raspberry Pi API
  MAX98357A amp -> speaker plays reply

Raspberry Pi (Docker, port 8000)
  POST /voice
  1. faster-whisper large-v3 (STT, CPU int8)
  2. httpx -> OLLAMA_HOST_IP:11434/api/chat
  3. Kokoro-82M (TTS, ONNX CPU-native)
  4. return WAV bytes to ESP32

Ollama machine (64GB RAM, 6TB)
  gemma3:27b (CPU now)
  llama3.3:70b (GPU later)
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

## Kokoro voice options

| Voice ID | Style |
|----------|-------|
| `bm_george` | British male, authoritative (default) |
| `bm_lewis` | British male, calm |
| `am_adam` | American male, deep |
| `am_michael` | American male, neutral |
| `af_bella` | American female, warm |
| `af_sarah` | American female, neutral |
| `bf_emma` | British female, crisp |

## Wiring (ESP32-C3 breadboard)

### INMP441 mic
| INMP441 | ESP32-C3 |
|---------|----------|
| VDD | 3.3V |
| GND | GND |
| SCK | GPIO4 |
| WS | GPIO5 |
| SD | GPIO6 |
| L/R | GND (left channel) |

### MAX98357A amp
| MAX98357A | ESP32-C3 |
|-----------|----------|
| VIN | 5V |
| GND | GND |
| BCLK | GPIO7 |
| LRC | GPIO8 |
| DIN | GPIO10 |
| OUT+/OUT- | Speaker |

## Quick start

### 1. Pull Ollama model
```bash
ollama pull gemma3:27b
```

### 2. Set up env on Pi
```bash
cd jarvis/backend
cp .env.example .env
# edit .env: set OLLAMA_HOST to your big machine LAN IP
```

### 3. Download Kokoro model files
```bash
# Run once to cache the ONNX model and voices
python3 -c "from kokoro_onnx import Kokoro; Kokoro('kokoro-v0_19.onnx', 'voices.bin')"
```

### 4. Start backend
```bash
make up
make logs
```

### 5. Run mock tests (no hardware needed)
```bash
make test
```

### 6. Smoke test live backend
```bash
make smoke
```

### 7. Flash ESP32
Edit `jarvis/esp32/main.py`:
- `WIFI_SSID` / `WIFI_PASS`
- `BACKEND = "http://YOUR_PI_IP:8000"`

Flash with Thonny or `mpremote cp jarvis/esp32/main.py :main.py`.

## GPU upgrade day (no code changes needed)

Edit `.env` only:
```env
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16
TTS_ENGINE=xtts
XTTS_VOICE_REF=/voices/jarvis_reference.wav
OLLAMA_MODEL=llama3.3:70b
```

Then `make up` and you're done.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Status + model info |
| POST | `/voice` | **Primary**: audio in -> WAV reply |
| POST | `/transcribe` | Debug: audio -> transcript |
| POST | `/chat` | Debug: text -> LLM reply |
| POST | `/speak` | Debug: text -> WAV |
| DELETE | `/history` | Clear conversation history |
