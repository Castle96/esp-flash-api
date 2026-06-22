import hashlib
import hmac
import os
import secrets
import time
import uuid

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from .config import AUTH_ENABLED, JWT_SECRET
from .db import validate_api_key

_PUBLIC_PATHS = {
    "/health",
    "/",
    "/events",
    "/docs",
    "/openapi.json",
    "/weather",
    "/login",
}

_DEVICE_PATHS = {
    "/devices/heartbeat",
    "/logs/",
}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _create_jwt(payload: dict) -> str:
    import json
    header = {"alg": "HS256", "typ": "JWT"}
    encoded = _base64url(json.dumps(header).encode()) + b"." + _base64url(json.dumps(payload).encode())
    sig = hmac.new(JWT_SECRET.encode(), encoded, hashlib.sha256).digest()
    return encoded.decode() + "." + _base64url(sig).decode()


def _base64url(data: bytes) -> bytes:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _decode_jwt(token: str) -> dict | None:
    import json
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        expected_sig = hmac.new(
            JWT_SECRET.encode(),
            (header_b64 + "." + payload_b64).encode(),
            hashlib.sha256,
        ).digest()
        actual_sig = _base64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_base64url_decode(payload_b64).decode())
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def _base64url_decode(data: str) -> bytes:
    import base64
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def create_session_token(username: str, role: str = "admin") -> tuple[str, int]:
    expires_in = 86400 * 7
    payload = {
        "sub": username,
        "role": role,
        "iat": time.time(),
        "exp": time.time() + expires_in,
        "jti": uuid.uuid4().hex,
    }
    return _create_jwt(payload), expires_in


def verify_request(request: Request) -> dict | None:
    if not AUTH_ENABLED:
        return {"role": "admin", "auth_disabled": True}

    path = request.url.path
    method = request.method

    if path in _PUBLIC_PATHS or (method == "OPTIONS"):
        return None

    auth_header = request.headers.get("Authorization", "")
    api_key = request.headers.get("X-API-Key", "")

    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = _decode_jwt(token)
        if payload:
            return payload
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    if api_key:
        result = validate_api_key(api_key)
        if result:
            return result
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    if path.startswith("/devices/") or path.startswith("/logs/"):
        return {"role": "device", "authenticated": False}

    raise HTTPException(
        status_code=HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide X-API-Key header or Authorization: Bearer <token>",
    )


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            auth_result = verify_request(request)
            if auth_result:
                request.state.auth = auth_result
            else:
                request.state.auth = {"role": "anonymous"}
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)
