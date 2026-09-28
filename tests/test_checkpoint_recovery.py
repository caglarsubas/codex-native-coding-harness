import copy
import http.client
import json
import threading
import time
import unittest
from types import SimpleNamespace

from orchestrator import conversation, missions, standard
from orchestrator.assistant_actions import catalog, resolve_action
from orchestrator.assistant_journey import JourneyProposals
from orchestrator.checkpoint_recovery import KIND
from orchestrator.core import Refusal
from orchestrator.development_help import plan
from orchestrator.notification import BrainNotifier
from orchestrator.recovery import describe
import test_standard


class OwnedWake:
    def __init__(self):
        self.sent = []

    def configured(self, brain_id):
        return True

    def send(self, brain_id, message, command_id):
        self.sent.append((brain_id, message, command_id))
        return {"status": "accepted", "nativeDelivery": "owned_turn_start",
                "detail": "Bound native turn started; ledger receipt is separate."}

    def close(self):
        pass


class CheckpointRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_standard.StandardTest()
        self.fixture.setUp()
        self.ledger, self.registry = self.fixture.ledger, self.fixture.registry
        self.fixture.control()
        self.fixture.call("receive")
        self.fixture.call("checkpoint", outcome="paused", summary="Budget evidence needs review",
                          brainObservedTokens=None, reasonCodes=["usage_evidence"])
        self.ledger.release(self.fixture.token, "Paused checkpoint retained")
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            run = meta["standardRun"]
            run["expiresAt"] = time.time() - 1
            run["usageHighWater"] = 80_000
            standard.save(self.ledger, db, meta, run, "fixture_expired")
        self.native = OwnedWake()
        self.notifier = BrainNotifier(self.ledger)
        self.notifier.app_server = self.native
        self.runtime = SimpleNamespace(ledger=self.ledger, registry=self.registry,
                                       notifier=self.notifier, standard_controls=standard.Controls())
        self.proposals = JourneyProposals(self.runtime)

    def tearDown(self):
        self.fixture.tearDown()

    def snapshot(self):
        s = self.ledger.snapshot()
        s.update(workspace={"id": "alpha", "name": "Alpha"}, standard=standard.read(self.ledger),
                 mission=missions.read(self.ledger), brainNotification=self.notifier.status(s["meta"]["brainId"]))
        s["recovery"] = describe(s)
        return s

    def preview(self):
        s = self.snapshot()
        action = resolve_action({"key": "phase_recovery"}, catalog(s, {}), "phase_recovery")
        return self.proposals.prepare(action, s, "session")

    def confirm(self, proposal, session="session"):
        return self.proposals.confirm(self.ledger, {"proposal": proposal, "confirmed": True}, session)

    def test_saved_message_is_reused_one_shot_without_resuming_phase(self):
        before = standard.read(self.ledger)["run"]
        meta = self.ledger.snapshot()["meta"]
        saved = self.ledger.submit({"id": "saved-recovery-message", "kind": "reconcile",
                                    "expectedRevision": meta["revision"],
                                    "payload": {"brainId": meta["brainId"], "message": "Explain this checkpoint and prepare a safe successor.",
                                                "confirmed": True}}, actor="dashboard")
        self.assertNotIn("notification", saved)
        self.assertEqual(plan(self.snapshot())["key"], "phase_recovery")
        proposal = self.preview()
        self.assertTrue(proposal["document"]["preview"]["recovery"]["reusesMessage"])
        self.assertEqual(proposal["document"]["request"]["messageId"], saved["id"])
        result, first = self.confirm(proposal)
        self.assertTrue(first)
        command = result["result"]
        self.assertEqual(command["kind"], KIND)
        current = standard.read(self.ledger)["run"]
        self.assertEqual(current["status"], "paused")
        self.assertEqual(current["limits"], before["limits"])
        self.assertEqual(current["brainAllowance"], before["brainAllowance"])
        self.assertEqual(current["usageHighWater"], before["usageHighWater"])
        self.assertEqual(sum(c["kind"] == "reconcile" and "message" in c["payload"]
                             for c in self.ledger.snapshot()["commands"]), 1)
        self.notifier.notify(command["id"])
        self.notifier.notify(command["id"])
        self.assertEqual(len(self.native.sent), 1)
        self.assertIn("not phase Resume", self.native.sent[0][1])
        self.assertNotIn(saved["payload"]["message"], self.native.sent[0][1], "Message text stays out of native argv")
        token = self.ledger.acquire(meta["brainId"] + ":recovery")
        with self.assertRaises(Refusal):
            conversation.receive(self.ledger, token, saved["id"])
        self.fixture.call("recovery_receive", token=token, requestId=command["id"])
        received = self.ledger.snapshot()["commands"]
        self.assertTrue(next(c for c in received if c["id"] == saved["id"])["conversationReceivedAt"])
        with self.assertRaises(Refusal):
            self.fixture.call("claim", token=token, id="another", repository="a", title="No worker",
                              paths=["tests/test_fixture.py"], instructions="No", acceptance=["No"],
                              model="fixture", effort="low", rationale="No", allowance=1000)
        conversation.reply(self.ledger, token, saved["id"],
                           {"message": "Usage incomplete; draft needs review.", "artifactIds": [], "decisionIds": []})
        after = standard.read(self.ledger)["run"]
        self.assertEqual(after["recovery"]["status"], "replied")
        self.assertEqual(after["status"], "paused")
        self.assertEqual(next(c for c in self.ledger.snapshot()["commands"] if c["id"] == command["id"])["status"], "completed")
        self.assertFalse(self.confirm(proposal)[1], "Exact confirmation replay returns the old receipt")
        self.assertEqual(len(self.native.sent), 1)

    def test_new_message_is_created_only_on_exact_confirmation(self):
        proposal = self.preview()
        self.assertIsNone(proposal["document"]["request"]["existingMessageId"])
        self.assertFalse(any(c["kind"] == "reconcile" for c in self.ledger.snapshot()["commands"]))
        result, _ = self.confirm(proposal)
        command = result["result"]
        messages = [c for c in self.ledger.snapshot()["commands"] if conversation.is_message(c)]
        self.assertEqual(len(messages), 1)
        self.assertEqual(command["payload"]["messageId"], messages[0]["id"])
        self.assertNotIn("notification", messages[0])
        self.assertEqual(plan(self.snapshot())["mode"], "follow")

    def test_foreign_stale_tampered_and_unbound_wake_refuse_without_effect(self):
        proposal = self.preview()
        with self.assertRaises(Refusal):
            self.confirm(proposal, "other-session")
        bad = copy.deepcopy(proposal)
        bad["document"]["request"]["allowanceTokens"] = 5_000_000
        with self.assertRaises(Refusal):
            self.confirm(bad)
        self.native.configured = lambda brain: False
        with self.assertRaises(Refusal):
            self.confirm(proposal)
        self.native.configured = lambda brain: True
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["standardRun"]["usageHighWater"] += 1
            standard.save(self.ledger, db, meta, meta["standardRun"], "fixture_changed")
        with self.assertRaises(Refusal):
            self.confirm(proposal)
        self.assertFalse(any(c["kind"] == KIND for c in self.ledger.snapshot()["commands"]))

    def test_uncertain_old_message_delivery_cannot_be_woken_again(self):
        meta = self.ledger.snapshot()["meta"]
        saved = self.ledger.submit({"id": "old-uncertain-message", "kind": "reconcile",
                                    "expectedRevision": meta["revision"],
                                    "payload": {"brainId": meta["brainId"], "message": "Check prior native delivery.",
                                                "confirmed": True}}, actor="dashboard")
        with self.ledger.tx() as db:
            value = self.ledger.get(db, "commands", saved["id"])
            value["notification"] = {"status": "uncertain", "attemptedAt": time.time()}
            self.ledger.put(db, "commands", saved["id"], value)
        self.assertFalse(catalog(self.snapshot(), {})["phase_recovery"]["available"])
        with self.assertRaises(Refusal):
            self.preview()

    def test_newer_brain_stop_prevents_native_claim(self):
        command = self.confirm(self.preview())[0]["result"]
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["brainControl"] = {"desired": "stopped", "phase": "stop_requested"}
            self.ledger.put(db, "meta", 1, meta)
        self.notifier.notify(command["id"])
        retained = next(c for c in self.ledger.snapshot()["commands"] if c["id"] == command["id"])
        self.assertNotIn("notification", retained)
        self.assertEqual(retained["status"], "queued")
        self.assertEqual(self.native.sent, [])

    def test_lost_owned_host_cannot_fall_back_to_desktop_queue(self):
        command = self.confirm(self.preview())[0]["result"]
        self.notifier.status = lambda _brain: {"status": "configured", "transport": "desktop_queue_only",
                                               "detail": "Desktop queue only"}
        self.notifier.notify(command["id"])
        retained = next(c for c in self.ledger.snapshot()["commands"] if c["id"] == command["id"])
        self.assertEqual(retained["notification"]["status"], "unavailable")
        self.assertIn("no desktop-queue fallback", retained["notification"]["detail"])
        self.assertEqual(self.native.sent, [])

    def test_authenticated_help_preview_and_confirmation_keep_the_phase_paused(self):
        from orchestrator.server import Dashboard
        server = Dashboard(self.ledger, 0, registry=self.registry, runtime_root=self.fixture.root,
                           inference_env=self.fixture.root / "absent.env")
        server.runtime_for("alpha").notifier.app_server = self.native
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def request(path, body=None, auth=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST" if body is not None else "GET", path,
                         json.dumps(body) if body is not None else None,
                         {"Content-Type": "application/json", "Origin": server.origin, **(auth or {})})
            response = conn.getresponse()
            value = response.status, dict(response.getheaders()), json.loads(response.read())
            conn.close()
            return value

        try:
            path = "/api/workspaces/alpha"
            self.assertEqual(request(path + "/assistant/help")[0], 401)
            _, headers, _ = request("/api/login", {"token": server.bootstrap})
            auth = {"Cookie": headers["Set-Cookie"].split(";")[0]}
            _, _, session = request(path + "/session", auth=auth)
            auth["X-CSRF-Token"] = session["csrf"]
            before = standard.read(self.ledger)["run"]
            status, _, help_view = request(path + "/assistant/help", auth=auth)
            self.assertEqual(status, 200)
            self.assertEqual(help_view["mode"], "prepare")
            self.assertEqual(help_view["key"], "phase_recovery")
            self.assertEqual(help_view["proposal"]["document"]["workflow"], "phase_recovery")
            self.assertEqual(before, standard.read(self.ledger)["run"], "GET must not authorize or send")
            self.assertEqual(len(self.native.sent), 0)
            submission = {"proposal": help_view["proposal"], "confirmed": True}
            self.assertEqual(request(path + "/assistant/confirm", submission,
                                  {**auth, "X-CSRF-Token": "wrong"})[0], 403)
            status, _, saved = request(path + "/assistant/confirm", submission, auth)
            self.assertEqual(status, 200, saved)
            self.assertEqual(saved["result"]["kind"], KIND)
            self.assertEqual(saved["result"]["notification"]["status"], "accepted")
            self.assertEqual(standard.read(self.ledger)["run"]["status"], "paused")
            self.assertEqual(len(self.native.sent), 1)
            self.assertEqual(request(path + "/assistant/help", auth=auth)[2]["mode"], "follow")
            self.assertEqual(request(path + "/assistant/confirm", submission, auth)[0], 200)
            self.assertEqual(len(self.native.sent), 1, "Exact replay never starts another turn")
        finally:
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
