import contextlib
import copy
import json
import time
import unittest
from unittest.mock import patch

from orchestrator import pause_receipt_recovery as recovery, standard
from orchestrator.app_server_wake import NATIVE_APPROVAL_POLICY
from orchestrator.assistant_actions import catalog
from orchestrator.core import Refusal, digest
from orchestrator.development_help import plan
import test_pause_recovery


class Metadata:
    def __init__(self, brain, cwd):
        self.calls = []
        self.thread = {"id": brain, "projectId": "native-project", "cwd": cwd,
                       "status": {"type": "notLoaded"}}
        self.page = {"data": [{"id": "pause-turn", "status": "completed", "completedAt": 1}], "nextCursor": None}
        self.terminals = {"data": [], "nextCursor": None}

    def _rpc(self, method, params):
        self.calls.append((method, copy.deepcopy(params)))
        if method == "project/read":
            return {"project": {"id": "native-project", "roots": [{"path": self.thread["cwd"]}]}}
        if method == "thread/read": return copy.deepcopy({"thread": self.thread})
        if method == "thread/turns/list": return copy.deepcopy(self.page)
        if method == "thread/backgroundTerminals/list": return copy.deepcopy(self.terminals)
        raise AssertionError(method)


class PauseReceiptRecoveryTest(unittest.TestCase):
    def setUp(self):
        # Reuse the existing disposable standard-project setup, not its tests.
        self.base = test_pause_recovery.PauseRecoveryTest()
        self.base.setUp()
        self.fixture, self.ledger, self.registry = self.base.fixture, self.base.ledger, self.base.registry
        self.brain, self.host, self.notifier = self.base.brain, self.base.host, self.base.notifier
        self.proposals = self.base.proposals
        self.metadata = Metadata(self.brain, str(self.fixture.repo))
        self.base.factory.return_value.__enter__.return_value = self.metadata
        with self.ledger.tx() as db:
            original = self.ledger.get(db, "commands", self.base.pause["id"])
            original["notification"].update(status="accepted", nativeDelivery="owned_turn_start",
                hostRunId=self.base.before["id"], hostBindingHash=digest(self.host.binding),
                nativeTurnId="pause-turn", nativeTurnStatus="completed",
                nativeThreadObservation={"version": 1, "rootThreadId": self.brain, "nativeTurnId": "pause-turn",
                    "streamStatus": "closed", "events": [], "monitoringEndedAt": time.time()-1,
                    "complete": False, "gaps": ["owned_stream_not_exhaustive"]},
                nativeResumeProfile={"version": 1, "brainId": self.brain, "commandId": original["id"],
                    "nativeTurnId": "pause-turn", "bindingHash": digest(self.host.binding),
                    "requested": NATIVE_APPROVAL_POLICY.copy(), "resumeAcknowledged": True})
            self.ledger.put(db, "commands", original["id"], original)
            meta = self.ledger.get(db, "meta", 1)
            meta["standardRun"].update(brainObservedTokens=719, brainUsageCoverage="observed_partial",
                usageHighWater=719,
                expiresAt=time.time()-3600)
            self.ledger.put(db, "meta", 1, meta)
        self.original = self.base.retained(original["id"])
        self.before = standard.read(self.ledger)["run"]

    def tearDown(self): self.base.tearDown()

    def preview(self):
        state = self.base.state()
        return self.proposals.prepare(catalog(state, {})["phase_pause_receipt_recovery"], state, "session")

    def confirm(self, preview): return self.base.confirm(preview)

    def claimed(self, command):
        # Simulate the existing notifier's committed claim, then use the actual
        # boundary checks. No fixture supplies guessed zero terminal coverage.
        with self.ledger.tx() as db:
            current = self.ledger.get(db, "commands", command["id"])
            current["notification"] = {"status": "sending", "brainId": self.brain,
                "wakeId": digest({"commandId": command["id"]})}
            self.ledger.put(db, "commands", current["id"], current)
        recovery.send_check(self.ledger, self.host.binding, command["id"], self.metadata)

    def loaded(self, command):
        self.metadata.thread["status"]["type"] = "idle"
        recovery.send_check(self.ledger, self.host.binding, command["id"], self.metadata, require_loaded=True)

    def test_preview_read_only_unloaded_is_unknown_and_metadata_has_no_transcripts(self):
        self.metadata.page["data"][0]["items"] = [{"text": "PRIVATE transcript"}]
        with contextlib.closing(self.ledger.connect()) as db: before = list(db.iterdump())
        preview = self.preview()
        with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))
        o = preview["document"]["request"]["payload"]["observation"]
        self.assertIsNone(o["trackedTerminals"])
        self.assertEqual(o["terminalCoverage"], "unknown")
        self.assertNotIn("PRIVATE", json.dumps(preview))
        self.assertFalse(self.host.sent)
        self.assertNotIn("thread/backgroundTerminals/list", [m for m, _ in self.metadata.calls])
        self.assertEqual(plan(self.base.state())["key"], "phase_pause_receipt_recovery")
        self.assertTrue(standard.read(self.ledger)["pauseReceiptRecovery"]["available"])

    def test_loaded_boundary_is_required_and_unknown_or_nonempty_terminals_refuse(self):
        command = self.confirm(self.preview())[0]["result"]
        self.claimed(command)
        with self.assertRaises(Refusal):
            recovery.send_check(self.ledger, self.host.binding, command["id"], self.metadata, require_loaded=True)
        self.metadata.thread["status"]["type"] = "idle"
        for terminals in (None, {}, {"data": [], "nextCursor": "more"}, {"data": [{"id": "active"}], "nextCursor": None}):
            self.metadata.terminals = terminals
            with self.subTest(terminals=terminals), self.assertRaises(Refusal): self.loaded(command)
        self.metadata.terminals = {"data": [], "nextCursor": None}
        self.loaded(command)
        o = self.base.retained(command["id"])["notification"]["receiptRecoveryObservation"]
        self.assertEqual(o["trackedTerminals"], 0)
        self.assertEqual(o["historicalTerminalCoverage"], "unknown")
        self.assertEqual(o["effectOutcome"], "unknown")
        with self.assertRaises(Refusal): self.loaded(command)

    def test_dedicated_receive_checkpoint_and_release_preserve_original_history_and_usage(self):
        preview = self.preview(); command = self.confirm(preview)[0]["result"]
        self.claimed(command)
        token = self.ledger.acquire(self.brain+":receipt")
        for operation, kwargs in (("receive", {}), ("pause_receipt_recovery_receive", {"requestId": command["id"]}),
                                  ("checkpoint", {"outcome": "paused", "summary": "Not yet received", "brainObservedTokens": None})):
            with self.subTest(operation=operation), self.assertRaises(Refusal): self.fixture.call(operation, token=token, **kwargs)
        self.ledger.release(token, "Pre-receipt test")
        self.loaded(command)
        token = self.ledger.acquire(self.brain+":receipt")
        self.fixture.call("pause_receipt_recovery_receive", token=token, requestId=command["id"])
        self.fixture.call("pause_receipt_recovery_receive", token=token, requestId=command["id"])
        for outcome, usage in (("completed", None), ("blocked", None), ("paused", 0), ("paused", 800)):
            with self.subTest(outcome=outcome, usage=usage), self.assertRaises(Refusal):
                self.fixture.call("checkpoint", token=token, outcome=outcome, summary="No fabricated success", brainObservedTokens=usage)
        self.fixture.call("checkpoint", token=token, outcome="paused", summary="Expired; historical effects and usage coverage unknown",
                          brainObservedTokens=None, reasonCodes=["duration", "usage_evidence"])
        self.ledger.release(token, "Stopped checkpoint")
        run = standard.read(self.ledger)["run"]
        self.assertEqual(run["status"], "paused")
        for key in ("limits", "expiresAt", "brainAllowance", "brainObservedTokens", "brainUsageCoverage", "usageHighWater", "tasks", "merges"):
            self.assertEqual(self.before.get(key), run.get(key), key)
        original = self.base.retained(self.original["id"])
        for key in ("notification", "payload", "fingerprint", "createdAt"):
            self.assertEqual(original.get(key), self.original.get(key), key)
        self.assertEqual(original["status"], "completed")
        self.assertFalse(run["checkpoint"]["taskTreeComplete"])
        self.assertEqual(run["checkpoint"]["historicalTerminalCoverage"], "unknown")
        self.assertIsNone(self.ledger.snapshot()["meta"]["controller"])
        self.assertFalse(self.confirm(preview)[1])
        self.assertFalse(standard.read(self.ledger)["pauseReceiptRecovery"]["available"])

    def test_notifier_fixed_restricted_pointer_is_not_overwritten_and_never_resends(self):
        preview = self.preview(); command = self.confirm(preview)[0]["result"]
        self.notifier.notify(command["id"]); self.notifier.notify(command["id"])
        self.assertEqual(len(self.host.sent), 1)
        message = self.host.sent[0][1]
        self.assertIn("pause_receipt_recovery_receive", message)
        self.assertIn("brainObservedTokens null", message)
        self.assertIn("reasons only when observed", message)
        self.assertNotIn("Explain the expired duration", message)
        self.assertNotIn("Keep supervising registered tasks", message)
        self.assertNotIn("standard-host-inspect", message)
        self.assertEqual(self.base.retained(self.original["id"]), self.original)
        self.assertFalse(self.confirm(preview)[1])

    def test_signature_session_false_assent_and_scope_drift_refuse(self):
        preview = self.preview()
        with self.assertRaises(Refusal): self.base.confirm(preview, "another-session")
        bad = copy.deepcopy(preview); bad["document"]["request"]["payload"]["bindingHash"] = "0"*64
        with self.assertRaises(Refusal): self.confirm(bad)
        with self.assertRaises(Refusal): self.proposals.confirm(self.ledger, {"proposal": preview, "confirmed": False}, "session")
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["standardRun"]["expiresAt"] += 1
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal): self.confirm(preview)
        self.assertFalse(self.host.sent)

    def test_completed_turn_identity_and_native_profile_are_exact(self):
        baseline = self.base.state()
        variants = [{"status": "uncertain"}, {"nativeTurnStatus": "inProgress"},
                    {"nativeTurnStatus": "interrupted"}, {"nativeApprovals": [{"status": "unknown"}]},
                    {"nativeResumeProfile": {}}, {"nativeDelivery": "desktop_queue_only"},
                    {"nativeThreadObservation": {"streamStatus": "open"}}]
        for changes in variants:
            state = copy.deepcopy(baseline)
            next(c for c in state["commands"] if c["id"] == self.original["id"])["notification"].update(changes)
            with self.subTest(changes=changes): self.assertFalse(recovery.availability(state)["available"])
        for field, value in (("controller", {}), ("brainControl", {"desired": "stopped"}),
                             ("runner", {"status": "unknown"}), ("admissionBinding", {})):
            state = copy.deepcopy(baseline); state["meta"][field] = value or {"exists": True}
            with self.subTest(field=field): self.assertFalse(recovery.availability(state)["available"])
        self.metadata.page["data"][0]["id"] = "later-turn"
        with self.assertRaises(Refusal): self.preview()
        self.metadata.page["data"][0]["id"] = "pause-turn"
        self.host.binding["endpoint"]["replacement"] = True
        with self.assertRaises(Refusal): self.preview()

    def test_failed_or_expired_attempt_permanently_retains_one_shot(self):
        preview = self.preview(); command = self.confirm(preview)[0]["result"]
        self.host.send = lambda *args: {"status": "unavailable", "detail": "No verified loaded tracker"}
        self.notifier.notify(command["id"])
        self.notifier.notify(command["id"])
        self.assertFalse(standard.read(self.ledger)["pauseReceiptRecovery"]["available"])
        with self.assertRaises(Refusal): self.preview()
        with patch("orchestrator.assistant_journey.time.time", return_value=time.time()+10000):
            self.assertFalse(self.confirm(preview)[1])
        self.assertEqual(self.base.retained(self.original["id"]), self.original)

    def test_send_boundary_drift_stop_and_other_pending_requests_fence(self):
        command = self.confirm(self.preview())[0]["result"]
        self.claimed(command)
        self.metadata.thread["status"]["type"] = "idle"
        self.metadata.page["data"][0]["completedAt"] = 2
        with self.assertRaises(Refusal): self.loaded(command)
        self.metadata.page["data"][0]["completedAt"] = 1
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["brainControl"] = {"desired": "stopped"}
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal): self.loaded(command)


    def bridge(self, mode):
        from orchestrator.app_server_wake import AppServerWake
        from test_app_server_wake import FakeThread
        command = self.confirm(self.preview())[0]["result"]
        self.claimed(command)
        fixture = self
        class Proxy(Metadata):
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def _rpc(self, method, params):
                if method == "thread/resume":
                    self.calls.append((method, copy.deepcopy(params)))
                    fixture.assertEqual(params["approvalPolicy"], "on-request")
                    fixture.assertEqual(params["sandbox"], "workspace-write")
                    fixture.assertIs(params["config"]["features"]["code_mode"]["enabled"], False)
                    fixture.assertIs(params["excludeTurns"], True)
                    self.thread["status"]["type"] = "idle"
                    if mode == "unknown": self.terminals = None
                    if mode == "busy": self.terminals = {"data": [{"id": "running"}], "nextCursor": None}
                    if mode == "drift": self.page["data"][0]["id"] = "different-turn"
                    if mode == "stop":
                        with fixture.ledger.tx() as db:
                            meta = fixture.ledger.get(db, "meta", 1); meta["brainControl"] = {"desired": "stopped"}
                            fixture.ledger.put(db, "meta", 1, meta)
                    return {"thread": copy.deepcopy(self.thread)}
                if method == "turn/start":
                    self.calls.append((method, copy.deepcopy(params)))
                    return {"turn": {"id": "receipt-turn"}}
                return super()._rpc(method, params)
        proxy = Proxy(self.brain, str(self.fixture.repo))
        wake = AppServerWake(self.host.binding, self.ledger)
        with patch.object(wake, "configured", return_value=True), \
             patch("orchestrator.app_server_wake.WakeProxy", return_value=proxy), \
             patch("orchestrator.app_server_wake.threading.Thread", FakeThread):
            result = wake.send(self.brain, "receipt-only fixed pointer", command["id"])
        wake.close()
        methods = [m for m, _ in proxy.calls]
        self.assertEqual(methods.count("thread/resume"), 1)
        self.assertEqual(methods.count("turn/start"), 1 if mode == "ok" else 0)
        self.assertEqual(result["status"], "accepted" if mode == "ok" else "unavailable")
        self.assertEqual(self.base.retained(self.original["id"]), self.original)
        self.assertEqual(standard.read(self.ledger)["run"]["usageHighWater"], 719)

    def test_bridge_inspection_load_proves_tracker_before_only_turn_start(self): self.bridge("ok")
    def test_bridge_unknown_tracker_never_starts_turn(self): self.bridge("unknown")
    def test_bridge_busy_tracker_never_starts_turn(self): self.bridge("busy")
    def test_bridge_changed_turn_never_starts_turn(self): self.bridge("drift")
    def test_bridge_racing_brain_stop_never_starts_turn(self): self.bridge("stop")

    def test_other_pending_worker_queue_decision_and_strict_scope_refuse(self):
        baseline = self.base.state()
        for key, value in (("workers", [{"id": "unknown"}]), ("queue", [{"id": "queued"}]),
                           ("decisions", [{"status": "answered"}])):
            state = copy.deepcopy(baseline); state[key] = value
            with self.subTest(key=key): self.assertFalse(recovery.availability(state)["available"])
        state = copy.deepcopy(baseline); state["repositories"][0]["policyProfile"] = "harness"
        self.assertFalse(recovery.availability(state)["available"])
        state = copy.deepcopy(baseline); state["commands"].append({"id": "another", "kind": "reconcile", "status": "queued"})
        self.assertFalse(recovery.availability(state)["available"])

    def test_concurrent_confirmation_retains_one_request_and_read_replay(self):
        import concurrent.futures
        preview = self.preview()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.confirm(preview), range(2)))
        self.assertEqual(sum(first for _, first in results), 1)
        self.assertEqual(results[0][0]["result"]["id"], results[1][0]["result"]["id"])
        self.assertEqual(sum(c["kind"] == recovery.KIND for c in self.ledger.snapshot()["commands"]), 1)

    def test_authenticated_http_poll_preview_csrf_confirmation_and_replay(self):
        import http.client
        import threading
        from orchestrator.server import Dashboard
        server = Dashboard(self.ledger, 0, registry=self.registry, runtime_root=self.fixture.root,
                           inference_env=self.fixture.root/"missing.env")
        server.runtime_for("alpha").notifier.app_server = self.host
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        def request(path, body=None, auth=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST" if body is not None else "GET", path,
                         json.dumps(body) if body is not None else None,
                         {"Content-Type": "application/json", "Origin": server.origin, **(auth or {})})
            response = conn.getresponse()
            value = response.status, dict(response.getheaders()), json.loads(response.read()); conn.close()
            return value
        try:
            path = "/api/workspaces/alpha"
            self.assertEqual(request(path+"/assistant/help")[0], 401)
            _, headers, _ = request("/api/login", {"token": server.bootstrap})
            auth = {"Cookie": headers["Set-Cookie"].split(";")[0]}
            _, _, session = request(path+"/session", auth=auth); auth["X-CSRF-Token"] = session["csrf"]
            with contextlib.closing(self.ledger.connect()) as db: before = list(db.iterdump())
            view = request(path+"/assistant/help", auth=auth)[2]
            self.assertEqual(view["key"], "phase_pause_receipt_recovery")
            self.assertFalse(self.metadata.calls, "Polling never collects native evidence")
            with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))
            status, _, preview = request(path+"/assistant/preview", {"key": "phase_pause_receipt_recovery"}, auth)
            self.assertEqual(status, 200, preview)
            body = {"proposal": preview, "confirmed": True}
            self.assertEqual(request(path+"/assistant/confirm", body, {**auth, "X-CSRF-Token": "wrong"})[0], 403)
            status, _, result = request(path+"/assistant/confirm", body, auth)
            self.assertEqual(status, 200, result)
            self.assertEqual(result["result"]["kind"], recovery.KIND)
            self.assertEqual(request(path+"/assistant/confirm", body, auth)[0], 200)
            self.assertEqual(len(self.host.sent), 1)
            self.assertEqual(self.base.retained(self.original["id"]), self.original)
        finally:
            server.shutdown(); server.server_close(); worker.join()


if __name__ == "__main__": unittest.main()
