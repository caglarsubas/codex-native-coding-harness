"""Real HTTP tests with disposable ledgers. No Docker or live native calls needed."""
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from deployment.gateway import Gateway
from orchestrator.core import Ledger
from orchestrator.server import Dashboard


class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root / "state")
        self.ledger.initialize({"schemaVersion": 1, "brainId": "fixture-brain", "repositories": []})
        self.gateway = Gateway(("127.0.0.1", 0), "127.0.0.1", 8767, 8768)
        self.public = self.gateway.server_port
        self.gateway.public_host = f"127.0.0.1:{self.public}"
        self.gateway.origin = "http://" + self.gateway.public_host
        self.start_backend()
        self.thread = threading.Thread(target=self.gateway.serve_forever, daemon=True)
        self.thread.start()

    def start_backend(self):
        self.backend = Dashboard(self.ledger, 0, self.root / ".env", runtime_root=self.root, public_port=self.public)
        self.gateway.backend_port = self.backend.server_port
        self.backend_thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.backend_thread.start()

    def stop_backend(self):
        self.backend.shutdown(); self.backend.server_close(); self.backend_thread.join()

    def tearDown(self):
        self.gateway.shutdown(); self.gateway.server_close(); self.thread.join()
        self.stop_backend(); self.tmp.cleanup()

    def request(self, path, body=None, headers=None, method=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.public, timeout=5)
        merged = {"Origin": self.gateway.origin, "Content-Type": "application/json", **(headers or {})}
        conn.request(method or ("POST" if body is not None else "GET"), path,
                     json.dumps(body) if body is not None else None, merged)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def login(self, days=0):
        status, headers, body = self.request("/api/login", {"token": self.backend.bootstrap, "rememberDays": days})
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        return {"Cookie": headers["Set-Cookie"].split(";")[0], "X-CSRF-Token": json.loads(body)["csrf"]}

    def test_health_is_metadata_free_and_read_only(self):
        before = self.ledger.snapshot()
        status, _, body = self.request("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"service": "codex-orchestrator", "status": "ok"})
        after = self.ledger.snapshot()
        before.pop("serverTime"); after.pop("serverTime")
        self.assertEqual(after, before)

    def test_static_auth_and_security_headers(self):
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertNotIn(self.backend.bootstrap.encode(), body)
        self.assertEqual(self.request("/api/state")[0], 401)
        auth = self.login()
        self.assertEqual(self.request("/api/state", headers=auth)[0], 200)
        self.assertEqual(self.request("/api/session/remember", {"rememberDays": 30}, {**auth, "X-CSRF-Token": "wrong"})[0], 403)
        self.assertEqual(self.request("/api/logout", {}, auth)[0], 200)
        self.assertEqual(self.request("/api/state", headers=auth)[0], 401)

    def test_remembered_auth_survives_backend_port_change(self):
        auth = self.login(30)
        old_cookie = self.backend.browser_auth.cookie
        self.stop_backend(); self.start_backend()
        self.assertEqual(self.backend.origin, self.gateway.origin)
        self.assertEqual(self.backend.browser_auth.cookie, old_cookie)
        self.assertEqual(self.request("/api/session", headers=auth)[0], 200)

    def test_backend_keeps_exact_public_origin(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.backend.server_port)
        conn.request("GET", "/healthz")
        self.assertEqual(conn.getresponse().status, 403)
        conn.close()
        self.assertEqual(self.backend.server_address[0], "127.0.0.1")

    def test_host_origin_and_forwarded_headers_cannot_bypass(self):
        for headers in ({"Host": "evil.test"}, {"Origin": "https://evil.test"},
                        {"Host": "evil.test", "X-Forwarded-Host": self.gateway.public_host}):
            self.assertEqual(self.request("/healthz", headers=headers)[0], 403)
        self.assertEqual(self.request("/healthz", headers={"X-Forwarded-Host": "evil.test"})[0], 200)

    def test_request_bounds_and_no_generic_proxy(self):
        self.assertEqual(self.request("/api/login", "x" * 32768)[0], 413)
        self.assertEqual(self.request("http://evil.test/", headers={"Host": self.gateway.public_host})[0], 400)
        self.assertEqual(self.request("/", headers={"Transfer-Encoding": "chunked"})[0], 400)
        self.assertEqual(self.request("/", headers={"Content-Length": "-1"})[0], 400)
        self.assertEqual(self.request("/", headers={"Content-Length": "1"})[0], 400)
        self.assertEqual(self.request("/", method="CONNECT")[0], 501)

    def test_duplicate_headers_and_missing_post_origin(self):
        for extra in (f"Host: {self.gateway.public_host}\r\n", "Content-Length: 0\r\nContent-Length: 0\r\n"):
            with socket.create_connection(("127.0.0.1", self.public), timeout=5) as connection:
                connection.sendall(f"GET / HTTP/1.0\r\nHost: {self.gateway.public_host}\r\n{extra}\r\n".encode())
                self.assertIn(b" 400 ", connection.recv(1024).split(b"\r\n")[0])
        connection = http.client.HTTPConnection("127.0.0.1", self.public)
        connection.request("POST", "/api/login", "{}", {"Content-Type": "application/json"})
        self.assertEqual(connection.getresponse().status, 403)
        connection.close()

    def test_unavailable_backend_fails_closed_without_retry(self):
        with patch("deployment.gateway.http.client.HTTPConnection.request", side_effect=OSError("private detail")) as send:
            # Use raw client so patch affects only the gateway's upstream connection.
            with socket.create_connection(("127.0.0.1", self.public), timeout=5) as connection:
                connection.sendall(f"GET /healthz HTTP/1.0\r\nHost: {self.gateway.public_host}\r\n\r\n".encode())
                chunks = []
                while data := connection.recv(4096): chunks.append(data)
            response = b"".join(chunks)
            self.assertIn(b" 503 ", response)
            self.assertNotIn(b"private detail", response)
            self.assertEqual(send.call_count, 1)

    def test_invalid_public_port_rejected(self):
        for value in (0, -1, 65536, True, "8768"):
            with self.assertRaises(ValueError):
                Dashboard(self.ledger, 0, public_port=value)

    def test_wrong_backend_service_is_not_healthy(self):
        from orchestrator.server import Handler
        original = Handler.respond
        def wrong(handler, status, value, *args, **kwargs):
            return original(handler, 200, {"status": "ok", "service": "unrelated"})
        with patch.object(Handler, "respond", wrong):
            self.assertEqual(self.request("/healthz")[0], 503)

    def test_ambiguous_post_is_not_retried(self):
        with patch("deployment.gateway.http.client.HTTPConnection.request", side_effect=OSError("disconnect")) as send:
            with socket.create_connection(("127.0.0.1", self.public), timeout=5) as connection:
                connection.sendall((f"POST /api/commands HTTP/1.0\r\nHost: {self.gateway.public_host}\r\n"
                                    f"Origin: {self.gateway.origin}\r\nContent-Length: 2\r\n\r\n{{}}").encode())
                chunks = []
                while data := connection.recv(4096): chunks.append(data)
            response = b"".join(chunks)
            self.assertIn(b" 502 ", response)
            self.assertIn(b"inspect its receipt before retrying", response)
            self.assertEqual(send.call_count, 1)


if __name__ == "__main__":
    unittest.main()
