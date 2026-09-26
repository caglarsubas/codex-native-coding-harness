import json
from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from orchestrator.app_server_wake import AppServerWake, WakeProxy, load_binding
from orchestrator.core import Refusal

BRAIN = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
PROJECT = "33333333-3333-4333-8333-333333333333"
TURN = "turn-1"


class FakeProxy:
    instances = []
    status = "notLoaded"
    fail_at = None

    def __init__(self, endpoint, timeout=15):
        self.calls = []
        self.closed = False
        self.deadline = 0
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def _rpc(self, method, params):
        self.calls.append((method, params))
        if method == self.fail_at:
            raise Refusal("private native error")
        if method == "thread/read":
            return {"thread": {"id": BRAIN, "cwd": "/fixture/brain", "projectId": PROJECT,
                               "status": {"type": self.status}}}
        if method == "thread/resume":
            return {"thread": {"id": BRAIN, "cwd": "/fixture/brain", "projectId": PROJECT}}
        if method == "turn/start":
            return {"turn": {"id": TURN, "status": "inProgress"}}
        raise AssertionError(method)


class FakeThread:
    started = False
    def __init__(self, *, target, args, daemon, name):
        self.args = args
        self.daemon = daemon
    def start(self):
        self.started = True


class MemoryLedger:
    def __init__(self):
        self.command = {"notification": {"brainId": BRAIN, "nativeTurnId": TURN, "status": "accepted"}}
    @contextmanager
    def tx(self):
        yield None
    def get(self, db, table, key):
        return self.command
    def put(self, db, table, key, value):
        self.command = value


class EventProxy:
    def __init__(self, event):
        self.event = event
        self.closed = False
    def _line(self):
        return self.event
    def __exit__(self, *_):
        self.closed = True


class WakeTest(unittest.TestCase):
    def setUp(self):
        FakeProxy.instances = []
        FakeProxy.status = "notLoaded"
        FakeProxy.fail_at = None
        self.binding = {"endpoint": {"executable": "/fixture/codex", "socket": "/fixture/codex.sock"},
                        "brains": {BRAIN: {"cwd": "/fixture/brain", "projectId": PROJECT,
                                           "workspaceId": "fixture"}}}
        self.wake = AppServerWake(self.binding, None)
        self.configured = patch.object(self.wake, "configured", return_value=True)
        self.configured.start()

    def tearDown(self):
        self.configured.stop()

    @patch("orchestrator.app_server_wake.threading.Thread", FakeThread)
    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    def test_unloaded_brain_is_resumed_and_started_once_on_bound_cwd(self):
        result = self.wake.send(BRAIN, "fixed pointer", "saved-control")
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["nativeDelivery"], "owned_turn_start")
        self.assertEqual([m for m, _ in FakeProxy.instances[0].calls],
                         ["thread/read", "thread/resume", "turn/start"])
        self.assertEqual(FakeProxy.instances[0].calls[-1][1],
                         {"threadId": BRAIN, "input": [{"type": "text", "text": "fixed pointer"}],
                          "cwd": "/fixture/brain"})
        self.assertFalse(FakeProxy.instances[0].closed)  # event subscription retained

    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    @patch("orchestrator.app_server_wake.subprocess.run")
    def test_active_brain_queues_only_on_same_owned_socket(self, run):
        FakeProxy.status = "active"
        run.return_value = subprocess.CompletedProcess([], 0,
            f"Queued message {OTHER} for thread {BRAIN}.\n", "")
        result = self.wake.send(BRAIN, "fixed pointer", "saved-control")
        self.assertEqual(result["nativeDelivery"], "owned_active_queue")
        self.assertEqual([m for m, _ in FakeProxy.instances[0].calls], ["thread/read"])
        self.assertEqual(run.call_args.args[0][:5],
                         ["/fixture/codex", "queue", "--remote", "unix:///fixture/codex.sock", "--thread"])
        self.assertTrue(FakeProxy.instances[0].closed)

    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    def test_read_failure_is_unsent_and_start_failure_is_uncertain(self):
        FakeProxy.fail_at = "thread/read"
        self.assertEqual(self.wake.send(BRAIN, "pointer", "control")["status"], "unavailable")
        FakeProxy.fail_at = "turn/start"
        self.assertEqual(self.wake.send(BRAIN, "pointer", "control")["status"], "uncertain")
        self.assertTrue(all(p.closed for p in FakeProxy.instances))

    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    def test_wrong_thread_or_checkout_refuses_before_start(self):
        self.binding["brains"][BRAIN]["cwd"] = "/other/project"
        result = self.wake.send(BRAIN, "pointer", "control")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual([m for m, _ in FakeProxy.instances[0].calls], ["thread/read"])
        self.assertNotIn("private", str(result))

    def test_binding_is_private_and_exact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / "binding.json"
            path.write_text(json.dumps(self.binding))
            path.chmod(0o600)
            with patch("orchestrator.app_server_wake.validate_endpoint"):
                with self.assertRaises(Refusal):
                    load_binding(path)  # fixture checkout does not exist
                self.binding["brains"][BRAIN]["cwd"] = str(Path(directory).resolve())
                path.write_text(json.dumps(self.binding))
                self.assertEqual(load_binding(path)["brains"][BRAIN]["cwd"], str(Path(directory).resolve()))
                path.chmod(0o644)
                with self.assertRaises(Refusal):
                    load_binding(path)

    def test_event_observer_retains_only_status_and_never_grants_permission(self):
        ledger = MemoryLedger()
        self.wake.ledger = ledger
        proxy = EventProxy({"id": 9, "method": "item/commandExecution/requestApproval",
                            "params": {"threadId": BRAIN, "turnId": TURN,
                                       "command": "PRIVATE COMMAND", "reason": "PRIVATE REASON"}})
        self.wake._observe_turn(proxy, "control", BRAIN, TURN)
        self.assertTrue(proxy.closed)
        self.assertEqual(ledger.command["notification"]["nativeTurnStatus"], "native_attention_required")
        self.assertNotIn("PRIVATE", str(ledger.command))
        ledger = MemoryLedger(); self.wake.ledger = ledger
        proxy = EventProxy({"method": "turn/completed", "params": {
            "threadId": BRAIN, "turn": {"id": TURN, "status": "completed", "items": ["PRIVATE"]}}})
        self.wake._observe_turn(proxy, "control", BRAIN, TURN)
        self.assertEqual(ledger.command["notification"]["nativeTurnStatus"], "completed")
        self.assertNotIn("PRIVATE", str(ledger.command))

    def test_early_turn_completion_is_retained_without_private_content(self):
        proxy = WakeProxy(self.binding["endpoint"])
        proxy._awaiting_start = True
        proxy.buffer = (json.dumps({"method": "turn/completed", "params": {
            "threadId": BRAIN, "turn": {"id": TURN, "status": "completed",
                                      "items": ["PRIVATE TRANSCRIPT"]}}}) + "\n").encode()
        proxy._line()
        self.assertEqual(proxy._early_completion, (BRAIN, TURN, "completed"))
        ledger = MemoryLedger()
        self.wake.ledger = ledger
        proxy.__exit__ = lambda *_: None
        self.wake._observe_turn(proxy, "control", BRAIN, TURN)
        self.assertEqual(ledger.command["notification"]["nativeTurnStatus"], "completed")
        self.assertNotIn("PRIVATE", str(ledger.command))
