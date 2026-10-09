import json
from contextlib import contextmanager
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from orchestrator.app_server_wake import (AppServerWake, NATIVE_APPROVAL_POLICY,
                                          THREAD_EVENT_LIMIT, THREAD_STREAM_GAP,
                                          WakeProxy, load_binding)
from orchestrator.core import Refusal
from orchestrator.native_read_client import NativeReadFailure, ReadProxy

BRAIN = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
PROJECT = "33333333-3333-4333-8333-333333333333"
TURN = "turn-1"
COMMAND_REQUIRED = {"kind": "command", "startedAtMs": 1, "environmentId": None}
FILE_REQUIRED = {"startedAtMs": 1}


class FakeProxy:
    instances = []
    status = "notLoaded"
    fail_at = None
    project_id = PROJECT

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
            return {"thread": {"id": BRAIN, "cwd": "/fixture/brain", "projectId": self.project_id,
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
        self.events = []
    @contextmanager
    def tx(self):
        yield None
    def get(self, db, table, key):
        return self.command
    def put(self, db, table, key, value):
        self.command = value
    def event(self, db, kind, payload):
        self.events.append((kind, payload))


class EventProxy:
    def __init__(self, event):
        self.event = event
        self.closed = False
    def _line(self):
        return self.event
    def __exit__(self, *_):
        self.closed = True


class ApprovalProxy:
    def __init__(self, *events):
        self.events = queue.Queue()
        for event in events:
            self.events.put(event)
        self.writes = []
        self.closed = False
        self.deadline = 0

    def _line(self):
        try:
            value = self.events.get(timeout=2)
        except queue.Empty:
            raise Refusal("Missing test event") from None
        if value is None:
            raise Refusal("Closed test subscription")
        return value

    def _write(self, value):
        self.writes.append(value)
        self.events.put({"method": "serverRequest/resolved", "params": {
            "threadId": BRAIN, "requestId": value["id"]}})
        self.events.put({"method": "turn/completed", "params": {
            "threadId": BRAIN, "turn": {"id": TURN, "status": "completed"}}})

    def __exit__(self, *_):
        self.closed = True
        self.events.put(None)


def wait_pending(wake, brain_id=BRAIN):
    until = time.monotonic() + 2
    while time.monotonic() < until:
        pending = wake.pending_approval(brain_id)
        if pending is not None:
            return pending
        time.sleep(0.005)
    raise AssertionError("Native approval was not offered")


class WakeTest(unittest.TestCase):
    def setUp(self):
        FakeProxy.instances = []
        FakeProxy.status = "notLoaded"
        FakeProxy.fail_at = None
        FakeProxy.project_id = PROJECT
        self.binding = {"endpoint": {"executable": "/fixture/codex", "socket": "/fixture/codex.sock"},
                        "brains": {BRAIN: {"cwd": "/fixture/brain", "projectId": PROJECT,
                                           "workspaceId": "fixture", "nativePolicy": NATIVE_APPROVAL_POLICY.copy()}}}
        self.wake = AppServerWake(self.binding, MemoryLedger())
        self.wake.ledger.command["notification"]["status"] = "sending"
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
        self.assertEqual(FakeProxy.instances[0].calls[1][1],
                         {"threadId": BRAIN,
                          "excludeTurns": True,
                          "config": {"features": {"code_mode": {"enabled": False}}},
                          "sandbox": "workspace-write", "approvalPolicy": "on-request"})
        self.assertEqual(FakeProxy.instances[0].calls[-1][1],
                         {"threadId": BRAIN, "input": [{"type": "text", "text": "fixed pointer"}],
                          "cwd": "/fixture/brain"})
        self.assertFalse(FakeProxy.instances[0].closed)  # event subscription retained
        observation = self.wake.ledger.command["notification"]["nativeThreadObservation"]
        self.assertEqual(observation["streamStatus"], "open")
        self.assertFalse(observation["complete"])
        self.assertEqual(observation["gaps"], [THREAD_STREAM_GAP])

    def test_owned_thread_events_are_bounded_private_and_never_complete(self):
        self.wake._begin_thread_observation("control", BRAIN)
        child = "44444444-4444-4444-8444-444444444444"
        grandchild = "55555555-5555-4555-8555-555555555555"
        event = {"method": "thread/started", "params": {"thread": {
            "id": child, "parentThreadId": BRAIN, "ephemeral": True,
            "preview": "PRIVATE MESSAGE", "cwd": "/private/foreign"}}}
        self.wake._record_thread_started("control", BRAIN, event)
        self.wake._record_thread_started("control", BRAIN, event)
        self.wake._record_thread_started("control", BRAIN, {"method": "thread/started", "params": {"thread": {
            "id": grandchild, "parentThreadId": child, "ephemeral": False,
            "turns": ["PRIVATE TURN"]}}})
        self.wake._record_thread_started("control", BRAIN, {"method": "thread/started", "params": {"thread": {
            "id": OTHER, "parentThreadId": PROJECT, "preview": "FOREIGN PRIVATE"}}})
        observation = self.wake.ledger.command["notification"]["nativeThreadObservation"]
        self.assertEqual([item["threadId"] for item in observation["events"]], [child, grandchild])
        self.assertEqual([item["ephemeral"] for item in observation["events"]], [True, False])
        self.assertNotIn("PRIVATE", str(observation))
        self.wake._finish_thread_observation("control", BRAIN, TURN, "completed")
        self.assertEqual(observation["streamStatus"], "closed")
        self.assertFalse(observation["complete"])
        self.assertEqual(observation["gaps"], [THREAD_STREAM_GAP])

    def test_thread_event_conflict_and_limit_retain_gaps_without_foreign_ids(self):
        self.wake._begin_thread_observation("control", BRAIN)
        child = "44444444-4444-4444-8444-444444444444"
        self.wake._record_thread_started("control", BRAIN, {"params": {"thread": {
            "id": child, "parentThreadId": BRAIN, "ephemeral": True}}})
        self.wake._record_thread_started("control", BRAIN, {"params": {"thread": {
            "id": child, "parentThreadId": BRAIN, "ephemeral": False}}})
        for index in range(THREAD_EVENT_LIMIT):
            self.wake._record_thread_started("control", BRAIN, {"params": {"thread": {
                "id": f"{index + 1:08x}-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "parentThreadId": BRAIN}}})
        observation = self.wake.ledger.command["notification"]["nativeThreadObservation"]
        self.assertEqual(len(observation["events"]), THREAD_EVENT_LIMIT)
        self.assertIn("conflicting_thread_event", observation["gaps"])
        self.assertIn("thread_event_limit", observation["gaps"])
        self.assertFalse(observation["complete"])

    def test_failed_start_and_stream_loss_remain_unconfirmed(self):
        self.wake._begin_thread_observation("control", BRAIN)
        self.wake._finish_thread_observation("control", BRAIN, None, "unconfirmed", event_error=True)
        observation = self.wake.ledger.command["notification"]["nativeThreadObservation"]
        self.assertEqual(observation["streamStatus"], "unconfirmed")
        self.assertIn("stream_ended_without_confirmed_turn", observation["gaps"])
        self.assertIn("thread_event_persist_failed", observation["gaps"])
        self.assertFalse(observation["complete"])
        self.wake._finish_thread_observation("control", BRAIN, TURN, "completed")
        self.assertEqual(observation["streamStatus"], "unconfirmed")

    def test_wake_proxy_intercepts_thread_start_even_during_rpc(self):
        proxy = WakeProxy({})
        captured = []
        proxy._on_thread_started = captured.append
        event = {"method": "thread/started", "params": {"thread": {
            "id": "44444444-4444-4444-8444-444444444444", "parentThreadId": BRAIN}}}
        with patch.object(ReadProxy, "_line", return_value=event):
            self.assertEqual(proxy._line(), event)
        self.assertEqual(captured, [event])

    @patch("orchestrator.app_server_wake.threading.Thread", FakeThread)
    def test_start_reply_race_retains_owned_child_before_notification_ack(self):
        child = "44444444-4444-4444-8444-444444444444"

        class EventDuringStartProxy(FakeProxy):
            def _rpc(self, method, params):
                if method == "turn/start":
                    self._on_thread_started({"method": "thread/started", "params": {"thread": {
                        "id": child, "parentThreadId": BRAIN, "ephemeral": True,
                        "preview": "PRIVATE EARLY TURN"}}})
                return super()._rpc(method, params)

        with patch("orchestrator.app_server_wake.WakeProxy", EventDuringStartProxy):
            result = self.wake.send(BRAIN, "fixed pointer", "control")
        self.assertEqual(result["status"], "accepted")
        observation = self.wake.ledger.command["notification"]["nativeThreadObservation"]
        self.assertEqual([item["threadId"] for item in observation["events"]], [child])
        self.assertNotIn("PRIVATE", str(observation))

    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    def test_failed_durable_marker_refuses_before_native_turn_start(self):
        with patch.object(self.wake, "_begin_thread_observation", side_effect=Refusal("ledger unavailable")):
            result = self.wake.send(BRAIN, "fixed pointer", "control")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual([method for method, _ in FakeProxy.instances[0].calls],
                         ["thread/read", "thread/resume"])
        self.assertEqual(result["nativeFailure"], {"version": 1, "stage": "observation_record",
            "reason": "validation_failed", "resumeAttempted": True, "turnStartAttempted": False})
        self.assertIn("saving the one-shot observation marker", result["detail"])
        self.assertNotIn("ledger unavailable", str(result))

    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    def test_failed_steps_are_distinct_private_and_keep_one_shot_boundary(self):
        for method, stage, resume, started in (("thread/read", "thread_read", False, False),
                ("thread/resume", "thread_resume", True, False), ("turn/start", "turn_start", True, True)):
            with self.subTest(method=method):
                FakeProxy.fail_at = method
                result = self.wake.send(BRAIN, "PRIVATE POINTER", "control")
                self.assertEqual(result["status"], "uncertain" if started else "unavailable")
                self.assertEqual(result["nativeFailure"], {"version": 1, "stage": stage,
                    "reason": "validation_failed", "resumeAttempted": resume, "turnStartAttempted": started})
                self.assertEqual(sum(m == method for m, _ in FakeProxy.instances[-1].calls), 1)
                self.assertNotIn("PRIVATE", str(result))
                self.assertNotIn("private native error", str(result))
                self.assertTrue(FakeProxy.instances[-1].closed)
                self.wake.ledger.command["notification"].pop("nativeThreadObservation", None)
                self.wake.ledger.command["notification"].pop("nativeResumeProfile", None)

    @patch("orchestrator.app_server_wake.threading.Thread", FakeThread)
    def test_resume_profile_retains_closed_native_facts_before_turn_without_content(self):
        class ProfileProxy(FakeProxy):
            def _rpc(self, method, params):
                result = super()._rpc(method, params)
                if method == "thread/resume":
                    result.update(sandbox={"type": "workspaceWrite", "writableRoots": ["/private/root"]},
                                  approvalPolicy="on-request", approvalsReviewer="user", model="PRIVATE MODEL")
                    result["thread"]["preview"] = "PRIVATE CONVERSATION"
                if method == "turn/start":
                    self_profile = self_outer.wake.ledger.command["notification"]["nativeResumeProfile"]
                    self_outer.assertEqual(self_profile["reported"]["sandbox"], "workspaceWrite")
                return result
        self_outer = self
        with patch("orchestrator.app_server_wake.WakeProxy", ProfileProxy):
            result = self.wake.send(BRAIN, "pointer", "control")
        self.assertEqual(result["status"], "accepted")
        profile = self.wake.ledger.command["notification"]["nativeResumeProfile"]
        self.assertIsNone(profile["reported"]["codeMode"])
        self.assertEqual(profile["requested"], NATIVE_APPROVAL_POLICY)
        self.assertNotIn("PRIVATE", str(profile))
        self.assertNotIn("/private/root", str(profile))

    @patch("orchestrator.app_server_wake.threading.Thread", FakeThread)
    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    def test_missing_resume_policy_is_unknown_not_copied_from_requested_policy(self):
        self.wake.send(BRAIN, "pointer", "control")
        profile = self.wake.ledger.command["notification"]["nativeResumeProfile"]
        self.assertTrue(all(v is None for v in profile["reported"].values()))

    def test_rpc_error_retains_only_reserved_code_and_failed_step(self):
        class RejectedResume(FakeProxy):
            def _rpc(self, method, params):
                if method == "thread/resume":
                    self.calls.append((method, params))
                    raise NativeReadFailure("rpc_error", "Native read unavailable", -32602)
                return super()._rpc(method, params)
        with patch("orchestrator.app_server_wake.WakeProxy", RejectedResume):
            result = self.wake.send(BRAIN, "pointer", "control")
        self.assertEqual(result["nativeFailure"]["rpcCode"], -32602)
        self.assertEqual(result["nativeFailure"]["stage"], "thread_resume")
        self.assertFalse(result["nativeFailure"]["turnStartAttempted"])
        self.assertEqual([m for m, _ in FakeProxy.instances[-1].calls], ["thread/read", "thread/resume"])

    @patch("orchestrator.app_server_wake.threading.Thread", FakeThread)
    def test_paginated_and_legacy_resume_request_only_metadata(self):
        for history_mode in ("paginated", "legacy"):
            with self.subTest(historyMode=history_mode):
                class MetadataOnlyProxy(FakeProxy):
                    def _rpc(self, method, params):
                        if method == "thread/resume" and params.get("excludeTurns") is not True:
                            self.calls.append((method, params))
                            raise NativeReadFailure("rpc_error", "Native read unavailable", -32600)
                        result = super()._rpc(method, params)
                        if method in ("thread/read", "thread/resume"):
                            result["thread"].update({"historyMode": history_mode, "turns": []})
                        return result
                with patch("orchestrator.app_server_wake.WakeProxy", MetadataOnlyProxy):
                    result = self.wake.send(BRAIN, "fixed pointer", "control")
                self.assertEqual(result["status"], "accepted")
                calls = FakeProxy.instances[-1].calls
                resume = next(params for method, params in calls if method == "thread/resume")
                self.assertIs(resume["excludeTurns"], True)
                self.assertEqual(set(resume), {"threadId", "excludeTurns", "config", "sandbox", "approvalPolicy"})
                self.assertEqual(resume["sandbox"], NATIVE_APPROVAL_POLICY["sandbox"])
                self.assertEqual(resume["approvalPolicy"], "on-request")
                self.assertEqual(resume["config"], {"features": {"code_mode": {"enabled": False}}})
                self.assertEqual(sum(method == "thread/resume" for method, _ in calls), 1)
                self.assertEqual(sum(method == "turn/start" for method, _ in calls), 1)
                self.wake.ledger.command["notification"].pop("nativeThreadObservation", None)
                self.wake.ledger.command["notification"].pop("nativeResumeProfile", None)

    def test_unsupported_metadata_resume_has_no_full_history_fallback(self):
        class UnsupportedMetadataProxy(FakeProxy):
            def _rpc(self, method, params):
                if method == "thread/resume":
                    self.calls.append((method, params))
                    if params.get("excludeTurns") is True:
                        raise NativeReadFailure("rpc_error", "Native read unavailable", -32600)
                    raise AssertionError("Full-history fallback must never be attempted")
                return super()._rpc(method, params)
        with patch("orchestrator.app_server_wake.WakeProxy", UnsupportedMetadataProxy):
            result = self.wake.send(BRAIN, "fixed pointer", "control")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["nativeFailure"]["stage"], "thread_resume")
        self.assertEqual(result["nativeFailure"]["rpcCode"], -32600)
        self.assertFalse(result["nativeFailure"]["turnStartAttempted"])
        self.assertEqual([m for m, _ in FakeProxy.instances[-1].calls], ["thread/read", "thread/resume"])
        self.assertNotIn("nativeThreadObservation", self.wake.ledger.command["notification"])

    def test_resume_must_not_return_full_history_before_starting_a_turn(self):
        for turns in ([{"privateTranscript": "PRIVATE HISTORY"}], "PRIVATE HISTORY", None):
            with self.subTest(turnsType=type(turns).__name__):
                class FullHistoryProxy(FakeProxy):
                    def _rpc(self, method, params):
                        result = super()._rpc(method, params)
                        if method == "thread/resume":
                            result["thread"]["turns"] = turns
                        return result
                with patch("orchestrator.app_server_wake.WakeProxy", FullHistoryProxy):
                    result = self.wake.send(BRAIN, "fixed pointer", "control")
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["nativeFailure"]["stage"], "resumed_identity")
                self.assertFalse(result["nativeFailure"]["turnStartAttempted"])
                self.assertEqual([m for m, _ in FakeProxy.instances[-1].calls], ["thread/read", "thread/resume"])
                self.assertNotIn("PRIVATE", str(result))
                self.assertNotIn("nativeThreadObservation", self.wake.ledger.command["notification"])

    def test_connection_constructor_failure_is_sanitized_without_send(self):
        with patch("orchestrator.app_server_wake.WakeProxy", side_effect=OSError("PRIVATE PATH TOKEN")):
            result = self.wake.send(BRAIN, "pointer", "control")
        self.assertEqual(result["nativeFailure"], {"version": 1, "stage": "connect",
            "reason": "io_unavailable", "resumeAttempted": False, "turnStartAttempted": False})
        self.assertNotIn("PRIVATE", str(result))
        self.assertFalse(FakeProxy.instances)

    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    def test_observer_start_failure_keeps_returned_turn_id_without_retry(self):
        with patch("orchestrator.app_server_wake.threading.Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("PRIVATE OBSERVER ERROR")
            result = self.wake.send(BRAIN, "pointer", "control")
        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["nativeTurnId"], TURN)
        self.assertEqual(result["nativeTurnStatus"], "unconfirmed")
        self.assertEqual(result["nativeFailure"]["stage"], "subscription")
        self.assertEqual(self.wake.ledger.command["notification"]["nativeThreadObservation"]["nativeTurnId"], TURN)
        self.assertEqual([m for m, _ in FakeProxy.instances[-1].calls], ["thread/read", "thread/resume", "turn/start"])
        self.assertFalse(self.wake._subscriptions)
        self.assertTrue(FakeProxy.instances[-1].closed)
        self.assertNotIn("PRIVATE", str(result))

    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    def test_active_brain_refuses_without_owned_prompt_stream(self):
        FakeProxy.status = "active"
        result = self.wake.send(BRAIN, "fixed pointer", "saved-control")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("approval coverage", result["detail"])
        self.assertEqual([m for m, _ in FakeProxy.instances[0].calls], ["thread/read"])
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

    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    def test_missing_native_project_identity_refuses_without_resume_or_start(self):
        FakeProxy.project_id = None
        result = self.wake.send(BRAIN, "pointer", "control")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("project identity", result["detail"])
        self.assertEqual([method for method, _ in FakeProxy.instances[0].calls], ["thread/read"])

    @patch("orchestrator.app_server_wake.threading.Thread", FakeThread)
    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    def test_distinct_catalog_project_id_does_not_replace_app_server_identity(self):
        self.binding["brains"][BRAIN]["catalogProjectId"] = OTHER
        result = self.wake.send(BRAIN, "fixed pointer", "control")
        self.assertEqual(result["status"], "accepted")
        self.assertEqual([method for method, _ in FakeProxy.instances[0].calls],
                         ["thread/read", "thread/resume", "turn/start"])

    @patch("orchestrator.app_server_wake.WakeProxy", FakeProxy)
    def test_catalog_project_id_cannot_authorize_a_different_native_project(self):
        self.binding["brains"][BRAIN]["catalogProjectId"] = OTHER
        FakeProxy.project_id = OTHER
        result = self.wake.send(BRAIN, "fixed pointer", "control")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual([method for method, _ in FakeProxy.instances[0].calls], ["thread/read"])

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
                self.binding["brains"][BRAIN]["catalogProjectId"] = OTHER
                path.write_text(json.dumps(self.binding))
                self.assertEqual(load_binding(path)["brains"][BRAIN]["catalogProjectId"], OTHER)
                self.binding["brains"][BRAIN]["catalogProjectId"] = "local-project-identity"
                path.write_text(json.dumps(self.binding))
                self.assertEqual(load_binding(path)["brains"][BRAIN]["catalogProjectId"],
                                 "local-project-identity")
                self.binding["brains"][BRAIN]["catalogProjectId"] = "bad\nidentity"
                path.write_text(json.dumps(self.binding))
                with self.assertRaises(Refusal):
                    load_binding(path)
                self.binding["brains"][BRAIN]["catalogProjectId"] = OTHER
                del self.binding["brains"][BRAIN]["nativePolicy"]
                path.write_text(json.dumps(self.binding))
                with self.assertRaises(Refusal):
                    load_binding(path)
                self.binding["brains"][BRAIN]["nativePolicy"] = {**NATIVE_APPROVAL_POLICY,
                                                                   "approvalPolicy": "never"}
                path.write_text(json.dumps(self.binding))
                with self.assertRaises(Refusal):
                    load_binding(path)
                self.binding["brains"][BRAIN]["nativePolicy"] = NATIVE_APPROVAL_POLICY.copy()
                self.binding["brains"][BRAIN]["extra"] = PROJECT
                path.write_text(json.dumps(self.binding))
                with self.assertRaises(Refusal):
                    load_binding(path)
                del self.binding["brains"][BRAIN]["extra"]
                path.write_text(json.dumps(self.binding))
                path.chmod(0o644)
                with self.assertRaises(Refusal):
                    load_binding(path)

    def test_event_observer_retains_only_status_and_never_grants_permission(self):
        ledger = MemoryLedger()
        self.wake.ledger = ledger
        proxy = EventProxy({"id": 9, "method": "tool/requestUserInput",
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

    def test_command_approval_is_exact_owner_choice_and_same_socket_response(self):
        ledger = MemoryLedger()
        self.wake.ledger = ledger
        proxy = ApprovalProxy(
            {"method": "item/started", "params": {"threadId": BRAIN, "turnId": TURN,
                "item": {"id": "item-1", "type": "commandExecution", "command": "echo test",
                         "cwd": "/fixture/brain"}}},
            {"id": 9, "method": "item/commandExecution/requestApproval", "params": {
                "threadId": BRAIN, "turnId": TURN, "itemId": "item-1",
                **COMMAND_REQUIRED,
                "command": "echo test", "cwd": "/fixture/brain", "reason": "run a check",
                "proposedExecpolicyAmendment": ["echo test"],
                "availableDecisions": ["accept", {"acceptWithExecpolicyAmendment": {
                    "execpolicy_amendment": ["echo test"]}}, "decline", "cancel"]}})
        with patch.object(self.wake, "_within_bound_checkout", return_value=True), \
                patch.object(self.wake, "_phase_allows_accept", return_value=True):
            observer = threading.Thread(target=self.wake._observe_turn,
                                        args=(proxy, "control", BRAIN, TURN))
            observer.start()
            offered = wait_pending(self.wake)
            self.assertTrue(offered["canAccept"])
            self.assertEqual(offered["request"]["command"], "echo test")
            self.assertEqual(offered["item"]["id"], "item-1")
            with self.assertRaises(Refusal):
                self.wake.confirm_approval(BRAIN, "wrong-command", offered["requestHash"], "accept")
            with self.assertRaises(Refusal):
                self.wake.confirm_approval(BRAIN, "control", "stale-hash", "accept")
            with patch.object(self.wake, "_accept_authorized_in_db", return_value=True):
                ledger.command["notification"]["nativeApprovals"] = [{
                    "requestHash": offered["requestHash"], "decision": "accept",
                    "turnId": TURN, "status": "claimed"}]
                self.assertEqual(self.wake.confirm_approval(BRAIN, "control", offered["requestHash"], "accept")["status"], "queued")
                with self.assertRaises(Refusal):
                    self.wake.confirm_approval(BRAIN, "control", offered["requestHash"], "accept")
                observer.join(timeout=2)
        self.assertFalse(observer.is_alive())
        self.assertEqual(proxy.writes, [{"id": 9, "result": {"decision": "accept"}}])
        self.assertTrue(proxy.closed)
        self.assertEqual(ledger.command["notification"]["nativeTurnStatus"], "completed")
        self.assertEqual(ledger.command["notification"]["nativeApprovals"][0]["status"], "resolved")
        self.assertEqual([event[0] for event in ledger.events],
                         ["native_permission_status", "native_permission_status"])
        self.assertNotIn("echo test", str(ledger.command))
        self.assertIsNone(self.wake.pending_approval(BRAIN))

    def test_incomplete_and_wider_approvals_are_decline_only(self):
        for method, params, item in (
            ("item/commandExecution/requestApproval", {"command": "curl example.com",
                "cwd": "/fixture/brain", "networkApprovalContext": {"host": "example.com", "protocol": "https"}}, None),
            ("item/fileChange/requestApproval", {"reason": "edit"}, None),
            ("item/fileChange/requestApproval", {"reason": "edit"},
                {"id": "item-1", "type": "fileChange", "changes": [{"path": "x", "kind": "update"}]}),
        ):
            with self.subTest(method=method, params=params):
                ledger = MemoryLedger()
                self.wake.ledger = ledger
                events = []
                if item is not None:
                    events.append({"method": "item/started", "params": {
                        "threadId": BRAIN, "turnId": TURN, "item": item}})
                events.append({"id": 13, "method": method, "params": {
                    "threadId": BRAIN, "turnId": TURN, "itemId": "item-1",
                    **(COMMAND_REQUIRED if method == "item/commandExecution/requestApproval" else FILE_REQUIRED),
                    **params}})
                proxy = ApprovalProxy(*events)
                observer = threading.Thread(target=self.wake._observe_turn,
                                            args=(proxy, "control", BRAIN, TURN))
                observer.start()
                offered = wait_pending(self.wake)
                self.assertFalse(offered["canAccept"])
                with self.assertRaises(Refusal):
                    self.wake.confirm_approval(BRAIN, "control", offered["requestHash"], "accept")
                self.wake.confirm_approval(BRAIN, "control", offered["requestHash"], "decline")
                observer.join(timeout=2)
                self.assertFalse(observer.is_alive())
                self.assertEqual(proxy.writes, [{"id": 13, "result": {"decision": "decline"}}])

    def test_native_resolution_invalidates_pending_before_owner_decision(self):
        self.wake.ledger = MemoryLedger()
        proxy = ApprovalProxy({"id": 7, "method": "item/commandExecution/requestApproval",
            "params": {"threadId": BRAIN, "turnId": TURN, "itemId": "item-1",
                       **COMMAND_REQUIRED,
                       "command": "echo test", "cwd": "/fixture/brain"}},
            {"method": "serverRequest/resolved", "params": {"threadId": BRAIN,
                "requestId": 7}})
        self.wake._observe_turn(proxy, "control", BRAIN, TURN)
        self.assertIsNone(self.wake.pending_approval(BRAIN))
        self.assertEqual(proxy.writes, [])
        self.assertEqual(self.wake.ledger.command["notification"]["nativeTurnStatus"], "native_attention_required")

    def test_complete_file_change_can_be_approved_only_with_exact_prior_item(self):
        self.wake.ledger = MemoryLedger()
        proxy = ApprovalProxy(
            {"method": "item/started", "params": {"threadId": BRAIN, "turnId": TURN,
                "item": {"id": "change-1", "type": "fileChange", "changes": [
                    {"path": "/fixture/brain/file.py", "kind": "update", "diff": "+safe\n"}]}}},
            {"id": "request-1", "method": "item/fileChange/requestApproval", "params": {
                "threadId": BRAIN, "turnId": TURN, "itemId": "change-1",
                **FILE_REQUIRED, "reason": "apply patch"}})
        with patch.object(self.wake, "_within_bound_checkout", return_value=True), \
                patch.object(self.wake, "_phase_allows_accept", return_value=True):
            observer = threading.Thread(target=self.wake._observe_turn,
                                        args=(proxy, "control", BRAIN, TURN))
            observer.start()
            offered = wait_pending(self.wake)
            self.assertTrue(offered["canAccept"])
            self.assertEqual(offered["item"]["changes"][0]["diff"], "+safe\n")
            with patch.object(self.wake, "_accept_authorized_in_db", return_value=True):
                self.wake.confirm_approval(BRAIN, "control", offered["requestHash"], "accept")
                observer.join(timeout=2)
        self.assertEqual(proxy.writes, [{"id": "request-1", "result": {"decision": "accept"}}])

    def test_pause_after_owner_click_prevents_native_accept_response(self):
        ledger = MemoryLedger()
        self.wake.ledger = ledger
        proxy = ApprovalProxy({"id": 5, "method": "item/commandExecution/requestApproval",
            "params": {"threadId": BRAIN, "turnId": TURN, "itemId": "item-1",
                       **COMMAND_REQUIRED, "command": "echo test", "cwd": "/fixture/brain"}})
        with patch.object(self.wake, "_within_bound_checkout", return_value=True), \
                patch.object(self.wake, "_phase_allows_accept", return_value=True):
            observer = threading.Thread(target=self.wake._observe_turn,
                                        args=(proxy, "control", BRAIN, TURN))
            observer.start()
            offered = wait_pending(self.wake)
            with patch.object(self.wake, "_accept_authorized_in_db", return_value=False) as guard:
                ledger.command["notification"]["nativeApprovals"] = [{
                    "requestHash": offered["requestHash"], "decision": "accept",
                    "turnId": TURN, "status": "claimed"}]
                self.wake.confirm_approval(BRAIN, "control", offered["requestHash"], "accept")
                observer.join(timeout=2)
        guard.assert_called_once_with(None, "control", BRAIN, TURN, offered["requestHash"])
        self.assertEqual(proxy.writes, [])
        self.assertEqual(ledger.command["notification"]["nativeApprovals"][0]["status"], "blocked")
        self.assertEqual(ledger.command["notification"]["nativeTurnStatus"], "native_attention_required")

    def test_native_approval_receipt_advances_only_matching_claim_monotonically(self):
        ledger = MemoryLedger()
        self.wake.ledger = ledger
        note = ledger.command["notification"]
        note["nativeApprovals"] = [{"requestHash": "a" * 64, "turnId": TURN,
                                    "decision": "accept", "status": "claimed"}]
        self.wake._record_approval_status("control", BRAIN, TURN, "b" * 64, "response_written")
        self.assertEqual(note["nativeApprovals"][0]["status"], "claimed")
        self.wake._record_approval_status("control", BRAIN, TURN, "a" * 64, "response_written")
        self.assertEqual(note["nativeApprovals"][0]["status"], "response_written")
        self.wake._record_approval_status("control", BRAIN, TURN, "a" * 64, "blocked")
        self.assertEqual(note["nativeApprovals"][0]["status"], "response_written")
        self.wake._record_approval_status("control", BRAIN, TURN, "a" * 64, "resolved")
        self.wake._record_approval_status("control", BRAIN, TURN, "a" * 64, "uncertain")
        self.assertEqual(note["nativeApprovals"][0]["status"], "resolved")
        self.assertEqual([row[1]["status"] for row in ledger.events], ["response_written", "resolved"])

    def test_final_accept_guard_requires_current_run_and_durable_owner_claim(self):
        class GuardLedger(MemoryLedger):
            def __init__(self):
                super().__init__()
                self.meta = {"brainId": BRAIN, "standardRun": {
                    "protocol": "standard_cooperative_v1", "status": "running"}}
                self.command["notification"].update(nativeApprovals=[{
                    "requestHash": "h" * 64, "decision": "accept", "turnId": TURN,
                    "status": "claimed"}])

            def get(self, db, table, key):
                return self.meta if table == "meta" else self.command

        ledger = GuardLedger()
        self.wake.ledger = ledger
        with patch("orchestrator.standard.current_blockers", return_value=[]):
            self.assertTrue(self.wake._accept_authorized_in_db(None, "control", BRAIN, TURN, "h" * 64))
            ledger.meta["brainControl"] = {"desired": "stopped", "phase": "stop_requested"}
            self.assertFalse(self.wake._accept_authorized_in_db(None, "control", BRAIN, TURN, "h" * 64))
            del ledger.meta["brainControl"]
            ledger.meta["standardRun"]["status"] = "paused"
            self.assertFalse(self.wake._accept_authorized_in_db(None, "control", BRAIN, TURN, "h" * 64))
            ledger.meta["standardRun"]["status"] = "running"
            ledger.command["notification"]["nativeApprovals"] = []
            self.assertFalse(self.wake._accept_authorized_in_db(None, "control", BRAIN, TURN, "h" * 64))

    def test_command_approval_requires_consistent_full_prompt(self):
        params = {"threadId": BRAIN, "turnId": TURN, "itemId": "item-1",
                  **COMMAND_REQUIRED, "command": "echo yes", "cwd": "/fixture/brain"}
        row = {"id": 8, "method": "item/commandExecution/requestApproval", "params": params}
        good_item = {"id": "item-1", "type": "commandExecution",
                     "command": "echo yes", "cwd": "/fixture/brain"}
        self.assertTrue(self.wake._complete_approval(row, BRAIN, TURN, good_item))
        self.assertFalse(self.wake._complete_approval(row, BRAIN, TURN,
            {**good_item, "command": "echo no"}))
        for changed in ({"kind": "writeStdin"},
                        {"networkApprovalContext": {"host": "example.com", "protocol": "https"}},
                        {"additionalPermissions": {"network": True}},
                        {"proposedNetworkPolicyAmendments": [{"host": "example.com", "action": "allow"}]},
                        {"approvalId": "opaque"}, {"cwd": "/fixture/../brain"}):
            with self.subTest(changed=changed):
                self.assertFalse(self.wake._complete_approval(
                    {**row, "params": {**params, **changed}}, BRAIN, TURN, good_item))

    def test_native_accept_is_confined_to_bound_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            checkout = base / "checkout"
            outside = base / "outside"
            checkout.mkdir(); outside.mkdir()
            (checkout / "nested").mkdir()
            (checkout / "escape").symlink_to(outside, target_is_directory=True)
            self.binding["brains"][BRAIN]["cwd"] = str(checkout)
            command = {"method": "item/commandExecution/requestApproval",
                       "params": {"cwd": str(checkout / "nested")}}
            self.assertTrue(self.wake._within_bound_checkout(command, BRAIN, None))
            self.assertFalse(self.wake._within_bound_checkout(
                {**command, "params": {"cwd": str(outside)}}, BRAIN, None))
            self.assertFalse(self.wake._within_bound_checkout(
                {**command, "params": {"cwd": str(checkout / "escape")}}, BRAIN, None))
            file_request = {"method": "item/fileChange/requestApproval", "params": {}}
            def item(path):
                return {"changes": [{"path": str(path), "kind": "update", "diff": "+line\n"}]}
            self.assertTrue(self.wake._within_bound_checkout(file_request, BRAIN,
                                                              item(checkout / "new.py")))
            self.assertFalse(self.wake._within_bound_checkout(file_request, BRAIN,
                                                               item(outside / "new.py")))
            self.assertFalse(self.wake._within_bound_checkout(file_request, BRAIN,
                                                               item(checkout / "escape" / "new.py")))

    def test_pending_projection_hides_accept_after_phase_stop(self):
        self.wake.ledger = MemoryLedger()
        proxy = ApprovalProxy({"id": 5, "method": "item/commandExecution/requestApproval",
            "params": {"threadId": BRAIN, "turnId": TURN, "itemId": "item-1",
                       **COMMAND_REQUIRED, "command": "echo test", "cwd": "/fixture/brain"}})
        with patch.object(self.wake, "_within_bound_checkout", return_value=True), \
                patch.object(self.wake, "_phase_allows_accept", side_effect=[True, False]):
            observer = threading.Thread(target=self.wake._observe_turn,
                                        args=(proxy, "control", BRAIN, TURN))
            observer.start()
            current = wait_pending(self.wake)
            self.assertTrue(current["canAccept"])
            stopped = self.wake.pending_approval(BRAIN)
            self.assertFalse(stopped["canAccept"])
            self.assertNotIn("accept", stopped["allowedDecisions"])
        self.wake.close()
        observer.join(timeout=2)

    def test_incomplete_native_prompt_never_advertises_accept(self):
        self.wake.ledger = MemoryLedger()
        proxy = ApprovalProxy({"id": 5, "method": "item/commandExecution/requestApproval",
            "params": {"threadId": BRAIN, "turnId": TURN, "itemId": "item-1",
                       "command": "echo test", "cwd": "/fixture/brain"}})
        observer = threading.Thread(target=self.wake._observe_turn,
                                    args=(proxy, "control", BRAIN, TURN))
        observer.start()
        current = wait_pending(self.wake)
        self.assertFalse(current["canAccept"])
        self.assertNotIn("accept", current["allowedDecisions"])
        with self.assertRaises(Refusal):
            self.wake.confirm_approval(BRAIN, "control", current["requestHash"], "accept")
        self.wake.close()
        observer.join(timeout=2)
        self.assertEqual(proxy.writes, [])

    def test_installed_schema_default_command_fields_are_complete(self):
        request = {"method": "item/commandExecution/requestApproval",
                   "params": {"threadId": BRAIN, "turnId": TURN, "itemId": "item-1",
                              "startedAtMs": 1, "command": "/usr/bin/true",
                              "cwd": "/fixture/brain", "availableDecisions": ["accept", "cancel"]}}
        self.assertTrue(self.wake._complete_approval(request, BRAIN, TURN, None))
        request["params"]["proposedExecpolicyAmendment"] = ["/usr/bin/true"]
        request["params"]["availableDecisions"] = ["accept", {"acceptWithExecpolicyAmendment": {
            "execpolicy_amendment": ["/usr/bin/true"]}}, "cancel"]
        self.assertTrue(self.wake._complete_approval(request, BRAIN, TURN, None))
        request["params"]["proposedExecpolicyAmendment"] = [""]
        self.assertFalse(self.wake._complete_approval(request, BRAIN, TURN, None))
        request["params"]["proposedExecpolicyAmendment"] = ["/usr/bin/true"]
        request["params"]["kind"] = "stdin"
        self.assertFalse(self.wake._complete_approval(request, BRAIN, TURN, None))

    def test_pause_writer_cannot_commit_between_accept_guard_and_frame(self):
        class LockedLedger:
            def __init__(self):
                self.lock = threading.Lock()

            @contextmanager
            def tx(self):
                with self.lock:
                    yield None

        class HeldProxy:
            def __init__(self):
                self.entered = threading.Event()
                self.release = threading.Event()
                self.writes = []

            def _write(self, value):
                self.entered.set()
                if not self.release.wait(timeout=2):
                    raise Refusal("Test write timed out")
                self.writes.append(value)

        ledger = LockedLedger()
        proxy = HeldProxy()
        self.wake.ledger = ledger
        result = []
        pause_committed = threading.Event()
        with patch.object(self.wake, "_accept_authorized_in_db", return_value=True):
            writer = threading.Thread(target=lambda: result.append(self.wake._write_accept_if_current(
                proxy, {"id": 1, "result": {"decision": "accept"}}, "control", BRAIN, TURN, "h" * 64)))
            writer.start()
            self.assertTrue(proxy.entered.wait(timeout=2))
            pause = threading.Thread(target=lambda: (ledger.lock.acquire(), pause_committed.set(), ledger.lock.release()))
            pause.start()
            self.assertFalse(pause_committed.wait(timeout=0.05))
            proxy.release.set()
            writer.join(timeout=2); pause.join(timeout=2)
        self.assertEqual(result, [True])
        self.assertTrue(pause_committed.is_set())
        self.assertEqual(proxy.writes, [{"id": 1, "result": {"decision": "accept"}}])

    def test_expired_preview_and_shutdown_cannot_send(self):
        self.wake.ledger = MemoryLedger()
        proxy = ApprovalProxy({"id": 5, "method": "item/commandExecution/requestApproval",
            "params": {"threadId": BRAIN, "turnId": TURN, "itemId": "item-1",
                       **COMMAND_REQUIRED, "command": "echo test", "cwd": "/fixture/brain"}})
        observer = threading.Thread(target=self.wake._observe_turn,
                                    args=(proxy, "control", BRAIN, TURN))
        observer.start()
        offered = wait_pending(self.wake)
        with self.wake._lock:
            self.wake._pending_approvals[BRAIN]["projection"]["expiresAt"] = time.time() - 1
        with self.assertRaises(Refusal):
            self.wake.confirm_approval(BRAIN, "control", offered["requestHash"], "accept")
        self.wake.close()
        observer.join(timeout=2)
        self.assertFalse(observer.is_alive())
        self.assertEqual(proxy.writes, [])

    def test_early_server_request_is_not_dropped_during_turn_start(self):
        proxy = WakeProxy(self.binding["endpoint"])
        proxy._awaiting_start = True
        request = {"id": 4, "method": "item/commandExecution/requestApproval",
                   "params": {"threadId": BRAIN, "turnId": TURN,
                              "itemId": "item-1", **COMMAND_REQUIRED}}
        payload = json.dumps(request).encode()
        proxy.buffer = b"\x81\x7e" + len(payload).to_bytes(2, "big") + payload
        self.assertEqual(proxy._line(), {"method": "wake/earlyServerRequest", "params": {}})
        self.assertEqual(proxy._early_requests, [request])

    def test_ping_and_approval_frames_are_serialized(self):
        proxy = WakeProxy(self.binding["endpoint"])
        overlap = {"active": 0, "maximum": 0}

        def record_frame(_proxy, _opcode, _payload):
            overlap["active"] += 1
            overlap["maximum"] = max(overlap["maximum"], overlap["active"])
            time.sleep(0.02)
            overlap["active"] -= 1

        with patch.object(ReadProxy, "_send_frame", record_frame):
            first = threading.Thread(target=proxy._send_frame, args=(10, b"ping"))
            second = threading.Thread(target=proxy._send_frame, args=(1, b"approval"))
            first.start(); second.start()
            first.join(); second.join()
        self.assertEqual(overlap["maximum"], 1)

    def test_early_turn_completion_is_retained_without_private_content(self):
        proxy = WakeProxy(self.binding["endpoint"])
        proxy._awaiting_start = True
        payload = json.dumps({"method": "turn/completed", "params": {
            "threadId": BRAIN, "turn": {"id": TURN, "status": "completed",
                                      "items": ["PRIVATE TRANSCRIPT"]}}}).encode()
        proxy.buffer = b"\x81\x7e" + len(payload).to_bytes(2, "big") + payload
        proxy._line()
        self.assertEqual(proxy._early_completion, (BRAIN, TURN, "completed"))
        ledger = MemoryLedger()
        self.wake.ledger = ledger
        proxy.__exit__ = lambda *_: None
        self.wake._observe_turn(proxy, "control", BRAIN, TURN)
        self.assertEqual(ledger.command["notification"]["nativeTurnStatus"], "completed")
        self.assertNotIn("PRIVATE", str(ledger.command))
