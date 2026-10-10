import copy
import json
import subprocess
import unittest
from unittest.mock import patch

from orchestrator import turn_host_continuity as continuity, turn_recovery as recovery
from orchestrator.app_server_wake import NATIVE_APPROVAL_POLICY
from orchestrator.core import Refusal, digest
import test_turn_recovery as base
from test_turn_recovery import Proxy, BRAIN, PROJECT, OTHER, TURN, COMMAND


class TurnHostContinuityTest(unittest.TestCase):
    setUp_base = base.TurnRecoveryTest.setUp
    tearDown = base.TurnRecoveryTest.tearDown
    preview = base.TurnRecoveryTest.preview
    confirm = base.TurnRecoveryTest.confirm
    reconcile = base.TurnRecoveryTest.reconcile
    change = base.TurnRecoveryTest.change

    def setUp(self):
        self.setUp_base()
        self.binding["brains"][BRAIN]["nativePolicy"] = copy.deepcopy(NATIVE_APPROVAL_POLICY)
        self.binding["brains"][BRAIN]["catalogProjectId"] = PROJECT
        self.binding["endpoint"] = {"executable": "/fixture/native", "sha256": "a"*64,
            "socket": "/fixture/old.sock", "serverIdentityHash": "b"*64,
            "socketIdentity": {"device": 7, "inode": 8, "owner": 9, "mode": 384,
                               "changedNs": 1791600000123456789}}
        self.old = copy.deepcopy(self.binding)
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", COMMAND)
            command["notification"]["hostBindingHash"] = digest(self.old)
            command["notification"]["nativeResumeProfile"]["bindingHash"] = digest(self.old)
            self.ledger.put(db, "commands", COMMAND, command)
        self.binding["endpoint"]["socket"] = "/fixture/candidate.sock"
        self.binding["endpoint"]["socketIdentity"]["inode"] = 18
        self.retired = {"version": 1, "bindingHash": digest(self.old), "processId": 12345, "launchClaimHash": "c"*64}
        self.controls = recovery.TurnRecoveryControls(self.old, self.retired)
        self.patches.append(patch.object(continuity, "process_absent", return_value=True))
        self.patches[-1].start()
        Proxy.turn_status, Proxy.ended_activity = "interrupted", "idle"

    def test_replacement_only_reads_preserves_original_and_private_integer_pins(self):
        before = recovery.saved_state(self.ledger)
        proposal = self.preview()
        doc = proposal["document"]
        self.assertEqual(doc["action"], "reconcile_ended_turn_on_reviewed_host")
        self.assertEqual(doc["originalBindingHash"], digest(self.old))
        self.assertIn("No cancellation", doc["boundary"])
        self.assertIsInstance(doc["hostContinuity"]["previousBinding"]["endpoint"]["socketIdentity"]["changedNs"], str)
        roundtrip = json.loads(subprocess.check_output(["node", "-e",
            "process.stdin.on('data', x => process.stdout.write(JSON.stringify(JSON.parse(x))))"],
            input=json.dumps(proposal).encode()))
        self.assertEqual(self.confirm(roundtrip)["status"], "controller_recovered")
        after = recovery.saved_state(self.ledger)
        entry = after["commands"][0]["notification"]["turnRecovery"]
        self.assertEqual(entry["hostContinuity"]["previousBinding"], self.old)
        self.assertEqual(entry["hostContinuity"]["candidateBinding"], self.binding)
        self.assertEqual(entry["delivery"], "not_needed")
        original = copy.deepcopy(after["commands"][0]); original["notification"].pop("turnRecovery")
        self.assertEqual(original, before["commands"][0])
        for key in ("expiresAt", "usageHighWater", "phaseId", "tasks", "merges"):
            self.assertEqual(before["meta"]["standardRun"][key], after["meta"]["standardRun"][key])
        self.assertNotIn("checkpoint", after["meta"]["standardRun"])
        self.assertFalse(entry["observation"]["taskTreeComplete"])
        self.assertEqual(entry["observation"]["effectOutcome"], "unknown")
        self.assertEqual(Proxy.interrupts, 0)
        self.assertTrue(all(m in ("project/read", "thread/read", "thread/turns/list", "thread/backgroundTerminals/list")
                            for m, _ in Proxy.calls))
        calls = list(Proxy.calls)
        self.controls.prior_binding = None
        self.wake.binding = None
        self.assertEqual(self.confirm(roundtrip)["status"], "controller_recovered")
        self.assertEqual(self.reconcile()["status"], "controller_recovered")
        self.assertEqual(Proxy.calls, calls, "Historical HTTP replay never inspects either endpoint")

    def test_old_endpoint_is_historical_never_validated_or_connected(self):
        with patch.object(recovery, "validate_endpoint") as endpoint:
            self.preview()
        self.assertTrue(endpoint.call_args_list)
        self.assertTrue(all(call.args[0] == self.binding["endpoint"] for call in endpoint.call_args_list))
        with patch("orchestrator.app_server_wake.validate_endpoint", side_effect=AssertionError("Old endpoint inspected")):
            path = self.root / "old-binding.json"
            path.write_text(json.dumps(self.old)); path.chmod(0o600)
            self.assertEqual(continuity.load_previous(path), self.old)

    def test_absent_wrong_historical_bytes_or_foreign_mapping_fail_before_native_reads(self):
        candidates = [None, {}, {**self.old, "endpoint": {"different": True}}]
        wrong = copy.deepcopy(self.old); wrong["brains"][BRAIN]["cwd"] = "/different"
        candidates.append(wrong)
        for old in candidates:
            self.controls.prior_binding = old
            Proxy.calls = []
            with self.subTest(old=old), self.assertRaises(Refusal): self.preview()
            self.assertEqual(Proxy.calls, [])

    def test_unloaded_active_unknown_terminal_or_new_turn_is_not_reconciled(self):
        for status, activity, page in (("inProgress", "idle", {"data": [], "nextCursor": None}),
                                      ("interrupted", "idle", {}),
                                      ("interrupted", "idle", {"data": [], "nextCursor": "more"}),
                                      ("interrupted", "idle", {"data": [{"processId": "42"}], "nextCursor": None})):
            Proxy.turn_status, Proxy.ended_activity, Proxy.terminals = status, activity, page
            with self.subTest(status=status, activity=activity, page=page), self.assertRaises(Refusal): self.preview()
        Proxy.turn_status, Proxy.ended_activity = "interrupted", "idle"
        Proxy.terminals = {"data": [], "nextCursor": None}
        Proxy.turns = {"data": [{"id": OTHER, "status": "completed"}], "nextCursor": None}
        with self.assertRaises(Refusal): self.preview()
        self.assertEqual(Proxy.interrupts, 0)
        self.assertIsNotNone(recovery.saved_state(self.ledger)["meta"]["controller"])

    def test_profile_or_either_project_identity_must_remain_identical(self):
        row = self.binding["brains"][BRAIN]
        for key, value in (("projectId", OTHER), ("catalogProjectId", OTHER), ("workspaceId", "other"),
                           ("cwd", "/different"), ("nativePolicy", {"sandbox": "danger-full-access"})):
            before = copy.deepcopy(row)
            row[key] = value
            with self.subTest(key=key), self.assertRaises((Refusal, OSError)): self.preview()
            row.clear(); row.update(before)
        self.assertEqual(Proxy.interrupts, 0)

    def test_already_claimed_original_host_cancellation_cannot_migrate(self):
        self.wake.binding = self.old
        self.controls = recovery.TurnRecoveryControls()
        Proxy.turn_status, Proxy.end_after_interrupt = "inProgress", False
        self.assertEqual(self.confirm(self.preview())["status"], "awaiting_end")
        Proxy.turn_status = "interrupted"
        self.wake.binding = self.binding
        self.controls.prior_binding = self.old
        self.controls.retired_host = self.retired
        self.assertEqual(self.reconcile()["status"], "awaiting_end")
        self.assertIsNotNone(recovery.saved_state(self.ledger)["meta"]["controller"])
        self.assertEqual(Proxy.interrupts, 1, "A consumed original cancellation never gains a replacement attempt")

    def test_new_activity_after_preview_and_during_terminal_reads_refuses_claim(self):
        proposal = self.preview()
        Proxy.turn_status = "completed"
        with self.assertRaises(Refusal): self.confirm(proposal)
        Proxy.turn_status = "interrupted"
        Proxy.on_enter = lambda: self.controls.prior_binding["endpoint"].update(sha256="c"*64)
        with self.assertRaises(Refusal): self.confirm(proposal)
        self.assertNotIn("turnRecovery", recovery.saved_state(self.ledger)["commands"][0]["notification"])

    def test_changed_browser_pins_even_when_signed_refuse_before_native_io(self):
        proposal = self.preview()
        proposal["document"]["hostContinuity"]["previousBinding"]["endpoint"]["socketIdentity"]["changedNs"] = 1
        proposal["signature"] = self.controls.sign(proposal["document"])
        Proxy.calls = []
        with self.assertRaises(Refusal): self.confirm(proposal)
        self.assertEqual(Proxy.calls, [])

    def test_original_host_live_reused_unknown_or_changed_provenance_refuses_release(self):
        with patch.object(continuity, "process_absent", return_value=False):
            with self.assertRaises(Refusal): self.preview()
        proposal = self.preview()
        self.controls.retired_host["processId"] += 1
        with self.assertRaises(Refusal): self.confirm(proposal)
        self.controls.retired_host = copy.deepcopy(self.retired)
        self.controls.retired_host["bindingHash"] = "d"*64
        with self.assertRaises(Refusal): self.preview()
        self.assertIsNotNone(recovery.saved_state(self.ledger)["meta"]["controller"])

    def test_retirement_drift_during_confirmation_is_fenced_before_claim(self):
        proposal = self.preview()
        Proxy.on_enter = lambda: self.controls.retired_host.update(processId=23456)
        with self.assertRaises(Refusal): self.confirm(proposal)
        self.assertNotIn("turnRecovery", recovery.saved_state(self.ledger)["commands"][0]["notification"])

    def test_unknown_candidate_does_not_claim_or_turn_on_native_tools(self):
        Proxy.unavailable = True
        with self.assertRaises(OSError): self.preview()
        self.assertNotIn("turnRecovery", recovery.saved_state(self.ledger)["commands"][0]["notification"])
        self.assertEqual(Proxy.interrupts, 0)


