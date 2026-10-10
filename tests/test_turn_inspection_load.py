import copy
import threading
import unittest
from unittest.mock import patch

from orchestrator import turn_recovery as recovery, turn_host_continuity as continuity
from orchestrator.core import Refusal
from orchestrator.native_read_client import ReadProxy
import test_turn_host_continuity as host_fixture
import test_turn_recovery as base_fixture
from test_turn_recovery import Proxy, BRAIN, PROJECT, OTHER, TURN, COMMAND


class LoadProxy(Proxy):
    loads = 0
    lost_load = False
    load_result = None
    on_load = None

    def __init__(self, *args):
        super().__init__(*args)
        self.load_permit = False

    def _rpc(self, method, params):
        if method != "thread/resume":
            return super()._rpc(method, params)
        assert self.load_permit and not self.interrupt_permit
        assert params == recovery.load_params(self.scope)
        self.load_permit = False
        type(self).loads += 1
        self.calls.append((method, params))
        type(self).ended_activity = "idle"
        if type(self).on_load:
            type(self).on_load()
        if self.lost_load:
            raise OSError("Lost private native response")
        return self.load_result or {"thread": {"id": BRAIN, "projectId": PROJECT, "cwd": self.cwd,
            "status": {"type": "idle"}, "turns": []}, "sandbox": {"type": "workspaceWrite"},
            "approvalPolicy": "on-request", "approvalsReviewer": "user"}


