import copy
import json
import threading
import time
import unittest
from unittest.mock import patch

from orchestrator import turn_recovery as recovery
from orchestrator.app_server_wake import NATIVE_APPROVAL_POLICY
from orchestrator.core import Refusal, digest
from orchestrator.native_read_client import ReadProxy
import test_native_project_assignment as fixture
import test_server
from test_native_project_assignment import NativeProxy, BRAIN, PROJECT, OTHER


TURN = "44444444-4444-4444-8444-444444444444"
COMMAND = "55555555-5555-4555-8555-555555555555"


class Proxy(NativeProxy):
    turn_status = "inProgress"
    turns = None
    terminals = None
    interrupts = 0
    lost_response = False
    end_after_interrupt = True
    unavailable = False
    on_interrupt = None
    on_enter = None
    ended_activity = "idle"

    def __init__(self, endpoint, scope, turn_id):
        super().__init__(endpoint)
        self.scope, self.turn_id, self.interrupt_permit = scope, turn_id, False

    def __enter__(self):
        if type(self).on_enter:
            type(self).on_enter()
        if self.unavailable:
            raise OSError("Reviewed host offline")
        return self

    def _rpc(self, method, params):
        if method == "thread/read":
            type(self).status = "active" if self.turn_status == "inProgress" else self.ended_activity
        if method in ("project/read", "thread/read"):
            return super()._rpc(method, params)
        self.calls.append((method, params))
        if method == "thread/turns/list":
            return self.turns or {"data": [{"id": TURN, "status": self.turn_status}], "nextCursor": None}
        if method == "thread/backgroundTerminals/list":
            return self.terminals
        if method == "turn/interrupt":
            assert self.interrupt_permit
            self.interrupt_permit = False
            type(self).interrupts += 1
            if type(self).on_interrupt:
                type(self).on_interrupt()
            if self.end_after_interrupt:
                type(self).turn_status = "interrupted"
            if self.lost_response:
                raise Refusal("Lost cancellation response")
            return {}
        raise AssertionError(method)


