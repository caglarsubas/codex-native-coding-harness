import contextlib
import http.client
import json
import threading
import unittest
from unittest.mock import patch

from orchestrator import model_controls as controls
from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from orchestrator.workspaces import fingerprint
import test_model_controls
import test_server


class ModelControlsServerTest(unittest.TestCase):
    request = test_server.ServerTest.request
    login = test_server.ServerTest.login

    def setUp(self):
        self.fx = test_model_controls.ModelControlsTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.ledger, self.registry = self.fx.ledger, self.fx.registry
        other = Ledger(self.registry.root.parent / "empty-model-fixture")
        other.initialize({"schemaVersion": 1, "brainId": "empty-fixture", "repositories": []})
        self.registry.register("other", "Other product", other.root)
        self.server = Dashboard(self.ledger, 0, self.registry.root / "missing.env", registry=self.registry,
                                notification_cli="/nonexistent-fixture-notifier")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start(); self.addCleanup(self.stop)

    def stop(self): self.server.shutdown(); self.server.server_close(); self.thread.join()
    def auth(self, wid="a", session=None):
        auth = session or self.login(); status, _, raw = self.request(f"/api/workspaces/{wid}/session", headers=auth)
        self.assertEqual(status, 200); return auth | {"X-CSRF-Token": json.loads(raw)["csrf"]}
    def path(self, suffix="", wid="a"): return f"/api/workspaces/{wid}/model-policy-controls"+suffix
    def preview(self, auth, operation="review"):
        status, _, raw = self.request(self.path("/preview"), self.fx.request(operation), auth)
        self.assertEqual(status, 200, raw); return json.loads(raw)

    def test_explicit_auth_read_only_and_no_poll_or_chat_inspection(self):
        self.assertEqual(self.request(self.path())[0], 401); auth = self.auth(); before = self.fx.logical()
        with patch.object(controls, "inspect", side_effect=AssertionError("No background inspection")):
            self.assertEqual(self.request("/api/workspaces/a/state", headers=auth)[0], 200)
            self.assertEqual(self.request("/api/workspaces/a/assistant/context?view=mission", headers=auth)[0], 200)
        status, _, raw = self.request(self.path(), headers=auth); self.assertEqual(status, 200, raw)
        self.assertTrue(json.loads(raw)["canReview"]); self.assertEqual(before, self.fx.logical())
        self.assertEqual(self.request(self.path()+"?refresh=true", headers=auth)[0], 400)
        self.assertEqual(self.request("/api/model-policy-controls", headers=auth)[0], 400)

    def test_review_revoke_and_replay_never_notify_or_start_tasks(self):
        auth = self.auth(); p = self.preview(auth); body = {"proposal": p, "confirmed": True}
        before = self.ledger.snapshot()
        with patch.object(self.server.runtime_for("a").notifier, "notify", side_effect=AssertionError("No notification")):
            self.assertEqual(self.request(self.path("/confirm"), body, auth)[0], 200)
            rev = self.preview(auth, "revoke")
            self.assertEqual(self.request(self.path("/confirm"), {"proposal": rev, "confirmed": True}, auth)[0], 200)
            status, _, raw = self.request(self.path("/confirm"), body, auth)
            self.assertEqual(status, 200); self.assertTrue(json.loads(raw)["replayed"])
        self.assertTrue(self.fx.state()["policy"]["revoked"])
        for key in ("queue", "commands", "workers"): self.assertEqual(before[key], self.ledger.snapshot()[key])

    def test_session_csrf_origin_workspace_and_literal_confirmation_are_bound(self):
        auth = self.auth(); body = {"proposal": self.preview(auth), "confirmed": True}
        for headers in ({}, auth | {"X-CSRF-Token": "wrong"}, auth | {"Origin": "https://evil.invalid"}, self.auth("other", auth)):
            self.assertEqual(self.request(self.path("/confirm"), body, headers)[0], 403)
        self.assertEqual(self.request(self.path("/confirm"), body, self.auth())[0], 409)
        self.assertEqual(self.request(self.path("/confirm", "other"), body, self.auth("other", auth))[0], 409)
        self.assertEqual(self.request(self.path("/confirm"), body | {"confirmed": 1}, auth)[0], 409)

    def test_no_direct_policy_capability_selection_native_or_play_routes(self):
        auth = self.auth(); before = self.fx.logical()
        for suffix in ("", "/review", "/revoke", "/capability", "/select", "/observe", "/play", "/resume"):
            self.assertEqual(self.request(self.path(suffix), {}, auth)[0], 404)
        self.assertEqual(self.request(self.path("/preview")+"?override=true", self.fx.request(), auth)[0], 400)
        self.assertEqual(before, self.fx.logical())

    def test_duplicate_nonfinite_oversize_and_busy_requests_refuse(self):
        auth = self.auth()
        for raw, expected in (('{"confirmed":false,"confirmed":true}', 409), ('{"value":NaN}',409), ('x'*32769,413)):
            conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
            conn.request("POST", self.path("/confirm"), raw, {"Content-Type":"application/json", "Origin":self.server.origin, **auth})
            res=conn.getresponse(); self.assertEqual(res.status, expected); res.read(); conn.close()
        with self.server.runtime_for("a").model_lock:
            self.assertEqual(self.request(self.path(), headers=auth)[0], 409)
            self.assertEqual(self.request(self.path("/preview"), self.fx.request(), auth)[0], 409)

    def test_empty_workspace_is_not_initialized_or_given_another_catalog(self):
        auth = self.auth("other"); other = self.registry.ledger("other")
        with contextlib.closing(other.connect()) as db: before = fingerprint(db)
        status, _, raw = self.request(self.path(wid="other"), headers=auth)
        self.assertEqual(status, 200); report = json.loads(raw)
        self.assertFalse(report["canReview"]); self.assertIsNone(report["capability"]); self.assertIsNone(report["policy"])
        self.assertNotIn(b"fixture-reasoner", raw)
        with contextlib.closing(other.connect()) as db: self.assertEqual(before, fingerprint(db))

    def test_assistant_gets_closed_cached_counts_not_models_or_owner_actions(self):
        auth = self.auth(); self.request(self.path(), headers=auth)
        status, _, raw = self.request("/api/workspaces/a/assistant/context?view=mission", headers=auth)
        self.assertEqual(status, 200, raw); value = json.loads(raw)
        fact = next(f["data"] for f in value["facts"] if f["id"] == "F38")
        self.assertTrue(fact["historical"]); self.assertFalse(fact["executionAuthorized"])
        for private in ("fixture-reasoner", "catalogHash", "policyHash", "profiles", "reason"): self.assertNotIn(private, json.dumps(fact))
        self.assertFalse(any("model_policy" in a["key"] for a in value["actions"]))
        self.assertEqual(self.request("/model-controls.js")[0], 200)


if __name__ == "__main__": unittest.main()
