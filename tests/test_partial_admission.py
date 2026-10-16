"""Disposable partial-admission disposition: preserve fences, never retry native work."""
import copy
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import unittest
from unittest.mock import patch

from orchestrator import core, standard, standard_successor as successor, partial_admission as partial
from orchestrator.core import Refusal, canonical, digest
from orchestrator.workspaces import fingerprint
import test_standard_successor as fixtures


class PartialAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.SuccessorTest('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.source, self.target, self.registry = self.f.source, self.f.target, self.f.registry
        self.original = self.f.prepare()
        self.original_path = self.target.root/'original-attempt.json'
        self.original_path.write_text(canonical(self.original['request'])); self.original_path.chmod(0o600)
        put = core.Ledger.put
        def fail(db, table, key, value):
            if table == 'meta' and value.get('schemaVersion') == 7: raise OSError('Fixture commit refusal')
            return put(db, table, key, value)
        with patch.object(core.Ledger, 'put', side_effect=fail), self.assertRaises(OSError):
            self.f.confirm(self.original)
        self.marker = self.target.root/successor.FENCE
        self.outgoing = successor.source_claim(self.registry.root, self.source.workspace_id)
        self.claims = [self.marker.read_bytes(), self.outgoing.read_bytes()]
        self.before = self.proofs()

    def proofs(self):
        return {name: partial.database_proof(path) for name, path in
                (('source', self.source.db), ('target', self.target.db), ('registry', self.registry.db))}

    def prepare(self): return partial.prepare(self.registry, self.source, self.original_path)
    def backup(self, p):
        path = self.target.root/'verified-backup'
        partial.create_backup(self.registry, self.source, p['request'], path, writers_stopped=True)
        return path
    def confirm(self, p, **kwargs):
        return partial.confirm(self.registry, self.source, p['request'], p['reviewHash'], **kwargs)
    def assert_preserved(self):
        self.assertEqual(self.proofs(), self.before)
        self.assertEqual([self.marker.read_bytes(), self.outgoing.read_bytes()], self.claims)
        self.assertEqual(self.f.q.f.fixture.fake.calls, [])

    def test_preview_is_read_only_no_countdown_or_native_collection(self):
        files = set(self.target.root.iterdir()); p = self.prepare()
        self.assertEqual(p['validUntil'], 'scope_changes'); self.assertFalse(p['nativeCollection'])
        with patch('time.time', return_value=time.time()+10**8): self.assertEqual(self.prepare(), p)
        self.assertEqual(files, set(self.target.root.iterdir())); self.assert_preserved()

    def test_grown_registry_disposition_preserves_every_database_and_both_claims(self):
        self.f.grow_registry(); self.before = self.proofs()
        p = self.prepare(); result = self.confirm(p, writers_stopped=True, backup_root=self.backup(p))
        self.assertEqual(result['status'], partial.OUTCOME)
        self.assertTrue(result['writesBlocked']); self.assertFalse(any(result['boundary'].values()))
        self.assertEqual(result['historicalTerminalSafety'], 'unknown')
        self.assertEqual(partial.status(self.registry, self.target), result)
        self.assertEqual(standard.read(self.target)['successor'], result)
        self.assert_preserved()
        with self.assertRaises(Refusal):
            with self.target.tx(): pass
        with self.assertRaises(Refusal): self.f.confirm(self.original)

    def test_exact_receipt_reread_never_reapplies_or_refreshes_time(self):
        p = self.prepare(); first = self.confirm(p, writers_stopped=True, backup_root=self.backup(p))
        info = (self.target.root/partial.FENCE).stat()
        with patch('time.time', return_value=time.time()+100000): self.assertEqual(first, self.confirm(p))
        self.assertEqual(info, (self.target.root/partial.FENCE).stat()); self.assert_preserved()

    def test_requires_exact_review_stopped_writers_and_matching_backup(self):
        p = self.prepare()
        with self.assertRaises(Refusal): self.confirm(p)
        with self.assertRaises(Refusal): self.confirm(p, writers_stopped=True)
        with self.assertRaises(Refusal):
            partial.confirm(self.registry, self.source, p['request'], 'a'*64, writers_stopped=True)
        self.assertFalse((self.target.root/partial.FENCE).exists()); self.assert_preserved()

    def test_missing_wrong_or_aliased_backup_refuses_before_disposition(self):
        p = self.prepare(); backup = self.backup(p)
        copied = backup/'target-claim.json'; copied.write_text('{}')
        with self.assertRaises(Refusal): self.confirm(p, writers_stopped=True, backup_root=backup)
        copied.unlink(); os.link(self.marker, copied)
        with self.assertRaises(Refusal): self.confirm(p, writers_stopped=True, backup_root=backup)
        self.assertFalse((self.target.root/partial.FENCE).exists())

    def test_claim_or_original_review_epoch_drift_invalidates_preview(self):
        p = self.prepare(); self.marker.write_bytes(self.marker.read_bytes())
        with self.assertRaises(Refusal): self.confirm(p, writers_stopped=True, backup_root=self.target.root)
        self.assertFalse((self.target.root/partial.FENCE).exists())
        self.marker.write_text('{}')
        with self.assertRaises(Refusal): self.prepare()

    def test_missing_or_foreign_claim_cannot_count_as_absent(self):
        self.outgoing.write_text(canonical({'kind': successor.KIND, 'target': 'foreign', 'recordHash': 'a'*64}))
        with self.assertRaises(Refusal): self.prepare()
        self.outgoing.unlink()
        with self.assertRaises(OSError): self.prepare()
        self.assertFalse((self.target.root/partial.FENCE).exists())

    def test_committed_snapshot_or_pending_effect_refuses(self):
        with contextlib.closing(sqlite3.connect(self.target.db)) as db, db:
            db.execute('INSERT INTO snapshots VALUES(?,?,?)', ('a'*64, successor.KIND, '{}'))
        with self.assertRaises(Refusal): self.prepare()

    def test_changed_target_meta_or_source_usage_refuses(self):
        with contextlib.closing(sqlite3.connect(self.target.db)) as db, db:
            meta = json.loads(db.execute('SELECT data FROM meta').fetchone()[0]); meta['runner'] = {'unknown': True}
            db.execute('UPDATE meta SET data=?', (canonical(meta),))
        with self.assertRaises(Refusal): self.prepare()
        with contextlib.closing(sqlite3.connect(self.source.db)) as db, db:
            meta = json.loads(db.execute('SELECT data FROM meta').fetchone()[0])
            meta['standardRun']['brainObservedTokens'] += 1
            db.execute('UPDATE meta SET data=?', (canonical(meta),))
        with self.assertRaises(Refusal): self.prepare()

    def test_interrupted_disposition_keeps_new_and_old_fences(self):
        p = self.prepare(); backup = self.backup(p)
        def interrupted(path, value):
            path.write_text('{'); path.chmod(0o600); raise OSError('Fixture interrupted write')
        with patch('orchestrator.standard_quarantine.exclusive', side_effect=interrupted), self.assertRaises(OSError):
            self.confirm(p, writers_stopped=True, backup_root=backup)
        self.assertEqual(partial.status(self.registry, self.target)['status'], 'partial_disposition_incomplete_or_changed')
        with self.assertRaises((Refusal, ValueError)): self.confirm(p)
        self.marker.unlink()  # Adversarial disposable deletion: the new fence must suffice.
        with self.assertRaises(Refusal):
            with self.target.tx(): pass
        self.assertFalse(standard.read(self.target)['available'])

    def test_status_corruption_or_binding_drift_never_unfreezes(self):
        p = self.prepare(); self.confirm(p, writers_stopped=True, backup_root=self.backup(p))
        self.f.binding_path.write_text('{}')
        self.assertEqual(partial.status(self.registry, self.target)['status'], 'partial_disposition_incomplete_or_changed')
        self.assertFalse(standard.read(self.target)['available'])
        with self.assertRaises(Refusal):
            with self.target.tx(): pass

    def test_original_request_can_pin_an_older_source_without_reconstructing_its_receipt(self):
        value = copy.deepcopy(self.original['request']); value['sourceHash'] = 'b'*64
        self.original_path.write_text(canonical(value))
        marker = json.loads(self.marker.read_bytes()); marker['reviewHash'] = digest(value)
        self.marker.write_text(canonical(marker))
        p = self.prepare()
        self.assertEqual(p['request']['originalRequestHash'], digest(value))
        self.assertFalse((self.target.root/partial.FENCE).exists())

    def test_wrong_route_changed_source_and_boolean_version_refuse(self):
        p = self.prepare()
        with self.assertRaises(Refusal): partial.prepare(self.registry, self.target, self.original_path)
        with patch.object(partial, 'source_hash', return_value='f'*64), self.assertRaises(Refusal):
            self.confirm(p, writers_stopped=True, backup_root=self.target.root)
        changed = copy.deepcopy(p['request']); changed['version'] = True
        with self.assertRaises(Refusal):
            partial.confirm(self.registry, self.source, changed, digest(changed), writers_stopped=True)
        self.assertFalse((self.target.root/partial.FENCE).exists()); self.assert_preserved()

    def test_alias_claim_and_replaced_registry_inode_refuse(self):
        p = self.prepare()
        os.link(self.marker, self.target.root/'claim-alias')
        with self.assertRaises(Refusal): self.prepare()
        (self.target.root/'claim-alias').unlink()
        replacement = self.registry.root/'replacement.sqlite3'
        with contextlib.closing(sqlite3.connect(self.registry.db.as_uri()+'?mode=ro', uri=True)) as src:
            with contextlib.closing(sqlite3.connect(replacement)) as dst: src.backup(dst)
        replacement.chmod(0o600); os.replace(replacement, self.registry.db)
        with self.assertRaises(Refusal): self.prepare()
        with self.assertRaises(Refusal): self.confirm(p, writers_stopped=True, backup_root=self.target.root)

    def test_preparing_and_applying_backup_are_distinct_from_recording_disposition(self):
        p = self.prepare()
        with self.assertRaises(Refusal):
            partial.create_backup(self.registry, self.source, p['request'], self.target.root/'no-stop')
        backup = self.backup(p)
        self.assertFalse((self.target.root/partial.FENCE).exists())
        self.assertEqual(self.prepare(), p)
        with self.assertRaises(Refusal):
            partial.create_backup(self.registry, self.source, p['request'], backup, writers_stopped=True)
        self.assert_preserved()

    def test_cli_preview_uses_only_readonly_routes_and_does_not_construct_writers(self):
        from orchestrator.cli import main
        argv = ['orchestrator', '--platform', str(self.registry.root), '--workspace', self.source.workspace_id,
                'partial-admission-preview', str(self.original_path)]
        stream = io.StringIO()
        with patch.object(sys, 'argv', argv), patch('sys.stdout', stream), \
             patch('orchestrator.workspaces.Registry', side_effect=AssertionError('No registry writer')), \
             patch('orchestrator.core.Ledger.__init__', side_effect=AssertionError('No ledger writer')):
            main()
        self.assertEqual(json.loads(stream.getvalue())['reviewHash'], self.prepare()['reviewHash'])
        self.assert_preserved()
