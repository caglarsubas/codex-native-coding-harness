import copy
import json
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import result_review, run_authority as runs, workspace_pause
from orchestrator.core import AXES, Refusal, canonical, digest
from orchestrator.observations import capture
from orchestrator.assistant_actions import catalog
from test_dispatch_admission import ESTIMATES, KEY
import test_ownership_settlement
import test_creation_recovery


class ResultReviewTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_ownership_settlement.OwnershipSettlementTest(); self.fx.setUp()
        self.ledger, self.token, self.store, self.wid = self.fx.ledger, self.fx.token, self.fx.store, self.fx.wid
        self.api = result_review.ResultReview(self.fx.bridge)
        if getattr(self, "pending_client", None): self.fx.fx.observe(clientThreadId=self.pending_client)
        self.fx.settle(self.fx.evidence(getattr(self, "descendants", ())))
        self.intent = self.ledger.document(self.fx.worker()["dispatchAdmission"]["intentHash"])
        self.seq = 0

    def tearDown(self): self.fx.tearDown()
    def worker(self): return self.fx.worker()
    def logical(self): return self.fx.fx.fx.fx.fx.logical()

    def artifact(self, subject, raw=b"Independently obtained fixture evidence; no live assertion.", commit="f"*40):
        self.seq += 1
        with self.ledger.tx() as db:
            return capture(db, "result-fixture-"+str(self.seq), raw,
                {"repository": "a", "name": subject+".json", "orderAt": time.time(), "references": [{
                    "workerId": self.wid, "intentHash": digest(self.intent), "commit": commit,
                    "subject": subject, "session": "brain-a", "at": time.time()}]})

    def proof(self, subject, status="verified"):
        artifact = self.artifact(subject) if status != "unverified" else None
        return {"status": status, "artifactId": artifact["id"] if artifact else None, "observedAt": time.time()}

    def evidence(self, outcome="accepted", **result_changes):
        seed = self.ledger.document(self.intent["seedHash"])
        result = {"seedHash": self.intent["seedHash"], "baseSHA": seed["baseSHA"], "commit": "f"*40,
            "branch": seed["branch"], "changedPaths": ["src/example.py"], "diffComplete": True,
            "pr": {"url": "https://github.com/example/repo/pull/1", "headSHA": "f"*40,
                   "baseSHA": seed["baseSHA"], "state": "open", "mergeCommit": None},
            "ci": {"headSHA": "f"*40, "complete": True, "requiredChecks": ["tests"],
                   "checks": [{"name": "tests", "headSHA": "f"*40, "status": "passed"}]},
            "evidence": {axis: self.proof(axis, "verified" if axis in seed["completionAxes"] else "unverified") for axis in AXES},
            "criteria": [{"index": i, "criterionHash": digest(c), "proof": self.proof("criterion:"+str(i))}
                         for i, c in enumerate(seed["acceptance"])],
            "preservation": self.proof("preservation"), "observedAt": time.time()}
        result.update(result_changes)
        return self.request(result, outcome)

    def request(self, result, outcome="accepted", reviewer=None, **report_changes):
        report = {"kind": "independent_result_review", "workerId": self.wid, "intentHash": digest(self.intent),
            "settlementHash": self.worker()["ownershipSettlementHash"], "resultHash": digest(result), "outcome": outcome,
            "reviewer": reviewer or {"hostId": "local", "threadId": "brain-a"}, "observedAt": time.time(),
            "summary": "Independently checked exact fixture result. No live acceptance."}
        report.update(report_changes)
        artifact = self.artifact("independent_review", canonical(report).encode())
        return {"id": "review-"+str(self.seq), "expectedRevision": self.ledger.snapshot()["meta"]["revision"],
                "settlementHash": self.worker()["ownershipSettlementHash"], "outcome": outcome,
                "result": result, "reviewArtifactId": artifact["id"]}

    def review(self, request=None): return self.api.review(self.token, self.wid, request or self.evidence())

    def test_acceptance_is_separate_and_does_not_upgrade_other_axes(self):
        before = self.store.snapshot(); meta = self.ledger.snapshot()["meta"]
        r = self.review(); w = self.worker(); q = self.ledger.snapshot()["queue"][0]
        self.assertTrue(r["packetAccepted"]); self.assertEqual(w["status"], "complete")
        self.assertTrue(w["preserved"]); self.assertFalse(w["archived"])
        for name in ("executionAuthorized", "nativeCallMade", "retryAuthorized", "pilotAccepted", "archiveAuthorized"):
            self.assertFalse(r[name])
        for axis in AXES:
            self.assertEqual(w["evidence"][axis]["status"], "verified" if axis in ("source", "ci") else "unverified")
        self.assertEqual(q["status"], "complete"); self.assertFalse(q["held"])
        self.assertEqual(before, self.store.snapshot())
        for field in ("paused", "pilotPassed", "concurrency", "heartbeat", "runner"):
            self.assertEqual(meta[field], self.ledger.snapshot()["meta"][field])
        summary = self.fx.fx.fx.registry.summary({"a"})
        self.assertEqual(summary["aggregate"]["completedTasks"], 1)
        self.assertEqual(summary["aggregate"]["settledTasks"], 0)

    def test_changes_required_stays_held_without_retry_or_evidence_upgrade(self):
        r = self.evidence("changes_required")
        r["result"]["criteria"][0]["proof"] = self.proof("criterion:0", "failed")
        r["result"]["observedAt"] = time.time()
        r = self.request(r["result"], "changes_required")
        before = self.worker(); result = self.review(r)
        self.assertFalse(result["packetAccepted"])
        self.assertEqual(self.worker()["status"], "settled")
        self.assertEqual(self.worker()["evidence"], before["evidence"])
        self.assertFalse(self.worker()["preserved"])
        with self.assertRaises(Refusal): self.fx.fx.fx.reserve()
        with self.assertRaises(Refusal): self.fx.fx.begin()
        with self.assertRaises(Refusal): self.fx.fx.observe()
        with self.assertRaises(Refusal): self.review()

    def test_exact_replay_is_read_only_after_pause_and_expiry(self):
        r = self.evidence(); receipt = self.review(r)
        self.fx.fx.fx.fx.fx.command("pause")
        before = self.logical(); shared = self.store.snapshot()
        with patch.object(self.store, "clock", return_value=time.time()+10000):
            self.assertEqual(self.review(r), receipt)
            self.assertEqual(self.api.read(self.token, self.wid), receipt)
        self.assertEqual(self.logical(), before); self.assertEqual(self.store.snapshot(), shared)

    def test_conflicting_replay_refuses(self):
        r = self.evidence(); self.review(r)
        with self.assertRaisesRegex(Refusal, "different content"): self.review({**r, "id": "another"})

    def test_settlement_recovery_after_review_does_not_undo_acceptance(self):
        r = self.review(); before = self.logical(); shared = self.store.snapshot()
        old = self.fx.api.recover(self.token, self.wid)
        self.assertFalse(old["packetAccepted"])
        self.assertEqual(self.worker()["status"], "complete")
        self.assertEqual(self.api.read(self.token, self.wid), r)
        self.assertEqual(before, self.logical()); self.assertEqual(shared, self.store.snapshot())

    def test_maintenance_blocks_new_review_but_allows_historical_read(self):
        r = self.evidence(); (self.ledger.root / "admission-fence.json").touch(mode=0o600)
        with self.assertRaisesRegex(Refusal, "maintenance"): self.review(r)
        # Remove only a synthetic empty fixture fence, never a live fence.
        (self.ledger.root / "admission-fence.json").unlink()
        receipt = self.review(r); (self.ledger.root / "admission-fence.json").touch(mode=0o600)
        with self.assertRaises(Refusal): self.review(r)
        self.assertEqual(self.api.read(self.token, self.wid), receipt)

    def test_pause_prevents_new_acceptance(self):
        r = self.evidence(); self.fx.fx.fx.fx.fx.command("pause")
        r["expectedRevision"] = self.ledger.snapshot()["meta"]["revision"]
        with self.assertRaisesRegex(Refusal, "paused"): self.review(r)
        self.assertEqual(self.worker()["status"], "settled")

    def test_stale_revision_does_not_write(self):
        r = self.evidence(); r["expectedRevision"] -= 1; before = self.logical()
        with self.assertRaisesRegex(Refusal, "Workspace changed"): self.review(r)
        self.assertEqual(before, self.logical())

    def test_expired_current_run_cannot_accept(self):
        r = self.evidence()
        with patch("orchestrator.run_authority.time.time", return_value=time.time()+7200):
            with self.assertRaisesRegex(Refusal, "expired"): self.review(r)

    def test_revoked_task_cannot_accept(self):
        run_fx = self.fx.fx.fx.fx
        runs.revoke_task(self.ledger, run_fx.request(queueId=self.intent["queueId"],
            approvalHash=self.intent["approvalHash"], reason="Withdrawn fixture"), actor="dashboard_owner")
        with self.assertRaisesRegex(Refusal, "approval"): self.review()

    def test_wrong_controller_or_workspace_cannot_accept(self):
        r = self.evidence()
        with self.assertRaises(Refusal): self.api.review("wrong", self.wid, r)
        with self.assertRaises(Refusal): self.api.review(self.token, "foreign", r)

    def test_complete_scope_is_required(self):
        for paths in (["other.py"], [], ["src/example.py", "src/example.py"], ["src/../example.py"],
                      ["./src/example.py"], ["src//example.py"], ["src/*"], ["/src/example.py"]):
            with self.subTest(paths=paths), self.assertRaises(Refusal): self.review(self.evidence(changedPaths=paths))
        with self.assertRaises(Refusal): self.review(self.evidence(diffComplete=False))

    def test_out_of_scope_failure_can_be_retained_but_not_accepted(self):
        request = self.evidence("changes_required", changedPaths=["outside-scope.py"])
        result = self.review(request)
        self.assertFalse(result["packetAccepted"])
        self.assertTrue(self.ledger.snapshot()["queue"][0]["held"])

    def test_exact_seed_base_branch_and_commit_bindings(self):
        for changed in ({"seedHash": "e"*64}, {"baseSHA": "d"*40}, {"branch": "codex/other"}, {"commit": "b"*40}):
            with self.subTest(changed=changed), self.assertRaises(Refusal): self.review(self.evidence(**changed))

    def test_ci_empty_missing_pending_failed_and_wrong_commit_refuse(self):
        base = self.evidence()["result"]
        for case in ("empty", "missing", "pending", "failed", "head", "incomplete", "duplicate"):
            r = copy.deepcopy(base); ci = r["ci"]
            if case == "empty": ci.update(checks=[], requiredChecks=[])
            if case == "missing": ci["checks"] = []
            if case in ("pending", "failed"): ci["checks"][0]["status"] = case
            if case == "head": ci["checks"][0]["headSHA"] = "b"*40
            if case == "incomplete": ci["complete"] = False
            if case == "duplicate": ci["checks"].append(ci["checks"][0])
            with self.subTest(case=case), self.assertRaises(Refusal): self.review(self.request(r))

    def test_all_exact_criteria_required_once(self):
        base = self.evidence()["result"]
        for case in ("missing", "duplicate", "wrong_hash", "failed", "unverified", "not_applicable"):
            r = copy.deepcopy(base)
            if case == "missing": r["criteria"] = []
            if case == "duplicate": r["criteria"].append(r["criteria"][0])
            if case == "wrong_hash": r["criteria"][0]["criterionHash"] = "f"*64
            if case in ("failed", "unverified", "not_applicable"): r["criteria"][0]["proof"]["status"] = case
            with self.subTest(case=case), self.assertRaises(Refusal): self.review(self.request(r))

    def test_all_axes_required_but_optional_axes_not_upgraded(self):
        base = self.evidence()["result"]
        for case in ("missing", "source", "ci", "extra"):
            r = copy.deepcopy(base)
            if case == "missing": del r["evidence"]["tenant"]
            elif case == "extra": r["evidence"]["allDone"] = r["evidence"]["source"]
            else: r["evidence"][case]["status"] = "unverified"
            with self.subTest(case=case), self.assertRaises(Refusal): self.review(self.request(r))

    def test_merge_success_cannot_be_inferred_from_open_pr(self):
        r = self.evidence()["result"]; r["evidence"]["merge"] = self.proof("merge")
        r["observedAt"] = time.time()
        with self.assertRaisesRegex(Refusal, "unmerged"): self.review(self.request(r))

    def test_merged_pr_still_does_not_prove_runtime(self):
        r = self.evidence()["result"]; r["pr"].update(state="merged", mergeCommit="e"*40)
        r["evidence"]["merge"] = self.proof("merge"); r["observedAt"] = time.time()
        self.review(self.request(r))
        self.assertEqual(self.worker()["evidence"]["merge"]["status"], "verified")
        self.assertEqual(self.worker()["evidence"]["runtime"]["status"], "unverified")

    def test_preservation_and_open_or_merged_pr_required(self):
        base = self.evidence()["result"]
        for case in ("preservation", "closed", "credential"):
            r = copy.deepcopy(base)
            if case == "preservation": r["preservation"]["status"] = "unverified"
            if case == "closed": r["pr"]["state"] = "closed"
            if case == "credential": r["pr"]["url"] = "https://secret@example.test/pull/1"
            with self.subTest(case=case), self.assertRaises(Refusal): self.review(self.request(r))

    def test_reviewer_cannot_be_worker(self):
        r = self.evidence()["result"]
        with self.assertRaisesRegex(Refusal, "review itself"):
            self.review(self.request(r, reviewer={"hostId": "local", "threadId": "worker-fixture"}))

    def test_reviewer_cannot_be_descendant_or_pending_client(self):
        for name in ("child", "pending"):
            other = ResultReviewTest()
            other.descendants = ("child",) if name == "child" else ()
            other.pending_client = "pending" if name == "pending" else None
            other.setUp()
            try:
                r = other.evidence()["result"]
                with self.subTest(name=name), self.assertRaisesRegex(Refusal, "review itself"):
                    other.review(other.request(r, reviewer={"hostId": "local", "threadId": name}))
            finally: other.tearDown()

    def test_review_binds_exact_result_and_verdict(self):
        result = self.evidence()["result"]
        for changes in ({"resultHash": "a"*64}, {"settlementHash": "b"*64}, {"intentHash": "c"*64},
                        {"workerId": "foreign"}, {"summary": ""}):
            with self.subTest(changes=changes), self.assertRaises(Refusal): self.review(self.request(result, **changes))
        r = self.request(result, "changes_required"); r["outcome"] = "accepted"
        with self.assertRaisesRegex(Refusal, "binding"): self.review(r)

    def test_missing_corrupt_foreign_and_oversized_proof_refuse(self):
        r = self.evidence(); aid = r["result"]["evidence"]["source"]["artifactId"]
        with self.ledger.tx() as db: original = db.execute("SELECT data,content FROM artifact_versions WHERE id=?", (aid,)).fetchone()
        for case in ("missing", "bytes", "oversized", "foreign", "commit", "subject", "intent"):
            with self.ledger.tx() as db:
                info, raw = json.loads(original[0]), original[1]
                if case == "missing": db.execute("DELETE FROM artifact_versions WHERE id=?", (aid,))
                else:
                    if case == "bytes": raw = b"changed"
                    if case == "oversized": raw = b"x"*16001
                    if case == "foreign": info["repository"] = "other"
                    if case in ("commit", "subject"): info["references"][0][case] = "other"
                    if case == "intent": info["references"][0]["intentHash"] = "b"*64
                    db.execute("UPDATE artifact_versions SET data=?,content=? WHERE id=?", (canonical(info), raw, aid))
            with self.subTest(case=case), self.assertRaises(Refusal): self.review(r)
            with self.ledger.tx() as db: db.execute("INSERT OR REPLACE INTO artifact_versions VALUES(?,?,?)", (aid, *original))

    def test_stale_future_and_predating_evidence_refuse(self):
        r = self.evidence()
        with patch.object(self.store, "clock", return_value=time.time()+1000):
            with self.assertRaisesRegex(Refusal, "Fresh"): self.review(r)
        with patch.object(self.store, "clock", return_value=time.time()-1000):
            with self.assertRaisesRegex(Refusal, "Fresh"): self.review(r)
        result = r["result"]
        with self.assertRaises(Refusal): self.review(self.request(result, observedAt=1))

    def test_local_event_failure_rolls_back_every_review_write(self):
        r = self.evidence(); before = self.logical(); shared = self.store.snapshot()
        original = self.api.ledger.event
        def failed(db, kind, data):
            original(db, kind, data)
            if kind == "result_reviewed": raise RuntimeError("fixture rollback")
        with patch.object(self.api.ledger, "event", side_effect=failed):
            with self.assertRaises(RuntimeError): self.review(r)
        self.assertEqual(before, self.logical()); self.assertEqual(shared, self.store.snapshot())
        self.review(r)

    def test_process_exit_before_workspace_commit_leaves_no_acceptance(self):
        r = self.evidence(); before = self.logical(); shared = self.store.snapshot()
        script = """
import json, os, sys
from orchestrator.admission import AdmissionStore
from orchestrator.dispatch_admission import DispatchAdmission
from orchestrator.result_review import ResultReview
from orchestrator.workspaces import Registry
registry = Registry(sys.argv[1])
api = ResultReview(DispatchAdmission(registry, 'a', AdmissionStore(registry.root)))
api.ledger.event = lambda *args: os._exit(23)
api.review(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]))
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.store.root), self.token, self.wid, canonical(r)], capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 23, child.stderr.decode())
        self.assertEqual(before, self.logical()); self.assertEqual(shared, self.store.snapshot())
        self.review(r)

    def test_process_exit_after_commit_needs_only_historical_receipt(self):
        r = self.evidence(); shared = self.store.snapshot()
        script = """
