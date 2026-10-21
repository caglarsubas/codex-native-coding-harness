"""Actual admitted SQLite/Git lineage; explicitly simulated reboot device/boot.

Native preparation and worker observation are synthetic fixture metadata. The
migration itself must make zero additional native or provider calls.
"""
import copy
import concurrent.futures
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator import post_reboot_maintenance as maintenance, standard
from orchestrator.core import Refusal, canonical, digest
import test_worker_readiness as fixtures

REAL_THREAD = threading.Thread  # Capture before predecessor fixtures replace the observer thread.


class RebootMaintenanceTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.WorkerReadinessTest('test_admitted_real_lineage_and_both_claims_remain_unchanged')
        self.addCleanup(self.f.doCleanups); self.f.setUp()
        self.f.collect()
        self.registry, self.ledger = self.f.registry, self.f.ledger
        self.witness = self.f.destination
        self.boot = time.time()
        self.calls = self.f.r.calls.copy()
        self.original = maintenance.startup.databases(self.registry)
        self.original_files = {p: Path(p).read_bytes() for p in self.f.protected}
        for p in (patch.object(maintenance, 'device', side_effect=lambda s: s.st_dev + 17),
                  patch.object(maintenance, 'boot_epoch', return_value=self.boot),
                  patch.object(maintenance, 'boot_session', return_value='bc741038-18ab-46a3-9212-35469ee79513'),
                  patch.object(maintenance, 'retired_endpoint', return_value={
                      'fixture': 'synthetic_predecessor_endpoint', 'nativeConnectionMade': False})):
            p.start(); self.addCleanup(p.stop)
        self.backup_root = self.f.r.f.root / 'maintenance-backup'

    def prepare(self):
        return maintenance.prepare(self.registry.root, self.ledger.workspace_id, self.witness)

    def apply(self):
        proposed = self.prepare(); self.q = proposed['request']
        maintenance.backup(self.q, self.backup_root, writers_stopped=True)
        return maintenance.confirm(self.q, proposed['reviewHash'], self.backup_root, writers_stopped=True)

    def conserved(self):
        self.assertEqual(maintenance.startup.databases(self.registry), self.original)
        for path, raw in self.original_files.items(): self.assertEqual(Path(path).read_bytes(), raw)
        self.assertEqual(self.f.r.calls, self.calls)
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass

    def test_prepare_is_file_only_scope_bound_and_keeps_old_binding(self):
        a, b = self.prepare(), self.prepare()
        self.assertEqual(a, b); self.assertEqual(a['validUntil'], 'scope_changes')
        self.assertFalse(a['request']['boundary']['bindingChanged'])
        self.assertFalse(Path(a['request']['journal']).exists()); self.conserved()

    def test_calendar_boot_drift_keeps_exact_review_and_original_cutoff(self):
        boot = self.boot + 1
        with patch.object(maintenance.time, 'time', return_value=boot + 2), \
             patch.object(maintenance, 'boot_epoch', return_value=boot):
            proposed = self.prepare(); q = proposed['request']
            maintenance.backup(q, self.backup_root, writers_stopped=True)
            with patch.object(maintenance, 'boot_epoch', return_value=boot + .061651):
                maintenance.current(q)
                maintenance.confirm(q, proposed['reviewHash'], self.backup_root, writers_stopped=True)
            with patch.object(maintenance, 'boot_epoch', return_value=boot - .061651):
                result = maintenance.status(q)
            self.assertEqual(q['context']['bootedAt'], boot)
            self.assertTrue(result['maintenanceIdentityRecognized'])
            self.assertEqual(proposed['reviewHash'], digest(q))
        self.conserved()

    def test_same_device_new_boot_session_refuses_before_and_after_claim(self):
        proposed = self.prepare(); q = proposed['request']
        maintenance.backup(q, self.backup_root, writers_stopped=True)
        other = '11111111-2222-4333-8444-555555555555'
        with patch.object(maintenance, 'boot_session', return_value=other):
            with self.assertRaises(Refusal):
                maintenance.confirm(q, proposed['reviewHash'], self.backup_root, writers_stopped=True)
        self.assertFalse(Path(q['journal']).exists())
        maintenance.confirm(q, proposed['reviewHash'], self.backup_root, writers_stopped=True)
        with patch.object(maintenance, 'boot_session', return_value=other):
            with self.assertRaises(Refusal): maintenance.status(q)
        self.conserved()

    def test_backward_clock_boundary_cannot_admit_postboot_evidence(self):
        proposed = self.prepare(); q = proposed['request']
        with patch.object(maintenance, 'boot_epoch', return_value=self.boot - 3600):
            with self.assertRaises(Refusal): maintenance.current(q)
        changed = copy.deepcopy(q); changed['context']['bootedAt'] = self.boot - 3600
        with patch.object(maintenance, 'boot_epoch', return_value=self.boot + 3600), \
             patch.object(maintenance.time, 'time', return_value=self.boot + 7200):
            with self.assertRaises(Refusal): maintenance.current(changed)
        self.assertFalse(Path(q['journal']).exists()); self.conserved()

    def test_legacy_review_never_converts_or_reuses_its_approval(self):
        proposed = self.prepare(); q = copy.deepcopy(proposed['request'])
        q['version'] = 1; q['kind'] = 'post_reboot_maintenance_epoch_v1'
        del q['context']['bootSessionUuid']
        with self.assertRaises(Refusal): maintenance.current(q)
        with self.assertRaises(Refusal): maintenance.confirm(q, digest(q), self.backup_root, writers_stopped=True)
        self.assertFalse(Path(q['journal']).exists()); self.conserved()

    def test_boot_change_during_collection_refuses_even_with_same_device(self):
        with patch.object(maintenance, 'boot_session', side_effect=[
                'bc741038-18ab-46a3-9212-35469ee79513', '11111111-2222-4333-8444-555555555555']):
            with self.assertRaisesRegex(Refusal, 'Boot session changed'): self.prepare()
        self.conserved()

    def test_one_confirmed_epoch_restores_only_explicit_maintenance_read(self):
        a = self.apply(); b = maintenance.status(self.q)
        self.assertEqual(a, b); self.assertTrue(a['maintenanceIdentityRecognized'])
        self.assertTrue(a['normalWritesBlocked']); self.assertFalse(a['boundary']['playAuthorized'])
        self.assertEqual(a['boundary']['currentTerminalSafety'], 'unknown')
        self.assertIn('loaded_policy_unknown_no_reload_authorized', a['blockers']); self.conserved()

    def test_existing_default_identity_recovery_stays_strict(self):
        with self.assertRaisesRegex(Refusal, 'Only device-number drift|Pending commands'):
            maintenance.recovery.preview(self.registry, self.ledger.workspace_id, self.f.f.b / 'database-0.sqlite3')
        self.conserved()

    def test_old_or_generic_confirmation_does_not_claim(self):
        proposed = self.prepare(); q = proposed['request']
        maintenance.backup(q, self.backup_root, writers_stopped=True)
        for bad in ('approved', self.f.q['predecessor']['reviewHash'], self.f.q['sourceHash']):
            with self.assertRaises(Refusal): maintenance.confirm(q, bad, self.backup_root, writers_stopped=True)
        self.assertFalse(Path(q['journal']).exists()); self.conserved()

    def test_stopped_writers_and_verified_disjoint_backup_are_mandatory(self):
        proposed = self.prepare(); q = proposed['request']
        with self.assertRaises(Refusal): maintenance.backup(q, self.backup_root)
        with self.assertRaises(Refusal): maintenance.backup(q, self.ledger.root / 'bad', writers_stopped=True)
        with self.assertRaises(Refusal): maintenance.confirm(q, proposed['reviewHash'], self.backup_root)
        self.conserved()

    def test_consumed_certificate_cannot_retry_or_rearm_on_source_or_id(self):
        self.apply()
        with self.assertRaises(Refusal): self.prepare()
        with self.assertRaises(Refusal): maintenance.confirm(self.q, digest(self.q), self.backup_root, writers_stopped=True)
        changed = copy.deepcopy(self.q); changed['journal'] += '-another'
        with self.assertRaises(Refusal): maintenance.confirm(changed, digest(changed), self.backup_root, writers_stopped=True)
        self.conserved()

    def test_concurrent_confirmations_have_one_permanent_winner(self):
        proposed = self.prepare(); q = proposed['request']
        maintenance.backup(q, self.backup_root, writers_stopped=True)
        def confirm():
            try:
                return maintenance.confirm(q, proposed['reviewHash'], self.backup_root, writers_stopped=True)['status']
            except Refusal:
                return 'refused'
        with patch.object(threading, 'Thread', REAL_THREAD), concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: confirm(), range(2)))
        self.assertCountEqual(results, ['maintenance_epoch_retained', 'refused']); self.conserved()

    def test_second_device_epoch_cannot_use_another_directory(self):
        self.apply()
        with patch.object(maintenance, 'device', side_effect=lambda s: s.st_dev + 18):
            with self.assertRaises(Refusal): maintenance.status(self.q)
            with self.assertRaises(Refusal): self.prepare()
        self.conserved()

    def test_partial_mirror_or_journal_is_unknown_and_never_resends(self):
        self.apply(); (Path(self.q['journal']) / 'result.json').unlink()
        with self.assertRaises((Refusal, OSError)): maintenance.status(self.q)
        with self.assertRaises(Refusal): self.prepare()
        self.conserved()

    def test_partial_claim_failure_is_permanent_without_registry_write(self):
        proposed = self.prepare(); q = proposed['request']
        maintenance.backup(q, self.backup_root, writers_stopped=True)
        native_exclusive = maintenance.exclusive
        def fail(path, value):
            if Path(path).name == maintenance.FENCE: raise OSError('Synthetic post-intent disk failure')
            return native_exclusive(path, value)
        with patch.object(maintenance, 'exclusive', side_effect=fail):
            with self.assertRaises(OSError): maintenance.confirm(q, proposed['reviewHash'], self.backup_root, writers_stopped=True)
        with self.assertRaises(Refusal): self.prepare()
        self.assertTrue((Path(q['journal']) / 'intent.json').exists()); self.conserved()

    def test_witness_is_historical_and_status_never_renews_native_time(self):
        result = self.apply(); old = json.loads((self.witness / 'report.json').read_text())
        with patch.object(maintenance.time, 'time', return_value=time.time() + 10000):
            again = maintenance.status(self.q)
        self.assertEqual(again['historicalObservedAt'], old['observedAt'])
        self.assertEqual(result, again); self.conserved()

    def test_no_real_device_drift_does_not_offer_a_review(self):
        with patch.object(maintenance, 'device', side_effect=lambda s: s.st_dev):
            with self.assertRaises(Refusal): self.prepare()
        self.conserved()

    def test_forged_or_postboot_witness_does_not_capture_old_effects(self):
        report = self.witness / 'report.json'; original = report.read_bytes()
        value = json.loads(original); value['throughAt'] = self.boot + 10
        report.write_text(canonical(value))
        with self.assertRaises(Refusal): self.prepare()
        self.assertEqual(self.f.r.calls, self.calls)

    def test_missing_seal_or_changed_context_is_not_owner_cleanup_evidence(self):
        (self.witness / 'seal.json').unlink()
        with self.assertRaises(Refusal): self.prepare()
        self.conserved()

    def test_changed_database_or_original_command_remains_fenced(self):
        with sqlite3.connect(self.ledger.db) as db: db.execute("UPDATE commands SET data='{}'")
        with self.assertRaises((Refusal, KeyError)): self.prepare()
        self.assertEqual(self.f.r.calls, self.calls)

    def test_source_epoch_changes_other_than_device_refuse(self):
        original = maintenance.startup.prior.source_proof
        def changed(root):
            p = original(root); p['sourceHash'] = 'f' * 64; return p
        with patch.object(maintenance.startup.prior, 'source_proof', side_effect=changed):
            with self.assertRaises(Refusal): self.prepare()
        self.conserved()

    def test_changed_inode_or_record_hash_never_becomes_epoch_continuity(self):
        report = json.loads((self.witness / 'report.json').read_text())
        path, previous = next(iter(report['context']['files'].items()))
        for field in ('identity', 'sha256'):
            value = copy.deepcopy(previous)
            if field == 'identity': value['identity'][1] += 1
            else: value['sha256'] = 'f' * 64
            with self.assertRaises(Refusal): maintenance.historical_pin(path, value,
                previous['identity'][0], previous['identity'][0] + 17, self.boot)
        self.conserved()

    def test_present_old_socket_does_not_connect_or_adopt_a_host(self):
        with patch.object(maintenance, 'retired_endpoint', side_effect=Refusal('Synthetic present old socket')):
            with self.assertRaises(Refusal): self.prepare()
        self.conserved()

    def test_corrupt_database_or_input_backup_refuses_before_claim(self):
        proposed = self.prepare(); q = proposed['request']
        maintenance.backup(q, self.backup_root, writers_stopped=True)
        file = next(self.backup_root.glob('input-*.json')); file.write_text('{}')
        with self.assertRaises(Refusal): maintenance.confirm(q, proposed['reviewHash'], self.backup_root, writers_stopped=True)
        self.assertFalse(Path(q['journal']).exists()); self.conserved()

    def test_drift_after_review_is_not_a_new_budget_or_approval(self):
        proposed = self.prepare(); q = proposed['request']
        maintenance.backup(q, self.backup_root, writers_stopped=True)
        (Path(self.f.q['journal']) / 'stop.json').write_text('{}')
        with self.assertRaises(Refusal): maintenance.confirm(q, proposed['reviewHash'], self.backup_root, writers_stopped=True)
        self.assertFalse(Path(q['journal']).exists()); self.assertEqual(self.f.r.calls, self.calls)


