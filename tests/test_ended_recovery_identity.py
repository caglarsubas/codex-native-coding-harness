import contextlib
import copy
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from orchestrator import workspace_identity_recovery as device, historical_effects as history
from orchestrator import ended_recovery_record as record, standard
from orchestrator.core import Refusal, canonical, digest
from orchestrator.notification import BrainNotifier
from orchestrator.projects import record as catalog_record, bind
import test_historical_effects as fixture


class EndedRecoveryIdentityTest(unittest.TestCase):
    """Disposable device drift, never live owner confirmation/native evidence."""

    def setUp(self):
        self.f = fixture.HistoricalEffectsTest(); self.f.setUp()
        self.ledger, self.registry = self.f.ledger, self.f.registry
        self.workspace = self.ledger.workspace_id
        self.root = self.ledger.root.parent
        self.binding = self.root / 'original-binding.json'
        self.binding.write_text(canonical(self.f.host.binding)); self.binding.chmod(0o600)
        saved = catalog_record(self.registry, {'schemaVersion': 2, 'projects': [{
            'projectKind': 'local', 'projectId': 'catalog-project', 'hostId': 'local',
            'label': 'Fixture', 'path': self.f.metadata.thread['cwd'], 'isGitRepository': True}]}, time.time())
        bind(self.registry, self.workspace, 'local', 'catalog-project', saved['hash'])
        self.reference = self.root / 'earlier-reference.sqlite3'
        os.close(os.open(self.reference, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        self.save_reference()
        self.drift()
        self.f.metadata.calls.clear()

    def tearDown(self):
        self.f.tearDown()

    def save_reference(self):
        # Fixture-only synthesis of a separately retained matching backup.
        with contextlib.closing(sqlite3.connect(self.ledger.db)) as source, \
             contextlib.closing(sqlite3.connect(self.reference)) as target:
            source.backup(target)

    def drift(self):
        old = [self.ledger.db.stat().st_dev - 1, self.ledger.db.stat().st_ino]
        with self.registry.tx() as db:
            row = json.loads(db.execute('SELECT data FROM workspaces WHERE id=?', (self.workspace,)).fetchone()[0])
            row['databaseIdentity'] = old
            db.execute('UPDATE workspaces SET data=? WHERE id=?', (canonical(row), self.workspace))
            binding = json.loads(db.execute('SELECT data FROM project_bindings WHERE workspace=?', (self.workspace,)).fetchone()[0])
            binding['databaseIdentity'] = old
            db.execute('UPDATE project_bindings SET data=? WHERE workspace=?', (canonical(binding), self.workspace))

    def contents(self, path):
        with device.read_database(path) as db:
            return device.checked_fingerprint(db)

    def preview(self):
        return device.preview(self.registry, self.workspace, self.reference, preserve_ended_recovery=self.binding)

    def apply(self, proposal):
        return device.confirm(self.registry, self.workspace, proposal, proposal['documentHash'],
                              confirmed=True, writers_stopped=True)

    def mutate(self, callback):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1); callback(meta); self.ledger.put(db, 'meta', 1, meta)
        self.save_reference()

    def command_change(self, ident, callback):
        with self.ledger.tx() as db:
            command = self.ledger.get(db, 'commands', ident)
            callback(command); self.ledger.put(db, 'commands', ident, command)
        self.save_reference()

    def test_preview_is_local_only_and_default_modes_remain_fenced(self):
        before = self.contents(self.ledger.db), self.contents(self.registry.db)
        with self.assertRaises(Refusal): device.preview(self.registry, self.workspace, self.reference)
        with self.assertRaises(Refusal): device.preview(self.registry, self.workspace, self.reference, preserve_pending_play=True)
        with patch('subprocess.Popen', side_effect=AssertionError('No native proxy')), \
             patch('subprocess.run', side_effect=AssertionError('No process or native call')):
            proposal = self.preview()
        self.assertEqual(proposal['document']['kind'], device.ENDED_RECOVERY_KIND)
        proof = proposal['document']['endedRecovery']
        self.assertEqual(proof['nativeEvidence'], 'retained_only')
        self.assertEqual(proof['currentTerminalCoverage'], 'unknown')
        self.assertEqual(proof['historicalTerminalCoverage'], 'unknown')
        self.assertEqual(proof['effectOutcome'], 'unknown')
        self.assertEqual(set(proof['originalCommands']), {'play', 'pause', 'recovery'})
        self.assertFalse(any(proposal['document']['boundary'].values()))
        self.assertEqual(before, (self.contents(self.ledger.db), self.contents(self.registry.db)))
        self.assertFalse(self.f.metadata.calls)

    def test_confirmation_changes_only_registry_pins_and_preserves_complete_ledger(self):
        old = record.saved_state(self.ledger)
        before = self.contents(self.ledger.db), self.contents(self.registry.db)
        original_binding = self.binding.read_bytes()
        proposal = self.preview()
        with patch('subprocess.Popen', side_effect=AssertionError('No native proxy')), \
             patch('subprocess.run', side_effect=AssertionError('No native call')):
            result = self.apply(proposal)
        self.assertEqual(self.registry.root_for(self.workspace), self.ledger.root)
        self.assertEqual(self.contents(self.ledger.db), before[0])
        self.assertEqual(record.saved_state(self.ledger), old)
        self.assertEqual(self.binding.read_bytes(), original_binding)
        self.assertFalse(any(result['boundary'].values()))
        retained = self.registry.root / 'backups' / result['backupId']
        self.assertEqual(self.contents(retained / 'ledger.sqlite3'), before[0])
        self.assertEqual(self.contents(retained / 'platform.sqlite3'), before[1])
        self.assertEqual(retained.stat().st_mode & 0o777, 0o700)
        self.assertEqual((retained / 'ledger.sqlite3').stat().st_mode & 0o777, 0o600)
        self.assertEqual(old['meta']['standardRun']['status'], 'stopping')
        self.assertFalse(old['meta']['pilotPassed'])

    def test_each_consumed_notification_still_cannot_be_resent(self):
        self.apply(self.preview())
        before = self.contents(self.ledger.db)
        notifier = BrainNotifier(self.ledger)
        for command in history.eligible(record.saved_state(self.ledger)):
            with patch.object(notifier, 'status', side_effect=AssertionError('No new native send')):
                self.assertEqual(notifier.notify(command['id'])['notification'], command['notification'])
        self.assertEqual(self.contents(self.ledger.db), before)
        self.assertFalse(history.close_available(self.ledger, record.saved_state(self.ledger))['available'])
        self.assertFalse(standard.read(self.ledger)['available'])

    def test_exact_owner_hash_and_stopped_writers_required(self):
        proposal = self.preview()
        for confirmed, stopped, hashed in ((False, True, proposal['documentHash']),
                                          (True, False, proposal['documentHash']), (True, True, '0' * 64)):
            with self.assertRaises(Refusal):
                device.confirm(self.registry, self.workspace, proposal, hashed,
                               confirmed=confirmed, writers_stopped=stopped)
        for kind in (device.KIND, device.PENDING_PLAY_KIND):
            altered = copy.deepcopy(proposal); altered['document']['kind'] = kind
            altered['documentHash'] = digest(altered['document'])
            with self.assertRaises(Refusal): self.apply(altered)

    def test_other_recovery_modes_cannot_be_combined_or_inferred(self):
        for value in (True, False, {}, 1):
            with self.assertRaises(Refusal):
                device.preview(self.registry, self.workspace, self.reference, preserve_ended_recovery=value)
        with self.assertRaises(Refusal):
            device.preview(self.registry, self.workspace, self.reference, preserve_pending_play=True,
                           preserve_ended_recovery=self.binding)

    def test_json_round_trip_and_old_review_never_repins_another_device(self):
        proposal = json.loads(canonical(self.preview()))
        result = self.apply(proposal)
        self.drift()
        before = self.contents(self.registry.db), self.contents(self.ledger.db)
        self.assertEqual(self.apply(proposal), result)
        self.assertEqual(before, (self.contents(self.registry.db), self.contents(self.ledger.db)))
        with self.assertRaises(Refusal): self.registry.root_for(self.workspace)
        self.assertEqual(len(list((self.registry.root / 'backups').glob('device-recovery-*'))), 1)

    def test_delayed_review_does_not_extend_expiry_or_renew_native_observations(self):
        proposal = self.preview()
        before = self.contents(self.ledger.db)
        with patch.object(device.time, 'time', return_value=time.time() + 86400): self.apply(proposal)
        self.assertEqual(self.contents(self.ledger.db), before)

    def test_usage_gap_expiry_and_revision_changes_invalidate_review(self):
        for change in (lambda m:m.update(revision=m['revision']+1),
                       lambda m:m['standardRun'].update(usageHighWater=999999),
                       lambda m:m['standardRun'].update(brainUsageCoverage='not_observed'),
                       lambda m:m['standardRun'].update(expiresAt=1)):
            original = record.saved_state(self.ledger)['meta']
            proposal = self.preview(); self.mutate(change)
            with self.assertRaises(Refusal): self.apply(proposal)
            with self.ledger.tx() as db: self.ledger.put(db, 'meta', 1, original)
            self.save_reference()

    def test_original_command_or_binding_epoch_changes_invalidate_review(self):
        proposal = self.preview()
        self.binding.write_text(self.binding.read_text())  # Same bytes, different epoch.
        with self.assertRaises(Refusal): self.apply(proposal)
        proposal = self.preview()
        recovery = history.eligible(record.saved_state(self.ledger))[1]
        self.command_change(recovery['id'], lambda c:c.update(result='Changed retained result'))
        with self.assertRaises(Refusal): self.apply(proposal)

    def test_unknown_open_received_or_approved_recovery_refuses(self):
        ident = history.eligible(record.saved_state(self.ledger))[1]['id']
        with contextlib.closing(self.ledger.connect()) as db: original = self.ledger.get(db, 'commands', ident)
        for change in (lambda c:c.update(receivedAt=1),
                       lambda c:c.update(checkpointHash='x'),
                       lambda c:c['notification'].update(nativeTurnStatus='unconfirmed'),
                       lambda c:c['notification']['nativeThreadObservation'].update(streamStatus='open'),
                       lambda c:c['notification'].update(nativeApprovals=False),
                       lambda c:c['notification'].update(nativeApprovals=[{'status':'uncertain'}]),
                       lambda c:c['notification']['nativeThreadObservation'].update(events=[{'threadId':'child'}])):
            self.command_change(ident, change)
            with self.assertRaises(Refusal): self.preview()
            with self.ledger.tx() as db: self.ledger.put(db, 'commands', ident, original)
            self.save_reference()

    def test_ownership_other_pending_control_and_brain_stop_remain_fenced(self):
        original = record.saved_state(self.ledger)['meta']
        for change in (lambda m:m.update(controller={'owner':'foreign'}),
                       lambda m:m.update(runner={'workerId':'owned'}),
                       lambda m:m['standardRun'].update(tasks=[{'status':'creating'}]),
                       lambda m:m['standardRun'].update(tasks={}),
                       lambda m:m['standardRun'].update(merges=[{'status':'uncertain'}]),
                       lambda m:m['standardRun'].update(merges={}),
                       lambda m:m.update(brainControl={'desired':'stopped'}),
                       lambda m:m.update(admissionBinding={})):
            self.mutate(change)
            with self.assertRaises(Refusal): self.preview()
            with self.ledger.tx() as db: self.ledger.put(db, 'meta', 1, original)
            self.save_reference()
        with self.ledger.tx() as db:
            self.ledger.put(db, 'commands', 'extra', {'id':'extra', 'kind':'reconcile', 'status':'queued'})
        self.save_reference()
        with self.assertRaises(Refusal): self.preview()

    def test_strict_profile_private_controller_and_admission_fences_refuse(self):
        with self.ledger.tx() as db:
            original = self.ledger.get(db, 'repos', 'a')
            changed = {**original, 'policyProfile':'harness'}
            self.ledger.put(db, 'repos', 'a', changed)
        self.save_reference()
        with self.assertRaises(Refusal): self.preview()
        with self.ledger.tx() as db: self.ledger.put(db, 'repos', 'a', original)
        self.save_reference()
        for name in ('standard-controller.json', 'admission-fence.json'):
            path = self.ledger.root / name; path.touch(mode=0o600)
            with self.assertRaises(Refusal): self.preview()
            path.unlink()  # Disposable fixture only.

    def test_corrupt_historical_receipt_cannot_authorize_another_device_repair(self):
        proposal = self.preview(); self.apply(proposal)
        with self.registry.tx() as db:
            value = json.loads(db.execute('SELECT data FROM workspaces WHERE id=?', (self.workspace,)).fetchone()[0])
            value['identityRecoveries'][-1]['document']['endedRecovery']['effectOutcome'] = 'safe'
            db.execute('UPDATE workspaces SET data=? WHERE id=?', (canonical(value), self.workspace))
        with self.assertRaisesRegex(Refusal, 'history is invalid'): self.apply(proposal)

    def test_foreign_project_catalog_changes_and_private_binding_epoch_are_review_pins(self):
        proposal = self.preview()
        with self.registry.tx() as db:
            db.execute('UPDATE workspaces SET name=? WHERE id=?', ('Renamed', self.workspace))
        with self.assertRaisesRegex(Refusal, 'scope or evidence changed'): self.apply(proposal)

    def test_unknown_native_profile_and_missing_explicit_dual_id_are_not_substituted(self):
        saved = self.binding.read_text()
        binding = json.loads(saved)
        del binding['brains'][self.f.brain]['catalogProjectId']
        self.binding.write_text(canonical(binding))
        with self.assertRaises(Refusal): self.preview()
        binding = json.loads(saved)
        binding['brains'][self.f.brain]['nativePolicy']['approvalPolicy'] = 'never'
        self.binding.write_text(canonical(binding))
        with self.assertRaises(Refusal): self.preview()

    def test_both_project_ids_original_binding_and_catalog_are_exact(self):
        saved = self.binding.read_text()
        for key, value in (('projectId', 'foreign'), ('catalogProjectId', 'foreign'),
                           ('workspaceId', 'foreign'), ('cwd', str(self.root))):
            binding = json.loads(saved); binding['brains'][self.f.brain][key] = value
            self.binding.write_text(canonical(binding))
            with self.assertRaises(Refusal): self.preview()
        self.binding.write_text(saved)
        with self.registry.tx() as db:
            data = json.loads(db.execute('SELECT data FROM project_bindings').fetchone()[0])
            data['locationHash'] = 'foreign'
            db.execute('UPDATE project_bindings SET data=?', (canonical(data),))
        with self.assertRaises(Refusal): self.preview()

    def test_private_binding_symlink_hardlink_duplicate_and_size_guards(self):
        saved = self.binding.read_bytes()
        self.binding.chmod(0o644)
        with self.assertRaises(Refusal): self.preview()
        self.binding.chmod(0o600)
        alias = self.root / 'alias.json'; alias.symlink_to(self.binding)
        with self.assertRaises(Refusal):
            device.preview(self.registry, self.workspace, self.reference, preserve_ended_recovery=alias)
        alias.unlink(); alias.hardlink_to(self.binding)
        with self.assertRaises(Refusal): self.preview()
        alias.unlink()
        for text in ('{"endpoint":{},"brains":{},"brains":{}}', ' ' * 20001):
            self.binding.write_text(text)
            with self.assertRaises(Refusal): self.preview()
        self.binding.write_bytes(saved)

    def test_mismatched_reference_and_changed_inode_still_refuse(self):
        with sqlite3.connect(self.reference) as db: db.execute('CREATE TABLE foreign_data(id TEXT)')
        with self.assertRaisesRegex(Refusal, 'contents do not match'): self.preview()
        self.save_reference()
        with self.registry.tx() as db:
            value = json.loads(db.execute('SELECT data FROM workspaces WHERE id=?', (self.workspace,)).fetchone()[0])
            value['databaseIdentity'][1] += 1
            db.execute('UPDATE workspaces SET data=? WHERE id=?', (canonical(value), self.workspace))
        with self.assertRaises(Refusal): self.preview()

    def test_dashboard_lock_and_post_backup_binding_drift_roll_back(self):
        proposal = self.preview()
        with open(self.ledger.root / 'dashboard.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(Refusal, 'Stop the dashboard'): self.apply(proposal)
        before = self.contents(self.registry.db)
        original = device.backup_database
        calls = []
        def save(*args):
            original(*args); calls.append(1)
            if len(calls) == 2: self.binding.write_text(self.binding.read_text())
        with patch.object(device, 'backup_database', side_effect=save), self.assertRaises(Refusal): self.apply(proposal)
        self.assertEqual(self.contents(self.registry.db), before)
        self.assertEqual(len(list((self.registry.root / 'backups').glob('device-recovery-*'))), 1)

    def test_concurrent_confirmations_have_one_receipt_and_no_ledger_writes(self):
        proposal, before = self.preview(), self.contents(self.ledger.db)
        results, errors = [], []
        def apply():
            try: results.append(self.apply(proposal))
            except Exception as error: errors.append(error)
        threads = [threading.Thread(target=apply) for _ in range(2)]
        for worker in threads: worker.start()
        for worker in threads: worker.join(timeout=10)
        self.assertFalse(any(worker.is_alive() for worker in threads)); self.assertFalse(errors, errors)
        self.assertEqual(len(results), 2); self.assertEqual(results[0], results[1])
        self.assertEqual(self.contents(self.ledger.db), before)

    def test_cli_explicit_mode_and_private_json_confirmation(self):
        base = [sys.executable, '-m', 'orchestrator.cli', '--platform', str(self.registry.root),
                '--workspace', self.workspace]
        command = [*base, 'workspace-identity-preview', str(self.reference), '--preserve-ended-recovery', str(self.binding)]
        before = self.contents(self.ledger.db), self.contents(self.registry.db)
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, (self.contents(self.ledger.db), self.contents(self.registry.db)))
        conflict = subprocess.run([*command, '--preserve-pending-play'], capture_output=True, timeout=15)
        self.assertEqual(conflict.returncode, 2)
        proposal = json.loads(result.stdout)
        path = self.root / 'preview.json'; path.write_text(canonical(proposal)); path.chmod(0o600)
        confirm = [*base, 'workspace-identity-recover', str(path), '--confirm-hash', proposal['documentHash']]
        self.assertEqual(subprocess.run(confirm, capture_output=True, timeout=15).returncode, 2)
        result = subprocess.run([*confirm, '--confirm', '--writers-stopped'], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.contents(self.ledger.db), before[0])
