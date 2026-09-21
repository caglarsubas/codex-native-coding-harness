import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from orchestrator.core import Ledger, Refusal
from orchestrator import conversation
from orchestrator.decisions import inbox, publish
from orchestrator.notification import BrainNotifier
from test_decisions import fixture

BRAIN = "11111111-1111-4111-8111-111111111111"


def envelope(ledger, **payload):
    return {"id": str(uuid.uuid4()), "kind": "reconcile",
            "expectedRevision": ledger.snapshot()["meta"]["revision"],
            "payload": {"message": "Private direction\n<script>not markup</script>", "brainId": BRAIN, "confirmed": True, **payload}}


class ConversationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "state")
        self.spec = fixture(self.ledger, BRAIN)
        self.token = self.ledger.acquire(BRAIN + ":conversation-test")
        self.answer = {"message": "Answer with an explicit evidence gap.", "artifactIds": self.spec["artifactIds"], "decisionIds": []}

    def tearDown(self):
        self.tmp.cleanup()

    def test_durable_reply_exact_replay_no_execution_authority(self):
        before = self.ledger.snapshot()
        request = envelope(self.ledger)
        command = self.ledger.submit(request)
        self.assertEqual(self.ledger.submit(request), command)
        self.assertEqual(self.ledger.process(self.token)[0]["kind"], "brain_message")
        self.assertEqual(self.ledger.process(self.token), [])
        self.assertEqual(conversation.read(self.ledger)["pending"], 1)
        with self.assertRaises(Refusal): self.ledger.acknowledge(self.token, command["id"], True, "Not a reply")
        result = conversation.reply(self.ledger, self.token, command["id"], self.answer)
        self.assertEqual(conversation.reply(self.ledger, self.token, command["id"], self.answer), result)
        with self.assertRaises(Refusal): conversation.reply(self.ledger, self.token, command["id"], {**self.answer, "message": "Changed"})
        data = conversation.read(Ledger(self.ledger.root))
        self.assertEqual(data["pending"], 0)
        self.assertEqual(data["messages"][0]["message"], request["payload"]["message"])
        self.assertEqual(data["messages"][0]["reply"]["message"], self.answer["message"])
        self.assertNotIn(self.token, json.dumps(data))
        after = self.ledger.snapshot()
        for key in ("paused", "concurrency", "pilotPassed", "heartbeat", "runner"):
            self.assertEqual(before["meta"][key], after["meta"][key])
        for key in ("workers", "queue"):
            self.assertEqual(before[key], after[key])

    def test_closed_validation_and_one_pending_message(self):
        for change in ({"message": ""}, {"message": " "}, {"message": "x" * 8001}, {"message": 7},
                       {"message": "bad\x00"}, {"confirmed": 1}, {"confirmed": False}, {"brainId": "other"}, {"shell": "x"}):
            with self.subTest(change=str(change)[:40]), self.assertRaises(Refusal):
                self.ledger.submit(envelope(self.ledger, **change))
        with self.assertRaises(Refusal): self.ledger.submit(envelope(self.ledger), actor="assistant_owner_confirmed")
        request = envelope(self.ledger)
        self.ledger.submit(request)
        with self.assertRaises(Refusal): self.ledger.submit(envelope(self.ledger))
        # A ordinary reconcile does not consume or suppress the message.
        self.ledger.submit({**envelope(self.ledger), "payload": {}})
        conflict = copy.deepcopy(request); conflict["payload"]["message"] = "Changed retry"
        with self.assertRaises(Refusal): self.ledger.submit(conflict)

    def test_no_forged_reply_wrong_controller_or_foreign_references(self):
        command = self.ledger.submit(envelope(self.ledger))
        with self.assertRaises(Refusal): conversation.reply(self.ledger, self.token, command["id"], self.answer)
        with self.assertRaises(Refusal): conversation.receive(self.ledger, "wrong", command["id"])
        conversation.receive(self.ledger, self.token, command["id"])
        for change in ({"artifactIds": ["a" * 64]}, {"decisionIds": ["b" * 64]}, {"message": "x" * 12001}, {"message": "\x00"}, {"extra": True}):
            with self.subTest(change=str(change)[:50]), self.assertRaises(Refusal):
                conversation.reply(self.ledger, self.token, command["id"], {**self.answer, **change})
        decision = publish(self.ledger, self.token, self.spec)
        conversation.reply(self.ledger, self.token, command["id"], {**self.answer, "decisionIds": [decision["id"]]})

    def test_old_helper_completion_is_not_a_reply_and_can_be_received(self):
        command = self.ledger.submit(envelope(self.ledger))
        with self.ledger.tx() as db:
            command.update(status="completed", result="Processed by old controller")
            self.ledger.put(db, "commands", command["id"], command)
        self.assertEqual(conversation.read(self.ledger)["pending"], 1)
        self.assertTrue(any(c["id"] == command["id"] for c in inbox(self.ledger.snapshot())["commands"]))
        conversation.receive(self.ledger, self.token, command["id"])
        conversation.reply(self.ledger, self.token, command["id"], self.answer)
        self.assertEqual(conversation.read(self.ledger)["pending"], 0)

    def test_stop_saves_without_wake_and_resume_points_at_reply_protocol(self):
        self.ledger.submit({**envelope(self.ledger), "kind": "brain_stop", "payload": {}})
        command = self.ledger.submit(envelope(self.ledger))
        notifier = BrainNotifier(self.ledger, sys.executable)
        ack = subprocess.CompletedProcess([], 0, f"Queued message 22222222-2222-4222-8222-222222222222 for thread {BRAIN}.", "")
        with patch("orchestrator.notification.subprocess.run", return_value=ack) as run:
            notifier.notify(command["id"])
            run.assert_not_called()
            with self.assertRaises(Refusal): conversation.receive(self.ledger, self.token, command["id"])
            resume = self.ledger.submit({**envelope(self.ledger), "kind": "brain_resume", "payload": {}})
            notifier.notify(resume["id"])
            message = run.call_args.args[0][-1]
            self.assertIn("references/conversation.md", message)
            self.assertIn("kind brain_resume", message)
            self.assertNotIn("Private direction", message)
            self.assertNotIn(self.token, message)
            notifier.notify(resume["id"])
            run.assert_called_once()
        self.ledger.process(self.token)
        self.assertEqual(conversation.read(self.ledger)["pending"], 1)

    def test_notification_one_shot_is_not_receipt(self):
        command = self.ledger.submit(envelope(self.ledger))
        with patch("orchestrator.notification.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 8)) as run:
            notifier = BrainNotifier(self.ledger, sys.executable)
            self.assertEqual(notifier.notify(command["id"])["notification"]["status"], "uncertain")
            notifier.notify(command["id"])
            run.assert_called_once()
            self.assertNotIn("Private direction", run.call_args.args[0][-1])
        self.assertIsNone(conversation.read(self.ledger)["messages"][0]["receivedAt"])

    def test_pagination_order_and_invalid_pages(self):
        for number in range(32):
            command = self.ledger.submit(envelope(self.ledger, message=str(number)))
            conversation.receive(self.ledger, self.token, command["id"])
            conversation.reply(self.ledger, self.token, command["id"], self.answer)
        latest = conversation.read(self.ledger)
        self.assertEqual([m["message"] for m in latest["messages"]], list(map(str, range(2, 32))))
        self.assertTrue(latest["hasOlder"])
        self.assertEqual([m["message"] for m in conversation.read(self.ledger, 1)["messages"]], ["0", "1"])
        for page in (-1, True, 1_000_001):
            with self.assertRaises(Refusal): conversation.read(self.ledger, page)

    def test_inference_context_withholds_owner_message_and_reply(self):
        from orchestrator.assistant import context
        command = self.ledger.submit(envelope(self.ledger))
        conversation.receive(self.ledger, self.token, command["id"])
        conversation.reply(self.ledger, self.token, command["id"], self.answer)
        data = json.dumps(context(self.ledger.snapshot(), "conversation"))
        self.assertNotIn("Private direction", data)
        self.assertNotIn(self.answer["message"], data)
