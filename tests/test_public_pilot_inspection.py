"""Inspection-only claims, hostile/drifting metadata and original conservation."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from orchestrator import public_pilot_inspection as inspection, public_host_restart as restart, standard
from orchestrator.core import Refusal, digest
from orchestrator.host_lifecycle import write_record
from orchestrator.workspaces import fingerprint
import test_public_host_restart as restart_fixtures
import test_native_policy_evidence as policy


class InspectionTest(unittest.TestCase):
    def setUp(self):
        self.f = restart_fixtures.RestartTest(methodName='runTest')
        self.f.setUp(); self.addCleanup(self.f.doCleanups); self.f.prepare()
        self.root, self.registry, self.ledger = self.f.root, self.f.registry, self.f.ledger
        self.restart_path = self.f.path
        spec = self.f.spec
        attempt = self.f.directory/'attempt'; attempt.mkdir(mode=0o700)
        write_record(attempt/'intent.json', {'kind': restart.KIND, 'specHash': digest(spec), 'reviewHash': self.f.hash, 'at': 1})
        write_record(attempt/'exec.claim', {})
        (attempt/'exec.claim').write_bytes(b'')
        write_record(attempt/'status.json', {'kind': restart.KIND, 'status': 'exec_boundary_issued',
            'pid': 234567890, 'parentPid': 2, 'at': 1, 'specHash': digest(spec),
            'processIdentity': '234567890 Thu Oct 15 15:05:58 2026',
            'hostReady': False, 'terminalSafety': 'unknown', 'pilotAccepted': False})
        write_record(Path(spec['fencePath']), {'kind': restart.KIND, 'specHash': digest(spec),
                                              'reviewDirectory': spec['reviewDirectory']})
        self.alias = self.f.sockets/'host.sock'; self.alias.write_bytes(b'fixture socket only')
        self.binding = copy.deepcopy(self.f.f.destination)
        self.binding['endpoint'].update(socket=str(self.alias), socketIdentity={'fixture': 'new-epoch'})
        self.binding_path = self.root/'current-binding.json'; write_record(self.binding_path, self.binding)
        self.directory = self.root/'inspection-review'; self.path = self.directory/'inspection.json'
        self.brain, self.cwd = self.f.f.brain, self.f.f.cwd
        self.project = self.f.f.project_id
        self.loaded, self.fail_load, self.terminals = False, False, []
        self.calls, self.callback, self.policy_wrong = [], None, False
        self.thread_override, self.latest_override, self.auth_missing, self.mcp = {}, {}, False, []
        outer = self
        def rpc(proxy, method, params):
            outer.calls.append((method, copy.deepcopy(params)))
            if outer.callback: outer.callback(method, params)
            if method == 'project/read': return {'project': {'id': outer.project, 'roots': [{'path': outer.cwd}]}}
            if method == 'thread/read':
                return {'thread': dict({'id': outer.brain, 'projectId': outer.project, 'cwd': outer.cwd,
                    'status': {'type': 'idle' if outer.loaded else 'notLoaded'}}, **outer.thread_override)}
            if method == 'thread/turns/list':
                return {'data': [dict({'id': 'owned-turn-1', 'status': 'completed'}, **outer.latest_override)], 'nextCursor': None}
            if method == 'thread/effectivePolicy/read':
                if not outer.loaded: return {'version': 1, 'threadId': outer.brain, 'policy': None}
                value = policy.response(outer.brain, outer.cwd)
                if outer.policy_wrong: value['policy']['codeModeOffEnforced'] = False
                return value
            if method == 'mcpServerStatus/list': return {'data': outer.mcp, 'nextCursor': None}
            if method == 'account/read': return {'account': None if outer.auth_missing else {'type': 'chatgpt'}, 'requiresOpenaiAuth': True}
            if method == 'thread/backgroundTerminals/list': return {'data': outer.terminals, 'nextCursor': None}
            if method == 'thread/resume':
                outer.loaded = True
                if outer.fail_load: raise Refusal('Synthetic lost acknowledgment; PRIVATE_NATIVE_BODY')
                return {'thread': {'id': outer.brain, 'cwd': outer.cwd, 'turns': []}}
            raise AssertionError('Unexpected native call: '+method)
        for item in (patch.object(inspection, 'load_binding', return_value=copy.deepcopy(self.binding)),
                     patch.object(inspection, 'inspect_endpoint', return_value=copy.deepcopy(self.binding['endpoint'])),
                     patch.object(restart, 'process_absent', return_value=True), patch.object(restart, 'live_process'),
                     patch.object(inspection.ReadProxy, '__enter__', lambda p: p),
                     patch.object(inspection.ReadProxy, '__exit__', lambda *_: None),
                     patch.object(inspection.ReadProxy, '_rpc', rpc)):
            item.start(); self.addCleanup(item.stop)
        with standard.read_db(self.ledger.db) as db: self.before = fingerprint(db)
        self.before_native_transfer = copy.deepcopy(self.f.f.calls)

    def prepare(self, **kwargs):
        result = inspection.prepare(self.registry, self.ledger, self.restart_path, self.binding_path, self.directory, **kwargs)
        self.spec = inspection.load_spec(self.path); self.hash = result['reviewHash']
        return result

    def apply(self): return inspection.apply(self.registry, self.ledger, self.path, self.hash)

    def assert_conserved(self):
        with standard.read_db(self.ledger.db) as db: self.assertEqual(self.before, fingerprint(db))
        self.assertEqual(self.f.f.calls, self.before_native_transfer, 'Historical endpoints are never reconnected')
        self.assertFalse(any(m in {'turn/start', 'turn/interrupt', 'thread/start', 'project/restoreMetadata',
                                  'thread/metadata/update', 'account/login/start'} for m, _ in self.calls))

    def test_one_exact_inspection_load_and_repeated_current_policy_without_turn_or_state_change(self):
        preview = self.prepare()
        self.assertFalse(self.loaded)
        self.assertEqual(preview['validity'], 'until_scope_changes')
        result = self.apply()
        self.assertEqual(result['loadDelivery'], 'acknowledged')
        self.assertEqual(result['currentObservation']['activity'], 'idle')
        self.assertEqual(result['currentObservation']['trackedTerminals'], [])
        self.assertEqual([p for m, p in self.calls if m == 'thread/resume'], [inspection.load_params(self.spec['provenance'])])
        for field in ('resumeAuthorized', 'migrationQualified', 'closeoutAuthorized', 'pilotAccepted', 'usageReset'):
            self.assertFalse(result['boundary'][field])
        self.assertEqual(result['boundary']['currentTerminalSafety'], 'unknown')
        self.assertEqual(result['boundary']['historicalTerminalSafety'], 'unknown')
        self.assert_conserved()

    def test_until_scope_changes_review_has_no_wall_clock_expiry(self):
        self.prepare()
        with patch.object(inspection.time, 'time', return_value=999999999999):
            self.assertEqual(inspection.preview(self.registry, self.ledger, self.path)['reviewHash'], self.hash)
            self.apply()
        self.assert_conserved()

    def test_wrong_review_old_launch_and_transfer_approvals_cannot_claim(self):
        self.prepare()
        for approval in ('yes', self.f.hash, self.f.f.review, 'a'*64):
            with self.subTest(approval=approval), self.assertRaises(Refusal):
                inspection.apply(self.registry, self.ledger, self.path, approval)
        self.assertFalse((self.directory/'attempt').exists()); self.assertFalse(self.loaded)
        self.assert_conserved()

    def test_already_loaded_matching_policy_only_observes_never_resumes(self):
        self.loaded = True
        self.assertEqual(self.prepare()['maximumInspectionLoads'], 0)
        self.assertEqual(self.apply()['loadDelivery'], 'not_requested')
        self.assertFalse(any(m == 'thread/resume' for m, _ in self.calls))
        self.assert_conserved()

    def test_interrupted_load_consumed_and_reconciliation_never_reloads_or_invents_ack(self):
        self.prepare(); self.fail_load = True
        with self.assertRaises(Refusal): self.apply()
        self.assertTrue((self.directory/'attempt/inspection-load.claim').exists())
        self.assertFalse((self.directory/'attempt/load-ack.json').exists())
        self.fail_load = False
        result = inspection.reconcile(self.registry, self.ledger, self.path)
        self.assertEqual(result['loadDelivery'], 'unknown'); self.assertTrue(result['reconciledReadOnly'])
        for _ in range(2):
            with self.assertRaises(Refusal): self.apply()
        self.assertEqual(sum(m == 'thread/resume' for m, _ in self.calls), 1)
        self.assert_conserved()

    def test_interruption_before_load_stays_consumed_without_a_reconcile_load(self):
        self.prepare()
        with patch.object(inspection, 'exclusive', side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt): self.apply()
        with self.assertRaises(Refusal): self.apply()
        with self.assertRaises((Refusal, FileNotFoundError)):
            inspection.reconcile(self.registry, self.ledger, self.path)
        self.assertFalse(any(m == 'thread/resume' for m, _ in self.calls))
        self.assert_conserved()

    def test_canonical_fence_prevents_new_directory_touched_file_or_new_endpoint_retry(self):
        self.prepare(); self.apply()
        self.directory = self.root/'another-inspection-review'
        with self.assertRaises(Refusal): self.prepare()
        os.utime(self.binding_path, None)
        with self.assertRaises(Refusal): self.prepare()
        self.assertEqual(sum(m == 'thread/resume' for m, _ in self.calls), 1)
        self.assert_conserved()

    def test_scope_drift_immediately_after_claim_sends_no_load(self):
        self.prepare(); original = inspection.exclusive
        def race(path, value):
            original(path, value)
            if path.name == 'inspection-load.claim':
                with self.ledger.tx() as db:
                    meta = self.ledger.get(db, 'meta', 1); meta['standardRun']['brainObservedTokens'] += 1
                    self.ledger.put(db, 'meta', 1, meta)
        with patch.object(inspection, 'exclusive', side_effect=race):
            with self.assertRaises(Refusal): self.apply()
        self.assertTrue(Path(self.spec['fencePath']).exists())
        self.assertFalse(any(m == 'thread/resume' for m, _ in self.calls))

    def test_competing_review_wins_canonical_fence_before_any_load(self):
        self.prepare(); original = inspection.exclusive
        def race(path, value):
            if path == Path(self.spec['fencePath']):
                original(path, dict(value, reviewDirectory='/another-owner-review'))
            original(path, value)
        with patch.object(inspection, 'exclusive', side_effect=race), self.assertRaises(FileExistsError): self.apply()
        with self.assertRaises(Refusal): inspection.reconcile(self.registry, self.ledger, self.path)
        self.assertFalse(any(m == 'thread/resume' for m, _ in self.calls)); self.assert_conserved()

    def test_pause_or_controller_or_usage_drift_invalidates_preview_and_apply(self):
        self.prepare()
        for field, value in (('controller', {'owner': 'new'}), ('paused', False),
                             ('brainControl', {'desired': 'stopped', 'phase': 'parked'})):
            with self.ledger.tx() as db:
                meta = self.ledger.get(db, 'meta', 1); existed = field in meta
                original = copy.deepcopy(meta.get(field)); meta[field] = value
                self.ledger.put(db, 'meta', 1, meta)
            with self.subTest(field=field), self.assertRaises(Refusal): self.apply()
            with self.ledger.tx() as db:
                meta = self.ledger.get(db, 'meta', 1)
                if not existed: meta.pop(field, None)
                else: meta[field] = original
                self.ledger.put(db, 'meta', 1, meta)
        self.assertFalse(self.loaded)
        self.assertFalse((self.directory/'attempt').exists()); self.assert_conserved()

    def test_native_identity_turn_activity_auth_and_mcp_gaps_refuse_before_claim(self):
        self.prepare()
        changes = [('thread_override', {'id': 'foreign'}), ('thread_override', {'projectId': 'foreign'}),
                   ('thread_override', {'status': {'type': 'active'}}),
                   ('thread_override', {'status': {'type': 'idle', 'activeFlags': ['waitingOnApproval']}}),
                   ('latest_override', {'id': 'another-turn'}), ('latest_override', {'status': 'inProgress'}),
                   ('auth_missing', True), ('mcp', [{'name': 'unexpected'}])]
        for field, value in changes:
            original = getattr(self, field); setattr(self, field, value)
            with self.subTest(field=field, value=value), self.assertRaises(Refusal): self.apply()
            setattr(self, field, original)
        self.assertFalse((self.directory/'attempt').exists()); self.assert_conserved()

    def test_loaded_wrong_policy_or_nonempty_terminals_stays_fenced(self):
        self.loaded = True; self.policy_wrong = True
        with self.assertRaises(Refusal): self.prepare()
        self.policy_wrong = False; self.terminals = [{'processId': 'p1', 'itemId': 'i1'}]
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists()); self.assert_conserved()

    def test_unloaded_reconcile_never_queries_terminals_or_loads_again(self):
        self.prepare(); self.apply(); self.loaded = False; count = len(self.calls)
        with self.assertRaises(Refusal): inspection.reconcile(self.registry, self.ledger, self.path)
        self.assertFalse(any(m in {'thread/resume', 'thread/backgroundTerminals/list'} for m, _ in self.calls[count:]))
        self.assert_conserved()

    def test_status_never_queries_native_or_ledger_or_claims_even_after_drift(self):
        self.prepare(); self.apply(); before = copy.deepcopy(self.calls)
        with (patch.object(inspection, 'provenance', side_effect=AssertionError('No live checks')),
              patch.object(restart, 'source_tree', side_effect=AssertionError('No source checks'))):
            result = inspection.status(self.path)
        self.assertTrue(result['historical']); self.assertTrue(result['claimRetained'])
        self.assertEqual(before, self.calls); self.assert_conserved()

    def test_authentication_file_is_never_opened_or_copied(self):
        auth = self.f.home/'auth.json'; auth.write_text('PRIVATE_CREDENTIAL_BODY'); auth.chmod(0o600)
        original = restart.read_file
        def guard(path, *args, **kwargs):
            self.assertNotEqual(Path(path), auth)
            return original(path, *args, **kwargs)
        with patch.object(restart, 'read_file', side_effect=guard):
            self.prepare(); result = self.apply()
        self.assertNotIn('PRIVATE_CREDENTIAL_BODY', json.dumps(result)); self.assert_conserved()

    def test_restart_journal_config_history_or_binding_epoch_change_refuses(self):
        self.prepare()
        (self.f.home/'config.toml').write_text('approval_policy = "never"')
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.loaded); self.assert_conserved()

    def test_binding_file_touch_invalidates_unchanged_review(self):
        self.prepare(); os.utime(self.binding_path, None)
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse((self.directory/'attempt').exists()); self.assert_conserved()

    def test_failed_or_uncertain_host_exec_never_becomes_inspection_authority(self):
        path = self.f.directory/'attempt/status.json'; saved = inspection.record(path)
        for state in ('exec_failed', 'exec_outcome_unknown'):
            write_record(path, dict(saved, status=state))
            with self.subTest(state=state), self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists()); self.assert_conserved()

    def test_foreign_workspace_cannot_use_matching_brain_or_path(self):
        with patch.object(self.ledger, 'workspace_id', 'another-workspace'), self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists()); self.assert_conserved()

    def test_missing_claim_refuses_reconcile_without_recreating_it(self):
        self.prepare(); self.apply(); claim = self.directory/'attempt/inspection-load.claim'
        claim.unlink(); calls = copy.deepcopy(self.calls)
        with self.assertRaises(FileNotFoundError): inspection.reconcile(self.registry, self.ledger, self.path)
        self.assertEqual(calls, self.calls); self.assertFalse(claim.exists()); self.assert_conserved()

    def test_activity_change_after_terminal_read_prevents_observation(self):
        self.loaded = True
        def race(method, _):
            if method == 'thread/backgroundTerminals/list': self.thread_override = {'status': {'type': 'active'}}
        self.callback = race
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists()); self.assert_conserved()

    def test_public_status_cli_does_not_open_an_unavailable_registry(self):
        import contextlib
        import io
        import sys
        self.prepare(); before = copy.deepcopy(self.calls); output = io.StringIO()
        with patch.object(sys, 'argv', ['inspection', '--platform', '/not/a/platform', '--workspace', 'foreign',
                                      'status', str(self.path)]), contextlib.redirect_stdout(output):
            inspection.main()
        self.assertEqual(json.loads(output.getvalue())['status'], 'prepared_not_submitted')
        self.assertEqual(before, self.calls); self.assert_conserved()

    def test_changed_implementation_refuses_before_new_native_read(self):
        self.prepare(); before = copy.deepcopy(self.calls)
        with patch.object(restart, 'source_tree', return_value='d'*40), self.assertRaises(Refusal): self.apply()
        self.assertEqual(before, self.calls); self.assert_conserved()

    def test_process_and_original_pid_absence_are_mandatory(self):
        with patch.object(restart, 'process_absent', return_value=False), self.assertRaises(Refusal): self.prepare()
        with patch.object(restart, 'live_process', side_effect=Refusal('birth differs')), self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.loaded); self.assert_conserved()

    def test_drift_during_native_reads_prevents_result_retention(self):
        self.prepare()
        def callback(method, _):
            if method == 'thread/resume': self.latest_override = {'id': 'new-native-turn'}
        self.callback = callback
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(list((self.directory/'attempt').glob('observation-*.json')))
        self.assertTrue(Path(self.spec['fencePath']).exists()); self.assert_conserved()

    def test_proxy_rejects_unreviewed_method_params_and_second_load(self):
        self.prepare(); proxy = inspection.InspectionProxy(self.spec['provenance'])
        for method, params in [('turn/start', {}), ('turn/interrupt', {}), ('account/read', {'refreshToken': True}),
                               ('thread/read', {'threadId': 'other', 'includeTurns': False}),
                               ('thread/resume', inspection.load_params(self.spec['provenance'])),
                               ('thread/backgroundTerminals/list', {'threadId': self.brain, 'cursor': None, 'limit': True})]:
            with self.subTest(method=method), self.assertRaises(Refusal): proxy._rpc(method, params)
        proxy.load_permitted = True
        wrong = inspection.load_params(self.spec['provenance']); wrong['path'] = '/arbitrary/history'
        with self.assertRaises(Refusal): proxy._rpc('thread/resume', wrong)
        proxy._rpc('thread/resume', inspection.load_params(self.spec['provenance']))
        with self.assertRaises(Refusal): proxy._rpc('thread/resume', inspection.load_params(self.spec['provenance']))

    def owned_clock(self, callback=None):
        from contextlib import ExitStack
        stack = ExitStack(); elapsed = [0.0]
        def sleep(seconds):
            elapsed[0] += seconds
            if callback: callback()
        stack.enter_context(patch('orchestrator.native_subscription.time.monotonic', lambda: elapsed[0]))
        stack.enter_context(patch('orchestrator.native_subscription.time.sleep', sleep))
        return stack

    def test_future_owned_window_keeps_same_connection_records_progress_then_closes(self):
        preview = self.prepare(subscription_seconds=75)
        self.assertEqual(self.spec['kind'], inspection.SUBSCRIPTION_KIND)
        self.assertEqual(preview['subscription']['maximumSeconds'], 75)
        with self.owned_clock(): result = self.apply()
        self.assertEqual(result['subscription']['currentEvidence'], 'unknown_after_release')
        self.assertEqual(sum(m == 'thread/resume' for m, _ in self.calls), 1)
        opened = inspection.record(self.directory/'attempt/subscription-open.json')
        closed = inspection.record(self.directory/'attempt/subscription-close.json')
        self.assertEqual(opened['connectionId'], closed['connectionId'])
        self.assertEqual(closed['status'], 'window_completed')
        observations = [inspection.record(p) for p in (self.directory/'attempt').glob('observation-*.json')]
        self.assertGreater(len(observations), 2)
        self.assertTrue(all(row['subscriptionOwner'] == opened for row in observations))
        self.assertFalse(result['boundary']['resumeAuthorized']); self.assert_conserved()

    def test_v2_bounds_and_loaded_adoption_refuse_without_claim(self):
        for seconds in (True, 0, 14, 301, 15.5, '75'):
            with self.subTest(seconds=seconds), self.assertRaises(Refusal): self.prepare(subscription_seconds=seconds)
        self.loaded = True
        with self.assertRaises(Refusal): self.prepare(subscription_seconds=75)
        self.assertFalse(self.directory.exists()); self.assert_conserved()

    def test_owned_interruption_closes_without_retry_or_claim_migration(self):
        self.prepare(subscription_seconds=75)
        def interrupted(): raise KeyboardInterrupt()
        with self.owned_clock(interrupted), self.assertRaises(KeyboardInterrupt): self.apply()
        self.assertEqual(inspection.record(self.directory/'attempt/subscription-close.json')['status'], 'interrupted_or_failed')
        with self.assertRaises(Refusal): self.apply()
        calls = len(self.calls)
        inspection.reconcile(self.registry, self.ledger, self.path)
        self.assertFalse(any(m == 'thread/resume' for m, _ in self.calls[calls:])); self.assert_conserved()

    def test_owned_lost_load_response_consumes_and_does_not_invent_ack_or_reconnect(self):
        self.prepare(subscription_seconds=75); self.fail_load = True
        with self.owned_clock(), self.assertRaises(Refusal): self.apply()
        self.fail_load = False
        self.assertFalse((self.directory/'attempt/load-ack.json').exists())
        result = inspection.reconcile(self.registry, self.ledger, self.path)
        self.assertEqual(result['loadDelivery'], 'unknown')
        self.assertEqual(inspection.status(self.path)['subscription']['status'], 'interrupted_or_failed')
        self.assertEqual(sum(m == 'thread/resume' for m, _ in self.calls), 1); self.assert_conserved()

    def test_owned_policy_drift_or_unloading_closes_and_remains_consumed(self):
        self.prepare(subscription_seconds=75)
        with self.owned_clock(lambda: setattr(self, 'loaded', False)), self.assertRaises(Refusal): self.apply()
        count = len(self.calls)
        with self.assertRaises(Refusal): inspection.reconcile(self.registry, self.ledger, self.path)
        self.assertFalse(any(m in {'thread/resume', 'thread/backgroundTerminals/list'} for m, _ in self.calls[count:]))
        self.assertEqual(sum(m == 'thread/resume' for m, _ in self.calls), 1); self.assert_conserved()

    def test_owned_new_controller_detected_before_another_native_read(self):
        self.prepare(subscription_seconds=75); at_drift = []
        def drift():
            with self.ledger.tx() as db:
                meta = self.ledger.get(db, 'meta', 1); meta['controller'] = {'owner': 'new-owner'}
                self.ledger.put(db, 'meta', 1, meta)
            at_drift.append(len(self.calls))
        with self.owned_clock(drift), self.assertRaises(Refusal): self.apply()
        self.assertEqual(len(self.calls), at_drift[0])
        self.assertEqual(inspection.record(self.directory/'attempt/subscription-close.json')['status'], 'interrupted_or_failed')

    def test_consumed_v1_cannot_become_v2_even_in_new_directory(self):
        self.prepare(); self.apply(); self.directory = self.root/'new-v2-review'
        with self.assertRaises(Refusal): self.prepare(subscription_seconds=75)
        self.assertEqual(sum(m == 'thread/resume' for m, _ in self.calls), 1); self.assert_conserved()

    def test_consumed_v2_cannot_become_v1_or_another_v2(self):
        self.prepare(subscription_seconds=15)
        with self.owned_clock(): self.apply()
        self.directory = self.root/'new-review'
        for kwargs in ({}, {'subscription_seconds': 75}):
            with self.assertRaises(Refusal): self.prepare(**kwargs)
        self.assert_conserved()

    def test_v2_duration_edit_requires_new_exact_review(self):
        self.prepare(subscription_seconds=75)
        edited = copy.deepcopy(self.spec); edited['subscription']['maximumSeconds'] = 80
        write_record(self.path, edited)
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse((self.directory/'attempt').exists()); self.assert_conserved()

    def test_owned_status_is_historical_not_a_liveness_probe_or_resume_permit(self):
        self.prepare(subscription_seconds=15)
        with self.owned_clock(): self.apply()
        calls = copy.deepcopy(self.calls)
        with patch.object(inspection, 'provenance', side_effect=AssertionError('No live checks')):
            state = inspection.status(self.path)
            self.assertEqual(state['subscription']['status'], 'window_completed')
            self.assertEqual(state['subscription']['currentEvidence'], 'unknown')
            (self.directory/'attempt/subscription-close.json').unlink()
            self.assertEqual(inspection.status(self.path)['subscription']['status'], 'unknown_not_reconnectable')
        self.assertEqual(self.calls, calls); self.assert_conserved()

    def test_owned_connection_failure_records_no_private_error_body_and_never_reconnects(self):
        from orchestrator.native_read_client import NativeReadFailure
        self.prepare(subscription_seconds=75)
        def disconnect():
            self.callback = lambda *_: (_ for _ in ()).throw(NativeReadFailure('proxy_closed', 'PRIVATE_ERROR'))
        with self.owned_clock(disconnect), self.assertRaises(NativeReadFailure): self.apply()
        end = inspection.record(self.directory/'attempt/subscription-close.json')
        self.assertNotIn('PRIVATE_ERROR', json.dumps(end))
        self.assertEqual(end['status'], 'interrupted_or_failed')
        self.callback = None
        with self.assertRaises(Refusal): self.apply()
        self.assertEqual(sum(m == 'thread/resume' for m, _ in self.calls), 1); self.assert_conserved()

    def test_owned_ack_persistence_failure_never_backfills_or_reloads(self):
        self.prepare(subscription_seconds=75); original = inspection.write_record
        def failure(path, value):
            if path.name == 'load-ack.json': raise OSError('fixture disk failure')
            return original(path, value)
        with patch.object(inspection, 'write_record', side_effect=failure), self.owned_clock(), self.assertRaises(OSError): self.apply()
        self.assertEqual(inspection.reconcile(self.registry, self.ledger, self.path)['loadDelivery'], 'unknown')
        self.assertEqual(sum(m == 'thread/resume' for m, _ in self.calls), 1); self.assert_conserved()

    def test_owned_registration_failure_leaves_canonical_claim_consumed_without_load(self):
        self.prepare(subscription_seconds=75); original = inspection.exclusive
        def failure(path, value):
            if path.name == 'subscription-open.json': raise OSError('fixture disk failure')
            return original(path, value)
        with patch.object(inspection, 'exclusive', side_effect=failure), self.owned_clock(), self.assertRaises(OSError): self.apply()
        with self.assertRaises(Refusal): self.apply()
        self.assertTrue(Path(self.spec['fencePath']).exists())
        self.assertFalse(any(m == 'thread/resume' for m, _ in self.calls)); self.assert_conserved()

    def test_owned_status_rejects_changed_owner_or_close_record(self):
        self.prepare(subscription_seconds=15)
        with self.owned_clock(): self.apply()
        path = self.directory/'attempt/subscription-close.json'; end = inspection.record(path)
        for field, value in (('status', 'active'), ('connectionId', 'other'), ('reconnectAllowed', True),
                             ('terminalSafety', 'safe'), ('connectionClosed', False)):
            write_record(path, dict(end, **{field: value}))
            with self.subTest(field=field), self.assertRaises(Refusal): inspection.status(self.path)
        write_record(path, end)
        opened = self.directory/'attempt/subscription-open.json'; saved = inspection.record(opened)
        write_record(opened, dict(saved, maximumSeconds=300))
        with self.assertRaises(Refusal): inspection.status(self.path)
        self.assert_conserved()


if __name__ == '__main__': unittest.main()
