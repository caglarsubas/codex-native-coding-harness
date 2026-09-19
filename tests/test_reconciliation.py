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

from orchestrator import adoption, reconciliation
from orchestrator.admission import AdmissionStore
from orchestrator.core import Refusal, digest
from orchestrator.reconciliation_evidence import assess, validate
from orchestrator.workspaces import Registry
import test_adoption as fixtures


def hard_exit_record(root, request):
    with patch.object(reconciliation, "public", side_effect=lambda *args: os._exit(74)):
        reconciliation.record(Registry(root), request)


class ReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.AdoptionTest(); self.fx.setUp()
        self.registry = self.fx.registry
        self.fx.enrolled()
        config = self.fx.config()
        for row in config["repositories"]: row["keys"] = ["repo-remote:" + row["bindingHash"]]
        self.adopted = adoption.apply(self.registry, {"id": "fixture-adoption", "confirmed": True,
                                                    "preview": adoption.preview(self.registry, config)})
        self.claims = self.fx.store().snapshot()["legacy"]["claims"]

    def tearDown(self):
        self.fx.tearDown()

    def evidence(self):
        now = time.time()
        proof = {"observedAt": now, "evidenceHash": "a" * 64}
        tasks = [{"hostId": "local", "threadId": "brain-" + wid, "workspaceId": wid, "role": "brain",
                  "parent": None, "state": "idle", "checkpointHash": "b" * 64, **proof} for wid in ("alpha", "beta")]
        reports, pending = [], []
        for claim in self.claims:
            natives = copy.deepcopy(claim["nativeIdentities"])
            if not natives: natives = [{"hostId": "local", "threadId": "resolved-" + claim["workspaceId"]}]
            for row in natives:
                tasks.append({**row, "workspaceId": claim["workspaceId"], "role": "worker", "parent": None,
                              "state": "idle", "checkpointHash": "b" * 64, **proof})
            for version in claim["versions"]:
                if version.get("clientThreadId"):
                    pending.append({"hostId": version["hostId"], "clientThreadId": version["clientThreadId"],
                                    "outcome": "resolved", "threadId": natives[0]["threadId"], **proof})
            reports.append({"claimId": claim["id"], "outcome": "quiescent", "native": natives, **proof})
        keys = sorted({key for c in self.claims for key in c["resourceKeys"]})
        return {"schemaVersion": 1, "adoptionHash": self.adopted["bundleHash"],
                "account": {"identityHash": "c" * 64, **proof,
                            "windows": {k: {"usedPercent": 20, "resetsAt": now + 600} for k in ("short", "long")}},
                "inventory": {"accountIdentityHash": "c" * 64, **proof, "complete": True, "includesDescendants": True,
                              "includesUnmanaged": True, "workspaceIds": ["alpha", "beta"], "hostIds": ["local"],
                              "tasks": tasks, "pending": pending},
                "claims": reports, "resources": [{"key": key, "verified": True, **proof} for key in keys],
                "runners": [{"key": key, "state": "idle", "cleanupObserved": True, **proof} for key in keys if key.startswith("runner:")],
                "usage": {"accountIdentityHash": "c" * 64, **proof, "complete": True,
                          "sessions": [{"hostId": t["hostId"], "threadId": t["threadId"], "counterEpoch": "d" * 64,
                                        "counters": {"inputTokens": 100, "cachedInputTokens": 90, "outputTokens": 20, "reasoningOutputTokens": 10},
                                        "complete": True, **proof} for t in tasks]}}

    def preview(self, evidence=None):
        return reconciliation.preview(self.registry, evidence or self.evidence())

    def save(self, evidence=None, request_id="fixture-review"):
        request = {"id": request_id, "confirmed": True, "preview": self.preview(evidence)}
        return reconciliation.record(self.registry, request)

    def codes(self, evidence):
        return {i["code"] for i in self.preview(evidence)["document"]["report"]["issues"]}

    def test_consistent_preview_is_read_only_and_token_subsets_are_not_double_counted(self):
        before = self.fx.store().snapshot()
        source = [self.fx.fixture.contents(l) for l in (self.fx.alpha, self.fx.beta)]
        preview = self.preview(); report = preview["document"]["report"]
        self.assertTrue(report["evidenceConsistent"], report["issues"])
        self.assertEqual(report["knownCumulativeTokens"]["rawTokens"], 480)
        self.assertEqual(report["knownCumulativeTokens"]["cachedInputTokens"], 360)
        self.assertFalse(report["executionAuthorized"]); self.assertFalse(report["ownershipReleased"])
        self.assertEqual(before, self.fx.store().snapshot())
        self.assertEqual(source, [self.fx.fixture.contents(l) for l in (self.fx.alpha, self.fx.beta)])
        self.assertEqual(reconciliation.status(self.registry)["state"], "not_reviewed")
        self.assertNotIn(str(self.fx.fixture.root), json.dumps(preview))

    def test_review_retains_exact_document_baseline_and_all_fences(self):
        preview = self.preview(); before = self.fx.store().snapshot()
        receipt = reconciliation.record(self.registry, {"id": "review-exact", "confirmed": True, "preview": preview})
        self.assertTrue(receipt["baselineRetained"])
        with self.registry.tx() as db:
            saved = reconciliation.records(db)[0]
        self.assertEqual(saved["reviewDocument"], preview["document"])
        self.assertEqual(saved["reviewHash"], digest(saved["reviewDocument"]))
        self.assertEqual(before, self.fx.store().snapshot())
        self.fx.assert_closed(self.fx.store())
        status = reconciliation.status(self.registry)
        self.assertTrue(status["currentEvaluation"]["evidenceConsistent"])
        self.assertTrue(status["receipt"]["receiptIsHistorical"])

    def test_missing_or_partial_native_inventory_never_means_clear(self):
        for field in ("complete", "includesDescendants", "includesUnmanaged"):
            evidence = self.evidence(); evidence["inventory"][field] = False
            self.assertIn("inventory_coverage_incomplete", self.codes(evidence))
        evidence = self.evidence(); evidence["inventory"]["tasks"] = []
        self.assertIn("brain_inventory_missing_or_ambiguous", self.codes(evidence))
        self.assertIn("native_task_missing", self.codes(evidence))

    def test_stale_future_and_predating_observations_are_explicit(self):
        for offset in (-1000, 1000):
            evidence = self.evidence(); evidence["inventory"]["observedAt"] += offset
            self.assertIn("evidence_not_fresh", self.codes(evidence))
        evidence = self.evidence(); evidence["runners"][0]["observedAt"] = 1
        self.assertIn("evidence_predates_adoption", self.codes(evidence))

    def test_account_unknown_reset_low_and_cross_account_observations_block(self):
        changes = [lambda e: e["account"]["windows"]["short"].update(usedPercent=None),
                   lambda e: e["account"]["windows"]["long"].update(resetsAt=time.time() - 1),
                   lambda e: e["account"]["windows"]["short"].update(usedPercent=99),
                   lambda e: e["usage"].update(accountIdentityHash="e" * 64)]
        for change, expected in zip(changes, ("account_window_unknown", "account_window_reset", "account_headroom_low", "account_identity_mismatch")):
            evidence = self.evidence(); change(evidence)
            self.assertIn(expected, self.codes(evidence))

    def test_pending_client_id_is_not_treated_as_native_identity(self):
        evidence = self.evidence(); evidence["inventory"]["pending"] = []
        self.assertIn("pending_creation_unresolved", self.codes(evidence))
        evidence = self.evidence(); evidence["inventory"]["pending"][0].update(outcome="unknown", threadId=None)
        self.assertIn("pending_creation_unresolved", self.codes(evidence))

    def test_not_created_cannot_discard_known_native_binding(self):
        evidence = self.evidence()
        alpha = next(c for c in self.claims if c["workspaceId"] == "alpha")
        report = next(c for c in evidence["claims"] if c["claimId"] == alpha["id"])
        report.update(outcome="not_created", native=[])
        self.assertIn("not_created_conflicts_with_native", self.codes(evidence))
        self.assertIn("native_binding_omitted", self.codes(evidence))

    def test_explicit_noncreation_can_be_recorded_without_releasing_pending_owner(self):
        evidence = self.evidence()
        beta = next(c for c in self.claims if c["workspaceId"] == "beta")
        report = next(c for c in evidence["claims"] if c["claimId"] == beta["id"])
        report.update(outcome="not_created", native=[])
        evidence["inventory"]["pending"][0].update(outcome="not_created", threadId=None)
        evidence["inventory"]["tasks"] = [t for t in evidence["inventory"]["tasks"] if t["threadId"] != "resolved-beta"]
        evidence["usage"]["sessions"] = [s for s in evidence["usage"]["sessions"] if s["threadId"] != "resolved-beta"]
        self.assertEqual(self.codes(evidence), set())
        self.save(evidence)
        self.assertEqual(self.fx.store().snapshot()["legacy"]["retainedSlots"], 2)

    def test_running_tasks_missing_checkpoints_and_busy_runners_block(self):
        evidence = self.evidence(); evidence["inventory"]["tasks"][0].update(state="running", checkpointHash=None)
        evidence["runners"][0].update(state="busy", cleanupObserved=False)
        self.assertTrue({"task_not_quiescent", "checkpoint_missing", "runner_not_quiescent"} <= self.codes(evidence))

    def test_mapping_and_runner_coverage_are_exact(self):
        evidence = self.evidence(); evidence["resources"] = []; evidence["runners"] = []
        self.assertTrue({"resource_coverage_mismatch", "runner_coverage_mismatch"} <= self.codes(evidence))
        evidence = self.evidence(); evidence["resources"][0]["verified"] = False
        self.assertIn("resource_identity_unverified", self.codes(evidence))

    def test_conflicting_resources_and_unresolved_import_gaps_remain_blocking(self):
        with self.registry.tx() as db:
            with reconciliation.locked_context(self.registry, db) as (context, _):
                modified = copy.deepcopy(context)
        modified["claims"][1]["resourceKeys"].append(modified["claims"][0]["resourceKeys"][0])
        modified["claims"][0]["issues"].extend(["repository_mapping_unknown", "runner_without_worker_record"])
        report = assess(modified, self.evidence(), None, time.time())
        self.assertTrue({"resource_owned_by_multiple_claims", "repository_mapping_unknown", "runner_without_worker_record"}
                        <= {i["code"] for i in report["issues"]})

    def test_one_native_task_cannot_satisfy_two_claims_or_foreign_scope(self):
        evidence = self.evidence()
        evidence["claims"][1]["native"] = copy.deepcopy(evidence["claims"][0]["native"])
        self.assertTrue({"native_owned_by_multiple_claims", "native_task_scope_mismatch"} <= self.codes(evidence))

    def test_current_native_binding_must_be_covered_by_its_own_claim(self):
        evidence = self.evidence()
        with self.fx.alpha.tx() as db:
            worker = self.fx.alpha.all(db, "workers")[0]; worker["threadId"] = "resolved-beta"
            self.fx.alpha.put(db, "workers", worker["id"], worker)
        self.assertIn("current_native_binding_uncovered", self.codes(evidence))

    def test_extra_nested_review_and_unmanaged_tasks_are_not_invisible(self):
        for role in ("nested", "reviewer", "external"):
            evidence = self.evidence(); task = copy.deepcopy(evidence["inventory"]["tasks"][0])
            task.update(threadId="new-task", role=role, parent={"hostId": "local", "threadId": "brain-alpha"})
            evidence["inventory"]["tasks"].append(task)
            codes = self.codes(evidence)
            self.assertIn("unadopted_task", codes); self.assertIn("usage_coverage_incomplete", codes)
            if role == "external": self.assertIn("unmanaged_task", codes)

    def test_parent_cycles_and_cross_workspace_relationships_block(self):
        evidence = self.evidence()
        task = evidence["inventory"]["tasks"][-1]
        task.update(role="nested", parent={"hostId": task["hostId"], "threadId": task["threadId"]})
        self.assertIn("parent_cycle", self.codes(evidence))
        task["parent"] = {"hostId": "local", "threadId": "brain-alpha" if task["workspaceId"] == "beta" else "brain-beta"}
        self.assertIn("parent_scope_mismatch", self.codes(evidence))

    def test_missing_brain_host_and_workspace_coverage_block(self):
        evidence = self.evidence(); evidence["inventory"].update(hostIds=[], workspaceIds=["alpha"])
        evidence["inventory"]["tasks"][0]["role"] = "worker"
        self.assertTrue({"host_coverage_missing", "workspace_coverage_mismatch", "brain_inventory_missing_or_ambiguous"} <= self.codes(evidence))

    def test_usage_missing_partial_null_and_invalid_subsets_are_not_zero(self):
        evidence = self.evidence(); evidence["usage"]["sessions"].pop()
        self.assertIn("usage_coverage_incomplete", self.codes(evidence))
        evidence = self.evidence(); evidence["usage"]["sessions"][0].update(counters=None, complete=False)
        self.assertIn("session_usage_unknown", self.codes(evidence))
        evidence = self.evidence(); evidence["usage"]["sessions"][0]["counters"]["cachedInputTokens"] = 200
        with self.assertRaises(Refusal): self.preview(evidence)

    def test_baseline_account_epoch_counters_and_session_coverage_cannot_reset(self):
        self.save()
        evidence = self.evidence()
        for part in ("inventory", "usage"): evidence[part]["accountIdentityHash"] = "e" * 64
        evidence["account"]["identityHash"] = "e" * 64
        self.assertIn("account_changed_since_baseline", self.codes(evidence))
        evidence = self.evidence(); evidence["usage"]["sessions"][0]["counterEpoch"] = "f" * 64
        self.assertIn("counter_epoch_changed", self.codes(evidence))
        evidence = self.evidence(); evidence["usage"]["sessions"][0]["counters"].update(inputTokens=99)
        self.assertIn("usage_counter_moved_backwards", self.codes(evidence))
        evidence = self.evidence(); evidence["usage"]["sessions"].pop()
        self.assertIn("baseline_session_dropped", self.codes(evidence))

    def test_invalid_reviews_do_not_replace_or_launder_consistent_baseline(self):
        first = self.save()
        evidence = self.evidence(); evidence["usage"]["sessions"][0]["counters"]["inputTokens"] = 99
        for index in range(21): self.save(evidence, request_id="invalid-review-" + str(index))
        status = reconciliation.status(self.registry)
        self.assertEqual(status["version"], 22); self.assertEqual(status["olderVersions"], 2)
        self.assertEqual(status["baselineRecordHash"], first["recordHash"])
        self.assertIn("usage_counter_moved_backwards", self.codes(evidence))

    def test_monotonic_baseline_update_keeps_usage_and_history(self):
        first = self.save(); evidence = self.evidence()
        for s in evidence["usage"]["sessions"]: s["counters"]["inputTokens"] += 10
        second = self.save(evidence, request_id="second-review")
        self.assertTrue(second["baselineRetained"])
        status = reconciliation.status(self.registry)
        self.assertEqual(status["baselineRecordHash"], second["recordHash"])
        self.assertEqual(status["history"][0]["recordHash"], first["recordHash"])
        self.assertEqual(status["reviewedReport"]["knownCumulativeTokens"]["rawTokens"], 520)

    def test_old_receipt_is_not_fresh_activity_or_activation(self):
        self.save()
        with patch.object(reconciliation.time, "time", return_value=time.time() + 1000):
            status = reconciliation.status(self.registry)
        self.assertEqual(status["reviewedReport"]["status"], "consistent")
        self.assertEqual(status["currentEvaluation"]["status"], "needs_evidence")
        self.assertFalse(status["activationAvailable"])

    def test_stale_preview_tampering_and_missing_confirmation_refuse(self):
        original = {"id": "fixture-record", "confirmed": True, "preview": self.preview()}
        for edit in (lambda r: r.update(confirmed=False), lambda r: r.update(extra=True),
                     lambda r: r["preview"].update(documentHash="f" * 64)):
            request = copy.deepcopy(original); edit(request)
            with self.assertRaises(Refusal): reconciliation.record(self.registry, request)
        for edit in (lambda d: d.update(effect="Enable Play"), lambda d: d["report"].update(activationAvailable=True)):
            request = copy.deepcopy(original); edit(request["preview"]["document"])
            request["preview"]["documentHash"] = digest(request["preview"]["document"])
            with self.assertRaises(Refusal): reconciliation.record(self.registry, request)
        with patch.object(reconciliation.time, "time", return_value=time.time() + 301), self.assertRaisesRegex(Refusal, "Fresh"):
            reconciliation.record(self.registry, original)

    def test_observation_expiring_between_preview_and_review_refuses_changed_conclusions(self):
        request = {"id": "freshness-race", "confirmed": True, "preview": self.preview()}
        with patch.object(reconciliation.time, "time", return_value=time.time() + 61), self.assertRaisesRegex(Refusal, "freshness changed"):
            reconciliation.record(self.registry, request)
        self.assertEqual(reconciliation.status(self.registry)["state"], "not_reviewed")

    def test_source_drift_refuses_old_review_and_invalidates_current_projection(self):
        self.save(); request = {"id": "stale-source", "confirmed": True, "preview": self.preview()}
        self.fx.fixture.command(self.fx.alpha, "pause")
        with self.assertRaisesRegex(Refusal, "kernel changed"): reconciliation.record(self.registry, request)
        status = reconciliation.status(self.registry)
        self.assertFalse(status["sourceMatchesReview"])
        self.assertIn("source_changed_since_review", {i["code"] for i in status["currentEvaluation"]["issues"]})

    def test_new_ledger_owner_and_changed_binding_are_reported(self):
        evidence = self.evidence()
        with self.fx.alpha.tx() as db:
            worker = self.fx.alpha.all(db, "workers")[0]
            db.execute("INSERT INTO workers(id,queue_id,data) VALUES(?,?,?)", ("extra-worker", "extra-queue",
                       json.dumps({**worker, "id": "extra-worker"})))
            repo = self.fx.alpha.all(db, "repos")[0]; repo["ref"] = "other-ref"
            self.fx.alpha.put(db, "repos", repo["id"], repo)
        self.assertTrue({"new_ledger_owner", "repository_binding_changed"} <= self.codes(evidence))

    def test_duplicate_foreign_and_arbitrary_fields_are_not_accepted(self):
        for edit in (lambda e: e["inventory"]["tasks"].append(e["inventory"]["tasks"][0]),
                     lambda e: e["usage"]["sessions"].append(e["usage"]["sessions"][0]),
                     lambda e: e.update(command="run something"),
                     lambda e: e["account"].update(apiKey="fixture-not-a-secret"),
                     lambda e: e["inventory"].update(complete="yes"),
                     lambda e: e["account"].update(observedAt=float("nan"))):
            evidence = self.evidence(); edit(evidence)
            with self.assertRaises(ValueError): validate(evidence)

    def test_changed_pending_creation_cannot_hide_behind_imported_worker(self):
        evidence = self.evidence()
        with self.fx.beta.tx() as db:
            worker = self.fx.beta.all(db, "workers")[0]
            worker["clientThreadId"] = "new-pending-attempt"
            self.fx.beta.put(db, "workers", worker["id"], worker)
        self.assertIn("current_pending_binding_unadopted", self.codes(evidence))

    def test_exact_retry_and_concurrent_review_record_once(self):
        request = {"id": "one-review", "confirmed": True, "preview": self.preview()}
        results, errors = [], []
        def save():
            try: results.append(reconciliation.record(Registry(self.registry.root), request))
            except Exception as error: errors.append(str(error))
        threads = [threading.Thread(target=save) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(12)
        self.assertFalse(any(t.is_alive() for t in threads)); self.assertEqual(errors, [])
        self.assertEqual(results[0], results[1]); self.assertEqual(reconciliation.status(self.registry)["version"], 1)
        with self.assertRaises(Refusal): reconciliation.record(self.registry, {**request, "preview": self.preview()})

    def test_competing_reviews_require_new_version(self):
        preview = self.preview(); self.save()
        with self.assertRaisesRegex(Refusal, "history changed"):
            reconciliation.record(self.registry, {"id": "different", "confirmed": True, "preview": preview})

    def test_hard_exit_after_commit_replays_only_historical_receipt(self):
        request = {"id": "crash-receipt", "confirmed": True, "preview": self.preview()}
        process = multiprocessing.get_context("spawn").Process(target=hard_exit_record, args=(str(self.registry.root), request))
        process.start(); process.join(12)
        self.assertEqual(process.exitcode, 74)
        receipt = reconciliation.record(Registry(self.registry.root), request)
        self.assertEqual(receipt["version"], 1); self.assertTrue(receipt["receiptIsHistorical"])
        self.fx.assert_closed(self.fx.store())

    def test_transaction_failure_does_not_leave_partial_review(self):
        self.save()
        with self.registry.tx() as db:
            db.execute("CREATE TRIGGER fixture_fail BEFORE INSERT ON admission_reconciliations BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.save(request_id="rollback-review")
        self.assertEqual(reconciliation.status(self.registry)["version"], 1)

    def test_missing_fences_or_changed_kernel_make_status_unavailable_not_ready(self):
        self.save()
        (self.registry.root / "adoption-kernel.json").unlink()
        status = reconciliation.status(self.registry)
        self.assertEqual(status["currentEvaluation"]["status"], "source_unavailable")
        self.assertFalse(status["currentEvaluation"]["evidenceConsistent"])

    def test_corrupt_history_is_detected_without_repair_or_baseline_reset(self):
        self.save()
        with self.registry.tx() as db:
            value = reconciliation.records(db)[0]
            value["report"]["baselineCandidate"] = False
            db.execute("UPDATE admission_reconciliations SET data=?", (json.dumps(value),))
        with self.assertRaisesRegex(Refusal, "history hash mismatch"): reconciliation.status(self.registry)
        with self.assertRaisesRegex(Refusal, "history hash mismatch"): self.preview()
        self.fx.assert_closed(self.fx.store())

    def test_issue_order_is_stable_across_cli_process_hash_seeds(self):
        evidence = self.evidence()
        evidence["inventory"]["tasks"] = []
        evidence["claims"] = []
        path = self.fx.fixture.root / "incomplete.json"; path.write_text(json.dumps(evidence))
        base = [sys.executable, "-m", "orchestrator.cli", "--platform", str(self.registry.root)]
        env = {**os.environ, "PYTHONHASHSEED": "1"}
        first = subprocess.run([*base, "platform-reconciliation-preview", str(path)], env=env, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        preview = self.fx.fixture.root / "incomplete-review.json"; preview.write_text(first.stdout)
        env["PYTHONHASHSEED"] = "3"
        result = subprocess.run([*base, "platform-reconciliation-record", str(preview), "--id", "different-process",
                                 "--confirm"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["baselineRetained"])

    def test_cli_preview_confirmation_scope_and_status(self):
        path = self.fx.fixture.root / "evidence.json"; path.write_text(json.dumps(self.evidence()))
        base = [sys.executable, "-m", "orchestrator.cli", "--platform", str(self.registry.root)]
        result = subprocess.run([*base, "platform-reconciliation-preview", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        preview = self.fx.fixture.root / "preview.json"; preview.write_text(result.stdout)
        args = [*base, "platform-reconciliation-record", str(preview), "--id", "cli-review"]
        result = subprocess.run(args, capture_output=True, text=True); self.assertEqual(result.returncode, 2)
        result = subprocess.run([*args, "--confirm"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([*base, "platform-reconciliation-status"], capture_output=True, text=True)
        self.assertTrue(json.loads(result.stdout)["currentEvaluation"]["evidenceConsistent"])
        result = subprocess.run([*base, "--workspace", "alpha", "platform-reconciliation-status"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__": unittest.main()