class TurnRecoveryTest(unittest.TestCase):
    def setUp(self):
        fixture.NativeProjectAssignmentTest.setUp(self)
        self.ledger.workspace_id = "pilot"
        self.controls = recovery.TurnRecoveryControls()
        self.wake = type("Wake", (), {"binding": self.binding, "idle": True,
                                     "orphan_recovery_idle": lambda w: w.idle})()
        self.patches += [patch.object(recovery, "RecoveryProxy", Proxy), patch.object(recovery, "validate_endpoint")]
        for item in self.patches[3:]:
            item.start()
        Proxy.project_id, Proxy.native_project_id = PROJECT, PROJECT
        Proxy.cwd, Proxy.project_roots = str(self.repo), [str(self.repo)]
        Proxy.turn_status, Proxy.turns = "inProgress", None
        Proxy.terminals = {"data": [], "nextCursor": None}
        Proxy.interrupts, Proxy.calls, Proxy.project_reads = 0, [], 0
        Proxy.lost_response, Proxy.end_after_interrupt, Proxy.unavailable = False, True, False
        Proxy.on_interrupt, Proxy.on_enter, Proxy.on_project_read = None, None, None
        Proxy.ended_activity = "idle"
        now = time.time()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta.update(schemaVersion=4, paused=True,
                        controller={"owner": BRAIN + ":pilot-" + COMMAND, "token": "fixture-private", "acquiredAt": now - 10},
                        standardRun={"protocol": recovery.PROTOCOL, "id": "run-a", "brainId": BRAIN,
                                     "phaseId": "phase-a", "status": "running", "revision": 1,
                                     "tasks": [], "merges": [], "expiresAt": now - 2,
                                     "usageHighWater": {"brainTokens": 17, "totalTokens": 19, "coverage": "partial"}})
            self.ledger.put(db, "meta", 1, meta)
            note = {"brainId": BRAIN, "status": "accepted", "attemptedAt": now - 9,
                    "nativeDelivery": "owned_turn_start", "hostRunId": "run-a", "hostBindingHash": digest(self.binding),
                    "nativeTurnId": TURN, "nativeTurnStatus": "native_attention_required",
                    "nativeThreadObservation": {"version": 1, "rootThreadId": BRAIN, "events": [],
                                                "streamStatus": "closed", "monitoringEndedAt": now - 1},
                    "nativeResumeProfile": {"version": 1, "brainId": BRAIN, "commandId": COMMAND,
                                            "nativeTurnId": TURN, "bindingHash": digest(self.binding),
                                            "requested": NATIVE_APPROVAL_POLICY, "resumeAcknowledged": True}}
            self.ledger.put(db, "commands", COMMAND, {"id": COMMAND, "kind": "standard_play", "status": "completed",
                                                       "notification": note, "createdAt": now - 9})

    def tearDown(self):
        fixture.NativeProjectAssignmentTest.tearDown(self)

    def preview(self):
        return self.controls.preview(self.registry, self.ledger, self.wake, {"commandId": COMMAND}, "session")

    def confirm(self, doc):
        return self.controls.confirm(self.registry, self.ledger, self.wake,
                                     {"proposal": doc, "confirmed": True}, "session")

    def reconcile(self):
        return self.controls.reconcile(self.registry, self.ledger, self.wake, {"commandId": COMMAND})

    def change(self, fn):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            fn(meta)
            self.ledger.put(db, "meta", 1, meta)

    def test_get_and_preview_are_read_only_no_hidden_native_effect(self):
        before = recovery.saved_state(self.ledger)
        self.assertEqual(recovery.inspect(self.ledger, self.wake)["status"], "review_available")
        self.assertEqual(Proxy.calls, [])
        doc = self.preview()
        self.assertEqual(doc["document"]["action"], "cancel_then_reconcile")
        self.assertEqual(before, recovery.saved_state(self.ledger))
        self.assertFalse(doc["document"]["observation"]["taskTreeComplete"])
        self.assertNotIn("fixture-private", str(doc))
        self.assertTrue(all(m in ("project/read", "thread/read", "thread/turns/list", "thread/backgroundTerminals/list")
                            for m, _ in Proxy.calls))

    def test_exact_interrupt_once_then_recover_controller_preserving_run_evidence(self):
        before = self.ledger.snapshot()
        doc = self.preview()
        self.assertEqual(self.confirm(doc)["status"], "controller_recovered")
        after = self.ledger.snapshot()
        self.assertIsNone(after["meta"]["controller"])
        self.assertTrue(after["meta"]["paused"])
        self.assertEqual(after["meta"]["standardRun"]["status"], "stopping")
        for key in ("usageHighWater", "expiresAt", "phaseId", "tasks", "merges"):
            self.assertEqual(before["meta"]["standardRun"][key], after["meta"]["standardRun"][key])
        self.assertNotIn("checkpoint", after["meta"]["standardRun"])
        original = copy.deepcopy(after["commands"][0]); original["notification"].pop("turnRecovery")
        self.assertEqual(original, before["commands"][0])
        self.assertEqual(Proxy.interrupts, 1)
        from orchestrator.native_approval_controls import _closed_attention
        self.assertEqual(_closed_attention(after, BRAIN)["status"], "turn_recovered")
        calls = list(Proxy.calls)
        self.assertEqual(self.confirm(doc)["status"], "controller_recovered")
        self.assertEqual(self.reconcile()["status"], "controller_recovered")
        self.assertEqual(calls, Proxy.calls, "HTTP replay never reconnects or repeats cancellation")
        self.assertIn(("turn/interrupt", {"threadId": BRAIN, "turnId": TURN}), calls)

    def test_already_ended_turn_does_not_interrupt(self):
        Proxy.turn_status = "interrupted"
        doc = self.preview()
        self.assertEqual(doc["document"]["action"], "reconcile_ended_turn")
        self.assertEqual(self.confirm(doc)["delivery"], "not_needed")
        self.assertEqual(Proxy.interrupts, 0)

    def test_lost_response_keeps_ownership_until_separate_read_only_end_check(self):
        Proxy.end_after_interrupt, Proxy.lost_response = False, True
        doc = self.preview()
        result = self.confirm(doc)
        self.assertEqual((result["status"], result["delivery"]), ("awaiting_end", "unknown"))
        self.assertIsNotNone(self.ledger.snapshot()["meta"]["controller"])
        self.assertEqual(Proxy.interrupts, 1)
        self.confirm(doc); self.reconcile()
        self.assertEqual(Proxy.interrupts, 1)
        Proxy.turn_status = "interrupted"
        self.assertEqual(self.reconcile()["status"], "controller_recovered")
        self.assertEqual(Proxy.interrupts, 1)

    def test_host_failure_after_claim_never_retries(self):
        Proxy.on_interrupt = lambda: setattr(Proxy, "unavailable", True)
        result = self.confirm(self.preview())
        self.assertEqual(result["status"], "awaiting_end")
        self.assertIsNotNone(self.ledger.snapshot()["meta"]["controller"])
        self.assertEqual(self.reconcile()["status"], "awaiting_end")
        Proxy.unavailable = False
        self.assertEqual(self.reconcile()["status"], "controller_recovered")
        self.assertEqual(Proxy.interrupts, 1)

    def test_restart_or_expired_review_cannot_send(self):
        doc = self.preview()
        with self.assertRaises(Refusal):
            recovery.TurnRecoveryControls().confirm(self.registry, self.ledger, self.wake,
                                                   {"proposal": doc, "confirmed": True}, "session")
        with patch.object(recovery.time, "time", return_value=doc["document"]["expiresAt"] + 1):
            with self.assertRaises(Refusal): self.confirm(doc)
        self.assertEqual(Proxy.interrupts, 0)

    def test_session_confirmation_and_tamper_are_exact(self):
        doc = self.preview()
        for body, session in (({"proposal": doc, "confirmed": False}, "session"),
                              ({"proposal": doc, "confirmed": True}, "other")):
            with self.assertRaises(Refusal):
                self.controls.confirm(self.registry, self.ledger, self.wake, body, session)
        doc["document"]["turnId"] = OTHER
        with self.assertRaises(Refusal): self.confirm(doc)
        self.assertEqual(Proxy.interrupts, 0)

    def test_changed_endpoint_and_catalog_project_fail_before_claim(self):
        doc = self.preview()
        self.binding["endpoint"] = {"fixture": "replacement"}
        with self.assertRaises(Refusal): self.confirm(doc)
        self.assertEqual(Proxy.interrupts, 0)

    def test_scope_or_controller_change_during_inspection_blocks_claim(self):
        doc = self.preview()
        Proxy.on_enter = lambda: self.change(lambda meta: meta.update(controller={"owner": "other", "token": "new"}))
        with self.assertRaises(Refusal): self.confirm(doc)
        self.assertEqual(Proxy.interrupts, 0)

    def test_new_activity_after_claim_cannot_clear_new_controller(self):
        Proxy.end_after_interrupt = False
        self.confirm(self.preview())
        self.change(lambda meta: meta.update(controller={"owner": BRAIN + ":new", "token": "new"}))
        Proxy.turn_status = "interrupted"
        self.assertEqual(self.reconcile()["status"], "awaiting_end")
        self.assertEqual(recovery.saved_state(self.ledger)["meta"]["controller"]["token"], "new")
        self.assertEqual(Proxy.interrupts, 1)

    def test_unknown_or_active_terminals_and_foreign_turn_fence(self):
        Proxy.turn_status, Proxy.ended_activity = "interrupted", "notLoaded"
        with self.assertRaises(Refusal): self.preview()
        Proxy.turn_status, Proxy.ended_activity = "inProgress", "idle"
        for page in ({}, {"data": []}, {"data": [], "nextCursor": "more"},
                     {"data": [{"processId": "42"}], "nextCursor": None}):
            Proxy.terminals = page
            with self.subTest(page=page), self.assertRaises(Refusal): self.preview()
        Proxy.terminals = {"data": [], "nextCursor": None}
        Proxy.turns = {"data": [{"id": OTHER, "status": "inProgress"}], "nextCursor": None}
        with self.assertRaises(Refusal): self.preview()
        self.assertEqual(Proxy.interrupts, 0)

    def test_active_observer_unknown_child_or_approval_intent_fences(self):
        self.wake.idle = False
        with self.assertRaises(Refusal): self.preview()
        self.wake.idle = True
        for key, value in (("nativeApprovals", [{"status": "uncertain"}]),
                           ("nativeThreadObservation", {"version": 1, "rootThreadId": BRAIN,
                            "events": [{"threadId": OTHER}], "streamStatus": "closed", "monitoringEndedAt": time.time()-1})):
            with self.ledger.tx() as db:
                row = self.ledger.get(db, "commands", COMMAND)
                prior = row["notification"].get(key)
                row["notification"][key] = value
                self.ledger.put(db, "commands", COMMAND, row)
            with self.subTest(key=key), self.assertRaises(Refusal): self.preview()
            with self.ledger.tx() as db:
                row = self.ledger.get(db, "commands", COMMAND)
                row["notification"][key] = prior
                self.ledger.put(db, "commands", COMMAND, row)

    def test_tasks_brain_stop_and_strict_managed_state_cannot_recover(self):
        initial = copy.deepcopy(self.ledger.snapshot()["meta"])
        for modify in (lambda m: m["standardRun"].update(tasks=[{"id": "task"}]),
                       lambda m: m.update(brainControl={"desired": "stopped"}),
                       lambda m: m.update(admissionBinding={"id": "strict"}),
                       lambda m: m["standardRun"].update(brainId=OTHER),
                       lambda m: m["standardRun"].update(status="paused")):
            self.change(modify)
            with self.assertRaises(Refusal): self.preview()
            with self.ledger.tx() as db: self.ledger.put(db, "meta", 1, initial)
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "source"); repo["policyProfile"] = "harness"
            self.ledger.put(db, "repos", "source", repo)
        with self.assertRaises(Refusal): self.preview()

    def test_pending_request_and_newer_owned_turn_are_not_bypassed(self):
        with self.ledger.tx() as db:
            self.ledger.put(db, "commands", "new", {"id": "new", "status": "queued"})
        with self.assertRaises(Refusal): self.preview()
        self.assertEqual(Proxy.interrupts, 0)

    def test_concurrent_confirmation_claims_one_cancellation(self):
        doc, results = self.preview(), []
        def send():
            try: results.append(self.confirm(doc)["status"])
            except Refusal: results.append("fenced")
        threads = [threading.Thread(target=send) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertIn("controller_recovered", results)
        self.assertEqual(Proxy.interrupts, 1)

    def test_catalog_drift_during_native_read_refuses_claim(self):
        from orchestrator import projects
        doc = self.preview()
        def changed_catalog():
            projects.record(self.registry, {"schemaVersion": 2, "projects": [{
                "projectId": PROJECT, "projectKind": "local", "label": "Changed catalog",
                "hostId": "local", "path": str(self.repo), "isGitRepository": True}]}, time.time())
        Proxy.on_enter = changed_catalog
        with self.assertRaises(Refusal): self.confirm(doc)
        self.assertEqual(Proxy.interrupts, 0)
        self.assertNotIn("turnRecovery", recovery.saved_state(self.ledger)["commands"][0]["notification"])

    def test_terminal_after_interrupt_retains_controller_until_known_empty(self):
        Proxy.on_interrupt = lambda: setattr(Proxy, "terminals", {"data": [{"processId": "42"}], "nextCursor": None})
        self.assertEqual(self.confirm(self.preview())["status"], "awaiting_end")
        self.assertIsNotNone(self.ledger.snapshot()["meta"]["controller"])
        Proxy.terminals = {"data": [], "nextCursor": None}
        self.assertEqual(self.reconcile()["status"], "controller_recovered")
        self.assertEqual(Proxy.interrupts, 1)

    def test_maintenance_changed_after_review_fences_native_send(self):
        doc = self.preview()
        with patch.object(recovery, "fence_exists", return_value=True):
            with self.assertRaises(Refusal): self.confirm(doc)
        self.assertEqual(Proxy.interrupts, 0)

    def test_foreign_native_project_and_changed_turn_reads_refuse(self):
        Proxy.project_id = OTHER
        with self.assertRaises(Refusal): self.preview()
        Proxy.project_id = PROJECT
        Proxy.on_project_read = lambda: setattr(Proxy, "turn_status", "interrupted")
        Proxy.project_reads = 1  # second repeated project read changes activity.
        with self.assertRaises(Refusal): self.preview()
        self.assertEqual(Proxy.interrupts, 0)

    def test_historical_receipt_does_not_shadow_successor_phase(self):
        self.confirm(self.preview())
        self.change(lambda meta: meta["standardRun"].update(id="successor"))
        self.assertEqual(recovery.inspect(self.ledger, self.wake)["status"], "unavailable")


class RecoveryProxyTest(unittest.TestCase):
    def test_closed_rpc_contract_and_consumed_permit(self):
        client = recovery.RecoveryProxy({}, {"brainId": BRAIN, "projectId": PROJECT}, TURN)
        with patch.object(ReadProxy, "_rpc", return_value={}) as native:
            for method, params in (("turn/start", {}), ("thread/resume", {}), ("turn/steer", {}),
                                   ("turn/interrupt", {"threadId": BRAIN, "turnId": TURN}),
                                   ("thread/read", {"threadId": OTHER, "includeTurns": False})):
                with self.assertRaises(Refusal): client._rpc(method, params)
            native.assert_not_called()
            client.interrupt_permit = True
            with self.assertRaises(Refusal): client._rpc("turn/interrupt", {"threadId": BRAIN, "turnId": OTHER})
            with patch.object(ReadProxy, "_rpc", side_effect=OSError("lost")):
                with self.assertRaises(OSError): client._rpc("turn/interrupt", {"threadId": BRAIN, "turnId": TURN})
            self.assertFalse(client.interrupt_permit)
            with self.assertRaises(Refusal): client._rpc("turn/interrupt", {"threadId": BRAIN, "turnId": TURN})


class TurnRecoveryServerTest(unittest.TestCase):
    request = test_server.ServerTest.request
    login = test_server.ServerTest.login

    def setUp(self):
        TurnRecoveryTest.setUp(self)
        from orchestrator.core import Ledger
        from orchestrator.server import Dashboard
        other = Ledger(self.root / "other")
        other.initialize({"schemaVersion": 1, "brainId": OTHER, "repositories": [{
            "id": "other", "path": str(self.repo), "projectId": PROJECT, "ref": "HEAD",
            "mergePolicy": "manual", "policyProfile": "standard"}]})
        self.registry.register("other", "Other", other.root)
        self.server = Dashboard(self.ledger, 0, self.root / ".env", registry=self.registry)
        self.server.runtime_for("pilot").notifier.app_server = self.wake
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        TurnRecoveryTest.tearDown(self)

    def auth(self, wid="pilot", session=None):
        auth = session or self.login()
        status, _, raw = self.request(f"/api/workspaces/{wid}/session", headers=auth)
        self.assertEqual(status, 200, raw)
        return auth | {"X-CSRF-Token": json.loads(raw)["csrf"]}

    def path(self, suffix="", wid="pilot"):
        return f"/api/workspaces/{wid}/turn-recovery{suffix}"

    def test_owner_auth_csrf_project_and_one_shot_http_replay(self):
        self.assertEqual(self.request(self.path())[0], 401)
        auth = self.auth()
        status, _, raw = self.request(self.path(), headers=auth)
        self.assertEqual(status, 200, raw)
        self.assertNotIn(b"fixture-private", raw)
        self.assertEqual(Proxy.calls, [])
        self.assertEqual(self.request(self.path("/preview"), {"commandId": COMMAND})[0], 403)
        self.assertEqual(self.request(self.path("/preview"), {"commandId": COMMAND}, self.auth("other", auth))[0], 403)
        status, _, raw = self.request(self.path("/preview"), {"commandId": COMMAND}, auth)
        self.assertEqual(status, 200, raw)
        body = {"proposal": json.loads(raw), "confirmed": True}
        self.assertEqual(self.request(self.path("/confirm"), body, self.auth())[0], 409)
        self.assertEqual(Proxy.interrupts, 0)
        for _ in range(2):
            status, _, raw = self.request(self.path("/confirm"), body, auth)
            self.assertEqual(status, 200, raw)
            self.assertEqual(json.loads(raw)["status"], "controller_recovered")
        self.assertEqual(Proxy.interrupts, 1)

    def test_closed_route_no_arbitrary_rpc_query_or_missing_claim(self):
        auth = self.auth()
        for suffix in ("/send", "/raw", "/resume", "/start"):
            self.assertEqual(self.request(self.path(suffix), {}, auth)[0], 404)
        for body in ({"commandId": COMMAND, "method": "turn/start"}, {"commandId": "foreign"}):
            self.assertEqual(self.request(self.path("/preview"), body, auth)[0], 409)
        self.assertEqual(self.request(self.path("/preview?target=other"), {"commandId": COMMAND}, auth)[0], 409)
        self.assertEqual(self.request(self.path("/reconcile"), {"commandId": COMMAND}, auth)[0], 409)
        runtime = self.server.runtime_for("pilot")
        with runtime.native_approval_lock:
            self.assertEqual(self.request(self.path("/preview"), {"commandId": COMMAND}, auth)[0], 409)
        self.assertEqual(Proxy.calls, [])


if __name__ == "__main__":
    unittest.main()
