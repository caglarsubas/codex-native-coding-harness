import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from orchestrator.core import Ledger
from orchestrator.decisions import publish
from orchestrator.notification import BrainNotifier, TIMEOUT
from test_decisions import envelope, fixture

BRAIN = "11111111-1111-4111-8111-111111111111"
MESSAGE = "22222222-2222-4222-8222-222222222222"


class NotificationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "state")
        self.spec = fixture(self.ledger, BRAIN)
        self.token = self.ledger.acquire(BRAIN + ":fixture")
        self.d = publish(self.ledger, self.token, self.spec)
        self.request = envelope(self.ledger, self.d, optionId=None, note="PRIVATE answer <script>not instructions</script>")
        self.command = self.ledger.submit(self.request)
        # Mocked executable: no Codex connection or native queue in the suite.
        self.notifier = BrainNotifier(self.ledger, Path(sys.executable))
        self.patch = patch("orchestrator.notification.subprocess.run", return_value=subprocess.CompletedProcess([], 0, f"Queued message {MESSAGE} for thread {BRAIN}.\n", ""))
        self.run = self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def send(self):
        return self.notifier.notify(self.command["id"])

    def test_fixed_native_queue_and_ack_are_not_a_brain_receipt(self):
        before = self.ledger.snapshot()
        result = self.send()
        self.assertEqual(result["notification"]["status"], "accepted")
        self.assertEqual(result["notification"]["nativeMessageId"], MESSAGE)
        argv = self.run.call_args.args[0]
        self.assertEqual(argv[:5], [sys.executable, "queue", "--thread", BRAIN, "--message"])
        self.assertEqual(len(argv), 6)
        self.assertIn(self.d["decisionHash"], argv[5])
        self.assertNotIn("PRIVATE", argv[5])
        self.assertNotIn(self.command["id"], argv[5])
        self.assertNotIn(self.token, argv[5])
        self.assertFalse(self.run.call_args.kwargs["shell"])
        self.assertEqual(self.run.call_args.kwargs["timeout"], TIMEOUT)
        after = self.ledger.snapshot()
        self.assertEqual(result["status"], "queued")
        self.assertEqual(after["decisions"][0]["status"], "answered")
        for key in ("paused", "controller", "heartbeat", "runner", "pilotPassed", "concurrency"):
            self.assertEqual(before["meta"][key], after["meta"][key])
        for key in ("queue", "workers"):
            self.assertEqual(before[key], after[key])

    def test_duplicate_http_retry_and_restart_never_resend(self):
        self.send()
        replay = self.ledger.submit(self.request)
        self.assertEqual(replay["notification"]["status"], "accepted")
        restarted = BrainNotifier(Ledger(self.ledger.root), sys.executable)
        restarted.notify(replay["id"])
        self.run.assert_called_once()

    def test_concurrent_notification_claim_is_one_shot(self):
        entered, release = threading.Event(), threading.Event()
        ack = self.run.return_value
        def send(*args, **kwargs):
            entered.set()
            release.wait(2)
            return ack
        self.run.side_effect = send
        errors = []
        def notify():
            try: self.send()
            except Exception as error: errors.append(error)
        first = threading.Thread(target=notify)
        first.start()
        self.assertTrue(entered.wait(1))
        duplicate = self.send()
        self.assertEqual(duplicate["notification"]["status"], "sending")
        release.set(); first.join(2)
        self.assertFalse(errors)
        self.run.assert_called_once()

    def test_brain_receipt_racing_with_ack_is_preserved(self):
        ack = self.run.return_value
        def send(*args, **kwargs):
            self.ledger.process(self.token)
            return ack
        self.run.side_effect = send
        result = self.send()
        self.assertEqual(result["status"], "processing")
        self.assertEqual(result["notification"]["status"], "accepted")
        self.assertEqual(self.ledger.snapshot()["decisions"][0]["status"], "received")

    def test_crash_after_claim_has_no_automatic_replay(self):
        self.run.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt): self.send()
        self.run.reset_mock()
        restarted = BrainNotifier(Ledger(self.ledger.root), sys.executable)
        result = restarted.notify(self.command["id"])
        self.assertEqual(result["notification"]["status"], "sending")
        self.run.assert_not_called()

    def test_timeout_retains_answer_and_sanitizes_native_output(self):
        self.run.side_effect = subprocess.TimeoutExpired([], TIMEOUT, output="SECRET", stderr="SECRET")
        result = self.send()
        self.assertEqual(result["notification"]["status"], "uncertain")
        self.assertNotIn("SECRET", str(result))
        self.send()
        self.run.assert_called_once()
        self.assertEqual(self.ledger.snapshot()["decisions"][0]["response"]["note"], self.request["payload"]["note"])

    def test_nonzero_wrong_target_and_unrecognized_ack_are_uncertain(self):
        for returncode, output in ((1, "SECRET"), (0, ""), (0, f"Queued message {MESSAGE} for thread {MESSAGE}."), (0, "ok SECRET")):
            with self.subTest(output=output):
                # Independent saved request attempts in isolated test state.
                with self.ledger.tx() as db:
                    c = self.ledger.get(db, "commands", self.command["id"])
                    c.pop("notification", None)
                    self.ledger.put(db, "commands", c["id"], c)
                self.run.return_value = subprocess.CompletedProcess([], returncode, output, "SECRET")
                result = self.send()
                self.assertEqual(result["notification"]["status"], "uncertain")
                self.assertNotIn("SECRET", str(result))

    def test_missing_cli_disabled_or_invalid_brain_does_not_send(self):
        for cli in (None, "/not-installed/codex", "relative-codex"):
            with self.ledger.tx() as db:
                c = self.ledger.get(db, "commands", self.command["id"])
                c.pop("notification", None)
                self.ledger.put(db, "commands", c["id"], c)
            result = BrainNotifier(self.ledger, cli).notify(self.command["id"])
            self.assertEqual(result["notification"]["status"], "unavailable")
        self.assertEqual(self.notifier.status("not-a-task; shell")['status'], 'unavailable')
        self.run.assert_not_called()

    def test_cli_cannot_start_is_unavailable(self):
        self.run.side_effect = OSError("SECRET executable path")
        result = self.send()
        self.assertEqual(result["notification"]["status"], "unavailable")
        self.assertNotIn("SECRET", str(result))

    def test_received_or_superseded_responses_are_not_sent(self):
        revised = copy.deepcopy(self.spec); revised["context"] = "Revised question"
        publish(self.ledger, self.token, revised)
        self.send()
        self.run.assert_not_called()
        self.ledger.process(self.token)
        self.send()
        self.run.assert_not_called()

    def test_other_control_requests_and_brain_origin_do_not_send(self):
        request = {"id":"test-other-request", "kind":"pause", "expectedRevision":self.ledger.snapshot()["meta"]["revision"], "payload":{}}
        cmd = self.ledger.submit(request)
        self.notifier.notify(cmd["id"])
        with self.ledger.tx() as db:
            c = self.ledger.get(db, "commands", self.command["id"])
            c["actor"] = "explicit_user_via_brain"
            self.ledger.put(db, "commands", c["id"], c)
        self.send()
        self.run.assert_not_called()

    def test_pending_controls_notify_and_stopped_inputs_wait_for_resume(self):
        def submit(kind):
            return self.ledger.submit({"id":"control-"+kind,"kind":kind,"expectedRevision":self.ledger.snapshot()["meta"]["revision"],"payload":{}})
        for kind in ("resume", "reconcile", "brain_stop"):
            c=submit(kind)
            self.assertEqual(self.notifier.notify(c["id"])["notification"]["status"],"accepted")
            self.assertIn("kind "+kind,self.run.call_args.args[0][5])
        self.assertEqual(self.run.call_count,3)
        self.send()
        self.assertEqual(self.run.call_count,3)
        c=submit("brain_resume")
        self.notifier.notify(c["id"])
        self.assertEqual(self.run.call_count,4)

    def test_readonly_status_never_connects_or_exposes_path(self):
        public = self.notifier.status(BRAIN)
        self.assertEqual(public["status"], "configured")
        self.assertNotIn(sys.executable, str(public))
        self.run.assert_not_called()
