import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from orchestrator.browser_auth import BrowserAuth
from orchestrator.core import Refusal, Ledger
from orchestrator.server import Dashboard
import test_server
import test_workspace_server


class BrowserAuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = 1000000.25
        self.auth = self.open()

    def tearDown(self):
        self.tmp.cleanup()

    def open(self, port=8768):
        return BrowserAuth(self.root, f"http://127.0.0.1:{port}", clock=lambda: self.now)

    def test_opt_in_survives_restart_but_temporary_session_does_not(self):
        temporary, _ = self.auth.issue()
        remembered, row = self.auth.issue(30)
        restarted = self.open()
        self.assertIsNone(restarted.session(temporary))
        self.assertEqual(restarted.session(remembered), row)
        self.assertEqual(restarted.cookie, self.auth.cookie)
        self.now += 9 * 3600
        self.assertIsNone(self.auth.session(temporary))
        self.assertEqual(restarted.session(remembered), row)
        self.now = row["expires"]
        self.assertIsNone(restarted.session(remembered))

    def test_only_digest_is_retained_in_private_files(self):
        sid, _ = self.auth.issue(7)
        path = self.auth.root / self.auth.filename
        self.assertNotIn(sid, path.read_text())
        self.assertIn(self.auth.key(sid), path.read_text())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.auth.root.stat().st_mode & 0o777, 0o700)

    def test_port_and_installation_namespaces_are_distinct(self):
        sid, _ = self.auth.issue(90)
        pilot = self.open(8791)
        self.assertNotEqual(self.auth.cookie, pilot.cookie)
        self.assertIsNone(pilot.session(sid))
        (self.root / 'other').mkdir()
        other_root = BrowserAuth(self.root / 'other', 'http://127.0.0.1:8768')
        self.assertNotEqual(self.auth.cookie, other_root.cookie)
        self.assertIsNone(other_root.session(sid))

    def test_renew_rotates_cookie_csrf_and_invalidates_old_session(self):
        old, old_row = self.auth.issue()
        sid, row = self.auth.issue(30, old)
        self.assertNotEqual(sid, old)
        self.assertNotEqual(row['csrf'], old_row['csrf'])
        self.assertIsNone(self.auth.session(old))
        self.assertEqual(self.open().session(sid), row)
        temporary, _ = self.auth.issue(0, sid)
        self.assertIsNone(self.open().session(sid))
        self.assertIsNone(self.open().session(temporary))

    def test_logout_and_revoke_all_are_durable(self):
        sid, _ = self.auth.issue(7)
        other, _ = self.auth.issue(30)
        temporary, _ = self.auth.issue()
        self.auth.revoke(sid)
        self.assertIsNone(self.open().session(sid))
        self.assertIsNotNone(self.open().session(other))
        self.auth.revoke(other, all_browsers=True)
        self.assertIsNone(self.auth.session(temporary))
        self.assertIsNone(self.open().session(other))
        with self.assertRaises(Refusal):
            self.auth.issue(30, other)

    def test_corruption_missing_file_or_unsafe_permissions_fail_closed(self):
        sid, _ = self.auth.issue(30)
        path = self.auth.root / self.auth.filename
        original = path.read_text()
        for raw in ('bad json', '{}', '{"version":1,"sessions":{"bad":{}}}'):
            path.write_text(raw)
            with self.assertRaises(Refusal): self.auth.session(sid)
            with self.assertRaises(Refusal): self.open()
        path.write_text(original)
        path.chmod(0o644)
        with self.assertRaises(Refusal): self.auth.session(sid)
        path.chmod(0o600)
        path.unlink()
        with self.assertRaises(Refusal): self.auth.session(sid)

    def test_symlink_and_hardlink_are_refused_without_touching_target(self):
        sid, _ = self.auth.issue(30)
        path = self.auth.root / self.auth.filename
        target = self.root / 'target'
        path.rename(target)
        path.symlink_to(target)
        original = target.read_bytes()
        with self.assertRaises(Refusal): self.auth.session(sid)
        with self.assertRaises(Refusal): self.auth.issue(7)
        self.assertEqual(target.read_bytes(), original)
        path.unlink()
        os.link(target, path)
        with self.assertRaises(Refusal): self.auth.revoke(sid)

    def test_write_failure_does_not_grant_or_revoke_in_memory(self):
        sid, row = self.auth.issue(30)
        with patch.object(self.auth, '_write', side_effect=OSError('disk full')):
            with self.assertRaises(Refusal): self.auth.issue(7, sid)
            with self.assertRaises(Refusal): self.auth.revoke(sid)
        self.assertEqual(self.auth.session(sid), row)

    def test_duration_limits_and_session_capacity(self):
        for value in (True, -1, 1, 365, '30', None, 30.0):
            with self.assertRaises(Refusal): self.auth.issue(value)
        for _ in range(32): self.auth.issue(7)
        with self.assertRaises(Refusal): self.auth.issue(7)
        self.now += 7 * 86400
        self.assertIsNotNone(self.auth.issue(7))


