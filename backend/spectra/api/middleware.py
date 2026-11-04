"""HTTP hardening middleware (pure ASGI, so streaming request bodies are never buffered)."""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_api = scope["path"].startswith("/api/")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Cross-Origin-Resource-Policy"] = "same-origin"
                headers["Content-Security-Policy"] = CSP
                if is_api:
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _host_without_port(host_header: str) -> str:
    h = host_header.strip().lower()
    if h.startswith("["):  # IPv6 literal: "[::1]:8000"
        end = h.find("]")
        return h[: end + 1] if end != -1 else h
    return h.split(":", 1)[0]


class HostCheckMiddleware:
    """Reject requests whose Host header is not allow-listed (defence against DNS rebinding)."""

    def __init__(self, app: ASGIApp, allowed_hosts: list[str]):
        self.app = app
        self.allowed = {h.lower() for h in allowed_hosts}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            host = _host_without_port(Headers(scope=scope).get("host", ""))
            if "*" not in self.allowed and host not in self.allowed:
                response = JSONResponse(
                    {"error": {"code": "host_not_allowed", "message": "Invalid Host header."}},
                    status_code=400,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class OriginCheckMiddleware:
    """Reject state-changing requests carrying a foreign ``Origin`` (CSRF against a localhost service).

    Requests without an Origin header (curl, scripts, same-origin GETs) pass; browsers always send
    Origin on cross-site POSTs.
    """

    def __init__(self, app: ASGIApp, allowed_origins: list[str]):
        self.app = app
        self.allowed = {o.rstrip("/").lower() for o in allowed_origins}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in _UNSAFE_METHODS:
            headers = Headers(scope=scope)
            origin = headers.get("origin")
            if origin is not None and not self._permitted(origin, headers.get("host", "")):
                response = JSONResponse(
                    {"error": {"code": "origin_not_allowed", "message": "Cross-origin request rejected."}},
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

    def _permitted(self, origin: str, host: str) -> bool:
        origin_l = origin.rstrip("/").lower()
        if origin_l in self.allowed:
            return True
        parts = urlsplit(origin_l)
        return bool(parts.netloc) and parts.netloc == host.lower()
