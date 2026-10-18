"""Browser screen-sharing sessions backed by MediaMTX WebRTC."""

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import math
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout, web

from config.settings import (
    STREAM_MEDIA_API_URL,
    STREAM_MEDIA_URL,
    STREAM_PUBLIC_URL,
    STREAM_ICE_SERVER_0_URL,
    STREAM_ICE_SERVER_1_PASSWORD,
    STREAM_ICE_SERVER_1_URL,
    STREAM_ICE_SERVER_1_USERNAME,
    STREAM_SESSION_MAX_MINUTES,
    STREAM_WEB_HOST,
    STREAM_WEB_PORT,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
WEBRTC_SESSION_PATH_PREFIX = "nss-"
PUBLISHER_HEARTBEAT_TIMEOUT = timedelta(seconds=18)
DIAGNOSTIC_STRING_FIELDS = {
    "userAgent",
    "errorName",
    "errorMessage",
    "connectionState",
    "iceConnectionState",
    "iceGatheringState",
    "sessionState",
    "trackKind",
    "trackState",
    "selectedLocalCandidateType",
    "selectedRemoteCandidateType",
    "selectedLocalCandidateProtocol",
    "selectedRemoteCandidateProtocol",
    "candidatePairState",
    "displaySurface",
    "videoErrorMessage",
}
DIAGNOSTIC_INT_FIELDS = {
    "attempt",
    "retryMs",
    "durationMs",
    "httpStatus",
    "readyState",
    "videoWidth",
    "videoHeight",
    "videoErrorCode",
}
DIAGNOSTIC_FLOAT_FIELDS = {
    "rttMs",
    "framesPerSecond",
    "bitrateMbps",
}
DIAGNOSTIC_WARNING_EVENTS = {
    "publisher.retry",
    "publisher.connection.failed",
    "publisher.connection.timeout",
    "publisher.ice.failed",
    "publisher.ice.timeout",
    "publisher.ice.gather.timeout",
    "publisher.http.failed",
    "publisher.capture.failed",
    "publisher.track.ended",
    "viewer.retry",
    "viewer.connection.failed",
    "viewer.connection.timeout",
    "viewer.ice.failed",
    "viewer.ice.timeout",
    "viewer.ice.gather.timeout",
    "viewer.status.failed",
    "viewer.http.failed",
    "viewer.no_frames",
    "viewer.video.error",
}


@dataclass
class ScreenShareSession:
    guild_id: int
    owner_id: int
    path: str
    publish_token: str
    read_token: str
    created_at: datetime
    expires_at: datetime
    state: str = "ready"
    last_publisher_heartbeat: datetime | None = None
    expiry_task: asyncio.Task | None = None


class ScreenShareError(RuntimeError):
    """Raised when a screen-share session cannot be created or stopped."""


class ScreenShareService:
    """Creates one-time links and authorizes their MediaMTX WebRTC sessions."""

    def __init__(self):
        self.web_host = STREAM_WEB_HOST
        self.web_port = STREAM_WEB_PORT
        self.public_url = STREAM_PUBLIC_URL.rstrip("/")
        self.media_url = STREAM_MEDIA_URL.rstrip("/")
        self.media_api_url = STREAM_MEDIA_API_URL.rstrip("/")
        self.max_session_minutes = STREAM_SESSION_MAX_MINUTES
        self.ice_server_0_url = STREAM_ICE_SERVER_0_URL
        self.ice_server_1_url = STREAM_ICE_SERVER_1_URL
        self.ice_server_1_username = STREAM_ICE_SERVER_1_USERNAME
        self.ice_server_1_password = STREAM_ICE_SERVER_1_PASSWORD
        if self.max_session_minutes < 1:
            raise ValueError("STREAM_SESSION_MAX_MINUTES deve ser maior que zero.")
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        self.local_only = any(
            urlsplit(value).hostname in local_hosts
            for value in (self.public_url, self.media_url)
        )
        self._sessions_by_path: dict[str, ScreenShareSession] = {}
        self._paths_by_guild: dict[int, str] = {}
        self._create_lock = asyncio.Lock()
        self._runner: web.AppRunner | None = None
        self._http: ClientSession | None = None
        self._diagnostic_windows: dict[tuple[str, str, str], tuple[float, int]] = {}

        for label, value in (
            ("STREAM_PUBLIC_URL", self.public_url),
            ("STREAM_MEDIA_URL", self.media_url),
        ):
            parsed = urlsplit(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"{label} deve ser uma URL HTTP ou HTTPS completa.")
            if parsed.scheme != "https" and parsed.hostname not in local_hosts:
                raise ValueError(
                    f"{label} deve usar HTTPS fora de localhost; o navegador exige uma origem segura para compartilhar a tela."
                )

    async def start(self) -> None:
        """Start the small HTTP application used for presenter and viewer pages."""
        if self._runner:
            return

        app = self.create_app()

        self._http = ClientSession(timeout=ClientTimeout(total=8))
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.web_host, self.web_port)
        await site.start()
        logging.info("Servidor de compartilhamento iniciado em %s:%s", self.web_host, self.web_port)

        try:
            await self._kick_old_noobsquad_sessions()
        except Exception:
            logging.warning("Não foi possível limpar sessões antigas do MediaMTX", exc_info=True)

    def create_app(self) -> web.Application:
        """Build the HTTP app so routes can be exercised without binding a port."""
        app = web.Application(client_max_size=64 * 1024, middlewares=[self._security_headers])
        app.add_routes(
            [
                web.get("/", self._index),
                web.get("/health", self._health),
                web.get("/present/{path:[A-Za-z0-9_-]+}", self._presenter_page),
                web.get("/watch/{path:[A-Za-z0-9_-]+}", self._viewer_page),
                web.get(
                    "/api/watch/{path:[A-Za-z0-9_-]+}/status",
                    self._viewer_status,
                ),
                web.post(
                    "/api/present/{path:[A-Za-z0-9_-]+}/status",
                    self._presenter_status,
                ),
                web.post(
                    "/api/present/{path:[A-Za-z0-9_-]+}/diagnostics",
                    self._presenter_diagnostics,
                ),
                web.post(
                    "/api/watch/{path:[A-Za-z0-9_-]+}/diagnostics",
                    self._viewer_diagnostics,
                ),
                web.post("/api/mediamtx/auth", self._mediamtx_auth),
                web.get("/static/{asset:[A-Za-z0-9._-]+}", self._static_asset),
            ]
        )
        return app

    async def close(self) -> None:
        """Stop active WebRTC sessions and close the HTTP server."""
        for session in list(self._sessions_by_path.values()):
            if session.expiry_task and session.expiry_task is not asyncio.current_task():
                session.expiry_task.cancel()
            if session.state != "ended":
                try:
                    await self._end_session(session)
                except Exception:
                    logging.warning(
                        "Falha ao encerrar a transmissão %s durante o fechamento",
                        session.path,
                        exc_info=True,
                    )

        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        if self._http:
            await self._http.close()
            self._http = None

    async def create_session(self, guild_id: int, owner_id: int) -> ScreenShareSession:
        """Create separate presenter and viewer credentials for a guild session."""
        async with self._create_lock:
            existing_path = self._paths_by_guild.get(guild_id)
            existing = self._sessions_by_path.get(existing_path or "")
            if existing and existing.state != "ended":
                raise ScreenShareError("Já existe uma transmissão ativa neste servidor.")

            await self._ensure_media_server()
            now = datetime.now(timezone.utc)
            path = f"{WEBRTC_SESSION_PATH_PREFIX}{secrets.token_urlsafe(18)}"
            session = ScreenShareSession(
                guild_id=guild_id,
                owner_id=owner_id,
                path=path,
                publish_token=secrets.token_urlsafe(32),
                read_token=secrets.token_urlsafe(32),
                created_at=now,
                expires_at=now + timedelta(minutes=self.max_session_minutes),
            )
            self._sessions_by_path[path] = session
            self._paths_by_guild[guild_id] = path
            session.expiry_task = asyncio.create_task(self._expire_session(session))
            return session

    def presenter_url(self, session: ScreenShareSession) -> str:
        return f"{self.public_url}/present/{session.path}#{session.publish_token}"

    def viewer_url(self, session: ScreenShareSession) -> str:
        return f"{self.public_url}/watch/{session.path}#{session.read_token}"

    def _ice_servers_for_session(self, session: ScreenShareSession) -> list[dict]:
        """Return browser ICE servers, using session-limited credentials for REST TURN."""
        servers = []
        if self.ice_server_0_url:
            servers.append({"urls": self.ice_server_0_url})

        if self.ice_server_1_url:
            server = {"urls": self.ice_server_1_url}
            if self.ice_server_1_url.lower().startswith(("turn:", "turns:")):
                if self.ice_server_1_username == "AUTH_SECRET":
                    username = f"{int(session.expires_at.timestamp())}:{session.path}"
                    digest = hmac.new(
                        self.ice_server_1_password.encode("utf-8"),
                        username.encode("utf-8"),
                        hashlib.sha1,
                    ).digest()
                    server["username"] = username
                    server["credential"] = base64.b64encode(digest).decode("ascii")
                else:
                    server["username"] = self.ice_server_1_username
                    server["credential"] = self.ice_server_1_password
                server["credentialType"] = "password"
            servers.append(server)
        return servers

    def active_session(self, guild_id: int) -> ScreenShareSession | None:
        path = self._paths_by_guild.get(guild_id)
        session = self._sessions_by_path.get(path or "")
        if session and session.state != "ended":
            return session
        return None

    async def stop_guild(self, guild_id: int) -> ScreenShareSession | None:
        session = self.active_session(guild_id)
        if session is None:
            return None
        await self._end_session(session)
        return session

    async def _end_session(self, session: ScreenShareSession) -> None:
        previous_state = session.state
        session.state = "stopping"
        try:
            await self._kick_media_sessions(session.path)
        except Exception:
            session.state = previous_state if previous_state != "stopping" else "ready"
            raise
        session.state = "ended"
        if self._paths_by_guild.get(session.guild_id) == session.path:
            self._paths_by_guild.pop(session.guild_id, None)
        if session.expiry_task and session.expiry_task is not asyncio.current_task():
            session.expiry_task.cancel()

    async def _expire_session(self, session: ScreenShareSession) -> None:
        try:
            delay = max(0, (session.expires_at - datetime.now(timezone.utc)).total_seconds())
            await asyncio.sleep(delay)
            if session.state != "ended":
                logging.info("A transmissão %s expirou", session.path)
                await self._end_session(session)
        except asyncio.CancelledError:
            return
        except Exception:
            logging.error("Falha ao expirar a transmissão %s", session.path, exc_info=True)

    async def _ensure_media_server(self) -> None:
        if not self._http:
            raise ScreenShareError("O servidor de compartilhamento ainda não foi iniciado.")
        try:
            async with self._http.get(f"{self.media_api_url}/v3/info") as response:
                if response.status != 200:
                    raise ScreenShareError("A API do MediaMTX não respondeu corretamente.")
        except ScreenShareError:
            raise
        except Exception as exc:
            raise ScreenShareError(
                "Não foi possível acessar o MediaMTX. Inicie o serviço com `docker compose up -d mediamtx`."
            ) from exc

    async def _api_json(self, route: str) -> dict:
        if not self._http:
            raise ScreenShareError("A conexão com o MediaMTX está fechada.")
        async with self._http.get(f"{self.media_api_url}{route}") as response:
            if response.status != 200:
                body = await response.text()
                raise ScreenShareError(f"Erro na API do MediaMTX ({response.status}): {body[:200]}")
            return await response.json()

    async def _kick_media_sessions(self, path: str) -> None:
        if not self._http:
            raise ScreenShareError("A conexão com o MediaMTX está fechada.")
        data = await self._api_json("/v3/webrtc/sessions/list?itemsPerPage=1000")
        for item in data.get("items", []):
            if item.get("path") == path:
                session_id = item.get("id")
                if not session_id:
                    continue
                async with self._http.post(
                    f"{self.media_api_url}/v3/webrtc/sessions/kick/{session_id}"
                ) as response:
                    if response.status not in {200, 404}:
                        body = await response.text()
                        raise ScreenShareError(
                            f"Não foi possível encerrar uma conexão WebRTC ({response.status}): {body[:200]}"
                        )

    async def _kick_old_noobsquad_sessions(self) -> None:
        data = await self._api_json("/v3/webrtc/sessions/list?itemsPerPage=1000")
        paths = {
            item.get("path")
            for item in data.get("items", [])
            if (item.get("path") or "").startswith(WEBRTC_SESSION_PATH_PREFIX)
        }
        for path in paths:
            await self._kick_media_sessions(path)

    def _get_session(self, path: str, token: str, role: str) -> ScreenShareSession | None:
        session = self._sessions_by_path.get(path)
        if session is None or not isinstance(token, str) or not token.isascii():
            return None
        expected = session.publish_token if role == "publish" else session.read_token
        if not hmac.compare_digest(token, expected):
            return None
        return session

    @staticmethod
    def _bearer_token(request: web.Request) -> str:
        authorization = request.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if separator and scheme.lower() == "bearer":
            return token.strip()
        return ""

    async def _index(self, _request: web.Request) -> web.Response:
        return web.Response(
            text=(
                "NoobSquad Screen Share is running. Use /stream iniciar in Discord "
                "to create a session."
            ),
            content_type="text/plain",
        )

    async def _health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _presenter_page(self, request: web.Request) -> web.Response:
        path = request.match_info["path"]
        session = self._sessions_by_path.get(path)
        if session is None:
            raise web.HTTPNotFound(text="Sessão de transmissão inválida ou expirada.")
        if session.state in {"ended", "stopping"}:
            raise web.HTTPGone(text="Esta transmissão já foi encerrada.")
        config = {
            "path": session.path,
            "mediaUrl": self.media_url,
            "iceServers": self._ice_servers_for_session(session),
            "statusUrl": f"/api/present/{session.path}/status",
            "diagnosticsUrl": f"/api/present/{session.path}/diagnostics",
            "expiresAt": session.expires_at.isoformat(),
        }
        return self._render_page("presenter.html", config)

    async def _viewer_page(self, request: web.Request) -> web.Response:
        path = request.match_info["path"]
        session = self._sessions_by_path.get(path)
        if session is None:
            raise web.HTTPNotFound(text="Sessão de visualização inválida ou expirada.")
        config = {
            "path": session.path,
            "mediaUrl": self.media_url,
            "iceServers": self._ice_servers_for_session(session),
            "statusUrl": f"/api/watch/{session.path}/status",
            "diagnosticsUrl": f"/api/watch/{session.path}/diagnostics",
            "expiresAt": session.expires_at.isoformat(),
            "ended": session.state == "ended",
        }
        return self._render_page("viewer.html", config)

    async def _viewer_status(self, request: web.Request) -> web.Response:
        session = self._get_session(
            request.match_info["path"], self._bearer_token(request), "read"
        )
        if session is None:
            raise web.HTTPNotFound(text="Sessão não encontrada.")

        if session.state == "live":
            heartbeat = session.last_publisher_heartbeat
            heartbeat_is_recent = (
                heartbeat is not None
                and datetime.now(timezone.utc) - heartbeat <= PUBLISHER_HEARTBEAT_TIMEOUT
            )
            if not heartbeat_is_recent or not await self._media_path_available(session.path):
                session.state = "ready"
                session.last_publisher_heartbeat = None

        return web.json_response({"state": session.state, "expiresAt": session.expires_at.isoformat()})

    async def _presenter_status(self, request: web.Request) -> web.Response:
        session = self._get_session(
            request.match_info["path"], self._bearer_token(request), "publish"
        )
        if session is None or session.state in {"ended", "stopping"}:
            raise web.HTTPNotFound(text="Sessão não encontrada.")
        try:
            payload = await request.json()
        except (json.JSONDecodeError, web.HTTPException):
            raise web.HTTPBadRequest(text="Corpo JSON inválido.")
        if not isinstance(payload, dict):
            raise web.HTTPBadRequest(text="Corpo JSON inválido.")
        state = payload.get("state")
        if state not in {"ready", "live"}:
            raise web.HTTPBadRequest(text="Estado de transmissão inválido.")

        if state == "live" and not await self._wait_for_media_path(session.path):
            session.state = "ready"
            session.last_publisher_heartbeat = None
            return web.json_response({"state": session.state, "reason": "media_not_ready"})

        session.state = state
        session.last_publisher_heartbeat = (
            datetime.now(timezone.utc) if state == "live" else None
        )
        return web.json_response({"state": session.state})

    async def _presenter_diagnostics(self, request: web.Request) -> web.Response:
        return await self._stream_diagnostics(request, "publish")

    async def _viewer_diagnostics(self, request: web.Request) -> web.Response:
        return await self._stream_diagnostics(request, "read")

    async def _stream_diagnostics(self, request: web.Request, role: str) -> web.Response:
        path = request.match_info["path"]
        session = self._get_session(path, self._bearer_token(request), role)
        if session is None:
            return web.json_response({"error": "Sessão não encontrada."}, status=404)

        try:
            payload = await request.json()
        except (json.JSONDecodeError, web.HTTPException):
            raise web.HTTPBadRequest(text="Corpo JSON inválido.")
        if not isinstance(payload, dict):
            raise web.HTTPBadRequest(text="Corpo JSON inválido.")

        event = payload.get("event")
        client_id = payload.get("clientId")
        details = payload.get("details", {})
        if (
            not isinstance(event, str)
            or re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", event) is None
            or not isinstance(client_id, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{8,64}", client_id) is None
            or not isinstance(details, dict)
        ):
            raise web.HTTPBadRequest(text="Evento de diagnóstico inválido.")

        now = time.monotonic()
        rate_key = (session.path, role, client_id)
        window_start, count = self._diagnostic_windows.get(rate_key, (now, 0))
        if now - window_start >= 60:
            window_start, count = now, 0
        if count >= 90:
            return web.json_response({"error": "Limite de diagnósticos excedido."}, status=429)
        self._diagnostic_windows[rate_key] = (window_start, count + 1)
        if len(self._diagnostic_windows) > 2048:
            self._diagnostic_windows = {
                key: value
                for key, value in self._diagnostic_windows.items()
                if now - value[0] < 60
            }

        safe_details = self._sanitize_diagnostic_details(details)
        user_agent = payload.get("userAgent")
        if isinstance(user_agent, str):
            safe_details["userAgent"] = self._sanitize_diagnostic_string(user_agent, 200)

        level = logging.WARNING if event in DIAGNOSTIC_WARNING_EVENTS else logging.INFO
        logging.log(
            level,
            "stream_diag role=%s path=%s client=%s session_state=%s event=%s details=%s",
            role,
            session.path,
            client_id,
            session.state,
            event,
            json.dumps(safe_details, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        )
        return web.json_response({"logged": True})

    @staticmethod
    def _sanitize_diagnostic_string(value: str, limit: int = 180) -> str:
        value = " ".join(value.split())
        value = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", value)
        value = re.sub(r"(?i)(token|credential|password)\s*[:=]\s*\S+", r"\1=[redacted]", value)
        value = re.sub(r"https?://\S+", "[url]", value)
        value = re.sub(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{40,}(?![A-Za-z0-9_-])", "[redacted]", value)
        return value[:limit]

    @classmethod
    def _sanitize_diagnostic_details(cls, details: dict) -> dict:
        safe = {}
        for key in DIAGNOSTIC_STRING_FIELDS:
            value = details.get(key)
            if isinstance(value, str):
                safe[key] = cls._sanitize_diagnostic_string(value)
        for key in DIAGNOSTIC_INT_FIELDS:
            value = details.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                safe[key] = max(-1_000_000, min(value, 1_000_000))
        for key in DIAGNOSTIC_FLOAT_FIELDS:
            value = details.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                safe[key] = round(max(-1_000_000, min(float(value), 1_000_000)), 3)
        return safe

    async def _media_path_available(self, path: str) -> bool:
        """Return whether MediaMTX currently has an active publisher for a path."""
        if not self._http:
            return False
        try:
            async with self._http.get(
                f"{self.media_api_url}/v3/paths/list?itemsPerPage=1000",
                timeout=ClientTimeout(total=2),
            ) as response:
                if response.status != 200:
                    return False
                payload = await response.json()
        except Exception:
            logging.debug("Não foi possível consultar o path %s no MediaMTX", path, exc_info=True)
            return False

        for item in payload.get("items", []):
            if item.get("name") == path:
                return bool(item.get("available", item.get("ready", False)))
        return False

    async def _wait_for_media_path(self, path: str, timeout: float = 5) -> bool:
        """Wait briefly for MediaMTX to expose the publisher before reporting live."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if await self._media_path_available(path):
                return True
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(0.25, remaining))

    async def _mediamtx_auth(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except (json.JSONDecodeError, web.HTTPException):
            raise web.HTTPBadRequest(text="Corpo JSON inválido.")
        if not isinstance(payload, dict):
            raise web.HTTPBadRequest(text="Corpo JSON inválido.")

        action = payload.get("action")
        path = payload.get("path")
        token = payload.get("token") or ""
        if not isinstance(path, str) or not isinstance(token, str):
            raise web.HTTPUnauthorized()
        session = self._sessions_by_path.get(path or "")
        if session is None or session.state in {"ended", "stopping"}:
            safe_action = action if action in {"publish", "read"} else "unknown"
            logging.warning(
                "stream_auth_denied path=%s action=%s reason=session_missing_or_ended",
                path if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", path) else "invalid",
                safe_action,
            )
            raise web.HTTPUnauthorized()
        if datetime.now(timezone.utc) >= session.expires_at:
            logging.warning(
                "stream_auth_denied path=%s action=%s reason=session_expired",
                session.path,
                action if action in {"publish", "read"} else "unknown",
            )
            raise web.HTTPUnauthorized()

        if action == "publish":
            allowed = token.isascii() and hmac.compare_digest(token, session.publish_token)
        elif action == "read":
            allowed = token.isascii() and hmac.compare_digest(token, session.read_token)
        else:
            allowed = False

        if not allowed:
            logging.warning(
                "stream_auth_denied path=%s action=%s reason=invalid_token",
                session.path,
                action if action in {"publish", "read"} else "unknown",
            )
            raise web.HTTPUnauthorized()
        return web.Response(status=200, text="OK")

    async def _static_asset(self, request: web.Request) -> web.FileResponse:
        asset = request.match_info["asset"]
        if asset not in {"stream.css", "stream-diagnostics.js", "presenter.js", "viewer.js"}:
            raise web.HTTPNotFound()
        return web.FileResponse(STATIC_DIR / asset)

    def _render_page(self, name: str, config: dict) -> web.Response:
        template = (STATIC_DIR / name).read_text(encoding="utf-8")
        encoded_config = json.dumps(config, ensure_ascii=False)
        encoded_config = (
            encoded_config.replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        html = template.replace("{{STREAM_CONFIG}}", encoded_config)
        return web.Response(text=html, content_type="text/html")

    @web.middleware
    async def _security_headers(self, request: web.Request, handler):
        response = await handler(request)
        media_origin = urlsplit(self.media_url)
        media_origin = f"{media_origin.scheme}://{media_origin.netloc}"
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Permissions-Policy": "display-capture=(self)",
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    f"connect-src 'self' {media_origin}; media-src 'self' blob:; "
                    "img-src 'self' data:; base-uri 'none'; form-action 'self'; "
                    "frame-ancestors 'none'"
                ),
            }
        )
        return response
