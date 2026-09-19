import copy
import contextlib
import io
import json
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import workspace_pause
from orchestrator.brain_control import park
from orchestrator.core import Ledger, Refusal
from orchestrator.observations import capture
from orchestrator.workspaces import Registry
import test_brain_control
import test_core


class WorkspacePauseTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_brain_control.BrainControlTest(); self.fx.setUp()
        self.registry = Registry(self.fx.ledger.root.parent / "platform", create=True)
        self.registry.register("alpha", "Alpha fixture", self.fx.ledger.root)
        self.fx.ledger = self.ledger = self.registry.ledger("alpha")

    def tearDown(self): self.fx.tearDown()

    def evidence(self, stop, extra=None):
        tasks = []
        for worker in self.ledger.snapshot()["workers"]:
            if worker.get("threadId"):
                tasks.append({"hostId": worker["hostId"], "threadId": worker["threadId"], "workerId": worker["id"], "parent": None,
                              "status": "idle", "repository": worker["repository"]})
        if extra: tasks.extend(copy.deepcopy(extra))
        for task in tasks:
            with self.ledger.tx() as db:
                artifact = capture(db, "checkpoint-" + task["threadId"], (stop["id"] + str(time.time())).encode(),
                    {"repository": task.pop("repository", "a"), "name": "checkpoint.md", "orderAt": time.time(),
                     "references": [{"session": task["threadId"], "at": time.time()}]})
            task.update(observedAt=time.time(), checkpointArtifactId=artifact["id"])
        return {"workspaceId": "alpha", "commandId": stop["id"], "observedAt": time.time(), "evidenceHash": "a" * 64,
                "complete": True, "includesDescendants": True,
                "brain": {"hostId": "local", "threadId": "brain-fixture"}, "tasks": tasks}

    def record(self, stop, document=None):
        return workspace_pause.observe(self.ledger, self.fx.token, stop["id"], document or self.evidence(stop))

    def checkpoint(self, stop, evidence=None):
        cp = self.fx.checkpoint(stop); cp.pop("workerObservations")
        cp["pauseEvidenceHash"] = self.record(stop, evidence)["documentHash"]
        return cp

    def codes(self): return {i["code"] for i in self.ledger.snapshot()["workspacePause"]["blockers"]}

    def test_pause_retains_scope_fences_approval_preparation_and_early_resume(self):
        seed = test_core.seed(); q = self.ledger.prepare(seed)
        stop = self.fx.stop()
        self.assertEqual(self.ledger.snapshot()["meta"]["brainControl"]["workspaceId"], "alpha")
        with self.assertRaises(Refusal): self.ledger.prepare(test_core.seed(packet="TEST-002"))
        with self.assertRaises(Refusal): self.fx.command("approve", {"queueId": q["id"], "seedHash": q["seedHash"], "packetDigest": q["packetDigest"]})
        with self.assertRaisesRegex(Refusal, "safe checkpoint"): self.fx.command("brain_resume")
        self.assertEqual(self.ledger.snapshot()["commands"][-1]["id"], stop["id"])
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])

    def test_legacy_state_client_cannot_bypass_an_existing_workspace_pause(self):
        stop = self.fx.stop()
        old = Ledger(self.ledger.root)
        with self.assertRaises(Refusal): old.prepare(test_core.seed())
        with self.assertRaises(Refusal): park(old, self.fx.token, stop["id"], self.fx.checkpoint(stop))
        with self.assertRaises(Refusal): old.submit({"id": "legacy-resume", "kind": "brain_resume", "payload": {}, "expectedRevision": old.snapshot()["meta"]["revision"]})

    def test_idle_empty_workspace_requires_explicit_inventory_then_can_park_and_resume(self):
        stop = self.fx.stop()
        self.assertIn("inventory_missing", self.codes())
        cp = self.checkpoint(stop)
        self.assertTrue(self.ledger.snapshot()["workspacePause"]["readyToPark"])
        saved = park(self.ledger, self.fx.token, stop["id"], cp)
        self.assertEqual(park(self.ledger, self.fx.token, stop["id"], cp), saved)
        state = self.ledger.snapshot()
        self.assertEqual(state["workspacePause"]["status"], "checkpoint_saved")
        self.assertTrue(state["workspacePause"]["canResumeBrain"])
        self.fx.command("brain_resume"); self.ledger.process(self.fx.token)
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertEqual(self.ledger.snapshot()["workspacePause"]["status"], "not_requested")

    def test_worker_and_descendant_checkpoints_are_required_without_releasing_ownership(self):
        worker = self.fx.running(); stop = self.fx.stop()
        evidence = self.evidence(stop, [{"hostId": "local", "threadId": "child", "workerId": None,
            "parent": {"hostId": "local", "threadId": "thread-1"}, "status": "idle"}])
        # Bind the child to the actual fixture worker, not a guessed identity.
        evidence["tasks"][-1]["parent"]["threadId"] = evidence["tasks"][0]["threadId"]
        cp = self.checkpoint(stop, evidence)
        saved = park(self.ledger, self.fx.token, stop["id"], cp)
        current = self.ledger.snapshot()["workers"][0]
        self.assertEqual(current["status"], "running"); self.assertFalse(current["archived"])
        self.assertEqual(current["id"], worker["id"])
        self.assertEqual(Ledger(self.ledger.root).snapshot()["meta"]["brainControl"]["checkpoint"], saved)

    def test_partial_stale_running_or_missing_checkpoint_evidence_never_parks(self):
        self.fx.running(); stop = self.fx.stop()
        for mutate, expected in (
            (lambda d: d.update(complete=False), "inventory_incomplete"),
            (lambda d: d.update(includesDescendants=False), "inventory_incomplete"),
            (lambda d: d["tasks"][0].update(status="running"), "task_not_idle"),
            (lambda d: d["tasks"][0].update(observedAt=time.time() - 500), "task_observation_stale"),
            (lambda d: d["tasks"][0].update(checkpointArtifactId=None), "task_checkpoint_missing")):
            evidence = self.evidence(stop); mutate(evidence)
            cp = self.checkpoint(stop, evidence)
            self.assertIn(expected, self.codes())
            with self.assertRaises(Refusal): park(self.ledger, self.fx.token, stop["id"], cp)

    def test_completed_after_request_or_disappeared_worker_stays_in_pause_scope(self):
        worker = self.fx.running(); stop = self.fx.stop()
        with self.ledger.tx() as db:
            w = self.ledger.get(db, "workers", worker["id"])
            w.update(status="complete", completedAt=time.time()); self.ledger.put(db, "workers", w["id"], w)
        evidence = self.evidence(stop); evidence["tasks"] = []
        self.record(stop, evidence)
        self.assertIn("worker_observation_missing", self.codes())
        self.assertIn("retained_native_missing", self.codes())
        with self.ledger.tx() as db: db.execute("DELETE FROM workers WHERE id=?", (worker["id"],))
        self.assertIn("retained_worker_missing", self.codes())

    def test_changed_native_binding_cannot_erase_prior_task(self):
        worker = self.fx.running(); stop = self.fx.stop()
        with self.ledger.tx() as db:
            w = self.ledger.get(db, "workers", worker["id"]); w["threadId"] = "replacement"
            self.ledger.put(db, "workers", w["id"], w)
        self.record(stop)
        self.assertIn("retained_native_missing", self.codes())

    def test_old_hash_or_worker_source_drift_refuses_checkpoint(self):
        worker = self.fx.running(); stop = self.fx.stop(); cp = self.checkpoint(stop)
        self.record(stop)
        with self.assertRaisesRegex(Refusal, "evidence hash"): park(self.ledger, self.fx.token, stop["id"], cp)
        cp["pauseEvidenceHash"] = self.ledger.snapshot()["workspacePause"]["evidenceHash"]
        self.ledger.transition(self.fx.token, worker["id"], "blocked", "Fixture state changed")
        self.assertIn("ownership_changed", self.codes())
        with self.assertRaises(Refusal): park(self.ledger, self.fx.token, stop["id"], cp)

    def test_observed_descendant_cannot_disappear_from_later_evidence(self):
        stop = self.fx.stop()
        child = {"hostId": "local", "threadId": "child", "workerId": None, "status": "idle",
                 "parent": {"hostId": "local", "threadId": "brain-fixture"}}
        self.record(stop, self.evidence(stop, [child]))
        with self.assertRaisesRegex(Refusal, "disappear"): self.record(stop)

    def test_foreign_or_cyclic_descendants_are_explicit(self):
        stop = self.fx.stop()
        child = {"hostId": "local", "threadId": "child", "workerId": None, "status": "idle",
                 "parent": {"hostId": "local", "threadId": "other-workspace-brain"}}
        self.record(stop, self.evidence(stop, [child])); self.assertIn("task_ancestry_unresolved", self.codes())
        child["parent"]["threadId"] = "child"
        self.record(stop, self.evidence(stop, [child])); self.assertIn("task_ancestry_unresolved", self.codes())

    def test_checkpoint_artifact_must_match_task_repository_and_post_request_time(self):
        self.fx.running(); stop = self.fx.stop()
        for mutation in (lambda a: a.update(observedAt=1), lambda a: a.update(references=[]), lambda a: a.update(repository="b")):
            evidence = self.evidence(stop); aid = evidence["tasks"][0]["checkpointArtifactId"]
            with self.ledger.tx() as db:
                artifact = self.ledger.get(db, "artifact_versions", aid); mutation(artifact)
                db.execute("UPDATE artifact_versions SET data=? WHERE id=?", (json.dumps(artifact), aid))
            self.record(stop, evidence); self.assertIn("task_checkpoint_missing", self.codes())

    def test_runner_and_uncertain_creation_remain_owned(self):
        q = self.fx.ready(); self.fx.resume(); worker = self.ledger.reserve(self.fx.token, q["id"])
        self.ledger.begin_creation(self.fx.token, worker["id"])
        stop = self.fx.stop(); self.record(stop)
        self.assertIn("worker_effect_inflight", self.codes())
        self.assertEqual(self.ledger.snapshot()["workers"][0]["status"], "starting")

    def test_heartbeat_freshness_and_evidence_expiration(self):
        self.ledger.heartbeat("fixture-hb", "ACTIVE")
        stop = self.fx.stop(); self.record(stop)
        self.assertIn("heartbeat_unconfirmed", self.codes())
        self.ledger.heartbeat("fixture-hb", "PAUSED")
        self.assertNotIn("heartbeat_unconfirmed", self.codes())
        with self.ledger.tx() as db:
            status = workspace_pause.status_in(self.ledger, db, time.time() + 121)
        self.assertIn("inventory_stale", {b["code"] for b in status["blockers"]})
        self.assertIn("heartbeat_unconfirmed", {b["code"] for b in status["blockers"]})

    def test_exact_evidence_retry_and_closed_scope(self):
        stop = self.fx.stop(); evidence = self.evidence(stop)
        saved = self.record(stop, evidence); revision = self.ledger.snapshot()["meta"]["revision"]
        self.assertEqual(self.record(stop, evidence), saved)
        self.assertEqual(self.ledger.snapshot()["meta"]["revision"], revision)
        for edit in (lambda d: d.update(workspaceId="beta"), lambda d: d.update(commandId="old-stop"),
                     lambda d: d.update(complete="yes"), lambda d: d.update(command="arbitrary"),
                     lambda d: d.update(observedAt=float("nan")), lambda d: d.update(observedAt=time.time()+20)):
            changed = copy.deepcopy(evidence); edit(changed)
            with self.assertRaises(ValueError): self.record(stop, changed)

    def test_cli_routes_evidence_and_bounds_input_before_recording(self):
        from orchestrator.cli import main
        stop = self.fx.stop(); evidence = self.evidence(stop)
        path = self.ledger.root.parent / "pause-evidence.json"
        path.write_text(json.dumps(evidence))
        argv = ["orchestrator", "--platform", str(self.registry.root), "--workspace", "alpha",
                "brain-stop-observe", stop["id"], str(path)]
        out = io.StringIO()
        with patch("sys.argv", argv), patch.dict(os.environ, {"ORCHESTRATOR_CONTROLLER_TOKEN": self.fx.token}), contextlib.redirect_stdout(out):
            main()
        self.assertEqual(json.loads(out.getvalue())["documentHash"], self.ledger.snapshot()["workspacePause"]["evidenceHash"])
        revision = self.ledger.snapshot()["meta"]["revision"]
        path.write_text(" " * 512_001)
        with patch("sys.argv", argv), self.assertRaisesRegex(Refusal, "exceeds its bound"):
            main()
        self.assertEqual(revision, self.ledger.snapshot()["meta"]["revision"])

    def test_only_designated_brain_can_record_evidence(self):
        stop = self.fx.stop(); evidence = self.evidence(stop)
        self.ledger.release(self.fx.token, "Fixture handoff")
        other = self.ledger.acquire("unrelated")
        with self.assertRaises(Refusal): workspace_pause.observe(self.ledger, other, stop["id"], evidence)

    def test_reserved_task_without_creation_needs_no_native_checkpoint(self):
        q = self.fx.ready(); self.fx.resume(); worker = self.ledger.reserve(self.fx.token, q["id"])
        stop = self.fx.stop(); cp = self.checkpoint(stop)
        park(self.ledger, self.fx.token, stop["id"], cp)
        self.assertEqual(self.ledger.snapshot()["workers"][0]["id"], worker["id"])
        self.assertEqual(self.ledger.snapshot()["workers"][0]["status"], "reserved")

    def test_pause_supersedes_unreceived_resume_and_old_evidence_cannot_cross_requests(self):
        stop = self.fx.stop(); cp = self.checkpoint(stop)
        park(self.ledger, self.fx.token, stop["id"], cp)
        old = self.ledger.document(cp["pauseEvidenceHash"])["document"]
        resume = self.fx.command("brain_resume")
        next_stop = self.fx.stop()
        commands = {c["id"]: c for c in self.ledger.snapshot()["commands"]}
        self.assertEqual(commands[resume["id"]]["status"], "rejected")
        with self.assertRaises(Refusal): self.record(next_stop, old)
        with self.assertRaises(Refusal): park(self.ledger, self.fx.token, next_stop["id"], cp)

    def test_subsequent_legacy_stop_keeps_workspace_protocol_after_resume(self):
        stop = self.fx.stop(); cp = self.checkpoint(stop); park(self.ledger, self.fx.token, stop["id"], cp)
        self.fx.command("brain_resume"); self.ledger.process(self.fx.token)
        legacy = Ledger(self.ledger.root)
        legacy.submit({"id": "legacy-new-pause", "kind": "brain_stop", "payload": {}, "expectedRevision": legacy.snapshot()["meta"]["revision"]})
        self.assertEqual(legacy.snapshot()["meta"]["brainControl"]["protocol"], workspace_pause.PROTOCOL)

    def test_concurrent_duplicate_observations_record_once(self):
        stop = self.fx.stop(); evidence = self.evidence(stop)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(workspace_pause.observe, Ledger(self.ledger.root), self.fx.token, stop["id"], evidence) for _ in range(2)]
            first, second = [f.result(timeout=10) for f in futures]
        self.assertEqual(first, second)
        with self.ledger.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE kind='workspace_pause_evidence'").fetchone()[0], 1)

    def test_failed_observation_transaction_keeps_prior_state(self):
        stop = self.fx.stop(); evidence = self.evidence(stop)
        with patch.object(self.ledger, "event", side_effect=RuntimeError("fixture crash")), self.assertRaises(RuntimeError):
            self.record(stop, evidence)
        self.assertIsNone(self.ledger.snapshot()["workspacePause"]["evidenceHash"])
        with self.ledger.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE kind='workspace_pause_evidence'").fetchone()[0], 0)

    def test_parked_receipt_replays_after_controller_handoff_and_stale_evidence(self):
        stop = self.fx.stop(); cp = self.checkpoint(stop); saved = park(self.ledger, self.fx.token, stop["id"], cp)
        self.ledger.release(self.fx.token, "Fixture checkpoint")
        fresh = Ledger(self.ledger.root); token = fresh.acquire("brain-fixture:recovery")
        with patch("orchestrator.brain_control.time.time", return_value=time.time()+1000):
            self.assertEqual(park(fresh, token, stop["id"], cp), saved)

    def test_owned_runner_and_inflight_worker_control_are_visible(self):
        worker = self.fx.running(); self.ledger.transition(self.fx.token, worker["id"], "awaiting_acceptance", "Fixture")
        self.ledger.runner(self.fx.token, worker["id"], "acquire", "Synthetic idle evidence")
        command = self.fx.command("checkpoint", {"workerId": worker["id"]}); self.ledger.process(self.fx.token)
        stop = self.fx.stop(); self.record(stop)
        self.assertTrue({"runner_owned", "worker_control_inflight", "worker_effect_inflight"} <= self.codes())
        self.ledger.acknowledge(self.fx.token, command["id"], True, "Synthetic checkpoint delivered")
        self.ledger.runner(self.fx.token, worker["id"], "release", "Synthetic exit and cleanup")
        self.assertIn("ownership_changed", self.codes())
        cp = self.checkpoint(stop); park(self.ledger, self.fx.token, stop["id"], cp)


if __name__ == "__main__": unittest.main()
