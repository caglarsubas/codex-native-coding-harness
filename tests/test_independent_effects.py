import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orchestrator import effect_capture as capture, independent_effects as independent
from orchestrator.core import Refusal, canonical, digest
from orchestrator.native_read_client import ReadProxy
from orchestrator.app_server_wake import AppServerWake, WakeProxy
import test_cleanup_collector as fixture

BRAIN = '11111111-1111-4111-8111-111111111111'


class EffectCaptureTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve(); self.root.chmod(0o700)
        self.ledger = SimpleNamespace(root=self.root, workspace_id='fixture')
        self.binding = {'endpoint': {}, 'brains': {BRAIN: {'workspaceId': 'fixture'}}}
        self.command = {'id': 'control', 'kind': 'standard_play', 'fingerprint': digest('original'),
            'notification': {'status': 'sending', 'brainId': BRAIN,
                'hostInspectionTransport': 'owned_observer_v1',
                'hostRunId': 'run', 'hostBindingHash': digest(self.binding)}}
        self.meta = {'brainId': BRAIN, 'standardRun': {'id': 'run', 'brainId': BRAIN,
            'protocol': 'standard_cooperative_v1'}}
        self.item = {'id': 'item-1', 'type': 'commandExecution', 'command': 'PRIVATE COMMAND',
            'cwd': '/PRIVATE/CWD', 'status': 'completed', 'exitCode': 0,
            'aggregatedOutput': 'PRIVATE OUTPUT', 'processId': 'native-handle', 'osPid': 123}

    def tearDown(self): self.temp.cleanup()

    def begin(self):
        self.command['notification'][capture.FIELD] = capture.begin(self.ledger, self.binding, self.command, self.meta)

    def event(self, method='item/completed', **changes):
        item = {**self.item, **changes}
        return {'method': method, 'params': {'threadId': BRAIN, 'turnId': 'turn', 'item': item}}

    def seal(self, *, status='completed', failed=False):
        self.command['notification']['nativeTurnId'] = 'turn'
        capture.seal(self.ledger, self.command, 'turn', status, failed=failed)

    def test_original_anchor_exclusive_chain_and_private_metadata_only(self):
        self.begin()
        capture.append(self.ledger, 'control', BRAIN, self.event('item/started', status='inProgress', exitCode=None))
        capture.append(self.ledger, 'control', BRAIN, self.event())
        self.seal()
        result = capture.retained(self.ledger, self.command)
        self.assertEqual(result['status'], 'observed')
        self.assertEqual(len(result['events']), 2)
        self.assertFalse(result['completeInventory'])
        self.assertEqual(result['historicalCleanup'], 'unknown')
        raw = capture.path_for(self.ledger, 'control').read_text()
        self.assertNotIn('PRIVATE', raw)
        self.assertNotIn('native-handle', raw)
        self.assertNotIn('"osPid":123', raw)
        self.assertEqual(capture.path_for(self.ledger, 'control').stat().st_mode & 0o777, 0o600)

    def test_no_original_capture_is_unavailable_not_empty_safety(self):
        result = capture.retained(self.ledger, self.command)
        self.assertEqual(result['reason'], 'capture_absent_at_original_effect')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_cannot_create_capture_after_an_accepted_original_effect(self):
        self.command['notification']['status'] = 'accepted'
        with self.assertRaises(Refusal): self.begin()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_wrong_run_binding_brain_or_protocol_refuses_before_creation(self):
        for mutation in (lambda: self.meta['standardRun'].update(protocol='strict'),
                         lambda: self.meta['standardRun'].update(id='foreign'),
                         lambda: self.meta.update(brainId='foreign'),
                         lambda: self.command['notification'].update(hostBindingHash=digest('foreign'))):
            before_meta, before_command = copy.deepcopy(self.meta), copy.deepcopy(self.command)
            mutation()
            with self.assertRaises(Refusal): self.begin()
            self.meta, self.command = before_meta, before_command
        self.assertEqual(list(self.root.iterdir()), [])

    def test_begin_cannot_overwrite_a_consumed_capture_even_without_marker(self):
        marker = capture.begin(self.ledger, self.binding, self.command, self.meta)
        before = capture.path_for(self.ledger, 'control').read_bytes()
        with self.assertRaises(FileExistsError): capture.begin(self.ledger, self.binding, self.command, self.meta)
        self.assertEqual(before, capture.path_for(self.ledger, 'control').read_bytes())
        self.assertEqual(marker['status'], 'open')

    def test_open_or_interrupted_capture_never_becomes_complete(self):
        self.begin()
        self.assertEqual(capture.retained(self.ledger, self.command)['status'], 'incomplete')
        capture.append(self.ledger, 'control', BRAIN, self.event())
        self.seal(status='connection_lost')
        result = capture.retained(self.ledger, self.command)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['reason'], 'capture_interrupted')
        self.assertFalse(result['completeInventory'])

    def test_persistence_failure_is_a_retained_capture_gap_not_retry_permission(self):
        self.begin(); self.seal(failed=True)
        self.assertEqual(capture.retained(self.ledger, self.command)['status'], 'incomplete')
        with self.assertRaises(Refusal): capture.seal(self.ledger, self.command, 'turn', 'completed')
        with self.assertRaises(Refusal): capture.append(self.ledger, 'control', BRAIN, self.event())

    def test_foreign_events_and_transcripts_are_not_retained(self):
        self.begin()
        row = self.event(); row['params']['threadId'] = 'foreign'
        capture.append(self.ledger, 'control', BRAIN, row)
        capture.append(self.ledger, 'control', BRAIN, self.event(type='agentMessage', text='PRIVATE'))
        self.seal()
        self.assertEqual(capture.retained(self.ledger, self.command)['events'], [])

    def test_observation_clock_does_not_fabricate_native_completion_time(self):
        self.begin()
        capture.append(self.ledger, 'control', BRAIN, {'method': 'turn/completed', 'params': {
            'threadId': BRAIN, 'turn': {'id': 'turn', 'status': 'completed'}}})
        self.seal()
        event = capture.retained(self.ledger, self.command)['events'][0]
        self.assertIsNone(event['nativeCompletedAt'])
        self.assertGreater(event['observedAt'], 0)

    def test_file_tampering_epoch_replacement_truncation_symlink_and_hardlink_refuse(self):
        self.begin(); capture.append(self.ledger, 'control', BRAIN, self.event()); self.seal()
        path = capture.path_for(self.ledger, 'control'); original = path.read_bytes()
        for data in (original[:-1], original.replace(b'"sequence":1', b'"sequence":2'),
                     original.replace(b'"exitCode":0', b'"exitCode":1')):
            path.write_bytes(data)
            with self.assertRaises(Refusal): capture.retained(self.ledger, self.command)
        path.write_bytes(original)
        moved = self.root / 'saved'; path.rename(moved); path.symlink_to(moved)
        with self.assertRaises(Refusal): capture.retained(self.ledger, self.command)
        path.unlink(); os.link(moved, path)
        with self.assertRaises(Refusal): capture.retained(self.ledger, self.command)

    def test_owner_authored_clean_flags_cannot_be_added_to_a_marker(self):
        self.begin(); self.seal()
        self.command['notification'][capture.FIELD]['cleanupVerified'] = True
        with self.assertRaises(Refusal): capture.retained(self.ledger, self.command)

    def test_original_fingerprint_binding_or_turn_substitution_refuses(self):
        self.begin(); capture.append(self.ledger, 'control', BRAIN, self.event()); self.seal()
        original = copy.deepcopy(self.command)
        for mutate in (lambda: self.command.update(fingerprint=digest('foreign')),
                       lambda: self.command['notification'].update(hostBindingHash=digest('foreign')),
                       lambda: self.command['notification'].update(nativeTurnId='foreign')):
            mutate()
            with self.assertRaises(Refusal): capture.retained(self.ledger, self.command)
            self.command = copy.deepcopy(original)

    def test_bounds_retain_unknown_and_do_not_rearm_capture(self):
        self.begin()
        with patch.object(capture, 'MAX_EVENTS', 1):
            capture.append(self.ledger, 'control', BRAIN, self.event())
            with self.assertRaises(Refusal): capture.append(self.ledger, 'control', BRAIN, self.event())
        self.seal(failed=True)
        self.assertEqual(capture.retained(self.ledger, self.command)['status'], 'incomplete')

    def test_current_reader_cannot_assume_an_unknown_producer_version(self):
        self.begin(); self.seal()
        with patch.object(capture, 'source_hash', return_value=digest('unknown producer')):
            with self.assertRaises(Refusal): capture.retained(self.ledger, self.command)

    def test_proxy_captures_early_events_during_rpc_and_permissions_without_extra_rpc(self):
        proxy = WakeProxy({})
        rows = []
        proxy._on_effect_event = rows.append
        proxy._awaiting_start = True
        event = self.event()
        with patch.object(ReadProxy, '_line', return_value=event): self.assertEqual(proxy._line(), event)
        self.assertEqual(rows, [event])
        proxy._on_effect_event = lambda _: (_ for _ in ()).throw(OSError('private'))
        with patch.object(ReadProxy, '_line', return_value=event): self.assertEqual(proxy._line(), event)
        self.assertTrue(proxy._effect_capture_error)


class IndependentEffectsTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.CleanupCollectorTest(); self.f.setUp()
        self.registry, self.ledger = self.f.registry, self.f.ledger
        self.wake, self.controls = self.f.wake, self.f.controls

    def tearDown(self): self.f.tearDown()

    def plan(self): return independent.plan(self.registry, self.ledger, self.wake, self.controls)

    def collect(self, request=None):
        return independent.collect(self.registry, self.ledger, self.wake, self.controls,
                                   self.plan() if request is None else request)

    def test_absent_old_capture_does_not_create_files_reduce_gaps_or_write_db(self):
        with contextlib.closing(self.ledger.connect()) as db: before = list(db.iterdump())
        files = set(self.ledger.root.rglob('*'))
        request = self.plan(); self.assertFalse(self.f.reads)
        result = self.collect(request)
        self.assertEqual([row['status'] for row in result['independentEvidence']['originalCaptureCoverage']],
                         ['unavailable'] * 3)
        self.assertEqual(result['independentEvidence']['positiveResultsCorroborated'], 0)
        self.assertEqual(result['primaryCollection']['qualification']['historicalCleanup'], 'unqualified')
        self.assertTrue(all(not value for value in result['boundary'].values()))
        self.assertEqual(files, set(self.ledger.root.rglob('*')))
        self.assertNotIn('PRIVATE', json.dumps(result))
        with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))

    def test_correlation_accepts_exact_positive_result_but_never_claims_cleanup(self):
        primary = self.collect()['primaryCollection']['historicalEvidence']
        effect = primary['native']['effects'][0]
        event = {'kind': 'item_completed', 'turnId': effect['turnId'], 'itemId': effect['id'],
                 'itemType': effect['type'], 'status': effect['status'], 'itemHash': effect['itemHash'],
                 'commandHash': effect['commandHash'], 'cwdHash': effect['cwdHash'], 'exitCode': effect['exitCode'],
                 'observedAt': 1}
        values = [{'commandId': 'original', 'turnId': effect['turnId'],
                   'capture': {'status': 'observed', 'reason': None, 'events': [event]}}]
        result = independent.correlate(primary, values)
        self.assertEqual(result['positiveResultsCorroborated'], 1)
        self.assertFalse(result['completeProcessLifecycleSource'])
        self.assertFalse(result['completeDescendantCleanupSource'])
        self.assertFalse(result['executedEffectDispositionAvailable'])
        self.assertEqual(result['resultEvidence'][0]['historicalCleanup'], 'unknown')
        changed = copy.deepcopy(values); changed[0]['capture']['events'][0]['exitCode'] = 99
        with self.assertRaisesRegex(Refusal, 'conflicts'): independent.correlate(primary, changed)

    def test_real_owned_observer_anchors_before_start_and_imports_exact_result(self):
        # Simulate a future original send in disposable state, not an adapter
        # that backfills an accepted historical command.
        with self.ledger.tx() as db:
            command = next(row for row in self.ledger.all(db, 'commands') if row['kind'] == 'standard_play')
            command['notification'].update(status='sending', hostInspectionTransport='owned_observer_v1')
            command['notification'].pop('nativeThreadObservation')
            self.ledger.put(db, 'commands', command['id'], command)
        brain = command['notification']['brainId']
        wake = AppServerWake(self.wake.binding, self.ledger)
        marker = wake._begin_thread_observation(command['id'], brain)
        self.assertEqual(marker['status'], 'open')
        item = copy.deepcopy(self.f.f.turns[-1]['items'][0])
        capture.append(self.ledger, command['id'], brain, {'method': 'item/completed',
            'params': {'threadId': brain, 'turnId': 'play-turn', 'item': item}})
        wake._finish_thread_observation(command['id'], brain, 'play-turn', 'completed')
        with self.ledger.tx() as db:
            current = self.ledger.get(db, 'commands', command['id'])
            current['notification'].update(status='accepted')
            self.ledger.put(db, 'commands', current['id'], current)
        with contextlib.closing(self.ledger.connect()) as db: before = list(db.iterdump())
        result = self.collect()
        self.assertEqual(result['independentEvidence']['positiveResultsCorroborated'], 1)
        self.assertFalse(result['independentEvidence']['executedEffectDispositionAvailable'])
        self.assertEqual(result['primaryCollection']['qualification']['historicalCleanup'], 'unqualified')
        with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))

    def test_duplicate_foreign_or_changed_capture_scope_refuses_correlation(self):
        primary = self.collect()['primaryCollection']['historicalEvidence']
        effect = primary['native']['effects'][0]
        event = {'kind': 'item_completed', 'turnId': effect['turnId'], 'itemId': effect['id'],
                 'itemType': effect['type'], 'status': effect['status'], 'itemHash': effect['itemHash'],
                 'commandHash': effect['commandHash'], 'cwdHash': effect['cwdHash'], 'exitCode': effect['exitCode'],
                 'observedAt': 1}
        value = {'commandId': 'original', 'turnId': effect['turnId'],
                 'capture': {'status': 'observed', 'reason': None, 'events': [event, event]}}
        with self.assertRaises(Refusal): independent.correlate(primary, [value])
        value['capture']['events'] = [event]
        with self.assertRaises(Refusal): independent.correlate(primary, [value, value])
        value['turnId'] = 'foreign'
        with self.assertRaises(Refusal): independent.correlate(primary, [value])

    def test_extra_capture_effect_is_retained_as_unknown_not_dropped(self):
        primary = self.collect()['primaryCollection']['historicalEvidence']
        values = [{'commandId': 'original', 'turnId': 'play-turn', 'capture': {
            'status': 'observed', 'reason': None, 'events': [{'kind': 'item_completed', 'turnId': 'play-turn',
                'itemId': 'extra', 'itemType': 'unsupported', 'itemHash': digest('extra'), 'observedAt': 1}]}}]
        result = independent.correlate(primary, values)
        self.assertEqual(result['positiveResultsCorroborated'], 0)
        self.assertTrue(any(row['reason'] == 'captured_effect_missing_from_persisted_history'
                            for row in result['missingIndependentEvidence']))

    def test_scope_fields_and_caller_attestations_are_refused_before_native_io(self):
        for name, value in (('path', '/untrusted'), ('cleanupVerified', True), ('captureSourceHash', digest('foreign'))):
            request = self.plan(); request[name] = value
            with self.assertRaises(Refusal): self.collect(request)
        self.assertFalse(self.f.reads)

    def test_capture_drift_before_collection_refuses_without_loading_or_execution(self):
        request = self.plan(); request['originalCaptureHashes'] = {}
        with self.assertRaises(Refusal): self.collect(request)
        self.assertFalse(self.f.reads)

    def test_unloaded_current_brain_is_unknown_and_not_resumed(self):
        self.f.f.metadata.thread['status']['type'] = 'notLoaded'
        result = self.collect()
        self.assertEqual(result['primaryCollection']['currentObservation']['tracker']['coverage'], 'unknown')
        self.assertIsNone(result['primaryCollection']['currentObservation']['tracker']['rows'])
        self.assertTrue(set(method for method, _ in self.f.reads) <= {
            'project/read', 'thread/read', 'thread/turns/list', 'thread/items/list'})

    def test_plan_usage_expiry_and_ownership_race_invalidates_scope(self):
        request = self.plan()
        self.f.f.f.mutate(lambda meta: meta['standardRun'].update(usageHighWater=987))
        with self.assertRaises(Refusal): self.collect(request)
        self.assertFalse(self.f.reads)

    def test_private_report_bound_refuses_whole_without_discarding_evidence(self):
        with patch.object(independent.cleanup, 'MAX_REPORT_BYTES', 200), self.assertRaises(Refusal): self.collect()

    def test_cli_closed_plan_and_collection_have_no_controller_or_confirmation(self):
        from orchestrator.cli import main
        path = self.ledger.root / 'independent-plan.json'
        base = ['orchestrator', '--platform', str(self.registry.root), '--workspace', self.ledger.workspace_id]
        with patch('orchestrator.app_server_wake.load_binding', return_value=self.wake.binding):
            output = io.StringIO()
            with patch.object(sys, 'argv', base + ['historical-independent-plan', 'ignored']), contextlib.redirect_stdout(output): main()
            self.assertFalse(self.f.reads)
            path.write_text(output.getvalue()); path.chmod(0o600)
            output = io.StringIO()
            with patch.object(sys, 'argv', base + ['historical-independent-collect', 'ignored', str(path)]), contextlib.redirect_stdout(output): main()
            self.assertEqual(json.loads(output.getvalue())['kind'], independent.KIND)


if __name__ == '__main__': unittest.main()
