import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid

from orchestrator.core import AXES, Ledger, Refusal, digest, validate_seed


def seed(repo="a", packet="TEST-001", profile="harness"):
    return {"schemaVersion": 1, "repository": repo, "policyProfile": profile, "packetId": packet,
        "packetDigest": "a" * 64, "packetPath": "task-packets/TEST-001.yaml", "catalogCommit": "b" * 40,
        "baseSHA": "c" * 40, "branch": "codex/test-001", "objective": "Write a fixture", "rationale": "Verify bounded inheritance",
        "allowedPaths": ["src/example.py"], "contracts": ["No external effects"], "predecessors": [], "locks": [],
        "execution": {"wrapperArgv": ["./ci/verify-offline.sh"], "prefetchCommands": [],
            "offlineAcceptanceCommands": [["python3", "-m", "unittest"]],
            "isolation": "OS_ENFORCED_DENY_ALL_OUTBOUND" if profile == "harness" else "REPOSITORY_POLICY"},
        "acceptance": ["Fixture tests pass"], "stopConditions": ["Scope changes"], "completionAxes": ["source", "ci"]}


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.temp.name) / "state")
        self.config = {"schemaVersion": 1, "brainId": "brain-fixture", "repositories": [
            {"id": name, "path": "/fixture/" + name, "projectId": "project-" + name, "ref": "origin/main", "mergePolicy": "manual", "policyProfile": "harness"} for name in ("a", "b", "c")]}
        self.ledger.initialize(self.config)
        self.token = self.ledger.acquire("test")

    def tearDown(self):
        self.temp.cleanup()

    def command(self, kind, payload=None):
        return self.ledger.submit({"id": str(uuid.uuid4()), "kind": kind, "expectedRevision": self.ledger.snapshot()["meta"]["revision"], "payload": payload or {}})

    def ready(self, repo="a", packet="TEST-001"):
        q = self.ledger.prepare(seed(repo, packet))
        self.command("approve", {"queueId": q["id"], "seedHash": q["seedHash"], "packetDigest": q["packetDigest"]})
        self.ledger.preflight(self.token, q["id"], {"seedHash": q["seedHash"], "packetDigest": q["packetDigest"], "baseSHA": "c" * 40,
            "projectId": "project-" + repo, "checks": {key: True for key in ("packetCurrent", "baseCurrent", "predecessorsVerified", "locksVerified", "noActiveDuplicate", "setupSafe", "policyReviewed", "runnerAvailable", "scopeApproved")}, "evidence": ["fixture-observation"]})
        return q

    def resume(self):
        self.command("resume")
        self.ledger.process(self.token)

    def running(self, repo="a", packet="TEST-001"):
        q = self.ready(repo, packet)
        self.resume()
        w = self.ledger.reserve(self.token, q["id"])
        action = self.ledger.begin_creation(self.token, w["id"])
        self.assertEqual(action["target"]["environment"], {"type": "worktree"})
        self.ledger.bind(self.token, w["id"], thread_id=str(uuid.uuid4()))
        return w

    def completion(self, w):
        return {"schemaVersion": 1, "seedHash": w["seedHash"], "commit": "f" * 40,
            "changedPaths": ["src/example.py"], "pr": "https://github.com/example/repo/pull/1",
            "evidence": {axis: {"status": "verified" if axis in ("source", "ci") else "unverified", "reference": "fixture-reviewed-exact-sha" if axis in ("source", "ci") else None} for axis in AXES},
            "preserved": True, "reviewReference": "independent fixture review"}

    def finish(self, w):
        self.ledger.transition(self.token, w["id"], "verifying", "Observed fixture result")
        self.ledger.complete(self.token, w["id"], self.completion(w))

    def test_default_paused_and_pilot_limit(self):
        q = self.ready()
        with self.assertRaisesRegex(Refusal, "paused"):
            self.ledger.reserve(self.token, q["id"])
        self.assertEqual(self.ledger.snapshot()["meta"]["concurrency"], 1)

    def test_unknown_ledger_version_refuses_reopen(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db,"meta",1); meta["schemaVersion"] = 99
            self.ledger.put(db,"meta",1,meta)
        with self.assertRaisesRegex(Refusal,"Unsupported ledger version"):
            Ledger(self.ledger.root)

    def test_no_approval_no_dispatch(self):
        q = self.ledger.prepare(seed()); self.resume()
        with self.assertRaises(Refusal): self.ledger.reserve(self.token, q["id"])

    def test_new_pause_supersedes_queued_resume(self):
        self.command("resume")
        self.command("pause")
        self.ledger.process(self.token)
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertEqual(self.ledger.snapshot()["commands"][0]["status"], "rejected")

    def test_completion_contract_cannot_skip_ci(self):
        s = seed(); s["completionAxes"] = ["source"]
        with self.assertRaises(Refusal): self.ledger.prepare(s)

    def test_stale_revision_and_idempotency(self):
        rev = self.ledger.snapshot()["meta"]["revision"]
        c = {"id": str(uuid.uuid4()), "kind": "pause", "expectedRevision": rev, "payload": {}}
        first = self.ledger.submit(c)
        self.assertEqual(self.ledger.submit(c), first)
        with self.assertRaises(Refusal): self.ledger.submit({**c, "kind": "resume"})
        with self.assertRaisesRegex(Refusal, "State changed"): self.ledger.submit({**c, "id": str(uuid.uuid4())})

    def test_changed_seed_invalidates_approval(self):
        q = self.ready(); updated = seed(); updated["rationale"] = "Different rationale"
        new = self.ledger.prepare(updated)
        self.assertIsNone(new["approval"])
        self.assertNotEqual(new["seedHash"], q["seedHash"])

    def test_pending_identity_and_uncertain_creation_cannot_retry(self):
        q = self.ready(); self.resume(); w = self.ledger.reserve(self.token, q["id"])
        self.ledger.begin_creation(self.token, w["id"])
        with self.assertRaisesRegex(Refusal, "already attempted"): self.ledger.begin_creation(self.token, w["id"])
        self.ledger.bind(self.token, w["id"], client_id="pending-client")
        current = self.ledger.snapshot()["workers"][0]
        self.assertIsNone(current["threadId"]); self.assertEqual(current["status"], "starting")
        with self.assertRaises(Refusal): self.ledger.prepare(seed())
        self.ledger.bind(self.token, w["id"], thread_id="resolved-native")
        self.assertEqual(self.ledger.snapshot()["workers"][0]["status"], "running")

    def test_pause_before_creation_blocks(self):
        q = self.ready(); self.resume(); w = self.ledger.reserve(self.token, q["id"]); self.command("pause")
        with self.assertRaises(Refusal): self.ledger.begin_creation(self.token, w["id"])
        self.assertEqual(self.ledger.snapshot()["workers"][0]["status"], "reserved")

    def test_pause_after_start_preserves_inflight(self):
        w = self.running(); self.command("pause")
        self.assertEqual(self.ledger.snapshot()["workers"][0]["status"], "running")

    def test_two_controller_exclusion(self):
        other = Ledger(self.ledger.root)
        with self.assertRaises(Refusal): other.acquire("second")
        with self.assertRaises(Refusal): other.release("wrong", "fake")
        self.assertNotIn(self.token, json.dumps(self.ledger.snapshot()))

    def test_crash_recovery_keeps_worker_ownership(self):
        w = self.running()
        self.ledger.recover("test", "Native task observed still active; only controller process is gone")
        state = Ledger(self.ledger.root).snapshot()
        self.assertTrue(state["meta"]["paused"])
        self.assertEqual(state["workers"][0]["id"], w["id"])
        self.assertIsNone(state["meta"]["controller"])

    def test_concurrent_duplicate_reservation(self):
        q = self.ready(); self.resume(); results = []
        def reserve():
            try: results.append(Ledger(self.ledger.root).reserve(self.token, q["id"])["id"])
            except Refusal: results.append("refused")
        threads = [threading.Thread(target=reserve) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(results.count("refused"), 1)
        self.assertEqual(len(self.ledger.snapshot()["workers"]), 1)

    def test_repository_ownership_and_two_worker_limit_after_pilot(self):
        pilot = self.running(); self.finish(pilot); self.ledger.pilot(self.token, pilot["id"], "Fresh-worker native pilot independently verified")
        first = self.running("a", "TEST-002")
        same = self.ready("a", "TEST-003")
        with self.assertRaisesRegex(Refusal, "Repository"): self.ledger.reserve(self.token, same["id"])
        second = self.running("b")
        third = self.ready("c")
        with self.assertRaisesRegex(Refusal, "capacity"): self.ledger.reserve(self.token, third["id"])
        for w in (first, second): self.ledger.transition(self.token, w["id"], "awaiting_acceptance", "Ready")
        self.ledger.runner(self.token, first["id"], "acquire", "Runner independently observed idle")
        with self.assertRaises(Refusal): self.ledger.runner(self.token, second["id"], "acquire", "Idle assertion cannot bypass ledger")
        with self.assertRaises(Refusal): self.ledger.transition(self.token, first["id"], "blocked", "Process still in flight")
        self.ledger.runner(self.token, first["id"], "release", "Process exited and cleanup independently observed")
        self.ledger.runner(self.token, second["id"], "acquire", "Runner idle")

    def test_false_or_missing_evidence_cannot_complete(self):
        w = self.running(); self.ledger.transition(self.token, w["id"], "verifying", "Worker result received")
        envelope = self.completion(w); envelope["evidence"]["ci"]["status"] = "unverified"
        with self.assertRaises(Refusal): self.ledger.complete(self.token, w["id"], envelope)
        envelope = self.completion(w); envelope["changedPaths"] = ["not-allowed.py"]
        with self.assertRaises(Refusal): self.ledger.complete(self.token, w["id"], envelope)

    def test_archive_requires_native_acknowledgment(self):
        w = self.running()
        with self.assertRaises(Refusal): self.command("archive", {"workerId": w["id"]})
        self.finish(w)
        self.assertEqual(self.ledger.snapshot()["queue"][0]["status"], "complete")
        self.assertEqual(self.ledger.snapshot()["delivery"]["aggregate"]["completed"], 1)
        cmd = self.command("archive", {"workerId": w["id"]})
        actions = self.ledger.process(self.token)
        self.assertEqual(actions[0]["kind"], "archive")
        self.assertFalse(self.ledger.snapshot()["workers"][0]["archived"])
        self.ledger.acknowledge(self.token, cmd["id"], True, "Native archive result verified")
        self.assertTrue(self.ledger.snapshot()["workers"][0]["archived"])

    def test_no_progress_is_bounded(self):
        w = self.running()
        self.ledger.transition(self.token, w["id"], "verifying", "First unsuccessful cycle", False)
        self.ledger.transition(self.token, w["id"], "running", "Second unsuccessful cycle", False)
        self.assertEqual(self.ledger.snapshot()["workers"][0]["status"], "blocked")

    def test_profile_cannot_be_downgraded(self):
        with self.assertRaises(Refusal): self.ledger.prepare(seed(profile="standard"))
        config = copy.deepcopy(self.config); config["repositories"][0]["policyProfile"] = "standard"
        with self.assertRaises(Refusal): self.ledger.initialize(config)

    def test_path_escape_and_absolute_source_context_refused(self):
        for path in ("../elsewhere.py", "/etc/passwd", "src/../../other"):
            s = seed(); s["allowedPaths"] = [path]
            with self.assertRaises(Refusal): validate_seed(s)
        s = seed(); s["contracts"].append("Read /Users/someone/warm-checkout")
        with self.assertRaises(Refusal): validate_seed(s)

    def test_missing_or_expired_preflight_refuses(self):
        q = self.ready(); self.resume()
        with self.ledger.tx() as db:
            stored = self.ledger.get(db, "queue", q["id"]); stored["preflight"]["at"] = 0
            db.execute("UPDATE queue SET data=? WHERE id=?", (json.dumps(stored), q["id"]))
        with self.assertRaisesRegex(Refusal, "Fresh"): self.ledger.reserve(self.token, q["id"])


if __name__ == "__main__": unittest.main()
