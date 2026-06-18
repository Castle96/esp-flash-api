from dataclasses import dataclass, field
from time import time


@dataclass
class AssistantState:
    last_event: str = ""
    last_event_ts: float = 0.0
    session_id: str = "default"
    history: list[dict] = field(default_factory=list)


state = AssistantState()


def mark_event(event: str):
    state.last_event = event
    state.last_event_ts = time()
