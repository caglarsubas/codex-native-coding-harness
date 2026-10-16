"""Prospective lineage, preserved original failure, no native reload or replay."""
import contextlib
import copy
import io
import json
import os
import sqlite3
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import core, standard, standard_successor as successor, partial_admission as partial
from orchestrator import forward_continuation as forward
from orchestrator.app_server_wake import AppServerWake
from orchestrator.core import Refusal, canonical, digest
import test_partial_admission as fixtures
from test_app_server_wake import FakeThread


class ForwardTest(unittest.TestCase):
    def setUp(self):
        self.p = fixtures.PartialAdmissionTest('runTest'); self.p.setUp(); self.addCleanup(self.p.doCleanups)
        self.f = self.p.f
        self.registry, self.source, self.target = self.p.registry, self.p.source, self.p.target
        self.claims = [successor.pin(self.p.marker), successor.pin(self.p.outgoing)]

    def prepare(self): return forward.prepare(self.registry, self.source, self.p.original_path)
    def backup(self, preview):
        destination = self.target.root/'forward-backup'
        forward.create_backup(self.registry, self.source, preview['request'], destination, writers_stopped=True)
        return destination
    def confirm(self, preview=None):
        p = preview or self.prepare()
        return forward.confirm(self.registry, self.source, p['request'], p['reviewHash'],
                               writers_stopped=True, backup_root=self.backup(p))
    def preserved(self):
        self.assertEqual([successor.pin(self.p.marker), successor.pin(self.p.outgoing)], self.claims)
        self.f.assert_source_unchanged()
        self.assertEqual(partial.database_proof(self.registry.db), self.p.before['registry'])
        self.assertEqual(self.source.snapshot()['meta']['standardRun']['brainObservedTokens'], 1049625)
        with standard.read_db(self.target.db) as db:
            self.assertFalse(db.execute('SELECT 1 FROM snapshots WHERE kind=?', (successor.KIND,)).fetchone())

    def sending(self):
        self.confirm(); command = self.f.play()
        with self.target.tx() as db:
            command = self.target.get(db, 'commands', command['id'])
            command['notification'] = {'status': 'sending', 'brainId': self.f.brain,
                'hostRunId': command['payload']['runId'], 'hostBindingHash': digest(self.f.binding),
                'successorHash': command['payload']['successorHash'], 'attemptedAt': time.time(),
                'hostInspectionTransport': 'owned_observer_v1'}
            self.target.put(db, 'commands', command['id'], command)
        return command

    def test_preview_is_nonwaking_bundled_and_has_no_timer(self):
        p = self.prepare()
        with patch('time.time', return_value=time.time()+10**8): self.assertEqual(p, self.prepare())
        self.assertTrue(p['recordsUnqualifiedDisposition']); self.assertFalse(p['playAuthorized'])
        self.assertEqual(p['validUntil'], 'scope_changes')
        self.assertFalse((self.target.root/forward.FENCE).exists())
        self.assertFalse((self.target.root/partial.FENCE).exists())
        self.p.assert_preserved()

    def test_one_review_records_failure_and_distinct_forward_lineage_without_old_confirm(self):
        with patch.object(successor, 'confirm', side_effect=AssertionError('Never retry admission')):
            receipt = self.confirm()
        self.assertEqual(receipt['lineageProtocol'], forward.KIND)
        self.assertEqual(receipt['outcome'], forward.OUTCOME)
        self.assertFalse(any(receipt['boundary'].values()))
        self.assertTrue(receipt['bothOriginalClaimsPreserved'])
        self.assertEqual(receipt['originalAdmission'], 'unqualified_uncommitted')
        self.assertIsNone(self.target.snapshot()['meta'].get('standardRun'))
        self.assertEqual(standard.read(self.target)['successor']['recordHash'], receipt['recordHash'])
        self.assertEqual(partial.status(self.registry, self.target)['status'], partial.OUTCOME)
        self.assertEqual(self.f.q.f.fixture.fake.calls, []); self.preserved()

    def test_an_already_recorded_unqualified_disposition_is_not_rewritten(self):
        p = self.p.prepare(); self.p.confirm(p, writers_stopped=True, backup_root=self.p.backup(p))
        before = successor.pin(self.target.root/partial.FENCE)
        proposal = self.prepare(); self.assertFalse(proposal['recordsUnqualifiedDisposition'])
        self.confirm(proposal)
        self.assertEqual(successor.pin(self.target.root/partial.FENCE), before); self.preserved()

    def test_exact_new_receipt_read_is_stable_and_cannot_rearm_play(self):
        p = self.prepare(); receipt = self.confirm(p)
        pin = successor.pin(self.target.root/forward.FENCE)
        with patch('time.time', return_value=time.time()+10**7):
            self.assertEqual(forward.confirm(self.registry, self.source, p['request'], p['reviewHash']), receipt)
        self.assertEqual(successor.pin(self.target.root/forward.FENCE), pin)
        self.f.play()
        with self.assertRaises(Refusal): self.f.play()
        self.preserved()

    def test_old_approval_or_missing_backup_cannot_confirm(self):
        p = self.prepare()
        with self.assertRaises(Refusal): forward.confirm(self.registry, self.source, p['request'], self.p.original['reviewHash'])
        with self.assertRaises(Refusal): forward.confirm(self.registry, self.source, p['request'], p['reviewHash'])
        with self.assertRaises(Refusal): forward.create_backup(self.registry, self.source, p['request'], self.target.root/'no-stop')
        self.assertFalse((self.target.root/forward.FENCE).exists()); self.p.assert_preserved()

    def test_changed_or_aliased_backup_refuses_before_intent(self):
        p = self.prepare(); backup = self.backup(p)
        (backup/'binding.json').write_text('{}')
        with self.assertRaises(Refusal):
            forward.confirm(self.registry, self.source, p['request'], p['reviewHash'], writers_stopped=True, backup_root=backup)
        self.assertFalse((self.target.root/forward.FENCE).exists()); self.p.assert_preserved()

    def test_source_usage_target_claim_and_binding_drift_refuse(self):
        p = self.prepare(); self.f.binding_path.write_text('{}')
        with self.assertRaises(Refusal): self.confirm(p)
        self.assertFalse((self.target.root/forward.FENCE).exists())

    def test_commit_interruption_keeps_new_intent_and_both_old_claims_without_retry(self):
        p = self.prepare(); backup = self.backup(p); put = core.Ledger.put
        def fail(db, table, key, value):
            if table == 'meta' and value.get('forwardContinuationVersion'): raise OSError('Fixture forward commit refused')
            return put(db, table, key, value)
        with patch.object(core.Ledger, 'put', side_effect=fail), self.assertRaises(OSError):
            forward.confirm(self.registry, self.source, p['request'], p['reviewHash'], writers_stopped=True, backup_root=backup)
        self.assertEqual(forward.status(self.registry, self.target)['status'], 'forward_continuation_incomplete_or_changed')
        with self.assertRaises(Refusal): forward.confirm(self.registry, self.source, p['request'], p['reviewHash'])
        with self.assertRaises(Refusal):
            with self.target.tx(): pass
        self.assertFalse(standard.read(self.target)['available']); self.preserved()

    def test_partial_file_is_unknown_not_a_new_attempt(self):
        path = self.target.root/forward.FENCE; path.write_text('{'); path.chmod(0o600)
        with self.assertRaises((Refusal, ValueError)): self.prepare()
        self.assertTrue(forward.status(self.registry, self.target)['writesBlocked'])
        with self.assertRaises((Refusal, ValueError)):
            with self.target.tx(): pass
        self.assertFalse(standard.read(self.target)['available']); self.preserved()

    def test_missing_old_claim_or_new_disposition_never_unfreezes(self):
        self.confirm(); self.p.marker.unlink()
        with self.assertRaises((OSError, Refusal)):
            with self.target.tx(): pass
        self.assertFalse(standard.read(self.target)['available'])

    def test_downgrade_and_original_history_mutation_roll_back(self):
        self.confirm()
        with self.assertRaises(Refusal):
            with self.target.tx() as db:
                meta = self.target.get(db, 'meta', 1); meta['schemaVersion'] = 1
                self.target.put(db, 'meta', 1, meta)
        with self.assertRaises(Refusal):
            with self.target.tx() as db: db.execute('DELETE FROM events')
        self.preserved()

    def test_native_loaded_only_preflight_refuses_unloaded_and_unknown_trackers(self):
        command = self.sending(); host = AppServerWake(self.f.binding, self.target)
        for native in (self.f.fake(loaded=False), self.f.fake(terminals=[{'itemId': 'x', 'processId': 'pending'}])):
            with self.assertRaises(Refusal): successor.loaded_profile(host, native, command['id'], self.f.brain)
            self.assertNotIn('thread/resume', native.calls); self.assertNotIn('turn/start', native.calls)
        self.preserved()

    def test_fresh_loaded_delivery_starts_once_without_reload_or_old_play(self):
        command = self.sending(); native = self.f.fake(); host = AppServerWake(self.f.binding, self.target)
        with patch.object(host, 'configured', return_value=True), patch('orchestrator.app_server_wake.validate_endpoint'), \
             patch('orchestrator.app_server_wake.WakeProxy', return_value=native), \
             patch('orchestrator.app_server_wake.threading.Thread', FakeThread):
            result = host.send(self.f.brain, 'Fixture NEW forward control pointer', command['id'])
        self.assertEqual(result['status'], 'accepted', result)
        self.assertEqual(native.calls.count('turn/start'), 1); self.assertNotIn('thread/resume', native.calls)
        self.preserved()

    def test_pause_and_expiry_refuse_new_turn_without_renewing_clock(self):
        command = self.sending(); expires = standard.read(self.target)['run']['expiresAt']
        with patch('time.time', return_value=expires+1):
            with self.assertRaises(Refusal): successor.loaded_profile(AppServerWake(self.f.binding, self.target), self.f.fake(), command['id'], self.f.brain)
        self.assertEqual(standard.read(self.target)['run']['expiresAt'], expires); self.preserved()

    def test_full_new_task_to_checkpoint_journey_preserves_failed_admission(self):
        # Reuse the normal broker/task/checkpoint journey with only its setup
        # changed to the NEW forward contract, not a duplicate dispatcher.
        self.f.sending = self.sending
        self.f.test_new_phase_journal_can_reach_its_checkpoint_without_reusing_old_run()
        self.assertEqual(standard.read(self.target)['run']['status'], 'completed')
        self.preserved()

    def test_pause_race_uses_the_same_loaded_only_guard(self):
        self.f.sending = self.sending
        self.f.test_pause_race_does_not_start_or_renew()
        self.preserved()

    def test_deleting_new_disposition_or_intent_does_not_bypass_old_claims(self):
        self.confirm(); (self.target.root/partial.FENCE).unlink()
        with self.assertRaises((OSError, Refusal)):
            with self.target.tx(): pass
        self.assertFalse(standard.read(self.target)['available'])

    def test_exact_claim_ctime_is_pinned_even_if_mtime_is_restored(self):
        proposal = self.prepare(); info = self.p.marker.stat()
        self.p.marker.write_bytes(self.p.marker.read_bytes())
        os.utime(self.p.marker, ns=(info.st_atime_ns, info.st_mtime_ns))
        with self.assertRaises(Refusal): self.confirm(proposal)
        self.assertFalse((self.target.root/forward.FENCE).exists())

    def test_committed_old_admission_or_pending_task_never_qualifies(self):
        with contextlib.closing(sqlite3.connect(self.target.db)) as db, db:
            db.execute('INSERT INTO snapshots VALUES(?,?,?)', ('a'*64, successor.KIND, '{}'))
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse((self.target.root/forward.FENCE).exists())

    def test_alias_backup_and_wrong_route_do_not_create_intent(self):
        p = self.prepare(); backup = self.backup(p)
        copied = backup/'target-claim.json'; copied.unlink(); os.link(self.p.marker, copied)
        with self.assertRaises(Refusal):
            forward.confirm(self.registry, self.source, p['request'], p['reviewHash'], writers_stopped=True, backup_root=backup)
        with self.assertRaises(Refusal): forward.confirm(self.registry, self.target, p['request'], p['reviewHash'])
        self.assertFalse((self.target.root/forward.FENCE).exists())

    def test_late_foreign_owner_fences_effects_but_keeps_local_pause(self):
        self.f.confirm = self.confirm
        self.f.test_late_foreign_owner_blocks_effects_but_not_local_pause()
        self.assertEqual(standard.read(self.target)['run']['status'], 'stopping')
        self.f.assert_source_unchanged()
        self.assertEqual([successor.pin(self.p.marker), successor.pin(self.p.outgoing)], self.claims)

    def test_concurrent_exact_confirmations_can_commit_only_one_new_record(self):
        p = self.prepare(); backup = self.backup(p)
        def apply(_):
            try:
                return forward.confirm(self.registry, self.source, p['request'], p['reviewHash'],
                                       writers_stopped=True, backup_root=backup)
            except (Refusal, OSError): return None
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(apply, range(2)))
        self.assertTrue(any(results))
        with standard.read_db(self.target.db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM snapshots WHERE kind=?', (forward.KIND,)).fetchone()[0], 1)
        self.assertEqual(len({r['recordHash'] for r in results if r}), 1); self.preserved()

    def test_interrupted_disposition_never_replays_it_or_drops_forward_intent(self):
        p = self.prepare(); backup = self.backup(p)
        from orchestrator.standard_quarantine import exclusive
        def fail(path, value):
            if path.name == partial.FENCE:
                path.write_text('{'); path.chmod(0o600); raise OSError('Interrupted unqualified record')
            return exclusive(path, value)
        with patch('orchestrator.standard_quarantine.exclusive', side_effect=fail), self.assertRaises(OSError):
            forward.confirm(self.registry, self.source, p['request'], p['reviewHash'], writers_stopped=True, backup_root=backup)
        self.assertTrue((self.target.root/forward.FENCE).exists())
        with self.assertRaises(Refusal): forward.confirm(self.registry, self.source, p['request'], p['reviewHash'])
        self.assertFalse(standard.read(self.target)['available']); self.preserved()

    def test_boolean_version_extra_authority_and_source_drift_refuse_before_claim(self):
        p = self.prepare(); backup = self.backup(p)
        for changed in ({**p['request'], 'version': True}, {**p['request'], 'terminalSafe': True}):
            with self.assertRaises(Refusal):
                forward.confirm(self.registry, self.source, changed, digest(changed), writers_stopped=True, backup_root=backup)
        with patch.object(forward, 'source_hash', return_value='f'*64), self.assertRaises(Refusal):
            forward.confirm(self.registry, self.source, p['request'], p['reviewHash'], writers_stopped=True, backup_root=backup)
        self.assertFalse((self.target.root/forward.FENCE).exists()); self.p.assert_preserved()

    def test_wrong_effective_policy_is_not_accepted_as_configuration_acknowledgment(self):
        self.f.sending = self.sending
        self.f.test_wrong_loaded_policy_never_becomes_configuration_acknowledgement()
        self.preserved()

    def test_new_target_schema_cannot_change_behind_the_preserved_history(self):
        self.confirm()
        with self.assertRaises(Refusal):
            with self.target.tx() as db: db.execute('CREATE TABLE unrelated(id INTEGER)')
        self.preserved()

    def test_cli_preview_and_status_never_construct_writers(self):
        from orchestrator.cli import main
        argv = ['orchestrator', '--platform', str(self.registry.root), '--workspace', self.source.workspace_id,
                'forward-continuation-preview', str(self.p.original_path)]
        stream = io.StringIO()
        with patch.object(sys, 'argv', argv), patch('sys.stdout', stream), \
             patch('orchestrator.workspaces.Registry', side_effect=AssertionError('No writer')), \
             patch('orchestrator.core.Ledger.__init__', side_effect=AssertionError('No writer')):
            main()
        self.assertEqual(json.loads(stream.getvalue())['reviewHash'], self.prepare()['reviewHash']); self.p.assert_preserved()


if __name__ == '__main__': unittest.main()
