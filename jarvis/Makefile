.PHONY: up down build logs test smoke clean

# ---- Docker ----------------------------------------------------------------

up:
	docker compose -f jarvis/docker-compose.yml up --build -d

down:
	docker compose -f jarvis/docker-compose.yml down

build:
	docker compose -f jarvis/docker-compose.yml build

logs:
	docker compose -f jarvis/docker-compose.yml logs -f

# ---- Tests (no hardware required) -----------------------------------------

test:
	cd jarvis/backend && pip install -q pytest httpx && pytest ../tests -v

# ---- Smoke tests (backend must be running on localhost:8000) ---------------

smoke:
	@echo "--- health ---"
	curl -sf http://localhost:8000/health | python3 -m json.tool
	@echo "--- chat ---"
	curl -sf -X POST http://localhost:8000/chat \
		-H "Content-Type: application/json" \
		-d '{"text": "are you online"}' | python3 -m json.tool
	@echo "--- speak ---"
	curl -sf -X POST http://localhost:8000/speak \
		-H "Content-Type: application/json" \
		-d '{"text": "Understood. I am online."}' \
		-o /tmp/jarvis_smoke.wav
	@file /tmp/jarvis_smoke.wav
	@echo "Smoke tests passed."

# ---- Clean -----------------------------------------------------------------

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
