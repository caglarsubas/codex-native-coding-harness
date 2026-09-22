import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from orchestrator.account import LocalAccount, Throttled, configure, password_hash
from orchestrator.core import Ledger, Refusal
from orchestrator.server import Dashboard
from orchestrator.workspaces import Registry
import test_server

USER = "owner@example.test"
PASSWORD = "fixture-only-password"


class AccountTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "account.json"
        configure(self.path, USER, PASSWORD)
        self.now = 1000
        self.account = LocalAccount(self.path, clock=lambda: self.now)

    def tearDown(self):
        self.tmp.cleanup()

    def test_hash_only_owner_storage_and_verification(self):
        self.assertNotIn(PASSWORD, self.path.read_text())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(self.account.verify(USER.upper(), PASSWORD))
        with patch("orchestrator.account.password_hash", wraps=password_hash) as derive:
            self.assertFalse(self.account.verify("unknown@example.test", PASSWORD))
            self.assertEqual(derive.call_count, 1)
        self.assertFalse(self.account.verify(USER, "wrong"))
        self.assertEqual(LocalAccount(self.path).identity, self.account.identity)

    def test_throttle_persists_restart_and_recovers(self):
        for _ in range(5): self.assertFalse(self.account.verify(USER, "wrong"))
        reopened = LocalAccount(self.path, clock=lambda: self.now)
        with self.assertRaises(Throttled): reopened.verify(USER, PASSWORD)
        self.now += 301
        self.assertTrue(reopened.verify(USER, PASSWORD))
        self.assertEqual(json.loads(self.path.read_text())["failures"], 0)

    def test_interrupted_attempt_and_write_failure_fail_closed(self):
        with patch("orchestrator.account.password_hash", side_effect=ValueError("interrupted")):
            with self.assertRaises(Refusal): self.account.verify(USER, PASSWORD)
        self.assertEqual(json.loads(self.path.read_text())["failures"], 1)
        with patch.object(self.account, "write", side_effect=OSError("disk full")):
            with self.assertRaises(Refusal): self.account.verify(USER, PASSWORD)

    def test_reset_requires_explicit_replace_and_invalidates_identity(self):
        with self.assertRaises(Refusal): configure(self.path, USER, "different-fixture-password")
        configure(self.path, USER, "different-fixture-password", replace=True)
        with self.assertRaises(Refusal): self.account.ensure_current()
        self.assertNotEqual(LocalAccount(self.path).identity, self.account.identity)

    def test_missing_corrupt_or_permissive_account_fails_closed(self):
        original = self.path.read_text()
        for content in ("{}", "bad", original.replace('"failures": 0', '"failures": -1')):
            self.path.write_text(content)
            with self.assertRaises(Refusal): LocalAccount(self.path)
        self.path.write_text(original); self.path.chmod(0o644)
        with self.assertRaises(Refusal): LocalAccount(self.path)
        self.path.unlink()
        with self.assertRaises(Refusal): LocalAccount(self.path)

    def test_symlink_hardlink_and_public_directory_refused(self):
        target = self.root / "target.json"
        self.path.rename(target); self.path.symlink_to(target)
        with self.assertRaises(Refusal): LocalAccount(self.path)
        self.path.unlink(); os.link(target, self.path)
        with self.assertRaises(Refusal): LocalAccount(self.path)
        self.path.unlink(); target.rename(self.path); self.root.chmod(0o755)
        with self.assertRaises(Refusal): LocalAccount(self.path)
        self.root.chmod(0o700)

    def test_password_bounds_and_schema(self):
        for password in (None, "short", "x" * 1025):
            with self.assertRaises(Refusal): configure(self.path, USER, password, replace=True)
        for username, password in ((None, PASSWORD), (USER, None), (USER, "x" * 1025)):
            self.assertFalse(self.account.verify(username, password))


