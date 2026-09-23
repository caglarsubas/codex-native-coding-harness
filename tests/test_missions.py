import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid

from orchestrator.core import Ledger, Refusal, digest
from orchestrator.missions import change, read
from orchestrator.workspaces import Registry


def specification(repository="a", mode="exact_owner"):
    return {"goal": "Deliver a bounded fixture", "successCriteria": ["Offline fixture checks pass"],
        "exclusions": ["No live infrastructure"],
        "phase": {"id": "phase-one", "title": "Fixture phase", "objective": "Implement one fixture",
            "checkpoint": "Owner reviews independent evidence before phase two",
            "stopConditions": ["Material plan change", "Budget revision needed"],
            "scope": [{"repository": repository, "allowedPaths": ["src/fixture/**", "tests/test_fixture.py"],
                       "operations": ["edit", "test", "commit", "open_pr"]}]},
        "authority": {"approvalMode": mode, "maxParallelTasks": 2, "maxTasks": 4,
                      "tokenBudget": 100000, "checkpointReserveTokens": 10000}}


def request(operation="save", revision=0, **extra):
    return {"id": str(uuid.uuid4()), "operation": operation, "expectedRevision": revision, **extra}


class MissionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.registry = Registry(self.root / "platform", create=True)
        ledger = Ledger(self.root / "state")
        ledger.initialize({"schemaVersion": 1, "brainId": "brain-a", "repositories": [
            {"id": "a", "path": "/fixture/a", "projectId": "project-a", "ref": "origin/main",
             "mergePolicy": "manual", "policyProfile": "standard"},
            {"id": "harness", "path": "/fixture/harness", "projectId": "project-h", "ref": "origin/main",
             "mergePolicy": "required_checks", "policyProfile": "harness"}]})
        self.registry.register("a", "Project A", ledger.root)
        self.ledger = self.registry.ledger("a")

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, spec=None, revision=0):
        return change(self.ledger, request(spec=spec or specification(), revision=revision))["current"]

    def review(self, current, operation="review"):
        return change(self.ledger, request(operation, current["revision"], documentHash=current["documentHash"], confirmed=True))["current"]

    def test_versioned_review_revoke_and_revision_chain(self):
        first = self.save()
        original = self.ledger.document(first["documentHash"])
        self.assertEqual(digest(original), first["documentHash"])
        reviewed = self.review(first)
        self.assertEqual(reviewed["status"], "reviewed")
        self.assertFalse(reviewed["activation"]["available"])
        revoked = self.review(reviewed, "revoke")
        self.assertEqual(revoked["status"], "revoked")
        second = self.save(revision=revoked["revision"])
        self.assertEqual(second["version"], 2)
        self.assertEqual(second["status"], "draft")
        self.assertEqual(second["document"]["previousHash"], first["documentHash"])
        self.assertEqual(self.ledger.document(first["documentHash"]), original)
        self.assertEqual([r["version"] for r in read(self.ledger)["history"]], [2, 1])
        self.assertEqual(read(self.registry.ledger("a"))["documentHash"], second["documentHash"])

    def test_review_has_no_execution_effect_even_for_delegated_mode(self):
        before = self.ledger.snapshot()
        current = self.save(specification(mode="phase_delegated"))
        self.review(current)
        after = self.ledger.snapshot()
        for name in ("queue", "workers", "commands", "decisions"):
            self.assertEqual(before[name], after[name])
        for name in ("paused", "concurrency", "brainId", "controller", "runner", "heartbeat", "pilotPassed"):
            self.assertEqual(before["meta"][name], after["meta"][name])
        self.assertFalse(self.ledger.document(after["mission"]["receiptHash"])["executionAuthorized"])

    def test_existing_packet_approval_is_not_revoked_by_configuration_review(self):
        from test_core import seed
        q = self.ledger.prepare(seed(profile="standard"))
        self.ledger.submit({"id": "existing-approval", "kind": "approve", "expectedRevision": self.ledger.snapshot()["meta"]["revision"],
                            "payload": {"queueId": q["id"], "seedHash": q["seedHash"], "packetDigest": q["packetDigest"]}})
        before = self.ledger.snapshot()["queue"]
        self.review(self.review(self.save()), "revoke")
        self.assertEqual(before, self.ledger.snapshot()["queue"])

    def test_hashes_and_revisions_are_exact(self):
        first = self.save()
        for body in (request("review", 0, documentHash=first["documentHash"], confirmed=True),
                     request("review", 1, documentHash="a" * 64, confirmed=True),
                     request("review", 1, documentHash=first["documentHash"], confirmed=False)):
            with self.assertRaises(Refusal): change(self.ledger, body)
        self.assertEqual(read(self.ledger)["revision"], 1)
        second = self.save(revision=1)
        with self.assertRaises(Refusal): self.review(first)
        self.assertEqual(read(self.ledger)["documentHash"], second["documentHash"])

    def test_duplicate_id_replays_receipt_not_change(self):
        body = request(spec=specification())
        first = change(self.ledger, body)
        after = self.ledger.snapshot()["meta"]["revision"]
        self.assertEqual(change(self.ledger, body), first)
        self.assertEqual(self.ledger.snapshot()["meta"]["revision"], after)
        self.review(first["current"])
        replay = change(self.ledger, body)
        self.assertEqual(replay["receipt"], first["receipt"])
        self.assertEqual(replay["current"]["status"], "reviewed")
        with self.assertRaisesRegex(Refusal, "reused"):
            change(self.ledger, {**body, "spec": {**specification(), "goal": "Another goal"}})

    def test_review_retry_does_not_restore_revoked_review(self):
        current = self.save()
        body = request("review", 1, documentHash=current["documentHash"], confirmed=True)
        first = change(self.ledger, body)
        self.review(first["current"], "revoke")
        replay = change(self.ledger, body)
        self.assertEqual(replay["receipt"]["status"], "reviewed")
        self.assertEqual(replay["current"]["status"], "revoked")

    def test_concurrent_reviews_have_one_winner(self):
        current = self.save(); outcomes = []
        def submit():
            try: self.review(current); outcomes.append("ok")
            except Refusal: outcomes.append("refused")
        threads = [threading.Thread(target=submit) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(sorted(outcomes), ["ok", "refused"])

    def test_mapping_change_stales_review_without_rewriting_it(self):
        current = self.review(self.save())
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "a"); repo["projectId"] = "new-project"
            self.ledger.put(db, "repos", "a", repo)
        observed = read(self.ledger)
        self.assertEqual(observed["effectiveStatus"], "stale")
        self.assertEqual(observed["status"], "reviewed")
        self.assertEqual(observed["documentHash"], current["documentHash"])
        updated = self.save(revision=current["revision"])
        self.assertEqual(updated["bindingIssues"], [])

    def test_draft_mapping_change_cannot_be_reviewed(self):
        current = self.save()
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "a"); repo["ref"] = "origin/revised"
            self.ledger.put(db, "repos", "a", repo)
        with self.assertRaisesRegex(Refusal, "binding changed"): self.review(current)

    def test_harness_and_manual_merge_policy_cannot_be_weakened(self):
        with self.assertRaisesRegex(Refusal, "Harness"):
            self.save(specification("harness", "phase_delegated"))
        spec = specification(); spec["phase"]["scope"][0]["operations"].append("merge")
        with self.assertRaisesRegex(Refusal, "Manual-merge"): self.save(spec)
        self.assertEqual(read(self.ledger)["version"], 0)
        self.assertEqual(self.save(specification("harness"))["status"], "draft")

    def test_merge_opt_in_is_explicit_and_preserves_repository_policy(self):
        spec = specification(mode="phase_delegated")
        spec["authority"]["mergeMode"] = "brain_exact_pr_v1"
        with self.assertRaisesRegex(Refusal, "exactly one"): self.save(spec)
        spec["phase"]["scope"][0]["operations"].append("merge")
        with self.assertRaisesRegex(Refusal, "Manual-merge"): self.save(spec)
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "a"); repo["mergePolicy"] = "required_checks"
            self.ledger.put(db, "repos", "a", repo)
        current = self.save(spec)
        self.assertEqual(current["document"]["spec"]["authority"]["mergeMode"], "brain_exact_pr_v1")
        self.assertFalse(self.review(current)["activation"]["available"])

    def test_scope_validation(self):
        variants = []
        for path in ("../elsewhere", "/etc/passwd", "**", "*", "./src/a.py", "src//a.py", "src/../a.py", "src/", "src\\a.py"):
            spec = specification(); spec["phase"]["scope"][0]["allowedPaths"] = [path]; variants.append(spec)
        for repo in ("missing", "other-workspace-repo"):
            variants.append(specification(repo))
        for scope in ([], [specification()["phase"]["scope"][0]] * 2):
            spec = specification(); spec["phase"]["scope"] = scope; variants.append(spec)
        for value in ([], ["shell"], ["test", "test"]):
            spec = specification(); spec["phase"]["scope"][0]["operations"] = value; variants.append(spec)
        for spec in variants:
            with self.subTest(spec=spec), self.assertRaises(Refusal): self.save(spec)

    def test_budget_and_schema_validation(self):
        for key, value in (("maxParallelTasks", True), ("maxParallelTasks", 17), ("maxTasks", 1),
                           ("tokenBudget", 0), ("tokenBudget", 1.5), ("tokenBudget", "100"),
                           ("checkpointReserveTokens", 100000), ("checkpointReserveTokens", -1)):
            spec = specification(); spec["authority"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(Refusal): self.save(spec)
        for field in ("goal", "successCriteria", "exclusions", "phase", "authority"):
            spec = specification(); spec.pop(field)
            with self.subTest(field=field), self.assertRaises(Refusal): self.save(spec)
        spec = specification(); spec["nativeArgs"] = {"model": "not-authorized"}
        with self.assertRaises(Refusal): self.save(spec)
        spec = specification(); spec["goal"] = "x" * 33000
        with self.assertRaises(Refusal): self.save(spec)

    def test_brain_can_draft_but_not_review_or_revoke(self):
        token = self.ledger.acquire("brain-a:proposal")
        body = request(spec=specification())
        with self.assertRaises(Refusal): change(self.ledger, body, actor="designated_brain", token="wrong")
        current = change(self.ledger, body, actor="designated_brain", token=token)["current"]
        self.assertEqual(current["document"]["actor"], "designated_brain")
        for op in ("review", "revoke"):
            with self.assertRaisesRegex(Refusal, "Only the authenticated owner"):
                change(self.ledger, request(op, 1, documentHash=current["documentHash"], confirmed=True), actor="designated_brain", token=token)

    def test_wrong_brain_and_unregistered_ledger_cannot_draft(self):
        token = self.ledger.acquire("different-brain:proposal")
        with self.assertRaisesRegex(Refusal, "designated brain"):
            change(self.ledger, request(spec=specification()), actor="designated_brain", token=token)
        with self.assertRaisesRegex(Refusal, "registered workspace"):
            read(Ledger(self.root / "unregistered"))

    def test_stopped_brain_cannot_publish_a_new_proposal(self):
        token = self.ledger.acquire("brain-a:proposal")
        self.ledger.submit({"id": "stop-fixture", "kind": "brain_stop", "expectedRevision": self.ledger.snapshot()["meta"]["revision"], "payload": {}})
        with self.assertRaisesRegex(Refusal, "Stopped brain"):
            change(self.ledger, request(spec=specification()), actor="designated_brain", token=token)

    def test_workspace_isolation_even_with_same_request_id(self):
        other = Ledger(self.root / "other")
        other.initialize({"schemaVersion": 1, "brainId": "brain-b", "repositories": self.ledger.snapshot()["repositories"]})
        self.registry.register("b", "Project B", other.root); other = self.registry.ledger("b")
        body = request(spec=specification())
        a = change(self.ledger, body)["current"]; b = change(other, body)["current"]
        self.assertNotEqual(a["documentHash"], b["documentHash"])
        with self.assertRaises(Refusal): change(other, request("review", 1, documentHash=a["documentHash"], confirmed=True))
        with self.assertRaises(Refusal): other.document(a["documentHash"])
        self.assertNotIn('"/fixture/a"', json.dumps(a))

    def test_history_is_bounded_and_previous_documents_remain_readable(self):
        for i in range(22): self.save(revision=i)
        result = read(self.ledger)
        self.assertEqual(len(result["history"]), 20)
        older = self.ledger.document(result["olderDocumentHash"])
        self.assertEqual(older["version"], 2)
        self.assertEqual(self.ledger.document(older["previousHash"])["version"], 1)

    def test_cli_read_requires_explicit_workspace_and_has_no_owner_review_command(self):
        base = [sys.executable, "-m", "orchestrator.cli", "--platform", str(self.registry.root)]
        result = subprocess.run([*base, "mission-state"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        result = subprocess.run([*base, "--workspace", "a", "mission-state"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)["activation"]["available"])
        result = subprocess.run([*base, "--workspace", "a", "mission-review"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
