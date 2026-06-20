.PHONY: \
	up-pi down-pi logs-pi \
	up-stt down-stt logs-stt \
	up-tts down-tts logs-tts \
	up-wakeword down-wakeword logs-wakeword \
	up-voice down-voice logs-voice \
	up-all down-all logs-all \
	up-server down-server logs-server \
	test smoke clean

# ---------------------------------------------------------------------------
# Remote hosts
# ---------------------------------------------------------------------------
# stargame: x86_64, 62GB RAM, runs Ollama + STT/TTS/WakeWord microservices
STARGAME ?= 100.120.207.67
# arceus: aarch64, 8GB Pi 5, runs the DIVA Pi gateway
ARCEUS ?= 100.85.238.85

LLM_MACHINE ?= kyle@$(STARGAME)
STT_MACHINE ?= kyle@$(STARGAME)
TTS_MACHINE ?= kyle@$(STARGAME)
WAKEWORD_MACHINE ?= kyle@$(STARGAME)
PI_GATEWAY ?= kyle@$(ARCEUS)

# ---------------------------------------------------------------------------
# Pi gateway (runs on Raspberry Pi)
# ---------------------------------------------------------------------------

PI_DIR ?= /home/kyle/diva

up-pi:
	rsync -avz --exclude __pycache__ --exclude '.git' --exclude venv \
		*.yml backend scripts $(PI_GATEWAY):$(PI_DIR)/
	ssh $(PI_GATEWAY) 'cd $(PI_DIR) && docker compose up --build -d'

down-pi:
	ssh $(PI_GATEWAY) 'cd $(PI_DIR) && docker compose down'

logs-pi:
	ssh $(PI_GATEWAY) 'cd $(PI_DIR) && docker compose logs -f'

restart-pi:
	ssh $(PI_GATEWAY) 'cd $(PI_DIR) && docker compose restart -d'

# ---------------------------------------------------------------------------
# Voice inference services (can run on separate hosts)
# ---------------------------------------------------------------------------

up-stt:
	ssh $(STT_MACHINE) 'cd ~/diva/services && docker compose up --build -d stt'

down-stt:
	ssh $(STT_MACHINE) 'cd ~/diva/services && docker compose down stt'

logs-stt:
	ssh $(STT_MACHINE) 'cd ~/diva/services && docker compose logs -f stt'

up-tts:
	ssh $(TTS_MACHINE) 'cd ~/diva/services && docker compose up --build -d tts'

down-tts:
	ssh $(TTS_MACHINE) 'cd ~/diva/services && docker compose down tts'

logs-tts:
	ssh $(TTS_MACHINE) 'cd ~/diva/services && docker compose logs -f tts'

up-wakeword:
	ssh $(WAKEWORD_MACHINE) 'cd ~/diva/services && docker compose up --build -d wakeword'

down-wakeword:
	ssh $(WAKEWORD_MACHINE) 'cd ~/diva/services && docker compose down wakeword'

logs-wakeword:
	ssh $(WAKEWORD_MACHINE) 'cd ~/diva/services && docker compose logs -f wakeword'

up-voice: up-stt up-tts up-wakeword

down-voice:
	-ssh $(STT_MACHINE) 'cd ~/diva/services && docker compose down stt'
	-ssh $(TTS_MACHINE) 'cd ~/diva/services && docker compose down tts'
	-ssh $(WAKEWORD_MACHINE) 'cd ~/diva/services && docker compose down wakeword'

logs-voice:
	@echo "--- STT logs ($(STT_MACHINE)) ---"
	-ssh $(STT_MACHINE) 'cd ~/diva/services && docker compose logs --tail=40 stt'
	@echo "--- TTS logs ($(TTS_MACHINE)) ---"
	-ssh $(TTS_MACHINE) 'cd ~/diva/services && docker compose logs --tail=40 tts'
	@echo "--- WakeWord logs ($(WAKEWORD_MACHINE)) ---"
	-ssh $(WAKEWORD_MACHINE) 'cd ~/diva/services && docker compose logs --tail=40 wakeword'

up-all: up-pi up-voice

down-all: down-pi down-voice

logs-all: logs-pi logs-voice

# Backward-compatible alias (legacy single "server" target now means voice stack)
up-server: up-voice

down-server: down-voice

logs-server: logs-voice

# ---------------------------------------------------------------------------
# Tests (no hardware required - mocked)
# ---------------------------------------------------------------------------

test:
	cd backend && python3 -m pytest ../tests -v

# ---------------------------------------------------------------------------
# Microphone round-trip test (run on a machine with a mic)
# ---------------------------------------------------------------------------

DURATION ?= 5

mic-test:
	@echo "Recording $(DURATION)s from mic -> /voice -> playback"
	python3 scripts/mic_test.py --duration $(DURATION) $(ARGS)

mic-test-arecord:
	@echo "Recording $(DURATION)s via arecord -> /voice -> playback"
	python3 scripts/mic_test.py --duration $(DURATION) --backend arecord $(ARGS)

mic-test-wake:
	python3 scripts/mic_test.py --duration $(DURATION) --no-wake $(ARGS)

# ---------------------------------------------------------------------------
# Smoke tests (all services must be running)
# ---------------------------------------------------------------------------

PI_HOST ?= 100.85.238.85
STT_HOST ?= 100.120.207.67
TTS_HOST ?= 100.120.207.67
WW_HOST  ?= 100.120.207.67

smoke:
	@echo "--- Pi gateway health (arceus) ---"
	curl -sf http://$(PI_HOST):8000/health | python3 -m json.tool
	@echo "--- STT service health (stargame) ---"
	curl -sf http://$(STT_HOST):8001/health | python3 -m json.tool
	@echo "--- TTS service health (stargame) ---"
	curl -sf http://$(TTS_HOST):8002/health | python3 -m json.tool
	@echo "--- WakeWord service health (stargame) ---"
	curl -sf http://$(WW_HOST):8003/health | python3 -m json.tool
	@echo "--- Full chat round-trip ---"
	curl -sf -X POST http://$(PI_HOST):8000/chat \
		-H "Content-Type: application/json" \
		-d '{"text": "are you online"}' | python3 -m json.tool
	@echo "All smoke tests passed."

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