class InspectionLoadTest(unittest.TestCase):
    setUp_base = host_fixture.TurnHostContinuityTest.setUp_base
    tearDown = host_fixture.TurnHostContinuityTest.tearDown
    preview = host_fixture.TurnHostContinuityTest.preview
    confirm = host_fixture.TurnHostContinuityTest.confirm
    reconcile = host_fixture.TurnHostContinuityTest.reconcile
    change = host_fixture.TurnHostContinuityTest.change

    def setUp(self):
        host_fixture.TurnHostContinuityTest.setUp(self)
        self.patches.append(patch.object(recovery, "RecoveryProxy", LoadProxy))
        self.patches[-1].start()
        LoadProxy.turn_status, LoadProxy.ended_activity = "interrupted", "notLoaded"
        LoadProxy.loads, LoadProxy.interrupts, LoadProxy.calls = 0, 0, []
        LoadProxy.lost_load, LoadProxy.load_result, LoadProxy.on_load = False, None, None
        LoadProxy.on_enter, LoadProxy.on_project_read = None, None
        LoadProxy.turns = None
        LoadProxy.terminals = {"data": [], "nextCursor": None}

    def test_preview_read_only_unknown_is_not_zero_and_no_terminal_query_on_unloaded_thread(self):
        before = recovery.saved_state(self.ledger)
        doc = self.preview()["document"]
        self.assertEqual(doc["action"], recovery.LOAD_ACTION)
        self.assertEqual(doc["observation"]["activity"], "notLoaded")
        self.assertIsNone(doc["observation"]["trackedTerminals"])
        self.assertEqual(doc["observation"]["terminalCoverage"], "unknown")
        self.assertEqual(LoadProxy.loads, 0)
        self.assertEqual(before, recovery.saved_state(self.ledger))
        self.assertFalse(any(m in ("thread/resume", "thread/backgroundTerminals/list") for m, _ in LoadProxy.calls))

    def test_one_load_then_actual_reads_recover_only_controller_preserving_original(self):
        before = recovery.saved_state(self.ledger)
        doc = self.preview()
        result = self.confirm(doc)
        self.assertEqual(result["status"], "controller_recovered")
        self.assertEqual(LoadProxy.loads, 1)
        self.assertEqual(LoadProxy.interrupts, 0)
        after = recovery.saved_state(self.ledger)
        self.assertIsNone(after["meta"]["controller"])
        self.assertTrue(after["meta"]["paused"])
        self.assertEqual(after["meta"]["standardRun"]["status"], "stopping")
        for k, v in before["meta"]["standardRun"].items():
            if k not in ("status", "revision", "updatedAt"):
                self.assertEqual(v, after["meta"]["standardRun"][k], k)
        note = after["commands"][0]["notification"]
        original = copy.deepcopy(after["commands"][0]); original["notification"].pop("turnRecovery")
        self.assertEqual(original, before["commands"][0])
        entry = note["turnRecovery"]
        self.assertIsNone(entry["inspectionLoad"]["before"]["trackedTerminals"])
        self.assertEqual(entry["inspectionLoad"]["historicalTerminalCoverage"], "unknown")
        self.assertEqual(entry["observation"]["terminalCoverage"], "observed_current_host")
        self.assertEqual(entry["observation"]["effectOutcome"], "unknown")
        self.assertFalse(entry["observation"]["taskTreeComplete"])
        self.assertNotIn("checkpoint", after["meta"]["standardRun"])
        self.assertEqual(entry["inspectionLoad"]["profile"]["reported"]["codeMode"], None)
        calls = list(LoadProxy.calls)
        self.confirm(doc); self.reconcile()
        self.assertEqual(LoadProxy.calls, calls, "Historical receipts do not perform another read or load")

    def test_load_acknowledgment_without_terminal_coverage_cannot_release(self):
        for page in ({}, {"data": []}, {"data": [], "nextCursor": "more"},
                     {"data": [{"processId": "42"}], "nextCursor": None}):
            with self.subTest(page=page):
                # A fresh fixture per case; not another attempt against one claim.
                before = recovery.saved_state(self.ledger)
                LoadProxy.terminals = page
                doc = self.preview()
                self.assertEqual(self.confirm(doc)["status"], "awaiting_end")
                self.assertIsNotNone(recovery.saved_state(self.ledger)["meta"]["controller"])
                calls = LoadProxy.loads
                self.confirm(doc); self.reconcile()
                self.assertEqual(LoadProxy.loads, calls)
                # Test-only restore permits independent scenarios, never live use.
                with self.ledger.tx() as db:
                    self.ledger.put(db, "meta", 1, before["meta"])
                    self.ledger.put(db, "commands", COMMAND, before["commands"][0])
                LoadProxy.ended_activity = "notLoaded"

    def test_unknown_load_can_only_be_reconciled_read_only(self):
        LoadProxy.lost_load = True
        LoadProxy.terminals = {}
        doc = self.preview()
        self.assertEqual(self.confirm(doc)["status"], "awaiting_end")
        entry = recovery.saved_state(self.ledger)["commands"][0]["notification"]["turnRecovery"]
        self.assertEqual(entry["inspectionLoad"]["status"], "issued")
        self.assertEqual(entry["delivery"], "unknown")
        self.confirm(doc); self.reconcile()
        self.assertEqual(LoadProxy.loads, 1)
        LoadProxy.terminals = {"data": [], "nextCursor": None}
        self.assertEqual(self.reconcile()["status"], "controller_recovered")
        self.assertEqual(LoadProxy.loads, 1)

    def test_no_active_or_foreign_turn_can_obtain_a_load(self):
        for row in ({"id": TURN, "status": "inProgress"}, {"id": OTHER, "status": "interrupted"},
                    {"id": TURN, "status": "unknown"}):
            LoadProxy.turns = {"data": [row]}
            with self.assertRaises(Refusal): self.preview()
        self.assertEqual(LoadProxy.loads, 0)

    def test_changed_loaded_state_before_confirmation_requires_new_read_only_review(self):
        doc = self.preview()
        LoadProxy.ended_activity = "idle"
        with self.assertRaises(Refusal): self.confirm(doc)
        self.assertEqual(LoadProxy.loads, 0)
        self.assertNotIn("turnRecovery", recovery.saved_state(self.ledger)["commands"][0]["notification"])
        self.assertEqual(self.preview()["document"]["action"], "reconcile_ended_turn_on_reviewed_host")

    def test_new_turn_after_load_fences_controller_recovery(self):
        LoadProxy.on_load = lambda: setattr(LoadProxy, "turns", {"data": [{"id": OTHER, "status": "completed"}]})
        self.assertEqual(self.confirm(self.preview())["status"], "awaiting_end")
        self.assertIsNotNone(recovery.saved_state(self.ledger)["meta"]["controller"])
        self.assertEqual(LoadProxy.loads, 1)

    def test_dead_host_must_remain_absent_at_load_and_release(self):
        doc = self.preview()
        with patch.object(continuity, "process_absent", return_value=False):
            with self.assertRaises(Refusal): self.confirm(doc)
        self.assertEqual(LoadProxy.loads, 0)
        LoadProxy.on_load = lambda: self.controls.retired_host.update(processId=23456)
        self.assertEqual(self.confirm(doc)["status"], "awaiting_end")
        self.assertIsNotNone(recovery.saved_state(self.ledger)["meta"]["controller"])

    def test_interrupted_confirmation_keeps_one_shot_load_intent(self):
        doc = self.preview()
        LoadProxy.on_load = lambda: (_ for _ in ()).throw(KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt): self.confirm(doc)
        self.assertEqual(LoadProxy.loads, 1)
        entry = recovery.saved_state(self.ledger)["commands"][0]["notification"]["turnRecovery"]
        self.assertEqual(entry["inspectionLoad"]["status"], "issued")
        LoadProxy.on_load = None
        self.confirm(doc); self.reconcile()
        self.assertEqual(LoadProxy.loads, 1)

    def test_concurrent_confirmations_issue_at_most_one_load(self):
        doc, results = self.preview(), []
        def confirm():
            try:
                results.append(self.confirm(doc)["status"])
            except Refusal:
                results.append("fenced")
        threads = [threading.Thread(target=confirm) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(LoadProxy.loads, 1)
        self.assertIn("controller_recovered", results)

    def test_same_original_host_never_gets_loading_exception(self):
        self.wake.binding = self.old
        with self.assertRaises(Refusal): self.preview()
        self.assertEqual(LoadProxy.loads, 0)

    def test_changed_policy_review_retirement_or_controller_cannot_load(self):
        for change in (lambda: self.change(lambda m: m.update(controller={"owner": "new", "token": "new"})),
                       lambda: self.controls.retired_host.update(processId=23456),
                       lambda: self.binding["brains"][BRAIN]["nativePolicy"].update(approvalPolicy="never")):
            state = recovery.saved_state(self.ledger)
            retired, binding = copy.deepcopy(self.controls.retired_host), copy.deepcopy(self.binding)
            doc = self.preview()
            change()
            with self.assertRaises(Refusal): self.confirm(doc)
            self.assertEqual(LoadProxy.loads, 0)
            with self.ledger.tx() as db:
                self.ledger.put(db, "meta", 1, state["meta"])
            self.controls.retired_host = retired
            self.binding.clear(); self.binding.update(binding)

    def test_maintenance_or_stop_during_review_fences_load(self):
        doc = self.preview()
        with patch.object(recovery, "fence_exists", return_value=True):
            with self.assertRaises(Refusal): self.confirm(doc)
        self.change(lambda m: m.update(brainControl={"desired": "stopped"}))
        with self.assertRaises(Refusal): self.confirm(doc)
        self.assertEqual(LoadProxy.loads, 0)

    def test_claim_durable_before_load_and_one_shot_even_before_frame(self):
        doc = self.preview()
        seen = []
        def interrupted(*args):
            state = recovery.saved_state(self.ledger)
            seen.append(state["commands"][0]["notification"]["turnRecovery"]["inspectionLoad"]["status"])
            raise KeyboardInterrupt()
        with patch.object(self.controls, "_load_for_inspection", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt): self.confirm(doc)
        self.assertEqual(seen, ["claimed"])
        self.confirm(doc); self.reconcile()
        self.assertEqual(LoadProxy.loads, 0, "Even a pre-frame crash cannot mint another load")
        self.assertIsNotNone(recovery.saved_state(self.ledger)["meta"]["controller"])


class InspectionLoadServerTest(unittest.TestCase):
    setUp_base = InspectionLoadTest.setUp_base
    request = base_fixture.TurnRecoveryServerTest.request
    login = base_fixture.TurnRecoveryServerTest.login
    auth = base_fixture.TurnRecoveryServerTest.auth
    path = base_fixture.TurnRecoveryServerTest.path

    def setUp(self):
        InspectionLoadTest.setUp(self)
        from orchestrator.server import Dashboard
        self.server = Dashboard(self.ledger, 0, self.root / ".env", registry=self.registry,
            turn_recovery_prior_binding=self.old, turn_recovery_retired_host=self.retired)
        self.server.runtime_for("pilot").notifier.app_server = self.wake
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        InspectionLoadTest.tearDown(self)

    def test_http_explicit_load_review_no_get_preview_or_replay_effect(self):
        self.assertEqual(self.request(self.path())[0], 401)
        auth = self.auth()
        before = recovery.saved_state(self.ledger)
        with patch.object(continuity, "process_absent", side_effect=AssertionError("Polling collected evidence")):
            self.assertEqual(self.request(self.path(), headers=auth)[0], 200)
        self.assertEqual(self.request(self.path("/preview"), {"commandId": COMMAND})[0], 403)
        status, _, raw = self.request(self.path("/preview"), {"commandId": COMMAND}, auth)
        self.assertEqual(status, 200, raw)
        import json
        doc = json.loads(raw)
        self.assertEqual(doc["document"]["action"], recovery.LOAD_ACTION)
        self.assertIsNone(doc["document"]["observation"]["trackedTerminals"])
        self.assertEqual(before, recovery.saved_state(self.ledger))
        self.assertEqual(LoadProxy.loads, 0)
        self.assertEqual(self.request(self.path("/confirm"), {"proposal": doc, "confirmed": False}, auth)[0], 409)
        status, _, raw = self.request(self.path("/confirm"), {"proposal": doc, "confirmed": True}, auth)
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["status"], "controller_recovered")
        self.assertEqual(LoadProxy.loads, 1)
        calls = list(LoadProxy.calls)
        self.assertEqual(self.request(self.path("/confirm"), {"proposal": doc, "confirmed": True}, auth)[0], 200)
        self.assertEqual(LoadProxy.calls, calls)


