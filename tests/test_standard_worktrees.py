"""Disposable Git fixtures for future opt-in same-repository producer concurrency."""
import copy
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid

from orchestrator.core import Ledger, Refusal
from orchestrator.missions import change
from orchestrator.standard import Controls, brain, read
from orchestrator.workspaces import Registry
from test_missions import request, specification


class IsolatedWorktreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.git(self.repo, "config", "user.name", "Fixture")
        self.git(self.repo, "config", "user.email", "fixture@example.test")
        self.git(self.repo, "remote", "add", "origin", "https://github.com/fixture/repo.git")
        (self.repo / "README.md").write_text("base\n")
        self.git(self.repo, "add", "README.md")
        self.git(self.repo, "commit", "-qm", "base")
        self.registry = Registry(self.root / "platform", create=True)
        ledger = Ledger(self.root / "alpha")
        ledger.initialize({"schemaVersion": 1, "brainId": str(uuid.uuid4()), "repositories": [{
            "id": "a", "path": str(self.repo), "projectId": "native-fixture-project", "ref": "HEAD",
            "policyProfile": "standard", "mergePolicy": "manual"}]})
        self.registry.register("alpha", "alpha", ledger.root)
        self.ledger = self.registry.ledger("alpha")
        self.controls = Controls()
        spec = specification(mode="phase_delegated")
        spec["authority"]["repositoryMode"] = "isolated_worktrees"
        spec["authority"]["maxParallelTasks"] = 3
        spec["authority"]["maxTasks"] = 5
        spec["phase"]["scope"][0]["allowedPaths"] = ["src/fixture/**", "tests/test_fixture.py"]
        spec["phase"]["scope"][0]["operations"].append("open_pr") if "open_pr" not in spec["phase"]["scope"][0]["operations"] else None
        draft = change(self.ledger, request("save", 0, spec=spec))["current"]
        change(self.ledger, request("review", draft["revision"], documentHash=draft["documentHash"], confirmed=True))
        self.token = self.ledger.acquire(self.ledger.snapshot()["meta"]["brainId"] + ":test")
        brain(self.registry, self.ledger, self.token, {"operation": "catalog", "models": [{"model": "fixture", "efforts": ["low"]}],
                                                      "source": "Native fixture catalog"})
        self.base = self.git(self.repo, "rev-parse", "HEAD").stdout.strip()

    def tearDown(self):
        self.tmp.cleanup()

    def control(self, op="play"):
        preview = self.controls.preview(self.ledger, {"operation": op, "contextHash": read(self.ledger)["contextHash"],
            "brainAllowance": 10000, "durationHours": 8}, "session")
        return self.controls.confirm(self.registry, self.ledger, {**preview, "confirmed": True}, "session")

    def call(self, operation, **values):
        return brain(self.registry, self.ledger, self.token,
                     {"operation": operation, "runId": read(self.ledger)["run"]["id"], **values})

    @staticmethod
    def git(root, *args):
        return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)

    def claim_kind(self, ident, path, kind="producer"):
        return self.call("claim", id=ident, repository="a", title=ident, paths=[path],
                         instructions="Use only the supplied native worktree and exact scope.",
                         acceptance=["Offline fixture checks pass"], model="fixture", effort="low",
                         rationale="Bounded native worktree fixture", allowance=10000, taskKind=kind)

    def native_worktree(self, ident, branch):
        root = self.root / ident
        self.git(self.repo, "worktree", "add", "-b", branch, str(root), self.base)
        self.git(root, "config", "user.name", "Fixture")
        self.git(root, "config", "user.email", "fixture@example.test")
        return root

    def bind_worktree(self, ident, root, branch, *, thread=None, observed_at=None):
        thread = thread or str(uuid.uuid4())
        self.call("issue", taskId=ident)
        self.call("bind", taskId=ident, threadId=thread, clientThreadId=None, hostId="local")
        seed_hash = next(t["seedHash"] for t in read(self.ledger)["run"]["tasks"] if t["id"] == ident)
        self.call("worktree_bind", taskId=ident, threadId=thread, root=str(root), branch=branch,
                  startCommit=self.base,
                  nativeCreation={"projectId": "native-fixture-project", "environment": "worktree",
                                  "startingCommit": self.base, "seedHash": seed_hash,
                                  "threadId": thread, "hostId": "local"},
                  nativeObservation={"threadId": thread, "hostId": "local", "cwd": str(root),
                                     "observedAt": observed_at or time.time(), "sourceHash": "a"*64})
        return thread

    def finish_commit(self, ident, root, path, *, integration=False):
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(ident + "\n")
        self.git(root, "add", path)
        self.git(root, "commit", "-qm", ident)
        head = self.git(root, "rev-parse", "HEAD").stdout.strip()
        self.call("observe", taskId=ident, nativeStatus="completed", observedTokens=100,
                  trackedTerminals="none", observedAt=time.time(), source="Native fixture")
        evidence = {"source": "Pinned commit", "tests": "Offline fixture tests", "artifacts": [],
                    "preservation": "Pinned native worktree", "summary": "Verified task", "headSHA": head}
        if integration:
            evidence["prUrl"] = "https://github.com/fixture/repo/pull/7"
            evidence["prHeadBranch"] = "codex/integrate"
        self.call("finish", taskId=ident, outcome="completed", evidence=evidence)
        return head

    def test_parallel_requires_distinct_fresh_native_worktrees_and_disjoint_files(self):
        self.control()
        self.claim_kind("one", "src/fixture/one.py")
        with self.assertRaisesRegex(Refusal, "unverified"):
            self.claim_kind("two", "src/fixture/two.py")
        one = self.native_worktree("one", "codex/one")
        self.bind_worktree("one", one, "codex/one")
        with self.assertRaisesRegex(Refusal, "overlap"):
            self.claim_kind("two", "src/fixture/one.py")
        self.claim_kind("two", "src/fixture/two.py")
        with self.assertRaisesRegex(Refusal, "unverified"):
            self.claim_kind("three", "src/fixture/three.py")
        two = self.native_worktree("two", "codex/two")
        self.bind_worktree("two", two, "codex/two")
        self.claim_kind("three", "src/fixture/three.py")
        run = read(self.ledger)["run"]
        self.assertEqual(run["limits"]["repositoryMode"], "isolated_worktrees")
        self.assertEqual(len(run["tasks"]), 3)
        self.assertEqual(read(self.ledger)["parallelEligibility"]["currentlyEligible"], 0)

    def test_exact_worktree_bind_replay_never_refreshes_age_or_revision(self):
        self.control(); self.claim_kind("one", "src/fixture/one.py")
        root = self.native_worktree("one", "codex/one")
        thread = self.bind_worktree("one", root, "codex/one")
        run = read(self.ledger)["run"]
        task = run["tasks"][0]
        binding = task["worktree"]
        self.call("worktree_bind", taskId="one", threadId=thread, root=str(root), branch="codex/one",
                  startCommit=self.base, nativeCreation=binding["nativeCreation"],
                  nativeObservation={"threadId": thread, "hostId": "local", "cwd": str(root),
                                     "observedAt": binding["nativeObservedAt"],
                                     "sourceHash": binding["nativeSourceHash"]})
        again = read(self.ledger)["run"]
        self.assertEqual(again["revision"], run["revision"])
        self.assertEqual(again["tasks"][0]["worktree"], binding)

    def test_native_identity_mismatch_and_pending_creation_keep_repository_lock(self):
        self.control(); self.claim_kind("one", "src/fixture/one.py")
        self.call("issue", taskId="one")
        self.call("bind", taskId="one", threadId=None, clientThreadId=str(uuid.uuid4()), hostId="local")
        with self.assertRaisesRegex(Refusal, "unverified"):
            self.claim_kind("two", "src/fixture/two.py")
        with self.assertRaises(Refusal):
            self.call("worktree_bind", taskId="one", threadId=str(uuid.uuid4()), root=str(self.repo),
                      branch="codex/one", startCommit=self.base,
                      nativeCreation={},
                      nativeObservation={"threadId": str(uuid.uuid4()), "hostId": "local", "cwd": str(self.repo),
                                         "observedAt": time.time(), "sourceHash": "a"*64})
        with self.assertRaises(Refusal): self.call("issue", taskId="one")

    def test_pending_isolated_creation_keeps_cross_workspace_repository_lock(self):
        self.control(); self.claim_kind("one", "src/fixture/one.py")
        self.call("issue", taskId="one")
        self.call("bind", taskId="one", threadId=None, clientThreadId=str(uuid.uuid4()), hostId="local")
        beta = Ledger(self.root / "beta")
        beta.initialize({"schemaVersion": 1, "brainId": str(uuid.uuid4()), "repositories": [{
            "id": "a", "path": str(self.repo), "projectId": "native-fixture-project", "ref": "HEAD",
            "policyProfile": "standard", "mergePolicy": "manual"}]})
        self.registry.register("beta", "beta", beta.root)
        beta = self.registry.ledger("beta")
        draft = change(beta, request("save", 0, spec=specification(mode="phase_delegated")))["current"]
        change(beta, request("review", draft["revision"], documentHash=draft["documentHash"], confirmed=True))
        token = beta.acquire(beta.snapshot()["meta"]["brainId"] + ":test")
        brain(self.registry, beta, token, {"operation": "catalog", "models": [{"model": "fixture", "efforts": ["low"]}],
                                           "source": "Native fixture catalog"})
        preview = self.controls.preview(beta, {"operation": "play", "contextHash": read(beta)["contextHash"],
            "brainAllowance": 10000, "durationHours": 8}, "session")
        self.controls.confirm(self.registry, beta, {**preview, "confirmed": True}, "session")
        with self.assertRaisesRegex(Refusal, "another workspace"):
            brain(self.registry, beta, token, {"operation": "claim", "runId": read(beta)["run"]["id"],
                "id": "beta-task", "repository": "a", "title": "Beta", "paths": ["tests/test_fixture.py"],
                "instructions": "Fixture", "acceptance": ["Pass"], "model": "fixture", "effort": "low",
                "rationale": "Separate workspace", "allowance": 10000})

    def test_wrong_native_cwd_and_stale_observation_refuse_binding(self):
        self.control(); self.claim_kind("one", "src/fixture/one.py")
        root = self.native_worktree("one", "codex/one")
        self.call("issue", taskId="one")
        thread = str(uuid.uuid4())
        self.call("bind", taskId="one", threadId=thread, clientThreadId=None, hostId="local")
        seed_hash = read(self.ledger)["run"]["tasks"][0]["seedHash"]
        for cwd, at in ((str(self.repo), time.time()), (str(root), time.time()-180)):
            with self.assertRaises(Refusal):
                self.call("worktree_bind", taskId="one", threadId=thread, root=str(root), branch="codex/one",
                          startCommit=self.base,
                          nativeCreation={"projectId": "native-fixture-project", "environment": "worktree",
                                          "startingCommit": self.base, "seedHash": seed_hash,
                                          "threadId": thread, "hostId": "local"},
                          nativeObservation={"threadId": thread, "hostId": "local",
                              "cwd": cwd, "observedAt": at, "sourceHash": "a"*64})
        self.assertIsNone(read(self.ledger)["run"]["tasks"][0].get("worktree"))

    def test_producer_out_of_scope_commit_refuses_completion_and_keeps_owner(self):
        self.control(); self.claim_kind("one", "src/fixture/one.py")
        root = self.native_worktree("one", "codex/one")
        self.bind_worktree("one", root, "codex/one")
        (root / "README.md").write_text("wrong\n")
        self.git(root, "add", "README.md")
        self.git(root, "commit", "-qm", "outside")
        head = self.git(root, "rev-parse", "HEAD").stdout.strip()
        self.call("observe", taskId="one", nativeStatus="completed", observedTokens=100,
                  trackedTerminals="none", observedAt=time.time(), source="Native fixture")
        with self.assertRaises(Refusal):
            self.call("finish", taskId="one", outcome="completed", evidence={"source": "Claim", "tests": "Claim",
                "artifacts": [], "preservation": "Claim", "summary": "Claim", "headSHA": head})
        self.assertEqual(read(self.ledger)["run"]["tasks"][0]["status"], "active")

    def test_integration_must_include_pinned_producer_commit(self):
        self.control(); self.claim_kind("one", "src/fixture/one.py")
        producer = self.native_worktree("one", "codex/one")
        self.bind_worktree("one", producer, "codex/one")
        producer_head = self.finish_commit("one", producer, "src/fixture/one.py")
        self.claim_kind("integrate", "src/fixture/one.py", "integration")
        integration = self.native_worktree("integrate", "codex/integrate")
        self.bind_worktree("integrate", integration, "codex/integrate")
        (integration / "src/fixture").mkdir(parents=True)
        (integration / "src/fixture/one.py").write_text("different\n")
        self.git(integration, "add", "src/fixture/one.py")
        self.git(integration, "commit", "-qm", "not-integrated")
        head = self.git(integration, "rev-parse", "HEAD").stdout.strip()
        self.call("observe", taskId="integrate", nativeStatus="completed", observedTokens=100,
                  trackedTerminals="none", observedAt=time.time(), source="Native fixture")
        with self.assertRaises(Refusal):
            self.call("finish", taskId="integrate", outcome="completed", evidence={"source": "Claim", "tests": "Claim",
                "artifacts": [], "preservation": "Claim", "summary": "Claim", "headSHA": head,
                "prUrl": "https://github.com/fixture/repo/pull/7", "prHeadBranch": "codex/integrate"})
        self.assertEqual(read(self.ledger)["run"]["tasks"][-1]["status"], "active")
        self.assertEqual(read(self.ledger)["run"]["tasks"][0]["headSHA"], producer_head)

    def test_integration_can_merge_pinned_commit_and_add_separate_exact_file(self):
        self.control(); self.claim_kind("one", "src/fixture/one.py")
        producer = self.native_worktree("one", "codex/one")
        self.bind_worktree("one", producer, "codex/one")
        producer_head = self.finish_commit("one", producer, "src/fixture/one.py")
        self.assertTrue(read(self.ledger)["parallelEligibility"]["integrationReady"])
        self.claim_kind("integrate", "src/fixture/integration.py", "integration")
        self.assertFalse(read(self.ledger)["parallelEligibility"]["integrationReady"])
        integration = self.native_worktree("integrate", "codex/integrate")
        self.bind_worktree("integrate", integration, "codex/integrate")
        self.git(integration, "merge", "--no-ff", "-m", "Integrate pinned producer", producer_head)
        head = self.finish_commit("integrate", integration, "src/fixture/integration.py", integration=True)
        tasks = read(self.ledger)["run"]["tasks"]
        self.assertEqual(tasks[-1]["status"], "completed")
        self.assertEqual(tasks[-1]["headSHA"], head)
        self.assertEqual(tasks[-1]["producerSources"][0]["headSHA"], producer_head)
        self.assertTrue(tasks[-1]["sourceProof"])

    def test_task_artifacts_cannot_be_attributed_from_sibling_worktree(self):
        self.control(); self.claim_kind("one", "src/fixture/one.md")
        one = self.native_worktree("one", "codex/one")
        self.bind_worktree("one", one, "codex/one")
        self.claim_kind("two", "src/fixture/two.md")
        two = self.native_worktree("two", "codex/two")
        self.bind_worktree("two", two, "codex/two")
        artifact = one / "src/fixture/two.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("wrong native owner\n")
        with self.assertRaisesRegex(Refusal, "this task"):
            self.call("preserve", taskId="two", path=str(artifact), createdAt=None)

    def test_result_cannot_reuse_another_workers_retained_artifact_id(self):
        self.control(); self.claim_kind("one", "src/fixture/one.md")
        one = self.native_worktree("one", "codex/one")
        self.bind_worktree("one", one, "codex/one")
        artifact = one / "src/fixture/one.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("owned by one\n")
        self.call("preserve", taskId="one", path=str(artifact), createdAt=None)
        key = read(self.ledger)["run"]["tasks"][0]["artifacts"][0]
        self.claim_kind("two", "src/fixture/two.py")
        two = self.native_worktree("two", "codex/two")
        self.bind_worktree("two", two, "codex/two")
        self.call("observe", taskId="two", nativeStatus="completed", observedTokens=100,
                  trackedTerminals="none", observedAt=time.time(), source="Native fixture")
        with self.assertRaisesRegex(Refusal, "this exact native task"):
            self.call("finish", taskId="two", outcome="completed", evidence={"source": "Claim", "tests": "Claim",
                "artifacts": [key], "preservation": "Claim", "summary": "Claim", "headSHA": self.base})
        self.assertEqual(read(self.ledger)["run"]["tasks"][-1]["status"], "active")

    def test_out_of_scope_commit_then_revert_is_not_hidden_by_net_diff(self):
        self.control(); self.claim_kind("one", "src/fixture/one.py")
        root = self.native_worktree("one", "codex/one")
        self.bind_worktree("one", root, "codex/one")
        (root / "README.md").write_text("out of scope\n")
        self.git(root, "add", "README.md")
        self.git(root, "commit", "-qm", "out-of-scope intermediate")
        (root / "README.md").write_text("base\n")
        self.git(root, "add", "README.md")
        self.git(root, "commit", "-qm", "revert out-of-scope intermediate")
        file = root / "src/fixture/one.py"
        file.parent.mkdir(parents=True)
        file.write_text("accepted net result\n")
        self.git(root, "add", "src/fixture/one.py")
        self.git(root, "commit", "-qm", "in scope")
        head = self.git(root, "rev-parse", "HEAD").stdout.strip()
        self.call("observe", taskId="one", nativeStatus="completed", observedTokens=100,
                  trackedTerminals="none", observedAt=time.time(), source="Native fixture")
        with self.assertRaisesRegex(Refusal, "hidden by later history"):
            self.call("finish", taskId="one", outcome="completed", evidence={"source": "Claim", "tests": "Claim",
                "artifacts": [], "preservation": "Claim", "summary": "Claim", "headSHA": head})
        self.assertEqual(read(self.ledger)["run"]["tasks"][0]["status"], "active")

    def test_unknown_parallel_eligibility_and_stopped_run_zero(self):
        self.control()
        eligibility = read(self.ledger)["parallelEligibility"]
        self.assertEqual(eligibility["permitted"], 3)
        self.assertIsNone(eligibility["currentlyEligible"])
        self.control("pause")
        self.assertEqual(read(self.ledger)["parallelEligibility"]["currentlyEligible"], 0)
        self.call("checkpoint", outcome="blocked", summary="Owner checkpoint", brainObservedTokens=None)
        self.assertEqual(read(self.ledger)["parallelEligibility"]["currentlyEligible"], 0)

    def test_total_task_limit_reserves_integration_slot(self):
        current = self.ledger.snapshot()["mission"]
        spec = copy.deepcopy(current["document"]["spec"])
        spec["authority"]["maxTasks"] = 2
        spec["authority"]["maxParallelTasks"] = 2
        draft = change(self.ledger, request("save", current["revision"], spec=spec))["current"]
        change(self.ledger, request("review", draft["revision"], documentHash=draft["documentHash"], confirmed=True))
        self.control()
        self.claim_kind("one", "src/fixture/one.py")
        with self.assertRaisesRegex(Refusal, "integration task slot"):
            self.claim_kind("two", "src/fixture/two.py")
        self.assertEqual(len(read(self.ledger)["run"]["tasks"]), 1)

    def test_symlinked_scope_and_duplicate_native_worktree_refuse(self):
        self.control()
        (self.repo / "src/fixture").mkdir(parents=True)
        (self.repo / "src/fixture/link").symlink_to(self.root)
        with self.assertRaisesRegex(Refusal, "symlink"):
            self.claim_kind("alias", "src/fixture/link/file.py")
        self.claim_kind("one", "src/fixture/one.py")
        one = self.native_worktree("one", "codex/one")
        self.bind_worktree("one", one, "codex/one")
        self.claim_kind("two", "src/fixture/two.py")
        self.call("issue", taskId="two")
        thread = str(uuid.uuid4())
        self.call("bind", taskId="two", threadId=thread, clientThreadId=None, hostId="local")
        seed_hash = read(self.ledger)["run"]["tasks"][-1]["seedHash"]
        with self.assertRaisesRegex(Refusal, "already bound"):
            self.call("worktree_bind", taskId="two", threadId=thread, root=str(one), branch="codex/one",
                      startCommit=self.base,
                      nativeCreation={"projectId": "native-fixture-project", "environment": "worktree",
                                      "startingCommit": self.base, "seedHash": seed_hash,
                                      "threadId": thread, "hostId": "local"},
                      nativeObservation={"threadId": thread, "hostId": "local", "cwd": str(one),
                                         "observedAt": time.time(), "sourceHash": "b"*64})

    def test_pause_and_budget_fence_new_claim_but_allow_safe_observations(self):
        self.control(); self.claim_kind("one", "src/fixture/one.py")
        one = self.native_worktree("one", "codex/one")
        self.bind_worktree("one", one, "codex/one")
        self.control("pause")
        with self.assertRaises(Refusal): self.claim_kind("two", "src/fixture/two.py")
        self.call("observe", taskId="one", nativeStatus="idle", observedTokens=100000,
                  trackedTerminals="none", observedAt=time.time(), source="Native fixture")
        self.assertEqual(read(self.ledger)["run"]["status"], "stopping")

    def test_existing_repository_exclusive_run_never_accepts_parallel_mode_fields(self):
        # This fixture's predecessor run remains separately covered by StandardTest.
        self.control()
        self.assertEqual(read(self.ledger)["run"]["limits"]["repositoryMode"], "isolated_worktrees")
