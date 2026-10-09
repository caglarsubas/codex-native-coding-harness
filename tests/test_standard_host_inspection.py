"""Disposable repositories and synthetic protocol metadata; no real wake."""
import copy
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from orchestrator import standard_host_inspection as inspection
from orchestrator.core import Refusal, canonical, digest
from orchestrator.standard import read, read_db
from orchestrator.workspaces import fingerprint
import test_standard_native_observation as fixtures


class HostInspectionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.StandardNativeObservationTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.ledger, self.registry, self.token = self.fixture.ledger, self.fixture.registry, self.fixture.token
        self.binding = self.fixture.binding
        self.run_id = self.fixture.run_id
        command = next(c for c in self.ledger.snapshot()["commands"] if c["kind"] == "standard_play")
        self.command_id = command["id"]
        self.key = inspection.retain_binding(self.ledger, self.binding)
        profile = inspection.resume_profile(self.binding, self.fixture.brain_id, self.command_id, {
            "sandbox": {"type": "workspaceWrite"}, "approvalPolicy": "on-request", "approvalsReviewer": "user"})
        profile["nativeTurnId"] = "owned-turn-1"
        self.fixture.fake.threads[self.fixture.brain_id]["status"]["activeFlags"] = []
        self.note = {"brainId": self.fixture.brain_id, "attemptedAt": time.time(),
            "status": "accepted", "nativeDelivery": "owned_turn_start", "nativeTurnId": "owned-turn-1",
            "hostBindingHash": self.key, "hostRunId": self.run_id, "nativeResumeProfile": profile,
            "nativeThreadObservation": {"rootThreadId": self.fixture.brain_id, "streamStatus": "open"}}
        self.update()
        for item in (patch.object(inspection, "TaskReadProxy", return_value=self.fixture.fake),
                     patch.object(inspection, "load_binding", side_effect=lambda _: copy.deepcopy(self.binding))):
            item.start(); self.addCleanup(item.stop)

    def update(self, **changes):
        self.note.update(changes)
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", self.command_id)
            command["notification"] = copy.deepcopy(self.note)
            self.ledger.put(db, "commands", self.command_id, command)

    def inspect(self, **kwargs):
        return inspection.inspect(self.registry, self.ledger, kwargs.get("token", self.token),
                                  kwargs.get("run_id", self.run_id), kwargs.get("command_id", self.command_id))

    def test_repeated_read_is_nonmutating_and_keeps_policy_evidence_separate(self):
        with read_db(self.ledger.db) as db: before = fingerprint(db)
        result = self.inspect()
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["ownedProjectId"], self.fixture.project_id)
        self.assertEqual(result["catalogProjectId"], self.fixture.catalog_project_id)
        self.assertIsNone(result["resumeProfile"]["reported"]["codeMode"])
        self.assertFalse(result["resumeProfile"]["requested"]["codeMode"])
        self.assertTrue(result["resumeProfile"]["resumeAcknowledged"])
        self.assertEqual(result["resumeProfile"]["observedAt"], self.inspect()["resumeProfile"]["observedAt"])
        self.assertTrue(all(v is False for v in result["boundary"].values()))
        self.assertIn("native_effect_inventory_not_complete", result["gaps"])
        self.assertNotIn("SECRET", canonical(result))
        self.assertNotIn(str(self.fixture.repo), canonical(result))
        self.assertNotIn("endpoint", result)
        self.assertEqual([m for m, _ in self.fixture.fake.calls], ["project/read", "thread/read"] * 4)
        with read_db(self.ledger.db) as db: self.assertEqual(fingerprint(db), before)

    def test_private_copy_never_overwrites_or_renews_review(self):
        path = inspection.binding_file(self.ledger, self.key)
        before = path.stat()
        self.assertEqual(inspection.retain_binding(self.ledger, self.binding), self.key)
        self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        os.chmod(path, 0o644)
        with self.assertRaises(Refusal): inspection.retain_binding(self.ledger, self.binding)

    def test_copy_refuses_symlink_and_changed_content(self):
        path = inspection.binding_file(self.ledger, self.key)
        path.unlink()
        path.symlink_to(self.ledger.db)
        with self.assertRaises(Refusal): inspection.retain_binding(self.ledger, self.binding)
        self.assertTrue(path.is_symlink())

    def test_unknown_native_policy_never_inherits_requested_values(self):
        self.note["nativeResumeProfile"] = inspection.resume_profile(self.binding, self.fixture.brain_id, self.command_id,
            {"preview": "PRIVATE RESPONSE", "approvalPolicy": {"granular": {}}, "sandbox": "workspace-write"})
        self.note["nativeResumeProfile"]["nativeTurnId"] = "owned-turn-1"
        self.update()
        result = self.inspect()
        self.assertEqual(len(result["issues"]), 3)
        self.assertTrue(all(v is None for v in result["resumeProfile"]["reported"].values()))
        self.assertNotIn("PRIVATE RESPONSE", canonical(result))

    def test_weaker_or_auto_approved_profile_is_explicitly_reported(self):
        self.note["nativeResumeProfile"] = inspection.resume_profile(self.binding, self.fixture.brain_id, self.command_id,
            {"approvalPolicy": "never", "sandbox": {"type": "dangerFullAccess"}, "approvalsReviewer": "auto_review"})
        self.note["nativeResumeProfile"]["nativeTurnId"] = "owned-turn-1"
        self.update()
        result = self.inspect()
        self.assertEqual(len(result["issues"]), 3)
        self.assertFalse(result["boundary"]["executionAuthorized"])

    def test_closed_old_unknown_or_foreign_control_refuses_before_native_read(self):
        for changes in ({"status": "uncertain"}, {"nativeTurnStatus": "completed"},
                        {"nativeDelivery": "desktop_queue_only"}, {"hostBindingHash": "a" * 64},
                        {"hostRunId": "foreign-run"},
                        {"nativeResumeProfile": None}, {"brainId": "foreign"},
                        {"nativeThreadObservation": {"rootThreadId": self.fixture.brain_id, "streamStatus": "closed"}}):
            original = copy.deepcopy(self.note)
            self.update(**changes)
            with self.assertRaises(Refusal): self.inspect()
            self.note = original; self.update()
        for kwargs in ({"token": "invalid"}, {"run_id": "another-run"}, {"command_id": "another-command"}):
            with self.assertRaises(Refusal): self.inspect(**kwargs)
        self.assertFalse(self.fixture.fake.calls)

    def test_newer_control_supersedes_handoff(self):
        with self.ledger.tx() as db:
            command = copy.deepcopy(self.ledger.get(db, "commands", self.command_id))
            command["id"] = "newer-control"
            command["notification"]["attemptedAt"] += 1
            self.ledger.put(db, "commands", command["id"], command)
        with self.assertRaisesRegex(Refusal, "superseded"): self.inspect()
        self.assertFalse(self.fixture.fake.calls)

    def test_known_unresolved_approval_is_not_treated_as_none(self):
        self.update(nativeApprovals=[{"status": "uncertain", "requestHash": "a" * 64}])
        self.assertIn("unresolved_recorded_native_approval", self.inspect()["issues"])

    def test_strict_and_foreign_workspace_fences_precede_host_reads(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["admissionBinding"] = {"fixture": "strict"}
            self.ledger.put(db, "meta", 1, meta)
        with patch.object(inspection, "load_binding") as host_read:
            with self.assertRaises(Refusal): self.inspect()
            host_read.assert_not_called()
        self.assertFalse(self.fixture.fake.calls)

    def test_changed_binding_and_endpoint_refuse_without_native_queries(self):
        with patch.object(inspection, "load_binding", return_value={**self.binding, "endpoint": {"fixture": "changed"}}):
            with self.assertRaisesRegex(Refusal, "binding changed"): self.inspect()
        with patch.object(inspection, "load_binding", side_effect=Refusal("Reviewed endpoint changed")):
            with self.assertRaises(Refusal): self.inspect()
        self.assertFalse(self.fixture.fake.calls)

    def test_queued_control_does_not_implicitly_receive_it(self):
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", self.command_id)
            command["status"] = "queued"
            self.ledger.put(db, "commands", self.command_id, command)
        with self.assertRaisesRegex(Refusal, "Receive"): self.inspect()
        self.assertFalse(self.fixture.fake.calls)

    def test_conversation_control_uses_bound_notification_run_not_inferred_payload(self):
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", self.command_id)
            command.update(kind="reconcile", payload={})
            self.ledger.put(db, "commands", self.command_id, command)
        self.assertEqual(self.inspect()["runId"], self.run_id)
        self.update(hostRunId="another-run")
        with self.assertRaises(Refusal): self.inspect()

    def test_native_membership_and_activity_must_remain_exact(self):
        thread = self.fixture.fake.threads[self.fixture.brain_id]
        for key, value in (("projectId", self.fixture.catalog_project_id), ("cwd", "/foreign"),
                           ("status", {"type": "notLoaded"}), ("status", {})):
            original = thread[key]; thread[key] = value
            with self.assertRaises(Refusal): self.inspect()
            thread[key] = original

    def test_missing_or_waiting_native_flags_do_not_prove_no_pending_approval(self):
        status = self.fixture.fake.threads[self.fixture.brain_id]["status"]
        status["activeFlags"] = ["waitingOnApproval"]
        self.assertIn("native_approval_or_user_input_pending", self.inspect()["issues"])
        status.pop("activeFlags")
        self.assertIn("native_active_flags_unavailable", self.inspect()["issues"])

    def test_profile_from_another_command_or_turn_is_not_current_evidence(self):
        for key in ("commandId", "nativeTurnId"):
            profile = self.note["nativeResumeProfile"]
            original = profile[key]; profile[key] = "another"
            self.update()
            with self.assertRaises(Refusal): self.inspect()
            profile[key] = original
        self.assertFalse(self.fixture.fake.calls)

    def test_pause_race_does_not_return_stale_context(self):
        def callback(*_):
            self.fixture.fake.callback = None
            with self.ledger.tx() as db:
                meta = self.ledger.get(db, "meta", 1)
                meta["standardRun"]["status"] = "stopping"
                meta["revision"] += 1
                self.ledger.put(db, "meta", 1, meta)
        self.fixture.fake.callback = callback
        with self.assertRaisesRegex(Refusal, "context changed"): self.inspect()
        self.assertEqual(read(self.ledger)["run"]["status"], "stopping")

    def test_cli_refuses_default_or_state_route_without_creating_state(self):
        path = self.fixture.fixture.root / "absent"
        result = subprocess.run([sys.executable, "-m", "orchestrator.cli", "--state", str(path),
            "standard-host-inspect", self.run_id, self.command_id], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(path.exists())

    def test_owned_notification_hands_off_without_browser_text_or_another_send(self):
        from orchestrator.notification import BrainNotifier
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", self.command_id)
            command.pop("notification")
            command["status"] = "queued"
            self.ledger.put(db, "commands", self.command_id, command)
        notifier = BrainNotifier(self.ledger, app_server_binding=self.binding)
        self.addCleanup(notifier.close)
        with patch.object(notifier, "status", return_value={"status": "configured"}), \
             patch.object(notifier.app_server, "send", return_value={"status": "accepted"}) as send:
            result = notifier.notify(self.command_id)
            self.assertEqual(result["notification"]["hostBindingHash"], self.key)
            pointer = send.call_args.args[1]
            self.assertIn("standard-host-inspect RUN_ID COMMAND_ID", pointer)
            self.assertIn(self.command_id, pointer)
            self.assertNotIn("endpoint", pointer)
            self.assertNotIn("socket", pointer)
            self.assertNotIn(str(inspection.binding_file(self.ledger, self.key)), pointer)
            notifier.notify(self.command_id)
            send.assert_called_once()

    def test_failed_private_handoff_is_saved_unsent_without_retry(self):
        from orchestrator.notification import BrainNotifier
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", self.command_id)
            command.pop("notification")
            command["status"] = "queued"
            self.ledger.put(db, "commands", self.command_id, command)
        notifier = BrainNotifier(self.ledger, app_server_binding=self.binding)
        self.addCleanup(notifier.close)
        with patch.object(notifier, "status", return_value={"status": "configured"}), \
             patch.object(inspection, "retain_binding", side_effect=Refusal("PRIVATE ERROR")), \
             patch.object(notifier.app_server, "send") as send:
            result = notifier.notify(self.command_id)
            self.assertEqual(result["notification"]["status"], "unavailable")
            self.assertNotIn("PRIVATE ERROR", str(result))
            notifier.notify(self.command_id)
            send.assert_not_called()
