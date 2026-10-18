import asyncio
import base64
import hashlib
import hmac
import json
import re
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

from aiohttp.test_utils import TestClient, TestServer
from dotenv import dotenv_values

from bot.streaming import ScreenShareService


class ScreenShareRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = ScreenShareService()
        self.client = TestClient(TestServer(self.service.create_app()))
        await self.client.start_server()
        self.service._ensure_media_server = AsyncMock()
        self.session = await self.service.create_session(guild_id=123, owner_id=456)

    async def asyncTearDown(self):
        if self.session.expiry_task:
            self.session.expiry_task.cancel()
            await asyncio.gather(self.session.expiry_task, return_exceptions=True)
        await self.client.close()

    async def test_health_endpoint_and_security_headers(self):
        response = await self.client.get("/health")

        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"status": "ok"})
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_presenter_page_is_served_for_an_active_session(self):
        response = await self.client.get(f"/present/{self.session.path}")
        body = await response.text()

        self.assertEqual(response.status, 200)
        self.assertIn("Compartilhar sua tela", body)
        config_match = re.search(
            r'<script id="stream-config" type="application/json">(.*?)</script>',
            body,
            re.DOTALL,
        )
        self.assertIsNotNone(config_match)
        config = json.loads(config_match.group(1))
        self.assertEqual(config["path"], self.session.path)
        self.assertEqual(config["mediaUrl"], self.service.media_url)
        self.assertEqual(
            config["diagnosticsUrl"],
            f"/api/present/{self.session.path}/diagnostics",
        )
        self.assertEqual(
            config["iceServers"],
            [
                {"urls": "stun:stun.l.google.com:19302"},
                {"urls": "stun:stun1.l.google.com:19302"},
            ],
        )
        self.assertEqual(
            config["statusUrl"], f"/api/present/{self.session.path}/status"
        )
        self.assertNotIn(self.session.publish_token, body)

    async def test_viewer_page_is_served_for_an_active_session(self):
        response = await self.client.get(f"/watch/{self.session.path}")
        body = await response.text()

        self.assertEqual(response.status, 200)
        self.assertIn("Conectar ao vivo", body)
        self.assertIn(self.service.media_url, body)
        self.assertIn("stream-diagnostics.js", body)

        config_match = re.search(
            r'<script id="stream-config" type="application/json">(.*?)</script>',
            body,
            re.DOTALL,
        )
        self.assertIsNotNone(config_match)
        config = json.loads(config_match.group(1))
        self.assertEqual(
            config["diagnosticsUrl"],
            f"/api/watch/{self.session.path}/diagnostics",
        )

    async def test_diagnostics_require_role_token_and_log_only_safe_correlated_fields(self):
        url = f"/api/watch/{self.session.path}/diagnostics"
        payload = {
            "event": "viewer.retry",
            "clientId": "client_test_123",
            "userAgent": "Browser Bearer DIAGNOSTIC_SECRET_DO_NOT_LOG",
            "details": {
                "attempt": 3,
                "httpStatus": 503,
                "connectionState": "failed",
                "errorMessage": "request failed; Bearer DIAGNOSTIC_SECRET_DO_NOT_LOG",
                "sdp": "PRIVATE_SDP_DO_NOT_LOG",
                "token": "PRIVATE_TOKEN_DO_NOT_LOG",
            },
        }

        unauthorized = await self.client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {self.session.publish_token}"},
        )
        self.assertEqual(unauthorized.status, 404)

        with self.assertLogs(level="WARNING") as captured:
            authorized = await self.client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {self.session.read_token}"},
            )

        self.assertEqual(authorized.status, 200)
        log_output = "\n".join(captured.output)
        self.assertIn(f"path={self.session.path}", log_output)
        self.assertIn("client=client_test_123", log_output)
        self.assertIn("event=viewer.retry", log_output)
        self.assertIn('"httpStatus":503', log_output)
        self.assertIn("[redacted]", log_output)
        self.assertNotIn("DIAGNOSTIC_SECRET_DO_NOT_LOG", log_output)
        self.assertNotIn("PRIVATE_SDP_DO_NOT_LOG", log_output)
        self.assertNotIn("PRIVATE_TOKEN_DO_NOT_LOG", log_output)

    async def test_unknown_session_is_not_found(self):
        response = await self.client.get("/present/nss-unknown-session")

        self.assertEqual(response.status, 404)

    async def test_status_routes_require_the_matching_role_token(self):
        viewer_url = f"/api/watch/{self.session.path}/status"
        presenter_url = f"/api/present/{self.session.path}/status"

        unauthorized_view = await self.client.get(viewer_url)
        authorized_view = await self.client.get(
            viewer_url,
            headers={"Authorization": f"Bearer {self.session.read_token}"},
        )
        unauthorized_publish = await self.client.post(
            presenter_url,
            json={"state": "ready"},
            headers={"Authorization": f"Bearer {self.session.read_token}"},
        )
        authorized_publish = await self.client.post(
            presenter_url,
            json={"state": "ready"},
            headers={"Authorization": f"Bearer {self.session.publish_token}"},
        )

        self.assertEqual(unauthorized_view.status, 404)
        self.assertEqual(authorized_view.status, 200)
        self.assertEqual((await authorized_view.json())["state"], "ready")
        self.assertEqual(unauthorized_publish.status, 404)
        self.assertEqual(authorized_publish.status, 200)

    async def test_mediamtx_auth_rejects_invalid_tokens(self):
        publish = await self.client.post(
            "/api/mediamtx/auth",
            json={
                "action": "publish",
                "path": self.session.path,
                "token": self.session.publish_token,
            },
        )
        read = await self.client.post(
            "/api/mediamtx/auth",
            json={
                "action": "read",
                "path": self.session.path,
                "token": self.session.read_token,
            },
        )
        invalid = await self.client.post(
            "/api/mediamtx/auth",
            json={"action": "publish", "path": self.session.path, "token": "wrong"},
        )

        self.assertEqual(publish.status, 200)
        self.assertEqual(read.status, 200)
        self.assertEqual(invalid.status, 401)

    async def test_generated_links_use_the_configured_public_origin(self):
        presenter_url = self.service.presenter_url(self.session)
        viewer_url = self.service.viewer_url(self.session)

        self.assertEqual(
            presenter_url,
            f"{self.service.public_url}/present/{self.session.path}#{self.session.publish_token}",
        )
        self.assertEqual(
            viewer_url,
            f"{self.service.public_url}/watch/{self.session.path}#{self.session.read_token}",
        )

    async def test_turn_shared_secret_generates_expiring_credentials(self):
        self.service.ice_server_1_url = "turn:turn.example.com:28478?transport=tcp"
        self.service.ice_server_1_username = "AUTH_SECRET"
        self.service.ice_server_1_password = "test-shared-secret"

        servers = self.service._ice_servers_for_session(self.session)
        turn_username = f"{int(self.session.expires_at.timestamp())}:{self.session.path}"
        expected_password = base64.b64encode(
            hmac.new(
                b"test-shared-secret",
                turn_username.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("ascii")

        self.assertEqual(servers[1]["urls"], self.service.ice_server_1_url)
        self.assertEqual(servers[1]["username"], turn_username)
        self.assertEqual(servers[1]["credential"], expected_password)
        self.assertNotIn("test-shared-secret", json.dumps(servers))


class StreamingDeploymentConfigTests(unittest.TestCase):
    def test_example_urls_and_proxy_use_the_same_public_port(self):
        root = Path(__file__).resolve().parents[1]
        example = dotenv_values(root / ".env_example")
        public_port = int(example["STREAM_PUBLIC_PORT"])

        for key in ("STREAM_PUBLIC_URL", "STREAM_PUBLIC_ORIGIN", "STREAM_MEDIA_URL"):
            with self.subTest(setting=key):
                self.assertEqual(urlsplit(example[key]).port, public_port)
                self.assertEqual(urlsplit(example[key]).hostname, example["STREAM_DOMAIN"])
                self.assertEqual(urlsplit(example[key]).hostname, "noobsquad.ddns.net")

        self.assertEqual(example["STREAM_DOMAIN"], "noobsquad.ddns.net")
        self.assertEqual(example["STREAM_MEDIA_PUBLIC_HOST"], example["STREAM_DOMAIN"])

        compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
        caddyfile = (root / "Caddyfile").read_text(encoding="utf-8")
        self.assertIn("MTX_WEBRTCICESERVERS2_0_URL", compose)
        self.assertIn("MTX_WEBRTCICESERVERS2_1_URL", compose)
        self.assertIn(f'"${{STREAM_PUBLIC_PORT:-{public_port}}}:443"', compose)
        self.assertNotIn('"443:443"', compose)
        self.assertNotIn('"80:80"', compose)
        self.assertIn("./caddy_certs:/etc/caddy/certs:ro", compose)
        self.assertIn("noobsquad_tls_fullchain.pem", caddyfile)
        self.assertIn("noobsquad_tls.key", caddyfile)
        self.assertIn("{$STREAM_PUBLIC_PORT}", caddyfile)
        self.assertIn("protocols h1 h2", caddyfile)
        self.assertNotIn("profile shortlived", caddyfile)
        self.assertNotIn("issuer internal", caddyfile)


if __name__ == "__main__":
    unittest.main()