class ContinuityServerTest(unittest.TestCase):
    request = base.TurnRecoveryServerTest.request
    login = base.TurnRecoveryServerTest.login
    auth = base.TurnRecoveryServerTest.auth
    path = base.TurnRecoveryServerTest.path

    def setUp(self):
        TurnHostContinuityTest.setUp(self)
        from orchestrator.server import Dashboard
        import threading
        self.server = Dashboard(self.ledger, 0, self.root / ".env", registry=self.registry,
            turn_recovery_prior_binding=self.old, turn_recovery_retired_host=self.retired)
        self.server.runtime_for("pilot").notifier.app_server = self.wake
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        TurnHostContinuityTest.tearDown(self)

    setUp_base = base.TurnRecoveryTest.setUp

    def test_registered_runtime_wire_confirmation_and_read_only_history(self):
        auth = self.auth()
        with patch.object(continuity, "process_absent", side_effect=AssertionError("Polling collected evidence")):
            status, _, raw = self.request(self.path(), headers=auth)
        self.assertEqual(status, 200, raw)
        self.assertIn(b"read-only recovery", raw)
        status, _, raw = self.request(self.path("/preview"), {"commandId": COMMAND}, auth)
        self.assertEqual(status, 200, raw)
        body = {"proposal": json.loads(raw), "confirmed": True}
        status, _, raw = self.request(self.path("/confirm"), body, auth)
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["status"], "controller_recovered")
        with patch.object(continuity, "process_absent", side_effect=AssertionError("Replay collected evidence")):
            status, _, raw = self.request(self.path("/confirm"), body, auth)
        self.assertEqual(status, 200, raw)
        self.assertEqual(Proxy.interrupts, 0)


class RetirementTest(unittest.TestCase):
    def test_only_exact_absence_on_fixed_ps_read_is_accepted(self):
        with patch.object(continuity.subprocess, "run") as run:
            for code, stdout, stderr, expected in ((1, b"", b"", True), (0, b"12345\n", b"", False),
                                                  (2, b"", b"", False), (1, b"", b"failure", False)):
                run.return_value = subprocess.CompletedProcess([], code, stdout, stderr)
                self.assertEqual(continuity.process_absent(12345), expected)
            self.assertEqual(run.call_args.args[0], ["/bin/ps", "-p", "12345", "-o", "pid="])
        for error in (OSError("Unavailable"), subprocess.TimeoutExpired("ps", 5)):
            with patch.object(continuity.subprocess, "run", side_effect=error):
                self.assertFalse(continuity.process_absent(12345))
        for pid in (True, 1, 0, -1, "12345", 2**31):
            with self.assertRaises(Refusal): continuity.validate_retired(
                {"version": 1, "bindingHash": "a"*64, "launchClaimHash": "b"*64, "processId": pid})


if __name__ == "__main__":
    unittest.main()
