import copy
import json
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import ownership_settlement, run_authority as runs, workspace_pause
from orchestrator.admission import AdmissionStore
from orchestrator.core import Refusal, canonical, digest
from orchestrator.dispatch_admission import DispatchAdmission
from orchestrator.native_lifecycle import NativeLifecycle
from orchestrator.observations import capture
import test_native_lifecycle
from test_dispatch_admission import KEY, ESTIMATES


class OwnershipSettlementTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_native_lifecycle.NativeLifecycleTest(); self.fx.setUp()
        self.fx.observe()
        self.ledger, self.token, self.store, self.wid = self.fx.ledger, self.fx.token, self.fx.store, self.fx.wid
        self.bridge = self.fx.fx.bridge
        self.api = ownership_settlement.OwnershipSettlement(self.bridge)
        self.seq = 0

    def tearDown(self): self.fx.tearDown()
    def worker(self): return self.fx.worker()
    def claim(self):
        with self.store.tx() as db: return self.store.get(db, "claims", self.wid)
    def budget(self):
        return next(a["budget"] for a in self.store.snapshot()["allocations"] if a["id"] == self.fx.fx.binding["id"])

    def evidence(self, descendants=()):
        self.seq += 1
        tasks, sessions = [], []
        root = {"hostId": "local", "threadId": "worker-fixture"}
        for tid in ("worker-fixture", *descendants):
            with self.ledger.tx() as db:
                artifact = capture(db, "terminal-"+tid+"-"+str(self.seq), b"Retained result, unresolved acceptance and handoff.",
                    {"repository": "a", "name": "handoff.md", "orderAt": time.time(),
                     "references": [{"session": tid, "at": time.time()}]})
            tasks.append({"hostId": "local", "threadId": tid, "parent": None if tid == "worker-fixture" else root,
                "status": "idle", "observedAt": time.time(), "evidenceHash": "a"*64, "checkpointArtifactId": artifact["id"]})
        inventory = {"observedAt": time.time(), "evidenceHash": "b"*64, "complete": True, "includesDescendants": True,
                     "pendingResolved": True, "effectsComplete": True, "tasks": tasks}
        for task in tasks:
            sessions.append({"hostId": task["hostId"], "threadId": task["threadId"], "counterEpoch": "c"*64,
                "counters": {"inputTokens": 800, "cachedInputTokens": 600, "outputTokens": 200, "reasoningOutputTokens": 100},
                "complete": True, "observedAt": time.time(), "evidenceHash": "d"*64})
        return {"id": "settle-"+str(self.seq), "expectedHash": self.claim()["nativeLifecycleHash"], "inventory": inventory,
                "resources": [{"key": KEY, "processesExited": True, "cleanupObserved": True, "observedAt": time.time(), "evidenceHash": "e"*64}],
                "usage": {"observedAt": time.time(), "evidenceHash": "f"*64, "complete": True, "sessions": sessions}}

    def settle(self, request=None): return self.api.settle(self.token, self.wid, request or self.evidence())
    def mutate_worker(self, **fields):
        with self.ledger.tx() as db:
            worker = self.ledger.get(db, "workers", self.wid); worker.update(fields)
            self.ledger.put(db, "workers", self.wid, worker)

    def test_settlement_releases_only_ownership_not_packet_acceptance(self):
        before = self.worker(); result = self.settle()
        self.assertEqual(self.claim()["status"], "settled")
        self.assertEqual(self.worker()["status"], "settled")
        self.assertTrue(result["ownershipReleased"])
        self.assertFalse(result["packetAccepted"]); self.assertFalse(result["nativeCallMade"])
        self.assertFalse(result["executionAuthorized"])
        self.assertEqual(self.store.snapshot()["resources"], [])
        self.assertEqual(self.budget()["heldTokens"], 0)
        self.assertEqual(self.budget()["unincorporatedSettledTokens"], 1000)
        self.assertEqual(self.claim()["estimatedTokens"], 11500)
        self.assertEqual(self.worker()["evidence"], before["evidence"])
        self.assertFalse(self.worker()["preserved"]); self.assertFalse(self.worker()["archived"])
        self.assertNotIn("completedAt", self.worker())
        q = self.ledger.snapshot()["queue"][0]
        self.assertTrue(q["held"]); self.assertNotEqual(q["status"], "complete")
        self.assertFalse(self.ledger.snapshot()["meta"]["pilotPassed"])

    def test_exact_replay_and_recovery_have_no_second_effect_or_freshness_reset(self):
        request = self.evidence(); result = self.settle(request); before = self.store.snapshot()
        with patch.object(self.store, "clock", return_value=time.time()+1000):
            self.assertEqual(self.settle(request), result)
            self.assertEqual(self.api.recover(self.token, self.wid), result)
        self.assertEqual(before, self.store.snapshot())
        with self.assertRaisesRegex(Refusal, "different evidence"): self.settle({**request, "id": "other"})

    def test_wrong_brain_and_foreign_worker_cannot_settle(self):
        request = self.evidence()
        with self.assertRaises(Refusal): self.api.settle("wrong", self.wid, request)
        with self.assertRaises(Refusal): self.api.settle(self.token, "other-worker", request)
        self.assertEqual(self.claim()["status"], "running")

    def test_missing_partial_or_inaccurate_shape_cannot_release(self):
        original = self.evidence()
        for field in ("complete", "includesDescendants", "pendingResolved", "effectsComplete"):
            for value in (False, None, 1):
                request = copy.deepcopy(original); request["inventory"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(Refusal): self.settle(request)
        for field in ("processesExited", "cleanupObserved"):
            request = copy.deepcopy(original); request["resources"][0][field] = False
            with self.assertRaises(Refusal): self.settle(request)
        for change in ({"extra": "no commands"}, {"id": "x"*101}, {"expectedHash": None}):
            with self.assertRaises(Refusal): self.settle({**original, **change})
        self.assertEqual(len(self.store.snapshot()["resources"]), 1)

    def test_unknown_running_and_unresolved_creation_refuse(self):
        for state in ("running", "unknown"):
            request = self.evidence(); request["inventory"]["tasks"][0]["status"] = state
            with self.assertRaises(Refusal): self.settle(request)
        self.fx.observe(outcome="uncertain", activity="unknown")
        with self.assertRaisesRegex(Refusal, "Confirmed idle"): self.settle()

    def test_stale_future_and_predating_evidence_refuse(self):
        request = self.evidence()
        for group in ("inventory", "usage"):
            for at in (time.time()-61, time.time()+60, 0, float("nan")):
                changed = copy.deepcopy(request); changed[group]["observedAt"] = at
                with self.subTest(group=group, at=at), self.assertRaises(Refusal): self.settle(changed)
        for rows in ("tasks", "sessions", "resources"):
            changed = copy.deepcopy(request)
            items = changed["inventory"][rows] if rows == "tasks" else changed["usage"][rows] if rows == "sessions" else changed[rows]
            items[0]["observedAt"] = self.claim()["startedAt"]-1
            with self.assertRaises(Refusal): self.settle(changed)
        with patch.object(self.store, "clock", return_value=time.time()+61):
            with self.assertRaises(Refusal): self.settle(request)

    def test_changed_native_hash_requires_new_evidence(self):
        request = self.evidence(); self.fx.observe()
        with self.assertRaisesRegex(Refusal, "journal changed"): self.settle(request)
        self.settle()

    def test_detached_native_receipt_requires_explicit_recovery(self):
        with patch.object(self.fx.api, "attach_in", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.fx.observe()
        with self.assertRaisesRegex(Refusal, "Recover exact"): self.settle()
        self.fx.api.recover(self.token, self.wid); self.settle()

    def test_inflight_and_uncertain_continuations_never_settle(self):
        self.fx.begin()
        for outcome in (None, "acknowledged", "uncertain"):
            if outcome: self.fx.deliver(outcome)
            with self.assertRaises(Refusal): self.settle()
        self.assertEqual(self.budget()["heldTokens"], 12650)

    def test_unmatched_local_continuation_marker_never_releases(self):
        with patch.object(self.fx.api, "append_in", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.fx.begin()
        with self.assertRaisesRegex(Refusal, "Unmatched"): self.settle()
        self.assertEqual(self.budget()["heldTokens"], 11500)

    def test_finished_correction_accounts_all_reserved_work_once(self):
        self.fx.begin(); self.fx.deliver(); self.fx.deliver("finished")
        result = self.settle()
        self.assertEqual(self.claim()["estimatedTokens"], 12650)
        self.assertEqual(result["actualTokens"], 1000)
        self.assertEqual(self.worker()["noProgressCycles"], 1)

    def test_pause_expiry_revocation_and_low_headroom_do_not_prevent_safe_settlement(self):
        self.fx.fx.fx.fx.command("pause")
        runs.revoke_task(self.ledger, self.fx.fx.fx.request(queueId=self.worker()["queueId"],
            approvalHash=self.fx.fx.approval["approvalHash"], reason="fixture revoked"), actor="dashboard_owner")
        # Settlement is not new work. Unknown account usage or expired authority
        # cannot conceal actual usage or prevent safe relinquishment.
        with self.store.tx() as db:
            meta = self.store.get(db, "meta", 1); meta["account"] = None; self.store.put(db, "meta", 1, meta)
        with patch("orchestrator.run_authority.require_current", side_effect=AssertionError("not a new effect")):
            self.settle()
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])

    def test_maintenance_fences_preserve_owners(self):
        request = self.evidence()
        for path in (self.ledger.root / "admission-fence.json", self.store.root / "adoption-fence.json", self.store.root / "adoption-kernel.json"):
            path.touch(mode=0o600)
            try:
                with self.assertRaises(Refusal): self.settle(request)
            finally: path.unlink()  # isolated fixture only
        with self.fx.fx.registry.tx() as db:
            db.execute("CREATE TABLE admission_enrollment(id INTEGER PRIMARY KEY,data TEXT)")
            db.execute("INSERT INTO admission_enrollment VALUES(1,?)", (canonical({"state": "prepared"}),))
        with self.assertRaisesRegex(Refusal, "enrollment"): self.settle(request)
        self.assertEqual(self.claim()["status"], "running")

    def test_local_and_shared_runner_ownership_prevents_release(self):
        self.fx.fx.meta(runner={"workerId": self.wid})
        with self.assertRaisesRegex(Refusal, "Local runner"): self.settle()
        self.fx.fx.meta(runner=None)
        with self.store.tx() as db:
            db.execute("INSERT INTO resources VALUES(?,?,?)", ("runner:"+"a"*64, self.wid, time.time()))
        with self.assertRaisesRegex(Refusal, "Shared runner"): self.settle()
        self.assertEqual(len(self.store.snapshot()["resources"]), 2)

    def test_worker_controls_block_until_resolved(self):
        cmd = self.fx.fx.fx.fx.command("checkpoint", {"workerId": self.wid})
        with self.assertRaisesRegex(Refusal, "control"): self.settle()
        self.ledger.process(self.token)
        with self.assertRaisesRegex(Refusal, "control"): self.settle()
        self.ledger.acknowledge(self.token, cmd["id"], False, "Fixture control withdrawn without effects")
        self.settle()

    def test_scope_and_ancestry_are_closed(self):
        request = self.evidence(descendants=("child",))
        for mutation in ("root", "cycle", "orphan", "brain"):
            changed = copy.deepcopy(request); tasks = changed["inventory"]["tasks"]
            if mutation == "root": tasks[0]["parent"] = {"hostId": "local", "threadId": "child"}
            if mutation == "cycle": tasks[1]["parent"] = {"hostId": "local", "threadId": "child"}
            if mutation == "orphan": tasks[1]["parent"] = None
            if mutation == "brain":
                tasks[1]["threadId"] = "brain-a"; changed["usage"]["sessions"][1]["threadId"] = "brain-a"
            with self.subTest(mutation=mutation), self.assertRaises(Refusal): self.settle(changed)
        result = self.settle(request)
        self.assertEqual(result["actualTokens"], 2000)

    def test_duplicate_and_foreign_usage_and_cleanup_refuse(self):
        original = self.evidence(descendants=("child",))
        for mutation in ("duplicate_task", "duplicate_usage", "foreign_usage", "missing_usage", "unknown_usage", "incomplete_usage", "foreign_resource", "duplicate_resource"):
            r = copy.deepcopy(original)
            if mutation == "duplicate_task": r["inventory"]["tasks"][1] = r["inventory"]["tasks"][0]
            if mutation == "duplicate_usage": r["usage"]["sessions"][1] = r["usage"]["sessions"][0]
            if mutation == "foreign_usage": r["usage"]["sessions"][0]["threadId"] = "foreign"
            if mutation == "missing_usage": r["usage"]["sessions"].pop()
            if mutation == "unknown_usage": r["usage"]["sessions"][0]["counters"] = None
            if mutation == "incomplete_usage": r["usage"]["complete"] = False
            if mutation == "foreign_resource": r["resources"][0]["key"] = "repo-local:"+"f"*64
            if mutation == "duplicate_resource": r["resources"].append(r["resources"][0])
            with self.subTest(mutation=mutation), self.assertRaises(Refusal): self.settle(r)

    def test_token_subsets_are_not_double_counted_and_invalid_counters_refuse(self):
        r = self.evidence()
        for change in ({"inputTokens": -1}, {"cachedInputTokens": 801}, {"outputTokens": True}, {"reasoningOutputTokens": 201}):
            changed = copy.deepcopy(r); changed["usage"]["sessions"][0]["counters"].update(change)
            with self.assertRaises(Refusal): self.settle(changed)
        self.assertEqual(self.settle(r)["actualTokens"], 1000)

    def test_actual_overrun_is_retained_and_blocks_subsequent_admission(self):
        r = self.evidence(); r["usage"]["sessions"][0]["counters"]["inputTokens"] = 100000
        self.settle(r)
        self.assertLess(self.budget()["remainingForNewWork"], 0)
        with self.assertRaisesRegex(Refusal, "headroom"):
            self.store.reserve("next", self.fx.fx.binding["id"], repositories=["a"], estimates=ESTIMATES)

    def test_usage_incorporation_does_not_double_count_or_reset_attempts(self):
        self.settle(); aid = self.fx.fx.binding["id"]
        self.store.observe_usage(aid, {"observedAt": time.time(), "evidenceHash": "a"*64,
            "counters": self.claim()["actual"], "coverage": ["brain", "workers", "reviews"], "settledClaimIds": [self.wid]})
        self.assertEqual(self.budget()["unincorporatedSettledTokens"], 0)
        self.assertEqual(self.budget()["observedTokens"], 1000)
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)
        with self.assertRaises(Refusal): self.fx.fx.reserve()
        with self.assertRaises(Refusal): self.fx.fx.begin()
        with self.assertRaises(Refusal): self.fx.begin()
        with self.assertRaises(Refusal): self.fx.observe()
        with self.assertRaises(Refusal): self.bridge.recover(self.token, self.wid)

    def test_shared_commit_failure_rolls_back_release_and_journal(self):
        before = self.store.snapshot(); original = self.api.commit_in
        def failed(*args): original(*args); raise RuntimeError("fixture after shared writes")
        with patch.object(self.api, "commit_in", side_effect=failed):
            with self.assertRaises(RuntimeError): self.settle()
        self.assertEqual(before, self.store.snapshot())
        with self.assertRaises(Refusal): self.api.recover(self.token, self.wid)
        self.settle()

    def test_local_attachment_failure_recovers_without_releasing_another_owner(self):
        r = self.evidence()
        with patch.object(self.api, "attach_in", side_effect=RuntimeError("fixture local failure")):
            with self.assertRaises(RuntimeError): self.settle(r)
        self.assertEqual(self.worker()["status"], "running")
        self.assertEqual(self.claim()["status"], "settled")
        self.store.reserve("new-owner", self.fx.fx.binding["id"], repositories=["a"], estimates=ESTIMATES)
        before = self.store.snapshot()
        self.fx.fx.fx.fx.command("pause")
        self.api.recover(self.token, self.wid)
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(self.worker()["status"], "settled")
        self.assertEqual(self.store.snapshot()["resources"][0]["claimId"], "new-owner")

    def test_process_exit_after_shared_release_recovers_exactly_once(self):
        request = self.evidence()
        script = """
import json, os, sys
from orchestrator.admission import AdmissionStore
from orchestrator.dispatch_admission import DispatchAdmission
from orchestrator.ownership_settlement import OwnershipSettlement
from orchestrator.workspaces import Registry
registry = Registry(sys.argv[1])
api = OwnershipSettlement(DispatchAdmission(registry, 'a', AdmissionStore(registry.root)))
api.attach_in = lambda *args: os._exit(23)
api.settle(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]))
"""
        child = subprocess.run([sys.executable, "-c", script, str(self.store.root), self.token, self.wid, canonical(request)],
                               capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 23, child.stderr.decode())
        self.assertEqual(self.worker()["status"], "running")
        self.assertEqual(self.claim()["status"], "settled")
        self.api = ownership_settlement.OwnershipSettlement(DispatchAdmission(self.fx.fx.registry, "a", AdmissionStore(self.store.root)))
        before = self.store.snapshot(); self.api.recover(self.token, self.wid)
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(self.settle(request)["settlementHash"], self.worker()["ownershipSettlementHash"])

    def test_competing_settlements_have_one_winner(self):
        requests = [self.evidence(), self.evidence()]
        def settle(r):
            try: return self.settle(r)["stage"]
            except Refusal: return "refused"
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(settle, requests))
        self.assertCountEqual(results, ["settled", "refused"])
        self.assertEqual(self.budget()["unincorporatedSettledTokens"], 1000)

    def test_corrupt_or_missing_settlement_never_recreates_a_release(self):
        self.settle()
        with self.store.tx() as db:
            db.execute("DELETE FROM ownership_settlements")
        with self.assertRaisesRegex(Refusal, "journal is missing"): self.api.recover(self.token, self.wid)

    def test_changed_shared_settlement_or_local_receipt_refuses(self):
        self.settle(); original = self.claim()
        with self.store.tx() as db:
            claim = copy.deepcopy(original); claim["actual"]["inputTokens"] += 1
            self.store.put(db, "claims", self.wid, claim)
        with self.assertRaisesRegex(Refusal, "diverged"): self.api.recover(self.token, self.wid)
        with self.store.tx() as db: self.store.put(db, "claims", self.wid, original)
        self.mutate_worker(status="complete")
        with self.assertRaisesRegex(Refusal, "diverged"): self.api.recover(self.token, self.wid)

    def test_missing_foreign_changed_and_oversized_artifacts_refuse(self):
        r = self.evidence(); aid = r["inventory"]["tasks"][0]["checkpointArtifactId"]
        with self.ledger.tx() as db:
            original = db.execute("SELECT data,content FROM artifact_versions WHERE id=?", (aid,)).fetchone()
        for mutation in ("missing", "foreign", "wrong_session", "old", "changed_bytes", "oversized"):
            with self.ledger.tx() as db:
                info, raw = json.loads(original[0]), original[1]
                if mutation == "missing": db.execute("DELETE FROM artifact_versions WHERE id=?", (aid,))
                else:
                    if mutation == "foreign": info["repository"] = "other"
                    if mutation == "wrong_session": info["references"] = []
                    if mutation == "old": info["observedAt"] = 1
                    if mutation == "changed_bytes": raw = b"Changed"
                    if mutation == "oversized": raw = b"x"*16001
                    db.execute("UPDATE artifact_versions SET data=?,content=? WHERE id=?", (canonical(info), raw, aid))
            with self.subTest(mutation=mutation), self.assertRaises(Refusal): self.settle(r)
            with self.ledger.tx() as db:
                db.execute("INSERT OR REPLACE INTO artifact_versions VALUES(?,?,?)", (aid, original[0], original[1]))
        self.settle(r)

    def pause_inventory(self, descendants=()):
        stop = self.fx.fx.fx.fx.command("brain_stop")
        self.ledger.process(self.token)
        r = self.evidence(descendants)
        tasks = [{k: t[k] for k in ("hostId", "threadId", "parent", "status", "observedAt", "checkpointArtifactId")} |
                 {"workerId": self.wid if t["parent"] is None else None} for t in r["inventory"]["tasks"]]
        workspace_pause.observe(self.ledger, self.token, stop["id"], {"workspaceId": "a", "commandId": stop["id"],
            "observedAt": time.time(), "evidenceHash": "c"*64, "complete": True, "includesDescendants": True,
            "brain": {"hostId": "local", "threadId": "brain-a"}, "tasks": tasks})
        return r

    def test_previously_observed_descendant_cannot_disappear(self):
        self.pause_inventory(descendants=("child", "review"))
        with self.assertRaisesRegex(Refusal, "descendant missing"): self.settle()
        with self.assertRaisesRegex(Refusal, "descendant missing"): self.settle(self.evidence(descendants=("child",)))
        self.assertEqual(self.settle(self.evidence(descendants=("child", "review")))["actualTokens"], 3000)

    def test_partial_inventory_with_missing_root_still_retains_known_child(self):
        self.pause_inventory(descendants=("child",))
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); old = meta["brainControl"]["pauseEvidenceHash"]
            record = self.ledger.get(db, "snapshots", old)
            record["document"]["tasks"] = record["document"]["tasks"][1:]
            record["document"]["complete"] = False
            db.execute("DELETE FROM snapshots WHERE id=?", (old,))
            new = digest(record)
            db.execute("INSERT INTO snapshots VALUES(?,?,?)", (new, "workspace_pause_evidence", canonical(record)))
            meta["brainControl"]["pauseEvidenceHash"] = new; self.ledger.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "descendant missing"): self.settle()

    def test_settlement_invalidates_old_pause_inventory(self):
        r = self.pause_inventory()
        self.assertNotIn("ownership_changed", [b["code"] for b in self.ledger.snapshot()["workspacePause"]["blockers"]])
        self.settle(r)
        snapshot = self.ledger.snapshot()
        self.assertIn("ownership_changed", [b["code"] for b in snapshot["workspacePause"]["blockers"]])
        self.assertTrue(snapshot["meta"]["paused"])
        self.assertFalse(snapshot["workspacePause"]["readyToPark"])

    def test_two_workspaces_can_reuse_resource_only_after_settlement(self):
        bridge, token, args = self.fx.fx.second_workspace(KEY)
        with self.assertRaisesRegex(Refusal, "already owned"): bridge.reserve(token, **args)
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)
        self.settle()
        result = bridge.reserve(token, **args)
        self.assertNotEqual(result["workerId"], self.wid)
        self.assertEqual(self.store.snapshot()["resources"][0]["claimId"], result["workerId"])
        before = self.store.snapshot(); self.api.recover(self.token, self.wid)
        self.assertEqual(before, self.store.snapshot())
        self.assertEqual(bridge.ledger.snapshot()["workers"][0]["status"], "reserved")

    def test_other_claim_and_registered_brain_cannot_be_imported_as_descendants(self):
        bridge, token, args = self.fx.fx.second_workspace("repo-remote:"+"b"*64)
        worker = bridge.reserve(token, **args); bridge.begin_creation(token, worker["workerId"])
        native = NativeLifecycle(bridge)
        native.observe(token, worker["workerId"], {"id": "other", "expectedHash": None, "outcome": "confirmed",
            "hostId": "local", "threadId": "foreign-task", "clientThreadId": None, "activity": "idle",
            "observedAt": time.time(), "evidenceHash": "f"*64})
        with self.assertRaisesRegex(Refusal, "another shared claim"): self.settle(self.evidence(descendants=("foreign-task",)))
        with self.assertRaisesRegex(Refusal, "registered brain"): self.settle(self.evidence(descendants=("brain-b",)))
        self.assertEqual(len(self.store.snapshot()["resources"]), 2)

    def test_settled_descendant_identity_cannot_be_rebound(self):
        self.settle(self.evidence(descendants=("child",)))
        bridge, token, args = self.fx.fx.second_workspace(KEY)
        worker = bridge.reserve(token, **args); bridge.begin_creation(token, worker["workerId"])
        native = NativeLifecycle(bridge)
        with self.assertRaisesRegex(Refusal, "another shared claim"):
            native.observe(token, worker["workerId"], {"id": "other", "expectedHash": None, "outcome": "confirmed",
                "hostId": "local", "threadId": "child", "clientThreadId": None, "activity": "idle",
                "observedAt": time.time(), "evidenceHash": "f"*64})

    def test_pending_client_id_never_counts_as_a_terminal_descendant(self):
        self.fx.observe(clientThreadId="pending-client")
        with self.assertRaisesRegex(Refusal, "client ID"): self.settle(self.evidence(descendants=("pending-client",)))

    def test_native_history_corruption_blocks_release_and_recovery(self):
        self.fx.observe(); self.settle()
        with self.store.tx() as db:
            key = self.store.get(db, "claims", self.wid)["nativeLifecycleHash"]
            db.execute("DELETE FROM native_records WHERE hash!=?", (key,))
        with self.assertRaisesRegex(Refusal, "history is incomplete"): self.api.recover(self.token, self.wid)

    def test_local_receipt_identity_drift_is_not_silently_repaired(self):
        with patch.object(self.api, "attach_in", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.settle()
        self.mutate_worker(clientThreadId="invented-client")
        with self.assertRaisesRegex(Refusal, "Local owner changed"): self.api.recover(self.token, self.wid)

    def test_missing_local_receipt_snapshot_requires_explicit_recovery(self):
        self.settle(); key = self.worker()["ownershipSettlementHash"]
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (key,))
        with self.assertRaises(Refusal): self.api.recover(self.token, self.wid)

    def test_resource_or_allocation_drift_cannot_be_repaired_by_settlement(self):
        with self.store.tx() as db:
            db.execute("UPDATE resources SET claim='foreign' WHERE claim=?", (self.wid,))
        with self.assertRaisesRegex(Refusal, "ownership changed"): self.settle()
        with self.store.tx() as db:
            db.execute("UPDATE resources SET claim=? WHERE claim='foreign'", (self.wid,))
            allocation = self.store.get(db, "allocations", self.fx.fx.binding["id"])
            allocation["spec"]["limits"]["tokenBudget"] += 1
            self.store.put(db, "allocations", allocation["id"], allocation)
        with self.assertRaisesRegex(Refusal, "allocation changed"): self.settle()

    def test_bounds_and_read_construction_do_not_create_a_settlement_store(self):
        before = self.store.snapshot(); ownership_settlement.OwnershipSettlement(self.bridge)
        self.assertEqual(before, self.store.snapshot())
        with self.store.tx() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='ownership_settlements'").fetchone())
        with self.assertRaises(Refusal): self.api.recover(self.token, self.wid)
        r = self.evidence(); r["inventory"]["tasks"] *= 17
        with self.assertRaises(Refusal): self.settle(r)
        r = self.evidence(); r["id"] = "a"*16001
        with self.assertRaises(Refusal): self.settle(r)
        self.assertEqual(before, self.store.snapshot())

    def test_portfolio_separates_settled_from_active_and_accepted_tasks(self):
        self.settle()
        summary = self.fx.fx.registry.summary({"a"})
        self.assertEqual(summary["workspaces"][0]["activeWorkers"], 0)
        self.assertEqual(summary["workspaces"][0]["settledWorkers"], 1)
        self.assertEqual(summary["aggregate"]["settledTasks"], 1)
        self.assertEqual(summary["aggregate"]["completedTasks"], 0)

    def test_exact_stale_recovery_stays_receipt_only_behind_maintenance_fence(self):
        request = self.evidence()
        with patch.object(self.api, "attach_in", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.settle(request)
        (self.ledger.root / "admission-fence.json").touch(mode=0o600)
        with self.assertRaises(Refusal): self.settle(request)
        before = self.store.snapshot()
        with patch.object(self.store, "clock", return_value=time.time()+1000):
            self.api.recover(self.token, self.wid)
        self.assertEqual(before, self.store.snapshot())

    def test_local_event_rollback_after_shared_commit_preserves_recovery(self):
        event = self.api.ledger.event
        def fail_event(db, kind, data):
            event(db, kind, data)
            if kind == "ownership_settlement_attached": raise RuntimeError("fixture local transaction rollback")
        with patch.object(self.api.ledger, "event", side_effect=fail_event):
            with self.assertRaises(RuntimeError): self.settle()
        self.assertEqual(self.claim()["status"], "settled")
        self.assertEqual(self.worker()["status"], "running")
        self.assertFalse(self.ledger.snapshot()["queue"][0]["held"])
        self.api.recover(self.token, self.wid)
        self.assertTrue(self.ledger.snapshot()["queue"][0]["held"])


if __name__ == "__main__": unittest.main()
