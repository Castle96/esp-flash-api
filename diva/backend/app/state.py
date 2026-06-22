import uuid
from collections import deque, OrderedDict
from dataclasses import dataclass, field
from time import time

from . import db

FLASH_PENDING = db.FLASH_PENDING
FLASH_APPROVED = db.FLASH_APPROVED
FLASH_REJECTED = db.FLASH_REJECTED
FLASH_RUNNING = db.FLASH_RUNNING
FLASH_DONE = db.FLASH_DONE
FLASH_FAILED = db.FLASH_FAILED

event_log: deque = deque(maxlen=100)


class LazyDict:
    def __init__(self, loader):
        self._loader = loader
        self._cache = None
        self._cache_ts = 0.0
        self._ttl = 2.0

    def _load(self):
        now = time()
        if self._cache is None or (now - self._cache_ts) > self._ttl:
            self._cache = OrderedDict()
            for item in self._loader():
                self._cache[item["id"]] = item
            self._cache_ts = now
        return self._cache

    def get(self, key, default=None):
        return self._load().get(key, default)

    def values(self):
        return self._load().values()

    def items(self):
        return self._load().items()

    def keys(self):
        return self._load().keys()

    def __len__(self):
        return len(self._load())

    def __contains__(self, key):
        return key in self._load()


@dataclass
class AssistantState:
    last_event: str = ""
    last_event_ts: float = 0.0
    session_id: str = "default"
    history: list[dict] = field(default_factory=list)

    @property
    def devices(self):
        return LazyDict(db.get_all_devices)

    @property
    def flash_jobs(self):
        def _loader():
            return db.get_flash_jobs()
        return LazyDict(_loader)

    @property
    def conversation(self):
        return [dict(r) for r in db.get_conversation()]

    @property
    def gitea_build_status(self):
        return {}


state = AssistantState()


def mark_event(event: str):
    state.last_event = event
    state.last_event_ts = time()
    event_log.append({"event": event, "ts": state.last_event_ts})
    db.mark_event(event)


def register_device(device_id: str, ip: str, name: str = "ESP32-C3", gitea_repo: str | None = None) -> dict:
    return db.register_device(device_id, ip, name, gitea_repo)


def add_device_log(device_id: str, message: str, level: str = "info"):
    db.add_device_log(device_id, message, level)


def get_device_logs(device_id: str, limit: int = 50) -> list[dict]:
    return db.get_device_logs(device_id, limit)


def add_conversation_entry(role: str, content: str):
    db.add_conversation_entry(role, content)


def create_flash_job(
    device_id: str,
    device_name: str,
    source: str,
    firmware_binary: str | None = None,
    firmware_code: str | None = None,
    description: str = "",
) -> dict:
    return db.create_flash_job(device_id, device_name, source, firmware_binary, firmware_code, description)


def update_flash_job(job_id: str, status: str, error: str | None = None) -> dict | None:
    return db.update_flash_job(job_id, status, error)


def find_device_by_gitea_repo(repo_full_name: str) -> dict | None:
    return db.find_device_by_gitea_repo(repo_full_name)


def update_gitea_build_status(repo: str, status: str, sha: str = "", run_url: str = ""):
    db.update_gitea_build_status(repo, status, sha, run_url)


def get_pending_reminder():
    return db.get_pending_reminder()
