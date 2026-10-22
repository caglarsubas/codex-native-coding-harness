"""Disposable SQLite/Unix/file lineage; native calls are explicitly synthetic."""
import contextlib
import copy
import os
from pathlib import Path
import queue
import sqlite3
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orchestrator import certificate_runtime_startup as api
from orchestrator.core import Refusal, digest
from orchestrator.host_lifecycle import write_record
from orchestrator.native_read_client import NativeReadFailure
import test_certificate_worker_readiness as fixtures


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.CertificateWorkerTest('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.f.collect(); self.f.calls.clear(); self.f.exporter.reset_mock()
        self.source = api.worker.startup.owned.preplay.SOURCE
        self.backups = self.f.f.root / 'startup-backup'
        self.q = None; self.callback = lambda *_: None; self.mode = 'ok'
        self.holder = patch.object(api, 'hold', side_effect=lambda *a: self.callback('hold') or 'window_ended')
        self.hold_mock = self.holder.start(); self.addCleanup(self.holder.stop)
        enter = patch.object(api.RuntimeProxy, '__enter__', lambda p: p)
        enter.start(); self.addCleanup(enter.stop)
        rpc = self.f.rpc
        def call(method, params):
            self.callback(method)
            if method == 'thread/resume':
                self.f.calls.append((method, copy.deepcopy(params)))
                if self.mode == 'lost_ack': raise NativeReadFailure('proxy_closed', 'Synthetic lost load ack')
                self.f.loaded = True
                if self.mode == 'wrong_ack': return {'thread': {'id': 'foreign'}}
                return {'thread': {'id': self.f.brain}}
            return rpc(method, params)
        self.f.callback = lambda _: None
        # Replace only this fixture's already-installed base RPC mock callback.
        from orchestrator.native_read_client import ReadProxy
        rpc_patch = patch.object(ReadProxy, '_rpc', side_effect=call)
        rpc_patch.start(); self.addCleanup(rpc_patch.stop)
        self.original_files = {p: p.read_bytes() for p in self.f.output.iterdir()}

    def prepare(self):
        self.preview = api.prepare(self.f.f.repair_file, self.f.f.c['launchedSource']['root'],
            self.f.output, self.source, self.f.f.catalog_file)
        self.q = self.preview['request']; return self.preview

    def backup(self):
        api.backup(self.q, self.backups, writers_stopped=True)

    def start(self):
        self.prepare(); self.backup()
        return api.start(self.q, digest(self.q), self.backups, self.f.f.catalog_file, writers_stopped=True)

    def conserved(self):
        self.f.f.conserved()
        for p, raw in self.original_files.items(): self.assertEqual(p.read_bytes(), raw)
        methods = [m for m, _ in self.f.calls]
        self.assertLessEqual(methods.count('thread/resume'), 1)
        self.assertFalse(any(m in ('thread/start', 'thread/subscribe', 'turn/start', 'turn/interrupt') for m in methods))
        self.assertFalse(any('requestApproval' in m or 'respond' in m for m in methods))

    def test_file_only_scope_bound_review_does_not_connect_or_claim(self):
        a = self.prepare(); b = self.prepare()
        self.assertEqual(a, b); self.assertEqual(a['validUntil'], 'scope_changes')
        self.assertEqual(self.f.calls, []); self.f.exporter.assert_not_called()
        self.assertFalse(Path(self.q['journal']).exists()); self.assertFalse(a['executionReviewAvailable']); self.conserved()

    def test_historical_unloaded_observation_is_not_renewed_by_review(self):
        self.prepare(); report = api.dashboard.read(self.f.output / 'report.json')
        self.assertEqual(api.dashboard.read(self.f.output / 'report.json')['observedAt'], report['observedAt'])
        self.assertIsNone(report['native']['policy']); self.conserved()

    def test_complete_private_backups_keep_every_database_and_observation_unchanged(self):
        self.prepare(); self.backup(); api.verify_backup(self.q, self.backups)
        self.assertEqual(len(list(self.backups.glob('database-*'))), 2)
        self.assertTrue(all(p.stat().st_mode & 0o077 == 0 for p in self.backups.iterdir()))
        self.assertEqual(self.f.calls, []); self.conserved()

    def test_one_restricted_load_zero_turns_preserves_old_claims_and_usage(self):
        result = self.start()
        self.assertEqual(result['status'], 'window_ended'); self.assertTrue(result['savedLoadedObservation'])
        self.assertFalse(result['connectionCurrentlyVerified']); self.assertFalse(result['executionReviewAvailable'])
        self.assertEqual([m for m, _ in self.f.calls].count('thread/resume'), 1)
        self.assertEqual(api.dashboard.read(Path(self.q['journal']) / 'loaded.json')['native']['trackedTerminals'], [])
        self.assertEqual(result['boundary']['currentTerminalSafety'], 'unknown'); self.conserved()

    def test_wrong_hash_or_absent_writer_assertion_never_claims_or_loads(self):
        self.prepare(); self.backup()
        for kw in ({'confirmation': 'old approval', 'writers_stopped': True},
                   {'confirmation': digest(self.q), 'writers_stopped': False}):
            with self.assertRaises(Refusal): api.start(self.q, backup_root=self.backups, catalog_file=self.f.f.catalog_file, **kw)
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.f.calls, []); self.conserved()

    def test_corrupt_missing_or_extra_backup_refuses_before_claim(self):
        self.prepare(); self.backup(); (self.backups / 'database-0.sqlite3').write_bytes(b'corrupt')
        with self.assertRaises((Refusal, sqlite3.Error)):
            api.start(self.q, digest(self.q), self.backups, self.f.f.catalog_file, writers_stopped=True)
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.f.calls, []); self.conserved()

    def test_source_database_or_observation_drift_invalidates_review(self):
        self.prepare()
        with patch.object(api.dashboard, 'source_hash', return_value='f'*64):
            with self.assertRaises(Refusal): api.validate(self.q)
        with contextlib.closing(sqlite3.connect(self.f.f.dbs['platform']['path'])) as db, db:
            db.execute("INSERT INTO preserved VALUES ('changed competing writer')")
        with self.assertRaises(Refusal): api.validate(self.q)
        self.assertEqual(self.f.calls, [])

    def test_incomplete_or_edited_original_observation_never_invents_qualification(self):
        self.prepare(); (self.f.output / 'report.json').write_bytes(b'{}')
        with self.assertRaises((Refusal, KeyError)): api.validate(self.q)
        self.assertEqual(self.f.calls, []); self.assertFalse(Path(self.q['journal']).exists())

    def test_old_observation_never_executes_historical_python(self):
        self.prepare()
        with patch('subprocess.Popen', side_effect=AssertionError('No historical execution')):
            api.original_observation(self.f.output, self.source, self.q['context'])
        self.assertEqual(self.f.calls, []); self.conserved()

    def test_partial_canonical_claim_cannot_retry_across_new_source_or_host(self):
        self.prepare(); root = Path(self.q['journal']); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        with self.assertRaises(Refusal): self.prepare()
        self.f.f.c['pid'] += 1
        with self.assertRaises(Refusal): self.prepare()
        self.assertEqual(self.f.calls, []); self.conserved()

    def test_completed_start_is_not_replayable_or_renewable(self):
        self.start(); calls = list(self.f.calls)
        with self.assertRaises(Refusal): api.start(self.q, digest(self.q), self.backups, self.f.f.catalog_file, writers_stopped=True)
        with self.assertRaises(Refusal): self.prepare()
        self.assertEqual(calls, self.f.calls); self.conserved()

    def test_lost_load_ack_is_permanently_consumed_unknown_not_safe(self):
        self.mode = 'lost_ack'
        with self.assertRaises(NativeReadFailure): self.start()
        state = api.status(self.q); self.assertEqual(state['status'], 'incomplete_unknown')
        self.assertFalse(state['savedLoadedObservation'])
        self.assertTrue((Path(self.q['journal']) / 'load.claim.json').exists())
        with self.assertRaises(Refusal): self.prepare()
        self.conserved()

    def test_wrong_ack_is_unknown_without_second_load(self):
        self.mode = 'wrong_ack'
        with self.assertRaises(Refusal): self.start()
        self.assertFalse(api.status(self.q)['savedLoadedObservation']); self.conserved()

    def test_actual_loaded_policy_is_required_not_requested_settings(self):
        self.f.bad_policy = True
        with self.assertRaises(Refusal): self.start()
        self.assertFalse(api.status(self.q)['savedLoadedObservation']); self.conserved()

    def test_active_nonempty_and_unknown_trackers_refuse_after_one_load(self):
        self.callback = lambda m: self.f.terminals.append({'processId': 'owned', 'itemId': 'item'}) if m == 'thread/resume' else None
        with self.assertRaises(Refusal): self.start()
        self.assertFalse(api.status(self.q)['savedLoadedObservation']); self.conserved()

    def test_before_load_account_or_latest_turn_drift_refuses_without_reload(self):
        self.prepare(); self.backup(); self.f.account['email'] = 'other-account'
        with self.assertRaises(Refusal): api.start(self.q, digest(self.q), self.backups, self.f.f.catalog_file, writers_stopped=True)
        self.assertNotIn('thread/resume', [m for m, _ in self.f.calls]); self.conserved()

    def test_already_loaded_brain_does_not_acquire_another_load_or_subscription(self):
        self.prepare(); self.backup(); self.f.loaded = True
        with self.assertRaises(Refusal): api.start(self.q, digest(self.q), self.backups, self.f.f.catalog_file, writers_stopped=True)
        self.assertNotIn('thread/resume', [m for m, _ in self.f.calls]); self.conserved()

    def test_post_load_account_drift_fences_before_ready(self):
        self.callback = lambda m: self.f.account.update(email='changed') if m == 'thread/resume' else None
        with self.assertRaises(Refusal): self.start()
        self.assertFalse(api.status(self.q)['savedLoadedObservation']); self.conserved()

    def test_status_is_file_only_and_never_calls_proxy_or_renews_observed_time(self):
        self.start(); before = list(self.f.calls)
        with patch.object(api, 'RuntimeProxy', side_effect=AssertionError('No reconnect on status')):
            a = api.status(self.q); b = api.status(self.q)
        self.assertEqual(a, b); self.assertEqual(self.f.calls, before); self.conserved()

    def test_stop_is_local_only_and_never_native_cancel(self):
        def stop_at_hold(method):
            if method == 'hold': self.assertEqual(api.stop(self.q, digest(self.q))['status'], 'stop_requested')
        self.callback = stop_at_hold; self.start()
        self.assertTrue((Path(self.q['journal']) / 'stop.json').exists()); self.conserved()

    def test_stop_during_preload_checks_prevents_the_load(self):
        def stop_at_scene(method):
            if method == 'model/list': return
            root = Path(self.q['journal'])
            if root.exists() and not (root / 'stop.json').exists(): api.stop(self.q, digest(self.q))
        self.callback = stop_at_scene
        with self.assertRaises(Refusal): self.start()
        self.assertNotIn('thread/resume', [m for m, _ in self.f.calls]); self.conserved()

    def test_stale_catalog_refuses_before_claim(self):
        self.prepare(); self.backup(); p = self.f.f.catalog_file; value = api.dashboard.read(p)
        # A fresh input is distinct; original pinned catalog is not overwritten.
        fresh = self.f.f.root / 'stale-catalog.json'; value['observedAt'] = time.time() - 121; write_record(fresh, value)
        with self.assertRaises(Refusal): api.start(self.q, digest(self.q), self.backups, fresh, writers_stopped=True)
        self.assertFalse(Path(self.q['journal']).exists()); self.conserved()

    def test_runtime_proxy_refuses_arbitrary_parameters_and_mutation_before_io(self):
        self.prepare(); proxy = api.RuntimeProxy(self.q['context']['host'])
        for method, params in [('turn/start', {}), ('turn/interrupt', {}), ('thread/subscribe', {}),
                ('thread/resume', api.load_params({'brainId': proxy.brain, 'cwd': proxy.host['checkout']})),
                ('account/read', {'refreshToken': True}), ('thread/read', {'threadId': 'foreign', 'includeTurns': False})]:
            with self.assertRaises(Refusal): proxy._rpc(method, params)
        self.assertEqual(self.f.calls, []); self.conserved()

    def test_fixed_load_cannot_be_sent_twice_even_after_lost_ack(self):
        self.prepare(); proxy = api.RuntimeProxy(self.q['context']['host']); proxy.load_permitted = True
        self.mode = 'lost_ack'; params = api.load_params({'brainId': proxy.brain, 'cwd': proxy.host['checkout']})
        with self.assertRaises(NativeReadFailure): proxy._rpc('thread/resume', params)
        with self.assertRaises(Refusal): proxy._rpc('thread/resume', params)
        self.conserved()

    def test_permission_notification_or_foreign_work_is_never_answered_or_ignored(self):
        for row in ({'id': 42, 'method': 'item/commandExecution/requestApproval', 'params': {}},
                    {'method': 'turn/started', 'params': {}},
                    {'method': 'thread/status/changed', 'params': {'threadId': 'foreign', 'status': {'type': 'idle'}}}):
            events = queue.Queue(); events.put((row, 12))
            stream = SimpleNamespace(check=lambda: None, events=events, bytes=12, lock=threading.Lock())
            with self.assertRaises(Refusal): api.no_events(SimpleNamespace(_event_stream=stream, brain=self.f.brain))
        self.assertEqual(self.f.calls, []); self.conserved()

    def test_original_connection_loss_never_reconnects(self):
        self.hold_mock.side_effect = NativeReadFailure('proxy_closed', 'Synthetic original connection closed')
        with self.assertRaises(NativeReadFailure): self.start()
        self.assertEqual(api.status(self.q)['status'], 'incomplete_unknown'); self.conserved()

    def test_hold_has_fixed_window_and_no_metadata_model_or_native_keepalive_rpc(self):
        self.prepare(); root = Path(self.q['journal']); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        write_record(root / 'intent.json', {'kind': api.KIND, 'reviewHash': digest(self.q), 'request': self.q})
        self.holder.stop(); now = [1.0]; checks = []
        clock = SimpleNamespace(monotonic=lambda: now[0], sleep=lambda v: now.__setitem__(0, now[0] + v))
        with patch.object(api, 'time', clock), patch.object(api, 'validate', side_effect=lambda *a, **k: checks.append(now[0])):
            self.assertEqual(api.hold(SimpleNamespace(_event_stream=None), self.q, 12), 'window_ended')
        self.assertEqual(checks, [1, 6, 11]); self.assertEqual(self.f.calls, []); self.conserved()

    def test_backup_cannot_write_into_native_source_checkout_or_operational_roots(self):
        self.prepare()
        for path in (self.f.f.platform / 'bad', Path(self.q['context']['host']['nativeHome']) / 'bad',
                     self.source / 'bad', self.f.output / 'bad'):
            with self.assertRaises((Refusal, FileNotFoundError)): api.backup(self.q, path, writers_stopped=True)
        self.assertEqual(self.f.calls, []); self.conserved()


if __name__ == '__main__': unittest.main()
