import copy
import unittest
from unittest.mock import patch

from orchestrator.app_server_wake import AppServerWake
from orchestrator.core import Refusal
from test_app_server_wake import BRAIN, OTHER, FakeProxy, MemoryLedger


class HostConnectionTest(unittest.TestCase):
    def setUp(self):
        FakeProxy.instances = []
        self.wake = AppServerWake({"endpoint": {}, "brains": {BRAIN: {"workspaceId": "fixture"}}}, MemoryLedger())

    def test_status_is_cached_and_unknown_until_explicit_handshake(self):
        with patch("orchestrator.app_server_wake.ReadProxy", FakeProxy), patch.object(self.wake, "configured", return_value=True), patch("orchestrator.app_server_wake.validate_endpoint"):
            before = copy.deepcopy(self.wake.ledger.command)
            self.assertEqual(self.wake.connection_status(BRAIN)["status"], "unchecked")
            self.assertEqual(FakeProxy.instances, [])
            result = self.wake.check_connection(BRAIN)
            self.assertEqual(result["status"], "connected")
            self.assertEqual(len(FakeProxy.instances), 1)
            self.assertEqual(FakeProxy.instances[0].calls, [], "No task read, resume, turn, or permission RPC")
            self.assertTrue(FakeProxy.instances[0].closed)
            self.assertEqual(self.wake.ledger.command, before)
            self.assertEqual(self.wake.connection_status(OTHER)["status"], "unchecked")
            with patch("orchestrator.app_server_wake.time.time", return_value=result["checkedAt"] + 31):
                stale = self.wake.connection_status(BRAIN)
            self.assertEqual(stale["status"], "stale")
            self.assertEqual(stale["checkedAt"], result["checkedAt"])
            self.assertEqual(len(FakeProxy.instances), 1)

    def test_stale_socket_error_is_sanitized_without_retry(self):
        with patch.object(self.wake, "configured", return_value=True), patch("orchestrator.app_server_wake.ReadProxy", side_effect=Refusal("PRIVATE_SOCKET_TOKEN")) as proxy:
            result = self.wake.check_connection(BRAIN)
        self.assertEqual(result["status"], "disconnected")
        self.assertNotIn("PRIVATE_SOCKET_TOKEN", str(result))
        proxy.assert_called_once()

    def test_binding_drift_and_foreign_workspace_do_not_connect(self):
        with patch.object(self.wake, "configured", return_value=False), patch("orchestrator.app_server_wake.ReadProxy") as proxy:
            self.assertEqual(self.wake.check_connection(BRAIN)["status"], "unavailable")
            proxy.assert_not_called()

    def test_post_handshake_identity_drift_is_not_healthy(self):
        with patch.object(self.wake, "configured", return_value=True), patch("orchestrator.app_server_wake.ReadProxy", FakeProxy), patch("orchestrator.app_server_wake.validate_endpoint", side_effect=Refusal("changed")):
            self.assertEqual(self.wake.check_connection(BRAIN)["status"], "disconnected")

    def test_concurrent_check_and_closed_host_never_connect(self):
        self.wake._connection_lock.acquire()
        with self.assertRaisesRegex(Refusal, "already in progress"):
            self.wake.check_connection(BRAIN)
        self.wake._connection_lock.release()
        self.wake.close()
        with patch("orchestrator.app_server_wake.ReadProxy") as proxy:
            self.assertEqual(self.wake.check_connection(BRAIN)["status"], "unavailable")
            proxy.assert_not_called()

    def test_shutdown_during_handshake_is_not_healthy(self):
        with patch.object(self.wake, "configured", return_value=True), patch("orchestrator.app_server_wake.ReadProxy", FakeProxy), patch("orchestrator.app_server_wake.validate_endpoint", side_effect=lambda endpoint: self.wake.close()):
            self.assertEqual(self.wake.check_connection(BRAIN)["status"], "disconnected")
