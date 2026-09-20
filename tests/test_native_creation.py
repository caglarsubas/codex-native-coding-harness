"""CLI/native-tool-shaped integration on private fixtures; no real task calls."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import native_creation as creation, run_authority as runs, workspace_pause
from orchestrator.core import Ledger, PREFLIGHT_CHECKS, Refusal, canonical, digest
import test_core
import test_dispatch_admission
import test_missions
import test_run_authority
from test_source_observation import GitFixture


class NativeCreationFixture(GitFixture):
    def setUp(self):
        self.make_git()
        initialize, seed = Ledger.initialize, test_core.seed
        profile = getattr(self, "fixture_profile", "standard")
        def initialize_fixture(ledger, config):
            config = copy.deepcopy(config)
            for repo in config["repositories"]:
                if repo["id"] == "a": repo.update(path=str(self.repo), policyProfile=profile)
            return initialize(ledger, config)
        def seed_fixture(*args, **kwargs): return {**seed(*args, **{**kwargs, "profile": profile}), "baseSHA": self.base}
        def preflight(fixture):
            q = fixture.fx.fx.q
            fixture.ledger.preflight(fixture.token, q["id"], {"seedHash": q["seedHash"], "packetDigest": q["packetDigest"],
                "baseSHA": self.base, "projectId": "project-a", "checks": {k: True for k in PREFLIGHT_CHECKS}, "evidence": ["fixture"]})
        for mock in (patch.object(Ledger, "initialize", initialize_fixture), patch.object(test_core, "seed", seed_fixture),
                     patch.object(test_dispatch_admission, "KEY", getattr(self, "fixture_resource", self.key)),
                     patch.object(test_dispatch_admission.DispatchAdmissionTest, "preflight", preflight)):
            mock.start(); self.addCleanup(mock.stop)
        self.fx = test_dispatch_admission.DispatchAdmissionTest(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.ledger, self.token, self.store = self.fx.ledger, self.fx.token, self.fx.store
        self.wid = self.fx.reserve()["workerId"]
        self.api = creation.NativeCreation(self.fx.bridge)

    def request(self, **fields):
        return {"id": "handoff-1", "expectedRevision": self.ledger.snapshot()["meta"]["revision"],
                "projectObservation": {"observedAt": time.time(), "evidenceHash": "a"*64,
                    "project": {"projectId": "project-a", "projectKind": "local", "hostId": "local",
                                "path": str(self.repo), "isGitRepository": True}}, **fields}

    def begin(self, request=None): return self.api.begin(self.token, self.wid, request or self.request())
    def check(self, handoff): return self.api.check(self.token, self.wid, handoff["handoffHash"])
    def logical(self): return self.fx.fx.fx.logical(), self.store.snapshot()

    def result_request(self, handoff, **fields):
        return {"id": "result-1", "handoffHash": handoff["handoffHash"],
                "expectedHash": self.fx.claim().get("nativeLifecycleHash"), "observedAt": time.time(),
                "outcome": "confirmed", "hostId": "local", "threadId": "native-task", "clientThreadId": None,
                "evidenceHash": "c"*64, **fields}

    def record(self, handoff, **fields): return self.api.record(self.token, self.wid, self.result_request(handoff, **fields))

    def cli(self, *args, request=None, token=None, select=True):
        argv = [sys.executable, "-m", "orchestrator.cli"]
        if select: argv += ["--platform", str(self.fx.registry.root), "--workspace", "a"]
        argv += args
        if request is not None:
            path = self.root / "request.json"; path.write_text(canonical(request)); argv.append(str(path))
        return subprocess.run(argv, cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
                              env={**os.environ, "ORCHESTRATOR_CONTROLLER_TOKEN": token or self.token})


class NativeCreationTest(NativeCreationFixture, unittest.TestCase):
    def test_begin_exact_base_scoped_prompt_and_native_defaults_without_git_writes(self):
        before = self.disk(); handoff = self.begin(); args = handoff["arguments"]
        self.assertEqual(before, self.disk())
        self.assertEqual(set(args), {"title", "prompt", "target"})
        self.assertEqual(args["target"], {"type": "project", "projectId": "project-a", "environment": {
            "type": "worktree", "startingState": {"type": "branch", "branchName": self.base}}})
        self.assertIn(self.wid, args["prompt"])
        self.assertIn("Permitted operations: commit, edit, open_pr, test.", args["prompt"])
        self.assertIn("Do not merge, archive, create other tasks", args["prompt"])
        self.assertIn(canonical(self.fx.fx.fx.seed), args["prompt"])
        self.assertTrue(handoff["mustCheckBeforeSend"]); self.assertFalse(handoff["nativeCallMade"])
        self.assertEqual(self.fx.worker()["nativeHandoffHash"], handoff["handoffHash"])
        self.assertEqual(self.fx.claim()["status"], "starting")
        self.assertIsNone(self.fx.worker()["threadId"])

    def test_cli_roundtrip_matches_native_pending_then_confirmed_return(self):
        begun = self.cli("native-create-begin", self.wid, request=self.request())
        self.assertEqual(begun.returncode, 0, begun.stderr)
        handoff = json.loads(begun.stdout)
        check = self.cli("native-create-check", self.wid, handoff["handoffHash"])
        self.assertEqual(check.returncode, 0, check.stderr); self.assertTrue(json.loads(check.stdout)["sendNow"])
        # Exact tool-shaped pending return, not a thread ID and not proof of running.
        native_return = {"clientThreadId": "pending-client"}
        pending = self.result_request(handoff, outcome="pending", threadId=None, **native_return)
        saved = self.cli("native-create-record", self.wid, request=pending)
        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertIsNone(self.fx.worker()["threadId"]); self.assertEqual(self.fx.worker()["clientThreadId"], "pending-client")
        confirmed = self.result_request(handoff, id="result-2", clientThreadId="pending-client")
        saved = self.cli("native-create-record", self.wid, request=confirmed)
        self.assertEqual(saved.returncode, 0, saved.stderr)
        state = self.cli("native-create-state", self.wid)
        self.assertEqual(state.returncode, 0, state.stderr)
        self.assertEqual(json.loads(state.stdout)["native"], {"hostId": "local", "threadId": "native-task"})
        self.assertEqual(self.fx.worker()["nativeActivity"]["activity"], "unknown")
        self.assertFalse(json.loads(state.stdout)["creationRetryAllowed"])
        self.assertNotIn("arguments", json.loads(state.stdout))

    def test_begin_and_send_check_are_independently_one_shot(self):
        handoff = self.begin(); self.check(handoff); before = self.logical()
        for call in (lambda: self.begin(), lambda: self.check(handoff)):
            with self.assertRaises(Refusal): call()
            self.assertEqual(before, self.logical())
        check = self.ledger.document(self.fx.worker()["nativeHandoffCheckHash"])
        self.assertEqual(check["handoffHash"], handoff["handoffHash"])

    def test_concurrent_begin_emits_only_one_handoff(self):
        request = self.request()
        def attempt():
            try: return self.begin(request)
            except Refusal: return None
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(len(self.store.snapshot()["claims"]), 1)

    def test_concurrent_check_consumes_only_once(self):
        handoff = self.begin()
        def attempt():
            try: return self.check(handoff)
            except Refusal: return None
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_wrong_project_refuses_before_any_repository_inspection(self):
        for key, value in (("projectId", "other"), ("path", str(self.root)), ("projectKind", "chatgpt"),
                           ("hostId", "remote"), ("isGitRepository", False), ("isGitRepository", 1)):
            with self.subTest(key=key):
                request = self.request(); request["projectObservation"]["project"][key] = value
                before = self.logical()
                with patch.object(creation, "inspect_base", side_effect=AssertionError("no repository read")):
                    with self.assertRaises(Refusal): self.begin(request)
                self.assertEqual(before, self.logical())

    def test_stale_and_future_project_evidence_refuse_without_writes(self):
        for at in (time.time()-61, time.time()+30, True, float("nan")):
            request = self.request(); request["projectObservation"]["observedAt"] = at
            before = self.logical()
            with self.assertRaises(Refusal): self.begin(request)
            self.assertEqual(before, self.logical())

    def test_wrong_controller_revision_and_closed_shape_refuse_without_writes(self):
        before = self.logical()
        with self.assertRaises(Refusal): self.api.begin("wrong", self.wid, self.request())
        for change in ({"expectedRevision": 0}, {"expectedRevision": True}, {"extra": True}, {"id": "bad/id"}):
            with self.assertRaises(Refusal): self.begin(self.request(**change))
        self.assertEqual(before, self.logical())

    def test_expired_account_evidence_blocks_before_probe(self):
        # Use the store's own clock beyond all evidence but inside run lifetime.
        with patch.object(self.store, "clock", return_value=time.time()+61), \
                patch.object(creation, "inspect_base", side_effect=AssertionError("no read")):
            with self.assertRaises(Refusal): self.begin()
        self.assertEqual(self.fx.claim()["status"], "reserved")

    def test_missing_object_and_git_identity_change_do_not_cross_boundary(self):
        obj = self.repo / ".git/objects" / self.base[:2] / self.base[2:]
        saved = self.root / "saved-base"; obj.rename(saved)
        before = self.logical()
        with self.assertRaises(Refusal): self.begin()
        self.assertEqual(before, self.logical()); saved.rename(obj)
        old = self.repo / ".git"; old.rename(self.root / "original-git"); old.mkdir()
        with self.assertRaisesRegex(Refusal, "identity changed"): self.begin()
        self.assertEqual(before, self.logical())

    def test_pause_during_base_probe_does_not_cross_creation_boundary(self):
        inspect = creation.inspect_base
        def pause(*args, **kwargs):
            result = inspect(*args, **kwargs); self.fx.fx.fx.command("pause"); return result
        with patch.object(creation, "inspect_base", side_effect=pause):
            with self.assertRaises(Refusal): self.begin()
        self.assertEqual(self.fx.worker()["dispatchAdmission"]["stage"], "reserved")
        self.assertEqual(self.fx.claim()["status"], "reserved")

    def test_revision_change_during_probe_requires_new_review(self):
        inspect = creation.inspect_base
        def changed(*args, **kwargs):
            result = inspect(*args, **kwargs)
            with self.ledger.tx() as db: self.ledger.event(db, "fixture_concurrent_change", {})
            return result
        with patch.object(creation, "inspect_base", side_effect=changed):
            with self.assertRaisesRegex(Refusal, "Workspace changed"): self.begin()
        self.assertEqual(self.fx.claim()["status"], "reserved")

    def test_pause_between_creation_commits_retains_uncertain_owner_no_reissue(self):
        locked = self.fx.bridge.locked; count = 0
        def pause(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 3: self.fx.fx.fx.command("pause")
            return locked(*args, **kwargs)
        with patch.object(self.fx.bridge, "locked", side_effect=pause):
            with self.assertRaises(Refusal): self.begin()
        self.assertEqual(self.fx.worker()["dispatchAdmission"]["stage"], "creation_pending")
        self.assertEqual(self.fx.claim()["status"], "reserved")
        state = self.api.state(self.token, self.wid)
        self.assertTrue(state["creationBoundaryCrossed"]); self.assertIsNone(state["handoffHash"])
        self.fx.meta(paused=False)
        with self.assertRaises(Refusal): self.begin()

    def test_failure_retaining_handoff_never_reissues_after_creation_boundary(self):
        retain = runs.retain
        def fail(db, kind, doc):
            if kind == creation.KIND: raise RuntimeError("fixture handoff commit failure")
            return retain(db, kind, doc)
        with patch.object(runs, "retain", side_effect=fail):
            with self.assertRaises(RuntimeError): self.begin()
        self.assertEqual(self.fx.claim()["status"], "starting")
        self.assertIsNone(self.fx.worker().get("nativeHandoffHash"))
        with self.assertRaises(Refusal): self.begin()

    def test_check_refuses_after_pause_or_revocation(self):
        handoff = self.begin(); self.fx.fx.fx.command("pause")
        with self.assertRaises(Refusal): self.check(handoff)
        self.fx.meta(paused=False)
        request = self.fx.fx.request(queueId=self.fx.args["queue_id"], approvalHash=self.fx.approval["approvalHash"], reason="Fixture revocation")
        runs.revoke_task(self.ledger, request, actor="dashboard_owner")
        with self.assertRaises(Refusal): self.check(handoff)
        self.assertIsNone(self.fx.worker().get("nativeHandoffCheckHash"))

    def test_check_reprobes_base_and_rejects_expired_handoff(self):
        handoff = self.begin()
        with patch("orchestrator.native_creation.time.time", return_value=time.time()+61):
            with self.assertRaises(Refusal): self.check(handoff)
        obj = self.repo / ".git/objects" / self.base[:2] / self.base[2:]; obj.rename(self.root / "saved-base")
        with self.assertRaises(Refusal): self.check(handoff)
        self.assertIsNone(self.fx.worker().get("nativeHandoffCheckHash"))

    def test_pause_during_send_probe_does_not_consume_check(self):
        handoff = self.begin(); inspect = creation.inspect_base
        def pause(*args, **kwargs):
            result = inspect(*args, **kwargs); self.fx.fx.fx.command("pause"); return result
        with patch.object(creation, "inspect_base", side_effect=pause):
            with self.assertRaises(Refusal): self.check(handoff)
        self.assertIsNone(self.fx.worker().get("nativeHandoffCheckHash"))

    def test_late_result_after_pause_records_without_resuming_or_releasing(self):
        handoff = self.begin(); self.check(handoff); self.fx.fx.fx.command("pause")
        receipt = self.record(handoff)
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertFalse(receipt["ownershipReleased"])
        self.assertEqual(self.fx.claim()["status"], "running")
        self.assertEqual(self.fx.worker()["nativeActivity"]["activity"], "unknown")
        self.assertTrue(self.store.snapshot()["resources"])

    def test_uncertain_outcome_retains_capacity_and_late_confirmation(self):
        handoff = self.begin(); self.check(handoff)
        self.record(handoff, outcome="uncertain", threadId=None)
        self.assertEqual(self.fx.claim()["status"], "uncertain")
        with self.assertRaises(Refusal): self.begin()
        with self.assertRaises(Refusal): self.check(handoff)
        self.record(handoff, id="resolved")
        self.assertEqual(self.fx.worker()["threadId"], "native-task")

    def test_pending_identity_cannot_be_promoted_erased_or_replaced(self):
        handoff = self.begin(); self.check(handoff)
        self.record(handoff, outcome="pending", threadId=None, clientThreadId="client-1")
        before = self.logical()
        for change in ({}, {"threadId": "client-1", "clientThreadId": "client-1"}, {"clientThreadId": "other"}, {"hostId": "remote"}):
            with self.assertRaises(Refusal): self.record(handoff, id="result-2", **change)
            self.assertEqual(before, self.logical())

    def test_result_requires_exact_consumed_check_and_closed_shape(self):
        handoff = self.begin()
        with self.assertRaises(Refusal): self.record(handoff)
        self.check(handoff); before = self.logical()
        for change in ({"activity": "idle"}, {"handoffHash": "d"*64}, {"expectedHash": "e"*64},
                       {"outcome": "not_created"}, {"threadId": "brain-a"}, {"observedAt": 0}):
            with self.assertRaises(Refusal): self.record(handoff, **change)
            self.assertEqual(before, self.logical())

    def test_result_replay_recovers_shared_commit_without_repeating_native_call(self):
        handoff = self.begin(); self.check(handoff); request = self.result_request(handoff)
        with patch.object(self.api.lifecycle, "attach_in", side_effect=RuntimeError("fixture interruption")):
            with self.assertRaises(RuntimeError): self.api.record(self.token, self.wid, request)
        self.assertIsNone(self.fx.worker().get("nativeLifecycleHash"))
        self.assertTrue(self.fx.claim().get("nativeLifecycleHash"))
        self.fx.fx.fx.command("pause")
        one = self.api.record(self.token, self.wid, request); before = self.logical()
        self.assertEqual(one, self.api.record(self.token, self.wid, request))
        self.assertEqual(before, self.logical())
        with self.assertRaises(Refusal): self.api.record(self.token, self.wid, {**request, "evidenceHash": "f"*64})
        self.assertEqual(before, self.logical())

    def test_explicit_recovery_attaches_only_native_receipt_after_pause(self):
        handoff = self.begin(); self.check(handoff)
        with patch.object(self.api.lifecycle, "attach_in", side_effect=RuntimeError("fixture interruption")):
            with self.assertRaises(RuntimeError): self.record(handoff)
        self.fx.fx.fx.command("pause")
        recovered = self.cli("native-create-recover", self.wid)
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(self.fx.worker()["threadId"], "native-task")
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertNotIn("arguments", json.loads(recovered.stdout))

    def test_state_does_not_refresh_any_evidence_and_pause_binding_tracks_handoff(self):
        reserved = workspace_pause.worker_binding(self.fx.worker())
        handoff = self.begin(); begun = workspace_pause.worker_binding(self.fx.worker())
        self.check(handoff); checked = workspace_pause.worker_binding(self.fx.worker())
        self.assertNotEqual(reserved, begun); self.assertNotEqual(begun, checked)
        before = self.logical(); state = self.api.state(self.token, self.wid)
        self.assertEqual(before, self.logical()); self.assertNotIn("arguments", state)
        self.assertFalse(state["creationRetryAllowed"])

    def test_cli_missing_workspace_and_wrong_token_have_no_side_effects(self):
        before = self.logical()
        for command in ("native-create-begin", "native-create-state", "native-create-recover", "native-create-record"):
            args = [command, self.wid]
            if command in ("native-create-begin", "native-create-record"): args.append("/does-not-exist")
            result = self.cli(*args, select=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("explicit registered workspace", result.stderr)
        wrong = self.cli("native-create-state", self.wid, token="wrong")
        self.assertNotEqual(wrong.returncode, 0)
        self.assertEqual(before, self.logical())

    def test_cli_refuses_oversized_symlink_and_fifo_requests(self):
        path = self.root / "bad.json"; path.write_text(" "*16001)
        for name in ("large", "link", "fifo"):
            if name == "large": selected = path
            elif name == "link": selected = self.root / "link"; selected.symlink_to(path)
            else: selected = self.root / "fifo"; os.mkfifo(selected)
            result = self.cli("native-create-begin", self.wid, str(selected))
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.fx.claim()["status"], "reserved")

    def test_pure_prompt_rejects_excessive_inheritance_or_operations(self):
        seed = self.fx.fx.fx.seed
        for operations in (["edit", "merge"], ["archive"], ["test"]):
            with self.assertRaises(Refusal): creation.arguments(self.fx.worker(), seed, {"spec": {"operations": operations}}, {"projectId": "project-a"})
        with self.assertRaisesRegex(Refusal, "20 KiB"):
            creation.arguments(self.fx.worker(), {**seed, "objective": "x"*20000}, {"spec": {"operations": ["edit"], "missionHash": "a"*64}}, {"projectId": "project-a"})

    def test_consumed_check_pointer_cannot_disappear_or_hide_history(self):
        handoff = self.begin(); self.check(handoff)
        with self.ledger.tx() as db:
            worker = self.ledger.get(db, "workers", self.wid); worker.pop("nativeHandoffCheckHash")
            self.ledger.put(db, "workers", self.wid, worker)
        with self.assertRaisesRegex(Refusal, "changed or missing"): self.check(handoff)
        with self.assertRaises(Refusal): self.api.state(self.token, self.wid)
        with self.assertRaises(Refusal): self.record(handoff)

    def test_consumed_check_slot_cannot_disappear(self):
        handoff = self.begin(); self.check(handoff)
        with self.ledger.tx() as db:
            db.execute("DELETE FROM snapshots WHERE kind='native_creation_check_slot'")
        with self.assertRaisesRegex(Refusal, "changed or missing"): self.check(handoff)
        with self.assertRaises(Refusal): self.record(handoff)

    def test_send_check_failure_rolls_back_before_send_now(self):
        handoff = self.begin(); event = self.api.ledger.event
        def fail(db, kind, value):
            if kind == "native_creation_send_check": raise RuntimeError("fixture commit interruption")
            return event(db, kind, value)
        with patch.object(self.api.ledger, "event", side_effect=fail):
            with self.assertRaises(RuntimeError): self.check(handoff)
        self.assertIsNone(self.fx.worker().get("nativeHandoffCheckHash"))
        self.assertTrue(self.check(handoff)["sendNow"])

class NativeCreationHarnessTest(NativeCreationFixture, unittest.TestCase):
    fixture_profile = "harness"

    def test_harness_refuses_before_filesystem_inspection(self):
        before = self.logical()
        with patch.object(creation, "inspect_base", side_effect=AssertionError("Harness must not be inspected")):
            with self.assertRaisesRegex(Refusal, "Harness needs its trusted adapter"): self.begin()
        self.assertEqual(before, self.logical())


class NativeCreationRemoteResourceTest(NativeCreationFixture, unittest.TestCase):
    fixture_resource = "repo-remote:"+"a"*64

    def test_remote_only_resource_does_not_allow_local_base_probe(self):
        before = self.logical()
        with patch.object(creation, "inspect_base", side_effect=AssertionError("no local probe")):
            with self.assertRaisesRegex(Refusal, "pinned local common-directory"): self.begin()
        self.assertEqual(before, self.logical())


class NativeCreationDelegationTest(NativeCreationFixture, unittest.TestCase):
    def setUp(self):
        specification = test_missions.specification
        approve = test_run_authority.RunAuthorityTest.approve
        def delegated_specification(*args, **kwargs): return specification(*args, **{**kwargs, "mode": "phase_delegated"})
        def delegated_approval(fixture, run, **kwargs): return approve(fixture, run, **{**kwargs, "actor": "designated_brain"})
        for mock in (patch.object(test_missions, "specification", delegated_specification),
                     patch.object(test_run_authority.RunAuthorityTest, "approve", delegated_approval)):
            mock.start(); self.addCleanup(mock.stop)
        super().setUp()

    def test_owner_delegated_handoff_preserves_seed_defaults_and_one_shot_check(self):
        handoff = self.begin()
        args = handoff["arguments"]
        self.assertEqual(set(args), {"title", "prompt", "target"})
        self.assertIn("Mission SHA-256", args["prompt"])
        self.assertIn(self.fx.worker()["seedHash"], args["prompt"])
        self.assertTrue(self.check(handoff)["sendNow"])
        with self.assertRaises(Refusal): self.check(handoff)
        self.assertFalse(self.record(handoff)["executionAuthorized"])


if __name__ == "__main__": unittest.main()
