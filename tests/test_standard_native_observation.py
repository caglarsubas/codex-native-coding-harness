"""Synthetic native metadata and temporary standard projects; no real Codex turn."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator import projects, standard_native_observation as observation
from orchestrator.core import Refusal, canonical, digest
from orchestrator.standard import read, read_db
from orchestrator.workspaces import fingerprint
import test_standard


class FakeProxy:
    def __init__(self, endpoint, project_id, thread_ids):
        self.endpoint, self.project_id, self.thread_ids = endpoint, project_id, thread_ids
        self.query_attempted = False
        self.calls, self.threads, self.terminals = [], {}, {}
        self.roots, self.callback = [], None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def call(self, method, params):
        self.query_attempted = True
        self.calls.append((method, copy.deepcopy(params)))
        if self.callback:
            self.callback(method, params)
        if method == "project/read":
            return {"project": {"id": self.project_id, "roots": [{"path": p} for p in self.roots]}}
        if method == "thread/read":
            return {"thread": copy.deepcopy(self.threads[params["threadId"]])}
        if method == "thread/backgroundTerminals/list":
            return copy.deepcopy(self.terminals.get((params["threadId"], params["cursor"]),
                                                    {"data": [], "nextCursor": None}))
        raise AssertionError("Unexpected native method")


class StandardNativeObservationTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_standard.StandardTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.ledger, self.registry, self.token = self.fixture.ledger, self.fixture.registry, self.fixture.token
        self.repo = self.fixture.repo
        self.brain_id = self.ledger.snapshot()["meta"]["brainId"]
        self.project_id = str(uuid.uuid4())
        self.catalog_project_id = str(uuid.uuid4())  # Deliberately different from the owned host ID.
        projects.record(self.registry, {"schemaVersion": 2, "projects": [{
            "projectId": self.catalog_project_id, "projectKind": "local", "label": "Pilot",
            "hostId": "local", "path": str(self.repo), "isGitRepository": True}]}, time.time())
        projects.bind(self.registry, "alpha", "local", self.catalog_project_id, projects.catalog(self.registry)["hash"])
        self.binding = {"endpoint": {"fixture": "pinned"}, "brains": {self.brain_id: {
            "workspaceId": "alpha", "projectId": self.project_id, "catalogProjectId": self.catalog_project_id,
            "cwd": str(self.repo), "nativePolicy": {"sandbox": "workspace-write", "approvalPolicy": "on-request", "codeMode": False}}}}
        self.binding_path = self.fixture.root / "binding.json"
        self.fixture.activate()
        self.run_id = read(self.ledger)["run"]["id"]
        self.thread_id = read(self.ledger)["run"]["tasks"][0]["threadId"]
        self.fake = FakeProxy(self.binding["endpoint"], self.project_id, [self.brain_id, self.thread_id])
        self.fake.roots = [str(self.repo)]
        self.fake.threads = {
            self.brain_id: {"id": self.brain_id, "projectId": self.project_id, "cwd": str(self.repo), "status": {"type": "active"}},
            self.thread_id: {"id": self.thread_id, "projectId": str(uuid.uuid4()), "cwd": str(self.repo),
                             "status": {"type": "idle"}, "preview": "SECRET", "turns": [{"text": "SECRET"}]} }
        patches = [patch.object(observation, "TaskReadProxy", return_value=self.fake),
                   patch.object(observation, "load_binding", side_effect=lambda _: copy.deepcopy(self.binding)),
                   patch.object(observation, "validate_endpoint"),
                   patch("orchestrator.native_project_assignment.validate_endpoint")]
        for item in patches:
            item.start(); self.addCleanup(item.stop)

    def plan(self):
        return observation.plan(self.registry, self.ledger, self.token, self.binding_path, self.run_id)

    def request(self):
        plan = self.plan()
        return {"id": str(uuid.uuid4()), **{k: plan[k] for k in
                ("runId", "expectedRevision", "contextHash", "bindingHash")}}

    def collect(self, request=None):
        return observation.collect(self.registry, self.ledger, self.token, self.binding_path, request or self.request())

    def task(self):
        return read(self.ledger)["run"]["tasks"][0]

    def test_plan_no_native_or_ledger_write(self):
        with read_db(self.ledger.db) as db: before = fingerprint(db)
        plan = self.plan()
        self.assertEqual(plan["registeredTasks"], [{"taskId": "task-1", "threadId": self.thread_id}])
        with read_db(self.ledger.db) as db: self.assertEqual(fingerprint(db), before)
        self.assertFalse(plan["readOnlyNativeQueriesAttempted"])
        self.assertFalse(self.fake.calls)

    def test_complete_registered_sample_can_finish_without_complete_tree_claim(self):
        before = read(self.ledger)["run"]
        result = self.collect()
        report = result["report"]
        self.assertEqual(self.task()["nativeStatus"], "idle")
        self.assertEqual(self.task()["trackedTerminals"], "none")
        self.assertEqual(report["samples"][0]["trackedTerminalCount"], 0)
        for name in ("taskTreeComplete", "processTreeCleanupVerified", "tokenUsageMeasured", "executionAuthorized", "ownershipReleased"):
            self.assertFalse(report["boundary"][name])
        for key in ("status", "limits", "brainAllowance", "brainObservedTokens", "brainUsageCoverage"):
            self.assertEqual(read(self.ledger)["run"][key], before[key])
        self.assertIsNone(self.task()["observedTokens"])
        self.assertNotIn("SECRET", canonical(result))
        self.assertNotIn(str(self.repo), canonical(result))
        self.assertNotIn("thread/list", [m for m, _ in self.fake.calls])
        self.assertTrue(all(params["includeTurns"] is False for m, params in self.fake.calls if m == "thread/read"))
        self.fixture.finish()
        self.fixture.call("checkpoint", outcome="completed", summary="Registered task checked and preserved", brainObservedTokens=None)
        self.assertEqual(read(self.ledger)["run"]["status"], "completed")

    def test_replay_is_historical_without_host_file_reads_or_new_revision(self):
        request = self.request()
        first = self.collect(request)
        revision = self.ledger.snapshot()["meta"]["revision"]
        with patch.object(observation, "load_binding", side_effect=AssertionError("No host file read")), \
             patch.object(observation, "TaskReadProxy", side_effect=AssertionError("No native connection")):
            self.assertEqual(self.collect(request), first)
        self.assertEqual(self.ledger.snapshot()["meta"]["revision"], revision)
        with self.assertRaisesRegex(Refusal, "different content"):
            self.collect({**request, "expectedRevision": request["expectedRevision"] + 1})

    def test_pending_client_id_never_queried_or_cancelled(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            task = meta["standardRun"]["tasks"][0]
            task.update(threadId=None, clientThreadId=self.thread_id, status="pending")
            self.ledger.put(db, "meta", 1, meta)
        sample = self.collect()["report"]["samples"][0]
        self.assertIsNone(sample["threadId"])
        self.assertIn("native_identity_unconfirmed", sample["issues"])
        self.assertEqual(self.task()["status"], "pending")
        self.assertFalse(any(p.get("threadId") == self.thread_id for _, p in self.fake.calls))
        with self.assertRaises(Refusal): self.fixture.finish()

    def test_unloaded_error_unknown_or_active_flags_never_claim_idle(self):
        for status in ({"type": "notLoaded"}, {"type": "systemError"}, {"type": "invented"},
                       {"type": "idle", "activeFlags": ["waitingOnApproval"]}):
            with self.subTest(status=status):
                self.fake.threads[self.thread_id]["status"] = status
                sample = self.collect()["report"]["samples"][0]
                self.assertEqual((sample["nativeStatus"], sample["trackedTerminals"]), ("unknown", "unknown"))
                self.assertIsNone(sample["trackedTerminalCount"])
                with self.assertRaises(Refusal): self.fixture.finish()

    def test_active_and_running_terminals_prevent_finish(self):
        self.fake.threads[self.thread_id]["status"] = {"type": "active"}
        self.fake.terminals[(self.thread_id, None)] = {"data": [{"processId": "42", "itemId": "item-a",
            "command": "SECRET", "cwd": "/SECRET"}], "nextCursor": None}
        sample = self.collect()["report"]["samples"][0]
        self.assertEqual((sample["nativeStatus"], sample["trackedTerminals"], sample["trackedTerminalCount"]), ("active", "running", 1))
        with self.assertRaises(Refusal): self.fixture.finish()

    def test_terminal_pages_must_complete_with_unique_bounded_identities(self):
        cases = [
            {None: {"data": []}},
            {None: {"data": [], "nextCursor": "repeat"}, "repeat": {"data": [], "nextCursor": "repeat"}},
            {None: {"data": [{"processId": "p", "itemId": "i"}] * 2, "nextCursor": None}},
            {None: {"data": [{"processId": str(n), "itemId": "i"} for n in range(65)], "nextCursor": None}},
        ]
        for pages in cases:
            with self.subTest(pages=list(pages)):
                self.fake.terminals = {(self.thread_id, cursor): page for cursor, page in pages.items()}
                sample = self.collect()["report"]["samples"][0]
                self.assertEqual(sample["trackedTerminals"], "unknown")
                self.assertIsNone(sample["trackedTerminalCount"])

    def test_complete_multipage_terminals_are_not_an_empty_page(self):
        self.fake.terminals = {(self.thread_id, None): {"data": [], "nextCursor": "next"},
            (self.thread_id, "next"): {"data": [{"processId": "p", "itemId": "i"}], "nextCursor": None}}
        sample = self.collect()["report"]["samples"][0]
        self.assertEqual((sample["trackedTerminals"], sample["trackedTerminalCount"]), ("running", 1))

    def test_racing_native_status_invalidates_earlier_safe_observation(self):
        self.collect()
        count = 0
        def change(method, params):
            nonlocal count
            if method == "thread/read" and params["threadId"] == self.thread_id:
                count += 1
                if count == 4: self.fake.threads[self.thread_id]["status"] = {"type": "active"}
        self.fake.callback = change
        sample = self.collect()["report"]["samples"][0]
        self.assertEqual(sample["nativeStatus"], "unknown")
        self.assertIn("native_task_changed_during_collection", sample["issues"])
        with self.assertRaises(Refusal): self.fixture.finish()

    def test_native_failure_invalidates_safe_observation_without_touching_tokens(self):
        self.fixture.observe(observedTokens=5000)
        self.collect()
        def fail(method, params):
            if method == "project/read": raise Refusal("SECRET native error")
        self.fake.callback = fail
        report = self.collect()["report"]
        self.assertEqual(report["issues"], ["owned_host_observation_unavailable"])
        self.assertIsNone(report["samples"][0]["trackedTerminalCount"])
        self.assertEqual(self.task()["observedTokens"], 5000)
        self.assertEqual(self.task()["trackedTerminals"], "unknown")
        self.assertNotIn("SECRET", canonical(report))
        with self.assertRaises(Refusal): self.fixture.finish()

    def test_wrong_brain_native_project_catalog_id_or_root_never_applies_safe_sample(self):
        cases = [{"id": str(uuid.uuid4())}, {"projectId": self.catalog_project_id}, {"cwd": str(self.repo.parent)}]
        for updates in cases:
            with self.subTest(updates=updates):
                prior = copy.deepcopy(self.fake.threads[self.brain_id])
                self.fake.threads[self.brain_id].update(updates)
                self.assertEqual(self.collect()["report"]["issues"], ["owned_host_observation_unavailable"])
                self.fake.threads[self.brain_id] = prior
        self.fake.roots = [str(self.repo), str(self.repo.parent)]
        self.assertEqual(self.collect()["report"]["issues"], ["owned_host_observation_unavailable"])

    def test_foreign_worker_checkout_and_symlink_escape_remain_unknown(self):
        other = self.fixture.root / "other-repo"; other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        link = self.fixture.root / "link"; link.symlink_to(self.repo)
        for cwd in (str(other), str(link), str(self.repo / ".." / "repo")):
            self.fake.threads[self.thread_id]["cwd"] = cwd
            self.assertEqual(self.collect()["report"]["samples"][0]["nativeStatus"], "unknown")

    def test_strict_foreign_controller_and_legacy_run_refuse_before_host_inspection(self):
        with patch.object(observation, "load_binding", side_effect=AssertionError("No host inspection")):
            with self.assertRaises(Refusal): self.plan_with_token("wrong")
            with self.assertRaises(Refusal): observation.plan(self.registry, self.ledger, self.token, self.binding_path, "foreign-run")
            with self.ledger.tx() as db:
                repo = self.ledger.get(db, "repos", "a"); repo["policyProfile"] = "harness"
                self.ledger.put(db, "repos", "a", repo)
            with self.assertRaisesRegex(Refusal, "Harness"): self.plan()

    def plan_with_token(self, token):
        return observation.plan(self.registry, self.ledger, token, self.binding_path, self.run_id)

    def test_stale_context_refuses_before_native_reads(self):
        request = self.request()
        self.fixture.control("pause")
        with self.assertRaisesRegex(Refusal, "context changed"): self.collect(request)
        self.assertFalse(self.fake.calls)
        self.assertEqual(read(self.ledger)["run"]["status"], "stopping")

    def test_pause_during_collection_never_commits_observations_or_loses_stop(self):
        request = self.request()
        fired = False
        def stop(method, params):
            nonlocal fired
            if not fired:
                fired = True
                self.fixture.control("pause")
        self.fake.callback = stop
        with self.assertRaisesRegex(Refusal, "changed during observation"): self.collect(request)
        run = read(self.ledger)["run"]
        self.assertEqual(run["status"], "stopping")
        self.assertNotIn("nativeObservationHash", run)

    def test_safety_observation_after_budget_or_phase_pause_cannot_resume(self):
        self.fixture.control("pause")
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["standardRun"]["expiresAt"] = time.time() - 100
            meta["brainControl"] = {"desired": "stopped", "phase": "checkpointing", "commandId": "legacy-stop"}
            self.ledger.put(db, "meta", 1, meta)
        self.collect()
        meta = self.ledger.snapshot()["meta"]
        self.assertEqual(meta["standardRun"]["status"], "stopping")
        self.assertEqual(meta["brainControl"]["phase"], "checkpointing")
        self.assertTrue(meta["paused"])
        self.assertTrue(any("expired" in b for b in read(self.ledger)["blockers"]))

    def test_changed_binding_rejected_before_connection(self):
        request = self.request()
        self.binding["endpoint"]["fixture"] = "replacement"
        with self.assertRaisesRegex(Refusal, "binding changed"): self.collect(request)
        self.assertFalse(self.fake.calls)

    def test_corrupt_measured_proof_blocks_finish_but_dashboard_reports_gap(self):
        result = self.collect()
        with self.ledger.tx() as db:
            db.execute("UPDATE snapshots SET data='{}' WHERE id=?", (result["reportHash"],))
        self.assertIn("retained_native_observation_unavailable", read(self.ledger)["nativeObservation"]["issues"])
        with self.assertRaises(Refusal): self.fixture.finish()

    def test_supplied_observation_does_not_inherit_measured_provenance(self):
        self.collect()
        self.fixture.observe()
        self.assertNotIn("nativeObservationHash", self.task())
        self.assertEqual(self.task()["observationSource"], "Native fixture observation")

    def test_proxy_rejects_discovery_mutation_and_foreign_ids_before_rpc(self):
        # Exercise the actual allowlist, not the fake collection transport.
        client = REAL_PROXY(self.binding["endpoint"], self.project_id, [self.brain_id, self.thread_id])
        with patch.object(client, "_rpc") as rpc:
            for method, params in (("thread/list", {}), ("thread/loaded/list", {}), ("turn/start", {}),
                ("thread/resume", {}), ("thread/backgroundTerminals/clean", {"threadId": self.thread_id}),
                ("thread/read", {"threadId": str(uuid.uuid4()), "includeTurns": False}),
                ("thread/read", {"threadId": self.thread_id, "includeTurns": True}),
                ("project/read", {"projectId": self.catalog_project_id})):
                with self.assertRaises(Refusal): client.call(method, params)
            rpc.assert_not_called()

    def test_foreign_registered_native_worker_id_is_refused(self):
        other, _ = self.fixture.workspace("beta")
        with other.tx() as db:
            meta = other.get(db, "meta", 1)
            meta["standardRun"] = {"tasks": [{"threadId": self.thread_id}]}
            other.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "Foreign"): self.plan()
        self.assertFalse(self.fake.calls)

    def test_duplicate_registered_id_is_refused(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            copy_task = copy.deepcopy(meta["standardRun"]["tasks"][0]); copy_task["id"] = "task-2"
            meta["standardRun"]["tasks"].append(copy_task)
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "duplicate"): self.plan()
        self.assertFalse(self.fake.calls)

    def test_confirmed_worker_with_same_retained_client_id_is_not_pending(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["standardRun"]["tasks"][0]["clientThreadId"] = self.thread_id
            self.ledger.put(db, "meta", 1, meta)
        self.assertEqual(self.collect()["report"]["samples"][0]["nativeStatus"], "idle")

    def test_isolated_mode_refuses_unbound_worktree_observation(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["standardRun"]["limits"]["repositoryMode"] = "isolated_worktrees"
            self.ledger.put(db, "meta", 1, meta)
        sample = self.collect()["report"]["samples"][0]
        self.assertIn("native_checkout_binding_unavailable", sample["issues"])
        self.assertEqual(sample["nativeStatus"], "unknown")

    def test_wrong_exact_pinned_worktree_does_not_claim_safe_observation(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["standardRun"]["tasks"][0]["worktree"] = {"root": str(self.repo.parent / "expected-worktree")}
            self.ledger.put(db, "meta", 1, meta)
        self.assertEqual(self.collect()["report"]["samples"][0]["nativeStatus"], "unknown")

    def test_remote_task_cannot_be_read_on_local_host(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["standardRun"]["tasks"][0]["hostId"] = "remote"
            self.ledger.put(db, "meta", 1, meta)
        self.assertEqual(self.collect()["report"]["samples"][0]["nativeStatus"], "unknown")
        self.assertFalse(any(p.get("threadId") == self.thread_id for _, p in self.fake.calls))

    def test_native_sample_cannot_be_reused_for_another_task_or_after_expiry(self):
        result = self.collect()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["standardRun"]["tasks"][0]["observedAt"] = time.time() - 301
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal): self.fixture.finish()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            task = meta["standardRun"]["tasks"][0]
            task["observedAt"] = result["report"]["observedAt"]
            task["threadId"] = str(uuid.uuid4())
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "proof changed"): self.fixture.finish()

    def test_binding_change_during_collection_never_updates_task(self):
        request = self.request()
        fired = False
        def change(method, params):
            nonlocal fired
            if not fired:
                self.binding["endpoint"]["fixture"] = "new-host"
                fired = True
        self.fake.callback = change
        with self.assertRaisesRegex(Refusal, "changed during observation"): self.collect(request)
        self.assertNotIn("nativeObservationHash", self.task())

    def test_wrong_worker_native_id_stays_unknown(self):
        self.fake.threads[self.thread_id]["id"] = str(uuid.uuid4())
        self.assertEqual(self.collect()["report"]["samples"][0]["nativeStatus"], "unknown")

    def test_cli_refuses_unregistered_scope_before_creating_state(self):
        path = self.fixture.root / "must-not-exist"
        result = subprocess.run([sys.executable, "-m", "orchestrator.cli", "--state", str(path),
                                 "standard-native-plan", str(self.binding_path), self.run_id],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("explicit registered workspace", result.stderr)
        self.assertFalse(path.exists())


REAL_PROXY = observation.TaskReadProxy
