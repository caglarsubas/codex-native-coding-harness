"""Disposable SQLite/socket preservation and synthetic metadata, no live pilot.

The certificate/issued-host foundation is separately exercised against complete
real fixture lineage. Here only its OS boundary is synthetic; the actual closed
read-only RPC validator and metadata parsers run without a native process.
"""
import contextlib
import copy
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orchestrator import certificate_worker_readiness as api
from orchestrator.core import Refusal, canonical, digest
from orchestrator.host_lifecycle import write_record
from orchestrator.native_read_client import ReadProxy, NativeReadFailure
from test_native_policy_evidence import response as policy_response
from test_public_readiness import schemas
import test_post_reboot_dashboard as fixtures


class CertificateWorkerTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ReviewTest('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        c = self.f.c; self.brain = c['brainId']; self.record = c['record']
        self.record['cwd'] = c['checkout']
        self.record['policyEvidence'] = {'protocol': 'loaded_thread_policy_v1', 'sourceCommit': 'a'*40, 'sourceTree': 'b'*40}
        self.record['nativeTaskBackend'] = {'protocol': 'public_app_server_tasks_v1', 'sourceCommit': 'a'*40,
            'sourceTree': 'b'*40, 'trust': 'operator_reviewed_build_v1', 'desktopBridge': 'absent', 'repositoryMode': 'repo_exclusive'}
        self.phase = {'maxTokens': 10000, 'carriedPhaseCeiling': 5736373,
                      'mission': {'authority': {'checkpointReserveTokens': 500000}}}
        self.witness = self.f.root / 'witness'; self.witness.mkdir(mode=0o700); self.publish_witness()
        foundation = self.f.foundation.side_effect
        self.f.foundation.side_effect = lambda *a: (foundation(*a)[0], {'witness': str(self.witness)},
            SimpleNamespace(root=self.f.platform), SimpleNamespace(root=self.f.ledger))
        self.loaded = False; self.active = False; self.bad_policy = False; self.terminals = []
        self.latest = {'id': c['latestTurnId'], 'status': 'completed'}
        self.model = 'fixture-observed'; self.account = {'type': 'chatgpt', 'email': 'PRIVATE-NOT-RETAINED'}
        self.calls = []; self.callback = lambda _: None
        self.output = self.f.root / 'worker-evidence'
        exporter = patch.object(api.worker.public, 'export_schemas', return_value=api.worker.public.schema_contract(schemas()))
        self.exporter = exporter.start(); self.addCleanup(exporter.stop)
        boundaries = [patch.object(api.worker.WorkerReadProxy, '__enter__', lambda p: p),
                      patch.object(api.worker.WorkerReadProxy, '__exit__', return_value=None),
                      patch.object(ReadProxy, '_rpc', side_effect=self.rpc)]
        for p in boundaries: p.start(); self.addCleanup(p.stop)

    def publish_witness(self):
        c = self.f.c
        write_record(self.witness / 'report.json', {'context': {'workspaceId': c['workspaceId'],
            'brainId': c['brainId'], 'nativeTurnId': c['latestTurnId'], 'usage': copy.deepcopy(c['originalUsage']),
            'phase': copy.deepcopy(self.phase)}})

    def rpc(self, method, params):
        self.calls.append((method, copy.deepcopy(params))); self.callback(method)
        if method == 'project/read': return {'project': {'id': self.record['projectId'], 'roots': [{'path': self.record['cwd']}]}}
        if method == 'thread/read': return {'thread': {'id': self.brain, 'projectId': self.record['projectId'],
            'cwd': self.record['cwd'], 'status': {'type': 'active' if self.active else 'idle' if self.loaded else 'notLoaded'}}}
        if method == 'thread/turns/list': return {'data': [self.latest], 'nextCursor': None}
        if method == 'thread/effectivePolicy/read':
            value = policy_response(self.brain, self.record['cwd'])
            if not self.loaded: value['policy'] = None
            elif self.bad_policy: value['policy']['codeModeOffEnforced'] = False
            return value
        if method == 'thread/backgroundTerminals/list': return {'data': self.terminals, 'nextCursor': None}
        if method == 'mcpServerStatus/list': return {'data': [], 'nextCursor': None}
        if method == 'account/read': return {'requiresOpenaiAuth': True, 'account': copy.deepcopy(self.account)}
        if method == 'model/list': return {'data': [{'hidden': False, 'model': self.model,
            'supportedReasoningEfforts': [{'reasoningEffort': 'high'}]}], 'nextCursor': None}
        raise AssertionError('Unlisted RPC attempted: ' + method)

    def prepare(self):
        self.preview = api.prepare(self.f.repair_file, self.f.c['launchedSource']['root'], self.f.catalog_file, self.output)
        self.q = self.preview['request']; return self.preview

    def collect(self):
        self.prepare()
        return api.collect(self.q, digest(self.q), self.f.catalog_file)

    def conserved(self):
        self.f.conserved()
        self.assertTrue(all(m not in ('thread/resume', 'thread/start', 'thread/subscribe', 'turn/start', 'turn/interrupt',
                                     'item/commandExecution/requestApproval') for m, _ in self.calls))
        self.assertTrue(all(m != 'account/read' or p == {'refreshToken': False} for m, p in self.calls))

    def test_exact_scope_review_is_file_only_and_has_no_timer_or_execution_grant(self):
        first = self.prepare(); second = self.prepare()
        self.assertEqual(first, second); self.assertEqual(first['validUntil'], 'scope_changes')
        self.assertEqual(first['reviewHash'], digest(self.q)); self.assertFalse(first['executionReviewAvailable'])
        self.assertFalse(self.output.exists()); self.assertEqual(self.calls, []); self.exporter.assert_not_called(); self.conserved()

    def test_unloaded_is_blocked_and_unknown_not_a_load_or_play_review(self):
        result = self.collect(); report = api.dashboard.read(self.output / 'report.json')
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['blockers'], ['brain_not_loaded', 'loaded_policy_unknown', 'current_trackers_unknown'])
        self.assertIsNone(report['native']['policy']); self.assertIsNone(report['native']['trackedTerminals'])
        self.assertFalse(result['executionReviewAvailable']); self.assertFalse(result['boundary']['playAuthorized'])
        self.assertEqual(result['boundary']['currentTerminalSafety'], 'unknown')
        self.assertEqual(result['boundary']['historicalTerminalSafety'], 'unknown'); self.conserved()

    def test_loaded_can_complete_evidence_without_activating_or_clearing_any_fence(self):
        self.loaded = True; result = self.collect()
        self.assertEqual(result['status'], 'evidence_complete_not_activated'); self.assertEqual(result['blockers'], [])
        self.assertTrue(result['normalWritesBlocked']); self.assertFalse(result['executionReviewAvailable'])
        self.assertFalse(result['boundary']['ownershipReleased']); self.conserved()

    def test_private_account_and_routing_bodies_are_not_retained(self):
        self.collect()
        for path in self.output.iterdir(): self.assertNotIn(b'PRIVATE-NOT-RETAINED', path.read_bytes())
        self.conserved()

    def test_status_has_no_proxy_schema_export_or_timestamp_renewal(self):
        self.collect(); calls = copy.deepcopy(self.calls); raw = (self.output / 'report.json').read_bytes()
        with patch.object(api.worker, 'WorkerReadProxy', side_effect=AssertionError('No connection on status')), \
             patch.object(api.worker.public, 'export_schemas', side_effect=AssertionError('No export on status')):
            a, b = api.status(self.output), api.status(self.output)
        self.assertEqual(a, b); self.assertEqual(calls, self.calls)
        self.assertEqual(raw, (self.output / 'report.json').read_bytes()); self.conserved()

    def test_stale_status_preserves_earliest_native_observation(self):
        self.collect(); report = api.dashboard.read(self.output / 'report.json')
        # Replace only this module's clock; never change the process-wide clock.
        with patch.object(api, 'time', SimpleNamespace(time=lambda: report['observedAt'] + 121)):
            value = api.status(self.output)
        self.assertFalse(value['fresh']); self.assertEqual(value['observedAt'], report['observedAt']); self.conserved()

    def test_wrong_approval_never_creates_output_or_reads_native_metadata(self):
        self.prepare()
        with self.assertRaises(Refusal): api.collect(self.q, 'approved', self.f.catalog_file)
        self.assertFalse(self.output.exists()); self.assertEqual(self.calls, []); self.exporter.assert_not_called()

    def test_existing_or_partial_output_never_overwrites_or_recollects(self):
        self.prepare(); self.output.mkdir(mode=0o700); write_record(self.output / 'intent.json', {'partial': True})
        with self.assertRaises(Refusal): api.collect(self.q, digest(self.q), self.f.catalog_file)
        self.assertEqual(self.calls, []); self.exporter.assert_not_called(); self.conserved()

    def test_second_collect_is_not_replayable(self):
        self.collect(); before = self.calls.copy()
        with self.assertRaises(Refusal): api.collect(self.q, digest(self.q), self.f.catalog_file)
        self.assertEqual(self.calls, before); self.conserved()

    def test_changed_full_database_or_source_refuses_before_schema_or_native(self):
        self.prepare()
        with patch.object(api.dashboard, 'source_hash', return_value='f'*64):
            with self.assertRaises(Refusal): api.collect(self.q, digest(self.q), self.f.catalog_file)
        with contextlib.closing(sqlite3.connect(self.f.dbs['platform']['path'])) as db, db:
            db.execute("INSERT INTO preserved VALUES ('stop or competing writer')")
        with self.assertRaises(Refusal): api.collect(self.q, digest(self.q), self.f.catalog_file)
        self.exporter.assert_not_called(); self.assertEqual(self.calls, [])

    def test_foreign_or_duplicate_catalog_and_changed_catalog_pin_refuse(self):
        self.prepare(); value = api.dashboard.read(self.f.catalog_file)
        for rows in ([{**value['completeResult']['projects'][0], 'projectId': 'foreign'}],
                     value['completeResult']['projects'] * 2):
            write_record(self.f.catalog_file, {**value, 'completeResult': {'schemaVersion': 2, 'projects': rows}})
            with self.assertRaises(Refusal): api.collect(self.q, digest(self.q), self.f.catalog_file)
        self.exporter.assert_not_called(); self.assertEqual(self.calls, []); self.conserved()

    def test_old_review_has_no_timer_but_start_needs_fresh_actual_catalog(self):
        self.prepare(); at = api.dashboard.read(self.f.catalog_file)['observedAt']
        with patch.object(api.dashboard, 'time', SimpleNamespace(time=lambda: at + 121)):
            api.validate(self.q)
            with self.assertRaises(Refusal): api.collect(self.q, digest(self.q), self.f.catalog_file)
        self.assertFalse(self.output.exists()); self.assertEqual(self.calls, [])

    def test_actual_new_catalog_can_match_without_overwriting_original_pinned_catalog(self):
        self.prepare(); original = self.f.catalog_file.read_bytes(); fresh = self.f.root / 'fresh-catalog.json'
        value = api.dashboard.read(self.f.catalog_file); value['observedAt'] = time.time(); write_record(fresh, value)
        api.collect(self.q, digest(self.q), fresh)
        self.assertEqual(original, self.f.catalog_file.read_bytes()); self.conserved()

    def test_native_failure_preserves_partial_output_without_fallback_or_reconnect(self):
        self.callback = lambda _: (_ for _ in ()).throw(NativeReadFailure('proxy_closed', 'Synthetic disconnect'))
        with self.assertRaises(NativeReadFailure): self.collect()
        self.assertEqual({p.name for p in self.output.iterdir()}, {'intent.json'})
        with self.assertRaises(Refusal): api.status(self.output)
        self.conserved()

    def test_active_nonempty_unknown_or_unenforced_policy_never_qualifies(self):
        self.active = True
        with self.assertRaises(Refusal): self.collect()
        self.active = False; self.loaded = True; self.bad_policy = True
        with self.assertRaises(Refusal): api.observe(self.q)
        self.bad_policy = False; self.terminals = [{'processId': 'process', 'itemId': 'item'}]
        with self.assertRaises(Refusal): api.observe(self.q)
        self.conserved()

    def test_different_latest_turn_cannot_inherit_readiness(self):
        self.latest = {'id': 'foreign-turn', 'status': 'completed'}
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse((self.output / 'report.json').exists()); self.conserved()

    def test_model_account_or_activity_drift_stays_unknown(self):
        calls = []
        def drift(method):
            if method == 'model/list':
                calls.append(1)
                if len(calls) == 2: self.loaded = True
        self.callback = drift
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse((self.output / 'report.json').exists()); self.conserved()

    def test_model_catalog_drift_is_not_a_selected_model_or_fallback(self):
        counts = []
        def drift(method):
            if method == 'model/list':
                counts.append(1)
                if len(counts) == 2: self.model = 'different-model'
        self.callback = drift
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse((self.output / 'report.json').exists()); self.conserved()

    def test_authentication_loss_and_routing_drift_never_sign_in_or_refresh(self):
        counts = []
        def drift(method):
            if method == 'account/read':
                counts.append(1)
                if len(counts) == 2: self.account['email'] = 'changed-routing'
        self.callback = drift
        with self.assertRaises(Refusal): self.collect()
        self.callback = lambda _: None; self.account = None
        with self.assertRaises(Refusal): api.observe(self.q)
        self.assertFalse((self.output / 'report.json').exists()); self.conserved()

    def test_unknown_loaded_policy_cannot_be_forged_into_a_saved_complete_report(self):
        self.collect(); report = api.dashboard.read(self.output / 'report.json')
        for edit in (lambda v: v['native'].update(activity='idle'), lambda v: v.update(executionReviewAvailable=True),
                     lambda v: v.update(observedAt=True), lambda v: v.update(usage={}),
                     lambda v: v.update(remainingAuthority=[]), lambda v: v.update(extra='unlisted')):
            value = copy.deepcopy(report); edit(value)
            with self.assertRaises(Refusal): api.check_report(self.q, value)
        self.conserved()

    def test_native_delay_does_not_retimestamp_or_publish_stale_observation(self):
        now = [time.time()]
        def delay(method):
            if method == 'model/list': now[0] += 121
        self.callback = delay
        with patch.object(api, 'time', SimpleNamespace(time=lambda: now[0])):
            with self.assertRaisesRegex(Refusal, 'stale before retention'): self.collect()
        self.assertFalse((self.output / 'report.json').exists()); self.conserved()

    def test_post_native_scope_drift_never_rolls_back_or_publishes_success(self):
        def change(method):
            if method == 'model/list': self.f.c['pid'] = 777
        self.callback = change
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse((self.output / 'report.json').exists()); self.assertEqual(self.f.c['pid'], 777); self.conserved()

    def test_usage_missing_overrun_and_exhaustion_never_reset_accounting(self):
        self.loaded = True; usage = self.f.c['originalUsage']
        usage.update(observedLastTurnTokens=None, chargedReservationFloor=10000, futurePhaseCeiling=5726373,
                     gaps=['startup_usage_missing_or_incomplete', 'lifetime_coverage_not_asserted'])
        self.publish_witness(); result = self.collect()
        self.assertIn('preparation_usage_unknown', result['blockers']); self.assertFalse(result['boundary']['usageReset'])
        self.assertEqual(api.dashboard.read(self.output / 'report.json')['usage'], usage); self.conserved()

    def test_larger_actual_overrun_is_charged_and_exhausted_allocation_blocks(self):
        self.loaded = True; usage = self.f.c['originalUsage']
        usage.update(observedLastTurnTokens=5736373, chargedReservationFloor=5736373, futurePhaseCeiling=0)
        self.publish_witness(); result = self.collect()
        self.assertIn('carried_allocation_exhausted', result['blockers']); self.conserved()

    def test_malformed_bool_or_reduced_floor_refuses(self):
        usage = self.f.c['originalUsage']; usage['observedLastTurnTokens'] = True; self.publish_witness()
        with self.assertRaises(Refusal): self.prepare()
        usage.update(observedLastTurnTokens=15823, chargedReservationFloor=0); self.publish_witness()
        with self.assertRaises(Refusal): self.prepare()
        self.assertEqual(self.calls, [])

    def test_changed_report_seal_or_extra_record_never_promotes_cached_evidence(self):
        self.collect(); report = self.output / 'report.json'; report.write_text('{}')
        with self.assertRaises(Refusal): api.status(self.output)
        write_record(self.output / 'extra.json', {})
        with self.assertRaises(Refusal): api.status(self.output)
        self.conserved()

    def test_disjoint_output_never_enters_operational_native_checkout_or_source_roots(self):
        for root in (self.f.platform, self.f.ledger, Path(self.f.c['nativeHome']),
                     Path(self.f.c['checkout']), Path(self.f.c['launchedSource']['root']), self.f.pkg.parent):
            root.mkdir(mode=0o700, exist_ok=True)
            with self.assertRaises(Refusal):
                api.prepare(self.f.repair_file, self.f.c['launchedSource']['root'], self.f.catalog_file, root / 'bad')
        self.assertEqual(self.calls, []); self.exporter.assert_not_called(); self.conserved()


if __name__ == '__main__': unittest.main()
