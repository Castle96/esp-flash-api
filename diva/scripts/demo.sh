#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# DIVA — Demo / Smoke Test Script
# ============================================================================
# Prerequisites: All services deployed and running (make up-all).
# This script walks through the full pipeline without requiring ESP32 hardware.
# ============================================================================

GATEWAY="${PI_HOST:-100.85.238.85}:8000"
STT="${STT_HOST:-100.120.207.67}:8001"
TTS="${TTS_HOST:-100.120.207.67}:8002"
WW="${WW_HOST:-100.120.207.67}:8003"
OLLAMA="${OLLAMA_HOST:-100.120.207.67}:11434"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
fail() { echo "[FAIL] $1"; exit 1; }

echo "=========================================="
echo "  DIVA Demo — $(date)"
echo "=========================================="

# ---- 1. Gateway health ----
info "Checking gateway health..."
curl -sf "http://$GATEWAY/health" > /dev/null && pass "Gateway is up" || fail "Gateway unreachable"

# ---- 2. Upstream service health ----
info "Probing upstream services..."
curl -sf "http://$STT/health"   > /dev/null && pass "STT health"   || fail "STT unreachable"
curl -sf "http://$TTS/health"   > /dev/null && pass "TTS health"   || fail "TTS unreachable"
curl -sf "http://$WW/health"    > /dev/null && pass "WakeWord health" || fail "WakeWord unreachable"
curl -sf "http://$OLLAMA/api/tags" > /dev/null && pass "Ollama reachable" || fail "Ollama unreachable"

# ---- 3. Dashboard ----
info "Fetching dashboard..."
curl -sf "http://$GATEWAY/" | grep -q "DIVA" && pass "Dashboard serves HTML" || fail "Dashboard not serving"

# ---- 4. Chat ----
info "Testing chat (text → LLM)..."
REPLY=$(curl -sf -X POST "http://$GATEWAY/chat" \
  -H "Content-Type: application/json" \
  -d '{"text": "are you online"}')
echo "$REPLY" | python3 -m json.tool | grep -q "reply" && pass "Chat returns reply" || fail "Chat failed"
SESSION_ID=$(echo "$REPLY" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")

# ---- 5. Speak (TTS) ----
info "Testing TTS (text → WAV)..."
curl -sf -X POST "http://$GATEWAY/speak" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello from DIVA"}' \
  -o /tmp/diva_demo_speak.wav
python3 -c "
import wave; w = wave.open('/tmp/diva_demo_speak.wav')
assert w.getnframes() > 0, 'empty WAV'
w.close()
" && pass "TTS produces valid WAV" || fail "TTS WAV invalid"
rm -f /tmp/diva_demo_speak.wav

# ---- 6. Transcribe ----
info "Testing STT (generate a silent WAV, transcribe it)..."
python3 -c "
import wave, struct
with wave.open('/tmp/diva_demo_silent.wav', 'w') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(struct.pack('<' + 'h' * 16000, *([0] * 16000)))
" 2>/dev/null
RESULT=$(curl -sf -X POST "http://$GATEWAY/transcribe" \
  -H "Content-Type: audio/wav" \
  --data-binary @/tmp/diva_demo_silent.wav)
echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'text' in d and 'language' in d" \
  && pass "STT returns text and language" || fail "STT failed"
rm -f /tmp/diva_demo_silent.wav

# ---- 7. Voice pipeline (mocked, no wake word) ----
info "Testing full /voice pipeline..."
python3 -c "
import wave, struct
with wave.open('/tmp/diva_demo_voice.wav', 'w') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(struct.pack('<' + 'h' * 16000, *([0] * 16000)))
" 2>/dev/null
curl -sf -X POST "http://$GATEWAY/voice?skip_wake=true" \
  -H "Content-Type: audio/wav" \
  --data-binary @/tmp/diva_demo_voice.wav \
  -o /tmp/diva_demo_reply.wav
python3 -c "
import wave; w = wave.open('/tmp/diva_demo_reply.wav')
assert w.getnframes() > 0, 'empty voice reply'
w.close()
" && pass "Voice pipeline returns valid WAV" || fail "Voice pipeline failed"
rm -f /tmp/diva_demo_voice.wav /tmp/diva_demo_reply.wav

# ---- 8. Device heartbeat ----
info "Registering a test device..."
curl -sf -X POST "http://$GATEWAY/devices/heartbeat" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "demo-device", "ip": "192.168.1.99"}' \
  | python3 -c "import sys,json; assert json.load(sys.stdin).get('status') == 'registered'" \
  && pass "Device registered" || fail "Device registration failed"

# ---- 9. Device list ----
info "Listing devices..."
curl -sf "http://$GATEWAY/devices" | python3 -c "
import sys,json; devices = json.load(sys.stdin)
assert any(d['id'] == 'demo-device' for d in devices), 'demo device not found'
" && pass "Device list includes demo device" || fail "Devices endpoint failed"

# ---- 10. Flash job workflow ----
info "Creating a flash job..."
JOB_ID=$(curl -sf -X POST "http://$GATEWAY/flash/jobs" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "demo-device", "source": "demo", "firmware_code": "print(\"hello\")"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
[[ -n "$JOB_ID" ]] && pass "Flash job created (#$JOB_ID)" || fail "Flash job creation failed"

info "Approving flash job..."
curl -sf -X POST "http://$GATEWAY/flash/jobs/$JOB_ID/approve" \
  -H "Content-Type: application/json" \
  | python3 -c "import sys,json; assert json.load(sys.stdin).get('status') in ('approved', 'dispatched')" \
  && pass "Flash job approved and dispatched" || fail "Flash job approval failed"

# ---- 11. Gitea status ----
info "Checking Gitea integration..."
curl -sf "http://$GATEWAY/gitea/status" > /dev/null 2>&1 \
  && pass "Gitea integration reachable" || info "Gitea not configured (SKIP)"

# ---- 12. Weather ----
info "Checking weather proxy..."
curl -sf "http://$GATEWAY/weather" | python3 -c "
import sys,json; d=json.load(sys.stdin)
assert isinstance(d, list) and len(d) > 0, 'weather data empty'
" && pass "Weather proxy works" || fail "Weather proxy failed"

echo ""
echo "=========================================="
echo "  All checks passed. DIVA is operational."
echo "=========================================="
echo ""
echo "  Dashboard: http://$GATEWAY"
echo "  API docs:  http://$GATEWAY/docs"
echo "  Chat API:  curl http://$GATEWAY/chat -d '{\"text\":\"hi\"}'"
echo "=========================================="
