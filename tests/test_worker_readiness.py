"""Actual disposable startup/SQLite/Git preservation; synthetic native metadata."""
import copy
import json
from pathlib import Path
import sqlite3
import time
import unittest
from unittest.mock import patch

from orchestrator import worker_readiness as worker, prestart_startup as startup, standard
from orchestrator.core import Refusal, canonical, digest
from orchestrator.native_read_client import ReadProxy, NativeReadFailure
from test_public_readiness import schemas
import test_prestart_startup as fixtures


class WorkerReadinessTest(unittest.TestCase):
    def setUp(self):
        name = 'test_admitted_same_project_preserves_both_claims_and_carried_usage' if 'admitted' in self._testMethodName else 'runTest'
        self.f = fixtures.StartupTest(name); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        if 'missing_usage' in self._testMethodName: self.f.usage = None
        if 'overrun' in self._testMethodName: self.f.usage = 12000
        self.f.apply()
        self.registry, self.ledger, self.r = self.f.registry, self.f.ledger, self.f.r
        self.q = self.f.q['request']; self.source = self.q['executionSource']['root']
        self.r.latest = {'id': self.r.turn, 'status': 'completed'}
        self.r.loaded = False
        self.calls = self.r.calls.copy()
        self.old_databases = startup.databases(self.registry)
        self.protected = {**worker.inventory(self.q['journal']), **worker.inventory(self.q['mailbox'])}
        self.destination = self.r.f.root / 'worker-evidence'
        export = patch.object(worker.public, 'export_schemas', return_value=worker.public.schema_contract(schemas()))
        self.export = export.start(); self.addCleanup(export.stop)
        validate = patch.object(worker, 'validate_endpoint'); validate.start(); self.addCleanup(validate.stop)
        proxy = patch.object(worker, 'WorkerReadProxy', self.r.Proxy); proxy.start(); self.addCleanup(proxy.stop)

    def collect(self):
        return worker.collect(self.registry, self.ledger, self.source, self.destination)

    def preserved(self):
        self.assertEqual(startup.databases(self.registry), self.old_databases)
        for p, original in self.protected.items(): self.assertEqual(startup.pin(p), original)
        self.assertFalse(standard.read(self.ledger)['available'])
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass
        reads = self.r.calls[len(self.calls):]
        self.assertFalse(any(m in ('thread/resume', 'thread/start', 'turn/start', 'thread/subscribe', 'turn/interrupt') for m, _ in reads))
        self.assertTrue(all(m != 'account/read' or p == {'refreshToken': False} for m, p in reads))

    def test_unloaded_observation_is_honest_not_new_readiness_or_load(self):
        result = self.collect()
        self.assertEqual(result['status'], 'blocked'); self.assertEqual(result['blockers'], ['brain_not_loaded'])
        report = json.loads((self.destination / 'report.json').read_text())
        self.assertIsNone(report['native']['policy']); self.assertIsNone(report['native']['trackedTerminals'])
        self.assertEqual(report['models'], [{'model': 'observed-fixture', 'efforts': ['high']}])
        self.assertEqual(report['context']['usage']['chargedReservationFloor'], 10000)
        self.preserved()

    def test_loaded_observation_can_complete_evidence_but_never_play(self):
        self.r.loaded = True; result = self.collect()
        self.assertEqual(result['status'], 'evidence_complete_not_activated'); self.assertEqual(result['blockers'], [])
        self.assertFalse(result['boundary']['playAuthorized']); self.assertTrue(result['normalWritesBlocked'])
        self.assertTrue(self.r.proxies[-1].closed); self.preserved()

    def test_admitted_real_lineage_and_both_claims_remain_unchanged(self):
        self.test_loaded_observation_can_complete_evidence_but_never_play()

    def test_status_is_file_only_and_never_refreshes_original_time(self):
        self.collect(); calls = self.r.calls.copy(); original = (self.destination / 'report.json').read_bytes()
        with patch.object(worker, 'WorkerReadProxy', side_effect=AssertionError('Native connection forbidden')), \
                patch.object(worker.public, 'export_schemas', side_effect=AssertionError('Export forbidden')):
            a = worker.status(self.registry, self.ledger, self.destination)
            b = worker.status(self.registry, self.ledger, self.destination)
        self.assertEqual(a, b); self.assertEqual(self.r.calls, calls)
        self.assertEqual((self.destination / 'report.json').read_bytes(), original); self.preserved()

    def test_stale_report_is_historical_not_renewed_or_authority(self):
        self.collect(); report = json.loads((self.destination / 'report.json').read_text())
        with patch.object(worker.time, 'time', return_value=report['observedAt'] + 121):
            result = worker.status(self.registry, self.ledger, self.destination)
        self.assertFalse(result['fresh']); self.assertEqual(result['observedAt'], report['observedAt'])
        self.preserved()

    def test_collection_never_overwrites_even_a_partial_artifact(self):
        self.destination.mkdir(mode=0o700); (self.destination / 'intent.json').write_text('{}')
        with self.assertRaises(Refusal): self.collect()
        self.export.assert_not_called(); self.preserved()

    def test_partial_report_never_counts_as_readiness(self):
        self.collect(); (self.destination / 'seal.json').unlink()
        with self.assertRaises(Refusal): worker.status(self.registry, self.ledger, self.destination)
        self.preserved()

    def test_changed_report_never_qualifies_cached_status(self):
        self.collect(); path = self.destination / 'report.json'
        row = json.loads(path.read_text()); row['status'] = 'ready'; path.write_text(canonical(row))
        with self.assertRaises(Refusal): worker.status(self.registry, self.ledger, self.destination)
        self.preserved()

    def test_changed_old_command_fails_before_native_connection(self):
        with sqlite3.connect(self.ledger.db) as db: db.execute("UPDATE commands SET data='{}'")
        with self.assertRaises((Refusal, KeyError)): self.collect()
        self.export.assert_not_called(); self.assertEqual(self.r.calls, self.calls)

    def test_stop_record_refuses_without_collecting(self):
        startup.exclusive(Path(self.q['journal']) / 'stop.json', {'reviewHash': digest(self.q), 'nativeCancelSent': False})
        with self.assertRaises(Refusal): self.collect()
        self.export.assert_not_called(); self.assertEqual(self.r.calls, self.calls)

    def test_missing_marker_or_anchor_never_rearms_any_old_control(self):
        for name in (startup.FENCE, startup.ANCHOR):
            path = self.ledger.root / name; raw = path.read_bytes(); path.unlink()
            with self.assertRaises(OSError): worker.context(self.registry, self.ledger, self.source)
            path.write_bytes(raw); path.chmod(0o600)
        self.assertEqual(self.r.calls, self.calls)

    def test_foreign_source_or_binding_is_never_substituted(self):
        with patch.object(startup.prior, 'source_proof', return_value={'root': self.source, 'sourceHash': 'f'*64, 'epochHash': 'e'*64}):
            with self.assertRaises(Refusal): self.collect()
        binding = Path(self.q['predecessor']['bindingFile']); original = binding.read_bytes()
        value = json.loads(original); value['brains'][self.r.f.brain]['projectId'] = 'foreign'
        binding.write_text(canonical(value))
        with self.assertRaises(Refusal): self.collect()
        self.export.assert_not_called()

    def test_explicit_historical_source_is_compared_not_executed(self):
        # Labelled source-version fixture: only the current implementation hash
        # differs from the original request. Exact original source proof remains.
        original = startup.owned.preplay.source_hash()
        with patch.object(startup.owned.preplay, 'source_hash', return_value='a'*64), \
                patch.object(worker, 'PR189_SOURCE', original), patch.object(startup.prior, 'PR187_SOURCE', original):
            c = worker.context(self.registry, self.ledger, self.source)
            self.assertEqual(c['startupSource']['sourceHash'], original)
            self.assertEqual(c['implementationHash'], 'a'*64)
        self.preserved()

    def test_unknown_historical_implementation_is_not_implicitly_trusted(self):
        with patch.object(startup.owned.preplay, 'source_hash', return_value='a'*64):
            with self.assertRaises(Refusal): worker.context(self.registry, self.ledger, self.source)
        self.preserved()

    def test_missing_usage_retains_floor_and_blocks_worker_readiness(self):
        self.r.loaded = True
        result = self.collect(); self.assertIn('preparation_usage_unknown', result['blockers'])
        self.assertEqual(json.loads((self.destination / 'report.json').read_text())['context']['usage']['chargedReservationFloor'], 10000)
        self.assertFalse(standard.read(self.ledger)['available'])
        self.preserved()

    def test_overrun_charge_is_not_reset(self):
        self.collect()
        self.assertEqual(json.loads((self.destination / 'report.json').read_text())['context']['usage']['chargedReservationFloor'], 12000)
        self.preserved()

    def test_bad_usage_floor_bool_or_regression_is_refused(self):
        path = Path(self.q['journal']) / 'usage.json'; u = startup.mailbox.read(path)
        for change in ({'chargedReservationFloor': 0}, {'observedLastTurnTokens': True}, {'futurePhaseCeiling': 999999}):
            path.write_text(canonical({**u, **change}))
            with self.assertRaises(Refusal): worker.context(self.registry, self.ledger, self.source)
        self.export.assert_not_called()

    def test_changed_native_latest_turn_is_not_adopted(self):
        self.r.latest = {'id': 'different-turn', 'status': 'completed'}
        with self.assertRaises(Refusal): self.collect()
        self.preserved()

    def test_wrong_or_unenforced_loaded_policy_is_not_static_schema_evidence(self):
        self.r.loaded = True; self.r.policy_bad = True
        with self.assertRaises(Refusal): self.collect()
        self.preserved()

    def test_active_or_nonempty_current_tracker_refuses_without_cancel(self):
        self.r.active = True
        with self.assertRaises(Refusal): worker.observe(self.registry, self.ledger, self.source)
        self.r.active = False; self.r.loaded = True; self.r.terminals = [{'id': 'running', 'status': 'running'}]
        with self.assertRaises(Refusal): worker.observe(self.registry, self.ledger, self.source)
        self.preserved()

    def test_model_or_policy_drift_is_unknown_not_fallback(self):
        count = []
        def callback(method):
            if method == 'model/list':
                count.append(1)
                if len(count) == 2: self.r.loaded = True
        self.r.callback = callback
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse((self.destination / 'report.json').exists()); self.preserved()

    def test_native_permission_or_disconnect_is_not_answered_or_reconnected(self):
        def fail(method):
            raise NativeReadFailure('unexpected_response', 'Synthetic held request')
        self.r.callback = fail
        with self.assertRaises(NativeReadFailure): self.collect()
        self.assertFalse((self.destination / 'report.json').exists()); self.preserved()

    def test_repository_drift_during_collection_is_retained_not_reverted(self):
        def drift(method):
            if method == 'model/list': (self.r.f.repo / 'unapproved-change.txt').write_text('retained')
        self.r.callback = drift
        with self.assertRaises(Refusal): self.collect()
        self.assertTrue((self.r.f.repo / 'unapproved-change.txt').exists()); self.preserved()

    def test_output_cannot_be_inside_source_ledger_or_checkout(self):
        for root in (self.ledger.root, Path(self.source), self.r.f.repo, self.registry.root):
            with self.assertRaises(Refusal): worker.collect(self.registry, self.ledger, self.source, root / 'bad-worker-evidence')
        self.export.assert_not_called(); self.preserved()

    def test_earliest_native_time_is_not_renewed_after_slow_validation(self):
        now = [time.time()]
        def slow(method):
            if method == 'model/list': now[0] += 121
        self.r.callback = slow
        with patch.object(worker.time, 'time', side_effect=lambda: now[0]):
            with self.assertRaisesRegex(Refusal, 'stale before publication'): self.collect()
        self.assertFalse((self.destination / 'report.json').exists()); self.preserved()

    def test_original_mailbox_receipt_must_match_the_publication(self):
        path = Path(self.q['mailbox']) / 'request.json'; value = startup.mailbox.read(path)
        value['result']['proposal']['objective'] = 'Changed after original receipt'
        path.write_text(canonical(value))
        with self.assertRaises(Refusal): self.collect()
        self.export.assert_not_called(); self.assertEqual(self.r.calls, self.calls)

    def test_historical_load_record_does_not_substitute_for_current_policy(self):
        path = Path(self.q['journal']) / 'load.json'; value = startup.mailbox.read(path)
        value['scope']['policy']['codeModeOffEnforced'] = False; path.write_text(canonical(value))
        with self.assertRaises(Refusal): self.collect()
        self.export.assert_not_called(); self.assertEqual(self.r.calls, self.calls)


