"""Event-driven wait boundaries on disposable state; no native operations."""
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import brain_waits
from orchestrator.core import Refusal, canonical, digest
import test_brain_coordinator


class BrainWaitTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_brain_coordinator.BrainCoordinatorTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.api, self.ledger, self.token = self.fx.api, self.fx.ledger, self.fx.token
        self.hold()

    def hold(self, value=True):
        with self.ledger.tx() as db:
            row = self.ledger.all(db, "queue")[0]; row["held"] = value
            self.ledger.put(db, "queue", row["id"], row)

    def wait(self): return self.fx.decide(choice="wait")
    def state(self, receipt): return self.api.wait_state(self.token, receipt["decisionHash"])
    def meta(self, **fields):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta.update(fields)
            self.ledger.put(db, "meta", 1, meta)

    def test_bound_wait_is_quiet_and_repeated_reads_are_logically_read_only(self):
        request = self.fx.request(choice="wait"); receipt = self.fx.decide(request)
        before = self.fx.logical()
        with patch("subprocess.Popen", side_effect=AssertionError("No native calls")):
            for _ in range(5):
                state = self.state(receipt)
                self.assertEqual(state["state"], "unchanged"); self.assertTrue(state["quietEligible"])
                self.assertFalse(state["nativeCallMade"]); self.assertFalse(state["executionAuthorized"])
                self.assertFalse(state["scheduleChangeAuthorized"])
            self.assertEqual(self.fx.decide(request), receipt)
        self.assertEqual(before, self.fx.logical())
        doc = self.api.read(self.token, receipt["decisionHash"])["decision"]
        self.assertEqual(set(doc["waitBoundary"]["sources"]), brain_waits.CATEGORIES)
        self.assertNotIn(self.token, canonical(doc))
        self.assertEqual(state["recordedAt"], doc["at"])

    def test_new_request_cannot_append_an_unchanged_wait(self):
        self.wait(); request = self.fx.request(choice="wait"); before = self.fx.logical()
        with self.assertRaisesRegex(Refusal, "No recorded event changed"): self.fx.decide(request)
        self.assertEqual(before, self.fx.logical())

    def test_controller_checkpoint_and_observation_bookkeeping_does_not_wake(self):
        receipt = self.wait()
        self.meta(lastReconciled=time.time(), checkpoint="Repeated idle checkpoint", inboxCheckedAt=time.time(),
                  heartbeat={"id": None, "status": "not_configured", "observedAt": time.time()})
        self.ledger.release(self.token, "Quiet wait")
        self.token = self.ledger.acquire("brain-a:next-turn")
        self.assertEqual(self.state(receipt)["state"], "unchanged")

    def test_clock_aging_never_renews_evidence_or_authorizes_work(self):
        receipt = self.wait(); before = self.fx.logical()
        with patch("orchestrator.brain_coordinator.time.time", return_value=time.time()+10000):
            state = self.state(receipt)
        self.assertFalse(state["executionAuthorized"]); self.assertFalse(state["quietEligible"])
        self.assertIn("eligibility", state["changedCategories"])
        self.assertEqual(before, self.fx.logical())

    def test_ready_candidate_requires_supervision_instead_of_idle_wait(self):
        self.hold(False); receipt = self.wait(); state = self.state(receipt)
        self.assertEqual(state["state"], "supervision_required")
        self.assertIn("eligible_work", state["supervisionReasons"]); self.assertFalse(state["quietEligible"])

    def test_recorded_event_reenters_guarded_selection_without_replaying_wait(self):
        receipt = self.wait(); wait_doc = self.api.read(self.token, receipt["decisionHash"])
        self.assertTrue(self.state(receipt)["quietEligible"])
        self.hold(False)
        state = self.state(receipt)
        self.assertIn("queue", state["changedCategories"]); self.assertFalse(state["quietEligible"])
        decision = self.fx.decide(); reserved = self.fx.reserve(decision)
        self.assertEqual(reserved["stage"], "reserved")
        self.assertEqual(len(self.fx.store.snapshot()["claims"]), 1)
        self.assertEqual(self.api.read(self.token, receipt["decisionHash"]), wait_doc)
        self.assertEqual(self.state(receipt)["state"], "superseded")

    def test_new_policy_and_shared_usage_are_changes_not_permissions(self):
        receipt = self.wait(); self.meta(concurrency=2)
        state = self.state(receipt); self.assertEqual(state["state"], "changed")
        self.assertIn("policy", state["changedCategories"])
        second = self.wait(); self.fx.fx.refresh_usage(total=100)
        state = self.state(second); self.assertIn("shared_admission", state["changedCategories"])
        self.assertFalse(state["quietEligible"])

    def test_stop_dominates_changed_input_and_listener(self):
        receipt = self.wait(); self.meta(decisionListener={"enabled": True}); self.fx.pause()
        state = self.state(receipt)
        self.assertEqual(state["state"], "stopped"); self.assertEqual(state["next"], "follow_safe_stop")
        self.assertFalse(state["quietEligible"]); self.assertIn("brain_stop", state["supervisionReasons"])

    def test_listener_preference_is_never_silently_disabled(self):
        self.meta(decisionListener={"enabled": True}); receipt = self.wait(); before = self.fx.logical()
        self.assertIn("idle_listener_enabled", self.state(receipt)["supervisionReasons"])
        self.assertFalse(self.state(receipt)["quietEligible"]); self.assertEqual(before, self.fx.logical())

    def test_schedule_identity_status_but_not_timestamp_is_significant(self):
        receipt = self.wait(); self.meta(heartbeat={"id": "heartbeat-a", "status": "PAUSED", "observedAt": time.time()})
        self.assertIn("policy", self.state(receipt)["changedCategories"])

    def test_pending_receipts_answers_and_follow_up_planning_require_attention(self):
        receipt = self.wait()
        for table, row, reason in (
            ("commands", {"id": "owner-input", "status": "completed", "needsBrainReceipt": True}, "pending_receipts"),
            ("decisions", {"id": "answer", "status": "received", "answer": "private inert input"}, "unresolved_answers"),
            ("continuations", {"id": "follow-up", "status": "needs_proposal"}, "follow_up_planning")):
            with self.ledger.tx() as db: self.ledger.put(db, table, row["id"], row)
            state = self.state(receipt)
            self.assertIn(table, state["changedCategories"]); self.assertIn(reason, state["supervisionReasons"])
            self.assertNotIn("private inert input", canonical(state))

    def test_open_question_alone_can_wait_without_model_polling(self):
        with self.ledger.tx() as db: self.ledger.put(db, "decisions", "question", {"id": "question", "status": "open"})
        receipt = self.wait(); self.assertTrue(self.state(receipt)["quietEligible"])

    def test_new_evidence_metadata_is_an_event_without_reading_proof_bytes(self):
        receipt = self.wait()
        with self.ledger.tx() as db:
            db.execute("INSERT INTO artifact_versions VALUES(?,?,?)", ("proof", canonical({"id": "proof"}), b"not-readable-proof"))
            db.execute("INSERT INTO observation_records VALUES(?,?)", ("observation", canonical({"observedAt": time.time()})))
        with patch("orchestrator.observations.read_regular", side_effect=AssertionError("No artifact inspection")):
            state = self.state(receipt)
        self.assertEqual(state["state"], "changed")
        self.assertIn("artifact_metadata", state["changedCategories"])
        self.assertIn("recorded_observations", state["changedCategories"])
        self.assertNotIn("not-readable-proof", canonical(state))

    def test_missing_local_worker_never_hides_retained_shared_claim(self):
        self.hold(False); created = self.fx.reserve(self.fx.decide())
        with self.ledger.tx() as db: db.execute("DELETE FROM workers WHERE id=?", (created["workerId"],))
        self.hold(); receipt = self.wait(); state = self.state(receipt)
        self.assertIn("retained_ownership", state["supervisionReasons"]); self.assertFalse(state["quietEligible"])

    def test_reserved_and_uncertain_workers_cannot_park_as_empty(self):
        self.hold(False); self.fx.reserve(self.fx.decide())
        receipt = self.wait(); state = self.state(receipt)
        self.assertIn("retained_ownership", state["supervisionReasons"])

    def test_orphan_shared_claim_is_not_free_capacity_or_quiet(self):
        self.hold(False); created = self.fx.reserve(self.fx.decide())
        with self.ledger.tx() as db: db.execute("DELETE FROM workers WHERE id=?", (created["workerId"],))
        with self.fx.store.tx() as db: db.execute("DELETE FROM allocations")
        self.hold(); receipt = self.wait()
        self.assertIn("unresolved_shared_ownership", self.state(receipt)["supervisionReasons"])
        self.assertFalse(self.state(receipt)["quietEligible"])

    def test_orphan_shared_resource_cannot_disappear_from_supervision(self):
        with self.fx.store.tx() as db:
            db.execute("INSERT INTO resources VALUES(?,?,?)", ("runner:"+"f"*64, "missing", time.time()))
        receipt = self.wait()
        self.assertIn("unresolved_shared_ownership", self.state(receipt)["supervisionReasons"])
        self.assertFalse(self.state(receipt)["quietEligible"])

    def test_reconciled_non_creation_waits_for_owner_without_impossible_result_review(self):
        import test_creation_recovery
        from orchestrator.brain_coordinator import BrainCoordinator
        fixture = test_creation_recovery.CreationRecoveryTest(); fixture.setUp(); self.addCleanup(fixture.tearDown)
        fixture.begin(); fixture.observe(); fixture.settle()
        api = BrainCoordinator(fixture.fx.bridge); context = api.inspect(fixture.token)
        request = self.fx.request(choice="wait") | {"expectedRevision": context["revision"], "contextHash": context["contextHash"]}
        receipt = api.decide(fixture.token, request)
        with patch("orchestrator.creation_recovery.artifact_in", side_effect=AssertionError("No proof scan")):
            self.assertTrue(api.wait_state(fixture.token, receipt["decisionHash"])["quietEligible"])
        terminal_hash = fixture.worker()["ownershipSettlementHash"]
        with fixture.ledger.tx() as db:
            db.execute("DELETE FROM snapshots WHERE id=?", (terminal_hash,))
        with self.assertRaises(Refusal): api.wait_state(fixture.token, receipt["decisionHash"])

    def test_quarantined_ownership_cannot_be_omitted_from_quiet_wait(self):
        with self.fx.store.tx() as db:
            db.execute("CREATE TABLE legacy_claims(id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("INSERT INTO legacy_claims VALUES(?,?)", ("legacy", canonical({"id": "legacy", "workspaceId": "a"})))
        receipt = self.wait()
        self.assertIn("retained_ownership", self.state(receipt)["supervisionReasons"])

    def test_wait_event_failure_rolls_back_boundary_pointer_and_receipt(self):
        request = self.fx.request(choice="wait"); before = self.fx.logical(); original = self.api.ledger.event
        def fail(db, kind, data):
            if kind == "brain_cycle_decided": raise RuntimeError("fixture crash")
            return original(db, kind, data)
        with patch.object(self.api.ledger, "event", side_effect=fail), self.assertRaises(RuntimeError):
            self.fx.decide(request)
        self.assertEqual(before, self.fx.logical())

    def test_stale_wait_context_is_rejected_before_any_write(self):
        request = self.fx.request(choice="wait"); self.fx.fx.refresh_usage(total=100); before = self.fx.logical()
        with self.assertRaisesRegex(Refusal, "context changed"): self.fx.decide(request)
        self.assertEqual(before, self.fx.logical())

    def test_different_workspaces_do_not_share_wait_receipts(self):
        receipt = self.wait()
        other = test_brain_coordinator.BrainCoordinatorTest(); other.setUp(); self.addCleanup(other.doCleanups)
        before = other.logical()
        with self.assertRaises(Refusal): other.api.wait_state(other.token, receipt["decisionHash"])
        self.assertEqual(before, other.logical())

    def test_new_decision_supersedes_wait_without_renewing_original(self):
        receipt = self.wait(); self.fx.decide(choice="handle"); before = self.fx.logical()
        self.assertEqual(self.state(receipt)["state"], "superseded")
        self.assertFalse(self.state(receipt)["quietEligible"]); self.assertEqual(before, self.fx.logical())

    def test_stop_still_dominates_a_superseded_wait(self):
        receipt = self.wait(); self.fx.decide(choice="handle"); self.fx.pause()
        self.assertEqual(self.state(receipt)["state"], "stopped")
        self.assertEqual(self.state(receipt)["next"], "follow_safe_stop")

    def test_old_unbound_wait_is_explicit_not_assumed_unchanged(self):
        # Build a genuine old-format document and corresponding pointers.
        receipt = self.wait()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); doc = self.api.document_in(db, receipt["decisionHash"])
            doc.pop("waitBoundary"); key = digest(doc)
            db.execute("DELETE FROM snapshots WHERE id=?", (receipt["decisionHash"],))
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (key, doc["kind"], canonical(doc)))
            from orchestrator.brain_coordinator import slot
            db.execute("UPDATE snapshots SET data=? WHERE id=?", (canonical({"decisionHash": key}), slot("a", doc["request"]["id"])))
            meta["brainCycleHash"] = key; self.ledger.put(db, "meta", 1, meta)
        self.assertEqual(self.api.wait_state(self.token, key)["state"], "unbound")
        self.assertFalse(self.api.wait_state(self.token, key)["quietEligible"])

    def test_concurrent_identical_wait_is_one_document(self):
        request = self.fx.request(choice="wait")
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: self.fx.decide(request), range(2)))
        self.assertEqual(results[0], results[1]); self.assertTrue(self.state(results[0])["quietEligible"])

    def test_cli_requires_workspace_controller_and_retained_wait(self):
        receipt = self.wait(); result = self.fx.cli("wait-state", receipt["decisionHash"])
        self.assertEqual(result.returncode, 0, result.stderr); self.assertEqual(json.loads(result.stdout)["state"], "unchanged")
        for fields in ({"select": False}, {"token": "wrong"}):
            self.assertNotEqual(self.fx.cli("wait-state", receipt["decisionHash"], **fields).returncode, 0)
        other = self.fx.decide(choice="handle")
        with self.assertRaisesRegex(Refusal, "wait decision"): self.state(other)

    def test_cli_never_initializes_missing_shared_store(self):
        receipt = self.wait(); path = self.fx.store.db
        path.rename(path.with_suffix(".retained"))
        result = self.fx.cli("wait-state", receipt["decisionHash"])
        self.assertNotEqual(result.returncode, 0); self.assertFalse(path.exists())

    def test_oversized_inventories_refuse_not_truncate_or_write(self):
        receipt = self.wait()
        with self.ledger.tx() as db:
            for i in range(501): self.ledger.put(db, "decisions", str(i), {"id": str(i), "status": "open"})
        before = self.fx.logical()
        with self.assertRaisesRegex(Refusal, "bound"): self.state(receipt)
        self.assertEqual(before, self.fx.logical())

    def test_large_input_bytes_refuse_and_do_not_leak(self):
        receipt = self.wait()
        with self.ledger.tx() as db: self.ledger.put(db, "decisions", "large", {"id": "large", "status": "open", "note": "x"*2_000_001})
        with self.assertRaisesRegex(Refusal, "byte bound"): self.state(receipt)

    def test_corrupt_receipt_refuses_without_repair(self):
        receipt = self.wait()
        with self.ledger.tx() as db:
            db.execute("UPDATE snapshots SET data='{}' WHERE id=?", (receipt["decisionHash"],))
        before = self.fx.logical()
        with self.assertRaises(Refusal): self.state(receipt)
        self.assertEqual(before, self.fx.logical())
