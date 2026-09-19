import contextlib
import copy
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import brain_control, missions, run_authority as runs, task_contracts, workspace_pause
from orchestrator.core import Ledger, Refusal, canonical, digest
from orchestrator.observations import capture
import test_core
import test_missions
import test_task_contracts


class RunAuthorityTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_task_contracts.TaskContractTest(); self.fx.setUp()
        self.ledger, self.token = self.fx.ledger, self.fx.token
        self.contract = self.fx.propose()
        self.seq = 0

    def tearDown(self): self.fx.tearDown()

    def request(self, **fields):
        self.seq += 1
        return {"id": "run-fixture-" + str(self.seq), "expectedRevision": self.ledger.snapshot()["meta"]["revision"], **fields}

    def auth_request(self, checkpoint=None):
        m = missions.read(self.ledger)
        return self.request(missionHash=m["documentHash"], reviewReceiptHash=m["receiptHash"],
            checkpointHash=checkpoint, expiresAt=time.time()+3600, settingsPolicy="native_defaults", confirmed=True)

    def authorize(self, request=None):
        return runs.authorize(self.ledger, request or self.auth_request(), actor="dashboard_owner")

    def approval_request(self, run):
        return self.request(runHash=run["runHash"], queueId=self.fx.q["id"], contractHash=self.contract["contractHash"],
                            scopeAssessment="Fixture is within the exact reviewed phase", confirmed=True)

    def approve(self, run, actor="dashboard_owner", request=None):
        return runs.approve_task(self.ledger, request or self.approval_request(run), actor=actor, token=self.token)

    def check(self, run, approval, operation="edit"):
        with self.ledger.tx() as db:
            return runs.check_task_in(self.ledger, db, run_hash=run["runHash"], queue_id=self.fx.q["id"],
                                      approval_hash=approval["approvalHash"], operation=operation)

    def state(self): return runs.read(self.ledger)["state"]

    def mode(self, mode):
        m = missions.read(self.ledger); spec = copy.deepcopy(m["document"]["spec"])
        spec["authority"]["approvalMode"] = mode
        saved = missions.change(self.ledger, test_missions.request(revision=m["revision"], spec=spec))["current"]
        missions.change(self.ledger, test_missions.request("review", saved["revision"], documentHash=saved["documentHash"], confirmed=True))
        self.contract = self.fx.propose()

    def stop(self, run, reason="phase_checkpoint", request=None):
        return runs.stop(self.ledger, self.token, request or self.request(runHash=run["runHash"], reason=reason))

    def park(self, stop):
        self.ledger.process(self.token)
        with self.ledger.tx() as db:
            artifact = capture(db, "brain-fixture-checkpoint", str(time.time()).encode(),
                {"repository": "a", "name": "checkpoint.md", "orderAt": time.time(),
                 "references": [{"session": "brain-a", "at": time.time()}]})
        proof = workspace_pause.observe(self.ledger, self.token, stop["commandId"], {
            "workspaceId": "a", "commandId": stop["commandId"], "observedAt": time.time(), "evidenceHash": "a"*64,
            "complete": True, "includesDescendants": True, "brain": {"hostId": "local", "threadId": "brain-a"}, "tasks": []})
        return brain_control.park(self.ledger, self.token, stop["commandId"], {
            "summary": "Fixture safe checkpoint", "artifactIds": [artifact["id"]], "pauseEvidenceHash": proof["documentHash"]})

    def test_intent_binds_review_generation_and_no_execution(self):
        before = self.ledger.snapshot(); receipt = self.authorize(); after = self.ledger.snapshot()
        self.assertEqual(self.state()["status"], "authorized_intent")
        self.assertEqual(receipt["generation"], 1)
        self.assertFalse(receipt["executionAuthorized"]); self.assertFalse(receipt["nativeNotificationSent"])
        grant = self.ledger.document(receipt["runHash"])
        self.assertEqual(grant["missionHash"], missions.read(self.ledger)["documentHash"])
        self.assertEqual(grant["authority"]["tokenBudget"], 100000)
        for key in ("workers", "commands", "queue"): self.assertEqual(before[key], after[key])
        for key in ("paused", "runner", "controller", "heartbeat", "concurrency", "pilotPassed"):
            self.assertEqual(before["meta"][key], after["meta"][key])
        self.assertFalse((self.fx.registry.root / "admission.sqlite3").exists())

    def test_reads_do_not_upgrade_and_reopen_retains_v3(self):
        before = self.fx.logical(); self.assertIsNone(self.state()); self.assertEqual(before, self.fx.logical())
        self.authorize()
        self.assertEqual(Ledger(self.ledger.root).snapshot()["meta"]["schemaVersion"], 3)
        self.assertIsNotNone(runs.read(self.fx.registry.ledger("a"))["state"])
        self.fx.propose(); self.assertEqual(self.ledger.snapshot()["meta"]["schemaVersion"], 3)

    def test_only_explicit_owner_and_exact_review(self):
        request = self.auth_request()
        with self.assertRaises(Refusal): runs.authorize(self.ledger, request, actor="designated_brain")
        for key, value in (("confirmed", False), ("missionHash", "a"*64), ("reviewReceiptHash", "b"*64),
                           ("expectedRevision", 0), ("checkpointHash", "c"*64), ("settingsPolicy", "adaptive")):
            bad = {**request, key: value}
            with self.assertRaises(Refusal): self.authorize(bad)
        self.assertIsNone(self.state())

    def test_expiry_is_bounded_and_enforced_on_checks(self):
        for value in (True, float("inf"), 0, time.time()-1, time.time()+90000):
            with self.assertRaises(Refusal): self.authorize({**self.auth_request(), "expiresAt": value})
        run = self.authorize(); approval = self.approve(run)
        expiry = self.ledger.document(run["runHash"])["expiresAt"]
        with patch("orchestrator.run_authority.time.time", return_value=expiry):
            with self.assertRaisesRegex(Refusal, "expired"): self.check(run, approval)
        self.assertEqual(self.state()["status"], "authorized_intent")  # reads never rewrite observation/state

    def test_prepare_only_is_not_authority(self):
        self.mode("prepare_only")
        with self.assertRaisesRegex(Refusal, "Prepare-only"): self.authorize()

    def test_initial_authority_requires_quiet_legacy_state(self):
        self.fx.command("resume"); self.ledger.process(self.token)
        with self.assertRaisesRegex(Refusal, "Pause legacy"): self.authorize()
        self.fx.command("pause")
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["runner"] = "fixture-runner"; self.ledger.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "legacy workers or runner"): self.authorize()

    def test_duplicate_request_and_changed_request_id(self):
        request = self.auth_request(); one = self.authorize(request); before = self.fx.logical()
        self.assertEqual(self.authorize(request), one); self.assertEqual(before, self.fx.logical())
        with self.assertRaisesRegex(Refusal, "reused"): self.authorize({**request, "expiresAt": request["expiresAt"]+1})
        with self.assertRaisesRegex(Refusal, "checkpoint"): self.authorize()

    def test_replay_after_stop_does_not_rearm(self):
        request = self.auth_request(); run = self.authorize(request); self.stop(run)
        self.assertEqual(self.authorize(request), run); self.assertEqual(self.state()["status"], "fenced")

    def test_exact_owner_approval_is_bound_but_not_native_permission(self):
        run = self.authorize(); approval = self.approve(run); result = self.check(run, approval)
        self.assertTrue(result["authoritySatisfied"]); self.assertFalse(result["executionAuthorized"])
        self.assertTrue(result["admissionRequired"]); self.assertFalse(result["nativeAdapterAvailable"])
        q = self.ledger.snapshot()["queue"][0]
        self.assertEqual(q["status"], "proposed"); self.assertIsNone(q["approval"])
        with self.assertRaisesRegex(Refusal, "owner"): self.approve(run, "designated_brain")

    def test_delegated_approval_actor_and_scope_assessment(self):
        self.mode("phase_delegated"); run = self.authorize(); approval = self.approve(run, "designated_brain")
        self.assertEqual(self.ledger.document(approval["approvalHash"])["actor"], "designated_brain")
        self.assertTrue(self.check(run, approval)["authoritySatisfied"])
        with self.assertRaises(Refusal): self.approve(run, request={**self.approval_request(run), "scopeAssessment": ""})
        with self.assertRaises(Refusal): runs.approve_task(self.ledger, self.approval_request(run), actor="designated_brain", token="wrong")

    def test_requested_overrides_block_instead_of_silent_fallback(self):
        spec = self.fx.spec(); spec["requestedSettings"]["model"] = "fixture-model"
        self.contract = self.fx.propose(self.fx.request(spec)); run = self.authorize()
        with self.assertRaisesRegex(Refusal, "settings"): self.approve(run)

    def test_undeclared_operations_and_changed_contract_block(self):
        run = self.authorize(); approval = self.approve(run)
        for operation in ("push", "merge", "deploy"):
            with self.assertRaises(Refusal): self.check(run, approval, operation)
        self.contract = self.fx.propose()
        with self.assertRaisesRegex(Refusal, "contract"): self.check(run, approval)

    def test_held_task_and_approval_hash_substitution_block(self):
        run = self.authorize(); approval = self.approve(run)
        with self.assertRaises(Refusal): self.check(run, {"approvalHash": "a"*64})
        self.fx.command("hold", {"queueId": self.fx.q["id"], "held": True})
        with self.assertRaisesRegex(Refusal, "held"): self.check(run, approval)

    def test_revocation_retains_history_and_replay_cannot_restore(self):
        run = self.authorize(); request = self.approval_request(run); approved = self.approve(run, request=request)
        revoked = runs.revoke_task(self.ledger, self.request(queueId=self.fx.q["id"], approvalHash=approved["approvalHash"], reason="Owner withdraws scope"), actor="dashboard_owner")
        doc = self.ledger.document(revoked["approvalHash"])
        self.assertEqual(doc["previousHash"], approved["approvalHash"]); self.assertEqual(doc["status"], "revoked")
        self.assertEqual(self.approve(run, request=request), approved)
        with self.assertRaises(Refusal): self.check(run, approved)
        with self.assertRaises(Refusal): self.check(run, revoked)

    def test_revocation_works_after_pause_as_safety_operation(self):
        run = self.authorize(); approved = self.approve(run); self.stop(run)
        runs.revoke_task(self.ledger, self.request(queueId=self.fx.q["id"], approvalHash=approved["approvalHash"], reason="Safety withdrawal"), actor="designated_brain", token=self.token)

    def test_reprepare_preserves_approval_history_but_not_validity(self):
        run = self.authorize(); approved = self.approve(run)
        seed = copy.deepcopy(self.fx.seed); seed["objective"] = "Changed fixture scope"; self.ledger.prepare(seed)
        self.assertEqual(self.ledger.snapshot()["queue"][0]["phaseApprovalHash"], approved["approvalHash"])
        with self.assertRaises(Refusal): self.check(run, approved)

    def test_ordinary_pause_fences_run_and_legacy_resume_refuses(self):
        run = self.authorize(); approved = self.approve(run); self.fx.command("pause")
        self.assertEqual(self.state()["reason"], "dispatch_pause")
        with self.assertRaises(Refusal): self.check(run, approved)
        with self.assertRaisesRegex(Refusal, "Run-managed"): self.fx.command("resume")

    def test_owner_workspace_pause_captures_exact_stop(self):
        run = self.authorize(); approved = self.approve(run); stop = self.fx.command("brain_stop")
        self.assertEqual(self.state()["stopCommandId"], stop["id"])
        with self.assertRaises(Refusal): self.check(run, approved)

    def test_mission_change_atomically_fences_and_replay_does_not(self):
        run = self.authorize(); approval = self.approve(run); m = missions.read(self.ledger)
        missions.change(self.ledger, test_missions.request("revoke", m["revision"], documentHash=m["documentHash"], confirmed=True))
        self.assertEqual(self.state()["reason"], "mission_revoke")
        with self.assertRaises(Refusal): self.check(run, approval)

    def test_mapping_drift_is_rechecked_and_legacy_mutation_blocked(self):
        run = self.authorize(); approval = self.approve(run)
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "a"); repo["projectId"] = "changed"; self.ledger.put(db, "repos", "a", repo)
        with self.assertRaises(Refusal): self.check(run, approval)

    def test_controller_recovery_fences_current_run(self):
        self.authorize(); self.ledger.recover("brain-a:contract-fixture", "Fixture native observations confirm controller is inactive")
        self.assertEqual(self.state()["reason"], "controller_recovery")

    def test_brain_stop_is_idempotent_and_preserves_workers(self):
        run = self.authorize(); request = self.request(runHash=run["runHash"], reason="budget_revision")
        before = self.ledger.snapshot()["workers"]; one = self.stop(run, request=request)
        self.assertEqual(self.stop(run, request=request), one)
        self.assertEqual(self.state()["reason"], "budget_revision")
        self.assertNotIn("owner_pause", self.state()["stopReasons"])
        self.assertIn("brain_stop", self.state()["stopReasons"])
        self.assertEqual(before, self.ledger.snapshot()["workers"])
        self.assertEqual(len([c for c in self.ledger.snapshot()["commands"] if c["kind"] == "brain_stop"]), 1)

    def test_stop_after_expiry_still_reaches_safe_checkpoint(self):
        run = self.authorize()
        with patch("orchestrator.run_authority.time.time", return_value=time.time()+7200):
            self.stop(run, "evidence_lost")
        self.assertEqual(self.state()["status"], "fenced")

    def test_checkpoint_and_exact_owner_release_new_generation(self):
        run = self.authorize(); approval = self.approve(run)
        stop = {"commandId": self.fx.command("brain_stop")["id"]}
        with self.assertRaises(Refusal): self.authorize()
        checkpoint = self.park(stop)
        self.assertEqual(self.state()["status"], "checkpointed")
        self.assertEqual(self.state()["checkpointHash"], checkpoint["documentHash"])
        with self.assertRaises(Refusal): self.authorize(self.auth_request("a"*64))
        next_run = self.authorize(self.auth_request(checkpoint["documentHash"]))
        self.assertEqual(next_run["generation"], 2)
        self.assertEqual(self.ledger.document(next_run["runHash"])["previousRunHash"], run["runHash"])
        self.assertEqual(self.ledger.document(next_run["runHash"])["authority"], self.ledger.document(run["runHash"])["authority"])
        with self.assertRaises(Refusal): self.check(run, approval)
        with self.assertRaises(Refusal): self.approve(next_run)  # owner intent never wakes a parked brain
        self.fx.command("brain_resume"); self.ledger.process(self.token)
        with self.assertRaises(Refusal): self.check(next_run, approval)
        self.assertTrue(self.check(next_run, self.approve(next_run))["authoritySatisfied"])

    def test_ordinary_brain_resume_does_not_restore_old_run(self):
        run = self.authorize(); approval = self.approve(run); self.park(self.stop(run))
        self.fx.command("brain_resume"); self.ledger.process(self.token)
        self.assertEqual(self.state()["status"], "checkpointed")
        with self.assertRaises(Refusal): self.check(run, approval)

    def test_legacy_dispatch_is_blocked_even_for_undeclared_packets(self):
        self.authorize(); q = self.ledger.prepare(test_core.seed(packet="LEGACY-002", profile="standard"))
        with self.assertRaisesRegex(Refusal, "run-aware"): self.fx.command("approve", {"queueId": q["id"], "seedHash": q["seedHash"], "packetDigest": q["packetDigest"]})
        with self.assertRaisesRegex(Refusal, "Run-managed"): self.ledger.reserve(self.token, q["id"])

    def test_corruption_cannot_block_owner_pause_or_restore_authority(self):
        self.authorize()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["runAuthority"] = None; self.ledger.put(db, "meta", 1, meta)
        self.fx.command("brain_stop")
        self.assertTrue(self.ledger.snapshot()["meta"]["runAuthorityInvalidated"])
        with self.assertRaises(Refusal): self.authorize()

    def test_foreign_workspace_cannot_use_authority(self):
        run = self.authorize(); approval = self.approve(run)
        ledger = Ledger(self.ledger.root); ledger.workspace_id = "foreign"
        with self.assertRaises(Refusal): runs.read(ledger)
        with self.assertRaises(Refusal): runs.authorize(Ledger(self.ledger.root), self.auth_request(), actor="dashboard_owner")

    def test_concurrent_distinct_requests_have_one_winner(self):
        one, two = self.auth_request(), self.auth_request()
        def call(request):
            try: return self.authorize(request)
            except Refusal: return None
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(call, (one, two)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(self.state()["generation"], 1)

    def test_concurrent_identical_requests_return_one_receipt(self):
        request = self.auth_request()
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(self.authorize, (request, request)))
        self.assertEqual(results[0], results[1])
        with contextlib.closing(self.ledger.connect()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE kind='run_authorization'").fetchone()[0], 1)

    def test_failure_rolls_back_grant_format_and_pointer(self):
        before = self.fx.logical()
        with patch.object(self.ledger, "event", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.authorize()
        self.assertEqual(before, self.fx.logical())

    def test_stop_failure_rolls_back_authority_and_brain_control(self):
        run = self.authorize(); before = self.fx.logical()
        with patch.object(self.ledger, "event", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.stop(run)
        self.assertEqual(before, self.fx.logical())

    def test_no_activation_cli_http_or_assistant_route(self):
        from pathlib import Path
        for path in ("orchestrator/cli.py", "orchestrator/server.py", "orchestrator/assistant_actions.py"):
            source = Path(path).read_text()
            self.assertNotIn("run_authority", source)
            self.assertNotIn("run-authorize", source)

    def test_phase_boundary_requires_new_review_not_released_checkbox(self):
        run = self.authorize(); cp = self.park(self.stop(run))
        with self.assertRaisesRegex(Refusal, "newly reviewed"): self.authorize(self.auth_request(cp["documentHash"]))
        m = missions.read(self.ledger); spec = copy.deepcopy(m["document"]["spec"])
        spec["phase"]["id"] = "phase-two"; spec["phase"]["objective"] = "Explicit next phase fixture"
        saved = missions.change(self.ledger, test_missions.request(revision=m["revision"], spec=spec))["current"]
        with self.assertRaises(Refusal): self.authorize(self.auth_request(cp["documentHash"]))
        missions.change(self.ledger, test_missions.request("review", saved["revision"], documentHash=saved["documentHash"], confirmed=True))
        following = self.authorize(self.auth_request(cp["documentHash"]))
        self.assertEqual(self.ledger.document(following["runHash"])["phaseId"], "phase-two")

    def test_pause_racing_approval_never_leaves_effective_authority(self):
        run = self.authorize(); approval_request = self.approval_request(run)
        pause = {"id": "concurrent-owner-pause", "kind": "brain_stop", "payload": {},
                 "expectedRevision": approval_request["expectedRevision"]}
        def approve():
            try: return self.approve(run, request=approval_request)
            except Refusal: return None
        def stop():
            try: return self.ledger.submit(pause)
            except Refusal:
                # Dashboard must re-read optimistic revision, never discard owner stop.
                return self.ledger.submit({**pause, "expectedRevision": self.ledger.snapshot()["meta"]["revision"]})
        with ThreadPoolExecutor(2) as pool:
            a, b = pool.submit(approve), pool.submit(stop)
            approved, _ = a.result(), b.result()
        self.assertEqual(self.state()["status"], "fenced")
        if approved:
            with self.assertRaises(Refusal): self.check(run, approved)

    def test_harness_still_requires_exact_owner_approval(self):
        m = missions.read(self.ledger); spec = copy.deepcopy(m["document"]["spec"])
        spec["phase"]["scope"][0]["repository"] = "harness"; spec["phase"]["scope"][0]["operations"].append("merge")
        draft = self.fx.fx.fx.save(spec, revision=m["revision"]); self.fx.fx.fx.review(draft)
        seed = test_core.seed(repo="harness"); seed["completionAxes"].append("merge"); q = self.ledger.prepare(seed)
        body = self.fx.spec(); body.update(queueId=q["id"], seedHash=q["seedHash"], packetDigest=q["packetDigest"])
        body["operations"].append("merge")
        self.contract = self.fx.propose(self.fx.request(body)); self.fx.q = q
        run = self.authorize()
        with self.assertRaisesRegex(Refusal, "owner"): self.approve(run, "designated_brain")
        self.assertTrue(self.check(run, self.approve(run), "merge")["authoritySatisfied"])

    def test_approval_for_owned_packet_refuses_without_owner_release(self):
        run = self.authorize(); request = self.approval_request(run)
        with self.ledger.tx() as db:
            db.execute("INSERT INTO workers VALUES(?,?,?)", ("owned-fixture", self.fx.q["id"], canonical({"id": "owned-fixture", "queueId": self.fx.q["id"], "status": "reserved"})))
        with self.assertRaisesRegex(Refusal, "Owned task"): self.approve(run, request=request)

    def test_corrupt_grant_never_passes_effect_check(self):
        run = self.authorize(); approval = self.approve(run)
        with self.ledger.tx() as db:
            db.execute("UPDATE snapshots SET data=? WHERE id=?", ('{"private":"not-an-authorization"}', run["runHash"]))
        with self.assertRaises(Refusal) as error: self.check(run, approval)
        self.assertNotIn("not-an-authorization", str(error.exception))

    def test_request_bounds_and_unknown_fields(self):
        for body in ({**self.auth_request(), "extra": True}, {**self.auth_request(), "id": "x"*101},
                     {**self.auth_request(), "settingsPolicy": "x"*17000}):
            with self.assertRaises(Refusal): self.authorize(body)

    def test_existing_owner_stop_does_not_duplicate_brain_stop(self):
        run = self.authorize(); owner_stop = self.fx.command("brain_stop"); self.stop(run)
        self.assertEqual(self.state()["stopCommandId"], owner_stop["id"])
        self.assertEqual(len([c for c in self.ledger.snapshot()["commands"] if c["kind"] == "brain_stop"]), 1)
        self.assertIn("phase_checkpoint", self.state()["stopReasons"])
        cp = self.park({"commandId": owner_stop["id"]})
        with self.assertRaisesRegex(Refusal, "newly reviewed"): self.authorize(self.auth_request(cp["documentHash"]))

    def test_unknown_stop_reason_and_wrong_controller_refuse(self):
        run = self.authorize()
        with self.assertRaises(Refusal): self.stop(run, "force_kill")
        with self.assertRaises(Refusal): runs.stop(self.ledger, "wrong", self.request(runHash=run["runHash"], reason="plan_revision"))

    def test_check_requires_transaction_and_cannot_authorize_native_effect(self):
        run = self.authorize(); approval = self.approve(run)
        with contextlib.closing(self.ledger.connect()) as db:
            with self.assertRaisesRegex(Refusal, "transaction"):
                runs.check_task_in(self.ledger, db, run_hash=run["runHash"], queue_id=self.fx.q["id"], approval_hash=approval["approvalHash"], operation="edit")

    def test_second_safe_stop_replaces_checkpoint_not_generation_or_limits(self):
        self.authorize(); first_stop = {"commandId": self.fx.command("brain_stop")["id"]}
        first = self.park(first_stop); self.fx.command("brain_resume"); self.ledger.process(self.token)
        second_stop = {"commandId": self.fx.command("brain_stop")["id"]}; second = self.park(second_stop)
        self.assertNotEqual(first["documentHash"], second["documentHash"])
        self.assertEqual(self.state()["generation"], 1)
        with self.assertRaises(Refusal): self.authorize(self.auth_request(first["documentHash"]))
        self.assertEqual(self.authorize(self.auth_request(second["documentHash"]))["generation"], 2)

    def test_missing_pointer_does_not_reset_generation_or_regain_legacy_dispatch(self):
        self.authorize()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta.pop("runAuthority"); self.ledger.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "missing"): self.authorize()
        with self.assertRaisesRegex(Refusal, "Run-managed"): self.fx.command("resume")
        self.fx.command("brain_stop")
        self.assertTrue(self.ledger.snapshot()["meta"]["runAuthorityInvalidated"])

    def test_hard_process_exit_rolls_back_authority_and_format(self):
        before = self.fx.logical(); request = self.auth_request()
        code = """import json, os, sys
from orchestrator.core import Ledger
from orchestrator.run_authority import authorize
ledger = Ledger(sys.argv[1]); ledger.workspace_id = 'a'
ledger.event = lambda *args, **kwargs: os._exit(77)
authorize(ledger, json.loads(sys.argv[2]), actor='dashboard_owner')
"""
        result = subprocess.run([sys.executable, "-c", code, str(self.ledger.root), canonical(request)],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 77, result.stderr.decode())
        self.assertEqual(before, self.fx.logical())
        self.assertEqual(self.authorize(request)["generation"], 1)

    def test_corruption_after_stop_does_not_prevent_safe_parking(self):
        run = self.authorize(); stop = self.stop(run)
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["runAuthority"] = None; self.ledger.put(db, "meta", 1, meta)
        self.park(stop)
        meta = self.ledger.snapshot()["meta"]
        self.assertEqual(meta["brainControl"]["phase"], "parked")
        self.assertTrue(meta["runAuthorityInvalidated"])

    def test_corrupt_or_oversized_request_receipt_refuses_replay(self):
        request = self.auth_request(); self.authorize(request)
        key = digest({"kind": "run_request", "workspaceId": "a", "id": request["id"]})
        for raw in ('{"private":"broken"}', '"' + 'x'*40000 + '"'):
            with self.ledger.tx() as db: db.execute("UPDATE snapshots SET data=? WHERE id=?", (raw, key))
            with self.assertRaises(Refusal): self.authorize(request)

    def test_completed_task_cannot_reuse_a_previous_approval(self):
        run = self.authorize(); approval = self.approve(run)
        with self.ledger.tx() as db:
            q = self.ledger.get(db, "queue", self.fx.q["id"]); q["status"] = "complete"
            self.ledger.put(db, "queue", q["id"], q)
        with self.assertRaisesRegex(Refusal, "Completed"): self.check(run, approval)


if __name__ == "__main__": unittest.main()
