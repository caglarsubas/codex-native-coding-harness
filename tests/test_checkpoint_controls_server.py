import contextlib
import http.client
import json
import threading
import unittest
from unittest.mock import patch

from orchestrator import checkpoint_controls as controls
from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from orchestrator.workspaces import fingerprint
import test_checkpoint_controls
import test_server


class CheckpointControlsServerTest(unittest.TestCase):
    request = test_server.ServerTest.request
    login = test_server.ServerTest.login

    def setUp(self):
        self.fx = test_checkpoint_controls.CheckpointControlsTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.ledger, self.registry = self.fx.ledger, self.fx.registry
        other = Ledger(self.registry.root.parent / "empty-owner-control-fixture")
        other.initialize({"schemaVersion": 1, "brainId": "other-fixture", "repositories": []})
        self.registry.register("other", "Other fixture", other.root)
        self.server = Dashboard(self.ledger, 0, self.registry.root / "missing.env", registry=self.registry,
                                notification_cli="/nonexistent-fixture-notifier")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start(); self.addCleanup(self.stop)

    def stop(self): self.server.shutdown(); self.server.server_close(); self.thread.join()
    def auth(self, wid="a", session=None):
        auth = session or self.login(); status, _, raw = self.request(f"/api/workspaces/{wid}/session", headers=auth)
        self.assertEqual(status, 200, raw); return auth | {"X-CSRF-Token": json.loads(raw)["csrf"]}
    def path(self, suffix="", wid="a"): return f"/api/workspaces/{wid}/checkpoint-decisions"+suffix
    def preview(self, auth, operation="review"):
        status, _, raw = self.request(self.path("/preview"), self.fx.request(operation), auth)
        self.assertEqual(status, 200, raw); return json.loads(raw)

    def test_explicit_authenticated_read_and_no_polling_inspection(self):
        self.assertEqual(self.request(self.path())[0], 401); auth = self.auth(); before = self.fx.logical()
        with patch.object(controls, "inspect", side_effect=AssertionError("No background inspection")):
            self.assertEqual(self.request("/api/workspaces/a/state", headers=auth)[0], 200)
            self.assertEqual(self.request("/api/workspaces/a/assistant/context?view=phaseCheckpoints", headers=auth)[0], 200)
        status, _, raw = self.request(self.path(), headers=auth); self.assertEqual(status, 200, raw)
        self.assertTrue(json.loads(raw)["canReview"]); self.assertEqual(before, self.fx.logical())
        self.assertEqual(self.request(self.path()+"?all=true", headers=auth)[0], 400)
        self.assertEqual(self.request("/api/checkpoint-decisions", headers=auth)[0], 400)

    def test_review_withdraw_and_historical_replay_are_local_only(self):
        auth = self.auth(); p = self.preview(auth); body = {"proposal": p, "confirmed": True}
        with patch.object(self.server.runtime_for("a").notifier, "notify", side_effect=AssertionError("No notification")):
            self.assertEqual(self.request(self.path("/confirm"), body, auth)[0], 200)
            w = self.preview(auth, "withdraw")
            self.assertEqual(self.request(self.path("/confirm"), {"proposal": w, "confirmed": True}, auth)[0], 200)
            status, _, raw = self.request(self.path("/confirm"), body, auth)
            self.assertEqual(status, 200); self.assertTrue(json.loads(raw)["replayed"])
        self.assertTrue(self.fx.state()["reviews"][0]["withdrawn"])
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertFalse((self.registry.root / "admission.sqlite3").exists())

    def test_session_csrf_origin_and_foreign_workspace_refuse(self):
        auth = self.auth(); body = {"proposal": self.preview(auth), "confirmed": True}
        for headers in ({}, auth | {"X-CSRF-Token": "wrong"}, auth | {"Origin": "https://evil.example"}, self.auth("other", auth)):
            self.assertEqual(self.request(self.path("/confirm"), body, headers)[0], 403)
        self.assertEqual(self.request(self.path("/confirm"), body, self.auth())[0], 409)
        self.assertEqual(self.request(self.path("/confirm", "other"), body, self.auth("other", auth))[0], 409)

    def test_no_direct_review_play_release_or_prepare_route(self):
        auth = self.auth(); before = self.fx.logical()
        for suffix in ("", "/review", "/withdraw", "/play", "/release", "/prepare"):
            self.assertEqual(self.request(self.path(suffix), {}, auth)[0], 404)
        self.assertEqual(self.request(self.path("/preview")+"?override=true", self.fx.request(), auth)[0], 400)
        self.assertEqual(before, self.fx.logical())

    def test_duplicate_json_and_overlapping_operation_refuse(self):
        auth = self.auth(); conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request("POST", self.path("/confirm"), '{"confirmed":false,"confirmed":true}', {"Content-Type": "application/json", "Origin": self.server.origin, **auth})
        response = conn.getresponse(); self.assertEqual(response.status, 409); response.read(); conn.close()
        with self.server.runtime_for("a").checkpoint_decision_lock:
            self.assertEqual(self.request(self.path(), headers=auth)[0], 409)
            self.assertEqual(self.request(self.path("/preview"), self.fx.request(), auth)[0], 409)

    def test_empty_workspace_is_not_initialized_or_given_authority(self):
        auth = self.auth("other"); ledger = self.registry.ledger("other")
        with contextlib.closing(ledger.connect()) as db: before = fingerprint(db)
        status, _, raw = self.request(self.path(wid="other"), headers=auth)
        self.assertEqual(status, 200, raw); value = json.loads(raw)
        self.assertFalse(value["canReview"]); self.assertEqual(value["reviews"], [])
        with contextlib.closing(ledger.connect()) as db: self.assertEqual(before, fingerprint(db))

    def test_assistant_only_receives_cached_closed_metadata(self):
        auth = self.auth(); self.request(self.path(), headers=auth)
        status, _, raw = self.request("/api/workspaces/a/assistant/context?view=phaseCheckpoints", headers=auth)
        self.assertEqual(status, 200, raw); value = json.loads(raw)
        fact = next(f["data"] for f in value["facts"] if f["id"] == "F36")
        self.assertTrue(fact["historical"]); self.assertFalse(fact["executionAuthorized"])
        self.assertNotIn("reportHash", json.dumps(fact)); self.assertNotIn(str(self.ledger.root).encode(), raw)
        self.assertFalse(any("phase_review" in a["key"] or "phase_withdraw" in a["key"] for a in value["actions"]))
        self.assertEqual(self.request("/checkpoint-controls.js")[0], 200)
