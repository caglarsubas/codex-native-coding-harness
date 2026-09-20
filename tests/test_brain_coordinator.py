"""Lifecycle composition on disposable state; never activate a real workspace."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import brain_coordinator as brain, missions, native_lifecycle, run_authority as runs, task_contracts
from orchestrator.core import PREFLIGHT_CHECKS, Refusal, canonical
import test_core
import test_dispatch_admission
import test_missions
import test_run_authority


class BrainCoordinatorTest(unittest.TestCase):
    def setUp(self):
        specification = test_missions.specification
        def delegated(*args, **kwargs): return specification(*args, **{**kwargs, "mode": "phase_delegated"})
        # No task approval: the coordinator must compose it under the real grant.
        with patch.object(test_missions, "specification", delegated), \
             patch.object(test_run_authority.RunAuthorityTest, "approve", return_value={"approvalHash": "a"*64}):
            self.fx = test_dispatch_admission.DispatchAdmissionTest(); self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.ledger, self.token, self.store = self.fx.ledger, self.fx.token, self.fx.store
        self.api = brain.BrainCoordinator(self.fx.bridge); self.seq = 0

    def inspect(self): return self.api.inspect(self.token)
    def logical(self): return self.fx.fx.fx.logical(), self.store.snapshot()
    def pause(self): self.fx.fx.fx.command("brain_stop")
    def request(self, choice="create", **fields):
        self.seq += 1; context = self.inspect()
        return {"id": "choice-"+str(self.seq), "contextHash": context["contextHash"], "expectedRevision": context["revision"],
                "choice": choice, "queueId": self.fx.args["queue_id"] if choice == "create" else None,
                "workerId": None, "estimates": test_dispatch_admission.ESTIMATES if choice == "create" else None,
                "rationale": "Advance the existing reviewed phase.", "reuseReason": "No owned task can implement this packet.",
                "scopeAssessment": "Exact packet remains inside the reviewed phase." if choice == "create" else None,
                "resumeEvent": "A new owner decision or external evidence arrives." if choice == "wait" else None, **fields}

    def decide(self, request=None, **fields): return self.api.decide(self.token, request or self.request(**fields))
    def reserve(self, receipt): return self.api.reserve(self.token, receipt["decisionHash"])
    def cli(self, operation, *args, request=None, token=None, select=True):
        argv = [sys.executable, "-m", "orchestrator.cli"]
        if select: argv += ["--platform", str(self.fx.registry.root), "--workspace", "a"]
        argv += ["brain-cycle-"+operation, *args]
        if request is not None:
            path = self.ledger.root / "decision.json"; path.write_text(canonical(request)); argv.append(str(path))
        return subprocess.run(argv, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
                              env={**os.environ, "ORCHESTRATOR_CONTROLLER_TOKEN": token or self.token})

    def idle_worker(self):
        worker = self.reserve(self.decide())["workerId"]; self.fx.bridge.begin_creation(self.token, worker)
        api = native_lifecycle.NativeLifecycle(self.fx.bridge)
        api.observe(self.token, worker, {"id": "idle", "expectedHash": None, "outcome": "confirmed", "hostId": "local",
            "threadId": "native-worker", "clientThreadId": None, "activity": "idle", "observedAt": time.time(), "evidenceHash": "b"*64})
        return worker, api

    def add_packet(self, packet="TEST-002", predecessors=None):
        seed = test_core.seed(profile="standard", packet=packet)
        seed["branch"] = "codex/"+packet.lower(); seed["predecessors"] = predecessors or []
        q = self.ledger.prepare(seed)
        spec = self.fx.fx.fx.spec() | {"queueId": q["id"], "seedHash": q["seedHash"], "packetDigest": q["packetDigest"]}
        task_contracts.propose(self.ledger, self.token, self.fx.fx.request(spec=spec))
        self.ledger.preflight(self.token, q["id"], {"seedHash": q["seedHash"], "packetDigest": q["packetDigest"],
            "baseSHA": seed["baseSHA"], "projectId": "project-a", "checks": {k: True for k in PREFLIGHT_CHECKS}, "evidence": ["fixture"]})
        return q

    def test_inspection_is_read_only_and_does_not_approve_or_reserve(self):
        before = self.logical()
        with patch("subprocess.Popen", side_effect=AssertionError("No transport")): context = self.inspect()
        self.assertEqual(before, self.logical())
        self.assertTrue(context["candidates"][0]["needsDelegatedApproval"])
        self.assertFalse(context["automaticSelection"]); self.assertFalse(context["executionAuthorized"])
        self.assertIsNone(self.ledger.snapshot()["queue"][0].get("phaseApprovalHash"))

    def test_decision_atomically_approves_but_does_not_reserve_or_send(self):
        before = self.store.snapshot(); receipt = self.decide()
        self.assertEqual(before, self.store.snapshot()); self.assertEqual(self.ledger.snapshot()["workers"], [])
        approval = self.ledger.document(receipt["approvalHash"])
        self.assertEqual(approval["actor"], "designated_brain")
        self.assertEqual(approval["runHash"], self.fx.run["runHash"])
        self.assertFalse(receipt["executionAuthorized"]); self.assertNotIn("arguments", receipt)
        decision = self.api.read(self.token, receipt["decisionHash"])["decision"]
        self.assertEqual(decision["target"]["seedHash"], self.fx.fx.fx.q["seedHash"])

    def test_reservation_uses_decision_estimates_and_exact_existing_kernel(self):
        receipt = self.decide(); one = self.reserve(receipt); two = self.reserve(receipt)
        self.assertEqual(one, two); self.assertEqual(one["stage"], "reserved")
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)
        self.assertEqual(self.fx.claim()["estimatedTokens"], 11500)
        self.assertEqual(self.inspect()["workers"][0]["next"], "native-create-begin")
        self.assertEqual(self.inspect()["candidates"], [])

    def test_subprocess_round_trip_and_explicit_selection(self):
        request = self.request(); result = self.cli("decide", request=request)
        self.assertEqual(result.returncode, 0, result.stderr); receipt = json.loads(result.stdout)
        for op in ("read", "reserve"):
            result = self.cli(op, receipt["decisionHash"]); self.assertEqual(result.returncode, 0, result.stderr)
        for fields in ({"select": False}, {"token": "wrong"}): self.assertNotEqual(self.cli("inspect", **fields).returncode, 0)
        self.assertEqual(self.cli("inspect").returncode, 0)

    def test_concurrent_duplicate_decisions_retain_one_approval_and_receipt(self):
        request = self.request()
        with ThreadPoolExecutor(max_workers=2) as pool: result = list(pool.map(lambda _: self.decide(request), range(2)))
        self.assertEqual(result[0], result[1])
        with self.ledger.tx() as db:
            for kind in (brain.KIND, "run_task_approval"):
                self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (kind,)).fetchone()[0], 1)

    def test_concurrent_reservations_do_not_duplicate_attempt_or_tokens(self):
        receipt = self.decide()
        with ThreadPoolExecutor(max_workers=2) as pool: result = list(pool.map(lambda _: self.reserve(receipt), range(2)))
        self.assertEqual(result[0], result[1]); self.assertEqual(len(self.store.snapshot()["claims"]), 1)

    def test_event_failure_rolls_back_decision_and_delegated_approval(self):
        before = self.logical(); request = self.request(); event = self.api.ledger.event
        def fail(db, kind, data):
            if kind == "brain_cycle_decided": raise RuntimeError("fixture interruption")
            return event(db, kind, data)
        with patch.object(self.api.ledger, "event", side_effect=fail), self.assertRaises(RuntimeError): self.decide(request)
        self.assertEqual(before, self.logical())

    def test_historical_replay_does_not_restore_latest_or_renew_freshness(self):
        request = self.request(); first = self.decide(request)
        second = self.decide(choice="wait")
        before = self.logical()
        with patch.object(brain.time, "time", return_value=time.time()+1000):
            self.assertEqual(self.decide(request), first)
        self.assertEqual(before, self.logical()); self.assertEqual(self.inspect()["latestDecisionHash"], second["decisionHash"])
        with self.assertRaisesRegex(Refusal, "latest"): self.reserve(first)

    def test_changed_id_content_context_or_budget_refuses_without_writes(self):
        request = self.request(); first = self.decide(request)
        with self.assertRaisesRegex(Refusal, "reused"): self.decide(request | {"rationale": "Other"})
        for changed in ({"expectedRevision": 0}, {"contextHash": "a"*64},
                        {"estimates": {"workTokens": 9999, "reviewTokens": 1000, "handoffTokens": 500}},
                        {"estimates": {"workTokens": 100000, "reviewTokens": 1000, "handoffTokens": 500}}):
            bad = self.request() | changed; before = self.logical()
            with self.assertRaises(Refusal): self.decide(bad)
            self.assertEqual(before, self.logical())
        self.assertEqual(self.inspect()["latestDecisionHash"], first["decisionHash"])

    def test_shared_state_change_invalidates_inspection(self):
        request = self.request(); self.fx.refresh_usage(total=100); before = self.logical()
        with self.assertRaisesRegex(Refusal, "context changed"): self.decide(request)
        self.assertEqual(before, self.logical())

    def test_pause_prevents_new_work_but_keeps_historical_and_wait_choices(self):
        request = self.request(); receipt = self.decide(request); self.pause()
        self.assertEqual(self.decide(request), receipt)
        with self.assertRaises(Refusal): self.reserve(receipt)
        with self.assertRaises(Refusal): self.decide()
        wait = self.decide(choice="wait"); self.assertEqual(wait["next"], "wait_for_named_event")
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])

    def test_revoked_approval_is_not_automatically_reapproved(self):
        receipt = self.decide()
        runs.revoke_task(self.ledger, self.fx.fx.request(queueId=self.fx.args["queue_id"],
            approvalHash=receipt["approvalHash"], reason="Owner withdrew scope"), actor="dashboard_owner")
        self.assertFalse(self.inspect()["candidates"][0]["canCreate"])
        with self.assertRaises(Refusal): self.reserve(receipt)
        with self.assertRaises(Refusal): self.decide()

    def test_expired_decision_is_not_reservation_permission(self):
        receipt = self.decide(); before = self.logical()
        with patch.object(brain.time, "time", return_value=time.time()+61), self.assertRaisesRegex(Refusal, "expired"):
            self.reserve(receipt)
        self.assertEqual(before, self.logical())

    def test_wait_and_handle_are_inert_and_wait_requires_event(self):
        for choice in ("wait", "handle"):
            before = self.store.snapshot(); receipt = self.decide(choice=choice)
            self.assertFalse(receipt["executionAuthorized"]); self.assertIsNone(receipt["approvalHash"])
            self.assertEqual(before, self.store.snapshot())
            with self.assertRaises(Refusal): self.reserve(receipt)
        with self.assertRaises(Refusal): self.decide(self.request("wait", resumeEvent=""))

    def test_confirmed_idle_task_can_be_selected_for_existing_correction(self):
        worker, _ = self.idle_worker(); context = self.inspect()
        self.assertTrue(context["workers"][0]["canContinue"])
        receipt = self.decide(self.request("continue", workerId=worker))
        self.assertEqual(receipt["next"], "correction-handoff-prepare")
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)
        self.assertFalse(receipt["executionAuthorized"])

    def test_running_and_unknown_tasks_do_not_offer_correction(self):
        worker, lifecycle = self.idle_worker()
        for activity in ("running", "unknown"):
            record = self.fx.claim()["nativeLifecycleHash"]
            lifecycle.observe(self.token, worker, {"id": activity, "expectedHash": record, "outcome": "confirmed", "hostId": "local",
                "threadId": "native-worker", "clientThreadId": None, "activity": activity, "observedAt": time.time(), "evidenceHash": "b"*64})
            self.assertFalse(self.inspect()["workers"][0]["canContinue"])
            with self.assertRaises(Refusal): self.decide(self.request("continue", workerId=worker))

    def test_maintenance_fences_decision_and_reservation(self):
        receipt = self.decide(); (self.ledger.root / "admission-fence.json").touch(mode=0o600)
        with self.assertRaises(Refusal): self.reserve(receipt)
        with self.assertRaises(Refusal): self.decide()
        self.assertFalse(self.inspect()["executionAuthorized"])

    def test_lost_local_reservation_receipt_recovers_without_new_claim(self):
        receipt = self.decide()
        with patch.object(brain.SelectedAdmission, "attach_in", side_effect=RuntimeError("fixture crash")), self.assertRaises(RuntimeError):
            self.reserve(receipt)
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)
        self.pause(); worker = self.ledger.snapshot()["workers"][0]["id"]
        saved = self.fx.bridge.recover(self.token, worker)
        self.assertEqual(saved["stage"], "reserved"); self.assertFalse(saved["executionAuthorized"])

    def test_pause_between_reservation_boundaries_retains_intent(self):
        receipt = self.decide(); locked = brain.SelectedAdmission.locked; calls = 0
        def pause_between(api, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2: self.pause()
            return locked(api, *args, **kwargs)
        with patch.object(brain.SelectedAdmission, "locked", pause_between), self.assertRaises(Refusal): self.reserve(receipt)
        self.assertEqual(self.store.snapshot()["claims"], [])
        self.assertEqual(self.ledger.snapshot()["workers"][0]["dispatchAdmission"]["stage"], "intent")

    def test_second_packet_cannot_ignore_retained_repository_owner(self):
        self.reserve(self.decide()); q = self.add_packet()
        candidate = next(c for c in self.inspect()["candidates"] if c["queueId"] == q["id"])
        self.assertFalse(candidate["canCreate"])
        with self.assertRaises(Refusal): self.decide(self.request(queueId=q["id"]))
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)

    def test_managed_predecessor_requires_its_evidence_axis(self):
        self.reserve(self.decide())
        q = self.add_packet(predecessors=[{"repository": "a", "packetId": "TEST-001", "axis": "source",
            "evidenceSHA256": "a"*64, "reference": "fixture independent proof"}])
        candidate = next(c for c in self.inspect()["candidates"] if c["queueId"] == q["id"])
        self.assertFalse(candidate["canCreate"]); self.assertIn("predecessor", candidate["reason"])

    def test_pointer_corruption_fails_closed_without_new_decision(self):
        receipt = self.decide()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta.pop("brainCycleHash"); self.ledger.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "pointer missing"): self.inspect()
        with self.assertRaises(Refusal): self.reserve(receipt)

    def test_unknown_fields_wrong_target_and_unbounded_requests_refuse(self):
        for fields in ({"choice": "merge"}, {"model": "override"}, {"workerId": "foreign"},
                       {"scopeAssessment": ""}, {"rationale": "x"*17000}, {"estimates": {}}):
            before = self.logical()
            with self.assertRaises(Refusal): self.decide(self.request() | fields)
            self.assertEqual(before, self.logical())

    def test_exact_owner_mode_never_infers_approval_but_preserves_existing_owner_approval(self):
        for approved in (False, True):
            other = test_dispatch_admission.DispatchAdmissionTest()
            if approved: other.setUp()
            else:
                with patch.object(test_run_authority.RunAuthorityTest, "approve", return_value={"approvalHash": "a"*64}): other.setUp()
            try:
                api = brain.BrainCoordinator(other.bridge); context = api.inspect(other.token)
                request = self.request() | {"contextHash": context["contextHash"], "expectedRevision": context["revision"]}
                self.assertEqual(context["candidates"][0]["canCreate"], approved)
                if approved:
                    receipt = api.decide(other.token, request)
                    self.assertEqual(receipt["approvalHash"], other.approval["approvalHash"])
                else:
                    with self.assertRaises(Refusal): api.decide(other.token, request)
                    self.assertIsNone(other.ledger.snapshot()["queue"][0].get("phaseApprovalHash"))
            finally: other.tearDown()

    def test_cli_rejects_duplicate_fields_nonfinite_and_symlink_without_writes(self):
        before = self.logical()
        for content in ('{"id":"one","id":"two"}', '{"id":NaN}', "x"*16001):
            path = self.ledger.root / "invalid.json"; path.write_text(content)
            self.assertNotEqual(self.cli("decide", str(path)).returncode, 0)
        target = self.ledger.root / "target.json"; target.write_text(canonical(self.request()))
        link = self.ledger.root / "link.json"; link.symlink_to(target)
        self.assertNotEqual(self.cli("decide", str(link)).returncode, 0)
        self.assertEqual(before, self.logical())

    def test_foreign_brain_cannot_read_decide_or_reserve(self):
        request = self.request(); receipt = self.decide(request)
        with self.assertRaises(Refusal): self.api.inspect("wrong")
        with self.assertRaises(Refusal): self.api.decide("wrong", request)
        with self.assertRaises(Refusal): self.api.read("wrong", receipt["decisionHash"])
        with self.assertRaises(Refusal): self.api.reserve("wrong", receipt["decisionHash"])

    def test_two_no_progress_corrections_and_stale_idle_are_not_selectable(self):
        import test_correction_handoff
        fixture = test_correction_handoff.CorrectionHandoffTest(); fixture.setUp()
        try:
            api = brain.BrainCoordinator(fixture.api.bridge)
            for _ in range(2):
                receipt = fixture.prepare(); fixture.check(receipt); fixture.record(receipt); fixture.record(receipt, "finished")
            self.assertFalse(api.inspect(fixture.token)["workers"][0]["canContinue"])
            self.assertIn("no-progress", api.inspect(fixture.token)["workers"][0]["reason"])
        finally: fixture.doCleanups()
        worker, _ = self.idle_worker()
        later = time.time()+61
        with patch.object(brain.time, "time", return_value=later), patch.object(self.store, "clock", return_value=later):
            self.assertFalse(self.inspect()["workers"][0]["canContinue"])

    def test_delegated_same_task_correction_and_runner_handoffs(self):
        import test_correction_handoff
        import test_runner_handoff
        specification, approve = test_missions.specification, test_run_authority.RunAuthorityTest.approve
        def spec(*args, **kwargs): return specification(*args, **{**kwargs, "mode": "phase_delegated"})
        def approval(fixture, run, **kwargs): return approve(fixture, run, **{**kwargs, "actor": "designated_brain"})
        for cls in (test_correction_handoff.CorrectionHandoffTest, test_runner_handoff.RunnerHandoffTest):
            fixture = cls()
            with patch.object(test_missions, "specification", spec), patch.object(test_run_authority.RunAuthorityTest, "approve", approval):
                fixture.setUp()
            try:
                receipt = fixture.prepare(); self.assertTrue(fixture.check(receipt)["sendNow"])
                with self.assertRaises(Refusal): fixture.check(receipt)
            finally:
                fixture.tearDown(); fixture.doCleanups()

    def test_reviewed_first_packet_exposes_next_delegated_packet_without_owner_continue(self):
        import test_result_handoff
        specification, approve = test_missions.specification, test_run_authority.RunAuthorityTest.approve
        def spec(*args, **kwargs): return specification(*args, **{**kwargs, "mode": "phase_delegated"})
        def approval(fixture, run, **kwargs): return approve(fixture, run, **{**kwargs, "actor": "designated_brain"})
        fixture = test_result_handoff.ResultHandoffTest()
        with patch.object(test_missions, "specification", spec), patch.object(test_run_authority.RunAuthorityTest, "approve", approval):
            fixture.setUp()
        try:
            ledger, token = fixture.ledger, fixture.token
            reviewed = fixture.call("review", fixture.review_request())
            self.assertTrue(reviewed["packetAccepted"])
            original_run = fixture.intent["runHash"]
            second = ledger.document(fixture.intent["seedHash"]) | {"packetId": "TEST-002", "branch": "codex/test-002",
                "predecessors": [{"repository": "a", "packetId": "TEST-001", "axis": "source", "evidenceSHA256": "a"*64,
                                  "reference": "Fixture independently reviewed source axis"}]}
            q = ledger.prepare(second)
            contract = ledger.document(fixture.intent["contractHash"])["spec"] | {
                "queueId": q["id"], "seedHash": q["seedHash"], "packetDigest": q["packetDigest"]}
            task_contracts.propose(ledger, token, {"id": "next-contract", "expectedRevision": ledger.snapshot()["meta"]["revision"], "spec": contract})
            ledger.preflight(token, q["id"], {"seedHash": q["seedHash"], "packetDigest": q["packetDigest"], "baseSHA": second["baseSHA"],
                "projectId": "project-a", "checks": {k: True for k in PREFLIGHT_CHECKS}, "evidence": ["fixture"]})
            api = brain.BrainCoordinator(fixture.api.bridge); context = api.inspect(token)
            candidate = next(c for c in context["candidates"] if c["queueId"] == q["id"])
            self.assertTrue(candidate["canCreate"], candidate)
            request = self.request() | {"id": "next-cycle", "queueId": q["id"],
                "expectedRevision": context["revision"], "contextHash": context["contextHash"]}
            receipt = api.decide(token, request); reserved = api.reserve(token, receipt["decisionHash"])
            intent = ledger.document(reserved["intentHash"])
            self.assertEqual(intent["runHash"], original_run)
            self.assertEqual(ledger.document(receipt["approvalHash"])["actor"], "designated_brain")
            self.assertEqual(len(fixture.store.snapshot()["claims"]), 2)
            self.assertEqual(intent["queueId"], q["id"])
            self.assertFalse(ledger.snapshot()["meta"]["pilotPassed"])
        finally:
            fixture.tearDown(); fixture.doCleanups()


if __name__ == "__main__": unittest.main()
