import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid

from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from orchestrator.observations import capture
from unittest.mock import patch


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

    def test_artifact_preview_is_authenticated_json_and_download_is_inert(self):
        with self.ledger.tx() as db:
            document = capture(db,"fixture",b"<script>alert('x')</script>",{"name":"page.html","references":[],"orderAt":1,"repository":"fixture"})
        path = "/api/artifacts/" + document["id"]
        self.assertEqual(self.request(path)[0],401)
        auth = self.login()
        status, headers, raw = self.request(path,headers=auth)
        self.assertEqual(status,200)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertEqual(json.loads(raw)["text"],"<script>alert('x')</script>")
        status, headers, raw = self.request(path + "/download",headers=auth)
        self.assertEqual(status,200)
        self.assertEqual(headers["Content-Type"],"application/octet-stream")
        self.assertTrue(headers["Content-Disposition"].startswith("attachment;"))
        self.assertNotEqual(self.request("/api/artifacts/../../ledger.sqlite3",headers=auth)[0],200)

    def test_observation_refresh_requires_csrf_and_fixed_shape(self):
        auth = self.login()
        self.assertEqual(self.request("/api/observe",{"remote":False},{"Origin":self.server.origin})[0],403)
        self.assertEqual(self.request("/api/observe",{"remote":False,"shell":"id"},auth)[0],400)
        entered = threading.Event(); release = threading.Event()
        def collect(*args):
            entered.set(); release.wait(2); return {"status":"complete"}
        with patch("orchestrator.observations.refresh_observations",side_effect=collect):
            self.assertEqual(self.request("/api/observe",{"remote":False},auth)[0],202)
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.request("/api/observe",{"remote":False},auth)[0],409)
            release.set()
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertEqual(self.ledger.snapshot()["workers"],[])


if __name__ == "__main__": unittest.main()
