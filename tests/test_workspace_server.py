import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from orchestrator.workspaces import Registry
import test_server


class WorkspaceServerTest(unittest.TestCase):
    request = test_server.ServerTest.request
    login = test_server.ServerTest.login

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.registry = Registry(self.root / "platform", create=True)
        self.ledgers = {}
        for wid in ("a", "b"):
            ledger = Ledger(self.root / wid)
            ledger.initialize({"schemaVersion": 1, "brainId": "brain-" + wid, "repositories": []})
            self.ledgers[wid] = ledger
            self.registry.register(wid, "Project " + wid, ledger.root)
        self.server = Dashboard(self.ledgers["a"], 0, self.root / ".env", runtime_root=self.root, registry=self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def auth(self, wid, session=None):
        auth = session or self.login()
        status, _, body = self.request("/api/workspaces/" + wid + "/session", headers=auth)
        self.assertEqual(status, 200)
        return {**auth, "X-CSRF-Token": json.loads(body)["csrf"]}

    def test_list_auth_and_no_ambiguous_or_traversal_routes(self):
        self.assertEqual(self.request("/api/workspaces")[0], 401)
        auth = self.login()
        status, _, body = self.request("/api/workspaces", headers=auth)
        self.assertEqual(status, 200)
        self.assertNotIn(str(self.root).encode(), body)
        self.assertEqual(len(json.loads(body)["workspaces"]), 2)
        for path in ("/api/state", "/api/workspaces/../state", "/api/workspaces/a%2Fb/state", "/api/workspaces/missing/state"):
            self.assertEqual(self.request(path, headers=auth)[0], 400)

    def test_new_registration_requires_restart_before_serving(self):
        c = Ledger(self.root / "c")
        c.initialize({"schemaVersion": 1, "brainId": "brain-c", "repositories": []})
        self.registry.register("c", "Project c", c.root)
        auth = self.login()
        self.assertEqual(self.request("/api/workspaces/c/state", headers=auth)[0], 400)
        _, _, raw = self.request("/api/workspaces", headers=auth)
        self.assertEqual(len(json.loads(raw)["workspaces"]), 2)

    def test_commands_scope_csrf_and_colliding_ids(self):
        auth_a = self.auth("a")
        auth_b = self.auth("b", auth_a)
        body = {"id": "same-command-id", "kind": "pause", "payload": {}, "expectedRevision": 1}
        self.assertEqual(self.request("/api/workspaces/b/commands", body, auth_a)[0], 403)
        self.assertEqual(self.request("/api/workspaces/a/commands", body, auth_a)[0], 200)
        self.assertEqual(self.ledgers["b"].snapshot()["commands"], [])
        self.assertEqual(self.request("/api/workspaces/b/commands", body, auth_b)[0], 200)
        for wid in ("a", "b"):
            status, _, raw = self.request("/api/workspaces/" + wid + "/state", headers=auth_a)
            self.assertEqual(status, 200)
            state = json.loads(raw)
            self.assertEqual(state["meta"]["brainId"], "brain-" + wid)
            self.assertEqual(state["workspace"]["id"], wid)
            self.assertEqual(len(state["commands"]), 1)

    def test_profiles_are_scoped_versioned_and_stale_writes_refused(self):
        profile = {"goal": "Unique alpha", "architecture": "Local", "roadmap": "First phase",
                   "successCriteria": ["Pass"], "techStack": ["Python"], "references": []}
        body = {"profile": profile, "expectedVersion": 0}
        auth = self.auth("a")
        self.assertEqual(self.request("/api/workspaces/a/profile", body, auth)[0], 200)
        self.assertEqual(self.request("/api/workspaces/a/profile", body, auth)[0], 409)
        _, _, raw = self.request("/api/workspaces/b/state", headers=auth)
        self.assertNotIn(b"Unique alpha", raw)
        _, _, raw = self.request("/api/workspaces/a/assistant/context", headers=auth)
        self.assertIn(b"Unique alpha", raw)
        _, _, raw = self.request("/api/workspaces/b/assistant/context", headers=auth)
        self.assertNotIn(b"Unique alpha", raw)

    def test_documents_do_not_fallback_to_another_workspace(self):
        # Same route and hash format, independently resolved by the selected ledger.
        with self.ledgers["a"].tx() as db:
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", ("a" * 64, "fixture", json.dumps({"private": "alpha only"})))
        auth = self.auth("a")
        self.assertEqual(self.request("/api/workspaces/a/documents/" + "a" * 64, headers=auth)[0], 200)
        self.assertEqual(self.request("/api/workspaces/b/documents/" + "a" * 64, headers=auth)[0], 400)

    def test_cached_runtime_rechecks_identity(self):
        auth = self.auth("a")
        with self.ledgers["a"].tx() as db:
            meta = self.ledgers["a"].get(db, "meta", 1)
            meta["brainId"] = "replaced"
            self.ledgers["a"].put(db, "meta", 1, meta)
        self.assertEqual(self.request("/api/workspaces/a/state", headers=auth)[0], 400)

    def test_assistant_confirmation_cannot_cross_workspaces(self):
        from orchestrator.assistant_actions import catalog
        a, b = self.server.runtime_for("a"), self.server.runtime_for("b")
        auth_a = self.auth("a")
        auth_b = self.auth("b", auth_a)
        state = a.snapshot()
        action = catalog(state, {})["brain_stop"]
        proposal = a.assistant_proposals.prepare(action, state, auth_a["X-CSRF-Token"])
        body = {"proposal": proposal, "confirmed": True}
        self.assertEqual(self.request("/api/workspaces/b/assistant/confirm", body, auth_b)[0], 409)
        self.assertEqual(self.ledgers["b"].snapshot()["commands"], [])
        with patch.object(a.notifier, "notify", side_effect=lambda command_id: {"id": command_id}):
            self.assertEqual(self.request("/api/workspaces/a/assistant/confirm", body, auth_a)[0], 200)
        self.assertIs(a.inference_lock, b.inference_lock)
        self.assertIsNot(a.observation_lock, b.observation_lock)

    def test_inference_capacity_shared_between_workspaces(self):
        a = self.server.runtime_for("a")
        auth = self.auth("b")
        a.inference_lock.acquire()
        try:
            body = {"view": "overview", "messages": [{"role": "user", "content": "Status?"}]}
            with patch("orchestrator.assistant.chat") as chat:
                self.assertEqual(self.request("/api/workspaces/b/assistant", body, auth)[0], 409)
                chat.assert_not_called()
        finally:
            a.inference_lock.release()

    def test_enrollment_blocks_http_resume_and_stale_assistant_preview_before_notification(self):
        from orchestrator import enrollment
        from orchestrator.assistant_actions import catalog
        auth = self.auth("a")
        runtime = self.server.runtime_for("a")
        state = runtime.snapshot()
        proposal = runtime.assistant_proposals.prepare(catalog(state, {})["dispatch_resume"], state, auth["X-CSRF-Token"])
        enrollment.apply(self.registry, {"id": "http-fixture-enrollment", "confirmed": True,
                                         "preview": enrollment.preview(self.registry)})
        with patch.object(runtime.notifier, "notify") as notify:
            body = {"id": "fenced-http-resume", "kind": "resume", "payload": {},
                    "expectedRevision": self.ledgers["a"].snapshot()["meta"]["revision"]}
            status, _, raw = self.request("/api/workspaces/a/commands", body, auth)
            self.assertEqual(status, 409, raw)
            self.assertIn(b"enrollment fences", raw)
            status, _, raw = self.request("/api/workspaces/a/assistant/confirm", {"proposal": proposal, "confirmed": True}, auth)
            self.assertEqual(status, 409, raw)
            notify.assert_not_called()
        self.assertEqual(self.ledgers["a"].snapshot()["commands"], [])
        _, _, raw = self.request("/api/workspaces/a/state", headers=auth)
        self.assertTrue(json.loads(raw)["admission"]["dispatchBlocked"])
        for path in ("/api/platform/enroll", "/api/workspaces/a/enroll", "/api/workspaces/a/play"):
            code, _, raw = self.request(path, {}, auth)
            self.assertIn(code, (400, 404, 409))
            self.assertIn("error", json.loads(raw))
        self.assertEqual(self.ledgers["a"].snapshot()["commands"], [])

    def test_mission_owner_review_is_scoped_and_never_notifies_or_dispatches(self):
        from test_missions import request, specification
        for wid, ledger in self.ledgers.items():
            ledger.initialize({"schemaVersion": 1, "brainId": "brain-" + wid, "repositories": [
                {"id": "fixture", "path": "/fixture/" + wid, "projectId": "project-" + wid,
                 "ref": "origin/main", "mergePolicy": "manual", "policyProfile": "standard"}]})
        body = request(spec=specification("fixture", "phase_delegated"))
        path = "/api/workspaces/a/mission"
        self.assertEqual(self.request(path)[0], 401)
        auth = self.auth("a"); other_auth = self.auth("b", auth)
        self.assertEqual(self.request(path, body, other_auth)[0], 403)
        runtime = self.server.runtime_for("a")
        with patch.object(runtime.notifier, "notify") as notify:
            status, _, raw = self.request(path, body, auth)
            self.assertEqual(status, 200, raw)
            current = json.loads(raw)["current"]
            review = request("review", 1, documentHash=current["documentHash"], confirmed=True)
            self.assertEqual(self.request("/api/workspaces/b/mission", review, other_auth)[0], 409)
            status, _, raw = self.request(path, review, auth)
            self.assertEqual(status, 200, raw)
            self.assertFalse(json.loads(raw)["receipt"]["executionAuthorized"])
            self.assertEqual(self.request(path, review, auth)[0], 200)
            notify.assert_not_called()
        status, _, raw = self.request("/api/workspaces/a/assistant/context?view=mission", headers=auth)
        self.assertEqual(status, 200, raw)
        context = json.loads(raw)
        mission = next(f["data"] for f in context["facts"] if f["id"] == "F31")
        self.assertEqual(mission["status"], "reviewed")
        self.assertFalse(mission["activation"]["available"])
        self.assertNotIn(b"/fixture/a", raw)
        for ledger in self.ledgers.values():
            self.assertEqual(ledger.snapshot()["commands"], [])
            self.assertEqual(ledger.snapshot()["workers"], [])
        _, _, raw = self.request("/api/workspaces/b/mission", headers=other_auth)
        self.assertEqual(json.loads(raw)["version"], 0)

    def test_mission_closed_schema_and_activation_routes_fail_closed(self):
        auth = self.auth("a")
        for body in ({"operation": "play"}, {"operation": "review", "confirmed": True}, [],
                     {"operation": "save", "id": "test-id-123", "expectedRevision": True, "spec": {}}):
            self.assertEqual(self.request("/api/workspaces/a/mission", body, auth)[0], 409)
        for path in ("/api/workspaces/a/mission/play", "/api/workspaces/a/mission/activate"):
            self.assertEqual(self.request(path, {}, auth)[0], 404)
        self.assertEqual(self.ledgers["a"].snapshot()["commands"], [])
