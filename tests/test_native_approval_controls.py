from pathlib import Path
import tempfile
import time
import unittest
import uuid

from orchestrator.core import Ledger, Refusal
from orchestrator.native_approval_controls import NativeApprovalControls, inspect

BRAIN = "11111111-1111-4111-8111-111111111111"
REQUEST = "a" * 64


class FakeWake:
    def __init__(self, command_id):
        self.calls = []
        self.pending = {"commandId": command_id, "brainId": BRAIN, "turnId": "turn-1",
                        "itemId": "item-1", "requestId": 42,
                        "method": "item/commandExecution/requestApproval", "requestHash": REQUEST,
                        "observedAt": time.time(), "expiresAt": time.time() + 600,
                        "canAccept": False, "allowedDecisions": ["accept", "decline", "cancel"],
                        "request": {"command": "fixture --read-only", "cwd": "/fixture"},
                        "item": None}

    def configured(self, brain_id):
        return brain_id == BRAIN

    def pending_approval(self, brain_id):
        return self.pending if brain_id == BRAIN else None

    def confirm_approval(self, brain_id, command_id, request_hash, decision):
        self.calls.append((brain_id, command_id, request_hash, decision))
        return {"status": "queued"}


class NativeApprovalControlsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger = Ledger(Path(self.tmp.name) / "state")
        self.ledger.initialize({"schemaVersion": 1, "brainId": BRAIN, "repositories": [
            {"id": "fixture", "path": "/fixture", "projectId": None, "ref": "main",
             "mergePolicy": "manual", "policyProfile": "standard"}]})
        self.ledger.workspace_id = "fixture"
        self.command = self.ledger.submit({"id": str(uuid.uuid4()), "kind": "pause",
                                           "expectedRevision": self.ledger.snapshot()["meta"]["revision"],
                                           "payload": {}})
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", self.command["id"])
            command["notification"] = {"status": "accepted", "brainId": BRAIN,
                                       "nativeTurnId": "turn-1", "nativeDelivery": "owned_turn_start"}
            self.ledger.put(db, "commands", command["id"], command)
        self.wake = FakeWake(self.command["id"])
        self.controls = NativeApprovalControls()

    def request(self, decision="decline"):
        return {"commandId": self.command["id"], "requestHash": REQUEST, "decision": decision}

    def test_exact_decline_is_signed_and_one_shot(self):
        self.assertEqual(inspect(self.ledger, self.wake)["status"], "pending")
        proposal = self.controls.preview(self.ledger, self.wake, self.request(), "session-a")
        self.assertNotIn("fixture --read-only", str(self.ledger.snapshot()))
        with self.assertRaises(Refusal):
            self.controls.confirm(self.ledger, self.wake, {"proposal": proposal, "confirmed": True}, "session-b")
        self.assertEqual(self.wake.calls, [])
        result = self.controls.confirm(self.ledger, self.wake,
                                       {"proposal": proposal, "confirmed": True}, "session-a")
        self.assertEqual(result["status"], "queued")
        self.assertEqual(self.wake.calls, [(BRAIN, self.command["id"], REQUEST, "decline")])
        saved = next(c for c in self.ledger.snapshot()["commands"] if c["id"] == self.command["id"])
        self.assertEqual(saved["notification"]["nativeApprovals"][0]["status"], "queued")
        self.assertNotIn("fixture --read-only", str(saved))
        self.wake.pending = None
        self.assertEqual(inspect(self.ledger, self.wake)["status"], "response_claimed")
        with self.assertRaises(Refusal):
            self.controls.confirm(self.ledger, self.wake,
                                  {"proposal": proposal, "confirmed": True}, "session-a")
        self.assertEqual(len(self.wake.calls), 1)

    def test_missing_or_changed_request_refuses_without_native_response(self):
        proposal = self.controls.preview(self.ledger, self.wake, self.request(), "session-a")
        self.wake.pending = {**self.wake.pending, "request": {"command": "changed"}}
        with self.assertRaises(Refusal):
            self.controls.confirm(self.ledger, self.wake,
                                  {"proposal": proposal, "confirmed": True}, "session-a")
        self.wake.pending = None
        self.assertEqual(inspect(self.ledger, self.wake)["status"], "unavailable")
        self.assertEqual(self.wake.calls, [])

    def test_accept_fails_closed_without_complete_context_or_running_phase(self):
        with self.assertRaises(Refusal):
            self.controls.preview(self.ledger, self.wake, self.request("accept"), "session-a")
        self.wake.pending["canAccept"] = True
        with self.assertRaises(Refusal):
            self.controls.preview(self.ledger, self.wake, self.request("accept"), "session-a")
        self.assertEqual(self.wake.calls, [])

    def test_accept_requires_exact_running_phase_at_preview_and_confirmation(self):
        self.wake.pending["canAccept"] = True
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            self.assertTrue(meta["paused"])  # Standard mode keeps legacy dispatch paused.
            meta["standardRun"] = {"status": "running"}
            self.ledger.put(db, "meta", 1, meta)
        proposal = self.controls.preview(self.ledger, self.wake, self.request("accept"), "session-a")
        self.assertEqual(proposal["document"]["decision"], "accept")
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["standardRun"]["status"] = "stopping"
            self.ledger.put(db, "meta", 1, meta)
            self.ledger.event(db, "test_phase_stopping", {})
        self.assertFalse(inspect(self.ledger, self.wake)["pending"]["canAccept"])
        with self.assertRaises(Refusal):
            self.controls.confirm(self.ledger, self.wake,
                                  {"proposal": proposal, "confirmed": True}, "session-a")
        self.assertEqual(self.wake.calls, [])
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["standardRun"]["status"] = "running"
            self.ledger.put(db, "meta", 1, meta)
            self.ledger.event(db, "test_new_phase_authority", {})
        with self.assertRaises(Refusal):
            self.controls.confirm(self.ledger, self.wake,
                                  {"proposal": proposal, "confirmed": True}, "session-a")
        proposal = self.controls.preview(self.ledger, self.wake, self.request("accept"), "session-a")
        result = self.controls.confirm(self.ledger, self.wake,
                                       {"proposal": proposal, "confirmed": True}, "session-a")
        self.assertEqual(result["status"], "queued")
        self.assertEqual(self.wake.calls, [(BRAIN, self.command["id"], REQUEST, "accept")])

    def test_native_send_failure_remains_durable_uncertainty(self):
        proposal = self.controls.preview(self.ledger, self.wake, self.request("cancel"), "session-a")
        def fail(*_):
            raise OSError("PRIVATE socket error")
        self.wake.confirm_approval = fail
        result = self.controls.confirm(self.ledger, self.wake,
                                       {"proposal": proposal, "confirmed": True}, "session-a")
        self.assertEqual(result["status"], "uncertain")
        self.assertNotIn("PRIVATE", str(result))
        with self.assertRaises(Refusal):
            self.controls.confirm(self.ledger, self.wake,
                                  {"proposal": proposal, "confirmed": True}, "session-a")


if __name__ == "__main__":
    unittest.main()
