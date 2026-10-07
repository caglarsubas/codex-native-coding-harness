"""Disposable pipes only; never launch or probe a real native host."""
import json
import os
import selectors
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orchestrator.app_server_wake import AppServerWake, NativeConnectionLost, WakeProxy
from orchestrator.core import Refusal
from test_app_server_wake import (BRAIN, TURN, MemoryLedger, ApprovalProxy,
                                  COMMAND_REQUIRED, wait_pending)


class WakeConnectionLifetimeTest(unittest.TestCase):
    def proxy(self):
        proxy = WakeProxy({})
        proxy.deadline = time.monotonic() + 2
        return proxy

    def watch(self, proxy, clock):
        with patch.object(proxy, "_epoch", return_value=("fixture",)), \
                patch("orchestrator.app_server_wake.time.monotonic", return_value=clock):
            proxy.watch_connection()

    def test_quiet_healthy_turn_has_no_idle_ttl(self):
        proxy = self.proxy()
        self.watch(proxy, 0)
        with patch.object(proxy, "_epoch", return_value=("fixture",)), \
                patch.object(proxy, "_send_frame") as send:
            for now in range(15, 1000, 15):
                with patch("orchestrator.app_server_wake.time.monotonic", return_value=now):
                    proxy._watch_tick()
                    self.assertEqual(send.call_args.args[0], 9)
                    self.assertTrue(proxy._control_frame(10, send.call_args.args[1]))
                    self.assertIsNone(proxy._pending_ping)
            self.assertGreater(send.call_count, 60)

    def test_many_control_pongs_do_not_end_a_quiet_healthy_subscription(self):
        proxy = self.proxy()
        self.watch(proxy, time.monotonic())
        payload = json.dumps({"method": "turn/completed", "params": {"threadId": BRAIN}}).encode()
        proxy.buffer = b"\x8a\x00" * 100 + bytes([0x81, len(payload)]) + payload
        self.assertEqual(proxy._line()["method"], "turn/completed")

    def test_wrong_pong_or_other_activity_cannot_renew_lost_connection(self):
        proxy = self.proxy()
        self.watch(proxy, 0)
        with patch.object(proxy, "_epoch", return_value=("fixture",)), \
                patch.object(proxy, "_send_frame") as send:
            with patch("orchestrator.app_server_wake.time.monotonic", return_value=15):
                proxy._watch_tick()
                proxy._control_frame(10, b"not-the-nonce")
                proxy._control_frame(9, b"server-ping")
            with patch("orchestrator.app_server_wake.time.monotonic", return_value=25):
                with self.assertRaises(NativeConnectionLost) as error:
                    proxy._watch_tick()
            self.assertEqual(error.exception.reason, "heartbeat_missing")
            self.assertEqual([call.args[0] for call in send.call_args_list], [9, 10])

    def test_endpoint_replacement_never_reconnects_or_sends_to_new_host(self):
        proxy = self.proxy()
        self.watch(proxy, 0)
        with patch.object(proxy, "_epoch", return_value=("replacement",)), \
                patch.object(proxy, "_send_frame") as send, \
                patch("orchestrator.app_server_wake.time.monotonic", return_value=15):
            with self.assertRaises(NativeConnectionLost) as error:
                proxy._watch_tick()
        self.assertEqual(error.exception.reason, "endpoint_changed")
        send.assert_not_called()

    def test_connection_epoch_is_pinned_before_initialize_and_retained_at_watch(self):
        from orchestrator.native_read_client import ReadProxy
        proxy = self.proxy()
        with patch.object(proxy, "_epoch", side_effect=[("original",), ("replacement",)]), \
                patch.object(ReadProxy, "__enter__") as enter, \
                patch.object(proxy, "__exit__") as close:
            with self.assertRaises(NativeConnectionLost):
                proxy.__enter__()
        enter.assert_called_once()
        close.assert_called_once()
        proxy = self.proxy()
        proxy._endpoint_epoch = ("original",)
        with patch.object(proxy, "_epoch", return_value=("replacement",)):
            with self.assertRaises(NativeConnectionLost):
                proxy.watch_connection()
        self.assertFalse(proxy._watching)

    def test_lost_approval_connection_keeps_decision_uncertain_with_no_second_response(self):
        class LostApprovalProxy(ApprovalProxy):
            def _line(self):
                value = super()._line()
                if isinstance(value, Exception):
                    raise value
                return value
            def _write(self, value):
                self.writes.append(value)
                self.events.put(NativeConnectionLost("heartbeat_missing"))
        proxy = LostApprovalProxy({'id': 9, 'method': 'item/commandExecution/requestApproval',
            'params': {'threadId': BRAIN, 'turnId': TURN, 'itemId': 'fixture',
                       **COMMAND_REQUIRED, 'command': 'echo synthetic', 'cwd': '/fixture'}})
        ledger = MemoryLedger()
        wake = AppServerWake({'endpoint': {}, 'brains': {BRAIN: {'cwd': '/fixture'}}}, ledger)
        observer = threading.Thread(target=wake._observe_turn, args=(proxy, 'control', BRAIN, TURN))
        observer.start()
        offered = wait_pending(wake)
        ledger.command['notification']['nativeApprovals'] = [{
            'requestHash': offered['requestHash'], 'decision': 'decline',
            'turnId': TURN, 'status': 'claimed'}]
        wake.confirm_approval(BRAIN, 'control', offered['requestHash'], 'decline')
        observer.join(timeout=2)
        self.assertFalse(observer.is_alive())
        self.assertEqual(proxy.writes, [{'id': 9, 'result': {'decision': 'decline'}}])
        self.assertEqual(ledger.command['notification']['nativeApprovals'][0]['status'], 'uncertain')
        self.assertEqual(ledger.command['notification']['nativeTurnStatus'], 'connection_lost')
        self.assertIsNone(wake.pending_approval(BRAIN))
        with self.assertRaises(Refusal):
            wake.confirm_approval(BRAIN, 'control', offered['requestHash'], 'decline')
        self.assertEqual(len(proxy.writes), 1)

    def test_probe_write_failure_is_sanitized_and_never_retried(self):
        proxy = self.proxy()
        self.watch(proxy, 0)
        with patch.object(proxy, "_epoch", return_value=("fixture",)), \
                patch.object(proxy, "_send_frame", side_effect=Refusal("PRIVATE")) as send, \
                patch("orchestrator.app_server_wake.time.monotonic", return_value=15):
            with self.assertRaises(NativeConnectionLost) as error:
                proxy._watch_tick()
        self.assertEqual(error.exception.reason, "proxy_unavailable")
        self.assertNotIn("PRIVATE", str(error.exception))
        self.assertEqual(send.call_count, 1)

    def test_close_frame_and_missing_endpoint_are_explicit_loss(self):
        proxy = self.proxy()
        self.watch(proxy, 0)
        with self.assertRaises(NativeConnectionLost) as error:
            proxy._control_frame(8, b"PRIVATE REASON")
        self.assertEqual(error.exception.reason, "websocket_closed")
        self.assertNotIn("PRIVATE", str(error.exception))
        with self.assertRaises(NativeConnectionLost) as error:
            self.proxy().watch_connection()
        self.assertEqual(error.exception.reason, "endpoint_changed")

    def test_real_blackholed_pipe_ends_stream_without_waiting_six_hours(self):
        incoming, server_output = os.pipe()
        server_input, outgoing = os.pipe()
        proxy = self.proxy()
        proxy.process = SimpleNamespace(stdout=os.fdopen(incoming, "rb", buffering=0),
                                        stdin=os.fdopen(outgoing, "wb", buffering=0))
        os.set_blocking(incoming, False)
        os.set_blocking(outgoing, False)
        proxy.heartbeat_interval = proxy.heartbeat_timeout = 0.025
        ledger = MemoryLedger()
        ledger.command.update(status="queued", result="Waiting for brain receipt")
        ledger.command["notification"]["nativeThreadObservation"] = {
            "rootThreadId": BRAIN, "streamStatus": "open", "complete": False, "events": [], "gaps": []}
        wake = AppServerWake({"endpoint": {}, "brains": {BRAIN: {"workspaceId": "fixture"}}}, ledger)
        def close(*_):
            proxy.process.stdin.close()
            proxy.process.stdout.close()
        try:
            with patch.object(proxy, "_epoch", return_value=("fixture",)), \
                    patch.object(proxy, "__exit__", side_effect=close):
                observer = threading.Thread(target=wake._observe_turn, args=(proxy, "control", BRAIN, TURN))
                observer.start()
                observer.join(timeout=1)
                self.assertFalse(observer.is_alive())
            notification = ledger.command["notification"]
            self.assertEqual(notification["status"], "accepted", "Start acknowledgment is not erased")
            self.assertEqual(ledger.command["status"], "queued", "No fabricated brain receipt")
            self.assertEqual(notification["nativeTurnStatus"], "connection_lost")
            self.assertEqual(notification["nativeConnectionLoss"]["outcome"], "unknown")
            self.assertFalse(notification["nativeConnectionLoss"]["replayed"])
            self.assertEqual(notification["nativeThreadObservation"]["streamStatus"], "unconfirmed")
            self.assertFalse(notification["nativeThreadObservation"]["complete"])
            frame = os.read(server_input, 64)
            self.assertEqual(frame[0], 0x89, "Only a WebSocket ping, not any native RPC")
            self.assertEqual(len(frame), 14, "One masked eight-byte probe, no retry")
            self.assertEqual(wake.connection_status(BRAIN)["status"], "disconnected")
            self.assertEqual(wake.connection_status("foreign")["status"], "unchecked")
        finally:
            close()
            os.close(server_input)
            os.close(server_output)

    def test_eof_is_loss_but_read_only_clients_do_not_start_watchdog(self):
        from orchestrator.native_read_client import ReadProxy
        proxy = self.proxy()
        self.watch(proxy, time.monotonic())
        with patch.object(ReadProxy, "_read_bytes", side_effect=Refusal("Native proxy output closed")):
            with self.assertRaises(NativeConnectionLost) as error:
                proxy._read_bytes(2)
        self.assertEqual(error.exception.reason, "proxy_unavailable")
        proxy = self.proxy()
        self.assertFalse(proxy._watching)
        with patch.object(ReadProxy, "_ready") as ready:
            proxy._ready("fixture", selectors.EVENT_READ)
            ready.assert_called_once()

    def test_real_quiet_pipe_answers_pings_and_retains_exact_completion(self):
        incoming, server_output = os.pipe()
        server_input, outgoing = os.pipe()
        proxy = self.proxy()
        proxy.process = SimpleNamespace(stdout=os.fdopen(incoming, 'rb', buffering=0),
                                        stdin=os.fdopen(outgoing, 'wb', buffering=0))
        os.set_blocking(incoming, False)
        os.set_blocking(outgoing, False)
        proxy.heartbeat_interval, proxy.heartbeat_timeout = 0.02, 0.25
        probes, errors = [], []
        def receive(count):
            value = b''
            while len(value) < count:
                part = os.read(server_input, count-len(value))
                if not part:
                    raise AssertionError('Synthetic client closed before completion')
                value += part
            return value
        def server():
            try:
                for _ in range(4):
                    header, mask, body = receive(2), receive(4), receive(8)
                    self.assertEqual(header, b'\x89\x88')
                    nonce = bytes(value ^ mask[i % 4] for i, value in enumerate(body))
                    probes.append(nonce)
                    os.write(server_output, b'\x8a\x08'+nonce)
                payload = json.dumps({'method': 'turn/completed', 'params': {
                    'threadId': BRAIN, 'turn': {'id': TURN, 'status': 'completed'}}}).encode()
                os.write(server_output, b'\x81\x7e'+len(payload).to_bytes(2, 'big')+payload)
            except Exception as error:
                errors.append(error)
        def close(*_):
            proxy.process.stdin.close()
            proxy.process.stdout.close()
        ledger = MemoryLedger()
        wake = AppServerWake({'endpoint': {}, 'brains': {BRAIN: {'workspaceId': 'fixture'}}}, ledger)
        try:
            with patch.object(proxy, '_epoch', return_value=('fixture',)), \
                    patch.object(proxy, '__exit__', side_effect=close):
                peer = threading.Thread(target=server, daemon=True)
                observer = threading.Thread(target=wake._observe_turn, args=(proxy, 'control', BRAIN, TURN))
                peer.start(); observer.start(); observer.join(timeout=2); peer.join(timeout=2)
                self.assertFalse(observer.is_alive())
                self.assertFalse(peer.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(set(probes)), 4)
            self.assertEqual(ledger.command['notification']['nativeTurnStatus'], 'completed')
            self.assertNotIn('nativeConnectionLoss', ledger.command['notification'])
        finally:
            close()
            os.close(server_input)
            os.close(server_output)


if __name__ == "__main__":
    unittest.main()
