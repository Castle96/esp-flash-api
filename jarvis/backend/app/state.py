from collections import deque
from dataclasses import dataclass, field
from time import time


@dataclass
class AssistantState:
    last_event: str = ""
    last_event_ts: float = 0.0
    session_id: str = "default"
    history: list[dict] = field(default_factory=list)


state = AssistantState()

# Ordered log of pipeline events consumed by the SSE /events endpoint.
event_log: deque = deque(maxlen=100)


def mark_event(event: str):
    state.last_event = event
    state.last_event_ts = time()
    event_log.append({"event": event, "ts": state.last_event_ts})
