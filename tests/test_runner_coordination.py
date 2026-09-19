import json
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import ownership_settlement, run_authority as runs, runner_coordination, workspace_pause
from orchestrator.core import Refusal, canonical, digest
from orchestrator.observations import capture
import test_native_lifecycle
import test_ownership_settlement
import test_task_contracts


RUNNER = "runner:" + "d" * 64
EXTRA = {"workTokens": 1000, "reviewTokens": 100, "handoffTokens": 50}


class Rig:
    def __init__(self, bridge, token, wid, thread="worker-fixture"):
        self.api = runner_coordination.RunnerCoordination(bridge)
        self.ledger, self.store, self.token, self.wid = bridge.ledger, bridge.store, token, wid
        self.thread, self.seq = thread, 0
        with self.ledger.tx() as db:
            self.artifact = capture(db, "runner-instruction", b"Observe the pinned fixture test contract; do not run commands here.",
                {"repository": "a", "name": "runner.md", "orderAt": time.time(),
                 "references": [{"session": thread, "at": time.time()}]})
            worker, intent = bridge.intent_in(db, wid)
        self.execution = digest(self.ledger.document(intent["seedHash"])["execution"])

    def claim(self):
        with self.store.tx() as db: return self.store.get(db, "claims", self.wid)

    def worker(self):
        with self.ledger.tx() as db: return self.ledger.get(db, "workers", self.wid)

    def state(self):
        key = self.claim()["nativeLifecycleHash"]
        with self.store.tx() as db:
            return json.loads(db.execute("SELECT data FROM native_records WHERE hash=?", (key,)).fetchone()[0])["state"]

    def request(self, **fields):
        self.seq += 1
        return {"id": "runner-"+str(self.seq), "expectedHash": self.claim().get("nativeLifecycleHash"), **fields}

    def idle(self):
        return {"state": "idle", "complete": True, "cleanupObserved": True, "observedAt": time.time(), "evidenceHash": "c"*64}

    def reservation(self, **fields):
        return self.request(runnerKey=RUNNER, executionHash=self.execution, instructionArtifactId=self.artifact["id"],
                            estimates=EXTRA, observation=self.idle()) | fields

    def acquire(self, request=None, **fields): return self.api.acquire(self.token, self.wid, request or self.reservation(**fields))

    def launch(self, **fields):
        return self.request(runnerKey=RUNNER, reservationId=self.state()["runner"]["reservationId"], observation=self.idle()) | fields

    def begin(self, request=None, **fields): return self.api.begin(self.token, self.wid, request or self.launch(**fields))

    def process(self, outcome="running", **fields):
        return self.request(runnerKey=RUNNER, reservationId=self.state()["runner"]["reservationId"], hostId="local", threadId=self.thread,
            outcome=outcome, processIdentityHash=None if outcome == "uncertain" else "e"*64, exitCode=0 if outcome == "exited" else None,
            processTreeExited=outcome == "exited", observedAt=time.time(), evidenceHash="f"*64) | fields

    def observe(self, outcome="running", request=None, **fields):
        return self.api.observe_process(self.token, self.wid, request or self.process(outcome, **fields))

    def cleanup(self, outcome="exited", **fields):
        return self.request(runnerKey=RUNNER, reservationId=self.state()["runner"]["reservationId"], outcome=outcome,
            observedAt=time.time(), evidenceHash="b"*64, nativeEvidenceHash="c"*64,
            nativeIdle=True, runnerIdle=True, cleanupObserved=True, processesExited=True, complete=True) | fields

    def release(self, outcome="exited", request=None, **fields):
        return self.api.release(self.token, self.wid, request or self.cleanup(outcome, **fields))


class RunnerCoordinationTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_native_lifecycle.NativeLifecycleTest(); self.fx.runners = [RUNNER]; self.fx.setUp(); self.fx.observe()
        self.r = Rig(self.fx.fx.bridge, self.fx.token, self.fx.wid)
        self.api, self.ledger, self.store = self.r.api, self.r.ledger, self.r.store

    def tearDown(self): self.fx.tearDown()

    def other(self):
        bridge, token, args = self.fx.fx.second_workspace("repo-remote:"+"b"*64, [RUNNER])
        wid = bridge.reserve(token, **args)["workerId"]; bridge.begin_creation(token, wid)
        r = Rig(bridge, token, wid, "second-fixture")
        r.api.observe(token, wid, r.request(outcome="confirmed", hostId="local", threadId=r.thread, clientThreadId=None,
                                         activity="idle", observedAt=time.time(), evidenceHash="a"*64))
        return r

    def mutate_worker(self, **fields):
        with self.ledger.tx() as db:
            worker = self.ledger.get(db, "workers", self.r.wid); worker.update(fields)
            self.ledger.put(db, "workers", self.r.wid, worker)

    def between_launch(self, change):
        locked, calls = self.api.bridge.locked, 0
        def boundary(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 3: change()
            return locked(*args, **kwargs)
        return patch.object(self.api.bridge, "locked", side_effect=boundary)

    def crash_receipt(self):
        attach = self.api.attach_in
        def crash(db, worker, claim, record):
            if worker.get("nativeLifecycleHash") != digest(record): raise RuntimeError("fixture local receipt crash")
            return attach(db, worker, claim, record)
        return patch.object(self.api, "attach_in", side_effect=crash)

    def test_reservation_separates_runner_tokens_and_slot_from_launch(self):
        result = self.r.acquire()
        self.assertEqual(result["runnerStatus"], "reserved")
        self.assertFalse(result["executionAuthorized"]); self.assertFalse(result["nativeCallMade"])
        self.assertFalse(result["ownershipReleased"])
        self.assertEqual(self.r.worker()["status"], "awaiting_acceptance")
        self.assertEqual(self.r.claim()["status"], "running")
        self.assertEqual(self.r.claim()["estimatedTokens"], 12650)
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)
        self.assertEqual(len(self.store.snapshot()["resources"]), 2)
        self.assertEqual(self.ledger.snapshot()["meta"]["runner"]["workerId"], self.r.wid)
        self.assertNotIn("runnerLaunchIntentHash", self.r.worker())

    def test_unpinned_runner_and_invalid_estimates_refuse(self):
        for fields in ({"runnerKey": "runner:"+"a"*64}, {"runnerKey": "shell"},
                       {"estimates": {**EXTRA, "workTokens": 0}}, {"estimates": {**EXTRA, "reviewTokens": True}},
                       {"executionHash": "b"*64}, {"instructionArtifactId": "b"*64}):
            with self.subTest(fields=fields), self.assertRaises(Refusal): self.r.acquire(**fields)
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)

    def test_harness_policy_is_not_acceptance_authority(self):
        original = runner_coordination.document_in
        def harness(*args, **kwargs):
            seed = original(*args, **kwargs); seed["policyProfile"] = "harness"; return seed
        with patch.object(runner_coordination, "document_in", side_effect=harness):
            with self.assertRaisesRegex(Refusal, "trusted acceptance adapter"): self.r.acquire()

    def test_test_operation_must_be_authorized_independently(self):
        original = test_task_contracts.TaskContractTest.spec
        def edit_only(fx): return original(fx) | {"operations": ["edit"]}
        fixture = test_native_lifecycle.NativeLifecycleTest(); fixture.runners = [RUNNER]
        with patch.object(test_task_contracts.TaskContractTest, "spec", edit_only): fixture.setUp()
        try:
            fixture.observe(); r = Rig(fixture.fx.bridge, fixture.token, fixture.wid)
            with self.assertRaisesRegex(Refusal, "operation|Operation"): r.acquire()
            self.assertEqual(r.claim()["estimatedTokens"], 11500)
        finally: fixture.tearDown()

    def test_artifact_bytes_repository_and_identity_are_bound(self):
        with self.ledger.tx() as db:
            db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"changed", self.r.artifact["id"]))
        with self.assertRaisesRegex(Refusal, "instruction binding"): self.r.acquire()

    def test_positive_complete_fresh_idle_observation_required(self):
        for fields in ({"state": "unknown"}, {"complete": False}, {"cleanupObserved": 1},
                       {"observedAt": time.time()-61}, {"observedAt": time.time()+61}, {"observedAt": 0},
                       {"observedAt": float("nan")}, {"evidenceHash": "invalid"}):
            with self.subTest(fields=fields), self.assertRaises(Refusal): self.r.acquire(observation=self.r.idle() | fields)

    def test_new_observation_invalidates_old_reservation_request(self):
        request = self.r.reservation(); self.fx.observe()
        with self.assertRaisesRegex(Refusal, "journal changed"): self.r.acquire(request)

    def test_native_running_or_unknown_cannot_reserve(self):
        for activity in ("running", "unknown"):
            self.fx.observe(activity=activity)
            with self.assertRaisesRegex(Refusal, "idle native"): self.r.acquire()

    def test_inflight_correction_cannot_reserve(self):
        self.fx.begin()
        with self.assertRaises(Refusal): self.r.acquire()

    def test_budget_headroom_includes_extra_reservation(self):
        self.fx.fx.refresh_usage(total=78000)
        with self.assertRaisesRegex(Refusal, "headroom"): self.r.acquire()
        self.assertEqual(self.r.claim()["estimatedTokens"], 11500)

    def test_expired_and_revoked_authority_refuse(self):
        with patch("orchestrator.run_authority.time.time", return_value=self.fx.fx.grant["expiresAt"]):
            with self.assertRaisesRegex(Refusal, "expired"): self.r.acquire()
        runs.revoke_task(self.ledger, self.fx.fx.fx.request(queueId=self.fx.fx.args["queue_id"],
            approvalHash=self.fx.fx.approval["approvalHash"], reason="Fixture withdrawal"), actor="dashboard_owner")
        with self.assertRaises(Refusal): self.r.acquire()

    def test_two_workspaces_compete_for_one_runner(self):
        other = self.other()
        def acquire(r):
            try: return r.acquire()["runnerStatus"]
            except Refusal as error: return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(acquire, [self.r, other]))
        self.assertCountEqual(results, ["reserved", "Shared runner already owned"])
        self.assertEqual(len(self.store.snapshot()["resources"]), 3)
        self.assertEqual(sorted(c["estimatedTokens"] for c in self.store.snapshot()["claims"]), [11500, 12650])

    def test_foreign_controller_and_local_owner_refuse(self):
        with self.assertRaises(Refusal): self.api.acquire("wrong", self.r.wid, self.r.reservation())
        self.fx.fx.meta(runner={"workerId": "another"})
        with self.assertRaisesRegex(Refusal, "Local runner"): self.r.acquire()

    def test_exact_acquire_replay_does_not_reserve_twice(self):
        request = self.r.reservation(); first = self.r.acquire(request); self.r.begin()
        before = self.store.snapshot(); replay = self.r.acquire(request)
        self.assertEqual(first["recordHash"], replay["recordHash"])
        self.assertEqual(self.r.worker()["status"], "accepting")
        self.assertEqual(before, self.store.snapshot())
        with self.assertRaises(Refusal): self.r.acquire({**request, "estimates": {**EXTRA, "workTokens": 2}})

    def test_launch_is_one_shot_and_retains_all_ownership(self):
        self.r.acquire(); request = self.r.launch(); first = self.r.begin(request)
        self.assertEqual(self.r.worker()["status"], "accepting")
        self.assertEqual(self.r.claim()["status"], "starting")
        self.assertEqual(first["runnerStatus"], "launch_intent")
        self.assertFalse(first["nativeCallMade"])
        before = self.store.snapshot(); self.r.begin(request)
        self.assertEqual(before, self.store.snapshot())
        with self.assertRaisesRegex(Refusal, "already attempted"): self.r.begin()
        self.assertEqual(self.r.claim()["estimatedTokens"], 12650)

    def test_pause_between_launch_commits_retains_marker_and_blocks_retries(self):
        self.r.acquire()
        with self.between_launch(lambda: self.fx.fx.fx.fx.command("pause")):
            with self.assertRaisesRegex(Refusal, "paused"): self.r.begin()
        self.assertEqual(self.r.worker()["dispatchAdmission"]["stage"], "runner_launch_pending")
        self.assertEqual(self.r.state()["runner"]["status"], "reserved")
        self.api.recover(self.r.token, self.r.wid)
        self.assertEqual(self.r.worker()["status"], "accepting")
        with self.assertRaisesRegex(Refusal, "Unmatched"): self.r.release("unlaunched")
        with self.assertRaises(Refusal): self.fx.observe()

    def test_preflight_is_rechecked_between_launch_commits(self):
        self.r.acquire()
        def change():
            with self.ledger.tx() as db:
                q = self.ledger.get(db, "queue", self.fx.fx.args["queue_id"])
                q["preflight"]["checks"]["locksVerified"] = False
                self.ledger.put(db, "queue", q["id"], q)
        with self.between_launch(change):
            with self.assertRaisesRegex(Refusal, "locksVerified"): self.r.begin()
        self.assertEqual(self.r.worker()["status"], "accepting")

    def test_native_identity_drift_between_launch_commits_refuses(self):
        self.r.acquire()
        with self.between_launch(lambda: self.mutate_worker(threadId="changed")):
            with self.assertRaisesRegex(Refusal, "marker changed"): self.r.begin()

    def test_retained_marker_bytes_are_rechecked(self):
        self.r.acquire()
        def change():
            marker = self.r.worker()["runnerLaunchIntentHash"]
            with self.ledger.tx() as db:
                db.execute("UPDATE snapshots SET data='{}' WHERE id=?", (marker,))
        with self.between_launch(change):
            with self.assertRaises(Refusal): self.r.begin()
        with self.assertRaises(Refusal): self.api.recover(self.r.token, self.r.wid)

    def test_launch_rechecks_budget_before_marker(self):
        self.r.acquire(); self.fx.fx.refresh_usage(total=79000)
        with self.assertRaisesRegex(Refusal, "headroom"): self.r.begin()
        self.assertNotIn("runnerLaunchIntentHash", self.r.worker())

    def test_process_uncertainty_and_exit_do_not_release(self):
        self.r.acquire(); self.r.begin(); self.r.observe("uncertain")
        with self.assertRaises(Refusal): self.r.release("unlaunched")
        with self.assertRaises(Refusal): self.r.release()
        self.r.observe("running"); self.r.observe("exited", exitCode=7)
        self.assertEqual(len(self.store.snapshot()["resources"]), 2)
        self.assertEqual(self.r.worker()["status"], "accepting")
        self.assertFalse(self.ledger.snapshot()["meta"]["pilotPassed"])

    def test_process_identity_and_native_task_cannot_change(self):
        self.r.acquire(); self.r.begin(); self.r.observe()
        for fields in ({"threadId": "another"}, {"hostId": "foreign"}, {"processIdentityHash": "b"*64},
                       {"processIdentityHash": None}, {"exitCode": 0}, {"processTreeExited": True}):
            with self.subTest(fields=fields), self.assertRaises(Refusal): self.r.observe(**fields)
        with self.assertRaises(Refusal): self.r.observe("uncertain")

    def test_process_observations_require_new_finite_timestamps(self):
        self.r.acquire(); self.r.begin()
        for at in (0, time.time()-61, time.time()+61, float("nan")):
            with self.assertRaises(Refusal): self.r.observe(observedAt=at)

    def test_cleanup_requires_every_flag_and_reconciled_exit(self):
        self.r.acquire(); self.r.begin()
        with self.assertRaises(Refusal): self.r.release()
        self.r.observe("exited")
        for field in ("nativeIdle", "runnerIdle", "cleanupObserved", "processesExited", "complete"):
            for bad in (False, 1, None):
                with self.subTest(field=field, bad=bad), self.assertRaises(Refusal): self.r.release(**{field: bad})
        for at in (0, time.time()-61, time.time()+61, float("nan")):
            with self.assertRaises(Refusal): self.r.release(observedAt=at)

    def test_release_only_runner_keeps_repository_tokens_and_attempts(self):
        self.r.acquire(); self.r.begin(); self.r.observe("exited"); result = self.r.release()
        self.assertTrue(result["runnerResourceReleased"]); self.assertFalse(result["ownershipReleased"])
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)
        self.assertEqual(self.r.claim()["estimatedTokens"], 12650)
        self.assertEqual(self.r.worker()["status"], "running")
        self.assertIsNone(self.ledger.snapshot()["meta"]["runner"])
        self.assertEqual(self.r.worker()["nativeActivity"]["activity"], "idle")
        with self.assertRaisesRegex(Refusal, "One runner attempt"): self.r.acquire()

    def test_cancel_unlaunched_does_not_replenish_attempt_or_tokens(self):
        self.r.acquire(); self.r.release("unlaunched")
        self.assertNotIn("runnerLaunchIntentHash", self.r.worker())
        self.assertEqual(self.r.claim()["estimatedTokens"], 12650)
        with self.assertRaisesRegex(Refusal, "One runner attempt"): self.r.acquire()

    def test_safety_facts_and_release_after_pause_do_not_resume(self):
        self.r.acquire(); self.r.begin(); self.fx.fx.fx.fx.command("pause")
        self.r.observe("uncertain"); self.r.observe("exited"); self.r.release()
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)

    def test_maintenance_allows_facts_but_not_release(self):
        self.r.acquire(); self.r.begin(); self.fx.fx.meta(admissionBinding={"fixture": True})
        self.r.observe("exited")
        with self.assertRaisesRegex(Refusal, "maintenance fence"): self.r.release()
        self.api.recover(self.r.token, self.r.wid)
        self.assertEqual(len(self.store.snapshot()["resources"]), 2)

    def test_file_only_shared_fence_blocks_acquisition(self):
        (self.store.root / "adoption-fence.json").touch(mode=0o600)
        with self.assertRaises(Refusal): self.r.acquire()

    def test_owned_runner_blocks_native_corrections_polling_and_settlement(self):
        self.r.acquire()
        with self.assertRaises(Refusal): self.fx.begin()
        with self.assertRaises(Refusal): self.fx.observe()
        helper = self.settlement_helper()
        with self.assertRaises(Refusal): helper.settle()
        with self.assertRaises(Refusal): self.store.runner(self.r.wid, RUNNER, "release", evidence_hash="a"*64, observed_at=time.time())

    def settlement_helper(self):
        helper = test_ownership_settlement.OwnershipSettlementTest()
        helper.fx, helper.ledger, helper.token, helper.store, helper.wid = self.fx, self.ledger, self.r.token, self.store, self.r.wid
        helper.bridge, helper.api, helper.seq = self.api.bridge, ownership_settlement.OwnershipSettlement(self.api.bridge), 0
        return helper

    def test_after_release_correction_and_terminal_settlement_still_work(self):
        self.r.acquire(); self.r.begin(); self.r.observe("exited"); self.r.release()
        self.fx.begin(); self.fx.deliver(); self.fx.deliver("finished", progress=True)
        helper = self.settlement_helper(); result = helper.settle()
        self.assertTrue(result["ownershipReleased"]); self.assertFalse(result["packetAccepted"])
        self.assertEqual(self.r.claim()["estimatedTokens"], 13800)
        self.assertEqual(helper.budget()["unincorporatedSettledTokens"], 1000)
        self.assertEqual(helper.api.recover(self.r.token, self.r.wid), result)

    def test_historical_settlement_binding_keeps_its_original_shape(self):
        binding = ownership_settlement.local_binding(self.r.worker())
        self.assertNotIn("runnerBinding", binding); self.assertNotIn("runnerLaunchIntentHash", binding)
        self.assertNotIn("runnerLaunchIntentHash", workspace_pause.worker_binding(self.r.worker()))

    def test_shared_acquire_commit_recovers_once_after_local_failure(self):
        request = self.r.reservation()
        with self.crash_receipt(), self.assertRaises(RuntimeError): self.r.acquire(request)
        self.assertIsNone(self.ledger.snapshot()["meta"]["runner"])
        self.assertEqual(self.r.claim()["estimatedTokens"], 12650)
        self.api.recover(self.r.token, self.r.wid); self.r.acquire(request)
        self.assertEqual(self.r.claim()["estimatedTokens"], 12650)
        self.assertEqual(self.r.worker()["status"], "awaiting_acceptance")

    def test_shared_rollback_keeps_reservation_and_unmatched_launch(self):
        self.r.acquire(); original = self.api.append_in
        def fail(*args, **kwargs):
            original(*args, **kwargs); raise RuntimeError("fixture shared rollback")
        with patch.object(self.api, "append_in", side_effect=fail), self.assertRaises(RuntimeError): self.r.begin()
        self.assertEqual(self.r.state()["runner"]["status"], "reserved")
        self.api.recover(self.r.token, self.r.wid)
        with self.assertRaisesRegex(Refusal, "Unmatched"): self.r.begin()
        with self.assertRaises(Refusal): self.r.release("unlaunched")

    def test_release_receipt_recovery_preserves_new_shared_owner(self):
        other = self.other(); self.r.acquire()
        request = self.r.cleanup("unlaunched")
        with self.crash_receipt(), self.assertRaises(RuntimeError): self.r.release(request=request)
        other.acquire(); before = self.store.snapshot()
        self.api.recover(self.r.token, self.r.wid); self.r.release(request=request)
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(other.ledger.snapshot()["meta"]["runner"]["workerId"], other.wid)
        self.assertIsNone(self.ledger.snapshot()["meta"]["runner"])

    def test_historical_released_runner_cannot_clear_other_local_owner(self):
        self.r.acquire(); self.r.release("unlaunched")
        owner = {"workerId": "another", "key": RUNNER, "reservationId": "new", "since": time.time()}
        self.fx.fx.meta(runner=owner)
        self.fx.observe(); self.api.recover(self.r.token, self.r.wid)
        self.assertEqual(self.ledger.snapshot()["meta"]["runner"], owner)

    def test_missing_shared_runner_cannot_be_repaired_by_cleanup_claim(self):
        self.r.acquire()
        with self.store.tx() as db: db.execute("DELETE FROM resources WHERE id=?", (RUNNER,))
        with self.assertRaisesRegex(Refusal, "ownership changed"): self.r.release("unlaunched")

    def test_shared_projection_or_local_owner_drift_refuses(self):
        self.r.acquire(); self.fx.fx.meta(runner=None)
        with self.assertRaisesRegex(Refusal, "ownership diverged"): self.r.begin()

    def test_changed_local_stage_requires_explicit_recovery(self):
        self.r.acquire(); worker = self.r.worker()
        worker["dispatchAdmission"]["stage"] = "native_observed"
        self.mutate_worker(dispatchAdmission=worker["dispatchAdmission"])
        with self.assertRaisesRegex(Refusal, "receipt diverged"): self.r.begin()

    def test_concurrent_launches_have_only_one_intent(self):
        self.r.acquire(); requests = [self.r.launch(), self.r.launch()]
        def begin(request):
            try: return self.r.begin(request)["runnerStatus"]
            except Refusal: return "refused"
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(begin, requests))
        self.assertCountEqual(results, ["launch_intent", "refused"])
        self.assertEqual(self.r.claim()["estimatedTokens"], 12650)

    def test_release_rollback_preserves_both_owners_and_token_hold(self):
        self.r.acquire(); before = self.store.snapshot(); original = self.api.append_in
        def fail(*args, **kwargs):
            original(*args, **kwargs); raise RuntimeError("fixture release rollback")
        with patch.object(self.api, "append_in", side_effect=fail), self.assertRaises(RuntimeError): self.r.release("unlaunched")
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(self.r.worker()["status"], "awaiting_acceptance")
        self.assertEqual(self.ledger.snapshot()["meta"]["runner"]["workerId"], self.r.wid)

    def test_release_replay_ignores_expired_evidence_and_later_fence(self):
        self.r.acquire(); request = self.r.cleanup("unlaunched"); result = self.r.release(request=request)
        self.fx.fx.meta(admissionBinding={"fixture": True}); before = self.store.snapshot()
        with patch.object(self.store, "clock", return_value=time.time()+1000):
            self.assertEqual(self.r.release(request=request), result)
        self.assertEqual(before, self.store.snapshot())

    def test_budget_drift_between_launch_commits_leaves_inflight_marker(self):
        self.r.acquire()
        with self.between_launch(lambda: self.fx.fx.refresh_usage(total=79000)):
            with self.assertRaisesRegex(Refusal, "headroom"): self.r.begin()
        self.assertEqual(self.r.worker()["dispatchAdmission"]["stage"], "runner_launch_pending")
        with self.assertRaisesRegex(Refusal, "Unmatched"): self.r.release("unlaunched")

    def test_subprocess_crashes_at_each_shared_commit_recover_without_effects(self):
        for method, request_fn in (("acquire", self.r.reservation), ("begin", self.r.launch),
                                   ("observe_process", lambda: self.r.process("exited")), ("release", self.r.cleanup)):
            request = request_fn()
            script = """
import json, os, sys
from orchestrator.admission import AdmissionStore
from orchestrator.core import digest
from orchestrator.dispatch_admission import DispatchAdmission
from orchestrator.runner_coordination import RunnerCoordination
from orchestrator.workspaces import Registry
registry = Registry(sys.argv[1])
api = RunnerCoordination(DispatchAdmission(registry, 'a', AdmissionStore(registry.root)))
original = api.attach_in
def crash(db, worker, claim, record):
    if worker.get('nativeLifecycleHash') != digest(record): os._exit(19)
    return original(db, worker, claim, record)
api.attach_in = crash
getattr(api, sys.argv[4])(sys.argv[2], sys.argv[3], json.loads(sys.argv[5]))
"""
            child = subprocess.run([sys.executable, "-c", script, str(self.store.root), self.r.token, self.r.wid, method, canonical(request)],
                                   capture_output=True, timeout=15)
            self.assertEqual(child.returncode, 19, child.stderr.decode())
            before = self.store.snapshot()
            self.api.recover(self.r.token, self.r.wid)
            getattr(self.api, method)(self.r.token, self.r.wid, request)
            self.assertEqual(before, self.store.snapshot())
        self.assertEqual(self.r.claim()["estimatedTokens"], 12650)
        self.assertIsNone(self.ledger.snapshot()["meta"]["runner"])

    def test_stop_cannot_park_while_runner_is_owned(self):
        self.r.acquire(); self.r.begin(); self.fx.fx.fx.fx.command("brain_stop")
        blockers = [b["code"] for b in self.ledger.snapshot()["workspacePause"]["blockers"]]
        self.assertIn("worker_effect_inflight", blockers)
        self.assertTrue(self.ledger.snapshot()["meta"]["runner"])


if __name__ == "__main__": unittest.main()
