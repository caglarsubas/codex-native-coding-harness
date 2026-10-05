import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid

from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from orchestrator.workspaces import Registry
import test_server

BRAIN = "11111111-1111-4111-8111-111111111111"
REQUEST = "b" * 64


class Wake:
    def __init__(self, command_id):
        self.calls = []
        self.pending = {"commandId": command_id, "brainId": BRAIN, "turnId": "turn-1",
                        "itemId": "item-1", "requestId": 19,
                        "method": "item/commandExecution/requestApproval", "requestHash": REQUEST,
                        "observedAt": time.time(), "expiresAt": time.time() + 600,
                        "canAccept": False, "allowedDecisions": ["accept", "decline", "cancel"],
                        "request": {"command": "PRIVATE fixture command", "cwd": "/fixture"},
                        "item": None}

    def configured(self, brain_id):
        return brain_id == BRAIN

    def connection_status(self, brain_id):
        return {"status": "unchecked", "checkedAt": None, "detail": "Synthetic host, not checked."}

    def pending_approval(self, brain_id):
        return self.pending if brain_id == BRAIN else None

    def confirm_approval(self, brain_id, command_id, request_hash, decision):
        self.calls.append((brain_id, command_id, request_hash, decision))
        return {"status": "queued"}


class NativeApprovalServerTest(unittest.TestCase):
    request = test_server.ServerTest.request
    login = test_server.ServerTest.login

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.registry = Registry(self.root / "platform", create=True)
        self.ledgers = {}
        for wid in ("a", "b"):
            ledger = Ledger(self.root / wid)
            ledger.initialize({"schemaVersion": 1, "brainId": BRAIN if wid == "a" else str(uuid.uuid4()),
                               "repositories": [{"id": "fixture", "path": "/fixture", "projectId": None,
                                                 "ref": "main", "mergePolicy": "manual",
                                                 "policyProfile": "standard"}]})
            self.registry.register(wid, "Project " + wid, ledger.root)
            self.ledgers[wid] = ledger
        ledger = self.registry.ledger("a")
        self.command = ledger.submit({"id": str(uuid.uuid4()), "kind": "pause",
                                      "expectedRevision": ledger.snapshot()["meta"]["revision"], "payload": {}})
        with ledger.tx() as db:
            command = ledger.get(db, "commands", self.command["id"])
            command["notification"] = {"status": "accepted", "brainId": BRAIN,
                                       "nativeTurnId": "turn-1", "nativeDelivery": "owned_turn_start"}
            ledger.put(db, "commands", command["id"], command)
        self.server = Dashboard(self.ledgers["a"], 0, self.root / ".env", registry=self.registry)
        self.wake = Wake(self.command["id"])
        self.server.runtime_for("a").notifier.app_server = self.wake
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def auth(self, wid, session=None):
        auth = session or self.login()
        status, _, body = self.request(f"/api/workspaces/{wid}/session", headers=auth)
        self.assertEqual(status, 200)
        return auth | {"X-CSRF-Token": json.loads(body)["csrf"]}

    def path(self, suffix="", wid="a"):
        return f"/api/workspaces/{wid}/native-permission" + suffix

    def test_owner_only_exact_preview_confirmation_and_isolation(self):
        self.assertEqual(self.request(self.path())[0], 401)
        auth = self.auth("a")
        status, _, raw = self.request(self.path(), headers=auth)
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["pending"]["request"]["command"], "PRIVATE fixture command")
        _, _, other = self.request(self.path(wid="b"), headers=self.auth("b", auth))
        self.assertNotIn(b"PRIVATE fixture command", other)
        request = {"commandId": self.command["id"], "requestHash": REQUEST, "decision": "decline"}
        self.assertEqual(self.request(self.path("/preview"), request)[0], 403)
        status, _, raw = self.request(self.path("/preview"), request, auth)
        self.assertEqual(status, 200, raw)
        proposal = json.loads(raw)
        self.assertEqual(self.request(self.path("/confirm"),
                                      {"proposal": proposal, "confirmed": True},
                                      auth | {"X-CSRF-Token": "wrong"})[0], 403)
        self.assertEqual(self.request(self.path("/confirm"),
                                      {"proposal": proposal, "confirmed": True},
                                      self.auth("a"))[0], 409)
        self.assertEqual(self.wake.calls, [])
        status, _, raw = self.request(self.path("/confirm"),
                                      {"proposal": proposal, "confirmed": True}, auth)
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["status"], "queued")
        self.assertEqual(self.wake.calls, [(BRAIN, self.command["id"], REQUEST, "decline")])
        self.assertEqual(self.request(self.path("/confirm"),
                                      {"proposal": proposal, "confirmed": True}, auth)[0], 409)
        state = json.loads(self.request("/api/workspaces/a/state", headers=auth)[2])
        self.assertNotIn("PRIVATE fixture command", json.dumps(state))

    def test_no_arbitrary_native_method_or_cross_project_confirmation(self):
        auth = self.auth("a")
        for suffix in ("/send", "/replay", "/resume", "/raw"):
            self.assertEqual(self.request(self.path(suffix), {}, auth)[0], 404)
        self.assertEqual(self.request(self.path("/preview"),
                                      {"commandId": self.command["id"], "requestHash": REQUEST,
                                       "decision": "accept"}, auth)[0], 409)
        self.assertEqual(self.request(self.path("/preview"),
                                      {"commandId": self.command["id"], "requestHash": REQUEST,
                                       "decision": "decline"}, self.auth("b", auth))[0], 403)
        self.assertEqual(self.wake.calls, [])

    def test_owner_can_confirm_exact_accept_only_during_running_phase(self):
        self.wake.pending["canAccept"] = True
        ledger = self.server.runtime_for("a").ledger
        with ledger.tx() as db:
            meta = ledger.get(db, "meta", 1)
            meta["standardRun"] = {"status": "running"}
            ledger.put(db, "meta", 1, meta)
        auth = self.auth("a")
        status, _, raw = self.request(self.path(), headers=auth)
        self.assertEqual(status, 200, raw)
        self.assertTrue(json.loads(raw)["pending"]["canAccept"])
        request = {"commandId": self.command["id"], "requestHash": REQUEST,
                   "decision": "accept"}
        status, _, raw = self.request(self.path("/preview"), request, auth)
        self.assertEqual(status, 200, raw)
        proposal = json.loads(raw)
        status, _, raw = self.request(self.path("/confirm"),
                                      {"proposal": proposal, "confirmed": True}, auth)
        self.assertEqual(status, 200, raw)
        self.assertEqual(self.wake.calls, [(BRAIN, self.command["id"], REQUEST, "accept")])


if __name__ == "__main__": unittest.main()
