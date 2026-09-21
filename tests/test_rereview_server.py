import contextlib
import http.client
import json
import threading
import unittest
from unittest.mock import patch

from orchestrator import rereview_controls as controls
from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from orchestrator.workspaces import fingerprint
import test_rereview_controls
import test_server


class RereviewServerTest(unittest.TestCase):
    request = test_server.ServerTest.request
    login = test_server.ServerTest.login

    def setUp(self):
        self.fx = test_rereview_controls.RereviewControlsTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.ledger, self.registry = self.fx.ledger, self.fx.registry
        other = Ledger(self.registry.root.parent / "empty-rereview-fixture")
        other.initialize({"schemaVersion": 1, "brainId": "empty-fixture", "repositories": []})
        self.registry.register("other", "Other product", other.root)
        self.server = Dashboard(self.ledger, 0, self.registry.root / "missing.env", registry=self.registry,
                                notification_cli="/nonexistent-fixture-notifier")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start(); self.addCleanup(self.stop)

    def stop(self): self.server.shutdown(); self.server.server_close(); self.thread.join()
    def auth(self, wid="a", session=None):
        auth = session or self.login(); status, _, raw = self.request(f"/api/workspaces/{wid}/session", headers=auth)
        self.assertEqual(status, 200); return auth | {"X-CSRF-Token": json.loads(raw)["csrf"]}
    def path(self, suffix="", wid="a"): return f"/api/workspaces/{wid}/result-review-controls"+suffix
    def read_path(self, wid="a"): return self.path(wid=wid)+"?workerId="+self.fx.wid
    def preview(self, auth, operation="authorize"):
        status, _, raw = self.request(self.path("/preview"), self.fx.request(operation), auth)
        self.assertEqual(status, 200, raw); return json.loads(raw)

    def test_explicit_private_read_and_no_background_inspection(self):
        self.assertEqual(self.request(self.read_path())[0], 401); auth = self.auth(); before = self.fx.logical()
        with patch.object(controls, "inspect", side_effect=AssertionError("No background proof read")):
            self.assertEqual(self.request("/api/workspaces/a/state", headers=auth)[0], 200)
            self.assertEqual(self.request("/api/workspaces/a/assistant/context?view=workers", headers=auth)[0], 200)
        status, _, raw = self.request(self.read_path(), headers=auth); self.assertEqual(status, 200, raw)
        self.assertTrue(json.loads(raw)["canAuthorize"]); self.assertEqual(before, self.fx.logical())
        for suffix in ("", "?workerId=a&workerId=b", "?workerId=a&all=true", "?workerId=", "?workerId=a&x=b&y=c"):
            self.assertEqual(self.request(self.path()+suffix, headers=auth)[0], 400)
        self.assertEqual(self.request("/api/result-review-controls?workerId=a", headers=auth)[0], 400)

    def test_authorize_revoke_and_replay_never_notify_or_reset_shared_accounting(self):
        auth = self.auth(); shared = self.fx.store.snapshot(); p = self.preview(auth); body = {"proposal": p, "confirmed": True}
        with patch.object(self.server.runtime_for("a").notifier, "notify", side_effect=AssertionError("No notification")):
            self.assertEqual(self.request(self.path("/confirm"), body, auth)[0], 200)
            rev = self.preview(auth, "revoke")
            self.assertEqual(self.request(self.path("/confirm"), {"proposal": rev, "confirmed": True}, auth)[0], 200)
            status, _, raw = self.request(self.path("/confirm"), body, auth)
            self.assertEqual(status, 200); self.assertTrue(json.loads(raw)["replayed"])
        self.assertEqual(self.fx.state()["authority"]["status"], "revoked"); self.assertEqual(shared, self.fx.store.snapshot())

    def test_session_csrf_origin_and_workspace_are_bound(self):
        auth = self.auth(); body = {"proposal": self.preview(auth), "confirmed": True}
        for headers in ({}, auth | {"X-CSRF-Token": "wrong"}, auth | {"Origin": "https://evil.invalid"}, self.auth("other", auth)):
            self.assertEqual(self.request(self.path("/confirm"), body, headers)[0], 403)
        self.assertEqual(self.request(self.path("/confirm"), body, self.auth())[0], 409)
        self.assertEqual(self.request(self.path("/confirm", "other"), body, self.auth("other", auth))[0], 409)

    def test_no_direct_acceptance_authority_play_or_execution_shortcuts(self):
        auth = self.auth(); before = self.fx.logical()
        for suffix in ("", "/authorize", "/revoke", "/review", "/accept", "/play", "/resume", "/collect"):
            self.assertEqual(self.request(self.path(suffix), {}, auth)[0], 404)
        self.assertEqual(self.request(self.path("/preview")+"?override=true", self.fx.request(), auth)[0], 400)
        self.assertEqual(before, self.fx.logical())

    def test_duplicate_json_and_busy_operation_refuse(self):
        auth = self.auth(); conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request("POST", self.path("/confirm"), '{"confirmed":false,"confirmed":true}', {"Content-Type": "application/json", "Origin": self.server.origin, **auth})
        res = conn.getresponse(); self.assertEqual(res.status, 409); res.read(); conn.close()
        with self.server.runtime_for("a").rereview_lock:
            self.assertEqual(self.request(self.read_path(), headers=auth)[0], 409)
            self.assertEqual(self.request(self.path("/preview"), self.fx.request(), auth)[0], 409)

    def test_foreign_worker_does_not_initialize_or_leak_into_empty_workspace(self):
        auth = self.auth("other"); other = self.registry.ledger("other")
        with contextlib.closing(other.connect()) as db: before = fingerprint(db)
        status, _, raw = self.request(self.read_path("other"), headers=auth)
        self.assertEqual(status, 200); self.assertEqual(json.loads(raw)["status"], "unavailable")
        self.assertIsNone(json.loads(raw)["task"]); self.assertNotIn(b"changes_required", raw)
        with contextlib.closing(other.connect()) as db: self.assertEqual(before, fingerprint(db))

    def test_assistant_gets_closed_cached_counts_not_permission_or_proofs(self):
        auth = self.auth(); self.request(self.read_path(), headers=auth)
        status, _, raw = self.request("/api/workspaces/a/assistant/context?view=workers", headers=auth)
        self.assertEqual(status, 200, raw); value = json.loads(raw)
        fact = next(f["data"] for f in value["facts"] if f["id"] == "F37")
        self.assertTrue(fact["historical"]); self.assertFalse(fact["executionAuthorized"])
        self.assertEqual(fact["recordedVersions"], 1)
        for private in (self.fx.wid, "commit", "settlementHash", "reason"): self.assertNotIn(private, json.dumps(fact))
        self.assertFalse(any("result_review" in a["key"] for a in value["actions"]))
        self.assertEqual(self.request("/rereview.js")[0], 200)


if __name__ == "__main__": unittest.main()