class ClosedReadProxyTest(unittest.TestCase):
    def test_internal_rpc_rejects_mutation_subscription_and_foreign_targets(self):
        proxy = worker.WorkerReadProxy({}, 'brain', 'project')
        with patch.object(ReadProxy, '_rpc') as native:
            for method, params in [('thread/resume', {'threadId': 'brain'}), ('turn/start', {'threadId': 'brain'}),
                    ('thread/start', {}), ('thread/subscribe', {'threadId': 'brain'}), ('turn/interrupt', {}),
                    ('account/read', {'refreshToken': True}), ('thread/read', {'threadId': 'foreign', 'includeTurns': False}),
                    ('thread/read', {'threadId': 'brain', 'includeTurns': True}), ('project/read', {'projectId': 'foreign'})]:
                with self.assertRaises(Refusal): proxy._rpc(method, params)
            native.assert_not_called()

    def test_closed_read_vocabulary_does_not_add_native_authority(self):
        brain = '00000000-0000-4000-8000-000000000001'
        proxy = worker.WorkerReadProxy({}, brain, 'project')
        with patch.object(ReadProxy, '_rpc', return_value={'fixture': True}) as native:
            self.assertEqual(proxy._rpc('thread/read', {'threadId': brain, 'includeTurns': False}), {'fixture': True})
            proxy._rpc('account/read', {'refreshToken': False})
            proxy._rpc('model/list', {'cursor': None, 'limit': 30, 'includeHidden': False})
        self.assertEqual(native.call_count, 3)


if __name__ == '__main__': unittest.main()