class InspectionLoadProxyTest(unittest.TestCase):
    def test_fixed_policy_and_consumed_load_permit_no_start_or_other_rpc(self):
        client = recovery.RecoveryProxy({}, {"brainId": BRAIN, "projectId": PROJECT}, TURN)
        params = recovery.load_params(client.scope)
        with patch.object(ReadProxy, "_rpc", return_value={}) as native:
            for method in ("turn/start", "thread/start", "thread/metadata/update", "turn/steer"):
                with self.assertRaises(Refusal): client._rpc(method, {})
            with self.assertRaises(Refusal): client._rpc("thread/resume", params)
            client.load_permit = True
            for key, value in (("threadId", OTHER), ("approvalPolicy", "never"),
                               ("sandbox", "danger-full-access"), ("approvalsReviewer", "auto_review"),
                               ("excludeTurns", False), ("model", "invented"), ("history", [])):
                with self.assertRaises(Refusal): client._rpc("thread/resume", {**params, key: value})
            native.assert_not_called()
            with patch.object(ReadProxy, "_rpc", side_effect=OSError("lost")):
                with self.assertRaises(OSError): client._rpc("thread/resume", params)
            self.assertFalse(client.load_permit)
            with self.assertRaises(Refusal): client._rpc("thread/resume", params)
