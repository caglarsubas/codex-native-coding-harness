"""Disposable certificate/dashboard tests; native/OS boundaries are synthetic.

The existing real SQLite/Git certificate fixture validates historical continuity.
Review/HTTP fixtures use real private SQLite backups and Unix/TCP sockets, but
never start Codex, sign in, read credentials, call a provider or touch live state.
"""
import collections
import contextlib
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import sqlite3
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from orchestrator import post_reboot_dashboard as api, maintenance_dashboard as web
from orchestrator import post_reboot_host_repair as repair
from orchestrator.core import Refusal, canonical, digest
from orchestrator.host_lifecycle import write_record
from orchestrator.native_read_client import inspect_endpoint
import test_post_reboot_maintenance as certificate_fixtures


class CertificateConsumerTest(unittest.TestCase):
    def test_real_completed_certificate_keeps_all_original_rows_and_default_write_fence(self):
        f = certificate_fixtures.RebootMaintenanceTest('runTest'); f.setUp(); self.addCleanup(f.doCleanups)
        f.apply(); path = f.f.r.f.root / 'certificate.json'; write_record(path, f.q)
        q, _, ledger, pins = repair.certificate(path)
        self.assertEqual(q, f.q); self.assertEqual(len(pins), 5)
        self.assertFalse(hasattr(ledger, 'tx'))
        f.conserved()


