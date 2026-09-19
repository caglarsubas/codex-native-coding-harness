import copy
import json
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import creation_recovery, ownership_settlement, run_authority as runs, workspace_pause
from orchestrator.core import Refusal, canonical, digest
from orchestrator.native_lifecycle import NativeLifecycle
from orchestrator.observations import capture
import test_dispatch_admission


class CreationRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_dispatch_admission.DispatchAdmissionTest(); self.fx.setUp()
        self.ledger, self.token, self.store = self.fx.ledger, self.fx.token, self.fx.store
        self.wid = self.fx.reserve()["workerId"]
        self.api = creation_recovery.CreationRecovery(self.fx.bridge)
        self.native = NativeLifecycle(self.fx.bridge)
        self.seq = 0

    def tearDown(self): self.fx.tearDown()
    def worker(self):
        with self.ledger.tx() as db: return self.ledger.get(db, "workers", self.wid)
    def claim(self):
        with self.store.tx() as db: return self.store.get(db, "claims", self.wid)
    def begin(self): return self.fx.begin(self.wid)
    def inspect(self): return self.api.inspect(self.token, self.wid)
    def budget(self):
        return next(a["budget"] for a in self.store.snapshot()["allocations"] if a["id"] == self.fx.binding["id"])
    def mutate_worker(self, **fields):
        with self.ledger.tx() as db:
            worker = self.ledger.get(db, "workers", self.wid); worker.update(fields)
            self.ledger.put(db, "workers", self.wid, worker)
    def observe(self, **fields):
        self.seq += 1
        return self.native.observe(self.token, self.wid, {"id": "observe-"+str(self.seq),
            "expectedHash": self.claim().get("nativeLifecycleHash"), "outcome": "pending", "hostId": "local",
            "threadId": None, "clientThreadId": "client-fixture", "activity": "unknown", "observedAt": time.time(),
            "evidenceHash": "c"*64} | fields)
    def evidence(self):
        candidate = self.inspect(); self.seq += 1
        with self.ledger.tx() as db:
            artifact = capture(db, "absence-"+str(self.seq), b"Fixture final creation result and independently reconciled absence.",
                {"repository": "a", "name": "non-creation.md", "orderAt": time.time(),
                 "references": [{"workerId": self.wid, "intentHash": candidate["intentHash"], "at": time.time()}]})
        return {"id": "close-"+str(self.seq), "expectedHash": candidate["sourceHash"], "reconciliationArtifactId": artifact["id"],
            "inventory": {"intentHash": candidate["intentHash"], "hostId": candidate["hostId"], "clientThreadId": candidate["clientThreadId"],
                "outcome": "not_created", "requestFinal": True, "complete": True, "includesDescendants": True,
                "pendingResolved": True, "effectsComplete": True, "tasks": [], "observedAt": time.time(), "evidenceHash": "a"*64},
            "resources": [{"key": test_dispatch_admission.KEY, "processesExited": True, "cleanupObserved": True,
                           "observedAt": time.time(), "evidenceHash": "b"*64}],
            "usage": {"intentHash": candidate["intentHash"], "counterEpoch": "e"*64, "counters": dict(test_dispatch_admission.ZERO),
                      "complete": True, "observedAt": time.time(), "evidenceHash": "f"*64}}
    def settle(self, request=None): return self.api.settle(self.token, self.wid, request or self.evidence())
    def local_only(self):
        locked, count = self.fx.bridge.locked, 0
        def fail(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2: raise RuntimeError("fixture gap before shared creation")
            return locked(*args, **kwargs)
        with patch.object(self.fx.bridge, "locked", side_effect=fail), self.assertRaises(RuntimeError): self.begin()
    def pause_inventory(self, tasks=()):
        stop = self.fx.fx.fx.command("brain_stop"); self.ledger.process(self.token)
        result = workspace_pause.observe(self.ledger, self.token, stop["id"], {"workspaceId": "a", "commandId": stop["id"],
            "observedAt": time.time(), "evidenceHash": "a"*64, "complete": True, "includesDescendants": True,
            "brain": {"hostId": "local", "threadId": "brain-a"}, "tasks": list(tasks)})
        return stop, result
    def task(self, thread="unexpected", worker=True):
        return {"hostId": "local", "threadId": thread, "workerId": self.wid if worker else None,
                "parent": None if worker else {"hostId": "local", "threadId": "brain-a"}, "status": "idle",
                "observedAt": time.time(), "checkpointArtifactId": None}

    def test_shared_boundary_settles_without_claiming_acceptance_or_retry(self):
        self.begin(); before = self.worker(); result = self.settle()
        self.assertTrue(result["ownershipReleased"]); self.assertFalse(result["executionAuthorized"])
        self.assertFalse(result["nativeCallMade"]); self.assertFalse(result["retryAuthorized"]); self.assertFalse(result["packetAccepted"])
        self.assertEqual(result["creationOutcome"], "not_created"); self.assertEqual(result["actualTokens"], 0)
        self.assertEqual(self.claim()["status"], "settled"); self.assertEqual(self.worker()["status"], "settled")
        self.assertEqual(self.store.snapshot()["resources"], [])
        self.assertEqual(self.worker()["evidence"], before["evidence"])
        self.assertFalse(self.worker()["archived"]); self.assertFalse(self.worker()["preserved"])
        self.assertTrue(self.ledger.snapshot()["queue"][0]["held"])
        self.assertIn("no retry", self.ledger.snapshot()["queue"][0]["reason"])
        self.assertFalse(self.ledger.snapshot()["meta"]["pilotPassed"])

    def test_local_first_boundary_can_be_closed_without_advancing_creation(self):
        self.local_only(); self.assertEqual(self.claim()["status"], "reserved")
        self.assertEqual(self.worker()["dispatchAdmission"]["stage"], "creation_pending")
        self.settle(); self.assertNotIn("startedAt", self.claim())
        self.assertEqual(self.claim()["status"], "settled")
        self.assertEqual(self.api.recover(self.token, self.wid)["creationOutcome"], "not_created")

    def test_pending_client_and_uncertainty_retained_after_closure(self):
        self.begin(); self.observe(); self.observe(outcome="uncertain")
        before = self.claim(); self.settle()
        self.assertEqual(self.claim()["clientNative"], before["clientNative"])
        self.assertEqual(self.worker()["clientThreadId"], "client-fixture")
        self.assertEqual(self.claim()["nativeLifecycleHash"], before["nativeLifecycleHash"])
        self.assertIsNone(self.worker()["threadId"])

    def test_unconfirmed_uncertainty_without_client_id_can_close(self):
        self.begin(); self.observe(outcome="uncertain", clientThreadId=None); self.settle()
        self.assertEqual(self.claim()["creationOutcome"], "not_created")

    def test_inspection_is_read_only_and_does_not_claim_absence(self):
        self.begin(); before = self.store.snapshot(); local = self.fx.fx.fx.logical()
        first = self.inspect(); second = self.inspect()
        self.assertEqual(first, second); self.assertTrue(first["reconciliationRequired"])
        self.assertFalse(first["ownershipReleased"])
        self.assertEqual(before, self.store.snapshot()); self.assertEqual(local, self.fx.fx.fx.logical())
        with self.store.tx() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='ownership_settlements'").fetchone())
        with self.assertRaises(Refusal): self.api.recover(self.token, self.wid)

    def test_unattempted_reservation_refuses(self):
        with self.assertRaisesRegex(Refusal, "attempted creation"): self.inspect()
        self.assertEqual(self.claim()["status"], "reserved")

    def test_missing_shared_claim_never_recreated(self):
        self.local_only()
        with self.store.tx() as db: db.execute("DELETE FROM claims WHERE id=?", (self.wid,))
        with self.assertRaises(Refusal): self.inspect()
        self.assertEqual(len(self.store.snapshot()["claims"]), 0)
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)

    def test_confirmed_task_never_becomes_not_created(self):
        self.begin(); request = self.evidence()
        self.observe(outcome="confirmed", threadId="real-task", activity="idle", clientThreadId=None)
        with self.assertRaisesRegex(Refusal, "Known native work"): self.settle(request)
        self.observe(outcome="uncertain", threadId="real-task", clientThreadId=None)
        with self.assertRaises(Refusal): self.settle(request)

    def test_inventory_must_be_explicit_final_complete_and_empty(self):
        self.begin(); original = self.evidence()
        for field in ("requestFinal", "complete", "includesDescendants", "pendingResolved", "effectsComplete"):
            for value in (False, None, 1):
                changed = copy.deepcopy(original); changed["inventory"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(Refusal): self.settle(changed)
        for key, value in (("outcome", "unknown"), ("tasks", [self.task()]), ("tasks", None)):
            changed = copy.deepcopy(original); changed["inventory"][key] = value
            with self.assertRaises(Refusal): self.settle(changed)
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)

    def test_exact_intent_host_pending_id_and_usage_epoch_required(self):
        self.begin(); self.observe(); original = self.evidence()
        for group, field, value in (("inventory", "hostId", "other"), ("inventory", "clientThreadId", None),
                ("inventory", "clientThreadId", "different"), ("inventory", "intentHash", "b"*64),
                ("usage", "intentHash", "b"*64), ("usage", "counterEpoch", None)):
            changed = copy.deepcopy(original); changed[group][field] = value
            with self.subTest(field=field), self.assertRaises(Refusal): self.settle(changed)

    def test_missing_nonzero_or_partial_usage_is_not_zero(self):
        self.begin(); original = self.evidence()
        for change in ({"counters": None}, {"complete": False}, {"counters": {}},
                       {"counters": {**test_dispatch_admission.ZERO, "inputTokens": 1}},
                       {"counters": {**test_dispatch_admission.ZERO, "outputTokens": True}},
                       {"counters": {**test_dispatch_admission.ZERO, "cachedInputTokens": 1}}):
            changed = copy.deepcopy(original); changed["usage"].update(change)
            with self.subTest(change=change), self.assertRaises(Refusal): self.settle(changed)

    def test_exact_fresh_resource_cleanup_required(self):
        self.begin(); original = self.evidence()
        for values in ([], original["resources"]*2, [{**original["resources"][0], "key": "repo-remote:"+"f"*64}],
                       [{**original["resources"][0], "processesExited": False}], [{**original["resources"][0], "cleanupObserved": 1}]):
            with self.subTest(values=values), self.assertRaises(Refusal): self.settle({**original, "resources": values})

    def test_evidence_times_finite_fresh_ordered_and_post_attempt(self):
        self.begin(); original = self.evidence()
        for group in ("inventory", "usage", "resources"):
            for at in (0, time.time()-61, time.time()+61, float("nan")):
                changed = copy.deepcopy(original)
                row = changed[group][0] if group == "resources" else changed[group]; row["observedAt"] = at
                with self.subTest(group=group, at=at), self.assertRaises(Refusal): self.settle(changed)
        changed = copy.deepcopy(original); changed["usage"]["observedAt"] = original["inventory"]["observedAt"] - .001
        with self.assertRaisesRegex(Refusal, "predates"): self.settle(changed)

    def test_new_native_observation_invalidates_candidate_hash(self):
        self.begin(); self.observe(); request = self.evidence(); self.observe()
        with self.assertRaisesRegex(Refusal, "source changed"): self.settle(request)
        self.settle()

    def test_partial_native_receipt_requires_recovery_first(self):
        self.begin()
        with patch.object(self.native, "attach_in", side_effect=RuntimeError("fixture gap")), self.assertRaises(RuntimeError): self.observe()
        with self.assertRaisesRegex(Refusal, "receipt first"): self.inspect()
        self.native.recover(self.token, self.wid); self.settle()

    def test_partial_creation_receipt_requires_recovery_first(self):
        with patch.object(self.fx.bridge, "attach_in", side_effect=RuntimeError("fixture gap")), self.assertRaises(RuntimeError): self.begin()
        with self.assertRaisesRegex(Refusal, "receipt first"): self.inspect()
        self.fx.bridge.recover(self.token, self.wid); self.settle()

    def test_artifact_missing_changed_wrong_scope_or_old_refuses(self):
        self.begin(); request = self.evidence(); key = request["reconciliationArtifactId"]
        with self.ledger.tx() as db:
            row = db.execute("SELECT data,content FROM artifact_versions WHERE id=?", (key,)).fetchone()
        original = json.loads(row[0])
        for changes in ({"repository": "other"}, {"references": []}, {"observedAt": self.claim()["createdAt"]-1}, {"id": "f"*64}):
            with self.ledger.tx() as db: db.execute("UPDATE artifact_versions SET data=? WHERE id=?", (canonical(original | changes), key))
            with self.assertRaises(Refusal): self.settle(request)
        with self.ledger.tx() as db: db.execute("UPDATE artifact_versions SET data=?,content=? WHERE id=?", (canonical(original), b"modified", key))
        with self.assertRaisesRegex(Refusal, "bytes or version"): self.settle(request)
        with self.assertRaises(Refusal): self.settle({**request, "reconciliationArtifactId": "a"*64})

    def test_oversized_artifact_and_request_refuse(self):
        self.begin(); request = self.evidence()
        with self.ledger.tx() as db: db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"x"*16001, request["reconciliationArtifactId"]))
        with self.assertRaises(Refusal): self.settle(request)
        with self.assertRaises(Refusal): self.settle({**request, "extra": "x"*16000})

    def test_prior_pause_native_observation_contradicts_absence(self):
        self.begin(); request = self.evidence(); self.pause_inventory([self.task()])
        with self.assertRaisesRegex(Refusal, "Previously observed tasks"): self.settle(request)

    def test_pending_client_used_as_task_is_a_contradiction(self):
        self.begin(); self.observe(); request = self.evidence(); self.pause_inventory([self.task("client-fixture", worker=False)])
        with self.assertRaisesRegex(Refusal, "Previously observed tasks"): self.settle(request)

    def test_retained_stop_binding_cannot_disappear(self):
        self.begin(); request = self.evidence()
        self.fx.meta(brainControl={"retainedWorkers": [{"id": self.wid, "threadId": "known-task"}]})
        with self.assertRaisesRegex(Refusal, "Pause retained"): self.settle(request)

    def test_usage_history_and_attempts_not_reset(self):
        self.begin(); self.fx.refresh_usage(total=1234); self.settle()
        self.assertEqual(self.budget()["observedTokens"], 1234)
        self.assertEqual(self.budget()["heldTokens"], 0)
        self.assertEqual(self.budget()["remainingForNewWork"], 88766)
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)
        self.assertEqual(self.claim()["estimatedTokens"], 11500)
        self.store.observe_usage(self.fx.binding["id"], {"observedAt": time.time(), "evidenceHash": "b"*64,
            "counters": {**test_dispatch_admission.ZERO, "inputTokens": 1234}, "coverage": ["brain", "workers", "reviews"], "settledClaimIds": [self.wid]})
        self.assertEqual(self.budget()["observedTokens"], 1234)

    def test_settled_attempt_never_reopened_through_old_paths(self):
        self.begin(); self.settle()
        for action in (self.fx.reserve, self.begin, lambda: self.fx.bridge.recover(self.token, self.wid), self.observe,
                       lambda: self.native.recover(self.token, self.wid), lambda: self.store.begin(self.wid)):
            with self.subTest(action=action), self.assertRaises(Refusal): action()
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)

    def test_final_client_identity_cannot_bind_another_workspace(self):
        self.begin(); self.observe(); self.settle()
        bridge, token, args = self.fx.second_workspace("repo-remote:"+"b"*64)
        wid = bridge.reserve(token, **args)["workerId"]; bridge.begin_creation(token, wid)
        api = NativeLifecycle(bridge)
        with self.assertRaisesRegex(Refusal, "another shared claim"):
            api.observe(token, wid, {"id": "other", "expectedHash": None, "outcome": "confirmed", "hostId": "local", "threadId": "client-fixture",
                                    "clientThreadId": None, "activity": "idle", "observedAt": time.time(), "evidenceHash": "a"*64})

    def test_pause_expired_approval_or_exhausted_budget_do_not_prevent_accounting(self):
        self.begin(); self.fx.fx.fx.command("pause"); self.fx.refresh_usage(total=100000)
        runs.revoke_task(self.ledger, self.fx.fx.request(queueId=self.fx.args["queue_id"],
            approvalHash=self.fx.approval["approvalHash"], reason="Fixture withdrawal"), actor="dashboard_owner")
        self.settle(); self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertLess(self.budget()["remainingForNewWork"], 0)

    def test_maintenance_fences_block_new_release_but_not_committed_recovery(self):
        self.begin(); request = self.evidence(); self.fx.meta(admissionBinding={"fixture": True})
        with self.assertRaisesRegex(Refusal, "maintenance fence"): self.settle(request)
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)

    def test_file_only_shared_fence_blocks_release(self):
        self.begin(); request = self.evidence(); (self.store.root / "adoption-fence.json").touch(mode=0o600)
        with self.assertRaises(Refusal): self.settle(request)
        self.assertTrue(self.inspect()["reconciliationRequired"])

    def test_wrong_controller_worker_or_allocation_refuses(self):
        self.begin(); request = self.evidence()
        with self.assertRaises(Refusal): self.api.settle("wrong", self.wid, request)
        with self.assertRaises(Refusal): self.api.settle(self.token, "wrong-worker", request)
        with self.store.tx() as db:
            allocation = self.store.get(db, "allocations", self.fx.binding["id"]); allocation["spec"]["limits"]["tokenBudget"] += 1
            self.store.put(db, "allocations", allocation["id"], allocation)
        with self.assertRaisesRegex(Refusal, "allocation changed"): self.settle(request)

    def test_worker_controls_and_local_runner_block(self):
        self.begin(); request = self.evidence()
        # Public controls already refuse unresolved task IDs. Simulate a retained
        # in-flight control from interrupted recovery; it must remain a blocker.
        cmd = {"id": "retained-control", "kind": "checkpoint", "status": "processing", "payload": {"workerId": self.wid}}
        with self.ledger.tx() as db: self.ledger.put(db, "commands", cmd["id"], cmd)
        with self.assertRaisesRegex(Refusal, "control"): self.settle(request)
        cmd["status"] = "failed"
        with self.ledger.tx() as db: self.ledger.put(db, "commands", cmd["id"], cmd)
        self.fx.meta(runner={"workerId": "other"})
        with self.assertRaisesRegex(Refusal, "runner"): self.settle(request)

    def test_unmatched_continuation_or_runner_marker_refuses(self):
        self.begin(); request = self.evidence()
        for field in ("nativeContinuationIntentHash", "runnerLaunchIntentHash"):
            self.mutate_worker(**{field: "a"*64})
            with self.assertRaisesRegex(Refusal, "Local native work"): self.settle(request)
            self.mutate_worker(**{field: None})

    def test_exact_replay_and_conflicting_request(self):
        self.begin(); request = self.evidence(); result = self.settle(request); before = self.store.snapshot()
        with patch.object(self.store, "clock", return_value=time.time()+1000):
            self.assertEqual(self.settle(request), result); self.assertEqual(self.api.recover(self.token, self.wid), result)
        self.assertEqual(before, self.store.snapshot())
        with self.assertRaisesRegex(Refusal, "different evidence"): self.settle({**request, "id": "different"})

    def test_terminal_coordinators_cannot_cross_outcomes(self):
        self.begin(); self.settle()
        with self.assertRaisesRegex(Refusal, "exact terminal outcome"):
            ownership_settlement.OwnershipSettlement(self.fx.bridge).recover(self.token, self.wid)

    def test_concurrent_closures_release_once(self):
        self.begin(); requests = [self.evidence(), self.evidence()]
        def settle(request):
            try: return self.settle(request)["creationOutcome"]
            except Refusal: return "refused"
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(settle, requests))
        self.assertCountEqual(results, ["not_created", "refused"])
        with self.store.tx() as db: self.assertEqual(db.execute("SELECT count(*) FROM ownership_settlements").fetchone()[0], 1)

    def test_shared_commit_rollback_retains_every_owner(self):
        self.begin(); request = self.evidence(); before = self.store.snapshot(); commit = self.api.commit_in
        def fail(*args): commit(*args); raise RuntimeError("fixture shared rollback")
        with patch.object(self.api, "commit_in", side_effect=fail), self.assertRaises(RuntimeError): self.settle(request)
        self.assertEqual(before, self.store.snapshot()); self.assertEqual(self.worker()["status"], "starting")

    def test_local_receipt_recovery_never_releases_new_workspace_owner(self):
        self.begin(); request = self.evidence()
        bridge, token, args = self.fx.second_workspace(test_dispatch_admission.KEY)
        with self.assertRaisesRegex(Refusal, "already owned"): bridge.reserve(token, **args)
        with patch.object(self.api, "attach_in", side_effect=RuntimeError("fixture gap")), self.assertRaises(RuntimeError): self.settle(request)
        new_worker = bridge.reserve(token, **args)["workerId"]
        before = self.store.snapshot(); self.api.recover(self.token, self.wid); self.settle(request)
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(self.store.snapshot()["resources"][0]["claimId"], new_worker)

    def test_process_exit_after_shared_commit_recovers_once(self):
        self.begin(); self.observe(); request = self.evidence()
        script = """
import json, os, sys
from orchestrator.admission import AdmissionStore
from orchestrator.creation_recovery import CreationRecovery
from orchestrator.dispatch_admission import DispatchAdmission
from orchestrator.workspaces import Registry
registry = Registry(sys.argv[1])
api = CreationRecovery(DispatchAdmission(registry, 'a', AdmissionStore(registry.root)))
api.attach_in = lambda *args: os._exit(29)
api.settle(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]))
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.store.root), self.token, self.wid, canonical(request)],
                               capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 29, child.stderr.decode())
        self.assertEqual(self.claim()["status"], "settled"); self.assertEqual(self.worker()["status"], "starting")
        (self.ledger.root / "admission-fence.json").touch(mode=0o600)
        with self.assertRaises(Refusal): self.settle(request)
        before = self.store.snapshot(); self.api.recover(self.token, self.wid)
        self.assertEqual(before, self.store.snapshot()); self.assertEqual(self.worker()["status"], "settled")

    def test_missing_or_corrupt_terminal_history_never_reopens_claim(self):
        self.begin(); self.settle()
        with self.store.tx() as db: db.execute("UPDATE ownership_settlements SET data='{}'")
        with self.assertRaisesRegex(Refusal, "integrity"): self.api.recover(self.token, self.wid)
        with self.assertRaises(Refusal): self.begin()

    def test_deep_native_history_is_verified_during_recovery(self):
        self.begin(); first = self.observe(); self.observe(); self.observe(); self.settle()
        with self.store.tx() as db: db.execute("UPDATE native_records SET data='{}' WHERE hash=?", (first["recordHash"],))
        with self.assertRaisesRegex(Refusal, "integrity"): self.api.recover(self.token, self.wid)

    def test_changed_local_receipt_is_not_overwritten(self):
        self.begin(); self.settle(); self.mutate_worker(clientThreadId="changed")
        with self.assertRaisesRegex(Refusal, "receipt diverged"): self.api.recover(self.token, self.wid)

    def test_noncreation_receipt_removes_only_nonexistent_task_pause_requirement(self):
        self.begin(); self.observe(); self.settle(); self.pause_inventory()
        status = self.ledger.snapshot()["workspacePause"]
        self.assertTrue(status["readyToPark"], status["blockers"])
        self.assertEqual(status["retainedWorkers"], 1)
        self.assertEqual(self.worker()["clientThreadId"], "client-fixture")

    def test_empty_pause_inventory_before_settlement_still_blocks(self):
        self.begin(); self.observe(); self.pause_inventory()
        status = self.ledger.snapshot()["workspacePause"]
        self.assertFalse(status["readyToPark"])
        self.assertIn("worker_observation_missing", [b["code"] for b in status["blockers"]])

    def test_contradictory_task_after_noncreation_blocks_pause(self):
        self.begin(); self.observe(); self.settle(); self.pause_inventory([self.task()])
        self.assertIn("creation_recovery_conflict", [b["code"] for b in self.ledger.snapshot()["workspacePause"]["blockers"]])

    def test_missing_local_proof_cannot_bypass_pause_by_status(self):
        self.begin(); self.settle(); key = self.worker()["ownershipSettlementHash"]
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (key,))
        self.pause_inventory()
        self.assertIn("worker_observation_missing", [b["code"] for b in self.ledger.snapshot()["workspacePause"]["blockers"]])

    def test_missing_reconciliation_bytes_block_pause_and_receipt_recovery(self):
        self.begin(); request = self.evidence(); self.settle(request)
        with self.ledger.tx() as db: db.execute("DELETE FROM artifact_versions WHERE id=?", (request["reconciliationArtifactId"],))
        with self.assertRaisesRegex(Refusal, "artifact required"): self.api.recover(self.token, self.wid)
        self.pause_inventory()
        self.assertIn("worker_observation_missing", [b["code"] for b in self.ledger.snapshot()["workspacePause"]["blockers"]])

    def test_settlement_invalidates_prior_pause_inventory(self):
        self.begin(); stop, _ = self.pause_inventory(); self.settle()
        self.assertIn("ownership_changed", [b["code"] for b in self.ledger.snapshot()["workspacePause"]["blockers"]])
        workspace_pause.observe(self.ledger, self.token, stop["id"], {"workspaceId": "a", "commandId": stop["id"],
            "observedAt": time.time(), "evidenceHash": "b"*64, "complete": True, "includesDescendants": True,
            "brain": {"hostId": "local", "threadId": "brain-a"}, "tasks": []})
        self.assertTrue(self.ledger.snapshot()["workspacePause"]["readyToPark"])

    def test_local_event_failure_keeps_committed_settlement_recoverable(self):
        self.begin(); request = self.evidence(); event = self.api.ledger.event
        def fail(db, kind, data):
            event(db, kind, data)
            if kind == "ownership_settlement_attached": raise RuntimeError("fixture local rollback")
        with patch.object(self.api.ledger, "event", side_effect=fail), self.assertRaises(RuntimeError): self.settle(request)
        self.assertEqual(self.claim()["status"], "settled"); self.assertEqual(self.worker()["status"], "starting")
        self.api.recover(self.token, self.wid); self.assertTrue(self.ledger.snapshot()["queue"][0]["held"])

    def test_noncreation_is_settled_but_never_completed_in_portfolio(self):
        self.begin(); self.settle(); summary = self.fx.registry.summary({"a"})
        self.assertEqual(summary["aggregate"]["settledTasks"], 1)
        self.assertEqual(summary["aggregate"]["completedTasks"], 0)


if __name__ == "__main__": unittest.main()