class BrowserAuthServerTest(unittest.TestCase):
    request = test_server.ServerTest.request
    login = test_server.ServerTest.login

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root / 'state')
        self.ledger.initialize({'schemaVersion': 1, 'brainId': 'fixture-brain', 'repositories': []})
        self.start()

    def start(self, port=0):
        self.server = Dashboard(self.ledger, port, self.root / '.env', runtime_root=self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def tearDown(self):
        self.stop(); self.tmp.cleanup()

    def test_real_http_cookie_restart_and_logout(self):
        status, headers, raw = self.request('/api/login', {'token': self.server.bootstrap, 'rememberDays': 30})
        self.assertEqual(status, 200)
        auth = {'Cookie': headers['Set-Cookie'].split(';')[0], 'X-CSRF-Token': json.loads(raw)['csrf']}
        for flag in ('HttpOnly', 'SameSite=Strict', 'Path=/'):
            self.assertIn(flag, headers['Set-Cookie'])
        before = self.ledger.snapshot()['meta']
        bootstrap = self.server.bootstrap
        port = self.server.server_port
        self.stop(); self.start(port)
        self.assertNotEqual(bootstrap, self.server.bootstrap)
        self.assertEqual(self.request('/api/session', headers=auth)[0], 200)
        self.assertEqual(self.request('/api/state', headers=auth)[0], 200)
        status, headers, _ = self.request('/api/logout', {}, auth)
        self.assertEqual(status, 200)
        self.assertIn('Max-Age=0', headers['Set-Cookie'])
        self.assertEqual(self.request('/api/session', headers=auth)[0], 401)
        self.assertEqual(before, self.ledger.snapshot()['meta'])

    def test_security_guards_and_explicit_revoke_confirmation(self):
        auth = self.login()
        path = '/api/session/remember'
        body = {'rememberDays': 30}
        self.assertEqual(self.request(path, body)[0], 403)
        for overrides in ({'Origin': 'https://evil.example'}, {'Host': 'evil.example'}, {'X-CSRF-Token': 'wrong'}):
            self.assertEqual(self.request(path, body, {**auth, **overrides})[0], 403)
        self.assertEqual(self.request(path, body, {**auth, 'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('/api/sessions/revoke', {}, auth)[0], 409)
        self.assertEqual(self.request('/api/sessions/revoke', {'confirmed': 1}, auth)[0], 409)
        other = self.login()
        status, headers, raw = self.request(path, body, auth)
        self.assertEqual(status, 200)
        remembered = {'Cookie': headers['Set-Cookie'].split(';')[0], 'X-CSRF-Token': json.loads(raw)['csrf']}
        self.assertEqual(self.request('/api/session', headers=auth)[0], 401)
        self.assertEqual(self.request('/api/sessions/revoke', {'confirmed': True}, remembered)[0], 200)
        for item in (remembered, other):
            self.assertEqual(self.request('/api/session', headers=item)[0], 401)

    def test_private_link_reopen_preserves_remembered_choice(self):
        _, headers, raw = self.request('/api/login', {'token': self.server.bootstrap, 'rememberDays': 7})
        auth = {'Cookie': headers['Set-Cookie'].split(';')[0]}
        _, _, raw = self.request('/api/login', {'token': self.server.bootstrap}, auth)
        self.assertEqual(json.loads(raw)['rememberDays'], 7)
        status, _, raw = self.request('/auth.js')
        self.assertEqual(status, 200)
        self.assertNotIn(self.server.bootstrap.encode(), raw)


class BrowserAuthWorkspaceTest(unittest.TestCase):
    setUp = test_workspace_server.WorkspaceServerTest.setUp
    tearDown = test_workspace_server.WorkspaceServerTest.tearDown
    request = test_server.ServerTest.request
    login = test_server.ServerTest.login
    auth = test_workspace_server.WorkspaceServerTest.auth

    def test_global_auth_controls_do_not_accept_workspace_csrf_or_change_ledgers(self):
        before = {key: ledger.snapshot()['meta'] for key, ledger in self.ledgers.items()}
        auth = self.login()
        scoped = self.auth('a', auth)
        self.assertEqual(self.request('/api/session/remember', {'rememberDays': 30}, scoped)[0], 403)
        self.assertEqual(self.request('/api/workspaces/a/session/remember', {'rememberDays': 30}, scoped)[0], 404)
        status, headers, raw = self.request('/api/session/remember', {'rememberDays': 30}, auth)
        self.assertEqual(status, 200)
        new_auth = {'Cookie': headers['Set-Cookie'].split(';')[0], 'X-CSRF-Token': json.loads(raw)['csrf']}
        for wid in self.ledgers:
            self.assertEqual(self.request('/api/workspaces/'+wid+'/state', headers=new_auth)[0], 200)
        self.assertEqual(before, {key: ledger.snapshot()['meta'] for key, ledger in self.ledgers.items()})
