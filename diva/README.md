# DIVA — Device Integrated Voice Agent

Local AI voice assistant + ESP32 fleet management. No cloud.

## Architecture

```
ESP32-C3  (audio edge)
  button press -> POST /voice -> Pi gateway -> STT -> LLM -> TTS -> WAV reply

Pi 5 (arceus, 8GB)          — DIVA gateway :8000
x86_64 (stargame, 62GB)     — STT :8001, TTS :8002, WakeWord :8003, Ollama :11434
```

## Quick start

```bash
make test                          # run mock tests
make up-pi                         # deploy gateway to arceus
make up-voice                      # deploy services to stargame
make smoke                         # smoke test all services
```

## Microphone test

```bash
make mic-test-arecord              # 5s recording -> /voice -> playback
make mic-test-arecord ARGS="--no-wake"
make mic-test-arecord ARGS="--transcribe-only"
```

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Gateway status |
| POST | `/voice` | Audio in -> WAV reply |
| POST | `/transcribe` | Audio -> text |
| POST | `/chat` | Text -> LLM reply |
| POST | `/speak` | Text -> WAV |
| POST | `/devices/heartbeat` | Device registration |
| GET | `/devices` | Device list |
| POST | `/flash/jobs` | Create flash job |
| POST | `/gitea/webhook/setup` | Install Gitea webhooks |
| GET | `/gitea/actions/{repo}` | Build status |
| POST | `/wakeword/train/{name}` | Train custom wake word |
