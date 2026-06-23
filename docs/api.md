# API Reference

Base URL: `http://<gateway>:8000`

---

## Health

```bash
curl http://localhost:8000/health
# {"status":"ok","model":"gemma4","whisper":"faster-whisper-large-v3","tts":"kokoro"}

curl http://localhost:8000/health?deps=true
# Includes upstream service health checks
```

---

## Voice Pipeline

### POST /voice — Full voice round-trip
```
Content-Type: audio/wav
Body: PCM audio (16kHz, 16-bit, mono)
```
Returns WAV audio of the spoken reply.

### POST /transcribe — Speech to text
```
Content-Type: audio/wav
Body: PCM audio (16kHz, 16-bit, mono)
```
```json
{"text": "turn on the lab lights", "language": "en"}
```

### POST /chat — Text conversation
```json
{"text": "are you online", "session_id": "optional-uuid"}
```
```json
{"reply": "Online and ready.", "session_id": "uuid"}
```

### POST /speak — Text to speech
```json
{"text": "Hello from DIVA"}
```
Returns WAV audio bytes.

---

## Devices

### POST /devices/heartbeat — Register/update device
```json
{"device_id": "esp-c3-lab-01", "ip": "192.168.1.42"}
```
```json
{"status": "registered"}
```

### GET /devices — List all devices
Returns array of `{id, name, ip, first_seen, last_seen, gitea_repo, online}`

### GET /devices/{id}/config — Device configuration
Returns device-specific config JSON.

---

## Flash (OTA Firmware)

### POST /flash/jobs — Create flash job
```json
{
  "device_id": "esp-c3-lab-01",
  "source": "manual",
  "firmware_code": "import machine..."
}
```
```json
{"id": 42, "status": "pending_review", "device_id": "esp-c3-lab-01"}
```

### GET /flash/jobs — List flash jobs
Returns all jobs with their status.

### POST /flash/jobs/{id}/approve — Approve & dispatch
Triggers OTA push to the device.

### POST /flash/jobs/{id}/reject — Reject
```json
{"status": "rejected"}
```

### POST /flash/jobs/{id}/cancel — Cancel
Only cancellable while pending.

---

## Fleet

### POST /fleet/action — Bulk action
```json
{"action": "flash_approve", "device_ids": ["esp-01", "esp-02"]}
```
```json
{"results": {"esp-01": "approved", "esp-02": "approved"}}
```

---

## Gitea Integration

### GET /gitea/status — Connectivity check
### GET /gitea/repos — List firmware repos
### POST /gitea/webhook — Incoming webhook (from Gitea)
### POST /gitea/webhook/setup — Auto-install webhooks on all repos
### GET /gitea/actions/{repo} — Build status for a repo

---

## Wake Word

### GET /wakeword/status — Wake word service health
### GET /wakeword/custom — List custom wake words
### POST /wakeword/detect — Detect built-in wake words
```
Content-Type: audio/wav
Body: PCM audio
```
```json
{"wake_words": [{"name": "alexa", "confidence": 0.87}]}
```
### POST /wakeword/train/{name} — Train custom wake word
```
Content-Type: multipart/form-data
Field: audio (WAV file, min 0.5s)
```
### DELETE /wakeword/custom/{name} — Delete custom wake word

---

## Logs

### POST /logs/{device_id} — Push device log
```json
{"message": "WiFi connected", "level": "info"}
```

### GET /logs/{device_id} — Pull device logs
### GET /logs/{device_id}/stream — SSE log streaming

---

## Conversation

### GET /conversation — Conversation history
```json
[{"role": "user", "content": "are you online", "ts": "..."}, ...]
```
### DELETE /history — Clear all conversations

---

## Authentication

### POST /login — Get JWT token
```json
{"username": "admin", "password": "..."}
```
```json
{"token": "eyJ...", "expires": 604800}
```

### GET /auth/keys — List API keys (admin only)
### POST /auth/keys — Create API key
```json
{"name": "deploy-bot", "role": "admin"}
```
```json
{"key": "diva_a1b2c3..."}
```
### DELETE /auth/keys/{id} — Revoke API key

---

## Weather

### GET /weather — 4-day forecast (Open-Meteo proxy)
```json
[{"date": "2026-06-22", "temp_max": 28, "temp_min": 18, "code": 1}, ...]
```

---

## Metrics

### GET /metrics — Prometheus metrics
Key metrics:
- `diva_requests_total{method,path,status}` — Request count
- `diva_voice_total` — Voice pipeline invocations
- `diva_latency_seconds{stage}` — Per-stage latency histogram

---

## Events (SSE)

### GET /events — Server-Sent Events stream
```
data: {"type": "stt", "text": "turn on the lights", "ts": "..."}

data: {"type": "llm", "text": "Understood.", "ts": "..."}
```
