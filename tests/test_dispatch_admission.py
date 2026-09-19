import copy
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import dispatch_admission as dispatch, missions, run_authority as runs, task_contracts
from orchestrator.admission import AdmissionStore
from orchestrator.core import Ledger, PREFLIGHT_CHECKS, Refusal, digest
import test_core
import test_missions
import test_run_authority


POLICY = {"maxParallelTasks": 2, "maxObservationAgeSeconds": 60, "minAccountRemainingPercent": 10}
KEY = "repo-remote:" + "a"*64
ESTIMATES = {"workTokens": 10000, "reviewTokens": 1000, "handoffTokens": 500}
ZERO = {"inputTokens": 0, "cachedInputTokens": 0, "outputTokens": 0, "reasoningOutputTokens": 0}


class DispatchAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_run_authority.RunAuthorityTest(); self.fx.setUp()
        self.ledger, self.token = self.fx.ledger, self.fx.token
        self.registry = self.fx.fx.registry
        self.run = self.fx.authorize(); self.approval = self.fx.approve(self.run)
        self.grant = self.ledger.document(self.run["runHash"])
        self.store = AdmissionStore(self.registry.root, policy=POLICY)
        self.binding = dispatch.phase_allocation(self.grant, {"a": [KEY]})
        spec = self.binding["spec"]
        self.store.open_allocation(self.binding["id"], workspace_id="a", binding_hash=spec["bindingHash"],
            limits=spec["limits"], repositories=spec["repositories"], runners=spec["runners"])
        self.refresh_usage()
        self.preflight()
        # Deliberate isolated fixture activation only. No production route exists.
        self.meta(paused=False)
        self.bridge = dispatch.DispatchAdmission(self.registry, "a", self.store)
        self.args = {"run_hash": self.run["runHash"], "queue_id": self.fx.fx.q["id"],
                     "approval_hash": self.approval["approvalHash"], "estimates": ESTIMATES}

    def tearDown(self): self.fx.tearDown()

    def meta(self, **fields):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta.update(fields); self.ledger.put(db, "meta", 1, meta)

    def preflight(self):
        q = self.fx.fx.q
        self.ledger.preflight(self.token, q["id"], {"seedHash": q["seedHash"], "packetDigest": q["packetDigest"],
            "baseSHA": "c"*40, "projectId": "project-a", "checks": {k: True for k in PREFLIGHT_CHECKS}, "evidence": ["fixture"]})

    def refresh_usage(self, total=0, coverage=None):
        now = time.time()
        self.store.observe_account({"observedAt": now, "evidenceHash": "a"*64,
            "windows": {k: {"usedPercent": 10, "resetsAt": now+3600} for k in ("short", "long")}})
        self.store.observe_usage(self.binding["id"], {"observedAt": now, "evidenceHash": "b"*64,
            "counters": {**ZERO, "inputTokens": total}, "coverage": coverage if coverage is not None else ["brain", "workers", "reviews"],
            "settledClaimIds": []})

    def reserve(self, **fields): return self.bridge.reserve(self.token, **{**self.args, **fields})
    def worker(self): return self.ledger.snapshot()["workers"][0]
    def claim(self): return self.store.snapshot()["claims"][0]
    def begin(self, wid=None): return self.bridge.begin_creation(self.token, wid or self.worker()["id"])

    def second_workspace(self, resource_key):
        ledger = Ledger(self.registry.root.parent / "second")
        ledger.initialize({"schemaVersion": 1, "brainId": "brain-b", "repositories": [
            {"id": "a", "path": "/fixture/b", "projectId": "project-b", "ref": "origin/main",
             "mergePolicy": "manual", "policyProfile": "standard"}]})
        self.registry.register("b", "Project B", ledger.root); ledger = self.registry.ledger("b")
        spec = test_missions.specification(); spec["phase"]["scope"][0]["allowedPaths"] = ["src/**", "tests/test_fixture.py"]
        mission = missions.change(ledger, test_missions.request(spec=spec))["current"]
        mission = missions.change(ledger, test_missions.request("review", mission["revision"],
            documentHash=mission["documentHash"], confirmed=True))["current"]
        q = ledger.prepare(test_core.seed(profile="standard")); token = ledger.acquire("brain-b:fixture")
        spec = self.fx.fx.spec(); spec.update(missionHash=mission["documentHash"], reviewReceiptHash=mission["receiptHash"])
        def request(**fields):
            return {"id": "second-"+str(ledger.snapshot()["meta"]["revision"]),
                    "expectedRevision": ledger.snapshot()["meta"]["revision"], **fields}
        contract = task_contracts.propose(ledger, token, request(spec=spec))
        run = runs.authorize(ledger, request(missionHash=mission["documentHash"], reviewReceiptHash=mission["receiptHash"],
            checkpointHash=None, expiresAt=time.time()+3600, settingsPolicy="native_defaults", confirmed=True), actor="dashboard_owner")
        approval = runs.approve_task(ledger, request(runHash=run["runHash"], queueId=q["id"], contractHash=contract["contractHash"],
            scopeAssessment="Isolated second workspace fixture", confirmed=True), actor="dashboard_owner")
        binding = dispatch.phase_allocation(ledger.document(run["runHash"]), {"a": [resource_key]}); spec = binding["spec"]
        self.store.open_allocation(binding["id"], workspace_id="b", binding_hash=spec["bindingHash"], limits=spec["limits"],
            repositories=spec["repositories"])
        self.store.observe_usage(binding["id"], {"observedAt": time.time(), "evidenceHash": "b"*64, "counters": ZERO,
            "coverage": ["brain", "workers", "reviews"], "settledClaimIds": []})
        ledger.preflight(token, q["id"], {"seedHash": q["seedHash"], "packetDigest": q["packetDigest"], "baseSHA": "c"*40,
            "projectId": "project-b", "checks": {k: True for k in PREFLIGHT_CHECKS}, "evidence": ["fixture"]})
        with ledger.tx() as db:
            meta = ledger.get(db, "meta", 1); meta["paused"] = False; ledger.put(db, "meta", 1, meta)
        bridge = dispatch.DispatchAdmission(self.registry, "b", self.store)
        args = {"run_hash": run["runHash"], "queue_id": q["id"], "approval_hash": approval["approvalHash"], "estimates": ESTIMATES}
        return bridge, token, args

    def test_reserve_binds_authority_claim_resources_and_overhead(self):
        result = self.reserve(); worker = self.worker(); claim = self.claim()
        self.assertEqual(result["stage"], "reserved")
        self.assertFalse(result["executionAuthorized"]); self.assertFalse(result["nativeCallMade"])
        self.assertFalse(result["nativeAdapterAvailable"])
        self.assertEqual(worker["id"], claim["id"])
        self.assertEqual(claim["estimatedTokens"], 11500)
        intent = self.ledger.document(result["intentHash"])
        self.assertEqual(claim["bindingHash"], result["intentHash"])
        self.assertEqual(intent["runHash"], self.run["runHash"])
        self.assertEqual(intent["approvalHash"], self.approval["approvalHash"])
        self.assertEqual(intent["resourceKeys"], [KEY])
        self.assertEqual(self.store.snapshot()["allocations"][0]["budget"]["remainingForNewWork"], 78500)
        self.assertIsNone(worker["threadId"]); self.assertIsNone(worker["clientThreadId"])

    def test_duplicate_and_restart_reservation_are_exactly_once(self):
        first = self.reserve(); events = self.store.snapshot()["eventCount"]
        self.bridge = dispatch.DispatchAdmission(self.registry, "a", AdmissionStore(self.registry.root))
        self.assertEqual(self.reserve(), first)
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)
        self.assertEqual(events, self.store.snapshot()["eventCount"])
        self.assertEqual(len(self.ledger.snapshot()["workers"]), 1)

    def test_concurrent_reservations_share_one_owner_and_claim(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.reserve(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)

    def test_two_workspaces_share_capacity_but_not_authority_or_ownership(self):
        second, token, args = self.second_workspace("repo-remote:"+"b"*64)
        with self.assertRaises(Refusal): second.reserve(self.token, **args)
        with self.assertRaises(Refusal): second.reserve(token, **self.args)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.reserve), pool.submit(second.reserve, token, **args)]
            results = [future.result() for future in futures]
        self.assertNotEqual(results[0]["workerId"], results[1]["workerId"])
        snapshot = self.store.snapshot()
        self.assertEqual(len(snapshot["claims"]), 2); self.assertEqual(len(snapshot["resources"]), 2)
        self.assertTrue(all(a["budget"]["heldTokens"] == 11500 for a in snapshot["allocations"]))

    def test_two_workspaces_cannot_own_aliases_of_same_repository(self):
        second, token, args = self.second_workspace(KEY)
        def reserve(bridge, controller, fields):
            try: return bridge.reserve(controller, **fields)["stage"]
            except Refusal as error: return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(reserve, self.bridge, self.token, self.args), pool.submit(reserve, second, token, args)]
            results = [future.result() for future in futures]
        self.assertCountEqual(results, ["reserved", "Repository resource already owned"])
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)

    def test_constructor_without_existing_kernel_never_initializes_it(self):
        # Constructor requires an AdmissionStore; opening an absent kernel is
        # itself refused, without creating a file or implicit policy.
        root = self.registry.root.parent / "uninitialized"
        root.mkdir(mode=0o700)
        with self.assertRaisesRegex(Refusal, "not initialized"): AdmissionStore(root)
        self.assertFalse((root / "admission.sqlite3").exists())

    def test_registered_database_identity_drift_blocks(self):
        with self.registry.tx() as db:
            import json
            data = json.loads(db.execute("SELECT data FROM workspaces WHERE id='a'").fetchone()[0])
            data["databaseIdentity"] = [0, 0]
            db.execute("UPDATE workspaces SET data=? WHERE id='a'", (json.dumps(data),))
        with self.assertRaisesRegex(Refusal, "identity changed"): self.reserve()

    def test_estimates_and_existing_intent_cannot_be_replaced(self):
        for bad in ({**ESTIMATES, "workTokens": 9999}, {**ESTIMATES, "reviewTokens": 0}, {**ESTIMATES, "handoffTokens": True}):
            with self.assertRaises(Refusal): self.reserve(estimates=bad)
        self.assertEqual(self.ledger.snapshot()["workers"], [])
        self.reserve()
        with self.assertRaisesRegex(Refusal, "different dispatch"): self.reserve(estimates={**ESTIMATES, "reviewTokens": 1001})
        with self.assertRaises(Refusal): self.ledger.prepare(self.fx.fx.seed)
        with self.assertRaises(Refusal): self.fx.approve(self.run)

    def test_pause_is_not_implicitly_cleared_by_run_intent(self):
        self.meta(paused=True)
        with self.assertRaisesRegex(Refusal, "not activation"): self.reserve()
        self.assertEqual(self.ledger.snapshot()["workers"], [])

    def test_wrong_brain_cannot_write_or_recover(self):
        with self.assertRaises(Refusal): self.bridge.reserve("wrong", **self.args)
        result = self.reserve()
        with self.assertRaises(Refusal): self.bridge.recover("wrong", result["workerId"])

    def test_pause_between_intent_and_claim_preserves_unclaimed_owner(self):
        original = self.bridge.locked; calls = 0
        def locked(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2: self.fx.fx.command("pause")
            return original(*args, **kwargs)
        with patch.object(self.bridge, "locked", side_effect=locked):
            with self.assertRaises(Refusal): self.reserve()
        self.assertEqual(self.worker()["dispatchAdmission"]["stage"], "intent")
        self.assertEqual(self.store.snapshot()["claims"], [])
        result = self.bridge.recover(self.token, self.worker()["id"])
        self.assertEqual(result["stage"], "intent")
        self.assertEqual(self.store.snapshot()["claims"], [])

    def test_failure_before_shared_commit_can_resume_same_reservation(self):
        reserve_in = self.store.reserve_in
        def interrupted(*args, **kwargs):
            reserve_in(*args, **kwargs)
            raise RuntimeError("fixture crash before commit")
        with patch.object(self.store, "reserve_in", side_effect=interrupted):
            with self.assertRaises(RuntimeError): self.reserve()
        wid = self.worker()["id"]
        self.assertEqual(self.worker()["dispatchAdmission"]["stage"], "intent")
        self.assertEqual(self.store.snapshot()["claims"], [])
        self.assertEqual(self.store.snapshot()["resources"], [])
        self.assertEqual(self.reserve()["workerId"], wid)
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)

    def test_failure_after_shared_commit_recovers_after_pause_without_new_claim(self):
        with patch.object(self.bridge, "attach_in", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.reserve()
        self.assertEqual(self.worker()["dispatchAdmission"]["stage"], "intent")
        self.assertEqual(self.claim()["status"], "reserved")
        self.fx.fx.command("pause")
        with self.assertRaises(Refusal): self.reserve()
        restarted = dispatch.DispatchAdmission(self.registry, "a", AdmissionStore(self.registry.root))
        result = restarted.recover(self.token, self.worker()["id"])
        self.assertEqual(result["stage"], "reserved")
        self.assertFalse(result["executionAuthorized"])
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)

    def test_begin_is_one_shot_and_does_not_call_native_tools(self):
        self.reserve(); result = self.begin()
        self.assertEqual(result["stage"], "creation_intent")
        self.assertEqual(self.worker()["status"], "starting")
        self.assertEqual(self.claim()["status"], "starting")
        self.assertFalse(result["executionAuthorized"])
        self.assertNotIn("target", result); self.assertNotIn("prompt", result)
        with self.assertRaises(Refusal): self.begin()
        with self.assertRaises(Refusal): self.reserve()
        self.assertEqual(self.bridge.recover(self.token, result["workerId"]), result)

    def test_concurrent_begin_has_one_winner(self):
        self.reserve()
        def begin(_):
            try: return self.begin()["stage"]
            except Refusal: return "refused"
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(begin, range(2)))
        self.assertCountEqual(results, ["creation_intent", "refused"])

    def test_local_creation_commit_blocks_retry_even_if_shared_begin_fails(self):
        self.reserve()
        with patch.object(self.store, "begin_in", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.begin()
        self.assertEqual(self.worker()["status"], "starting")
        self.assertEqual(self.claim()["status"], "reserved")
        result = self.bridge.recover(self.token, self.worker()["id"])
        self.assertEqual(result["stage"], "creation_pending")
        with self.assertRaises(Refusal): self.begin()
        self.assertEqual(self.worker()["status"], "starting")

    def test_shared_creation_commit_recovers_without_repeating_boundary(self):
        self.reserve()
        with patch.object(self.bridge, "attach_in", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.begin()
        self.assertEqual(self.claim()["status"], "starting")
        self.assertEqual(self.worker()["dispatchAdmission"]["stage"], "creation_pending")
        self.fx.fx.command("brain_stop")
        self.assertIn("worker_effect_inflight", [i["code"] for i in self.ledger.snapshot()["workspacePause"]["blockers"]])
        result = self.bridge.recover(self.token, self.worker()["id"])
        self.assertEqual(result["stage"], "creation_intent")
        with self.assertRaises(Refusal): self.begin()

    def test_process_exit_after_shared_creation_commit_preserves_local_inflight_owner(self):
        result = self.reserve()
        script = """
import os, sys
from orchestrator.admission import AdmissionStore
from orchestrator.dispatch_admission import DispatchAdmission
from orchestrator.workspaces import Registry
registry = Registry(sys.argv[1])
bridge = DispatchAdmission(registry, 'a', AdmissionStore(registry.root))
bridge.attach_in = lambda *args: os._exit(17)
bridge.begin_creation(sys.argv[2], sys.argv[3])
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.registry.root), self.token, result["workerId"]],
                               capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 17, child.stderr.decode())
        self.assertEqual(self.worker()["status"], "starting")
        self.assertEqual(self.worker()["dispatchAdmission"]["stage"], "creation_pending")
        self.assertEqual(self.claim()["status"], "starting")
        self.bridge = dispatch.DispatchAdmission(self.registry, "a", AdmissionStore(self.registry.root))
        recovered = self.bridge.recover(self.token, result["workerId"])
        self.assertEqual(recovered["stage"], "creation_intent")
        with self.assertRaises(Refusal): self.begin()

    def test_pause_between_creation_commits_blocks_shared_advance(self):
        self.reserve(); original = self.bridge.locked; calls = 0
        def locked(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2: self.fx.fx.command("pause")
            return original(*args, **kwargs)
        with patch.object(self.bridge, "locked", side_effect=locked):
            with self.assertRaises(Refusal): self.begin()
        self.assertEqual(self.worker()["status"], "starting")
        self.assertEqual(self.claim()["status"], "reserved")

    def test_preflight_is_rechecked_at_creation(self):
        self.reserve()
        with self.ledger.tx() as db:
            q = self.ledger.get(db, "queue", self.args["queue_id"]); q["preflight"]["at"] = 0
            self.ledger.put(db, "queue", q["id"], q)
        with self.assertRaisesRegex(Refusal, "preflight"): self.begin()
        self.assertEqual(self.claim()["status"], "reserved")

    def test_revocation_is_rechecked_at_creation(self):
        self.reserve()
        runs.revoke_task(self.ledger, self.fx.request(queueId=self.args["queue_id"], approvalHash=self.approval["approvalHash"],
            reason="Fixture withdrawal"), actor="dashboard_owner")
        with self.assertRaises(Refusal): self.begin()
        self.assertEqual(self.claim()["status"], "reserved")

    def test_usage_expiry_and_budget_are_rechecked_at_creation(self):
        self.reserve()
        with patch.object(self.store, "clock", return_value=time.time()+61):
            with self.assertRaisesRegex(Refusal, "Fresh"): self.begin()
        self.refresh_usage(total=80000)
        with self.assertRaisesRegex(Refusal, "headroom"): self.begin()
        self.assertEqual(self.claim()["status"], "reserved")

    def test_unknown_usage_is_not_zero_and_phase_reserve_protected(self):
        self.refresh_usage(coverage=["workers"])
        with self.assertRaisesRegex(Refusal, "coverage"): self.reserve()
        self.refresh_usage(total=80000)
        with self.assertRaisesRegex(Refusal, "headroom"): self.reserve()
        self.assertEqual(self.store.snapshot()["claims"], [])

    def test_local_capacity_cannot_be_bypassed_by_larger_phase_limit(self):
        self.meta(concurrency=0)
        with self.assertRaisesRegex(Refusal, "Local worker capacity"): self.reserve()

    def test_canonical_resource_conflicts_leave_intent_not_native_task(self):
        self.store.reserve("other", self.binding["id"], repositories=["a"], estimates=ESTIMATES)
        with self.assertRaisesRegex(Refusal, "already owned"): self.reserve()
        self.assertEqual(self.worker()["dispatchAdmission"]["stage"], "intent")
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)

    def test_preexisting_unbound_claim_cannot_be_adopted_by_id_collision(self):
        wid = "dispatch-" + digest({"workspaceId": "a", "queueId": self.args["queue_id"]})
        self.store.reserve(wid, self.binding["id"], repositories=["a"], estimates=ESTIMATES)
        with self.assertRaisesRegex(Refusal, "different content"): self.reserve()
        self.assertNotIn("bindingHash", self.claim())
        self.assertEqual(self.worker()["dispatchAdmission"]["stage"], "intent")
        with self.assertRaisesRegex(Refusal, "binding changed"): self.bridge.recover(self.token, wid)

    def test_changed_allocation_binding_blocks(self):
        with self.store.tx() as db:
            allocation = self.store.get(db, "allocations", self.binding["id"])
            allocation["spec"]["limits"]["tokenBudget"] += 1
            allocation["fingerprint"] = digest(allocation["spec"])
            self.store.put(db, "allocations", allocation["id"], allocation)
        with self.assertRaisesRegex(Refusal, "binding changed"): self.reserve()

    def test_phase_binding_is_generation_independent_but_limits_and_mapping_are_not(self):
        changed = {**self.grant, "generation": 200, "missionHash": "e"*64, "reviewReceiptHash": "f"*64}
        self.assertEqual(dispatch.phase_allocation(changed, {"a": [KEY]}), self.binding)
        changed = copy.deepcopy(self.grant); changed["authority"]["tokenBudget"] += 1
        new = dispatch.phase_allocation(changed, {"a": [KEY]})
        self.assertEqual(new["id"], self.binding["id"])
        self.assertNotEqual(new["spec"]["bindingHash"], self.binding["spec"]["bindingHash"])

    def test_real_checkpoint_release_keeps_cumulative_phase_usage_and_claim(self):
        self.reserve(); self.refresh_usage(total=1234)
        before = self.store.snapshot()
        stop = {"commandId": self.fx.fx.command("brain_stop")["id"]}
        checkpoint = self.fx.park(stop)
        next_run = self.fx.authorize(self.fx.auth_request(checkpoint["documentHash"]))
        self.assertEqual(next_run["generation"], 2)
        grant = self.ledger.document(next_run["runHash"])
        self.assertEqual(dispatch.phase_allocation(grant, {"a": [KEY]}), self.binding)
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(before["allocations"][0]["budget"]["observedTokens"], 1234)
        self.assertEqual(before["allocations"][0]["budget"]["heldTokens"], 11500)
        self.assertEqual(len(before["claims"]), 1)

    def test_expired_run_and_held_task_cannot_advance_creation(self):
        self.reserve()
        with patch("orchestrator.run_authority.time.time", return_value=self.grant["expiresAt"]):
            with self.assertRaisesRegex(Refusal, "expired"): self.begin()
        # Legacy Hold correctly refuses owned packets. Inject drift to verify
        # the future adapter still rechecks the queue, not an old receipt.
        with self.ledger.tx() as db:
            q = self.ledger.get(db, "queue", self.args["queue_id"]); q["held"] = True
            self.ledger.put(db, "queue", q["id"], q)
        with self.assertRaisesRegex(Refusal, "held"): self.begin()
        self.assertEqual(self.claim()["status"], "reserved")

    def test_changed_mapping_cannot_advance_creation(self):
        self.reserve()
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "a"); repo["projectId"] = "different"
            self.ledger.put(db, "repos", "a", repo)
        with self.assertRaises(Refusal): self.begin()
        self.assertEqual(self.claim()["status"], "reserved")

    def test_account_headroom_and_reset_are_rechecked(self):
        self.reserve()
        with self.store.tx() as db:
            meta = self.store.get(db, "meta", 1); meta["account"]["windows"]["short"]["usedPercent"] = 95
            self.store.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "Account headroom"): self.begin()
        self.refresh_usage()
        with self.store.tx() as db:
            meta = self.store.get(db, "meta", 1); meta["account"]["windows"]["short"]["resetsAt"] = time.time()-1
            self.store.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "window reset"): self.begin()

    def test_shared_slot_and_attempt_limits_block_before_creation(self):
        with self.store.tx() as db:
            meta = self.store.get(db, "meta", 1); meta["policy"]["maxParallelTasks"] = 1
            self.store.put(db, "meta", 1, meta)
        self.store.reserve("other", self.binding["id"], repositories=["a"], estimates=ESTIMATES)
        with self.assertRaisesRegex(Refusal, "Global task slots"): self.reserve()
        self.store.settle("other", actual=ZERO, evidence_hash="c"*64, observed_at=time.time(), outcome="not_created")
        for number in range(3):
            cid = "attempt-"+str(number)
            self.store.reserve(cid, self.binding["id"], repositories=["a"], estimates=ESTIMATES)
            self.store.settle(cid, actual=ZERO, evidence_hash="c"*64, observed_at=time.time(), outcome="not_created")
        with self.assertRaisesRegex(Refusal, "task-attempt limit"): self.reserve()
        self.assertEqual(len(self.store.snapshot()["claims"]), 4)

    def test_file_only_enrollment_and_adoption_fences_block(self):
        # An empty/invalid sidecar is still a fence, not an excuse to ignore it.
        for path in (self.ledger.root / "admission-fence.json", self.registry.root / "adoption-fence.json",
                     self.registry.root / "adoption-kernel.json"):
            with self.subTest(path=path.name):
                path.touch(mode=0o600)
                with self.assertRaises(Refusal): self.reserve()
                path.unlink()  # isolated test fixture only
        self.assertEqual(self.ledger.snapshot()["workers"], [])

    def test_changed_admission_identity_blocks_even_after_bridge_restart(self):
        self.reserve()
        with self.ledger.tx() as db:
            w = self.ledger.get(db, "workers", self.worker()["id"])
            old = w["dispatchAdmission"]["intentHash"]
            intent = self.ledger.get(db, "snapshots", old)
            intent["admissionIdentity"] = [0, 0]
            w["dispatchAdmission"]["intentHash"] = runs.retain(db, "dispatch_intent", intent)
            self.ledger.put(db, "workers", w["id"], w)
        self.bridge = dispatch.DispatchAdmission(self.registry, "a", AdmissionStore(self.registry.root))
        with self.assertRaisesRegex(Refusal, "identity changed"): self.begin()
        with self.assertRaisesRegex(Refusal, "identity changed"): self.bridge.recover(self.token, self.worker()["id"])
        new = dispatch.phase_allocation(self.grant, {"a": ["repo-local:"+"b"*64]})
        self.assertEqual(new["id"], self.binding["id"])
        self.assertNotEqual(new["spec"]["bindingHash"], self.binding["spec"]["bindingHash"])

    def test_enrollment_and_adoption_fences_are_not_bypassed(self):
        self.meta(admissionBinding={"enrollmentId": "fixture"})
        with self.assertRaisesRegex(Refusal, "maintenance fence"): self.reserve()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta.pop("admissionBinding"); self.ledger.put(db, "meta", 1, meta)
        with self.store.tx() as db:
            meta = self.store.get(db, "meta", 1); meta["legacyAdoption"] = {}; self.store.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal): self.reserve()
        self.assertEqual(self.ledger.snapshot()["workers"], [])

    def test_missing_shared_claim_is_not_recreated_by_recovery(self):
        self.reserve()
        with self.store.tx() as db: db.execute("DELETE FROM claims")
        with self.assertRaisesRegex(Refusal, "missing"): self.bridge.recover(self.token, self.worker()["id"])
        with self.assertRaises(Refusal): self.reserve()
        self.assertEqual(self.store.snapshot()["claims"], [])

    def test_missing_resource_is_not_reacquired_by_begin_or_recovery(self):
        self.reserve()
        with self.store.tx() as db: db.execute("DELETE FROM resources")
        with self.assertRaisesRegex(Refusal, "ownership changed"): self.begin()
        with self.assertRaisesRegex(Refusal, "ownership changed"): self.bridge.recover(self.token, self.worker()["id"])

    def test_legacy_binding_transition_and_runner_cannot_desynchronize_claim(self):
        self.reserve(); self.begin(); wid = self.worker()["id"]
        with self.assertRaisesRegex(Refusal, "native result adapter"): self.ledger.bind(self.token, wid, thread_id="native-fixture")
        with self.assertRaisesRegex(Refusal, "continuation adapter"): self.ledger.transition(self.token, wid, "blocked", "fixture")
        with self.assertRaisesRegex(Refusal, "shared runner"): self.ledger.runner(self.token, wid, "acquire", "fixture")
        self.assertIsNone(self.worker()["threadId"]); self.assertIsNone(self.claim()["native"])


if __name__ == "__main__": unittest.main()
