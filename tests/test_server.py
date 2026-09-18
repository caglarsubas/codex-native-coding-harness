import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid

from orchestrator.core import Ledger
from orchestrator.server import Dashboard


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "state")
        self.server = Dashboard(self.ledger, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        merged = {"Content-Type": "application/json", "Origin": self.server.origin, **(headers or {})}
        conn.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None, merged)
        res = conn.getresponse(); result = res.status, dict(res.getheaders()), res.read(); conn.close(); return result

    def login(self):
        status, headers, body = self.request("/api/login", {"token": self.server.bootstrap})
        self.assertEqual(status, 200)
        return {"Cookie": headers["Set-Cookie"].split(";")[0], "X-CSRF-Token": json.loads(body)["csrf"]}

    def test_private_reads_need_auth_and_never_expose_controller_token(self):
        self.assertEqual(self.request("/api/state")[0], 401)
        auth = self.login(); token = self.ledger.acquire("fixture")
        status, headers, body = self.request("/api/state", headers=auth)
        self.assertEqual(status, 200); self.assertNotIn(token.encode(), body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_cross_origin_csrf_and_host_refused(self):
        auth = self.login()
        command = {"id": str(uuid.uuid4()), "kind": "pause", "expectedRevision": 0, "payload": {}}
        for change in ({"Origin": "https://malicious.example"}, {"X-CSRF-Token": "wrong"}, {"Host": "malicious.example"}):
            self.assertEqual(self.request("/api/commands", command, {**auth, **change})[0], 403)
        self.assertEqual(self.request("/api/commands", command, auth)[0], 200)

    def test_static_has_no_private_data_and_traversal_not_served(self):
        status, _, body = self.request("/"); self.assertEqual(status, 200)
        self.assertNotIn(self.server.bootstrap.encode(), body)
        self.assertNotEqual(self.request("/../.state/ledger.sqlite3", headers=self.login())[0], 200)

    def test_unknown_command_and_bad_revision_rejected(self):
        auth = self.login()
        for kind, rev in (("shell",0), ("pause",999)):
            status, _, _ = self.request("/api/commands", {"id":str(uuid.uuid4()),"kind":kind,"expectedRevision":rev,"payload":{}}, auth)
            self.assertEqual(status, 409)

    def test_paused_dashboard_resume_is_queued_not_executed(self):
        status, _, raw = self.request("/api/commands", {"id":str(uuid.uuid4()),"kind":"resume","expectedRevision":0,"payload":{}}, self.login())
        self.assertEqual(status,200); self.assertEqual(json.loads(raw)["status"],"queued")
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])


if __name__ == "__main__": unittest.main()
