import copy
import json
import multiprocessing
import os
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from orchestrator import adoption, admission_legacy, enrollment
from orchestrator.admission import AdmissionStore
from orchestrator.core import Refusal, digest
from orchestrator.workspaces import Registry
import test_enrollment as fixtures
import test_admission as kernel_fixtures

POLICY = {"maxParallelTasks": 2, "maxObservationAgeSeconds": 60, "minAccountRemainingPercent": 10}
REPO = "repo-remote:" + "a" * 64
RUNNER = "runner:" + "b" * 64


def crash_import(root, request, boundary):
    if boundary == "after_commit":
        with patch.object(adoption, "complete", side_effect=lambda *args: os._exit(76)):
            adoption.apply(Registry(root), request)
    else:
        original = admission_legacy.install
        def crash(*args):
            original(*args)
            os._exit(75)
        with patch.object(admission_legacy, "install", side_effect=crash):
            adoption.apply(Registry(root), request)


class AdoptionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.EnrollmentTest()
        self.fixture.setUp()
        self.registry = self.fixture.registry
        self.alpha, self.beta = self.fixture.alpha, self.fixture.beta

    def tearDown(self):
        self.fixture.tearDown()

    def enrolled(self, *, workers=True):
        if workers:
            self.fixture.worker(self.alpha, "accepting")
            self.fixture.worker(self.beta, "starting")
        return self.fixture.enroll()

    def config(self, *, mapped=True):
        result = {"policy": dict(POLICY), "repositories": [], "runners": []}
        if mapped:
            owners = enrollment.status(self.registry)["retainedOwnership"]
            hashes = {o["repositoryBindingHash"] for o in owners if o["kind"] == "worker"}
            result["repositories"] = [{"bindingHash": h, "keys": [REPO], "evidenceHash": "c" * 64} for h in sorted(hashes)]
            result["runners"] = [{"recordHash": o["recordHash"], "key": RUNNER, "evidenceHash": "d" * 64}
                                 for o in owners if o["kind"] == "runner"]
        return result

    def request(self, **kwargs):
        return {"id": "fixture-adoption", "confirmed": True,
                "preview": adoption.preview(self.registry, self.config(**kwargs))}

    def store(self):
        return AdmissionStore(self.registry.root)

    def assert_closed(self, store):
        with self.assertRaisesRegex(Refusal, "quarantined"):
            store.open_allocation("attempt", workspace_id="alpha", binding_hash="a" * 64,
                                  limits=kernel_fixtures.LIMITS, repositories={"a": [REPO]})
        self.assertTrue(store.snapshot()["legacy"]["dispatchBlocked"])
        self.assertFalse(store.snapshot()["executionAuthorized"])

    def test_preview_requires_completed_enrollment_and_changes_nothing(self):
        config = {"policy": POLICY, "repositories": [], "runners": []}
        with self.assertRaisesRegex(Refusal, "enrollment"): adoption.preview(self.registry, config)
        self.enrolled()
        before = [self.fixture.contents(l) for l in (self.alpha, self.beta)]
        result = self.request()
        self.assertEqual(before, [self.fixture.contents(l) for l in (self.alpha, self.beta)])
        self.assertEqual(adoption.status(self.registry)["state"], "not_adopted")
        self.assertFalse((self.registry.root / "admission.sqlite3").exists())
        self.assertFalse((self.registry.root / admission_legacy.FENCE_FILE).exists())
        self.assertNotIn(str(self.fixture.root), json.dumps(result))
        self.assertNotIn("/fixture/", json.dumps(result))

    def test_import_retains_owners_runner_pending_ids_conflicts_and_no_allocations(self):
        self.enrolled()
        before = [self.fixture.contents(l) for l in (self.alpha, self.beta)]
        receipt = adoption.apply(self.registry, self.request())
        state = self.store().snapshot()
        self.assertEqual(receipt["state"], "quarantined")
        self.assertEqual(receipt["retainedSlots"], 2)
        self.assertEqual(receipt["claimVersionCount"], 3)
        self.assertFalse(receipt["usageKnown"])
        self.assertEqual(state["allocations"], [])
        self.assertEqual(state["claims"], [])
        self.assertEqual(len(state["legacy"]["resourceConflicts"]), 1)
        self.assertIn(RUNNER, {r["key"] for r in state["legacy"]["resources"]})
        pending = next(c for c in state["legacy"]["claims"] if c["workspaceId"] == "beta")
        self.assertEqual(pending["pendingClientIds"], ["fixture-pending"])
        self.assertEqual(pending["nativeIdentities"], [])
        self.assertIn("native_identity_unresolved", pending["issues"])
        self.assert_closed(self.store())
        self.assertEqual(before, [self.fixture.contents(l) for l in (self.alpha, self.beta)])

    def test_unknown_mappings_are_preserved_not_invented_or_dropped(self):
        self.enrolled()
        adoption.apply(self.registry, self.request(mapped=False))
        legacy = self.store().snapshot()["legacy"]
        self.assertEqual(legacy["retainedSlots"], 2)
        self.assertEqual(legacy["resources"], [])
        self.assertGreater(legacy["issues"], 0)
        self.assert_closed(self.store())

    def test_empty_recorded_inventory_never_means_free_capacity(self):
        self.enrolled(workers=False)
        adoption.apply(self.registry, self.request())
        self.assertEqual(self.store().snapshot()["legacy"]["retainedSlots"], 0)
        self.assert_closed(self.store())

    def test_version_changes_are_grouped_without_discarding_old_native_ids(self):
        self.enrolled()
        with self.alpha.tx() as db:
            worker = self.alpha.all(db, "workers")[0]
            worker.update(status="blocked", threadId="different-native-task")
            self.alpha.put(db, "workers", worker["id"], worker)
        enrollment.recover(self.registry, "fixture-enrollment", confirmed=True)
        adoption.apply(self.registry, self.request())
        claim = next(c for c in self.store().snapshot()["legacy"]["claims"] if c["workspaceId"] == "alpha")
        self.assertEqual(len(claim["nativeIdentities"]), 2)
        self.assertIn("conflicting_native_bindings", claim["issues"])
        self.assertEqual(self.store().snapshot()["legacy"]["retainedSlots"], 2)

    def test_missing_completed_and_runner_only_owners_remain_held(self):
        self.enrolled()
        with self.alpha.tx() as db:
            db.execute("DELETE FROM workers")
            meta = self.alpha.get(db, "meta", 1)
            meta["runner"] = {"workerId": "missing-worker", "since": time.time()}
            self.alpha.put(db, "meta", 1, meta)
        with self.beta.tx() as db:
            worker = self.beta.all(db, "workers")[0]; worker["status"] = "complete"
            self.beta.put(db, "workers", worker["id"], worker)
        enrollment.recover(self.registry, "fixture-enrollment", confirmed=True)
        adoption.apply(self.registry, self.request(mapped=False))
        legacy = self.store().snapshot()["legacy"]
        self.assertEqual(legacy["retainedSlots"], 3)
        self.assertIn("runner_without_worker_record", next(c for c in legacy["claims"] if c["workerId"] == "missing-worker")["issues"])

    def test_duplicate_native_identity_across_workspaces_is_reported_not_deduplicated(self):
        self.enrolled()
        for ledger in (self.alpha, self.beta):
            with ledger.tx() as db:
                worker = ledger.all(db, "workers")[0]
                worker.update(threadId="shared-native", hostId="local")
                ledger.put(db, "workers", worker["id"], worker)
        adoption.apply(self.registry, self.request())
        legacy = self.store().snapshot()["legacy"]
        self.assertEqual(legacy["retainedSlots"], 2)
        self.assertEqual(len(legacy["nativeConflicts"]), 1)

    def test_confirmation_shape_hash_and_effect_cannot_be_changed(self):
        self.enrolled(); original = self.request()
        for edit in (lambda r: r.update(confirmed=False), lambda r: r.update(extra=True),
                     lambda r: r["preview"].update(documentHash="a" * 64)):
            candidate = copy.deepcopy(original); edit(candidate)
            with self.assertRaises(Refusal): adoption.apply(self.registry, candidate)
        for edit in (lambda d: d.update(effect="Start work"), lambda d: d.update(claims=[]),
                     lambda d: d.update(observedAt=True), lambda d: d.update(sourceHash="a" * 64)):
            candidate = copy.deepcopy(original); edit(candidate["preview"]["document"])
            candidate["preview"]["documentHash"] = digest(candidate["preview"]["document"])
            with self.assertRaises(Refusal): adoption.apply(self.registry, candidate)
        self.assertEqual(adoption.status(self.registry)["state"], "not_adopted")

    def test_expired_future_and_changed_ownership_refuse_before_intent(self):
        self.enrolled(); request = self.request()
        for offset in (1000, -1000):
            candidate = copy.deepcopy(request)
            doc = candidate["preview"]["document"]
            doc.update(observedAt=time.time() + offset); doc["expiresAt"] = doc["observedAt"] + 300
            candidate["preview"]["documentHash"] = digest(doc)
            with self.assertRaisesRegex(Refusal, "Fresh"): adoption.apply(self.registry, candidate)
        self.fixture.command(self.beta, "pause")
        with self.assertRaisesRegex(Refusal, "Ownership changed"): adoption.apply(self.registry, request)
        self.assertFalse((self.registry.root / "admission.sqlite3").exists())

    def test_mapping_validation_rejects_unknown_duplicate_and_noncanonical(self):
        self.enrolled()
        for edit in (lambda c: c["repositories"].append(c["repositories"][0]),
                     lambda c: c["repositories"][0].update(keys=["/private/path"]),
                     lambda c: c["repositories"][0].update(bindingHash="0" * 64),
                     lambda c: c["runners"][0].update(key=REPO),
                     lambda c: c["policy"].update(maxParallelTasks=True)):
            config = self.config(); edit(config)
            with self.assertRaises(Refusal): adoption.preview(self.registry, config)

    def test_controllers_and_missing_enrollment_fences_block_import(self):
        self.enrolled(); request = self.request()
        token = self.alpha.acquire("brain-alpha:fixture")
        with self.assertRaisesRegex(Refusal, "release controllers"): adoption.apply(self.registry, request)
        self.alpha.release(token, "Fixture idle")
        (self.beta.root / enrollment.FENCE_FILE).unlink()
        with self.assertRaises(OSError): adoption.preview(self.registry, self.config())
        self.assertEqual(adoption.status(self.registry)["state"], "not_adopted")

    def test_matching_empty_existing_kernel_is_adopted_but_populated_or_changed_refuses(self):
        self.enrolled()
        existing = AdmissionStore(self.registry.root, policy=POLICY)
        request = self.request()
        existing.open_allocation("before", workspace_id="alpha", binding_hash="a" * 64,
                                 limits=kernel_fixtures.LIMITS, repositories={"a": [REPO]})
        with self.assertRaisesRegex(Refusal, "store changed"): adoption.apply(self.registry, request)
        with self.assertRaisesRegex(Refusal, "Kernel must be empty"): self.request()
        self.assertEqual(adoption.status(self.registry)["state"], "not_adopted")

    def test_cached_kernel_object_and_both_independent_fences_remain_closed(self):
        self.enrolled()
        cached = AdmissionStore(self.registry.root, policy=POLICY)
        adoption.apply(self.registry, self.request())
        self.assert_closed(cached)
        (self.registry.root / admission_legacy.FENCE_FILE).unlink()
        (self.registry.root / "adoption-kernel.json").unlink()
        self.assert_closed(cached)

    def test_sidecar_blocks_kernel_paths_even_without_metadata_marker(self):
        root = self.registry.root
        store = AdmissionStore(root, policy=POLICY)
        store.open_allocation("a", workspace_id="alpha", binding_hash="a" * 64,
                              limits=kernel_fixtures.LIMITS, repositories={"a": [REPO]}, runners=[RUNNER])
        now = time.time()
        store.observe_account({"observedAt": now, "evidenceHash": "c" * 64,
            "windows": {k: {"usedPercent": 1, "resetsAt": now + 1000} for k in ("short", "long")}})
        store.observe_usage("a", {"observedAt": time.time(), "evidenceHash": "c" * 64,
            "counters": kernel_fixtures.usage(), "coverage": ["brain", "workers", "reviews"], "settledClaimIds": []})
        store.reserve("claim", "a", repositories=["a"], estimates=kernel_fixtures.ESTIMATE)
        path = root / admission_legacy.FENCE_FILE
        path.write_text("malformed file is still a fence")
        self.assert_closed(store)
        with self.assertRaisesRegex(Refusal, "quarantined"): store.begin("claim")
        with self.assertRaisesRegex(Refusal, "quarantined"):
            store.reserve("other", "a", repositories=["a"], estimates=kernel_fixtures.ESTIMATE)
        path.unlink(); store.begin("claim"); store.bind("claim", host_id="local", thread_id="native")
        store.runner("claim", RUNNER, "acquire", evidence_hash="c" * 64, observed_at=time.time())
        path.symlink_to(root / "missing")
        with self.assertRaisesRegex(Refusal, "quarantined"):
            store.runner("claim", RUNNER, "acquire", evidence_hash="c" * 64, observed_at=time.time())
        store.runner("claim", RUNNER, "release", evidence_hash="d" * 64, observed_at=time.time())
        store.settle("claim", actual=kernel_fixtures.usage(), evidence_hash="d" * 64, observed_at=time.time(), outcome="terminal")
        self.assertTrue(store.snapshot()["legacy"]["dispatchBlocked"])

    def test_duplicate_confirmation_is_receipt_only_and_recovery_is_idempotent(self):
        self.enrolled(); request = self.request()
        first = adoption.apply(self.registry, request)
        before = self.store().snapshot()
        self.assertEqual(adoption.apply(self.registry, request), first)
        self.assertEqual(adoption.recover(self.registry, request["id"], confirmed=True), first)
        self.assertEqual(self.store().snapshot(), before)
        self.assertEqual(adoption.status(self.registry)["historyEntries"], 2)
        with self.assertRaises(Refusal): adoption.apply(self.registry, {**request, "id": "different"})

    def test_interruption_before_kernel_retains_intent_and_durable_fence(self):
        self.enrolled(); request = self.request()
        with patch.object(adoption, "pin_kernel", side_effect=RuntimeError("fixture")), self.assertRaises(RuntimeError):
            adoption.apply(self.registry, request)
        self.assertEqual(adoption.status(self.registry)["state"], "prepared")
        self.assertTrue((self.registry.root / admission_legacy.FENCE_FILE).exists())
        self.assertEqual(adoption.apply(self.registry, request)["state"], "prepared")
        with self.assertRaises(Refusal): adoption.recover(self.registry, request["id"])
        self.assertEqual(adoption.recover(self.registry, request["id"], confirmed=True)["state"], "quarantined")

    def test_kernel_transaction_failure_rolls_back_import_but_retains_pinned_identity(self):
        self.enrolled(); request = self.request()
        with patch.object(AdmissionStore, "event", side_effect=RuntimeError("fixture transaction failure")), self.assertRaises(RuntimeError):
            adoption.apply(self.registry, request)
        self.assertEqual(adoption.kernel_state(self.registry)["contentHash"], digest({}))
        pinned = json.loads((self.registry.root / "adoption-kernel.json").read_text())["kernelIdentity"]
        receipt = adoption.recover(self.registry, request["id"], confirmed=True)
        self.assertEqual(receipt["kernelIdentity"], pinned)

    def test_hard_process_exit_inside_kernel_transaction_recovers_without_losing_owners(self):
        self.crash_and_recover("inside_transaction", 75)

    def test_hard_process_exit_after_kernel_commit_recovers_exact_receipt(self):
        self.crash_and_recover("after_commit", 76)

    def crash_and_recover(self, boundary, code):
        self.enrolled(); request = self.request()
        ctx = multiprocessing.get_context("spawn")
        process = ctx.Process(target=crash_import, args=(str(self.registry.root), request, boundary))
        process.start(); process.join(12)
        self.assertEqual(process.exitcode, code)
        self.assertEqual(adoption.status(self.registry)["state"], "prepared")
        recovered = adoption.recover(Registry(self.registry.root), request["id"], confirmed=True)
        self.assertEqual(recovered["retainedSlots"], 2)
        self.assert_closed(self.store())

    def test_recovery_refuses_ownership_drift_without_releasing_imported_claims(self):
        self.enrolled(); request = self.request()
        adoption.apply(self.registry, request)
        self.fixture.command(self.alpha, "pause")
        with self.assertRaisesRegex(Refusal, "ownership changed"):
            adoption.recover(self.registry, request["id"], confirmed=True)
        self.assertEqual(self.store().snapshot()["legacy"]["retainedSlots"], 2)

    def test_recovery_refuses_replaced_kernel(self):
        self.enrolled(); request = self.request()
        with patch.object(adoption, "complete", side_effect=RuntimeError("fixture")), self.assertRaises(RuntimeError):
            adoption.apply(self.registry, request)
        path = self.registry.root / "admission.sqlite3"
        moved = self.registry.root / "retained.sqlite3"
        path.rename(moved)
        replacement = sqlite3.connect(path); replacement.close(); path.chmod(0o600)
        with self.assertRaisesRegex(Refusal, "Pinned kernel identity changed"):
            adoption.recover(self.registry, request["id"], confirmed=True)
        self.assertTrue(moved.exists())

    def test_conflicting_fence_is_retained_and_never_overwritten(self):
        self.enrolled(); request = self.request()
        with patch.object(adoption, "pin_kernel", side_effect=RuntimeError("fixture")), self.assertRaises(RuntimeError):
            adoption.apply(self.registry, request)
        path = self.registry.root / admission_legacy.FENCE_FILE
        path.write_text("foreign fence")
        with self.assertRaisesRegex(Refusal, "fence identity changed"):
            adoption.recover(self.registry, request["id"], confirmed=True)
        self.assertEqual(path.read_text(), "foreign fence")
        self.assertEqual(adoption.status(self.registry)["state"], "prepared")

    def test_empty_file_left_before_identity_pin_recovers_without_replacement(self):
        self.enrolled(); request = self.request()
        original = enrollment.durable_fence
        def interrupt(root, binding, **kwargs):
            if kwargs.get("filename") == "adoption-kernel.json": raise RuntimeError("fixture before pin")
            return original(root, binding, **kwargs)
        with patch.object(enrollment, "durable_fence", side_effect=interrupt), self.assertRaises(RuntimeError):
            adoption.apply(self.registry, request)
        identity = adoption.kernel_state(self.registry)["identity"]
        self.assertFalse((self.registry.root / "adoption-kernel.json").exists())
        self.assertEqual(adoption.recover(self.registry, request["id"], confirmed=True)["kernelIdentity"], identity)

    def test_incompatible_existing_policy_refuses_before_journal_or_platform_fence(self):
        self.enrolled()
        AdmissionStore(self.registry.root, policy={**POLICY, "maxParallelTasks": 1})
        with self.assertRaisesRegex(Refusal, "exact policy"): self.request()
        self.assertEqual(adoption.status(self.registry)["state"], "not_adopted")
        self.assertFalse((self.registry.root / admission_legacy.FENCE_FILE).exists())

    def test_recovery_refuses_missing_imported_rows_without_releasing_fences(self):
        self.enrolled(); request = self.request()
        adoption.apply(self.registry, request)
        with self.store().tx() as db: db.execute("DELETE FROM legacy_claims")
        with self.assertRaisesRegex(Refusal, "ownership changed"):
            adoption.recover(self.registry, request["id"], confirmed=True)
        self.assert_closed(self.store())

    def test_registry_permissions_and_brain_identity_are_rechecked(self):
        self.enrolled(); request = self.request()
        self.registry.db.chmod(0o644)
        try:
            with self.assertRaisesRegex(Refusal, "private regular"): adoption.apply(self.registry, request)
        finally: self.registry.db.chmod(0o600)
        with self.beta.tx() as db:
            meta = self.beta.get(db, "meta", 1); meta["brainId"] = "new-brain"
            self.beta.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "identity changed"): adoption.apply(self.registry, request)
        self.assertEqual(adoption.status(self.registry)["state"], "not_adopted")

    def test_concurrent_recovery_has_one_kernel_import_and_receipt(self):
        self.enrolled(); request = self.request()
        with patch.object(adoption, "pin_kernel", side_effect=RuntimeError("fixture")), self.assertRaises(RuntimeError):
            adoption.apply(self.registry, request)
        errors = []; results = []
        def recover():
            try: results.append(adoption.recover(Registry(self.registry.root), request["id"], confirmed=True))
            except Exception as error: errors.append(str(error))
        threads = [threading.Thread(target=recover) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(12)
        self.assertFalse(any(t.is_alive() for t in threads)); self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(self.store().snapshot()["eventCount"], 1)
        self.assertEqual(adoption.status(self.registry)["historyEntries"], 2)

    def test_kernel_legacy_import_requires_exact_fences_and_identity(self):
        self.enrolled(); request = self.request()
        with patch.object(adoption, "pin_kernel", side_effect=RuntimeError("fixture")), self.assertRaises(RuntimeError):
            adoption.apply(self.registry, request)
        with self.registry.tx() as db: bundle = adoption.record_in(db)["bundle"]
        with self.assertRaisesRegex(Refusal, "Pinned database"):
            AdmissionStore(self.registry.root, policy=POLICY, legacy_bundle=bundle)
        self.assertFalse((self.registry.root / "admission.sqlite3").exists())

    def test_concurrent_confirmation_retains_one_import_and_does_not_deadlock(self):
        self.enrolled(); request = self.request(); results = []; errors = []
        def confirm():
            try: results.append(adoption.apply(Registry(self.registry.root), request))
            except Exception as error: errors.append(str(error))
        threads = [threading.Thread(target=confirm) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(12)
        self.assertFalse(any(t.is_alive() for t in threads)); self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(adoption.status(self.registry)["state"], "quarantined")
        self.assertEqual(self.store().snapshot()["eventCount"], 1)

    def test_cli_scope_confirmation_and_historical_status(self):
        self.enrolled()
        config = self.fixture.root / "config.json"; config.write_text(json.dumps(self.config()))
        base = [sys.executable, "-m", "orchestrator.cli", "--platform", str(self.registry.root)]
        result = subprocess.run([*base, "platform-adoption-preview", str(config)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        preview = self.fixture.root / "preview.json"; preview.write_text(result.stdout)
        args = [*base, "platform-adopt", str(preview), "--id", "fixture-cli"]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        result = subprocess.run([*args, "--confirm"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([*base, "platform-adoption-status"], capture_output=True, text=True)
        status = json.loads(result.stdout)
        self.assertTrue(status["receiptIsHistorical"]); self.assertTrue(status["kernelIdentityMatches"])
        self.assertEqual(status["reviewedInventory"]["retainedSlots"], 2)
        self.assertEqual(len(status["reviewedInventory"]["resourceConflicts"]), 1)
        result = subprocess.run([*base, "--workspace", "alpha", "platform-adoption-status"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
