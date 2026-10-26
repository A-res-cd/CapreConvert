"""Same-origin sessions, bootstrap/pairing exchange and Host validation."""

import hashlib
import ipaddress
import json
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

import psutil
from starlette.requests import Request
from starlette.responses import JSONResponse

from .errors import Problem
from .storage import atomic_json, opaque_id

COOKIE = "localraw_session"


def private_addresses():
    addresses = set()
    for entries in psutil.net_if_addrs().values():
        for entry in entries:
            try:
                ip = ipaddress.ip_address(entry.address)
                if ip.version == 4 and ip.is_private and not (ip.is_loopback or ip.is_link_local):
                    addresses.add(str(ip))
            except ValueError:
                pass
    return sorted(addresses)


def error_response(problem, request_id):
    return JSONResponse(
        {
            "error": {
                "code": problem.code,
                "message": problem.message,
                "request_id": request_id,
                "details": problem.details,
            }
        },
        status_code=problem.status,
    )


class Security:
    def __init__(self, workspace, settings):
        self.workspace, self.settings = workspace, settings
        self.bootstrap = secrets.token_urlsafe(32)
        self.bootstrap_expires = time.time() + 120
        self.pairing = secrets.token_urlsafe(24) if settings.lan else None
        self.attempts = defaultdict(deque)
        self.global_attempts = deque()
        self.sessions = {}
        self.path = workspace.root / "manifests" / "sessions.json"
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text("utf-8"))
                self.sessions = {
                    key: value
                    for key, value in data.items()
                    if len(key) == 64
                    and value["expires"] > time.time()
                    and len(value["owner"]) == 32
                    and value["csrf"]
                }
            except (OSError, ValueError, TypeError, KeyError):
                self.sessions = {}
        self.addresses = private_addresses() if settings.lan else []
        self.hosts = {"127.0.0.1", "localhost", *self.addresses, *settings.allowed_hosts}

    def origin(self, request):
        host = request.headers.get("host", "")
        try:
            parsed = urlsplit("//" + host)
            valid = (
                parsed.hostname in self.hosts
                and (parsed.port or (443 if self.settings.tls_cert else 80)) == self.settings.port
                and not parsed.username
                and not parsed.password
                and not parsed.path
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            valid = False
        if not valid:
            raise Problem(403, "INVALID_HOST", "This host address is not allowed.")
        scheme = "https" if self.settings.tls_cert else "http"
        return f"{scheme}://{host}"

    def authenticate(self, request):
        token = request.cookies.get(COOKIE, "")
        hashed = hashlib.sha256(token.encode()).hexdigest()
        with self.workspace.lock:
            session = self.sessions.get(hashed)
            if not session or session["expires"] <= time.time():
                raise Problem(401, "SESSION_REQUIRED", "Pair this browser to continue.")
            return session

    def exchange(self, credential, client_ip):
        now = time.time()
        with self.workspace.lock:
            attempts = self.attempts[client_ip]
            for bucket in (attempts, self.global_attempts):
                while bucket and bucket[0] < now - 300:
                    bucket.popleft()
            if len(attempts) >= 8 or len(self.global_attempts) >= 50:
                raise Problem(429, "PAIRING_RATE_LIMIT", "Too many pairing attempts. Wait five minutes.")
            attempts.append(now)
            self.global_attempts.append(now)
            try:
                loopback = ipaddress.ip_address(client_ip).is_loopback
            except ValueError:
                loopback = False
            local = (
                loopback
                and now < self.bootstrap_expires
                and self.bootstrap
                and secrets.compare_digest(credential.encode(), self.bootstrap.encode())
            )
            paired = self.pairing and secrets.compare_digest(credential.encode(), self.pairing.encode())
            if not (local or paired):
                raise Problem(401, "PAIRING_FAILED", "Pairing code invalid or expired.")
            self.sessions = {
                key: value for key, value in self.sessions.items() if value["expires"] > now
            }
            if len(self.sessions) >= self.settings.max_sessions:
                raise Problem(429, "SESSION_LIMIT", "Session limit reached on this computer.")
            token = secrets.token_urlsafe(32)
            session = {
                "owner": opaque_id(),
                "csrf": secrets.token_urlsafe(32),
                "expires": now + self.settings.session_expiry_seconds,
            }
            self.sessions[hashlib.sha256(token.encode()).hexdigest()] = session
            atomic_json(self.path, self.sessions)
            if local:
                self.bootstrap = ""
            return token, session


class SecurityMiddleware:
    def __init__(self, app, server):
        self.app, self.server = app, server

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        request_id = opaque_id()
        scope.setdefault("state", {})["request_id"] = request_id

        async def secured_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message["headers"]) + [
                    (b"x-request-id", request_id.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                    ),
                ]
            await send(message)

        try:
            security = self.server.state.security
            expected = security.origin(request)
            path = scope["path"]
            mutation = request.method in {"POST", "PUT", "PATCH", "DELETE"}
            public = path in {"/health", "/api/v1/health", "/", "/favicon.ico"} or path.startswith(
                "/static/"
            )
            exchange = path == "/api/v1/sessions" and request.method == "POST"
            if mutation and request.headers.get("origin") != expected:
                raise Problem(403, "INVALID_ORIGIN", "A same-origin browser request is required.")
            if path.startswith("/api/") and not public and not exchange:
                session = security.authenticate(request)
                scope["state"]["session"] = session
                if mutation and not secrets.compare_digest(
                    request.headers.get("x-csrf-token", "").encode(), session["csrf"].encode()
                ):
                    raise Problem(403, "INVALID_CSRF", "Session security token is missing or invalid.")
            if mutation and not (request.method == "PUT" and path.endswith("/content")):
                body = bytearray()
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > 64 * 1024:
                        raise Problem(413, "REQUEST_TOO_LARGE", "Request JSON exceeds 64 KiB.")
                    body.extend(chunk)
                    if not message.get("more_body"):
                        break
                sent = False
                original_receive = receive

                async def buffered_receive():
                    nonlocal sent
                    if not sent:
                        sent = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return await original_receive()

                receive = buffered_receive
            await self.app(scope, receive, secured_send)
        except Problem as problem:
            await error_response(problem, request_id)(scope, receive, secured_send)