class LocalGuardTest(unittest.TestCase):
    def test_fixed_boot_session_read_is_bounded_private_metadata_only(self):
        with patch.object(maintenance.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stderr=b'', stdout=b'BC741038-18AB-46A3-9212-35469EE79513\n')) as run:
            self.assertEqual(maintenance.boot_session(), 'bc741038-18ab-46a3-9212-35469ee79513')
        run.assert_called_once_with(['/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid'], capture_output=True,
                                    timeout=5, env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})

    def test_unsupported_boot_identity_never_falls_back_to_wall_time(self):
        for out, err, code in ((b'', b'', 0), (b'not-a-uuid\n', b'', 0),
                               (b'00000000-0000-0000-0000-000000000000\n', b'', 0),
                               (b'BC741038-18AB-46A3-9212-35469EE79513\nextra', b'', 0),
                               (b'x' * 128, b'', 0), (b'', b'unsupported', 1)):
            with self.subTest(output=out), patch.object(maintenance.subprocess, 'run', return_value=SimpleNamespace(
                    returncode=code, stderr=err, stdout=out)):
                with self.assertRaises(Refusal): maintenance.boot_session()

    def test_private_child_of_writable_ancestor_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            outer = Path(d).resolve() / 'public'; outer.mkdir(mode=0o777); outer.chmod(0o777)
            private = outer / 'private'; private.mkdir(mode=0o700)
            file = private / 'record.json'; file.write_text('{}'); file.chmod(0o600)
            with self.assertRaises(Refusal): maintenance.pin(file)

    def test_symlink_and_hardlink_records_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d).resolve() / 'record.json'; file.write_text('{}'); file.chmod(0o600)
            link = Path(d).resolve() / 'link.json'; link.symlink_to(file)
            with self.assertRaises(Refusal): maintenance.pin(link)
            link.unlink(); os.link(file, link)
            with self.assertRaises(Refusal): maintenance.pin(file)

    def test_decode_open_cannot_follow_a_post_pin_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve(); file = root / 'record.json'; secret = root / 'auth.json'
            for path in (file, secret): path.write_text('{}'); path.chmod(0o600)
            native_open = os.open; calls = []
            def replacing(path, flags, *args, **kwargs):
                if Path(path) == file:
                    calls.append(flags)
                    if len(calls) == 2:
                        file.unlink(); file.symlink_to(secret)
                return native_open(path, flags, *args, **kwargs)
            with patch.object(maintenance.os, 'open', side_effect=replacing), patch.object(maintenance, 'decode') as decode:
                with self.assertRaises(OSError): maintenance.read(file)
                decode.assert_not_called()

    def test_partial_mirror_alone_fences_normal_startup_controls(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); (root / maintenance.FENCE).write_text('{}')
            self.assertTrue(maintenance.startup.blocked(SimpleNamespace(root=root)))

    def test_endpoint_with_no_reviewed_socket_is_not_a_restart_permit(self):
        with self.assertRaises(Refusal): maintenance.retired_endpoint({'endpoint': {'fixture': True}})

    def test_present_socket_or_alias_is_never_recreated_or_connected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'present'; path.touch()
            endpoint = {'executable': str(path), 'sha256': 'a'*64, 'socket': str(path),
                        'socketIdentity': {}, 'serverIdentityHash': 'b'*64}
            with self.assertRaises(Refusal): maintenance.retired_endpoint({'endpoint': endpoint})
            self.assertTrue(path.exists())


if __name__ == '__main__': unittest.main()
