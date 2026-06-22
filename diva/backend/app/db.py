import sqlite3
import threading
import uuid
from collections import deque
from pathlib import Path
from time import time

_DB_PATH = Path(__file__).parent.parent / "diva.db"
_local = threading.local()
_init_lock = threading.Lock()
_initialized = False

FLASH_PENDING = "pending_review"
FLASH_APPROVED = "approved"
FLASH_REJECTED = "rejected"
FLASH_RUNNING = "in_progress"
FLASH_DONE = "completed"
FLASH_FAILED = "failed"


def _ensure_init():
    if not _initialized:
        init_db()


def _get_conn() -> sqlite3.Connection:
    _ensure_init()
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def init_db():
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT 'ESP32-C3',
                ip TEXT NOT NULL,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL,
                gitea_repo TEXT
            );

            CREATE TABLE IF NOT EXISTS flash_jobs (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                device_name TEXT NOT NULL,
                source TEXT NOT NULL,
                firmware_binary TEXT,
                firmware_code TEXT,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending_review',
                error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL DEFAULT 'default',
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS device_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                message TEXT NOT NULL,
                level TEXT NOT NULL DEFAULT 'info',
                ts REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                trigger_at REAL,
                done INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS gitea_builds (
                repo TEXT NOT NULL PRIMARY KEY,
                status TEXT NOT NULL,
                sha TEXT DEFAULT '',
                run_url TEXT DEFAULT '',
                ts REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                created_at REAL NOT NULL,
                last_used_at REAL
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                ts REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_conversation_session ON conversation(session_id, ts);
            CREATE INDEX IF NOT EXISTS idx_device_logs_device ON device_logs(device_id, ts);
            CREATE INDEX IF NOT EXISTS idx_flash_jobs_device ON flash_jobs(device_id);
            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
        """)
        conn.commit()
        _initialized = True


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

_event_buffer: deque = deque(maxlen=100)


def mark_event(event: str):
    now = time()
    _event_buffer.append({"event": event, "ts": now})
    try:
        conn = _get_conn()
        conn.execute("INSERT INTO events (event, ts) VALUES (?, ?)", (event, now))
        conn.commit()
    except Exception:
        pass


def get_recent_events(limit: int = 100) -> list[dict]:
    return list(_event_buffer)


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------

def register_device(device_id: str, ip: str, name: str = "ESP32-C3", gitea_repo: str | None = None) -> dict:
    now = time()
    conn = _get_conn()
    existing = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE devices SET ip = ?, name = ?, last_seen = ?, gitea_repo = COALESCE(?, gitea_repo) WHERE id = ?",
            (ip, name, now, gitea_repo, device_id),
        )
    else:
        conn.execute(
            "INSERT INTO devices (id, name, ip, first_seen, last_seen, gitea_repo) VALUES (?, ?, ?, ?, ?, ?)",
            (device_id, name, ip, now, now, gitea_repo),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    dev = dict(row)
    dev["online"] = True
    return dev


def get_all_devices() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM devices ORDER BY last_seen DESC").fetchall()
    now = time()
    result = []
    for row in rows:
        d = dict(row)
        d["online"] = (now - d["last_seen"]) <= 120
        result.append(d)
    return result


def find_device_by_gitea_repo(repo_full_name: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM devices WHERE gitea_repo IS NOT NULL AND gitea_repo LIKE ?",
        (f"%{repo_full_name}%",),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Flash jobs
# ---------------------------------------------------------------------------

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
    conn = _get_conn()
    conn.execute(
        """INSERT INTO flash_jobs
           (id, device_id, device_name, source, firmware_binary, firmware_code, description, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (job_id, device_id, device_name, source, firmware_binary, firmware_code, description, FLASH_PENDING, now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM flash_jobs WHERE id = ?", (job_id,)).fetchone()
    mark_event(f"flash:created:{job_id}")
    return dict(row)


def update_flash_job(job_id: str, status: str, error: str | None = None) -> dict | None:
    conn = _get_conn()
    existing = conn.execute("SELECT * FROM flash_jobs WHERE id = ?", (job_id,)).fetchone()
    if not existing:
        return None
    now = time()
    if error:
        conn.execute(
            "UPDATE flash_jobs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, error, now, job_id),
        )
    else:
        conn.execute(
            "UPDATE flash_jobs SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, job_id),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM flash_jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row)


def get_flash_jobs(status: str | None = None) -> list[dict]:
    conn = _get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM flash_jobs WHERE status = ? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM flash_jobs ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

def add_conversation_entry(role: str, content: str, session_id: str = "default"):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO conversation (session_id, role, content, ts) VALUES (?, ?, ?, ?)",
        (session_id, role, content, time()),
    )
    conn.commit()
    _prune_conversation(session_id)


def _prune_conversation(session_id: str = "default", max_entries: int = 100):
    conn = _get_conn()
    conn.execute(
        """DELETE FROM conversation WHERE id IN (
            SELECT id FROM conversation WHERE session_id = ? ORDER BY ts DESC LIMIT -1 OFFSET ?
        )""",
        (session_id, max_entries),
    )
    conn.commit()


def get_conversation(session_id: str = "default", limit: int = 50) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role, content, ts FROM conversation WHERE session_id = ? ORDER BY ts ASC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def clear_conversation(session_id: str = "default"):
    conn = _get_conn()
    conn.execute("DELETE FROM conversation WHERE session_id = ?", (session_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Device logs
# ---------------------------------------------------------------------------

def add_device_log(device_id: str, message: str, level: str = "info"):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO device_logs (device_id, message, level, ts) VALUES (?, ?, ?, ?)",
        (device_id, message, level, time()),
    )
    conn.commit()
    _prune_device_logs(device_id)


def _prune_device_logs(device_id: str, max_entries: int = 200):
    conn = _get_conn()
    conn.execute(
        """DELETE FROM device_logs WHERE id IN (
            SELECT id FROM device_logs WHERE device_id = ? ORDER BY ts DESC LIMIT -1 OFFSET ?
        )""",
        (device_id, max_entries),
    )
    conn.commit()


def get_device_logs(device_id: str, limit: int = 50) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT message, level, ts FROM device_logs WHERE device_id = ? ORDER BY ts ASC LIMIT ?",
        (device_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

def add_reminder(message: str, trigger_at: float | None = None):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO reminders (message, trigger_at, created_at) VALUES (?, ?, ?)",
        (message, trigger_at, time()),
    )
    conn.commit()


def pop_pending_reminder() -> str | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM reminders WHERE done = 0 AND (trigger_at IS NULL OR trigger_at <= ?) ORDER BY created_at ASC LIMIT 1",
        (time(),),
    ).fetchone()
    if row:
        conn.execute("UPDATE reminders SET done = 1 WHERE id = ?", (row["id"],))
        conn.commit()
        return row["message"]
    return None


def has_pending_reminders() -> bool:
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM reminders WHERE done = 0 AND (trigger_at IS NULL OR trigger_at <= ?) LIMIT 1",
        (time(),),
    ).fetchone()
    return row is not None


def get_pending_reminder() -> str | None:
    return pop_pending_reminder()


# ---------------------------------------------------------------------------
# Gitea builds
# ---------------------------------------------------------------------------

def update_gitea_build_status(repo: str, status: str, sha: str = "", run_url: str = ""):
    conn = _get_conn()
    conn.execute(
        """INSERT INTO gitea_builds (repo, status, sha, run_url, ts)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(repo) DO UPDATE SET status=excluded.status, sha=excluded.sha, run_url=excluded.run_url, ts=excluded.ts""",
        (repo, status, sha[:8], run_url, time()),
    )
    conn.commit()


def get_gitea_build_status(repo: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM gitea_builds WHERE repo = ?", (repo,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

import hashlib


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_api_key(name: str, role: str = "admin") -> str:
    key = f"diva_{uuid.uuid4().hex}"
    key_hash = _hash_key(key)
    conn = _get_conn()
    conn.execute(
        "INSERT INTO api_keys (key_hash, name, role, created_at) VALUES (?, ?, ?, ?)",
        (key_hash, name, role, time()),
    )
    conn.commit()
    return key


def validate_api_key(key: str) -> dict | None:
    key_hash = _hash_key(key)
    conn = _get_conn()
    row = conn.execute("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)).fetchone()
    if row:
        conn.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (time(), row["id"]))
        conn.commit()
        return {"name": row["name"], "role": row["role"]}
    return None


def list_api_keys() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT id, name, role, created_at, last_used_at FROM api_keys ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_api_key(key_id: int) -> bool:
    conn = _get_conn()
    cur = conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Migrations / first-run setup
# ---------------------------------------------------------------------------

def get_or_create_admin_key() -> str:
    conn = _get_conn()
    existing = conn.execute("SELECT id FROM api_keys LIMIT 1").fetchone()
    if existing:
        return None
    key = create_api_key("admin-bootstrap", role="admin")
    return key
