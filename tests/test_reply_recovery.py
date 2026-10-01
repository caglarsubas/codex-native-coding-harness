import copy
import contextlib
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from orchestrator import conversation, reply_recovery as recovery
from orchestrator.app_server_wake import NATIVE_APPROVAL_POLICY
from orchestrator.assistant_journey import JourneyProposals
from orchestrator.core import Ledger, Refusal, digest
from orchestrator.native_read_client import ReadProxy
from orchestrator.notification import BrainNotifier
from test_decisions import fixture

BRAIN = "11111111-1111-4111-8111-111111111111"
PROJECT = "33333333-3333-4333-8333-333333333333"
CATALOG = "44444444-4444-4444-8444-444444444444"


class Metadata:
    def __init__(self):
        self.calls = []
        self.thread = {"id": BRAIN, "projectId": PROJECT, "cwd": "/fixture",
                       "status": {"type": "notLoaded"}}
        self.page = {"data": [{"id": "original-turn", "status": "interrupted", "completedAt": 1}],
                     "nextCursor": None}
    def call(self, method, params):
        self.calls.append((method, copy.deepcopy(params)))
        return copy.deepcopy({"thread": self.thread} if method == "thread/read" else self.page)


class ReplyRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "state")
        fixture(self.ledger, BRAIN)
        self.ledger.workspace_id = "fixture"
        self.ledger.platform_root = Path(self.tmp.name)
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "fixture")
            repo["projectId"] = CATALOG
            self.ledger.put(db, "repos", "fixture", repo)
        self.original = self.ledger.submit({"id": "original-message", "kind": "reconcile",
            "expectedRevision": self.ledger.snapshot()["meta"]["revision"],
            "payload": {"message": "PRIVATE original diagnostic; do not replay", "brainId": BRAIN, "confirmed": True}})
        token = self.ledger.acquire(BRAIN + ":original")
        conversation.receive(self.ledger, token, self.original["id"])
        self.ledger.release(token, "Interrupted diagnostic preserved")
        with self.ledger.tx() as db:
            self.original = self.ledger.get(db, "commands", self.original["id"])
            self.original["notification"] = {"brainId": BRAIN, "status": "accepted",
                "nativeTurnId": "original-turn", "nativeDelivery": "owned_turn_start", "attemptedAt": 1}
            self.ledger.put(db, "commands", self.original["id"], self.original)
        self.binding = {"endpoint": {}, "brains": {BRAIN: {"workspaceId": "fixture", "cwd": "/fixture",
            "projectId": PROJECT, "catalogProjectId": CATALOG, "nativePolicy": NATIVE_APPROVAL_POLICY.copy()}}}
        self.runtime = SimpleNamespace(ledger=self.ledger,
            notifier=SimpleNamespace(app_server=SimpleNamespace(binding=self.binding)))
        self.runtime.snapshot = self.state
        self.proposals = JourneyProposals(self.runtime)
        self.metadata = Metadata()
        self.proxy = patch("orchestrator.native_read_client.ReadProxy")
        self.factory = self.proxy.start()
        self.factory.return_value.__enter__.return_value = self.metadata

    def tearDown(self):
        self.proxy.stop()
        self.tmp.cleanup()

    def state(self):
        state = self.ledger.snapshot()
        state["workspace"] = {"id": "fixture"}
        state["brainNotification"] = {"transport": "owned_app_server"}
        return state

    def preview(self):
        state = self.state()
        return self.proposals.prepare(recovery.catalog(state)["reply_recovery"], state, "owner-session")

    def confirm(self, preview):
        return self.proposals.confirm(self.ledger, {"proposal": preview, "confirmed": True}, "owner-session")

    def accepted(self, command):
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", command["id"])
            command["notification"] = {"brainId": BRAIN, "status": "accepted",
                "nativeTurnId": "recovery-turn", "nativeDelivery": "owned_turn_start"}
            self.ledger.put(db, "commands", command["id"], command)
        return command

    def test_explicit_preview_is_metadata_only_and_read_only(self):
        with contextlib.closing(self.ledger.connect()) as db: before = list(db.iterdump())
        preview = self.preview()
        with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))
        self.assertEqual([m for m, _ in self.metadata.calls],
                         ["thread/read", "thread/turns/list", "thread/turns/list", "thread/read"])
        for method, params in self.metadata.calls:
            if method == "thread/read": self.assertIs(params["includeTurns"], False)
            else: self.assertEqual((params["limit"], params["itemsView"]), (64, "notLoaded"))
        self.assertNotIn("PRIVATE original", json.dumps(preview))
        self.assertEqual(preview["document"]["expiresAt"] - preview["document"]["createdAt"], 300)

    def test_signed_confirmation_replay_no_second_check_or_attempt(self):
        preview = self.preview()
        command, first = self.confirm(preview)
        self.assertTrue(first)
        calls = len(self.metadata.calls)
        with patch("orchestrator.assistant_actions.time.time", return_value=time.time() + 1000):
            same, first = self.confirm(preview)
        self.assertFalse(first); self.assertEqual(command, same)
        self.assertEqual(len(self.metadata.calls), calls)
        self.assertEqual(recovery.catalog(self.state()), {})
        another = copy.deepcopy(preview)
        another["document"]["command"]["id"] = str(uuid.uuid4())
        another["signature"] = self.proposals.sign(another["document"])
        with self.assertRaises(Refusal): self.confirm(another)
        self.assertEqual(conversation.read(self.ledger)["pending"], 1)

    def test_confirmation_signature_session_scope_and_direct_http_actor(self):
        preview = self.preview()
        for changed in ("signature", "session", "ledger", "workspace"):
            altered = copy.deepcopy(preview)
            if changed == "signature": altered["signature"] = "bad"
            else:
                key = "workspaceId" if changed == "workspace" else changed
                altered["document"][key] = "foreign"
                altered["signature"] = self.proposals.sign(altered["document"])
            calls = len(self.metadata.calls)
            with self.subTest(changed=changed), self.assertRaises(Refusal): self.confirm(altered)
            self.assertEqual(len(self.metadata.calls), calls)
        with self.assertRaises(Refusal):
            self.proposals.confirm(self.ledger, {"proposal": preview, "confirmed": False}, "owner-session")
        with self.assertRaisesRegex(Refusal, "signed owner preview"):
            self.ledger.submit(preview["document"]["command"])

    def test_pause_binding_revision_and_unknown_native_changes_refuse(self):
        for change in ("active", "turn", "project", "binding", "catalog", "revision", "stop"):
            with self.subTest(change=change):
                preview = self.preview()
                old_thread, old_page, old_binding = copy.deepcopy(self.metadata.thread), copy.deepcopy(self.metadata.page), copy.deepcopy(self.binding)
                with contextlib.closing(self.ledger.connect()) as db: old_meta = self.ledger.get(db, "meta", 1)
                if change == "active": self.metadata.thread["status"] = {"type": "active"}
                elif change == "turn": self.metadata.page["data"][0]["status"] = "inProgress"
                elif change == "project": self.metadata.thread["projectId"] = CATALOG
                elif change == "binding": self.binding["endpoint"]["changed"] = True
                elif change == "catalog": self.binding["brains"][BRAIN]["catalogProjectId"] = "different"
                else:
                    with self.ledger.tx() as db:
                        meta = self.ledger.get(db, "meta", 1)
                        if change == "stop": meta["brainControl"] = {"desired": "stopped", "phase": "checkpointing"}
                        else: meta["revision"] += 1
                        self.ledger.put(db, "meta", 1, meta)
                with self.assertRaises(Refusal): self.confirm(preview)
                self.metadata.thread, self.metadata.page = old_thread, old_page
                self.binding.clear(); self.binding.update(old_binding)
                with self.ledger.tx() as db: self.ledger.put(db, "meta", 1, old_meta)

    def test_absence_duplicate_pages_unknown_and_changing_reads_fail_closed(self):
        for page in ({"data": [], "nextCursor": None},
                     {"data": [{"id": "x", "status": "completed"}], "nextCursor": "repeated"},
                     {"data": [{"id": "original-turn", "status": "interrupted"}], "nextCursor": None},
                     {"data": [{"id": "original-turn", "status": "unknown", "completedAt": 1}], "nextCursor": None}):
            with self.subTest(page=page):
                self.metadata.page = page
                with self.assertRaises(Refusal): self.preview()
        self.metadata = Metadata()
        count = 0
        def changing(method, params):
            nonlocal count
            count += 1
            result = self.metadata.call(method, params)
            if count == 3: result["data"][0]["status"] = "completed"
            return result
        self.factory.return_value.__enter__.return_value = SimpleNamespace(call=changing)
        with self.assertRaisesRegex(Refusal, "changed"): self.preview()

    def test_native_items_and_error_bodies_never_retained(self):
        self.metadata.page["data"][0].update(items=[{"private": "SECRET transcript"}], error={"message": "SECRET error"})
        self.assertNotIn("SECRET", json.dumps(self.preview()))

    def test_dedicated_receive_and_reply_preserve_original_and_dispatch(self):
        preview = self.preview()
        command, _ = self.confirm(preview)
        token = self.ledger.acquire(BRAIN + ":recovery")
        self.assertEqual(self.ledger.process(token), [])  # No generic replay or draining.
        with self.assertRaises(Refusal): recovery.receive(self.ledger, token, command["id"])
        self.accepted(command)
        with self.assertRaises(Refusal): recovery.receive(self.ledger, "foreign", command["id"])
        received = recovery.receive(self.ledger, token, command["id"])
        self.assertEqual(received["messageId"], self.original["id"])
        recovery.receive(self.ledger, token, command["id"])
        answer = {"message": "Interrupted; command outcome remains unknown. No replay.", "artifactIds": [], "decisionIds": []}
        result = conversation.reply(self.ledger, token, self.original["id"], answer)
        for key in ("payload", "fingerprint", "conversationReceivedAt", "notification"):
            self.assertEqual(self.original[key], result[key])
        view = conversation.read(self.ledger)
        self.assertEqual(view["pending"], 0)
        self.assertEqual(view["messages"][0]["receiptRecovery"]["status"], "completed")
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertEqual(self.ledger.snapshot()["workers"], [])
        self.assertEqual(conversation.reply(self.ledger, token, self.original["id"], answer), result)
        with self.assertRaises(Refusal): self.ledger.acknowledge(token, command["id"], True, "Not a reply")

    def test_notifier_one_claim_fixed_pointer_and_no_original_text(self):
        command, _ = self.confirm(self.preview())
        with patch("orchestrator.app_server_wake.AppServerWake.configured", return_value=True), \
             patch("orchestrator.app_server_wake.AppServerWake.send", return_value={
                 "status": "uncertain", "detail": "Unconfirmed"}) as send:
            notifier = BrainNotifier(self.ledger, app_server_binding=self.binding)
            self.assertEqual(notifier.notify(command["id"])["notification"]["status"], "uncertain")
            notifier.notify(command["id"])
            send.assert_called_once()
            message = send.call_args.args[1]
            self.assertNotIn("PRIVATE original", message)
            self.assertIn("Do NOT use generic process", message)
            self.assertIn("Do not rerun original commands", message)
            self.assertIn("brain-reply-recovery-receive", message)
            notifier.close()

    def test_late_original_reply_cancels_only_an_unsent_recovery(self):
        command, _ = self.confirm(self.preview())
        token = self.ledger.acquire(BRAIN + ":late-original-reply")
        conversation.reply(self.ledger, token, self.original["id"], {
            "message": "Original reply arrived; diagnostic outcome remains unknown.", "artifactIds": [], "decisionIds": []})
        self.ledger.release(token, "Reply retained")
        view = conversation.read(self.ledger)["messages"][0]["receiptRecovery"]
        self.assertEqual(view["status"], "completed")
        self.assertIsNone(view["receivedAt"])
        with patch("orchestrator.app_server_wake.AppServerWake.configured", return_value=True), \
             patch("orchestrator.app_server_wake.AppServerWake.send") as send:
            notifier = BrainNotifier(self.ledger, app_server_binding=self.binding)
            self.assertNotIn("notification", notifier.notify(command["id"]))
            send.assert_not_called()
            notifier.close()

    def test_no_queue_fallback_and_stop_wins_before_claim(self):
        command, _ = self.confirm(self.preview())
        notifier = BrainNotifier(self.ledger)
        self.assertNotIn("notification", notifier.notify(command["id"]))
        with patch("orchestrator.app_server_wake.AppServerWake.configured", return_value=True), \
             patch("orchestrator.app_server_wake.AppServerWake.send") as send:
            notifier = BrainNotifier(self.ledger, app_server_binding=self.binding)
            with self.ledger.tx() as db:
                meta = self.ledger.get(db, "meta", 1)
                meta["brainControl"] = {"desired": "stopped", "phase": "checkpointing"}
                self.ledger.put(db, "meta", 1, meta)
            self.assertNotIn("notification", notifier.notify(command["id"]))
            send.assert_not_called()
            notifier.close()

    def test_pending_recovery_fences_development_not_pause(self):
        self.confirm(self.preview())
        with contextlib.closing(self.ledger.connect()) as db:
            with self.assertRaises(Refusal): recovery.fence_development(self.ledger, db)
        revision = self.ledger.snapshot()["meta"]["revision"]
        with self.assertRaisesRegex(Refusal, "Receipt-only recovery"):
            self.ledger.submit({"id": str(uuid.uuid4()), "kind": "resume", "payload": {}, "expectedRevision": revision})
        self.ledger.submit({"id": str(uuid.uuid4()), "kind": "pause", "payload": {}, "expectedRevision": revision})

    def test_send_boundary_rechecks_original_and_current_controls(self):
        command, _ = self.confirm(self.preview())
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", command["id"])
            command["notification"] = {"status": "sending", "brainId": BRAIN}
            self.ledger.put(db, "commands", command["id"], command)
        recovery.send_check(self.ledger, self.binding, command["id"], self.metadata)
        self.metadata.thread["status"] = {"type": "active"}
        with self.assertRaises(Refusal): recovery.send_check(self.ledger, self.binding, command["id"], self.metadata)
        self.metadata.thread["status"] = {"type": "idle"}
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["paused"] = False
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal): recovery.send_check(self.ledger, self.binding, command["id"], self.metadata)

    def bridge_send(self, stop_on_resume=False):
        from orchestrator.app_server_wake import AppServerWake
        from test_app_server_wake import FakeThread
        command, _ = self.confirm(self.preview())
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", command["id"])
            command["notification"] = {"status": "sending", "brainId": BRAIN}
            self.ledger.put(db, "commands", command["id"], command)
        fixture = self
        class Proxy(Metadata):
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def _rpc(self, method, params):
                if method == "thread/read": return self.call(method, params)
                self.calls.append((method, params))
                if method == "thread/resume":
                    self.thread["status"] = {"type": "idle"}
                    if stop_on_resume:
                        with fixture.ledger.tx() as db:
                            meta = fixture.ledger.get(db, "meta", 1)
                            meta["brainControl"] = {"desired": "stopped", "phase": "checkpointing"}
                            fixture.ledger.put(db, "meta", 1, meta)
                    return {"thread": copy.deepcopy(self.thread)}
                if method == "turn/start": return {"turn": {"id": "recovery-turn"}}
                raise AssertionError(method)
        proxy = Proxy()
        wake = AppServerWake(self.binding, self.ledger)
        with patch.object(wake, "configured", return_value=True), \
             patch("orchestrator.app_server_wake.WakeProxy", return_value=proxy), \
             patch("orchestrator.app_server_wake.threading.Thread", FakeThread):
            result = wake.send(BRAIN, "fixed receipt-only pointer", command["id"])
        wake.close()
        return result, proxy.calls

    def test_bridge_checks_same_connection_before_and_after_resume(self):
        result, calls = self.bridge_send()
        self.assertEqual(result["status"], "accepted")
        methods = [method for method, _ in calls]
        self.assertEqual(methods.count("thread/turns/list"), 4)
        self.assertEqual(methods.count("turn/start"), 1)
        self.assertLess(methods.index("thread/turns/list"), methods.index("thread/resume"))
        self.assertGreater(len(methods) - 1 - methods[::-1].index("thread/turns/list"), methods.index("thread/resume"))
        self.assertEqual(calls[-1][1]["input"], [{"type": "text", "text": "fixed receipt-only pointer"}])

    def test_bridge_stop_race_after_resume_prevents_turn_start(self):
        result, calls = self.bridge_send(stop_on_resume=True)
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("thread/resume", [m for m, _ in calls])
        self.assertNotIn("turn/start", [m for m, _ in calls])
        self.assertEqual(recovery.catalog(self.state()), {})

    def test_strict_activated_maintenance_and_owned_work_refused(self):
        baseline = self.state()
        for change in ("strict", "run", "controller", "runner", "worker", "queue", "maintenance", "schema", "unreceived", "uncertain"):
            state = copy.deepcopy(baseline)
            if change == "strict": state["repositories"][0]["policyProfile"] = "harness"
            elif change == "run": state["meta"]["standardRun"] = {"status": "paused"}
            elif change in ("controller", "runner"): state["meta"][change] = {"owner": "held"}
            elif change in ("worker", "queue"): state["workers" if change == "worker" else "queue"] = [{}]
            elif change == "maintenance": state["admission"]["dispatchBlocked"] = True
            elif change == "schema": state["meta"]["schemaVersion"] = 3
            elif change == "unreceived": state["commands"][0].pop("conversationReceivedAt")
            else: state["commands"][0]["notification"]["status"] = "uncertain"
            with self.subTest(change=change): self.assertEqual(recovery.catalog(state), {})

    def test_proxy_closed_allowlist(self):
        client = ReadProxy({})
        params = {"threadId": BRAIN, "cursor": None, "limit": 64, "sortDirection": "desc", "itemsView": "notLoaded"}
        with patch.object(client, "_rpc", return_value={}) as rpc:
            client.call("thread/turns/list", params)
            rpc.assert_called_once()
            for mutation in ({"itemsView": "full"}, {"itemsView": "summary"}, {"limit": 128}, {"sortDirection": "asc"}, {"shell": "x"}):
                with self.assertRaises(Refusal): client.call("thread/turns/list", {**params, **mutation})


if __name__ == "__main__":
    unittest.main()