class AccountServerTest(unittest.TestCase):
    request = test_server.ServerTest.request

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "account.json"
        configure(self.path, USER, PASSWORD)
        self.ledger = Ledger(self.root / "state")
        self.ledger.initialize({"schemaVersion": 1, "brainId": "fixture-brain", "repositories": []})
        self.registry = Registry(self.root / "platform", create=True)
        self.registry.register("fixture", "Fixture", self.ledger.root)
        self.start()

    def start(self, port=0):
        self.server = Dashboard(self.ledger, port, self.root / ".env", runtime_root=self.root,
                                registry=self.registry, account_file=self.path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def tearDown(self):
        self.stop(); self.tmp.cleanup()

    def login(self, days=0):
        status, headers, raw = self.request("/api/login", {"username": USER, "password": PASSWORD, "rememberDays": days})
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        return {"Cookie": headers["Set-Cookie"].split(";")[0], "X-CSRF-Token": json.loads(raw)["csrf"]}

    def test_account_login_no_token_fallback_and_no_disclosure(self):
        status, _, raw = self.request("/api/auth/options")
        self.assertEqual(status, 200); self.assertEqual(json.loads(raw), {"mode": "account"})
        self.assertIsNone(self.server.bootstrap)
        self.assertEqual(self.request("/api/login", {"token": "old-link"})[0], 403)
        self.assertEqual(self.request("/api/workspaces")[0], 401)
        for path in ("/", "/api/auth/options", "/api/session"):
            raw = self.request(path)[2]
            self.assertNotIn(USER.encode(), raw); self.assertNotIn(PASSWORD.encode(), raw)
        auth = self.login()
        self.assertEqual(self.request("/api/workspaces", headers=auth)[0], 200)

    def test_generic_errors_persistent_throttle_and_same_origin(self):
        wrong = self.request("/api/login", {"username": USER, "password": "wrong"})
        unknown = self.request("/api/login", {"username": "other", "password": PASSWORD})
        self.assertEqual(wrong[2], unknown[2])
        for _ in range(3): self.request("/api/login", {"username": USER, "password": "wrong"})
        self.stop(); self.start()
        status, headers, _ = self.request("/api/login", {"username": USER, "password": PASSWORD})
        self.assertEqual(status, 429); self.assertEqual(headers["Retry-After"], "300")
        for change in ({"Host": "evil.test"}, {"Origin": "https://evil.test"}):
            self.assertEqual(self.request("/api/login", {"username": USER, "password": PASSWORD}, change)[0], 403)

    def test_remembered_session_restart_and_logout(self):
        auth = self.login(30); port = self.server.server_port
        self.stop(); self.start(port)
        self.assertEqual(self.request("/api/session", headers=auth)[0], 200)
        self.assertEqual(self.request("/api/logout", {}, {**auth, "X-CSRF-Token": "bad"})[0], 403)
        self.assertEqual(self.request("/api/logout", {}, auth)[0], 200)
        self.assertEqual(self.request("/api/session", headers=auth)[0], 401)

    def test_password_rotation_fences_existing_sessions(self):
        auth = self.login(30); port = self.server.server_port
        configure(self.path, USER, "changed-fixture-password", replace=True)
        self.assertEqual(self.request("/api/session", headers=auth)[0], 503)
        self.stop(); self.start(port)
        self.assertEqual(self.request("/api/session", headers=auth)[0], 401)

    def test_workspace_csrf_and_ledger_unchanged_by_login(self):
        before = self.ledger.snapshot()["meta"]
        auth = self.login()
        status, _, raw = self.request("/api/workspaces/fixture/session", headers=auth)
        self.assertEqual(status, 200)
        self.assertNotEqual(json.loads(raw)["csrf"], auth["X-CSRF-Token"])
        self.assertEqual(self.request("/api/workspaces/fixture/commands", {}, auth)[0], 403)
        self.assertEqual(self.ledger.snapshot()["meta"], before)

    def test_missing_account_does_not_reenable_token_mode(self):
        self.path.unlink()
        self.assertEqual(self.request("/api/login", {"username": USER, "password": PASSWORD})[0], 503)
        self.assertEqual(self.request("/api/login", {"token": "anything"})[0], 403)
        with self.assertRaises(Refusal):
            Dashboard(self.ledger, 0, account_file=self.path)
