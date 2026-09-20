"""Private synthetic counter evidence only; no live collector or admission writes."""
import copy
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import phase_usage, native_supervision
from orchestrator.core import Refusal, canonical, digest
from test_native_creation import NativeCreationFixture
from test_native_supervision import usage_result


def values(input=100, cached=80, output=20, reasoning=10):
    return {"inputTokens": input, "cachedInputTokens": cached, "outputTokens": output, "reasoningOutputTokens": reasoning}


class PhaseUsageTest(NativeCreationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.aid = self.fx.binding["id"]
        self.usage = phase_usage.PhaseUsage(self.fx.bridge)
        self.native = native_supervision.NativeSupervision(self.fx.bridge)
        self.native.account_record(self.token, {"id": "account", "expectedHash": None, "observedAt": time.time(), "result": usage_result()})
        self.baseline_at = self.store.snapshot()["allocations"][0]["createdAt"]-1
        self.seq = 0

    def state(self): return self.usage.state(self.token, self.aid)
    def begin(self): return NativeCreationFixture.begin(self, NativeCreationFixture.request(self))
    def start(self):
        handoff = self.begin(); self.check(handoff); self.record(handoff)

    def sample(self, thread="brain-a", claim=None, role="brain", parent=None, current=None):
        return {"hostId": "local", "threadId": thread, "claimId": claim, "role": role, "parent": parent,
                "counterEpoch": "a"*64, "baseline": {"observedAt": self.baseline_at, "evidenceHash": "b"*64,
                    "counters": values(1000, 800, 200, 100) if role == "brain" else dict(phase_usage.ZERO)},
                "observedAt": time.time(), "evidenceHash": "c"*64, "counters": current or (values(1100, 880, 220, 110) if role == "brain" else values()), "complete": True}

    def request(self, sessions=None, **fields):
        self.seq += 1; state = self.state()
        if sessions is None:
            sessions = [self.sample()]
            if self.fx.claim()["native"]: sessions.append(self.sample("native-task", self.wid, "worker"))
        return {"id": "usage-"+str(self.seq), "expectedHash": state["expectedHash"], "contextHash": state["contextHash"],
                "observedAt": time.time(), "evidence": {"accountIdentityHash": state["accountIdentityHash"], "complete": True,
                    "includesDescendants": True, "evidenceHash": "d"*64, "sessions": sessions}, **fields}

    def save(self, request=None): return self.usage.record(self.token, self.aid, request or self.request())
    def budget_check(self):
        with self.store.tx() as db: self.store.check_budget(db, self.store.get(db, "allocations", self.aid))
    def doc(self):
        with self.store.tx() as db: return phase_usage.current_in(db, self.store.get(db, "allocations", self.aid))

    def test_read_does_not_initialize_or_write(self):
        before = self.logical(); state = self.state()
        self.assertEqual(before, self.logical()); self.assertEqual(state["status"], "needs_evidence")
        self.assertIsNone(state["expectedHash"])
        with self.store.tx() as db: self.assertFalse(phase_usage.exists(db))

    def test_brain_delta_and_worker_lifetime_no_double_counting_subsets(self):
        self.start(); owners = self.store.snapshot()["resources"]
        self.save(); state = self.state(); self.budget_check()
        self.assertEqual(self.doc()["counters"], values(200, 160, 40, 20))
        self.assertEqual(state["budget"]["observedTokens"], 240)
        self.assertEqual(state["knownRawTokensByRole"], {"brain": 120, "worker": 120})
        self.assertEqual(len(state["knownSessions"]), 2)
        self.assertEqual(state["budget"]["heldTokens"], 11500)
        self.assertEqual(owners, self.store.snapshot()["resources"])
        self.assertFalse(state["executionAuthorized"]); self.assertFalse(state["ownershipReleased"])

    def test_creation_boundaries_and_new_native_binding_require_refresh(self):
        self.save(); handoff = self.begin(); self.check(handoff)
        self.assertIn("phase_context_changed", self.state()["issues"])
        with self.fx.bridge.locked(self.token) as (db, _):
            with self.store.tx() as kernel:
                with self.assertRaisesRegex(Refusal, "context changed"):
                    phase_usage.enforce_context(self.fx.bridge, db, kernel, self.store.get(kernel, "allocations", self.aid))
        self.record(handoff)
        with self.assertRaisesRegex(Refusal, "membership changed"): self.budget_check()
        self.save(); self.budget_check()

    def test_missing_unknown_incomplete_and_stale_sessions_fence_old_health(self):
        self.start(); self.save()
        for change in ("missing", "unknown", "incomplete", "future"):
            request = self.request(); row = request["evidence"]["sessions"][1]
            if change == "missing": request["evidence"]["sessions"].pop()
            if change == "unknown": row["counters"] = None
            if change == "incomplete": row["complete"] = False
            if change == "future": row["observedAt"] += 1
            self.save(request)
            self.assertEqual(self.state()["status"], "needs_evidence")
            with self.assertRaises(Refusal): self.budget_check()
            self.assertEqual(self.doc()["counters"], values(200, 160, 40, 20))
        self.save(); self.budget_check()

    def test_old_session_sample_stays_stale_when_outer_observation_newer(self):
        self.save(); request = self.request()
        later = time.time()+61; request["observedAt"] = later
        with patch.object(self.store, "clock", return_value=later):
            self.save(request)
            self.assertTrue(any(i.startswith("session_usage_unavailable") for i in self.doc()["issues"]))

    def test_new_envelope_does_not_extend_constituent_freshness(self):
        request = self.request(); original_time = request["evidence"]["sessions"][0]["observedAt"]
        later = time.time()+30; request["observedAt"] = later
        with patch.object(self.store, "clock", return_value=later): self.save(request)
        self.assertEqual(self.state()["oldestSampleAt"], original_time)
        with patch.object(self.store, "clock", return_value=original_time+61):
            self.assertIn("phase_usage_stale", self.state()["issues"])
            with self.store.tx() as db:
                allocation = self.store.get(db, "allocations", self.aid)
                with self.assertRaises(Refusal): self.store.fresh(allocation["usage"]["observedAt"], self.store.get(db, "meta", 1)["policy"])

    def test_new_retained_pause_descendant_invalidates_effect_context(self):
        self.start(); self.save()
        from orchestrator.run_authority import retain
        root = {"hostId": "local", "threadId": "native-task"}
        with self.ledger.tx() as db:
            retain(db, "workspace_pause_evidence", {"document": {"tasks": [
                {**root, "parent": None}, {"hostId": "local", "threadId": "new-child", "parent": root}]}})
        self.assertIn("phase_context_changed", self.state()["issues"])
        with self.fx.bridge.locked(self.token) as (db, _):
            with self.store.tx() as kernel:
                with self.assertRaisesRegex(Refusal, "context changed"):
                    phase_usage.enforce_context(self.fx.bridge, db, kernel, self.store.get(kernel, "allocations", self.aid))
        self.save(); self.assertIn("required_session_missing", self.doc()["issues"])

    def test_record_rechecks_native_context_after_state_read(self):
        request = self.request(); self.start(); before = self.logical()
        with self.assertRaisesRegex(Refusal, "source changed"): self.save(request)
        self.assertEqual(before, self.logical())

    def test_pending_creation_invalidates_older_coverage(self):
        self.save(); handoff = self.begin(); self.check(handoff)
        self.record(handoff, outcome="pending", threadId=None, clientThreadId="pending-client")
        with self.assertRaisesRegex(Refusal, "membership changed"): self.budget_check()
        self.save(); self.assertTrue(any(i.startswith("unresolved_native_creation") for i in self.doc()["issues"]))
        with self.assertRaises(Refusal): self.budget_check()

    def second_workspace(self):
        from orchestrator.core import Ledger
        from orchestrator.dispatch_admission import DispatchAdmission
        ledger = Ledger(self.fx.registry.root.parent / "second-usage")
        ledger.initialize({"schemaVersion": 1, "brainId": "brain-b", "repositories": [
            {"id": "a", "path": str(self.repo), "projectId": "project-b", "ref": "origin/main", "mergePolicy": "manual", "policyProfile": "standard"}]})
        self.fx.registry.register("b", "Other", ledger.root)
        other = phase_usage.PhaseUsage(DispatchAdmission(self.fx.registry, "b", self.store))
        return other, ledger.acquire("brain-b:fixture")

    def test_context_detects_another_workspace_brain_and_foreign_allocation(self):
        other, token = self.second_workspace()
        self.start(); rows = self.request()["evidence"]["sessions"]
        rows.append(self.sample("brain-b", self.wid, "nested", {"hostId": "local", "threadId": "native-task"}))
        with self.assertRaisesRegex(Refusal, "Foreign"): self.save(self.request(rows))
        with self.assertRaisesRegex(Refusal, "Foreign"): other.state(token, self.aid)

    def test_two_workspaces_keep_independent_phase_totals_and_replay_ids(self):
        other, token = self.second_workspace()
        spec = self.store.snapshot()["allocations"][0]["spec"]
        self.store.open_allocation("phase-b", workspace_id="b", binding_hash="a"*64, limits=spec["limits"], repositories=spec["repositories"])
        first = self.request(); self.save(first)
        state = other.state(token, "phase-b")
        brain = self.sample("brain-b", current=values(1500, 1200, 300, 150))
        request = {"id": first["id"], "expectedHash": None, "contextHash": state["contextHash"], "observedAt": time.time(),
            "evidence": {"accountIdentityHash": state["accountIdentityHash"], "complete": True, "includesDescendants": True,
                "evidenceHash": "d"*64, "sessions": [brain]}}
        other.record(token, "phase-b", request)
        self.assertEqual(self.state()["knownRawTokensByRole"], {"brain": 120})
        self.assertEqual(other.state(token, "phase-b")["knownRawTokensByRole"], {"brain": 600})
        self.assertEqual(self.state()["accountIdentityHash"], state["accountIdentityHash"])
        with self.assertRaises(Refusal): other.record(self.token, "phase-b", request)

    def test_expired_read_and_replay_do_not_refresh_evidence(self):
        request = self.request(); self.save(request); before = self.logical()
        with patch.object(self.store, "clock", return_value=time.time()+61):
            self.assertIn("phase_usage_stale", self.state()["issues"])
            self.save(request)
        self.assertEqual(before, self.logical())

    def test_closed_schema_invalid_counters_duplicate_and_oversized_refuse(self):
        for field, value in (("text", "PRIVATE-NOT-ALLOWED"), ("complete", "yes")):
            request = self.request(); request["evidence"]["sessions"][0][field] = value
            with self.assertRaises(Refusal): self.save(request)
        for value in (-1, True, float("nan"), 10**15):
            request = self.request(); request["evidence"]["sessions"][0]["counters"]["inputTokens"] = value
            with self.assertRaises(Refusal): self.save(request)
        request = self.request(); request["evidence"]["sessions"] *= 2
        with self.assertRaisesRegex(Refusal, "Duplicate"): self.save(request)
        with self.assertRaises(Refusal): self.save({**self.request(), "text": "x"*128000})

    def test_higher_previous_phase_totals_cannot_be_reset_by_first_record(self):
        with self.store.tx() as db:
            allocation = self.store.get(db, "allocations", self.aid)
            allocation["usage"]["counters"] = values(9000, 800, 200, 100)
            self.store.put(db, "allocations", self.aid, allocation)
        self.save()
        self.assertIn("phase_counter_regressed", self.doc()["issues"])
        self.assertEqual(self.doc()["counters"]["inputTokens"], 9000)

    def test_retained_journal_tampering_refuses(self):
        self.save()
        with self.store.tx() as db:
            doc = phase_usage.current_in(db, self.store.get(db, "allocations", self.aid))
            key = digest(doc); doc["counters"]["inputTokens"] += 1
            db.execute("UPDATE phase_usage_records SET data=? WHERE hash=?", (canonical(doc), key))
        with self.assertRaisesRegex(Refusal, "integrity"): self.state()

    def test_sample_baseline_epoch_and_high_water_are_sticky(self):
        self.start(); self.save()
        for change in ("baseline", "epoch", "lower"):
            request = self.request(); row = request["evidence"]["sessions"][0]
            if change == "baseline": row["baseline"]["counters"] = values(1010, 800, 200, 100)
            if change == "epoch": row["counterEpoch"] = "e"*64
            if change == "lower": row["counters"] = values(1090, 870, 220, 110)
            self.save(request)
            with self.assertRaises(Refusal): self.budget_check()
            self.assertEqual(self.doc()["counters"]["inputTokens"], 200)
        self.save(); self.budget_check()

    def test_invalid_delta_subsets_do_not_become_usage(self):
        request = self.request(); request["evidence"]["sessions"][0]["counters"] = values(1100, 1000, 220, 110)
        self.save(request)
        self.assertTrue(any(i.startswith("counter_delta_invalid") for i in self.doc()["issues"]))
        with self.assertRaises(Refusal): self.budget_check()

    def test_descendant_tree_and_retained_membership(self):
        self.start(); root = {"hostId": "local", "threadId": "native-task"}
        rows = [self.sample(), self.sample("native-task", self.wid, "worker"), self.sample("child", self.wid, "nested", root),
                self.sample("reviewer", self.wid, "reviewer", {"hostId": "local", "threadId": "child"})]
        self.save(self.request(rows)); self.budget_check()
        self.assertEqual(self.doc()["counters"]["inputTokens"], 400)
        self.save(); self.assertIn("previous_session_missing", self.doc()["issues"])
        with self.assertRaises(Refusal): self.budget_check()

    def test_foreign_or_cyclic_ancestry_refuses(self):
        self.start()
        for parent in ("child", "missing", "brain-a"):
            rows = [self.sample(), self.sample("native-task", self.wid, "worker"),
                    self.sample("child", self.wid, "nested", {"hostId": "local", "threadId": parent})]
            request = self.request(rows); before = self.logical()
            with self.assertRaisesRegex(Refusal, "ancestry"): self.save(request)
            self.assertEqual(before, self.logical())

    def test_wrong_root_role_foreign_claim_and_pending_identity_refuse(self):
        self.start()
        for field, value in (("claimId", "foreign"), ("role", "brain"), ("role", "reviewer"), ("hostId", "remote")):
            request = self.request(); request["evidence"]["sessions"][1][field] = value
            with self.assertRaises(Refusal): self.save(request)

    def test_nonzero_worker_baseline_and_late_brain_baseline_refuse(self):
        self.start()
        request = self.request(); request["evidence"]["sessions"][1]["baseline"]["counters"] = values()
        with self.assertRaisesRegex(Refusal, "full task lifetime"): self.save(request)
        request = self.request(); request["evidence"]["sessions"][0]["baseline"]["observedAt"] = time.time()-0.001
        with self.assertRaises(Refusal): self.save(request)

    def test_account_mismatch_is_retained_blocker_not_implicit_account_change(self):
        self.save(); request = self.request(); request["evidence"]["accountIdentityHash"] = "f"*64
        self.save(request)
        self.assertIn("account_identity_changed", self.doc()["issues"])
        with self.assertRaises(Refusal): self.budget_check()
        self.save(); self.budget_check()

    def test_inventory_flags_never_inferred(self):
        for key in ("complete", "includesDescendants"):
            request = self.request(); request["evidence"][key] = False; self.save(request)
            self.assertIn("inventory_incomplete", self.doc()["issues"])

    def test_stale_future_and_changed_sources_refuse_without_writes(self):
        for change in ({"observedAt": time.time()-100}, {"observedAt": time.time()+5}, {"contextHash": "f"*64}, {"expectedHash": "a"*64}):
            request = self.request(**change); before = self.logical()
            with self.assertRaises(Refusal): self.save(request)
            self.assertEqual(before, self.logical())

    def test_replay_is_historical_and_does_not_revive_health(self):
        one = self.request(); receipt = self.save(one)
        two = self.request(); two["evidence"]["complete"] = False; self.save(two)
        before = self.logical(); replay = self.save(one)
        self.assertEqual(before, self.logical()); self.assertTrue(replay["historical"])
        self.assertEqual(replay["recordHash"], receipt["recordHash"])
        with self.assertRaises(Refusal): self.budget_check()
        with self.assertRaises(Refusal): self.save({**one, "observedAt": time.time()})

    def test_transaction_failure_rolls_back_all_usage_state(self):
        request = self.request(); before = self.logical()
        with patch.object(self.store, "event", side_effect=RuntimeError("fixture failure")):
            with self.assertRaises(RuntimeError): self.save(request)
        self.assertEqual(before, self.logical()); self.save(request); self.budget_check()

    def test_concurrent_records_have_one_winner(self):
        requests = [self.request(), self.request()]
        def attempt(request):
            try: return self.save(request)
            except Refusal: return None
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(attempt, requests))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_pause_and_stopped_run_do_not_prevent_accounting_or_resume(self):
        self.start(); self.fx.fx.fx.command("pause")
        before = self.fx.worker(); self.save()
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertEqual(before, self.fx.worker())

    def test_legacy_update_pointer_loss_and_projection_drift_refuse(self):
        self.save(); observation = self.store.snapshot()["allocations"][0]["usage"]
        with self.assertRaisesRegex(Refusal, "legacy updates"): self.store.observe_usage(self.aid, observation)
        with self.store.tx() as db:
            allocation = self.store.get(db, "allocations", self.aid); allocation["usage"]["counters"]["inputTokens"] += 1
            self.store.put(db, "allocations", self.aid, allocation)
        with self.assertRaisesRegex(Refusal, "projection diverged"): self.budget_check()
        with self.store.tx() as db:
            allocation = self.store.get(db, "allocations", self.aid); allocation.pop("phaseUsageHash")
            self.store.put(db, "allocations", self.aid, allocation)
        with self.assertRaisesRegex(Refusal, "pointer missing"): self.state()

    def test_cli_roundtrip_and_wrong_controller(self):
        state = self.cli("phase-usage-state", self.aid)
        self.assertEqual(state.returncode, 0, state.stderr)
        saved = self.cli("phase-usage-record", self.aid, request=self.request())
        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertEqual(self.state()["status"], "usage_observed")
        with self.assertRaises(Refusal): self.usage.state("wrong", self.aid)
        with self.assertRaises(Refusal): self.usage.record("wrong", self.aid, self.request())
        absent = self.cli("phase-usage-state", self.aid, select=False)
        self.assertNotEqual(absent.returncode, 0)

    def test_overrun_is_retained_and_reserve_not_spent(self):
        self.save(self.request([self.sample(current=values(1_000_000, 800, 200, 100))]))
        self.assertGreater(self.doc()["counters"]["inputTokens"], 100000)
        self.assertLess(self.state()["budget"]["remainingForNewWork"], 0)
        with self.assertRaisesRegex(Refusal, "headroom exhausted"): self.budget_check()