import json, os, sys
from orchestrator.admission import AdmissionStore
from orchestrator.dispatch_admission import DispatchAdmission
from orchestrator.result_review import ResultReview
from orchestrator.workspaces import Registry
registry = Registry(sys.argv[1])
api = ResultReview(DispatchAdmission(registry, 'a', AdmissionStore(registry.root)))
api.review(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]))
os._exit(24)
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.store.root), self.token, self.wid, canonical(r)], capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 24, child.stderr.decode())
        before = self.logical()
        self.assertEqual(self.api.read(self.token, self.wid), self.review(r))
        self.assertEqual(before, self.logical()); self.assertEqual(shared, self.store.snapshot())

    def test_competing_reviews_have_one_winner(self):
        requests = [self.evidence(), self.evidence("changes_required")]
        for r in requests: r["expectedRevision"] = self.ledger.snapshot()["meta"]["revision"]
        def attempt(r):
            try: return self.review(r)["outcome"]
            except Refusal: return "refused"
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(attempt, requests))
        self.assertEqual(results.count("refused"), 1)
        with self.ledger.tx() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM snapshots WHERE kind='result_review'").fetchone()[0], 1)

    def test_other_workspace_resource_owner_is_untouched(self):
        bridge, token, args = self.fx.fx.fx.second_workspace(KEY)
        other = bridge.reserve(token, **args); before = self.store.snapshot()
        self.review(); self.fx.api.recover(self.token, self.wid)
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(self.store.snapshot()["resources"][0]["claimId"], other["workerId"])

    def test_corruption_after_review_blocks_reads_and_settlement_recovery(self):
        r = self.evidence(); self.review(r)
        with self.ledger.tx() as db: db.execute("DELETE FROM artifact_versions WHERE id=?", (r["reviewArtifactId"],))
        with self.assertRaises(Refusal): self.api.read(self.token, self.wid)
        with self.assertRaises(Refusal): self.fx.api.recover(self.token, self.wid)

    def test_changed_worker_and_queue_projection_refuse(self):
        self.review(); self.fx.mutate_worker(preserved=False)
        with self.assertRaisesRegex(Refusal, "projection"): self.api.read(self.token, self.wid)

    def test_legacy_archive_and_pilot_paths_remain_fenced(self):
        self.review()
        with self.assertRaisesRegex(Refusal, "archival"):
            self.fx.fx.fx.fx.fx.command("archive", {"workerId": self.wid})
        with self.assertRaisesRegex(Refusal, "pilot"): self.ledger.pilot(self.token, self.wid, "not independent qualification")
        for status in ("queued", "processing"):
            with self.ledger.tx() as db:
                self.ledger.put(db, "commands", "stale-archive", {"id": "stale-archive", "kind": "archive",
                    "payload": {"workerId": self.wid}, "status": status})
            if status == "queued":
                self.assertEqual(self.ledger.process(self.token), [])
            else:
                with self.assertRaisesRegex(Refusal, "archival"): self.ledger.acknowledge(self.token, "stale-archive", True, "stale result")
        self.assertFalse(self.worker()["archived"])

    def test_result_review_changes_pause_binding(self):
        before = workspace_pause.worker_binding(self.worker()); self.review()
        after = workspace_pause.worker_binding(self.worker())
        self.assertNotEqual(before, after); self.assertIn("resultReviewHash", after)

    def test_accepted_worker_remains_in_next_safe_pause_inventory(self):
        self.review(); stop = self.fx.fx.fx.fx.fx.command("brain_stop")
        state = self.ledger.snapshot(); retained = state["meta"]["brainControl"]["retainedWorkers"]
        self.assertEqual(len(retained), 1); self.assertEqual(retained[0]["id"], self.wid)
        self.assertTrue(retained[0]["requiresNativeSupervision"])
        self.assertEqual(state["workspacePause"]["retainedWorkers"], 1)
        self.assertFalse(state["workspacePause"]["readyToPark"])
        self.ledger.process(self.token)
        workspace_pause.observe(self.ledger, self.token, stop["id"], {"workspaceId": "a", "commandId": stop["id"],
            "observedAt": time.time(), "evidenceHash": "c"*64, "complete": True, "includesDescendants": True,
            "brain": {"hostId": "local", "threadId": "brain-a"}, "tasks": []})
        state = self.ledger.snapshot()
        self.assertFalse(state["workspacePause"]["readyToPark"])
        self.assertTrue(any(b.get("workerId") == self.wid for b in state["workspacePause"]["blockers"]))

    def test_assistant_does_not_offer_managed_archive(self):
        self.review(); actions = catalog(self.ledger.snapshot(), {})
        self.assertFalse(actions["archive_W1"]["available"])
        self.assertIn("adapter", actions["archive_W1"]["unavailableReason"])

    def test_detached_local_settlement_requires_separate_recovery(self):
        r = self.evidence(); self.fx.mutate_worker(ownershipSettlementHash=None)
        before = self.logical()
        with self.assertRaisesRegex(Refusal, "Recover local settlement"): self.review(r)
        self.assertEqual(before, self.logical())

    def test_no_terminal_journal_cannot_accept(self):
        r = self.evidence()
        with self.store.tx() as db: db.execute("DELETE FROM ownership_settlements")
        with self.assertRaisesRegex(Refusal, "journal is missing"): self.review(r)

    def test_changed_allocation_does_not_reset_or_accept(self):
        r = self.evidence()
        with self.store.tx() as db:
            allocation = self.store.get(db, "allocations", self.intent["allocationId"])
            allocation["spec"]["limits"]["tokenBudget"] += 1
            self.store.put(db, "allocations", self.intent["allocationId"], allocation)
        before = self.store.snapshot()
        with self.assertRaisesRegex(Refusal, "allocation binding"): self.review(r)
        self.assertEqual(before, self.store.snapshot())

    def test_handoff_bytes_required_even_after_result_review(self):
        self.review()
        record = self.ledger.document(self.worker()["ownershipSettlementHash"])
        aid = record["request"]["inventory"]["tasks"][0]["checkpointArtifactId"]
        with self.ledger.tx() as db: db.execute("DELETE FROM artifact_versions WHERE id=?", (aid,))
        with self.assertRaisesRegex(Refusal, "handoff"): self.api.read(self.token, self.wid)

    def test_queue_projection_corruption_refuses_replay(self):
        r = self.evidence(); self.review(r)
        with self.ledger.tx() as db:
            q = self.ledger.get(db, "queue", self.intent["queueId"]); q["held"] = True
            self.ledger.put(db, "queue", q["id"], q)
        with self.assertRaisesRegex(Refusal, "queue projection"): self.review(r)

    def test_unreviewed_evidence_cannot_be_promoted_by_mutable_fields(self):
        r = self.evidence(); self.fx.mutate_worker(preserved=True)
        with self.assertRaisesRegex(Refusal, "projection changed"): self.review(r)

    def test_pending_control_blocks_result_review(self):
        self.fx.fx.fx.fx.fx.command("checkpoint", {"workerId": self.wid})
        with self.assertRaisesRegex(Refusal, "control remains unresolved"): self.review()

    def test_independent_report_must_be_unique_field_json(self):
        r = self.evidence()
        with self.ledger.tx() as db: raw = db.execute("SELECT content FROM artifact_versions WHERE id=?", (r["reviewArtifactId"],)).fetchone()[0]
        for data in (b"not JSON", b"[1,2]", raw[:-1]+b',"outcome":"accepted"}'):
            artifact = self.artifact("independent_review", data)
            with self.assertRaises(Refusal): self.review({**r, "reviewArtifactId": artifact["id"]})

    def test_native_history_corruption_does_not_become_acceptance(self):
        r = self.evidence()
        with self.store.tx() as db: db.execute("DELETE FROM native_records")
        with self.assertRaises(Refusal): self.review(r)

    def test_harness_has_no_generic_result_acceptance(self):
        import test_core
        initialize, make_seed = test_core.Ledger.initialize, test_core.seed
        def harness_initialize(ledger, config):
            config = copy.deepcopy(config)
            for repo in config["repositories"]:
                if repo["id"] == "a": repo.update(policyProfile="harness")
            return initialize(ledger, config)
        def harness_seed(*args, **kwargs):
            kwargs["profile"] = "harness"
            return make_seed(*args, **kwargs)
        other = test_ownership_settlement.OwnershipSettlementTest()
        with patch.object(test_core.Ledger, "initialize", harness_initialize), patch.object(test_core, "seed", harness_seed):
            other.setUp()
        try:
            other.settle()
            api = result_review.ResultReview(other.bridge)
            r = self.evidence(); r["settlementHash"] = other.worker()["ownershipSettlementHash"]
            r["expectedRevision"] = other.ledger.snapshot()["meta"]["revision"]
            with self.assertRaisesRegex(Refusal, "Harness result acceptance needs its trusted adapter"):
                api.review(other.token, other.wid, r)
        finally: other.tearDown()

    def test_read_without_review_has_no_effect(self):
        before = self.logical(); shared = self.store.snapshot()
        with self.assertRaisesRegex(Refusal, "No result review"): self.api.read(self.token, self.wid)
        self.assertEqual(before, self.logical()); self.assertEqual(shared, self.store.snapshot())

    def test_invalid_and_oversized_request_never_writes(self):
        r = self.evidence(); before = self.logical()
        for change in ({"extra": 1}, {"id": "x"*16001}, {"expectedRevision": True}, {"expectedRevision": float("nan")},
                       {"outcome": "complete"}, {"reviewArtifactId": None}):
            with self.subTest(change=change), self.assertRaises(Refusal): self.review({**r, **change})
        self.assertEqual(before, self.logical())

    def test_noncreation_outcome_cannot_be_accepted(self):
        fx = test_creation_recovery.CreationRecoveryTest(); fx.setUp()
        try:
            fx.begin(); fx.settle()
            api = result_review.ResultReview(fx.fx.bridge)
            r = self.evidence(); r["settlementHash"] = fx.worker()["ownershipSettlementHash"]
            with self.assertRaisesRegex(Refusal, "exact terminal outcome"): api.review(fx.token, fx.wid, r)
        finally: fx.tearDown()


if __name__ == "__main__": unittest.main()
