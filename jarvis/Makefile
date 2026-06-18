.PHONY: up-pi down-pi up-server down-server logs-pi logs-server test smoke clean

BIG_MACHINE ?= user@BIG_MACHINE_IP

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
# Inference services (runs on big machine)
# ---------------------------------------------------------------------------

up-server:
	ssh $(BIG_MACHINE) 'cd ~/jarvis && docker compose -f jarvis/services/docker-compose.yml up --build -d'

down-server:
	ssh $(BIG_MACHINE) 'cd ~/jarvis && docker compose -f jarvis/services/docker-compose.yml down'

logs-server:
	ssh $(BIG_MACHINE) 'cd ~/jarvis && docker compose -f jarvis/services/docker-compose.yml logs -f'

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
	curl -sf http://$(BIG_MACHINE_IP):8001/health | python3 -m json.tool
	@echo "--- TTS service health ---"
	curl -sf http://$(BIG_MACHINE_IP):8002/health | python3 -m json.tool
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