class PhaseUsageSettlementTest(unittest.TestCase):
    def setUp(self):
        import test_ownership_settlement
        self.fx = test_ownership_settlement.OwnershipSettlementTest(); self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.bridge = self.fx.bridge; self.store = self.fx.store; self.token = self.fx.token
        self.aid = self.fx.fx.fx.binding["id"]; self.usage = phase_usage.PhaseUsage(self.bridge)
        self.native = native_supervision.NativeSupervision(self.bridge)
        self.native.account_record(self.token, {"id": "account", "expectedHash": None, "observedAt": time.time(), "result": usage_result()})
        self.base_at = self.store.snapshot()["allocations"][0]["createdAt"]-1
        self.seq = 0

    def request(self, final):
        self.seq += 1; state = self.usage.state(self.token, self.aid)
        brain = {"hostId": "local", "threadId": "brain-a", "claimId": None, "role": "brain", "parent": None,
            "counterEpoch": "b"*64, "baseline": {"observedAt": self.base_at, "evidenceHash": "b"*64, "counters": dict(phase_usage.ZERO)},
            "observedAt": time.time(), "evidenceHash": "b"*64, "counters": values(), "complete": True}
        rows = [brain]
        for sample in final["usage"].get("sessions", []):
            row = {**sample, "claimId": self.fx.wid, "role": "worker" if sample["threadId"] == "worker-fixture" else "nested",
                   "parent": None if sample["threadId"] == "worker-fixture" else {"hostId": "local", "threadId": "worker-fixture"},
                   "baseline": {"observedAt": self.base_at, "evidenceHash": "b"*64, "counters": dict(phase_usage.ZERO)}, "observedAt": time.time()}
            rows.append(row)
        return {"id": "usage-"+str(self.seq), "expectedHash": state["expectedHash"], "contextHash": state["contextHash"], "observedAt": time.time(),
            "evidence": {"accountIdentityHash": state["accountIdentityHash"], "complete": True, "includesDescendants": True, "evidenceHash": "d"*64, "sessions": rows}}

    def save(self, request): return self.usage.record(self.token, self.aid, request)

    def test_settlement_is_incorporated_only_by_exact_complete_session_evidence(self):
        final = self.fx.evidence(descendants=["child"]); self.fx.settle(final)
        self.assertEqual(self.fx.budget()["unincorporatedSettledTokens"], 2000)
        self.save(self.request(final))
        budget = self.fx.budget()
        self.assertEqual(budget["unincorporatedSettledTokens"], 0)
        self.assertEqual(budget["observedTokens"], 2120)
        self.assertEqual(budget["heldTokens"], 0)
        self.assertEqual(self.fx.worker()["status"], "settled")

    def test_settlement_does_not_drop_previously_counted_sessions(self):
        final = self.fx.evidence(); before = self.request(final); self.save(before)
        self.fx.settle(final)
        with self.store.tx() as db:
            with self.assertRaisesRegex(Refusal, "membership changed"):
                self.store.check_budget(db, self.store.get(db, "allocations", self.aid))
        self.save(self.request(final))
        self.assertEqual(self.fx.budget()["unincorporatedSettledTokens"], 0)

    def test_settled_usage_regression_epoch_change_and_later_growth_block(self):
        final = self.fx.evidence(); self.fx.settle(final)
        for field, value in (("counterEpoch", "e"*64), ("counters", values(900, 600, 200, 100)), ("counters", values(700, 600, 200, 100))):
            request = self.request(final); request["evidence"]["sessions"][1][field] = value
            receipt = self.save(request)
            self.assertTrue(any(i.startswith("settled_usage_mismatch") for i in receipt["issues"]))
            self.assertEqual(self.fx.budget()["unincorporatedSettledTokens"], 1000)

    def test_non_creation_receipt_incorporates_only_actual_zero_without_inventing_task(self):
        import test_creation_recovery
        other = test_creation_recovery.CreationRecoveryTest(); other.setUp(); self.addCleanup(other.tearDown)
        other.begin(); final = other.evidence(); other.settle(final)
        api = phase_usage.PhaseUsage(other.fx.bridge)
        native = native_supervision.NativeSupervision(other.fx.bridge)
        native.account_record(other.token, {"id": "account", "expectedHash": None, "observedAt": time.time(), "result": usage_result()})
        aid = other.fx.binding["id"]; state = api.state(other.token, aid)
        brain = self.request({"usage": {}})["evidence"]["sessions"][0]
        brain["baseline"]["observedAt"] = other.store.snapshot()["allocations"][0]["createdAt"]-1
        request = {"id": "zero", "expectedHash": state["expectedHash"], "contextHash": state["contextHash"], "observedAt": time.time(),
            "evidence": {"accountIdentityHash": state["accountIdentityHash"], "complete": True, "includesDescendants": True,
                "evidenceHash": "d"*64, "sessions": [brain]}}
        result = api.record(other.token, aid, request)
        self.assertEqual(result["issues"], [])
        self.assertEqual(other.store.snapshot()["allocations"][0]["usage"]["settledClaimIds"], [other.wid])


if __name__ == "__main__": unittest.main()
