import copy
import multiprocessing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from orchestrator.admission import AdmissionStore, counters
from orchestrator.core import Refusal


POLICY = {"maxParallelTasks": 2, "maxObservationAgeSeconds": 60, "minAccountRemainingPercent": 10}
LIMITS = {"maxParallelTasks": 2, "maxTasks": 4, "tokenBudget": 10000, "checkpointReserveTokens": 1000}
REPO = "repo-remote:" + "a" * 64
OTHER = "repo-remote:" + "b" * 64
RUNNER = "runner:" + "c" * 64
EVIDENCE = "d" * 64
ESTIMATE = {"workTokens": 1000, "reviewTokens": 500, "handoffTokens": 100}


def usage(input_tokens=0, output_tokens=0):
    return {"inputTokens": input_tokens, "cachedInputTokens": input_tokens // 2,
            "outputTokens": output_tokens, "reasoningOutputTokens": output_tokens // 2}


def contention(root, allocation, claim, results):
    try:
        AdmissionStore(root, clock=lambda: 1000).reserve(claim, allocation, repositories=["repo"], estimates=ESTIMATE)
        results.put("reserved")
    except Refusal:
        results.put("refused")


class AdmissionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.now = 1000
        self.store = AdmissionStore(self.root, policy=POLICY, clock=lambda: self.now)
        self.allocate("a", "alpha")
        self.account()
        self.observe("a")

    def tearDown(self):
        self.tmp.cleanup()

    def allocate(self, aid, wid, repo=REPO, limits=None):
        return self.store.open_allocation(aid, workspace_id=wid, binding_hash=EVIDENCE,
            limits=limits or LIMITS, repositories={"repo": [repo], "other": [OTHER]}, runners=[RUNNER])

    def account(self, used=20, **extra):
        value = {"observedAt": self.now, "evidenceHash": EVIDENCE,
                 "windows": {"short": {"usedPercent": used, "resetsAt": self.now + 100},
                             "long": {"usedPercent": used, "resetsAt": self.now + 10000}}, **extra}
        self.store.observe_account(value)
        return value

    def observe(self, aid, tokens=None, included=None, **extra):
        value = {"observedAt": self.now, "evidenceHash": EVIDENCE, "counters": tokens or usage(),
                 "coverage": ["brain", "workers", "reviews"], "settledClaimIds": included or [], **extra}
        self.store.observe_usage(aid, value)
        return value

    def reserve(self, cid="claim", aid="a", repo="repo", **extra):
        return self.store.reserve(cid, aid, repositories=[repo], estimates=ESTIMATE, **extra)

    def start(self, cid="claim", aid="a", repo="repo"):
        self.reserve(cid, aid, repo)
        self.store.begin(cid)
        self.store.bind(cid, host_id="local", thread_id="native-" + cid)

    def finish(self, cid="claim", tokens=None, outcome="terminal"):
        return self.store.settle(cid, actual=tokens or usage(1000, 500), evidence_hash=EVIDENCE,
                                 observed_at=self.now, outcome=outcome)

    def test_atomic_capacity_and_budget_receipt_is_not_authority(self):
        result = self.reserve()
        state = self.store.snapshot()
        self.assertFalse(state["executionAuthorized"])
        self.assertFalse(state["dispatchIntegrated"])
        self.assertEqual(result["status"], "reserved")
        self.assertEqual(state["allocations"][0]["budget"]["remainingForNewWork"], 7400)
        self.assertEqual(len(state["resources"]), 1)

    def test_duplicate_request_and_restart_preserve_ownership(self):
        first = self.reserve()
        self.assertEqual(self.reserve(), first)
        before = self.store.snapshot()
        reopened = AdmissionStore(self.root, clock=lambda: self.now)
        self.assertEqual(reopened.snapshot(), before)
        with self.assertRaisesRegex(Refusal, "reused"):
            reopened.reserve("claim", "a", repositories=["other"], estimates=ESTIMATE)
        self.assertEqual(self.store.snapshot(), before)

    def test_transaction_failure_rolls_back_all_claim_and_resource_writes(self):
        before = self.store.snapshot()
        with self.store.tx() as db:
            db.execute("CREATE TRIGGER fixture_failure BEFORE INSERT ON resources BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.reserve()
        self.assertEqual(self.store.snapshot(), before)

    def test_two_processes_contending_for_same_repository_have_one_winner(self):
        self.allocate("b", "beta"); self.observe("b")
        ctx = multiprocessing.get_context("spawn")
        results = ctx.Queue()
        processes = [ctx.Process(target=contention, args=(str(self.root), aid, "claim-" + aid, results)) for aid in ("a", "b")]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sorted(results.get(timeout=2) for _ in processes), ["refused", "reserved"])
        results.close(); results.join_thread()
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)

    def test_cross_workspace_global_slot_race_has_one_winner(self):
        self.allocate("b", "beta", repo=OTHER); self.observe("b")
        # Separate fixture store policy, never a live policy update.
        with self.store.tx() as db:
            meta = self.store.get(db, "meta", 1); meta["policy"]["maxParallelTasks"] = 1
            self.store.put(db, "meta", 1, meta)
        ctx = multiprocessing.get_context("spawn"); results = ctx.Queue()
        processes = [ctx.Process(target=contention, args=(str(self.root), aid, "claim-" + aid, results)) for aid in ("a", "b")]
        for process in processes: process.start()
        for process in processes:
            process.join(10); self.assertEqual(process.exitcode, 0)
        self.assertEqual(sorted(results.get(timeout=2) for _ in processes), ["refused", "reserved"])
        results.close(); results.join_thread()
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)

    def test_global_slots_count_review_and_nested_tasks_in_other_workspaces(self):
        self.allocate("b", "beta", repo=OTHER); self.observe("b")
        self.reserve(role="reviewer")
        self.reserve("second", "b", role="nested")
        with self.assertRaisesRegex(Refusal, "Global task slots"):
            self.reserve("third", repo="other")

    def test_workspace_limit_and_phase_attempt_limit(self):
        self.allocate("b", "beta", repo=OTHER, limits={**LIMITS, "maxParallelTasks": 1, "maxTasks": 1})
        self.observe("b")
        self.reserve("second", "b")
        with self.assertRaisesRegex(Refusal, "Workspace task slots"):
            self.reserve("third", "b")
        self.finish("second", tokens=usage(), outcome="not_created")
        with self.assertRaisesRegex(Refusal, "task-attempt"):
            self.reserve("third", "b")

    def test_stale_account_blocks_new_claim_without_releasing_old(self):
        self.reserve()
        before = self.store.snapshot()
        self.now += 61
        self.observe("a")
        with self.assertRaisesRegex(Refusal, "Fresh"):
            self.reserve("second", repo="other")
        self.assertEqual(self.store.snapshot()["resources"], before["resources"])

    def test_begin_rechecks_stale_phase_usage_and_is_one_shot(self):
        self.reserve()
        self.now += 61; self.account()
        with self.assertRaisesRegex(Refusal, "Fresh"):
            self.store.begin("claim")
        self.observe("a")
        self.store.begin("claim")
        with self.assertRaisesRegex(Refusal, "already attempted"):
            self.store.begin("claim")
        self.assertEqual(self.store.snapshot()["claims"][0]["status"], "starting")

    def test_begin_rechecks_new_usage_without_freeing_reservation(self):
        self.reserve(); self.now += 1
        self.observe("a", usage(8000, 0))
        with self.assertRaisesRegex(Refusal, "headroom"): self.store.begin("claim")
        self.assertEqual(self.store.snapshot()["claims"][0]["status"], "reserved")
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)

    def test_unknown_incomplete_future_and_reset_usage_are_not_unlimited(self):
        self.allocate("b", "beta", repo=OTHER)
        with self.assertRaisesRegex(Refusal, "coverage"):
            self.reserve("second", "b")
        self.observe("b", coverage=["workers"])
        with self.assertRaisesRegex(Refusal, "coverage"):
            self.reserve("second", "b")
        with self.assertRaisesRegex(Refusal, "Fresh"):
            self.observe("b", observedAt=self.now + 1)
        self.now += 1
        self.account(windows={"short": {"usedPercent": 20, "resetsAt": self.now + 1},
                              "long": {"usedPercent": 20, "resetsAt": self.now + 1000}})
        self.now += 2; self.observe("a")
        with self.assertRaisesRegex(Refusal, "reset"):
            self.reserve()

    def test_unknown_account_and_low_headroom_block(self):
        with self.store.tx() as db:
            meta = self.store.get(db, "meta", 1); meta["account"] = None
            self.store.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "unknown"):
            self.reserve()
        self.now += 1; self.account(used=95)
        with self.assertRaisesRegex(Refusal, "headroom"):
            self.reserve()

    def test_subset_counts_not_added_or_discounted(self):
        self.assertEqual(counters(usage(1000, 100)), 1100)
        self.now += 1; self.observe("a", tokens=usage(7000, 1000))
        with self.assertRaisesRegex(Refusal, "checkpoint reserve"):
            self.reserve()
        for bad in ({**usage(), "inputTokens": True}, {**usage(), "inputTokens": -1},
                    {**usage(), "cachedInputTokens": 1}, {**usage(), "reasoningOutputTokens": 1}):
            with self.subTest(bad=bad), self.assertRaises(Refusal):
                counters(bad)

    def test_inflight_uncertainty_never_expires_or_restarts(self):
        self.reserve(); self.store.begin("claim"); self.store.block("claim", EVIDENCE)
        self.now += 10000
        reopened = AdmissionStore(self.root, clock=lambda: self.now)
        self.assertEqual(reopened.snapshot()["claims"][0]["status"], "uncertain")
        self.assertEqual(len(reopened.snapshot()["resources"]), 1)
        with self.assertRaises(Refusal): reopened.begin("claim")
        with self.assertRaises(Refusal): reopened.close_allocation("a", EVIDENCE)
        reopened.bind("claim", host_id="local", thread_id="discovered-native")
        self.assertEqual(reopened.snapshot()["claims"][0]["status"], "running")

    def test_reconciled_absence_is_explicit_not_automatic_retry(self):
        self.reserve(); self.store.begin("claim"); self.store.block("claim", EVIDENCE)
        self.finish(tokens=usage(), outcome="not_created")
        self.assertEqual(self.reserve()["status"], "settled")
        self.assertEqual(self.store.snapshot()["resources"], [])
        with self.assertRaises(Refusal): self.store.begin("claim")

    def test_unique_native_identity_across_workspaces_and_settlements(self):
        self.start()
        self.finish()
        self.allocate("b", "beta"); self.observe("b")
        self.reserve("second", "b"); self.store.begin("second")
        with self.assertRaisesRegex(Refusal, "already belongs"):
            self.store.bind("second", host_id="local", thread_id="native-claim")
        self.store.bind("second", host_id="remote", thread_id="native-claim")
        self.store.bind("second", host_id="remote", thread_id="native-claim")
        with self.assertRaisesRegex(Refusal, "already bound"):
            self.store.bind("second", host_id="remote", thread_id="changed")

    def test_global_runner_exclusion_and_exit_evidence(self):
        self.allocate("b", "beta", repo=OTHER); self.observe("b")
        self.start(); self.start("second", "b")
        runner = lambda cid, op, **kw: self.store.runner(cid, RUNNER, op, evidence_hash=EVIDENCE,
                                                       observed_at=kw.get("at", self.now))
        self.now += 1; runner("claim", "acquire")
        with self.assertRaisesRegex(Refusal, "unavailable"): runner("second", "acquire")
        with self.assertRaisesRegex(Refusal, "another"): runner("second", "release")
        with self.assertRaisesRegex(Refusal, "predates"): runner("claim", "release", at=1000)
        with self.assertRaisesRegex(Refusal, "Runner still owned"): self.finish()
        self.store.block("claim", EVIDENCE)
        runner("claim", "release")
        self.finish()
        runner("second", "acquire")

    def test_overrun_is_recorded_and_blocks_next_work(self):
        self.start(); self.finish(tokens=usage(10000, 1000))
        self.assertLess(self.store.snapshot()["allocations"][0]["budget"]["remainingForNewWork"], 0)
        with self.assertRaisesRegex(Refusal, "headroom"): self.reserve("second")

    def test_settlement_coverage_prevents_disappearing_or_double_charged_usage(self):
        self.start(); self.now += 1; self.finish(tokens=usage(1000, 500))
        before = self.store.snapshot()["allocations"][0]["budget"]
        self.assertEqual(before["unincorporatedSettledTokens"], 1500)
        self.now += 1; self.observe("a", usage(1200, 600), ["claim"])
        after = self.store.snapshot()["allocations"][0]["budget"]
        self.assertEqual(after["unincorporatedSettledTokens"], 0)
        self.assertEqual(after["observedTokens"], 1800)
        self.assertEqual(after["remainingForNewWork"], 7200)
        self.now += 1
        with self.assertRaisesRegex(Refusal, "backwards"): self.observe("a", usage(1200, 600))
        with self.assertRaisesRegex(Refusal, "backwards"): self.observe("a", usage(1000, 500), ["claim"])

    def test_partial_active_usage_keeps_full_estimate_conservatively(self):
        self.start(); self.now += 1; self.observe("a", usage(100, 100))
        budget = self.store.snapshot()["allocations"][0]["budget"]
        self.assertEqual(budget["heldTokens"], 1600)
        self.assertEqual(budget["remainingForNewWork"], 7200)
        self.now += 1
        with self.assertRaisesRegex(Refusal, "unsettled"): self.observe("a", usage(200, 100), ["claim"])

    def test_foreign_settlements_and_underreported_usage_refused(self):
        self.start(); self.finish(tokens=usage(1000, 500))
        self.allocate("b", "beta")
        self.now += 1
        with self.assertRaisesRegex(Refusal, "foreign"): self.observe("b", usage(2000, 1000), ["claim"])
        with self.assertRaisesRegex(Refusal, "does not cover"): self.observe("a", usage(10, 10), ["claim"])

    def test_allocation_policy_immutability_and_close_preserve_history(self):
        allocation = self.allocate("a", "alpha")
        with self.assertRaisesRegex(Refusal, "reused"):
            self.allocate("a", "alpha", limits={**LIMITS, "maxTasks": 5})
        with self.assertRaisesRegex(Refusal, "already has"): self.allocate("b", "alpha")
        with self.assertRaisesRegex(Refusal, "immutable"):
            AdmissionStore(self.root, policy={**POLICY, "maxParallelTasks": 3})
        self.store.close_allocation("a", EVIDENCE)
        self.assertTrue(self.allocate("a", "alpha")["closed"])
        with self.assertRaisesRegex(Refusal, "closed"): self.reserve()
        self.assertEqual(self.store.snapshot()["allocations"][0]["fingerprint"], allocation["fingerprint"])

    def test_invalid_schema_and_numeric_inputs_do_not_mutate_state(self):
        before = self.store.snapshot()
        for key, value in (("usedPercent", None), ("usedPercent", True), ("usedPercent", float("nan")),
                           ("usedPercent", 101), ("resetsAt", 999)):
            observation = copy.deepcopy(before["meta"]["account"])
            observation["windows"]["short"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(Refusal):
                self.store.observe_account(observation)
        for estimates in ({}, {**ESTIMATE, "workTokens": 0}, {**ESTIMATE, "handoffTokens": True}):
            with self.assertRaises(Refusal):
                self.store.reserve("claim", "a", repositories=["repo"], estimates=estimates)
        with self.assertRaises(Refusal): self.reserve(repo="outside")
        self.assertEqual(self.store.snapshot(), before)

    def test_permissions_and_missing_store_fail_closed(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaisesRegex(Refusal, "not initialized"): AdmissionStore(Path(other).resolve())
            self.assertFalse((Path(other) / "admission.sqlite3").exists())
        os.chmod(self.store.db, 0o644)
        try:
            with self.assertRaises(Refusal): self.store.snapshot()
            with self.assertRaises(Refusal): AdmissionStore(self.root)
        finally:
            os.chmod(self.store.db, 0o600)

    def test_database_replacement_is_not_silent_recovery(self):
        original = self.root / "retained.sqlite3"
        self.store.db.rename(original)
        with sqlite3.connect(self.store.db) as db: db.execute("CREATE TABLE fixture(id)")
        os.chmod(self.store.db, 0o600)
        with self.assertRaisesRegex(Refusal, "identity"): self.store.snapshot()


if __name__ == "__main__":
    unittest.main()