def observed():
    return {'observation': {'activity': 'notLoaded', 'latestTurnId': 'fixture-completed-turn', 'policy': None},
            'authentication': {'accountPresent': True, 'ready': True, 'responseHash': 'a' * 64},
            'observedAt': time.time(), 'modelAccessVerified': False, 'terminalSafety': 'unknown'}


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.root.chmod(0o700)
        self.platform = self.root / 'platform'; self.platform.mkdir(mode=0o700)
        self.ledger = self.root / 'ledger'; self.ledger.mkdir(mode=0o700)
        self.dbs = {}
        for key, directory in [('platform', self.platform), ('workspace:v1', self.ledger)]:
            path = directory / 'ledger.sqlite3'
            with contextlib.closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE preserved(value TEXT)'); db.execute("INSERT INTO preserved VALUES ('original usage and claims')")
            path.chmod(0o600); self.dbs[key] = {'path': str(path), **repair.maintenance.partial.database_proof(path)}
        self.file = self.root / 'original.json'; write_record(self.file, {'oldClaim': 'permanent', 'usage': 15823})
        self.binary = self.root / 'codex'; self.binary.write_bytes(b'disposable binary never executed'); self.binary.chmod(0o700)
        self.ipc = self.root / 'ipc'; self.ipc.mkdir(mode=0o700)
        self.sock = socket.socket(socket.AF_UNIX); self.addCleanup(self.sock.close)
        self.socket_path = self.ipc / 'host.sock'; self.sock.bind(str(self.socket_path)); self.socket_path.chmod(0o600)
        self.endpoint = inspect_endpoint(str(self.binary), str(self.socket_path), 'f' * 64)
        brain, project, catalog = [str(uuid.uuid4()) for _ in range(3)]
        self.record = {'workspaceId': 'v1', 'cwd': str(self.root), 'projectId': project, 'catalogProjectId': catalog,
                       'nativePolicy': {'sandbox': 'workspace-write', 'approvalPolicy': 'on-request', 'codeMode': False}}
        self.c = {'workspaceId': 'v1', 'brainId': brain, 'checkout': str(self.root / 'checkout'),
            'nativeHome': str(self.root / 'home'), 'startupHash': 'a' * 64, 'bootSessionUuid': 'fixture-boot',
            'repairPin': api.pin(self.file), 'certificatePin': api.pin(self.file), 'certificatePins': {'original': api.pin(self.file)},
            'launchedSource': {'root': str(self.root / 'source'), 'sourceHash': api.PR193, 'epochHash': 'b' * 64},
            'launchPins': {'intent.json': api.pin(self.file)}, 'oldBindingFile': str(self.file), 'oldBindingPin': api.pin(self.file),
            'oldBindingHash': digest({'unchanged': True}), 'databases': copy.deepcopy(self.dbs),
            'historicalPins': {str(self.file): api.pin(self.file)}, 'originalReadinessId': str(uuid.uuid4()),
            'historicalObservedAt': 1, 'latestTurnId': 'fixture-completed-turn', 'pid': os.getpid(), 'processIdentity': 'fixture-birth',
            'endpoint': self.endpoint, 'record': self.record,
            'originalUsage': {'observedLastTurnTokens': 15823, 'chargedReservationFloor': 15823,
                'carriedPhaseCeiling': 5736373, 'futurePhaseCeiling': 5720550,
                'coverage': 'per_turn_not_lifetime', 'gaps': ['lifetime_coverage_not_asserted']}}
        # Protected roots must not encompass the disjoint outputs. The executable
        # package is in a separate private directory, like the actual profile.
        self.pkg = self.root / 'package' / 'bin'; self.pkg.mkdir(mode=0o700, parents=True)
        self.binary.rename(self.pkg / 'codex'); self.binary = self.pkg / 'codex'
        self.endpoint = inspect_endpoint(str(self.binary), str(self.socket_path), 'f' * 64); self.c['endpoint'] = self.endpoint
        self.repair_dir = self.root / 'repair'; self.repair_dir.mkdir(mode=0o700)
        self.repair_file = self.repair_dir / 'repair.json'; write_record(self.repair_file, {'synthetic': 'reviewed launch boundary'})
        self.c['repairPin'] = api.pin(self.repair_file)
        self.before = {p['path']: Path(p['path']).read_bytes() for p in self.dbs.values()}
        self.old = self.file.read_bytes()
        def foundation(*_):
            c = copy.deepcopy(self.c)
            c['databases'] = {k: {'path': v['path'], **repair.maintenance.partial.database_proof(v['path'])} for k, v in self.dbs.items()}
            c['oldBindingPin'] = api.pin(self.file)
            return c, {}, SimpleNamespace(root=self.platform), SimpleNamespace(root=self.ledger)
        foundation_patch = patch.object(api, 'foundation', side_effect=foundation)
        self.foundation = foundation_patch.start(); self.addCleanup(foundation_patch.stop)
        collector_patch = patch.object(api, 'collect', side_effect=lambda _: observed())
        self.collector = collector_patch.start(); self.addCleanup(collector_patch.stop)
        quiet_patch = patch.object(api, 'quiet')
        self.quiet = quiet_patch.start(); self.addCleanup(quiet_patch.stop)
        self.catalog_file = self.root / 'catalog.json'
        write_record(self.catalog_file, {'source': 'codex_app.list_projects', 'observedAt': time.time(), 'completeResult': {
            'schemaVersion': 2, 'projects': [{'projectId': catalog, 'path': self.c['checkout'], 'hostId': 'local',
                'projectKind': 'local', 'isGitRepository': True}]}})
        self.evidence = self.root / 'evidence'; self.view = self.root / 'view'; self.backups = self.root / 'backups'

    def prepare(self):
        api.inspect(self.repair_file, self.c['launchedSource']['root'], self.catalog_file, self.evidence)
        self.proposed = api.prepare(self.repair_file, self.c['launchedSource']['root'], self.evidence, self.view, 18810)
        self.q = self.proposed['request']; return self.proposed

    def backup(self):
        api.backup(self.q, self.backups, writers_stopped=True)

    def conserved(self):
        self.assertEqual(self.old, self.file.read_bytes())
        for path, raw in self.before.items(): self.assertEqual(Path(path).read_bytes(), raw)

    def test_prepare_is_scope_bound_and_file_only_with_unchanged_brain_record(self):
        a = self.prepare(); self.collector.assert_called_once()
        b = api.prepare(self.repair_file, self.c['launchedSource']['root'], self.evidence, self.view, 18810)
        self.assertEqual(a, b); self.assertEqual(a['validUntil'], 'scope_changes')
        self.assertEqual(api.read(self.evidence / 'binding.json')['brains'], {self.c['brainId']: self.record})
        self.assertFalse(Path(self.q['journal']).exists()); self.assertFalse(self.view.exists()); self.conserved()

    def test_backup_complete_private_and_verified_without_state_mutation(self):
        self.prepare(); self.backup(); api.verify_backup(self.q, self.backups)
        self.assertEqual(len(list(self.backups.glob('database-*.sqlite3'))), 2)
        for p in self.backups.iterdir(): self.assertEqual(p.stat().st_mode & 0o077, 0)
        self.conserved()

    def test_missing_duplicate_changed_or_unlisted_backup_inputs_refuse(self):
        self.prepare(); self.backup()
        manifest = self.backups / 'manifest.json'; original = manifest.read_bytes(); m = api.read(manifest)
        name = next(n for n in m['files'] if n.startswith('input-'))
        (self.backups / name).unlink()
        del m['files'][name]; manifest.write_text(canonical(m))
        with self.assertRaises(Refusal): api.verify_backup(self.q, self.backups)
        self.conserved(); self.assertNotEqual(manifest.read_bytes(), original)

    def test_corrupt_database_backup_refuses(self):
        self.prepare(); self.backup(); (self.backups / 'database-0.sqlite3').write_bytes(b'corrupt')
        with self.assertRaises((Refusal, sqlite3.Error)): api.verify_backup(self.q, self.backups)

    def test_no_backup_or_start_without_explicit_stopped_writers_and_exact_review(self):
        self.prepare()
        with self.assertRaises(Refusal): api.backup(self.q, self.backups)
        with self.assertRaises(Refusal): api.serve(self.q, 'approved', self.backups, self.catalog_file, writers_stopped=True)
        with self.assertRaises(Refusal): api.serve(self.q, digest(self.q), self.backups, self.catalog_file)
        self.assertFalse(Path(self.q['journal']).exists()); self.conserved()

    def test_scope_source_frontend_or_database_change_invalidates_review(self):
        self.prepare()
        with patch.object(api, 'source_hash', return_value='f' * 64):
            with self.assertRaises(Refusal): api.validate(self.q)
        with contextlib.closing(sqlite3.connect(self.dbs['platform']['path'])) as db, db:
            db.execute("INSERT INTO preserved VALUES ('new writer')")
        with self.assertRaises(Refusal): api.validate(self.q)
        self.assertFalse(Path(self.q['journal']).exists())

    def test_pending_claim_blocks_new_source_port_directory_and_repeated_start(self):
        self.prepare(); root = Path(self.q['journal']); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        for port in (18810, 18811):
            with self.assertRaises(Refusal): api.prepare(self.repair_file, self.c['launchedSource']['root'], self.evidence, self.root / 'other', port)
        self.collector.assert_called_once(); self.conserved()

    def test_disjoint_outputs_cannot_enter_native_home_checkout_platform_or_evidence(self):
        self.prepare()
        for path in (self.platform / 'view', Path(self.c['nativeHome']), Path(self.c['checkout'])):
            with self.assertRaises(Refusal): api.disjoint(path, self.c)
        with self.assertRaises(Refusal): api.prepare(self.repair_file, self.c['launchedSource']['root'], self.evidence, self.evidence / 'view', 18810)

    def test_foreign_duplicate_or_stale_catalog_refuses(self):
        self.prepare(); value = api.read(self.catalog_file)
        for mutate in (lambda v: v['completeResult']['projects'].append(copy.deepcopy(v['completeResult']['projects'][0])),
                       lambda v: v['completeResult']['projects'][0].update(projectId=str(uuid.uuid4())),
                       lambda v: v.update(observedAt=time.time() - 121)):
            bad = copy.deepcopy(value); mutate(bad); self.catalog_file.write_text(canonical(bad))
            with self.assertRaises(Refusal): api.catalog(self.catalog_file, self.c, fresh=True)
        self.conserved()

    def test_post_claim_scope_loss_has_no_server_or_second_attempt(self):
        self.prepare(); self.backup(); before = self.foundation.side_effect; calls = 0
        def drift(*args):
            nonlocal calls
            calls += 1
            if calls >= 2: raise Refusal('Synthetic post-claim drift')
            return before(*args)
        self.foundation.side_effect = drift
        fixed = SimpleNamespace(returncode=1, stdout=b'')
        with patch.object(repair.restart, 'fixed', return_value=fixed), patch.object(web, 'RecoveryDashboard') as server:
            with self.assertRaises(Refusal): api.serve(self.q, digest(self.q), self.backups, self.catalog_file, writers_stopped=True)
        server.assert_not_called(); self.assertTrue((Path(self.q['journal']) / 'serve.claim.json').exists())
        self.foundation.side_effect = before
        with self.assertRaises(Refusal): api.validate(self.q)
        self.conserved()

    def test_one_foreground_server_has_no_notifier_and_preserves_every_database(self):
        self.prepare(); self.backup()
        server = SimpleNamespace(server_port=18810, serve_forever=lambda **_: None, server_close=lambda: None)
        with patch.object(repair.restart, 'fixed', return_value=SimpleNamespace(returncode=1, stdout=b'')), \
             patch.object(repair.restart, 'process_identity', return_value='fixture-process-birth'), \
             patch.object(web, 'RecoveryDashboard', return_value=server) as create:
            api.serve(self.q, digest(self.q), self.backups, self.catalog_file, writers_stopped=True)
        self.assertEqual(create.call_count, 1); self.assertTrue((Path(self.q['journal']) / 'serving.json').exists())
        with self.assertRaises(Refusal): api.validate(self.q)
        self.conserved()

    def test_occupied_port_never_signals_or_consumes_start(self):
        self.prepare(); self.backup()
        with patch.object(repair.restart, 'fixed', return_value=SimpleNamespace(returncode=0, stdout=b'999\n')):
            with self.assertRaises(Refusal): api.serve(self.q, digest(self.q), self.backups, self.catalog_file, writers_stopped=True)
        self.assertFalse(Path(self.q['journal']).exists()); self.conserved()

    def test_startup_account_drift_consumes_claim_without_serving_or_retry(self):
        self.prepare(); self.backup()
        changed = observed(); changed['authentication']['responseHash'] = 'b' * 64
        self.collector.side_effect = lambda _: changed
        with patch.object(repair.restart, 'fixed', return_value=SimpleNamespace(returncode=1, stdout=b'')), \
             patch.object(web, 'RecoveryDashboard') as create:
            with self.assertRaises(Refusal): api.serve(self.q, digest(self.q), self.backups, self.catalog_file, writers_stopped=True)
        create.assert_not_called(); self.assertTrue((Path(self.q['journal']) / 'serve.claim.json').exists())
        with self.assertRaises(Refusal): api.validate(self.q)
        self.conserved()

    def test_polls_are_cached_and_closed_projection_keeps_unknowns(self):
        self.prepare(); count = self.collector.call_count
        a = web.projection(self.q, observed()); b = web.projection(self.q, observed())
        self.assertEqual(self.collector.call_count, count)
        self.assertFalse(a['connection']['nativeMetadataFreshlyCollected']); self.assertFalse(a['connection']['policyVerified'])
        self.assertEqual(a['usage'], b['usage']); self.assertEqual(a['boundary']['currentTerminalSafety'], 'unknown')
        self.assertNotIn('endpoint', a); self.assertNotIn('context', a); self.assertNotIn('commands', a); self.conserved()

    def test_changed_retained_evidence_fails_closed_without_recollection(self):
        self.prepare(); count = self.collector.call_count
        (self.evidence / 'result.json').write_bytes(b'{}')
        with self.assertRaises(Refusal): web.projection(self.q, observed())
        self.assertEqual(self.collector.call_count, count)

    def test_saved_observation_becomes_stale_without_renewing_or_granting_policy(self):
        self.prepare(); old = observed(); old['observedAt'] = time.time() - 301
        a = web.projection(self.q, old)
        self.assertTrue(a['connection']['observationStale']); self.assertFalse(a['connection']['policyVerified'])
        self.assertEqual(a['connection']['observedAt'], old['observedAt']); self.collector.assert_called_once()


