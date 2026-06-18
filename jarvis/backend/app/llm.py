import httpx

from .config import FUNCTION_CALLING_ENABLED, OLLAMA_HOST, OLLAMA_MODEL, SYSTEM_PROMPT

# Maximum tool-call rounds before falling back to a plain response.
_MAX_TOOL_ROUNDS = 5


def chat_once(text: str, history: list[dict] | None = None) -> str:
    """
    Send a prompt to the remote Ollama instance and return the reply text.
    Uses direct HTTP - no ollama Python package needed on the Pi.
    When FUNCTION_CALLING_ENABLED, tool calls are transparently dispatched
    and results fed back until the model produces a final text response.
    """
    if FUNCTION_CALLING_ENABLED:
        return _chat_with_tools(text, history)
    return _chat_plain(text, history)


def _chat_plain(text: str, history: list[dict] | None = None) -> str:
    """Single-shot LLM call with no tool support."""
    messages = _build_messages(text, history)
    resp = httpx.post(
        f"{OLLAMA_HOST}/api/chat",
        json={"model": OLLAMA_MODEL, "messages": messages, "stream": False},
        timeout=90.0,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def _chat_with_tools(text: str, history: list[dict] | None = None) -> str:
    """
    Multi-round tool-use loop.
    Sends tools schema with each request; if the model emits tool_calls,
    dispatches them and feeds results back until a plain text reply arrives.
    """
    from .tools import TOOL_SCHEMAS, dispatch_tool

    messages = _build_messages(text, history)

    for _ in range(_MAX_TOOL_ROUNDS):
        resp = httpx.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "tools": TOOL_SCHEMAS,
                "stream": False,
            },
            timeout=90.0,
        )
        resp.raise_for_status()
        msg = resp.json()["message"]

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            # Model produced a final text reply.
            return msg.get("content", "")

        # Append the assistant's tool-call turn, then each tool result.
        messages.append(msg)
        for tc in tool_calls:
            fn = tc.get("function", {})
            result = dispatch_tool(
                fn.get("name", ""),
                fn.get("arguments") or {},
            )
            messages.append({"role": "tool", "content": result})

    # Fallback: if the tool loop exhausts, do a plain call.
    return _chat_plain(text, history)


def _build_messages(text: str, history: list[dict] | None) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": text})
    return messages
