# DIVA — Project Context

## Remote Machines
| Host | Tailnet IP | LAN IP | Role |
|------|-----------|--------|------|
| arceus | `100.85.238.85` | `192.168.5.65` | Pi 5 (8GB) — DIVA gateway (port 8000) |
| stargame | `100.120.207.67` | `192.168.5.233` | x86_64 (62GB) — STT :8001, TTS :8002, WakeWord :8003, Ollama :11434, Gitea :30529 |

## SSH Credentials
- User: `kyle`, Password: `1023` on all machines
- stargame: use `sshpass -p 1023` since key auth isn't set up

## Gitea
- URL: `http://100.120.207.67:30529`
- Admin: `admin` / `admin123!`
- Repo: `Castle96/esp-flash-api` (clone: `http://100.120.207.67:30529/Castle96/esp-flash-api.git`)

## Services
| Service | Port | Runs on | Deploy path |
|---------|------|---------|-------------|
| DIVA backend | 8000 | arceus | `~/diva/` (Docker Compose) |
| STT | 8001 | stargame | `~/diva/services/` (Docker Compose) |
| TTS | 8002 | stargame | `~/diva/services/` (Docker Compose) |
| WakeWord | 8003 | stargame | `~/diva/services/` (Docker Compose) |
| Ollama | 11434 | stargame | Native (systemd), model `gemma4:e4b` |

## Makefile (in `diva/`)
```bash
make test                # run unit tests (no hardware)
make up-pi               # deploy backend to arceus
make up-voice            # deploy STT/TTS/WakeWord to stargame
make up-all              # deploy everything
make smoke               # smoke test all services
make mic-test-arecord    # mic → wake → STT → LLM → TTS → playback
```

## Wake Word
- Built-in pretrained models: `alexa`, `hey_jarvis` (from openWakeWord library)
- Custom words can be trained via dashboard UI at `/wakeword/train/{name}`
- Config in `~/diva/services/wakeword/.env`

## Dashboard
- URL: `http://100.85.238.85:8000`
- Catppuccin Mocha dark theme
- Features: device fleet, flash queue, Gitea panel, wake word training, voice conversation log, weather

## Tests
- All 10 tests pass: `cd diva/backend && python3 -m pytest ../tests -v`
- Tests mock STT/LLM/TTS/wakeword — no hardware required
- `conftest.py` uses `monkeypatch.setattr` on main_mod

## Key Config
- `.env` files are gitignored; use `.env.example` as template
- Backend `.env` at `diva/backend/.env` — has actual IPs and credentials
- Ollama model: `gemma4:e4b` on stargame
- Wake word enabled (`WAKEWORD_ENABLED=true`)