class NativeReadClosureTest(unittest.TestCase):
    def test_exact_closed_proxy_rejects_every_load_turn_subscription_and_mutation(self):
        proxy = repair.restart.RestartReadProxy({}, 'brain', 'project')
        for method in ('thread/resume', 'thread/start', 'thread/subscribe', 'turn/start', 'turn/interrupt', 'account/login/start', 'account/logout'):
            with self.subTest(method=method), self.assertRaises(Refusal): proxy._rpc(method, {})
        with self.assertRaises(Refusal): proxy._rpc('account/read', {'refreshToken': True})
        with self.assertRaises(Refusal): proxy._rpc('thread/read', {'threadId': 'foreign', 'includeTurns': False})

    def test_collect_retains_unloaded_policy_and_only_exact_metadata(self):
        c = {'brainId': 'brain', 'checkout': '/fixture', 'latestTurnId': 'turn', 'endpoint': {}, 'record': {'projectId': 'project'}}
        methods = []
        class Proxy:
            def __init__(self, *args): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def _rpc(self, method, params):
                methods.append((method, params))
                values = {'project/read': {'project': {'id': 'project', 'roots': [{'path': '/fixture'}]}},
                    'thread/read': {'thread': {'id': 'brain', 'projectId': 'project', 'cwd': '/fixture', 'status': {'type': 'notLoaded'}}},
                    'thread/turns/list': {'data': [{'id': 'turn', 'status': 'completed'}]},
                    'thread/effectivePolicy/read': {'version': 1, 'threadId': 'brain', 'policy': None},
                    'mcpServerStatus/list': {'data': [], 'nextCursor': None},
                    'account/read': {'account': {'type': 'chatgpt', 'email': 'DO_NOT_RETAIN'}, 'requiresOpenaiAuth': True}}
                return copy.deepcopy(values[method])
        with patch.object(repair.restart, 'RestartReadProxy', Proxy): value = api.collect(c)
        self.assertIsNone(value['observation']['policy']); self.assertNotIn('DO_NOT_RETAIN', canonical(value))
        self.assertEqual(collections.Counter(m for m, _ in methods), {m: 2 for m in ('project/read', 'thread/read', 'thread/turns/list', 'thread/effectivePolicy/read', 'mcpServerStatus/list', 'account/read')})
        self.assertTrue(all(p == {'refreshToken': False} for m, p in methods if m == 'account/read'))


class HttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.root.chmod(0o700)
        self.q = {'port': 0, 'context': {'workspaceId': 'v1'}, 'sourceHash': api.source_hash()}
        self.server = web.RecoveryDashboard(self.q, observed(), self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)
        projector_patch = patch.object(web, 'projection', return_value={'mode': 'certificate_read_only', 'boundary': api.BOUNDARY})
        self.projector = projector_patch.start(); self.addCleanup(projector_patch.stop)
        self.cookie = None

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)

    def request(self, method, path, body=None, origin=True, cookie=True, host=None):
        h = {'Host': host or self.server.origin.split('//')[1]}
        if origin: h['Origin'] = self.server.origin
        if self.cookie and cookie: h['Cookie'] = self.cookie
        raw = canonical(body) if body is not None else None
        if raw is not None: h['Content-Type'] = 'application/json'
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            c.request(method, path, raw, h); r = c.getresponse(); return r.status, dict(r.getheaders()), r.read()
        finally: c.close()

    def login(self):
        code, headers, _ = self.request('POST', '/api/login', {'token': self.server.bootstrap})
        self.assertEqual(code, 200); self.cookie = headers['Set-Cookie'].split(';')[0]

    def test_no_state_without_browser_auth_or_with_wrong_host(self):
        self.assertEqual(self.request('GET', '/api/state')[0], 401)
        self.assertEqual(self.request('GET', '/api/state', host='evil.test')[0], 403)
        self.projector.assert_not_called()

    def test_pairing_is_same_origin_private_and_separate_from_operational_state(self):
        self.assertEqual(self.request('POST', '/api/login', {'token': self.server.bootstrap}, origin=False)[0], 403)
        self.login(); code, _, raw = self.request('GET', '/api/state')
        self.assertEqual(code, 200); self.assertEqual(json.loads(raw)['mode'], 'certificate_read_only')
        self.assertTrue((self.root / 'browser-auth').is_dir())
        self.assertEqual(api.read(self.root / 'dashboard-session.json')['mode'], 'certificate_read_only')

    def test_every_operational_write_and_method_is_closed(self):
        self.login()
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'):
            for path in ('/api/workspaces/v1/assistant/confirm', '/api/workspaces/v1/standard/play', '/api/native-permission/confirm', '/api/state'):
                with self.subTest(method=method, path=path): self.assertEqual(self.request(method, path, {'confirmed': True})[0], 405)
        self.projector.assert_not_called()

    def test_foreign_workspace_alias_query_and_traversal_cannot_read(self):
        self.login()
        for path in ('/api/workspaces/foreign/state', '/api/state?refresh=true', '/api/native-policy', '/../../etc/passwd'):
            with self.subTest(path=path): self.assertIn(self.request('GET', path)[0], (400, 404))
        self.projector.assert_not_called()

    def test_scope_loss_returns_unavailable_not_last_good_state(self):
        self.login(); self.projector.side_effect = Refusal('SENSITIVE private diagnostic')
        code, headers, raw = self.request('GET', '/api/state')
        self.assertEqual(code, 503); self.assertNotIn(b'SENSITIVE', raw)
        self.assertEqual(headers['Cache-Control'], 'no-store'); self.assertEqual(headers['X-Frame-Options'], 'DENY')

    def test_assets_are_closed_and_changed_source_is_never_served(self):
        self.assertEqual(self.request('GET', '/')[0], 200)
        with patch.object(api, 'source_hash', return_value='f' * 64):
            code, _, body = self.request('GET', '/maintenance.js')
        self.assertEqual(code, 503); self.assertNotIn(b'function', body)
        with self.assertRaises(Refusal): api.asset('../auth.json')


if __name__ == '__main__': unittest.main()
