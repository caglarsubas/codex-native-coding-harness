"""Disposable canceled-readiness disposition; never touches a live native host."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sqlite3
import time
import threading
import unittest
import uuid
from unittest.mock import patch

from orchestrator import core, projects, standard, standard_preplay
from orchestrator import readiness_disposition as disposition
from orchestrator.app_server_wake import NATIVE_APPROVAL_POLICY
from orchestrator.core import Refusal, canonical, digest
from orchestrator.notification import BrainNotifier
from orchestrator.partial_admission import database_proof
import test_standard_preplay as fixtures


class ReadinessDispositionTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PreplayTest('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.ledger, self.registry = self.f.ledger, self.f.registry
        self.cid, self.brain = self.f.cid, self.f.brain
        self.turn, self.project, self.catalog = (str(uuid.uuid4()) for _ in range(3))
        self.binding = {'endpoint': {'fixture': 'unreachable-no-connection'}, 'brains': {self.brain: {
            'workspaceId': 'v3', 'cwd': str(self.f.repo), 'projectId': self.project,
            'catalogProjectId': self.catalog, 'nativePolicy': dict(NATIVE_APPROVAL_POLICY)}}}
        self.binding_file = self.f.root/'original-binding.json'
        self.binding_file.write_text(canonical(self.binding)); self.binding_file.chmod(0o600)
        projects.record(self.registry, {'schemaVersion': 2, 'projects': [{
            'projectId': self.catalog, 'projectKind': 'local', 'hostId': 'local', 'label': 'Disposable',
            'path': str(self.f.repo), 'isGitRepository': True}]}, time.time())
        projects.bind(self.registry, 'v3', 'local', self.catalog, projects.catalog(self.registry)['hash'])
        now = time.time()-10
        with self.ledger.tx() as db:
            command = self.ledger.get(db, 'commands', self.cid)
            command['notification'] = {
                'status': 'accepted', 'nativeDelivery': 'owned_turn_start', 'brainId': self.brain,
                'wakeId': digest({'commandId': self.cid}), 'attemptedAt': now-10, 'finishedAt': now-9,
                'nativeTurnId': self.turn, 'nativeTurnStatus': 'interrupted',
                'nativeApprovals': [{'turnId': self.turn, 'requestHash': 'f'*64, 'decision': 'cancel', 'status': 'resolved',
                                     'claimedAt': now-3, 'observedAt': now-2}],
                'nativePermissionObservation': {'version': 1, 'turnId': self.turn, 'requestHash': 'f'*64,
                                                'reason': 'native_resolved', 'endedAt': now-1},
                'nativeResumeProfile': {'version': 1, 'brainId': self.brain, 'commandId': self.cid,
                                        'nativeTurnId': self.turn, 'requested': dict(NATIVE_APPROVAL_POLICY),
                                        'resumeAcknowledged': True, 'bindingHash': digest(self.binding)},
                'nativeThreadObservation': {'version': 1, 'rootThreadId': self.brain, 'nativeTurnId': self.turn,
                    'streamStatus': 'closed', 'monitoringEndedAt': now, 'events': [], 'complete': False,
                    'gaps': ['owned_stream_not_exhaustive']}}
            self.ledger.put(db, 'commands', self.cid, command)
            self.original = copy.deepcopy(command)
        self.old = core.Ledger(self.f.root/'preserved-old')
        with self.old.tx() as db:
            meta = self.old.get(db, 'meta', 1)
            meta['standardRun'] = {'status': 'paused', 'brainObservedTokens': 1049625,
                                   'usageHighWater': 1049625, 'expiresAt': 1, 'gaps': ['unknown']}
            self.old.put(db, 'meta', 1, meta)
        self.claim_files = [self.f.root/'claim-one', self.f.root/'claim-two']
        for path in self.claim_files: path.write_bytes(b'preserved-issued-claim'); path.chmod(0o600)
        self.old_proof = database_proof(self.old.db)
        self.binding_bytes = self.binding_file.read_bytes()
        self.registry_proof = database_proof(self.registry.db)
        self.target_proof = database_proof(self.ledger.db)

    def prepare(self):
        return disposition.prepare(self.registry, self.ledger, self.binding_file, self.cid)

    def backup(self, p):
        path = self.f.root/'verified-backup'
        disposition.create_backup(self.registry, self.ledger, p['request'], path, writers_stopped=True)
        return path

    def confirm(self, p=None, **kw):
        p = p or self.prepare()
        return disposition.confirm(self.registry, self.ledger, p['request'], p['reviewHash'], **kw)

    def apply(self):
        p = self.prepare()
        return p, self.confirm(p, writers_stopped=True, backup_root=self.backup(p))

    def assert_preserved(self):
        self.assertEqual(database_proof(self.old.db), self.old_proof)
        self.assertEqual(database_proof(self.registry.db), self.registry_proof)
        self.assertEqual(self.binding_file.read_bytes(), self.binding_bytes)
        self.assertTrue(all(p.read_bytes() == b'preserved-issued-claim' for p in self.claim_files))
        with standard.read_db(self.ledger.db) as db:
            self.assertEqual(self.ledger.get(db, 'commands', self.cid), self.original)
            meta = self.ledger.get(db, 'meta', 1)
            self.assertIsNone(meta.get('standardRun')); self.assertIsNone(meta.get('controller'))
            self.assertTrue(meta['paused']); self.assertFalse(meta.get('standardCatalog'))

    def mutate(self, fn):
        with self.ledger.tx() as db:
            command = self.ledger.get(db, 'commands', self.cid)
            fn(command); self.ledger.put(db, 'commands', self.cid, command)

    def test_preview_is_read_only_scope_bound_and_has_no_timer_or_native_calls(self):
        before = set(self.ledger.root.iterdir())
        p = self.prepare()
        self.assertEqual(p['validUntil'], 'scope_changes')
        with patch('time.time', return_value=time.time()+10**8): self.assertEqual(self.prepare(), p)
        self.assertEqual(set(self.ledger.root.iterdir()), before)
        self.assertEqual(database_proof(self.ledger.db), self.target_proof)
        self.assertEqual(self.f.sent, []); self.assert_preserved()

    def test_exact_local_disposition_preserves_request_meta_history_and_unknowns(self):
        before = self.ledger.snapshot()['meta']
        p, result = self.apply()
        self.assertEqual(result['status'], 'disposed_unqualified')
        self.assertEqual(result['brainReceipt'], 'missing'); self.assertEqual(result['originalStatus'], 'queued')
        self.assertEqual(result['boundary']['terminalSafety'], 'unknown')
        self.assertFalse(result['boundary']['playAuthorized']); self.assertEqual(disposition.status(self.ledger), result)
        self.assertEqual(self.ledger.snapshot()['meta'], before)
        self.assertEqual(self.ledger.snapshot()['workflow']['pendingRequests'], 0)
        from orchestrator.decisions import inbox
        self.assertEqual(inbox(self.ledger.snapshot())['commands'], [])
        self.assertEqual(standard.read(self.ledger)['catalogRefresh']['disposition'], result)
        self.assert_preserved()

    def test_lost_confirmation_reply_reads_same_record_without_reapplying(self):
        p, result = self.apply()
        proof = database_proof(self.ledger.db)
        with patch('time.time', return_value=time.time()+10**8):
            self.assertEqual(self.confirm(p), result)
        self.assertEqual(database_proof(self.ledger.db), proof); self.assert_preserved()

    def test_missing_exact_review_quiescence_or_backup_refuses_before_claim(self):
        p = self.prepare()
        for kw in ({}, {'writers_stopped': True}):
            with self.assertRaises(Refusal): self.confirm(p, **kw)
        with self.assertRaises(Refusal):
            disposition.confirm(self.registry, self.ledger, p['request'], 'a'*64)
        self.assertFalse((self.ledger.root/disposition.FENCE).exists()); self.assert_preserved()

    def test_changed_backup_or_binding_epoch_refuses(self):
        p = self.prepare(); backup = self.backup(p)
        (backup/'binding.json').write_text('{}')
        with self.assertRaises(Refusal): self.confirm(p, writers_stopped=True, backup_root=backup)
        self.binding_file.touch()
        with self.assertRaises(Refusal): self.confirm(p, writers_stopped=True, backup_root=backup)
        self.assertFalse((self.ledger.root/disposition.FENCE).exists())

    def test_pause_race_invalidates_review_before_claim(self):
        p = self.prepare(); backup = self.backup(p)
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1); meta['brainControl'] = {'desired': 'stopped', 'phase': 'stop_requested'}
            self.ledger.put(db, 'meta', 1, meta)
        with self.assertRaises(Refusal): self.confirm(p, writers_stopped=True, backup_root=backup)
        self.assertFalse((self.ledger.root/disposition.FENCE).exists())

    def test_unknown_delivery_open_observer_pending_permission_and_other_decisions_refuse(self):
        changes = [lambda c: c['notification'].update(status='uncertain'),
                   lambda c: c['notification'].update(nativeTurnStatus='unconfirmed'),
                   lambda c: c['notification']['nativeThreadObservation'].update(streamStatus='open'),
                   lambda c: c['notification']['nativeApprovals'][0].update(status='sent'),
                   lambda c: c['notification']['nativeApprovals'][0].update(decision='accept'),
                   lambda c: c['notification']['nativePermissionObservation'].update(reason='connection_ended'),
                   lambda c: c['notification']['nativeResumeProfile'].update(resumeAcknowledged=False),
                   lambda c: c['notification']['nativeThreadObservation'].update(events=[{'effect': 'unknown'}]),
                   lambda c: c.update(catalogReceipt={'unknown': True}),
                   lambda c: c['notification'].update(preplayCatalog={'version': 1}),
                   lambda c: c['notification']['nativeApprovals'][0].update(turnId=str(uuid.uuid4())),
                   lambda c: c['notification']['nativeThreadObservation'].update(monitoringEndedAt=True)]
        for change in changes:
            with self.subTest(change=change):
                self.mutate(change)
                with self.assertRaises((Refusal, ValueError)): self.prepare()
                with self.ledger.tx() as db: self.ledger.put(db, 'commands', self.cid, self.original)

    def test_other_pending_command_or_worker_prevents_disposition(self):
        with self.ledger.tx() as db:
            self.ledger.put(db, 'commands', 'other', {**self.original, 'id': 'other'})
        with self.assertRaises(Refusal): self.prepare()

    def test_pending_run_controller_runner_and_strict_schema_refuse(self):
        for key, value in (('standardRun', {'status': 'paused'}), ('controller', {'owner': 'unknown'}),
                           ('runner', {'unknown': True}), ('schemaVersion', 3)):
            with self.subTest(key=key):
                before = self.ledger.snapshot()['meta']
                with self.ledger.tx() as db: self.ledger.put(db, 'meta', 1, {**before, key: value})
                with self.assertRaises(Refusal): self.prepare()
                with self.ledger.tx() as db: self.ledger.put(db, 'meta', 1, before)

    def test_partial_admission_successor_and_quarantine_markers_never_become_free_scope(self):
        for name in ('standard-successor.json', 'standard-forward-continuation.json',
                     'standard-partial-admission-disposition.json', 'standard-quarantine.json',
                     'standard-controller.json'):
            with self.subTest(name=name):
                path = self.ledger.root/name
                path.write_text('{}'); path.chmod(0o600)
                try:
                    with self.assertRaises(Refusal): self.prepare()
                    self.assertEqual(path.read_text(), '{}')
                finally: path.unlink()  # Disposable fixture only; never a live fence.

    def test_wrong_project_policy_catalog_or_binding_refuses_without_endpoint_access(self):
        for key, value in (('projectId', str(uuid.uuid4())), ('catalogProjectId', str(uuid.uuid4())),
                           ('nativePolicy', {'sandbox': 'danger-full-access', 'approvalPolicy': 'never'})):
            with self.subTest(key=key):
                altered = copy.deepcopy(self.binding); altered['brains'][self.brain][key] = value
                self.binding_file.write_text(canonical(altered))
                with self.assertRaises(Refusal): self.prepare()
                self.binding_file.write_bytes(self.binding_bytes)

    def test_original_id_can_never_be_reused_receipted_rehanded_or_notified(self):
        self.apply()
        with self.assertRaises(Refusal):
            standard.request_catalog_refresh(self.ledger, {'id': self.cid, 'contextHash': self.original['payload']['contextHash']})
        with self.assertRaises(Refusal):
            with self.ledger.tx() as db:
                standard.catalog_in(self.ledger, db, self.ledger.get(db, 'meta', 1), {
                    'operation': 'catalog_error', 'requestId': self.cid, 'code': 'late', 'detail': 'Not a receipt', 'retryable': False})
        with self.assertRaises(Refusal):
            with self.ledger.tx() as db: standard_preplay.prepare(self.ledger, db, self.original, self.binding)
        with patch.object(BrainNotifier, 'status', side_effect=AssertionError('No native delivery permitted')):
            self.assertEqual(BrainNotifier(self.ledger).notify(self.cid), self.original)
        self.assert_preserved()

    def test_original_command_mutation_rolls_back_and_record_deletion_fails_closed(self):
        self.apply()
        with self.assertRaises(Refusal): self.mutate(lambda c: c.update(status='completed'))
        with self.assertRaises(Refusal):
            with self.ledger.tx() as db: db.execute('DELETE FROM snapshots WHERE kind=?', (disposition.KIND,))
        self.assert_preserved()

    def test_interrupted_after_claim_never_reapplies_or_implicitly_unfences(self):
        p = self.prepare(); backup = self.backup(p)
        with patch.object(disposition, 'retained_in', side_effect=OSError('Fixture interrupted commit')):
            with self.assertRaises(OSError): self.confirm(p, writers_stopped=True, backup_root=backup)
        self.assertTrue((self.ledger.root/disposition.FENCE).exists())
        self.assertEqual(disposition.status(self.ledger)['status'], 'incomplete_or_changed')
        with self.assertRaises(Refusal): self.confirm(p, writers_stopped=True, backup_root=backup)
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass
        with standard.read_db(self.ledger.db) as db:
            self.assertEqual(self.ledger.get(db, 'commands', self.cid), self.original)

    def test_missing_or_corrupt_claim_cannot_downgrade_into_ordinary_writes(self):
        self.apply()
        marker = self.ledger.root/disposition.FENCE
        marker.rename(marker.with_suffix('.preserved'))
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass
        self.assertEqual(disposition.status(self.ledger)['status'], 'incomplete_or_changed')

    def test_new_request_requires_explicit_distinct_id_and_genuine_future_receipt(self):
        self.apply()
        projected = standard.read(self.ledger)
        self.assertFalse(projected['available']); self.assertTrue(projected['catalogRequired'])
        new = standard.request_catalog_refresh(self.ledger, {'id': str(uuid.uuid4()), 'contextHash': projected['contextHash']})
        self.assertNotEqual(new['id'], self.cid); self.assertNotIn('notification', new)
        self.assertFalse(standard.read(self.ledger)['available'])
        with self.ledger.tx() as db:
            state = self.ledger.get(db, 'meta', 1)
            # A fixture-only independent brain receipt, not an owner-written catalog.
            standard.catalog_in(self.ledger, db, state, {'operation': 'catalog', 'requestId': new['id'],
                'models': [{'model': 'fixture-observed', 'efforts': ['high']}], 'source': 'Disposable actual schema'})
        self.assertTrue(standard.read(self.ledger)['available'])
        with standard.read_db(self.ledger.db) as db: self.assertEqual(self.ledger.get(db, 'commands', self.cid), self.original)

    def test_future_prospective_receipt_remains_checkout_local_and_never_backfills_original(self):
        self.apply()
        state = standard.read(self.ledger)
        new = standard.request_catalog_refresh(self.ledger, {'id': str(uuid.uuid4()), 'contextHash': state['contextHash']})
        with self.ledger.tx() as db: result = standard_preplay.prepare(self.ledger, db, new, self.binding)
        self.assertEqual(result['transport'], 'preplay_catalog_observer_v1')
        self.assertFalse(standard_preplay.path(self.ledger.root, self.cid, 'handoff').exists())
        self.assert_preserved()

    def test_plain_catalog_without_a_distinct_future_command_cannot_enable_play(self):
        self.apply()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1)
            standard.catalog_in(self.ledger, db, meta, {'operation': 'catalog',
                'models': [{'model': 'fixture-only', 'efforts': ['high']}], 'source': 'Disposable schema'})
        self.assertFalse(standard.read(self.ledger)['available'])
        controls = standard.Controls()
        p = controls.preview(self.ledger, {'operation': 'play', 'contextHash': standard.read(self.ledger)['contextHash'],
            'brainAllowance': 10000, 'durationHours': 8}, 'fixture')
        with self.assertRaises(Refusal): controls.confirm(self.registry, self.ledger, {**p, 'confirmed': True}, 'fixture')

    def test_two_confirmations_can_commit_only_one_disposition(self):
        p = self.prepare(); backup = self.backup(p)
        barrier = threading.Barrier(2); results, errors = [], []
        def submit():
            barrier.wait()
            try: results.append(self.confirm(p, writers_stopped=True, backup_root=backup))
            except (Refusal, OSError): errors.append('original already claimed')
        threads = [threading.Thread(target=submit) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(10); self.assertFalse(t.is_alive())
        self.assertEqual(len(results)+len(errors), 2); self.assertTrue(results)
        self.assertTrue(all(value == results[0] for value in results))
        with standard.read_db(self.ledger.db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM snapshots WHERE kind=?', (disposition.KIND,)).fetchone()[0], 1)
        self.assert_preserved()

    def test_foreign_workspace_or_different_exact_review_cannot_read_as_confirmation(self):
        p, _ = self.apply()
        altered = copy.deepcopy(p['request']); altered['missionHash'] = 'a'*64
        with self.assertRaises(Refusal):
            disposition.confirm(self.registry, self.ledger, altered, digest(altered))
        original = self.ledger.workspace_id; self.ledger.workspace_id = 'foreign'
        try:
            with self.assertRaises(Refusal): self.confirm(p)
        finally: self.ledger.workspace_id = original

    def test_snapshot_without_claim_refuses_even_a_new_readiness_request(self):
        self.apply()
        (self.ledger.root/disposition.FENCE).rename(self.ledger.root/'preserved-claim.json')
        with self.assertRaises(Refusal):
            standard.request_catalog_refresh(self.ledger, {'id': str(uuid.uuid4()), 'contextHash': 'changed'})

    def test_status_does_not_initialize_database_or_repair_partial_claim(self):
        from orchestrator.standard_quarantine import exclusive
        exclusive(self.ledger.root/disposition.FENCE, {'kind': disposition.KIND, 'reviewHash': 'a'*64})
        before = database_proof(self.ledger.db)
        marker = (self.ledger.root/disposition.FENCE).read_bytes()
        self.assertEqual(disposition.status(self.ledger)['status'], 'incomplete_or_changed')
        self.assertEqual(database_proof(self.ledger.db), before)
        self.assertEqual((self.ledger.root/disposition.FENCE).read_bytes(), marker)

    def test_no_brain_reload_native_rpc_or_process_launch_in_complete_adapter(self):
        with (patch('subprocess.run', side_effect=AssertionError('No process launch')),
              patch('socket.socket', side_effect=AssertionError('No native connection'))):
            p, result = self.apply()
            self.assertEqual(self.confirm(p), result)
        self.assert_preserved()

    def test_cli_routes_before_registry_or_ledger_writer_construction(self):
        from orchestrator.cli import main
        argv = ['orchestrator', '--platform', str(self.registry.root), '--workspace', 'v3', 'readiness-disposition-status']
        with (patch('sys.argv', argv), patch('orchestrator.workspaces.Registry', side_effect=AssertionError('Writer constructor')),
              patch('orchestrator.core.Ledger.__init__', side_effect=AssertionError('Ledger constructor')),
              contextlib.redirect_stdout(io.StringIO()) as output):
            main()
        self.assertEqual(json.loads(output.getvalue())['status'], 'not_recorded')
