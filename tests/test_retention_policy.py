"""Disposable policy/archival composition; never invokes native archival."""
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import retention_policy as retention, run_authority as runs
from orchestrator.core import Refusal, digest
import test_archive_handoff
import test_missions
import test_run_authority


class RetentionPolicyTest(unittest.TestCase):
    def setUp(self):
        self.serial = 0
        original = test_missions.specification
        def delegated(*args, **kwargs): return original(*args, **{**kwargs, "mode": "phase_delegated"})
        authorize = test_run_authority.RunAuthorityTest.authorize
        approve = test_run_authority.RunAuthorityTest.approve
        def approved(fx, run, actor="dashboard_owner", request=None):
            return approve(fx, run, actor="designated_brain", request=request)
        self.owner_request = None
        def authorized(fx, request=None):
            result = authorize(fx, request)
            self.owner_request = {"id": "retention-policy-fixture", "expectedRevision": fx.ledger.snapshot()["meta"]["revision"],
                "runHash": result["runHash"], "expectedPolicyHash": None, "maxArchives": 2,
                "minimumRetentionSeconds": 0, "allowManagedWorktreeCleanup": True, "confirmed": True}
            self.policy = retention.review(fx.ledger, self.owner_request, actor="dashboard_owner")
            return result
        with patch.object(test_missions, "specification", delegated), patch.object(test_run_authority.RunAuthorityTest, "authorize", authorized), \
             patch.object(test_run_authority.RunAuthorityTest, "approve", approved):
            self.fx = test_archive_handoff.ArchiveHandoffTest(); self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.ledger, self.token, self.wid, self.api = self.fx.ledger, self.fx.token, self.fx.wid, self.fx.api

    def request(self, **fields):
        self.serial += 1
        payload = self.fx.state()["ownerRequestPayload"]
        return {"id": "retention-request-"+str(self.serial), "expectedRevision": self.fx.revision(),
            "policyHash": self.policy["policyHash"], "reviewHash": payload["reviewHash"],
            "preservationArtifactId": payload["preservationArtifactId"], "rationale": "Accepted, preserved root; keep the brain's working set bounded.", **fields}

    def save(self, request=None): return self.api.request_delegated(self.token, self.wid, request or self.request())
    def prepare(self):
        receipt = self.save()
        prepared = self.api.prepare(self.token, self.wid, {"commandId": receipt["commandId"],
            "expectedRevision": self.fx.revision(), "inventory": self.fx.inventory()})
        return receipt, prepared
    def revoke(self):
        return retention.revoke(self.ledger, {"id": "retention-revoke-fixture", "expectedRevision": self.fx.revision(),
            "policyHash": self.policy["policyHash"], "reason": "Owner retains tasks"}, actor="dashboard_owner")
    def paused_flag(self, value):
        # Test-only gate setup; no public activation route is claimed.
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["paused"] = value; self.ledger.put(db, "meta", 1, meta)
    def revised(self, **fields):
        self.paused_flag(True)
        req = self.owner_request | {"id": "retention-policy-revision", "expectedRevision": self.fx.revision(),
            "expectedPolicyHash": self.policy["policyHash"]} | fields
        receipt = retention.review(self.ledger, req, actor="dashboard_owner")
        self.paused_flag(False)
        return receipt

    def test_policy_does_not_create_request_or_archive(self):
        state = self.fx.state()
        self.assertEqual(state["retention"]["status"], "reviewed_policy")
        self.assertEqual(state["retention"]["recordedAttempts"], 0)
        self.assertFalse(state["retention"]["sendPermit"]); self.assertFalse(self.fx.worker()["archived"])
        self.assertEqual(self.ledger.snapshot()["commands"], [])

    def test_request_cli_and_existing_one_shot_lifecycle_compose(self):
        shared = self.fx.fx.store.snapshot(); request = self.request()
        result = self.fx.cli("request-delegated", request)
        self.assertEqual(result.returncode, 0, result.stderr); receipt = json.loads(result.stdout)
        self.assertFalse(receipt["sendPermit"]); self.assertNotIn("arguments", receipt)
        prepared = self.api.prepare(self.token, self.wid, {"commandId": receipt["commandId"],
            "expectedRevision": self.fx.revision(), "inventory": self.fx.inventory()})
        result = self.api.check(self.token, self.wid, self.fx.check_request(prepared))
        self.assertTrue(result["sendPermit"]); self.assertFalse(self.fx.worker()["archived"])
        with self.assertRaises(Refusal): self.api.check(self.token, self.wid, self.fx.check_request(prepared))
        self.api.record(self.token, self.wid, self.fx.observation(prepared))
        self.assertTrue(self.fx.worker()["archived"])
        self.assertEqual(shared, self.fx.fx.store.snapshot())
        self.assertEqual(self.fx.state()["retention"]["recordedAttempts"], 1)
        self.assertEqual(self.fx.fx.call("state")["review"], self.fx.accepted)

    def test_owner_only_policy_internal_seam_and_cleanup_acknowledgment(self):
        self.paused_flag(True)
        req = self.owner_request | {"id": "new-review-fixture", "expectedRevision": self.fx.revision(), "expectedPolicyHash": self.policy["policyHash"]}
        before = self.fx.fx.logical()
        for actor in ("designated_brain", "dashboard", "model"):
            with self.assertRaises(Refusal): retention.review(self.ledger, req, actor=actor)
        for change in ({"allowManagedWorktreeCleanup": False}, {"confirmed": 1}, {"maxArchives": 0},
                       {"maxArchives": 5}, {"minimumRetentionSeconds": -1}, {"minimumRetentionSeconds": True},
                       {"expectedPolicyHash": None}, {"runHash": "a"*64}, {"extra": True}):
            with self.subTest(change=change), self.assertRaises(Refusal): retention.review(self.ledger, req | change, actor="dashboard_owner")
        self.assertEqual(before, self.fx.fx.logical())

    def test_review_requires_paused_setup_and_never_unpauses(self):
        req = self.owner_request | {"id": "another-policy-review", "expectedRevision": self.fx.revision(), "expectedPolicyHash": self.policy["policyHash"]}
        with self.assertRaisesRegex(Refusal, "paused"): retention.review(self.ledger, req, actor="dashboard_owner")
        self.assertFalse(self.ledger.snapshot()["meta"]["paused"])

    def test_retention_age_and_changed_review_or_preservation_refuse(self):
        for fields in ({"policyHash": "a"*64}, {"reviewHash": "b"*64}, {"preservationArtifactId": "c"*64}, {"rationale": ""}):
            with self.subTest(fields=fields), self.assertRaises(Refusal): self.save(self.request(**fields))
        self.policy = self.revised(minimumRetentionSeconds=3600)
        with self.assertRaisesRegex(Refusal, "age"): self.save()
        self.assertEqual(self.fx.state()["retention"]["recordedAttempts"], 0)

    def test_no_delegation_without_policy_and_missing_pointer_cannot_downgrade(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta.pop("retentionPolicyHash")
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "pointer"): self.fx.state()

    def test_policy_replay_cannot_unrevoke_or_refresh_time(self):
        self.revoke(); before = self.fx.fx.logical()
        self.assertEqual(retention.review(self.ledger, self.owner_request, actor="dashboard_owner"), self.policy)
        self.assertEqual(before, self.fx.fx.logical())
        self.assertEqual(self.fx.state()["retention"]["status"], "revoked")
        with self.assertRaises(Refusal): self.save()

    def test_request_replay_after_pause_does_not_resubmit_or_refresh(self):
        req = self.request(); first = self.save(req); self.fx.fx.pause(); before = self.fx.fx.logical()
        self.assertEqual(self.save(req), first); self.assertEqual(before, self.fx.fx.logical())
        with self.assertRaises(Refusal): self.save()
        with self.assertRaises(Refusal): self.save(req | {"rationale": "Different"})

    def test_concurrent_requests_are_atomic_and_one_per_worker(self):
        req = self.request()
        with ThreadPoolExecutor(max_workers=2) as pool: result = list(pool.map(lambda _: self.save(req), range(2)))
        self.assertEqual(result[0], result[1]); self.assertEqual(self.fx.state()["retention"]["recordedAttempts"], 1)
        with self.assertRaisesRegex(Refusal, "already requested"): self.save()
        self.assertEqual(len(self.ledger.snapshot()["commands"]), 1)

    def test_event_failure_rolls_back_command_quota_and_receipt(self):
        req = self.request(); before = self.fx.fx.logical(); event = self.api.ledger.event
        def fail(db, kind, data):
            if kind == "run_retention_request": raise RuntimeError("fixture failure")
            return event(db, kind, data)
        with patch.object(self.api.ledger, "event", side_effect=fail), self.assertRaises(RuntimeError): self.save(req)
        self.assertEqual(before, self.fx.fx.logical()); self.save(req)

    def test_revocation_before_check_blocks_but_allows_unsent_cancellation(self):
        _, prepared = self.prepare(); self.revoke()
        with self.assertRaises(Refusal): self.api.check(self.token, self.wid, self.fx.check_request(prepared))
        self.api.record(self.token, self.wid, self.fx.observation(prepared, "cancelled"))
        self.assertFalse(self.fx.worker()["archived"])
        self.assertEqual(self.fx.state()["retention"]["recordedAttempts"], 1)

    def test_revocation_after_send_keeps_uncertainty_and_late_confirmation(self):
        _, prepared = self.prepare(); self.api.check(self.token, self.wid, self.fx.check_request(prepared)); self.revoke()
        self.api.record(self.token, self.wid, self.fx.observation(prepared, "unknown"))
        with self.assertRaises(Refusal): self.api.record(self.token, self.wid, self.fx.observation(prepared, "cancelled"))
        self.api.record(self.token, self.wid, self.fx.observation(prepared, "archived"))
        self.assertTrue(self.fx.state()["archived"])

    def test_policy_supersession_does_not_reset_attempt_count(self):
        _, prepared = self.prepare()
        self.api.record(self.token, self.wid, self.fx.observation(prepared, "cancelled"))
        self.policy = self.revised(maxArchives=1)
        self.assertEqual(self.fx.state()["retention"]["recordedAttempts"], 1)
        with self.assertRaisesRegex(Refusal, "cap exhausted"): self.save()

    def test_no_owner_actor_fallback_after_a_delegated_request(self):
        receipt = self.save()
        with self.assertRaisesRegex(Refusal, "no owner fallback"): self.fx.owner()
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", receipt["commandId"])
            command["actor"] = "dashboard"; command.pop("retentionHash")
            self.ledger.put(db, "commands", command["id"], command)
        with self.assertRaisesRegex(Refusal, "no owner fallback"): self.fx.state()

    def test_removed_request_receipt_or_slot_fails_closed(self):
        receipt = self.save()
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (retention.slot(self.wid),))
        with self.assertRaises(Refusal): self.fx.state()

    def test_removed_receipt_blocks_historical_read(self):
        request = self.request(); self.save(request)
        key = digest({"kind": "run_request", "workspaceId": "a", "id": request["id"]})
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (key,))
        with self.assertRaisesRegex(Refusal, "receipt missing"): self.fx.state()

    def test_malformed_retention_pointer_is_a_bounded_refusal(self):
        self.save()
        for raw in ("{", "[]", '{"delegationHash":"wrong"}'):
            with self.ledger.tx() as db:
                db.execute("UPDATE snapshots SET data=? WHERE id=?", (raw, retention.slot(self.wid)))
            with self.subTest(raw=raw), self.assertRaises(Refusal): self.fx.state()

    def test_cli_cannot_review_policy_or_omit_exact_workspace(self):
        for operation in ("review", "revoke"):
            self.assertNotEqual(self.fx.cli(operation, self.request()).returncode, 0)
        self.assertNotEqual(self.fx.cli("request-delegated", self.request(), token="wrong").returncode, 0)
        self.assertNotEqual(self.fx.cli("request-delegated", self.request(), select=False).returncode, 0)

    def test_replay_cannot_target_another_worker(self):
        request = self.request(); self.save(request)
        with self.assertRaisesRegex(Refusal, "another worker"): self.api.request_delegated(self.token, "other-worker", request)

    def test_generic_actor_string_cannot_forge_delegation(self):
        request = {"id": "forged-retention-request", "kind": "archive", "expectedRevision": self.fx.revision(),
                   "payload": self.fx.state()["ownerRequestPayload"]}
        with self.assertRaisesRegex(Refusal, "proof is missing"): self.ledger.submit(request, actor=retention.ACTOR)
        self.assertEqual(self.ledger.snapshot()["commands"], [])

    def test_policy_change_blocks_old_preparation_without_changing_history(self):
        _, prepared = self.prepare(); self.policy = self.revised()
        with self.assertRaisesRegex(Refusal, "superseded"): self.api.check(self.token, self.wid, self.fx.check_request(prepared))
        self.assertEqual(self.fx.state()["handoffHash"], prepared["handoffHash"])
        self.api.record(self.token, self.wid, self.fx.observation(prepared, "cancelled"))

    def test_request_refuses_known_descendants_before_consuming_quota(self):
        request = self.request(); root = ("local", self.fx.worker()["threadId"])
        with patch.object(self.api.results.reviewer.settlement, "known_descendants", return_value={root, ("local", "child")}), self.assertRaisesRegex(Refusal, "descendants"):
            self.save(request)
        self.assertEqual(self.fx.state()["retention"]["recordedAttempts"], 0)

    def test_maintenance_and_stale_run_fence_new_requests(self):
        request = self.request(); before = self.fx.fx.logical()
        with patch.object(self.api.results.reviewer.settlement, "maintenance_check", side_effect=Refusal("maintenance")), self.assertRaisesRegex(Refusal, "maintenance"):
            self.save(request)
        self.assertEqual(before, self.fx.fx.logical())
        with patch("orchestrator.run_authority.time.time", return_value=time.time()+86401), self.assertRaisesRegex(Refusal, "expired"):
            self.save(request)

    def test_revoked_queued_request_is_rejected_by_normal_processor(self):
        receipt = self.save(); self.revoke()
        self.ledger.process(self.token)
        command = next(c for c in self.ledger.snapshot()["commands"] if c["id"] == receipt["commandId"])
        self.assertEqual(command["status"], "rejected"); self.assertEqual(self.fx.state()["retention"]["recordedAttempts"], 1)

    def test_brain_navigation_hint_is_not_eligibility_or_native_action(self):
        from orchestrator.brain_coordinator import BrainCoordinator
        result = BrainCoordinator(self.api.bridge).inspect(self.token)
        row = next(w for w in result["workers"] if w["workerId"] == self.wid)
        self.assertEqual(row["next"], "archive-handoff-state")
        self.assertFalse(row["canContinue"]); self.assertFalse(result["nativeCallMade"])


class RetentionDefaultTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_archive_handoff.ArchiveHandoffTest(); self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def test_owner_archive_without_policy_stays_available(self):
        state = self.fx.state()
        self.assertEqual(state["retention"]["status"], "not_delegated")
        _, prepared = self.fx.prepare()
        self.assertTrue(self.fx.api.check(self.fx.token, self.fx.wid, self.fx.check_request(prepared))["sendPermit"])

    def test_exact_owner_run_cannot_gain_phase_delegation(self):
        with self.fx.ledger.tx() as db:
            grant = runs.current_in(self.fx.ledger, db)["runHash"]
            meta = self.fx.ledger.get(db, "meta", 1); meta["paused"] = True; self.fx.ledger.put(db, "meta", 1, meta)
        request = {"id": "owner-retention-policy", "expectedRevision": self.fx.revision(), "runHash": grant,
                   "expectedPolicyHash": None, "maxArchives": 1, "minimumRetentionSeconds": 0,
                   "allowManagedWorktreeCleanup": True, "confirmed": True}
        with self.assertRaisesRegex(Refusal, "phase-delegated"):
            retention.review(self.fx.ledger, request, actor="dashboard_owner")
