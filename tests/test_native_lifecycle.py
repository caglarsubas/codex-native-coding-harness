import json
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import native_lifecycle, run_authority as runs, workspace_pause
from orchestrator.admission import AdmissionStore
from orchestrator.core import Refusal, canonical, digest
from orchestrator.dispatch_admission import DispatchAdmission
from orchestrator.observations import capture
import test_dispatch_admission


ESTIMATES = {"workTokens": 1000, "reviewTokens": 100, "handoffTokens": 50}


class NativeLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_dispatch_admission.DispatchAdmissionTest()
        self.fx.runners = getattr(self, "runners", ())
        self.fx.setUp()
        self.ledger, self.token, self.store = self.fx.ledger, self.fx.token, self.fx.store
        self.api = native_lifecycle.NativeLifecycle(self.fx.bridge)
        self.fx.reserve(); self.fx.begin(); self.wid = self.fx.worker()["id"]
        self.seq = 0
        with self.ledger.tx() as db:
            self.artifact = capture(db, "fixture-correction", b"Correct only the existing fixture within its approved paths.",
                {"repository": "a", "name": "correction.md", "orderAt": time.time(),
                 "references": [{"session": "brain-a", "at": time.time()}]})

    def tearDown(self): self.fx.tearDown()

    def claim(self): return self.fx.claim()
    def worker(self): return self.fx.worker()
    def state(self):
        key = self.claim()["nativeLifecycleHash"]
        with self.store.tx() as db:
            return json.loads(db.execute("SELECT data FROM native_records WHERE hash=?", (key,)).fetchone()[0])["state"]

    def request(self, **fields):
        self.seq += 1
        return {"id": "fixture-"+str(self.seq), "expectedHash": self.claim().get("nativeLifecycleHash"), **fields}

    def observation(self, **fields):
        return self.request(outcome="confirmed", hostId="local", threadId="worker-fixture", clientThreadId=None,
                            activity="idle", observedAt=time.time(), evidenceHash="a"*64) | fields

    def observe(self, request=None, **fields):
        return self.api.observe(self.token, self.wid, request or self.observation(**fields))

    def correction(self, **fields):
        return self.request(operation="edit", instructionArtifactId=self.artifact["id"], estimates=ESTIMATES) | fields

    def begin(self, request=None, **fields):
        return self.api.begin_continuation(self.token, self.wid, request or self.correction(**fields))

    def delivery(self, outcome="acknowledged", **fields):
        return self.request(continuationHash=self.worker()["nativeContinuationIntentHash"], hostId="local", threadId="worker-fixture",
            outcome=outcome, observedAt=time.time(), evidenceHash="b"*64, progress=False if outcome == "finished" else None,
            activity="idle" if outcome == "finished" else "unknown") | fields

    def deliver(self, outcome="acknowledged", request=None, **fields):
        return self.api.delivery(self.token, self.wid, request or self.delivery(outcome, **fields))

    def test_pending_client_is_separate_and_cannot_continue(self):
        result = self.observe(outcome="pending", threadId=None, clientThreadId="client-fixture", activity="unknown")
        self.assertIsNone(self.worker()["threadId"]); self.assertIsNone(self.claim()["native"])
        self.assertEqual(self.worker()["clientThreadId"], "client-fixture")
        self.assertFalse(result["executionAuthorized"]); self.assertFalse(result["ownershipReleased"])
        with self.assertRaisesRegex(Refusal, "confirmed idle"): self.begin()

    def test_confirmed_resolution_retains_client_identity_and_resources(self):
        self.observe(outcome="pending", threadId=None, clientThreadId="client-fixture", activity="unknown")
        self.observe(clientThreadId="client-fixture")
        self.assertEqual(self.claim()["native"], {"hostId": "local", "threadId": "worker-fixture"})
        self.assertEqual(self.worker()["clientThreadId"], "client-fixture")
        self.assertEqual(self.worker()["threadId"], "worker-fixture")
        self.assertEqual(self.store.snapshot()["allocations"][0]["budget"]["heldTokens"], 11500)
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)

    def test_ids_cannot_be_substituted_erased_or_used_in_wrong_role(self):
        self.observe(outcome="pending", threadId=None, clientThreadId="client-fixture", activity="unknown")
        for fields in ({"clientThreadId": None}, {"clientThreadId": "another"},
                       {"clientThreadId": "client-fixture", "threadId": "client-fixture"},
                       {"clientThreadId": "client-fixture", "hostId": "another-host"}):
            with self.assertRaises(Refusal): self.observe(**fields)
        self.observe(clientThreadId="client-fixture")
        with self.assertRaises(Refusal): self.observe(threadId="another", clientThreadId="client-fixture")
        with self.assertRaises(Refusal): self.observe(outcome="uncertain", threadId=None, clientThreadId="client-fixture", activity="unknown")

    def test_uncertainty_preserves_confirmed_identity_without_releasing(self):
        self.observe()
        self.observe(outcome="uncertain", activity="unknown")
        self.assertEqual(self.claim()["status"], "blocked")
        self.assertEqual(self.worker()["threadId"], "worker-fixture")
        with self.assertRaises(Refusal): self.begin()
        self.observe(); self.assertEqual(self.worker()["status"], "running")

    def test_unconfirmed_uncertainty_stays_inflight_for_pause(self):
        self.observe(outcome="uncertain", threadId=None, activity="unknown")
        self.assertEqual(self.worker()["status"], "starting")
        self.fx.fx.fx.command("brain_stop")
        blockers = self.ledger.snapshot()["workspacePause"]["blockers"]
        self.assertIn("worker_effect_inflight", [b["code"] for b in blockers])

    def test_read_recovery_does_not_create_journal_or_refresh_evidence(self):
        with self.assertRaisesRegex(Refusal, "No native result"): self.api.recover(self.token, self.wid)
        with self.store.tx() as db: self.assertFalse(native_lifecycle.table_exists(db))
        self.observe(); before = self.store.snapshot(); worker = self.worker()
        self.api.recover(self.token, self.wid)
        self.assertEqual(self.store.snapshot(), before)
        self.assertEqual(self.worker(), worker)

    def test_recording_after_pause_expiry_and_maintenance_fence_is_safety_only(self):
        self.fx.fx.fx.command("pause")
        self.fx.meta(admissionBinding={"fixture": True})
        request = self.observation()
        with patch("orchestrator.run_authority.time.time", return_value=self.fx.grant["expiresAt"]+1):
            result = self.observe(request)
        self.assertFalse(result["executionAuthorized"])
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        with self.assertRaises(Refusal): self.begin()

    def test_historical_replay_does_not_regress_current_state(self):
        request = self.observation(outcome="pending", threadId=None, clientThreadId="client-fixture", activity="unknown")
        first = self.observe(request)
        self.observe(clientThreadId="client-fixture"); before = self.store.snapshot(); worker = self.worker()
        replay = self.observe(request)
        self.assertEqual(replay["recordHash"], first["recordHash"])
        self.assertNotEqual(replay["currentHash"], first["recordHash"])
        self.assertEqual(before, self.store.snapshot()); self.assertEqual(worker, self.worker())
        with self.assertRaisesRegex(Refusal, "reused"): self.observe({**request, "evidenceHash": "c"*64})

    def test_optimistic_concurrency_has_one_winner(self):
        one = self.observation(); two = self.observation(threadId="different")
        def record(request):
            try: return self.observe(request)["recordHash"]
            except Refusal: return "refused"
        with ThreadPoolExecutor(max_workers=2) as pool: result = list(pool.map(record, [one, two]))
        self.assertEqual(result.count("refused"), 1)

    def test_wrong_controller_or_worker_cannot_record(self):
        with self.assertRaises(Refusal): self.api.observe("wrong", self.wid, self.observation())
        with self.assertRaises(Refusal): self.api.observe(self.token, "another-worker", self.observation())

    def test_stale_future_duplicate_time_and_malformed_evidence_refuse(self):
        for fields in ({"observedAt": time.time()-1000}, {"observedAt": time.time()+1000},
                       {"threadId": True}, {"evidenceHash": "x"}, {"outcome": "complete"},
                       {"outcome": "pending"}, {"activity": "done"}, {"hostId": ""}, {"extra": "not allowed"}):
            with self.assertRaises(Refusal): self.observe(**fields)
        req = self.observation(); self.observe(req)
        with self.assertRaisesRegex(Refusal, "not newer"): self.observe(observedAt=req["observedAt"])

    def test_shared_result_commit_recovers_after_local_failure(self):
        request = self.observation()
        with patch.object(self.api, "attach_in", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.observe(request)
        self.assertIsNone(self.worker()["threadId"])
        self.assertEqual(self.claim()["native"]["threadId"], "worker-fixture")
        self.api = native_lifecycle.NativeLifecycle(DispatchAdmission(self.fx.registry, "a", AdmissionStore(self.store.root)))
        self.api.recover(self.token, self.wid)
        self.assertEqual(self.worker()["threadId"], "worker-fixture")
        before = self.store.snapshot(); self.observe(request); self.assertEqual(before, self.store.snapshot())

    def test_rollback_before_shared_commit_keeps_old_binding(self):
        original = self.api.append_in
        def fail(*args, **kwargs):
            original(*args, **kwargs); raise RuntimeError("fixture rollback")
        with patch.object(self.api, "append_in", side_effect=fail):
            with self.assertRaises(RuntimeError): self.observe()
        self.assertIsNone(self.claim()["native"]); self.assertIsNone(self.worker()["threadId"])
        with self.store.tx() as db: self.assertFalse(native_lifecycle.table_exists(db))

    def test_journal_integrity_is_checked(self):
        self.observe()
        with self.store.tx() as db:
            row = db.execute("SELECT data FROM native_records").fetchone(); data = json.loads(row[0])
            data["state"]["noProgress"] = 0
            data["state"]["sequence"] = 99
            db.execute("UPDATE native_records SET data=?", (canonical(data),))
        with self.assertRaisesRegex(Refusal, "integrity"): self.api.recover(self.token, self.wid)

    def test_foreign_native_claim_and_registered_brains_cannot_bind(self):
        with self.assertRaisesRegex(Refusal, "registered brain"): self.observe(threadId="brain-a")
        second, token, args = self.fx.second_workspace("repo-remote:"+"b"*64)
        with self.assertRaisesRegex(Refusal, "registered brain"): self.observe(threadId="brain-b")
        self.observe(); wid = second.reserve(token, **args)["workerId"]; second.begin_creation(token, wid)
        other = native_lifecycle.NativeLifecycle(second)
        request = self.observation(expectedHash=None)
        with self.assertRaisesRegex(Refusal, "another shared claim"): other.observe(token, wid, request)
        request["threadId"] = "second-native"
        other.observe(token, wid, request)
        self.assertEqual(len(self.store.snapshot()["claims"]), 2)
        with self.assertRaises(Refusal): other.observe(self.token, wid, request)

    def test_correction_keeps_same_task_and_reserves_additional_budget(self):
        self.observe(); result = self.begin()
        self.assertFalse(result["executionAuthorized"]); self.assertFalse(result["nativeCallMade"])
        self.assertEqual(self.worker()["threadId"], "worker-fixture")
        self.assertEqual(self.worker()["status"], "starting")
        self.assertEqual(self.claim()["estimatedTokens"], 12650)
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)
        with self.assertRaisesRegex(Refusal, "idle|in flight"): self.begin()

    def test_acknowledgment_is_not_completion_or_release(self):
        self.observe(); self.begin(); self.deliver()
        self.assertEqual(self.worker()["status"], "starting")
        self.assertEqual(self.state()["continuation"]["status"], "acknowledged")
        with self.assertRaises(Refusal): self.begin()
        self.deliver("finished", progress=True)
        self.assertEqual(self.worker()["status"], "running")
        self.assertEqual(self.worker()["nativeActivity"]["activity"], "idle")
        self.assertEqual(self.claim()["estimatedTokens"], 12650)
        self.assertEqual(self.ledger.snapshot()["queue"][0]["status"], "dispatched")
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)

    def test_uncertain_send_needs_reconciliation_not_resend_or_finished_guess(self):
        self.observe(); self.begin(); self.deliver("uncertain")
        with self.assertRaises(Refusal): self.begin()
        with self.assertRaisesRegex(Refusal, "Acknowledge"): self.deliver("finished")
        self.observe()  # fresh idle alone does not settle the send
        self.assertEqual(self.worker()["status"], "starting")
        self.deliver(); self.deliver("finished")
        self.assertEqual(self.worker()["noProgressCycles"], 1)

    def test_two_no_progress_corrections_block_and_replay_does_not_double_count(self):
        self.observe()
        for cycle in range(2):
            self.begin(); self.deliver(); req = self.delivery("finished"); self.deliver(request=req)
            self.assertEqual(self.worker()["noProgressCycles"], cycle+1)
            self.deliver(request=req)
            self.assertEqual(self.worker()["noProgressCycles"], cycle+1)
        self.observe()
        with self.assertRaisesRegex(Refusal, "Two no-progress"): self.begin()
        self.assertEqual(self.claim()["estimatedTokens"], 13800)

    def test_progress_resets_only_after_finished_correction_not_polling(self):
        self.observe(); self.begin(); self.deliver(); self.deliver("finished")
        self.observe(); self.assertEqual(self.worker()["noProgressCycles"], 1)
        self.begin(); self.deliver(); self.deliver("finished", progress=True)
        self.assertEqual(self.worker()["noProgressCycles"], 0)

    def test_continuation_replay_is_receipt_only_after_pause(self):
        self.observe(); request = self.correction(); first = self.begin(request)
        self.deliver(); self.fx.fx.fx.command("pause")
        before = self.store.snapshot(); replay = self.begin(request)
        self.assertEqual(replay["recordHash"], first["recordHash"])
        self.assertEqual(before, self.store.snapshot())
        self.deliver("finished")  # retaining result is safe even when authority is fenced
        with self.assertRaises(Refusal): self.begin()

    def test_current_authority_preflight_and_budget_rechecked(self):
        self.observe()
        self.fx.refresh_usage(total=79000)
        with self.assertRaisesRegex(Refusal, "headroom"): self.begin()
        self.assertEqual(self.claim().get("continuationReservedTokens", 0), 0)

    def test_expired_or_revoked_run_approval_blocks_correction(self):
        self.observe()
        with patch("orchestrator.run_authority.time.time", return_value=self.fx.grant["expiresAt"]):
            with self.assertRaisesRegex(Refusal, "expired"): self.begin()
        runs.revoke_task(self.ledger, self.fx.fx.request(queueId=self.fx.args["queue_id"],
            approvalHash=self.fx.approval["approvalHash"], reason="Fixture owner withdrawal"), actor="dashboard_owner")
        with self.assertRaises(Refusal): self.begin()
        self.assertEqual(self.claim().get("continuationReservedTokens", 0), 0)

    def test_preflight_change_between_continuation_commits_blocks_shared_advance(self):
        self.observe(); locked = self.fx.bridge.locked; calls = 0
        def interrupted(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                with self.ledger.tx() as db:
                    q = self.ledger.get(db, "queue", self.fx.args["queue_id"])
                    q["preflight"]["checks"]["locksVerified"] = False
                    self.ledger.put(db, "queue", q["id"], q)
            return locked(*args, **kwargs)
        with patch.object(self.fx.bridge, "locked", side_effect=interrupted):
            with self.assertRaisesRegex(Refusal, "locksVerified"): self.begin()
        self.assertEqual(self.worker()["status"], "starting")
        self.assertEqual(self.claim().get("continuationReservedTokens", 0), 0)

    def test_new_continuation_respects_file_only_adoption_fence(self):
        self.observe()
        path = self.store.root / "adoption-fence.json"
        path.touch(mode=0o600)  # isolated fixture; no live fence is removed
        with self.assertRaises(Refusal): self.begin()
        self.observe(activity="unknown")  # ownership observations remain available

    def test_missing_history_cannot_be_laundered(self):
        first = self.observe(); self.observe(activity="running")
        with self.store.tx() as db: db.execute("DELETE FROM native_records WHERE hash=?", (first["recordHash"],))
        with self.assertRaisesRegex(Refusal, "history is incomplete"): self.api.recover(self.token, self.wid)

    def test_missing_journal_pointer_cannot_reset_observed_identity(self):
        self.observe()
        with self.store.tx() as db:
            claim = self.store.get(db, "claims", self.wid)
            claim.pop("nativeLifecycleHash"); claim.update(native=None, status="starting")
            self.store.put(db, "claims", self.wid, claim)
        with self.assertRaisesRegex(Refusal, "pointer is missing"): self.observe(expectedHash=None)
        with self.assertRaisesRegex(Refusal, "pointer is missing"): self.api.recover(self.token, self.wid)

    def test_local_identity_and_receipt_drift_require_explicit_recovery(self):
        self.observe()
        with self.ledger.tx() as db:
            worker = self.ledger.get(db, "workers", self.wid); worker["threadId"] = "foreign-task"
            self.ledger.put(db, "workers", self.wid, worker)
        with self.assertRaisesRegex(Refusal, "identity diverged"): self.api.recover(self.token, self.wid)
        with self.ledger.tx() as db:
            worker = self.ledger.get(db, "workers", self.wid); worker["threadId"] = "worker-fixture"; worker["noProgressCycles"] = 99
            self.ledger.put(db, "workers", self.wid, worker)
        with self.assertRaisesRegex(Refusal, "receipt diverged"): self.api.recover(self.token, self.wid)

    def test_oversized_or_changed_instruction_bytes_refuse(self):
        self.observe()
        with self.ledger.tx() as db:
            huge = capture(db, "oversized", b"x"*16001, {"repository": "a", "name": "large.md", "orderAt": time.time()})
            db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"Changed", self.artifact["id"]))
        with self.assertRaisesRegex(Refusal, "bytes changed"): self.begin(instructionArtifactId=huge["id"])
        with self.assertRaisesRegex(Refusal, "bytes changed"): self.begin()

    def test_unsupported_operations_and_unretained_or_foreign_artifacts_refuse(self):
        self.observe()
        for fields in ({"operation": "test"}, {"operation": "merge"}, {"operation": "deploy"},
                       {"instructionArtifactId": "f"*64}, {"estimates": {**ESTIMATES, "workTokens": 0}}):
            with self.assertRaises(Refusal): self.begin(**fields)
        with self.ledger.tx() as db:
            other = capture(db, "foreign-artifact", b"Fixture", {"repository": "harness", "name": "foreign.md", "orderAt": time.time()})
        with self.assertRaisesRegex(Refusal, "artifact binding"): self.begin(instructionArtifactId=other["id"])

    def test_stale_idle_or_running_observation_cannot_continue(self):
        self.observe(activity="running")
        with self.assertRaisesRegex(Refusal, "idle"): self.begin()
        self.observe()
        with patch.object(self.store, "clock", return_value=time.time()+61):
            with self.assertRaisesRegex(Refusal, "Fresh"): self.begin()

    def test_unmatched_local_intent_cannot_be_erased_by_recovery_or_observation(self):
        self.observe()
        original = self.api.append_in
        def rollback(*args, **kwargs):
            original(*args, **kwargs); raise RuntimeError("fixture rollback after writes")
        with patch.object(self.api, "append_in", side_effect=rollback):
            with self.assertRaises(RuntimeError): self.begin()
        self.assertEqual(self.worker()["dispatchAdmission"]["stage"], "continuation_pending")
        self.api.recover(self.token, self.wid)
        self.assertEqual(self.worker()["status"], "starting")
        self.assertEqual(self.claim().get("continuationReservedTokens", 0), 0)
        with self.assertRaisesRegex(Refusal, "Unmatched"): self.begin()
        with self.assertRaisesRegex(Refusal, "Unmatched"): self.observe()

    def test_process_exit_after_shared_continuation_commit_recovers_once(self):
        self.observe(); request = self.correction()
        script = """
import json, os, sys
from orchestrator.admission import AdmissionStore
from orchestrator.dispatch_admission import DispatchAdmission
from orchestrator.native_lifecycle import NativeLifecycle
from orchestrator.workspaces import Registry
registry = Registry(sys.argv[1])
api = NativeLifecycle(DispatchAdmission(registry, 'a', AdmissionStore(registry.root)))
api.attach_in = lambda *args: os._exit(19)
api.begin_continuation(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]))
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.store.root), self.token, self.wid, canonical(request)],
                               capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 19, child.stderr.decode())
        self.assertEqual(self.worker()["dispatchAdmission"]["stage"], "continuation_pending")
        self.assertEqual(self.claim()["estimatedTokens"], 12650)
        self.api = native_lifecycle.NativeLifecycle(DispatchAdmission(self.fx.registry, "a", AdmissionStore(self.store.root)))
        self.api.recover(self.token, self.wid); self.begin(request)
        self.assertEqual(self.claim()["estimatedTokens"], 12650)
        self.assertEqual(self.worker()["dispatchAdmission"]["stage"], "continuation_inflight")

    def test_shared_continuation_commit_recovers_without_double_reservation(self):
        self.observe(); request = self.correction()
        with patch.object(self.api, "attach_in", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.begin(request)
        self.assertEqual(self.claim()["estimatedTokens"], 12650)
        self.fx.fx.fx.command("pause")
        self.api.recover(self.token, self.wid)
        self.begin(request)
        self.assertEqual(self.claim()["estimatedTokens"], 12650)

    def test_pause_between_continuation_commits_retains_inflight_marker(self):
        self.observe(); locked = self.fx.bridge.locked; calls = 0
        def interrupted(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3: self.fx.fx.fx.command("pause")
            return locked(*args, **kwargs)
        with patch.object(self.fx.bridge, "locked", side_effect=interrupted):
            with self.assertRaisesRegex(Refusal, "paused"): self.begin()
        self.assertEqual(self.worker()["status"], "starting")
        self.assertIsNone(self.state()["continuation"])

    def test_concurrent_corrections_have_one_winner(self):
        self.observe(); requests = [self.correction(), self.correction()]
        def begin(request):
            try: return self.begin(request)["recordHash"]
            except Refusal: return "refused"
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(begin, requests))
        self.assertEqual(results.count("refused"), 1)
        self.assertEqual(self.claim()["estimatedTokens"], 12650)

    def test_completion_must_match_native_task_intent_and_fresh_idle_evidence(self):
        self.observe(); self.begin(); self.deliver()
        for fields in ({"threadId": "different"}, {"continuationHash": "f"*64},
                       {"observedAt": time.time()-100}, {"activity": "running"}, {"progress": None}):
            with self.assertRaises(Refusal): self.deliver("finished", **fields)

    def test_new_native_observation_invalidates_retained_pause_inventory(self):
        self.observe(); stop = self.fx.fx.fx.command("brain_stop")
        self.ledger.process(self.token)
        with self.ledger.tx() as db:
            artifact = capture(db, "worker-checkpoint", b"Retained fixture checkpoint", {"repository": "a", "name": "checkpoint.md",
                "orderAt": time.time(), "references": [{"session": "worker-fixture", "at": time.time()}]})
        now = time.time()
        workspace_pause.observe(self.ledger, self.token, stop["id"], {"workspaceId": "a", "commandId": stop["id"],
            "observedAt": now, "evidenceHash": "c"*64, "complete": True, "includesDescendants": True,
            "brain": {"hostId": "local", "threadId": "brain-a"}, "tasks": [{"hostId": "local", "threadId": "worker-fixture",
                "workerId": self.wid, "parent": None, "status": "idle", "observedAt": now, "checkpointArtifactId": artifact["id"]}]})
        self.assertNotIn("ownership_changed", [b["code"] for b in self.ledger.snapshot()["workspacePause"]["blockers"]])
        self.observe(activity="running")
        self.assertIn("ownership_changed", [b["code"] for b in self.ledger.snapshot()["workspacePause"]["blockers"]])

    def test_legacy_kernel_methods_cannot_desynchronize_bound_ownership(self):
        self.observe()
        with self.assertRaisesRegex(Refusal, "coordinator"): self.store.bind(self.wid, host_id="local", thread_id="worker-fixture")
        with self.assertRaisesRegex(Refusal, "coordinator"): self.store.block(self.wid, "b"*64)
        with self.assertRaisesRegex(Refusal, "coordination"): self.store.runner(self.wid, "runner:"+"c"*64, "acquire", evidence_hash="d"*64, observed_at=time.time())
        with self.assertRaisesRegex(Refusal, "settlement"): self.store.settle(self.wid, actual=test_dispatch_admission.ZERO,
            evidence_hash="e"*64, observed_at=time.time(), outcome="terminal")
        with self.assertRaises(Refusal): self.fx.bridge.recover(self.token, self.wid)


if __name__ == "__main__": unittest.main()
