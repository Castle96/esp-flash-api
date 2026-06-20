import uuid
from collections import deque, OrderedDict
from dataclasses import dataclass, field
from time import time


FLASH_PENDING  = "pending_review"
FLASH_APPROVED = "approved"
FLASH_REJECTED = "rejected"
FLASH_RUNNING  = "in_progress"
FLASH_DONE     = "completed"
FLASH_FAILED   = "failed"


@dataclass
class AssistantState:
    last_event: str = ""
    last_event_ts: float = 0.0
    session_id: str = "default"
    history: list[dict] = field(default_factory=list)
    devices: dict[str, dict] = field(default_factory=OrderedDict)
    conversation: list[dict] = field(default_factory=list)
    flash_jobs: dict[str, dict] = field(default_factory=OrderedDict)
    device_logs: dict[str, deque] = field(default_factory=OrderedDict)
    gitea_build_status: dict[str, dict] = field(default_factory=dict)


state = AssistantState()

event_log: deque = deque(maxlen=100)

_log_buffer_size = 200


def mark_event(event: str):
    state.last_event = event
    state.last_event_ts = time()
    event_log.append({"event": event, "ts": state.last_event_ts})


def register_device(device_id: str, ip: str, name: str = "ESP32-C3", gitea_repo: str | None = None) -> dict:
    now = time()
    if device_id not in state.devices:
        state.devices[device_id] = {
            "id": device_id,
            "name": name,
            "ip": ip,
            "first_seen": now,
            "gitea_repo": gitea_repo,
        }
    dev = state.devices[device_id]
    dev["last_seen"] = now
    dev["ip"] = ip
    dev["name"] = name
    dev["online"] = True
    if gitea_repo is not None:
        dev["gitea_repo"] = gitea_repo
    elif "gitea_repo" not in dev:
        dev["gitea_repo"] = None
    return dev


def add_device_log(device_id: str, message: str, level: str = "info"):
    if device_id not in state.device_logs:
        state.device_logs[device_id] = deque(maxlen=_log_buffer_size)
    state.device_logs[device_id].append({
        "message": message,
        "level": level,
        "ts": time(),
    })


def get_device_logs(device_id: str, limit: int = 50) -> list[dict]:
    logs = state.device_logs.get(device_id, deque())
    return list(logs)[-limit:]


def add_conversation_entry(role: str, content: str):
    state.conversation.append({
        "role": role,
        "content": content,
        "ts": time(),
    })
    if len(state.conversation) > 100:
        state.conversation = state.conversation[-100:]


def create_flash_job(
    device_id: str,
    device_name: str,
    source: str,
    firmware_binary: str | None = None,
    firmware_code: str | None = None,
    description: str = "",
) -> dict:
    job_id = uuid.uuid4().hex[:12]
    now = time()
    job = {
        "id": job_id,
        "device_id": device_id,
        "device_name": device_name,
        "source": source,
        "status": FLASH_PENDING,
        "firmware_binary": firmware_binary,
        "firmware_code": firmware_code,
        "description": description,
        "created_at": now,
        "updated_at": now,
        "error": None,
    }
    state.flash_jobs[job_id] = job
    mark_event(f"flash:created:{job_id}")
    return job


def update_flash_job(job_id: str, status: str, error: str | None = None) -> dict | None:
    job = state.flash_jobs.get(job_id)
    if not job:
        return None
    job["status"] = status
    job["updated_at"] = time()
    if error:
        job["error"] = error
    return job


def find_device_by_gitea_repo(repo_full_name: str) -> dict | None:
    """Match a Gitea repo (e.g. 'admin/esp32-sensor-node') to a registered device."""
    for dev in state.devices.values():
        if dev.get("gitea_repo") and repo_full_name in dev["gitea_repo"]:
            return dev
    return None


def update_gitea_build_status(repo: str, status: str, sha: str = "", run_url: str = ""):
    state.gitea_build_status[repo] = {
        "status": status,
        "sha": sha[:8],
        "run_url": run_url,
        "ts": time(),
    }
