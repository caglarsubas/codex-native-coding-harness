import http.client
import contextlib
import json
import threading
import unittest
from unittest.mock import patch

from orchestrator import retention_controls as controls
from orchestrator.core import Ledger
from orchestrator.server import Dashboard
import test_retention_controls
import test_server


class RetentionServerTest(unittest.TestCase):
    request = test_server.ServerTest.request
    login = test_server.ServerTest.login

    def setUp(self):
        self.fx = test_retention_controls.RetentionControlsTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.ledger = self.fx.ledger; self.registry = self.fx.fx.api.bridge.registry
        if "b" not in {w["id"] for w in self.registry.list()}:
            ledger = Ledger(self.registry.root.parent / "retention-other")
            ledger.initialize({"schemaVersion": 1, "brainId": "brain-retention-other", "repositories": []})
            self.registry.register("b", "Other fixture", ledger.root)
        self.server = Dashboard(self.ledger, 0, self.registry.root / "missing.env", runtime_root=self.registry.root, registry=self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.stop)

    def stop(self): self.server.shutdown(); self.server.server_close(); self.thread.join()
    def auth(self, wid="a", session=None):
        auth = session or self.login()
        status, _, body = self.request("/api/workspaces/"+wid+"/session", headers=auth)
        self.assertEqual(status, 200)
        return auth | {"X-CSRF-Token": json.loads(body)["csrf"]}
    def post(self, suffix, body, auth): return self.request("/api/workspaces/a/retention/"+suffix, body, auth)
    def preview(self, auth, operation="review"):
        status, _, raw = self.post("preview", self.fx.request(operation), auth)
        self.assertEqual(status, 200, raw); return json.loads(raw)
    def body(self, proposal): return {"proposal": proposal, "confirmed": True, "cleanupAcknowledged": proposal["document"]["operation"] == "review"}

    def test_read_is_explicit_scoped_authenticated_and_no_background_inspection(self):
        route = "/api/workspaces/a/retention"
        self.assertEqual(self.request(route)[0], 401); auth = self.auth(); before = self.fx.logical()
        with patch.object(controls, "inspect", side_effect=AssertionError("No polling inspection")):
            _, _, raw = self.request("/api/workspaces/a/state", headers=auth)
            self.assertEqual(json.loads(raw)["retentionInspection"]["status"], "not_inspected")
            self.assertEqual(self.request("/api/workspaces/a/assistant/context?view=retention", headers=auth)[0], 200)
        status, _, raw = self.request(route, headers=auth); self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["workspaceId"], "a"); self.assertEqual(before, self.fx.logical())
        _, _, raw = self.request("/api/workspaces/b/state", headers=auth)
        self.assertEqual(json.loads(raw)["retentionInspection"]["status"], "not_inspected")
        self.assertEqual(self.request(route+"?inspect=all", headers=auth)[0], 400)
        self.assertEqual(self.request("/api/retention", headers=auth)[0], 400)
        self.assertEqual(self.request(route, {}, auth)[0], 404)

    def test_review_and_revoke_require_csrf_same_session_and_scope(self):
        auth = self.auth(); proposal = self.preview(auth); body = self.body(proposal)
        for headers in ({}, auth | {"X-CSRF-Token": "wrong"}, auth | {"Origin": "https://evil.example"}, self.auth("b", auth)):
            self.assertEqual(self.post("confirm", body, headers)[0], 403)
        self.assertEqual(self.post("confirm", body, self.auth())[0], 409)
        other_auth = self.auth("b", auth)
        self.assertEqual(self.request("/api/workspaces/b/retention/confirm", body, other_auth)[0], 409)
        runtime = self.server.runtime_for("a"); shared = self.fx.fx.api.store.snapshot()
        with patch.object(runtime.notifier, "notify", side_effect=AssertionError("No notification")):
            status, _, raw = self.post("confirm", body, auth); self.assertEqual(status, 200, raw)
            self.assertFalse(json.loads(raw)["replayed"])
            status, _, raw = self.post("confirm", body, auth); self.assertEqual(status, 200, raw); self.assertTrue(json.loads(raw)["replayed"])
            revoked = self.preview(auth, "revoke"); self.assertEqual(self.post("confirm", self.body(revoked), auth)[0], 200)
        self.assertTrue(self.fx.state()["policy"]["revoked"]); self.assertEqual(shared, self.fx.fx.api.store.snapshot())
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"]); self.assertEqual(self.ledger.snapshot()["commands"], [])

    def test_preview_and_confirm_closed_inputs_and_no_mutation_shortcuts(self):
        auth = self.auth(); before = self.fx.logical()
        for value in ({}, {"operation": "archive"}, {"operation": "play"}, {"operation": "review", "confirmed": True}, []):
            self.assertEqual(self.post("preview", value, auth)[0], 409)
        for suffix in ("review", "revoke", "archive", "play"):
            self.assertEqual(self.post(suffix, {}, auth)[0], 404)
        self.assertEqual(self.request("/api/workspaces/a/retention/preview?override=true", self.fx.request(), auth)[0], 400)
        self.assertEqual(before, self.fx.logical())

    def test_duplicate_json_is_rejected_before_policy_write(self):
        auth = self.auth(); before = self.fx.logical()
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        conn.request("POST", "/api/workspaces/a/retention/confirm", '{"confirmed":false,"confirmed":true}',
                     {"Content-Type": "application/json", "Origin": self.server.origin, **auth})
        response = conn.getresponse(); self.assertEqual(response.status, 409); response.read(); conn.close()
        self.assertEqual(before, self.fx.logical())

    def test_assistant_gets_closed_cache_and_navigation_but_no_retention_action(self):
        auth = self.auth(); self.request("/api/workspaces/a/retention", headers=auth)
        status, _, raw = self.request("/api/workspaces/a/assistant/context?view=retention", headers=auth)
        self.assertEqual(status, 200, raw); value = json.loads(raw)
        fact = next(f["data"] for f in value["facts"] if f["id"] == "F35")
        self.assertTrue(fact["historical"]); self.assertNotIn("runHash", json.dumps(fact)); self.assertNotIn("policyHash", json.dumps(fact))
        self.assertFalse(any("retention" in a["key"] for a in value["actions"]))
        self.assertNotIn(str(self.ledger.root).encode(), raw)
        self.assertEqual(self.request("/retention.js")[0], 200)

    def test_unconfigured_workspace_never_initializes_run_or_admission(self):
        auth = self.auth("b"); ledger = self.registry.ledger("b")
        from orchestrator.workspaces import fingerprint
        with contextlib.closing(ledger.connect()) as db: before = fingerprint(db)
        status, _, raw = self.request("/api/workspaces/b/retention", headers=auth)
        self.assertEqual(status, 200, raw); value = json.loads(raw)
        self.assertFalse(value["canReview"]); self.assertFalse(value["canRevoke"])
        self.assertIsNone(value["currentRun"])
        with contextlib.closing(ledger.connect()) as db: self.assertEqual(before, fingerprint(db))
