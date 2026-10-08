import contextlib
import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

from orchestrator import pause_host_continuity as continuity, projects, standard
from orchestrator.core import Refusal, digest
from orchestrator.app_server_wake import load_binding
import test_pause_recovery as fixtures

NATIVE = "22222222-2222-4222-8222-222222222222"
CATALOG = "33333333-3333-4333-8333-333333333333"


class HostContinuityTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PauseRecoveryTest(); self.f.setUp()
        f = self.f
        f.host.binding["brains"][f.brain].update(projectId=NATIVE, catalogProjectId=CATALOG)
        f.metadata.thread["projectId"] = NATIVE
        with f.ledger.tx() as db:
            repo = f.ledger.get(db, "repos", "a"); repo["projectId"] = CATALOG
            f.ledger.put(db, "repos", "a", repo)
        projects.record(f.registry, {"schemaVersion": 2, "projects": [{"projectId": CATALOG,
            "projectKind": "local", "label": "Fixture", "hostId": "local", "path": str(f.fixture.repo),
            "isGitRepository": True}]}, 1)
        projects.bind(f.registry, "alpha", "local", CATALOG, projects.catalog(f.registry)["hash"])
        self.old_binding = copy.deepcopy(f.host.binding)
        self.old_preview, self.old, self.old_permit = f.failed_first()
        f.host.binding["endpoint"] = {"fixture": "new-reviewed-endpoint"}
        f.host.pause_recovery_prior_binding = copy.deepcopy(self.old_binding)
        # Bounded project identity reads are real contract checks with disposable
        # synthetic responses, not native qualification.
        self.project_root = str(f.fixture.repo)
        def rpc(method, params):
            if method == "project/read":
                f.metadata.calls.append((method, copy.deepcopy(params)))
                return {"project": {"id": NATIVE, "roots": [{"path": self.project_root}]}}
            return f.metadata.call(method, params)
        f.metadata._rpc = rpc
        self.endpoint = patch("orchestrator.native_project_assignment.validate_endpoint")
        self.endpoint.start()

    def tearDown(self):
        self.endpoint.stop(); self.f.tearDown()

    def test_signed_continuity_preview_is_read_only_and_preserves_original_bindings(self):
        f = self.f
        with contextlib.closing(f.ledger.connect()) as db: before = list(db.iterdump())
        with contextlib.closing(sqlite3.connect(f.registry.db)) as db: registry = list(db.iterdump())
        p = f.preview()
        proof = p["document"]["request"]["payload"]["hostContinuity"]
        self.assertEqual(proof["previousBinding"], self.old_binding)
        self.assertEqual(proof["candidateBinding"], f.host.binding)
        self.assertIn("separately reviewed replacement host", json.dumps(p))
        with contextlib.closing(f.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))
        with contextlib.closing(sqlite3.connect(f.registry.db)) as db: self.assertEqual(registry, list(db.iterdump()))
        self.assertEqual(f.host.sent, [])
        self.assertTrue(all(m in ("project/read", "thread/read", "thread/turns/list") for m, _ in f.metadata.calls))
        self.assertEqual(sum(m == "project/read" for m, _ in f.metadata.calls), 2)

    def test_confirmation_send_receipt_checkpoint_and_historical_replay(self):
        f = self.f; p = f.preview(); c = f.confirm(p)[0]["result"]
        proof = c["payload"]["hostContinuity"]
        self.assertEqual(standard.read(f.ledger)["run"]["pauseRecovery"]["priorAttempt"],
                         {"command": self.old, "permit": self.old_permit})
        f.host.send = fixtures.OwnedHost.send.__get__(f.host)
        f.notifier.notify(c["id"]); f.notifier.notify(c["id"])
        self.assertEqual(len(f.host.sent), 1)
        # Exercise the production same-connection send gate separately with a
        # retained claim, without creating a native send.
        with f.ledger.tx() as db:
            current = f.ledger.get(db, "commands", c["id"])
            accepted = copy.deepcopy(current); current["notification"]["status"] = "sending"
            f.ledger.put(db, "commands", c["id"], current)
        from orchestrator.pause_recovery import send_check
        send_check(f.ledger, f.host.binding, c["id"], f.metadata)
        self.project_root = str(f.fixture.root)
        with self.assertRaises(Refusal): send_check(f.ledger, f.host.binding, c["id"], f.metadata)
        self.project_root = str(f.fixture.repo)
        with f.ledger.tx() as db: f.ledger.put(db, "commands", c["id"], accepted)
        token = f.ledger.acquire(f.brain+":continuity")
        with self.assertRaises(Refusal): f.fixture.call("pause_recovery_receive", token=token, requestId=self.old["id"])
        f.fixture.call("pause_recovery_receive", token=token, requestId=c["id"])
        f.fixture.call("checkpoint", token=token, outcome="paused", summary="Synthetic continuity checkpoint",
                       brainObservedTokens=None, reasonCodes=["usage_evidence"])
        f.ledger.release(token, "Synthetic paused checkpoint")
        self.assertEqual(standard.read(f.ledger)["run"]["status"], "paused")
        self.assertEqual(f.retained(c["id"])["payload"]["hostContinuity"], proof)
        self.assertEqual(f.retained(self.old["id"])["notification"], self.old["notification"])
        before_calls = list(f.metadata.calls)
        with patch("orchestrator.assistant_journey.time.time", return_value=10**12):
            self.assertFalse(f.confirm(p)[1]); self.assertFalse(f.confirm(self.old_preview)[1])
        self.assertEqual(before_calls, f.metadata.calls)
        self.assertEqual(len(f.host.sent), 1)

    def test_only_transport_can_change_and_old_bytes_must_match(self):
        f = self.f; baseline = copy.deepcopy(f.host.binding)
        for key, value in (("cwd", str(f.fixture.root)), ("workspaceId", "other"),
                           ("projectId", CATALOG), ("catalogProjectId", NATIVE),
                           ("nativePolicy", {"sandbox": "danger-full-access", "approvalPolicy": "never", "codeMode": False})):
            f.host.binding = copy.deepcopy(baseline); f.host.binding["brains"][f.brain][key] = value
            with self.subTest(key=key), self.assertRaises(Refusal): f.preview()
        f.host.binding = baseline
        f.host.pause_recovery_prior_binding = None
        with self.assertRaises(Refusal): f.preview()
        f.host.pause_recovery_prior_binding = copy.deepcopy(self.old_binding)
        f.host.pause_recovery_prior_binding["endpoint"]["invented"] = True
        with self.assertRaises(Refusal): f.preview()
        f.host.pause_recovery_prior_binding = copy.deepcopy(self.old_binding)
        f.host.binding["brains"]["44444444-4444-4444-8444-444444444444"] = copy.deepcopy(baseline["brains"][f.brain])
        with self.assertRaises(Refusal): f.preview()

    def test_native_turn_project_root_and_catalog_drift_fence_continuity(self):
        f = self.f; p = f.preview()
        for field, value in (("id", "new-turn"), ("status", "interrupted"), ("completedAt", 2)):
            row = f.metadata.page["data"][0]; saved = row[field]; row[field] = value
            with self.subTest(field=field), self.assertRaises(Refusal): f.preview()
            with self.assertRaises(Refusal): f.confirm(p)
            row[field] = saved
        f.metadata.thread["status"] = {"type": "active"}
        with self.assertRaises(Refusal): f.preview()
        f.metadata.thread["status"] = {"type": "notLoaded"}
        self.project_root = str(f.fixture.root)
        with self.assertRaises(Refusal): f.preview()
        self.project_root = str(f.fixture.repo)
        projects.record(f.registry, {"schemaVersion": 2, "projects": []}, 2)
        with self.assertRaises(Refusal): f.confirm(p)

    def test_signed_proof_tampering_and_post_preview_endpoint_drift_refuse(self):
        f = self.f; p = f.preview()
        bad = copy.deepcopy(p)
        bad["document"]["request"]["payload"]["hostContinuity"]["candidateBinding"]["endpoint"]["changed"] = True
        with self.assertRaises(Refusal): f.confirm(bad)
        f.host.binding["endpoint"]["changed"] = True
        with self.assertRaises(Refusal): f.confirm(p)
        f.host.binding["endpoint"].pop("changed")
        f.confirm(p)
        self.assertFalse(f.state()["standard"]["pauseRecovery"]["available"])
        with self.assertRaises(Refusal): f.preview()

    def test_actual_bridge_rechecks_continuity_on_both_sides_of_resume(self):
        from orchestrator.app_server_wake import AppServerWake
        from test_app_server_wake import FakeThread
        f = self.f; c = f.confirm(f.preview())[0]["result"]
        with f.ledger.tx() as db:
            command = f.ledger.get(db, "commands", c["id"])
            command["notification"] = {"status": "sending", "brainId": f.brain,
                "wakeId": digest({"commandId": c["id"]})}
            f.ledger.put(db, "commands", c["id"], command)
        baseline = f.ledger.snapshot()["meta"]
        for drift in (None, "project", "turn", "stop"):
            with self.subTest(drift=drift):
                with f.ledger.tx() as db:
                    f.ledger.put(db, "meta", 1, baseline)
                    f.ledger.put(db, "commands", c["id"], copy.deepcopy(command))
                proxy = fixtures.Metadata(f.brain, str(f.fixture.repo))
                proxy.thread["projectId"] = NATIVE
                def rpc(method, params):
                    if method in ("thread/read", "thread/turns/list"):
                        return proxy.call(method, params)
                    proxy.calls.append((method, copy.deepcopy(params)))
                    if method == "project/read":
                        return {"project": {"id": NATIVE, "roots": [{"path": proxy.root}]}}
                    if method == "thread/resume":
                        self.assertIs(params["excludeTurns"], True)
                        proxy.thread.update(historyMode="paginated", status={"type": "idle"})
                        if drift == "project": proxy.root = str(f.fixture.root)
                        if drift == "turn": proxy.page["data"][0]["id"] = "new-turn"
                        if drift == "stop":
                            with f.ledger.tx() as db:
                                meta = f.ledger.get(db, "meta", 1)
                                meta["brainControl"] = {"desired": "stopped"}
                                f.ledger.put(db, "meta", 1, meta)
                        return {"thread": copy.deepcopy(proxy.thread)}
                    if method == "turn/start": return {"turn": {"id": "synthetic-turn"}}
                    raise AssertionError(method)
                proxy.root = str(f.fixture.repo); proxy._rpc = rpc
                proxy.__enter__ = lambda: proxy
                proxy.__exit__ = lambda *_: None
                wake = AppServerWake(f.host.binding, f.ledger, self.old_binding)
                with patch.object(wake, "configured", return_value=True), \
                     patch("orchestrator.app_server_wake.WakeProxy", return_value=proxy), \
                     patch("orchestrator.app_server_wake.threading.Thread", FakeThread):
                    result = wake.send(f.brain, "fixed checkpoint pointer", c["id"])
                wake.close()
                methods = [method for method, _ in proxy.calls]
                self.assertEqual(result["status"], "unavailable" if drift else "accepted")
                self.assertEqual(methods.count("turn/start"), 0 if drift else 1)
                resume = methods.index("thread/resume")
                self.assertIn("project/read", methods[:resume])
                if drift != "stop": self.assertIn("project/read", methods[resume+1:])
                if not drift: self.assertEqual(methods.count("project/read"), 4)

    def test_historical_binding_is_private_and_never_a_connection_target(self):
        path = self.f.fixture.root / "old-binding.json"
        path.write_text(json.dumps(self.old_binding)); path.chmod(0o600)
        with patch("orchestrator.app_server_wake.validate_endpoint", side_effect=Refusal("obsolete endpoint")) as check:
            self.assertEqual(continuity.load_previous(path), self.old_binding)
            check.assert_not_called()
            with self.assertRaises(Refusal): load_binding(path)
        path.chmod(0o644)
        with self.assertRaises(Refusal): continuity.load_previous(path)

    def test_continuity_cannot_override_uncertain_or_started_original_attempt(self):
        f = self.f
        for change in ({"status": "uncertain"}, {"nativeTurnId": "started"},
                       {"nativeDelivery": "owned_turn_start"}, {"nativeThreadObservation": {}},
                       {"nativeFailure": {"version": 1, "stage": "turn_start", "reason": "rpc_error",
                                          "resumeAttempted": True, "turnStartAttempted": True}}):
            row = copy.deepcopy(self.old); row["notification"].update(change)
            with f.ledger.tx() as db: f.ledger.put(db, "commands", row["id"], row)
            calls = list(f.metadata.calls)
            with self.subTest(change=change), self.assertRaises(Refusal): f.preview()
            self.assertEqual(f.metadata.calls, calls)
        with f.ledger.tx() as db: f.ledger.put(db, "commands", self.old["id"], self.old)

    def test_continuity_rollback_catalog_and_retained_proof_refuse(self):
        f = self.f; p = f.preview(); put = f.ledger.put
        def interrupted(db, table, ident, value):
            if table == "commands" and ident == p["document"]["id"]: raise RuntimeError("Synthetic interruption")
            return put(db, table, ident, value)
        with patch.object(f.ledger, "put", side_effect=interrupted), self.assertRaises(RuntimeError): f.confirm(p)
        self.assertEqual(f.retained(self.old["id"]), self.old)
        self.assertEqual(standard.read(f.ledger)["run"]["pauseRecovery"], self.old_permit)
        c = f.confirm(p)[0]["result"]
        with f.ledger.tx() as db:
            broken = copy.deepcopy(c); broken["payload"]["hostContinuity"]["catalogHash"] = "0"*64
            f.ledger.put(db, "commands", c["id"], broken)
        f.notifier.notify(c["id"])
        self.assertNotIn("notification", f.retained(c["id"]))
        self.assertEqual(f.host.sent, [])
        token = f.ledger.acquire(f.brain+":broken-proof")
        with self.assertRaises(Refusal): f.fixture.call("pause_recovery_receive", token=token, requestId=c["id"])
        f.ledger.release(token, "Synthetic broken proof; no receipt")

    def test_snapshot_and_health_polling_never_inspect_continuity(self):
        f = self.f; f.metadata.calls.clear()
        before = standard.read(f.ledger)["run"]
        for _ in range(3): f.state()
        self.assertEqual(f.metadata.calls, [])
        self.assertEqual(f.host.sent, [])
        self.assertEqual(before, standard.read(f.ledger)["run"])

    def test_without_owned_transport_the_historical_option_refuses(self):
        from orchestrator.notification import BrainNotifier
        with self.assertRaises(ValueError): BrainNotifier(self.f.ledger, pause_recovery_prior_binding=self.old_binding)


if __name__ == "__main__": unittest.main()
