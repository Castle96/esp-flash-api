"""
DIVA Tool Registry

Defines callable tools that the LLM can invoke via Ollama's function-calling API.
Add new tools by:
  1. Appending an entry to TOOL_SCHEMAS (OpenAI-compatible format).
  2. Adding a handler function to _HANDLERS.
"""

import json
import threading
from datetime import datetime

from .state import mark_event, state

# ---------------------------------------------------------------------------
# OpenAI-compatible tool schema (Ollama uses the same wire format)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Returns the current local date and time.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": (
                "Returns the DIVA assistant's last pipeline event, "
                "conversation turn count, and session ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_devices",
            "description": (
                "Lists all registered ESP32 devices with their ID, name, IP, "
                "and online status. Use this to discover which devices are "
                "available before flashing."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": (
                "Schedules a spoken reminder to be delivered to the user "
                "the next time they interact with DIVA."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The reminder message to speak back to the user.",
                    },
                    "minutes": {
                        "type": "integer",
                        "description": "Minutes from now to queue the reminder (1–1440).",
                    },
                },
                "required": ["message", "minutes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flash_firmware",
            "description": (
                "Generates or updates firmware for a specific ESP32 device. "
                "Creates a flash job that requires human approval before "
                "the firmware is sent via OTA. The user will be prompted to "
                "review and approve the firmware before flashing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "The device ID (MAC) or name of the target ESP32.",
                    },
                    "firmware_code": {
                        "type": "string",
                        "description": (
                            "The MicroPython source code for the firmware. "
                            "Include a complete main.py script."
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "What this firmware does (shown in the review queue).",
                    },
                },
                "required": ["device_id", "firmware_code", "description"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Pending reminder queue (thread-safe append, main-thread pop)
# ---------------------------------------------------------------------------

_pending_reminders: list[dict] = []
_reminder_lock = threading.Lock()


def get_pending_reminder() -> str | None:
    """Pop and return the next pending reminder message, or None if empty."""
    with _reminder_lock:
        if _pending_reminders:
            return _pending_reminders.pop(0)["message"]
    return None


# ---------------------------------------------------------------------------
# Handler implementations
# ---------------------------------------------------------------------------

def _list_devices(**_kwargs) -> str:
    from .state import state
    now = __import__("time").time()
    devices = []
    for d in state.devices.values():
        online = (now - d.get("last_seen", 0)) <= 120
        devices.append({
            "id": d["id"],
            "name": d.get("name", "ESP32"),
            "ip": d.get("ip", "?"),
            "online": online,
        })
    return json.dumps({"devices": devices})


def _flash_firmware(device_id: str, firmware_code: str, description: str, **_kwargs) -> str:
    from .state import create_flash_job, state

    dev = None
    for d in state.devices.values():
        if d["id"] == device_id or d.get("name", "").lower() == device_id.lower():
            dev = d
            break
    if not dev:
        return json.dumps({
            "error": f"Device '{device_id}' not found. Use list_devices to see available devices."
        })

    job = create_flash_job(
        device_id=dev["id"],
        device_name=dev.get("name", "ESP32"),
        source="llm",
        firmware_code=firmware_code,
        description=description,
    )
    return json.dumps({
        "status": "pending_review",
        "job_id": job["id"],
        "message": (
            f"Firmware for {dev['name']} ({dev['id'][:12]}...) has been created "
            f"and is pending your review. Check the Flash Queue in the dashboard "
            f"to review and approve before it is sent via OTA."
        ),
        "description": description,
    })


def _get_current_time(**_kwargs) -> str:
    now = datetime.now()
    return json.dumps({
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "day_of_week": now.strftime("%A"),
        "time_12h": now.strftime("%I:%M %p"),
    })


def _get_system_status(**_kwargs) -> str:
    return json.dumps({
        "last_event": state.last_event,
        "last_event_ts": round(state.last_event_ts, 2),
        "session_id": state.session_id,
        "history_turns": len(state.history) // 2,
    })


def _set_reminder(message: str, minutes: int, **_kwargs) -> str:
    if not (1 <= minutes <= 1440):
        return json.dumps({"error": "minutes must be between 1 and 1440"})

    def _fire():
        with _reminder_lock:
            _pending_reminders.append({"message": message})
        mark_event(f"reminder:queued:{message[:40]}")

    threading.Timer(minutes * 60, _fire).start()
    return json.dumps({
        "status": "scheduled",
        "message": message,
        "deliver_in_minutes": minutes,
    })


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_HANDLERS: dict = {
    "get_current_time": _get_current_time,
    "get_system_status": _get_system_status,
    "list_devices": _list_devices,
    "set_reminder": _set_reminder,
    "flash_firmware": _flash_firmware,
}


def dispatch_tool(name: str, arguments: dict) -> str:
    """Execute a registered tool by name and return a JSON result string."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return handler(**arguments)
    except Exception as exc:
        return json.dumps({"error": str(exc)})
