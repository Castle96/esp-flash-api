.PHONY: \
	up-pi down-pi logs-pi \
	up-stt down-stt logs-stt \
	up-tts down-tts logs-tts \
	up-voice down-voice logs-voice \
	up-all down-all logs-all \
	up-server down-server logs-server \
	test smoke clean

# ---------------------------------------------------------------------------
# Remote hosts
# ---------------------------------------------------------------------------
LLM_MACHINE ?= user@PI5_8GB_IP
STT_MACHINE ?= user@PI4_STT_IP
TTS_MACHINE ?= user@PI4_TTS_IP

# ---------------------------------------------------------------------------
# Pi gateway (runs on Raspberry Pi)
# ---------------------------------------------------------------------------

up-pi:
	docker compose -f jarvis/docker-compose.yml up --build -d

down-pi:
	docker compose -f jarvis/docker-compose.yml down

logs-pi:
	docker compose -f jarvis/docker-compose.yml logs -f

# ---------------------------------------------------------------------------
# Voice inference services (can run on separate hosts)
# ---------------------------------------------------------------------------

up-stt:
	ssh $(STT_MACHINE) 'cd ~/jarvis/services && docker compose up --build -d stt'

down-stt:
	ssh $(STT_MACHINE) 'cd ~/jarvis/services && docker compose down stt'

logs-stt:
	ssh $(STT_MACHINE) 'cd ~/jarvis/services && docker compose logs -f stt'

up-tts:
	ssh $(TTS_MACHINE) 'cd ~/jarvis/services && docker compose up --build -d tts'

down-tts:
	ssh $(TTS_MACHINE) 'cd ~/jarvis/services && docker compose down tts'

logs-tts:
	ssh $(TTS_MACHINE) 'cd ~/jarvis/services && docker compose logs -f tts'

up-voice: up-stt up-tts

down-voice:
	-ssh $(STT_MACHINE) 'cd ~/jarvis/services && docker compose down stt'
	-ssh $(TTS_MACHINE) 'cd ~/jarvis/services && docker compose down tts'

logs-voice:
	@echo "--- STT logs ($(STT_MACHINE)) ---"
	-ssh $(STT_MACHINE) 'cd ~/jarvis/services && docker compose logs --tail=40 stt'
	@echo "--- TTS logs ($(TTS_MACHINE)) ---"
	-ssh $(TTS_MACHINE) 'cd ~/jarvis/services && docker compose logs --tail=40 tts'

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
	cd jarvis/backend && pip install -q pytest httpx && pytest ../tests -v

# ---------------------------------------------------------------------------
# Smoke tests (all services must be running)
# ---------------------------------------------------------------------------

smoke:
	@echo "--- Pi gateway health ---"
	curl -sf http://localhost:8000/health | python3 -m json.tool
	@echo "--- STT service health ---"
	curl -sf http://$(STT_HOST):8001/health | python3 -m json.tool
	@echo "--- TTS service health ---"
	curl -sf http://$(TTS_HOST):8002/health | python3 -m json.tool
	@echo "--- Full chat round-trip ---"
	curl -sf -X POST http://localhost:8000/chat \
		-H "Content-Type: application/json" \
		-d '{"text": "are you online"}' | python3 -m json.tool
	@echo "All smoke tests passed."

# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
