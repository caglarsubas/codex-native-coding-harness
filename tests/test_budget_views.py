"""Synthetic saved accounting only; dashboard reads never invoke a collector."""
import copy
import time
import unittest
from unittest.mock import patch

from orchestrator import budget_views
from orchestrator.core import canonical
from orchestrator.workspaces import fingerprint
import test_phase_usage
import test_ownership_settlement


class BudgetViewsTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_phase_usage.PhaseUsageTest()
        self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.registry, self.ledger, self.store = self.fx.fx.registry, self.fx.ledger, self.fx.store

    def inspect(self): return budget_views.inspect(self.registry, self.ledger, "a")
    def row(self):
        result = self.inspect(); self.assertEqual(result["status"], "available", result)
        return result["allocations"][0]
    def mutate(self, **fields):
        with self.store.tx() as db:
            allocation = self.store.get(db, "allocations", self.fx.aid)
            allocation.update(fields); self.store.put(db, "allocations", self.fx.aid, allocation)

    def test_complete_counters_reuse_kernel_arithmetic_and_read_does_not_write(self):
        self.fx.start(); self.fx.save(); before = self.fx.logical()
        with budget_views.readonly(self.registry.db) as db: registry_before = fingerprint(db)
        with patch("orchestrator.admission.AdmissionStore.__init__", side_effect=AssertionError("No writer initialization")):
            report = self.inspect()
        self.assertEqual(before, self.fx.logical())
        with budget_views.readonly(self.registry.db) as db: self.assertEqual(registry_before, fingerprint(db))
        row = report["allocations"][0]
        self.assertEqual(row["observedTokens"], 240)  # Cached/reasoning subsets not added twice.
        self.assertEqual(row["heldTokens"], 11500)
        with self.store.tx() as db:
            kernel = self.store.budget(db, self.store.get(db, "allocations", self.fx.aid))
        self.assertEqual(row["recordedBalance"], kernel["remainingForNewWork"])
        self.assertFalse(row["effectContextChecked"])
        for key in ("executionAuthorized", "nativeCallMade", "atomicAcrossStores"): self.assertFalse(report[key])
        self.assertEqual(report["account"]["source"], "native_limit_record")

    def test_legacy_zero_is_historical_not_complete_phase_coverage(self):
        row = self.row()
        self.assertEqual(row["observedTokens"], 0)
        self.assertIsNone(row["recordedBalance"])
        self.assertIn("phase_journal_not_observed", row["issues"])

    def test_missing_usage_never_becomes_zero(self):
        self.mutate(usage=None); row = self.row()
        self.assertIsNone(row["observedTokens"]); self.assertIsNone(row["recordedBalance"])
        self.assertEqual(row["heldTokens"], 11500)

    def test_incomplete_and_stale_usage_suppress_balance_keep_high_water(self):
        self.fx.start(); self.fx.save()
        request = self.fx.request(); request["evidence"]["sessions"].pop(); self.fx.save(request)
        row = self.row(); self.assertEqual(row["observedTokens"], 240)
        self.assertIsNone(row["recordedBalance"]); self.assertIn("usage_evidence_incomplete", row["issues"])
        self.fx.save()
        with patch.object(budget_views.time, "time", return_value=time.time()+61):
            row = self.row(); self.assertIsNone(row["recordedBalance"])
            self.assertIn("usage_stale_or_future", row["issues"])

    def test_changed_membership_fences_earlier_balance(self):
        self.fx.save(); self.fx.start()
        row = self.row(); self.assertIn("membership_changed", row["issues"])
        self.assertIsNone(row["recordedBalance"])

    def test_complete_zero_and_negative_balance_are_not_clamped(self):
        self.fx.save(self.fx.request([self.fx.sample(current=test_phase_usage.values(1000, 800, 200, 100))]))
        self.assertEqual(self.row()["observedTokens"], 0)
        self.assertIsNotNone(self.row()["recordedBalance"])
        self.fx.save(self.fx.request([self.fx.sample(current=test_phase_usage.values(500000, 800, 200, 100))]))
        self.assertLess(self.row()["recordedBalance"], 0)

    def test_phase_pointer_removal_and_corruption_cannot_fallback(self):
        self.fx.save(); self.mutate(phaseUsageHash=None)
        self.assertEqual(self.inspect()["status"], "unavailable")

    def test_phase_journal_bytes_and_projection_are_checked(self):
        self.fx.save()
        with self.store.tx() as db:
            allocation = self.store.get(db, "allocations", self.fx.aid)
            allocation["usage"]["counters"]["inputTokens"] += 1
            self.store.put(db, "allocations", self.fx.aid, allocation)
        self.assertEqual(self.inspect()["status"], "unavailable")

    def test_native_account_pointer_removal_cannot_fallback(self):
        self.fx.save()
        with self.store.tx() as db:
            meta = self.store.get(db, "meta", 1); meta["nativeAccountHash"] = None
            self.store.put(db, "meta", 1, meta)
        self.assertEqual(self.inspect()["status"], "unavailable")

    def test_other_workspace_claims_only_contribute_anonymous_capacity(self):
        self.fx.save()
        other, token = self.fx.second_workspace()
        spec = self.store.snapshot()["allocations"][0]["spec"]
        self.store.open_allocation("foreign-private-id", workspace_id="b", binding_hash="a"*64,
            limits=spec["limits"], repositories=spec["repositories"])
        with self.store.tx() as db:
            claim = copy.deepcopy(self.store.rows(db, "claims")[0])
            claim.update(id="foreign-task-secret", allocationId="foreign-private-id")
            db.execute("INSERT INTO claims VALUES(?,?,?)", (claim["id"], claim["allocationId"], canonical(claim)))
        result = self.inspect(); raw = canonical(result)
        self.assertEqual(len(result["allocations"]), 1)
        self.assertEqual(result["sharedCapacity"]["recordedHeldClaims"], 2)
        for secret in ("foreign-private-id", "foreign-task-secret", "brain-b", str(self.ledger.root), "native-task"):
            self.assertNotIn(secret, raw)

    def test_changed_identity_or_permission_fails_closed(self):
        self.fx.save()
        self.store.db.chmod(0o644)
        self.assertEqual(self.inspect()["status"], "unavailable")
        self.store.db.chmod(0o600)
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["brainId"] = "replaced"
            self.ledger.put(db, "meta", 1, meta)
        self.assertEqual(self.inspect()["status"], "unavailable")

    def test_size_and_row_limits_refuse_without_partial_balances(self):
        self.fx.save()
        for name, limit in (("MAX_ROWS", 0), ("MAX_BYTES", 10), ("MAX_PHASES", 0)):
            with patch.object(budget_views, name, limit):
                result = self.inspect(); self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["allocations"], [])

    def test_cache_never_refreshes_clocks_or_exposes_identities_to_assistant(self):
        self.fx.save(); report = self.inspect(); revision = report["workspaceRevision"]
        cached = budget_views.cached_summary(report, revision, report["inspectedAt"])
        self.assertIsNotNone(cached["rows"][0]["recordedBalance"])
        for rev, now in ((revision+1, report["inspectedAt"]), (revision, report["inspectedAt"]+61), (revision, report["inspectedAt"]-1)):
            value = budget_views.cached_summary(report, rev, now)
            self.assertIsNone(value["rows"][0]["recordedBalance"])
            self.assertEqual(value["inspectedAt"], report["inspectedAt"])
        cached["rows"][0]["private"] = "SECRET"
        raw = canonical(budget_views.assistant_summary(cached))
        for secret in ("SECRET", self.fx.aid, "brain-a", "native-task"): self.assertNotIn(secret, raw)
        self.assertFalse(cached["sharedStateRechecked"])

    def test_cached_rows_are_bounded_without_summing_phase_wallets(self):
        self.fx.save(); report = self.inspect()
        report["allocations"] *= 9
        cached = budget_views.cached_summary(report, report["workspaceRevision"])
        self.assertEqual(cached["included"], 8); self.assertEqual(cached["omitted"], 1)
        self.assertNotIn("totalTokens", cached)


class BudgetSettlementTest(unittest.TestCase):
    def test_settlement_is_separate_until_incorporated(self):
        fx = test_ownership_settlement.OwnershipSettlementTest(); fx.setUp(); self.addCleanup(fx.tearDown)
        fx.settle(); before = fx.store.snapshot()
        report = budget_views.inspect(fx.bridge.registry, fx.ledger, "a")
        self.assertEqual(before, fx.store.snapshot())
        row = report["allocations"][0]
        self.assertEqual(row["heldTokens"], 0)
        self.assertEqual(row["unincorporatedSettledTokens"], 1000)
        self.assertIsNone(row["recordedBalance"])
