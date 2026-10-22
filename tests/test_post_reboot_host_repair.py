"""Disposable launch/package/home tests plus real admitted certificate lineage.

No actual reboot, native host, credentials, native SQL, RPC or provider is used.
The launch tests explicitly substitute the certificate/quiescence boundary;
the separate certificate tests exercise actual SQLite/startup/maintenance proof.
"""
import copy
import os
from pathlib import Path
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator import post_reboot_host_repair as repair
from orchestrator.core import Refusal, digest
from orchestrator.host_lifecycle import write_record
from orchestrator.host_runtime import file_record, stamp
import test_post_reboot_maintenance as maintenance_fixtures
import test_public_preplay_host_restart as launch_fixtures


class CertificateTest(unittest.TestCase):
    def setUp(self):
        self.f = maintenance_fixtures.RebootMaintenanceTest('runTest')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.f.apply(); self.q = self.f.q
        self.path = self.f.f.r.f.root / 'completed-maintenance.json'
        write_record(self.path, self.q)

    def test_completed_certificate_is_explicit_read_only_and_preserves_default_gate(self):
        q, registry, ledger, pins = repair.certificate(self.path)
        self.assertEqual(q, self.q); self.assertEqual(ledger.workspace_id, self.q['workspaceId'])
        self.assertEqual(len(pins), 5); self.f.conserved()
        self.assertTrue(repair.maintenance.status(q)['normalWritesBlocked'])

    def test_partial_certificate_never_grants_launch_authority(self):
        (Path(self.q['journal']) / 'result.json').unlink()
        with self.assertRaises(Refusal): repair.certificate(self.path)
        self.f.conserved()

    def test_foreign_source_scope_or_same_device_reboot_never_qualifies(self):
        altered = copy.deepcopy(self.q); altered['sourceHash'] = 'f' * 64
        other = self.path.parent / 'foreign.json'; write_record(other, altered)
        with self.assertRaises(Refusal): repair.certificate(other)
        with patch.object(repair.maintenance, 'boot_session', return_value='11111111-2222-4333-8444-555555555555'):
            with self.assertRaises(Refusal): repair.certificate(self.path)
        self.f.conserved()

    def test_maintenance_backup_or_old_usage_drift_refuses(self):
        (self.f.backup_root / 'input-0.json').write_bytes(b'{}')
        with self.assertRaises(Refusal): repair.certificate(self.path)


class QuietBoundaryTest(unittest.TestCase):
    def test_no_open_or_unknown_database_handles_can_pass(self):
        q = {'context': {'databases': {'target': {'path': '/fixture/ledger.sqlite3'}}}}
        for code, output in ((0, b'123\n'), (2, b''), (1, b'partial')):
            with patch.object(repair.restart, 'quiescent') as native, patch.object(repair.restart, 'fixed',
                    return_value=SimpleNamespace(returncode=code, stdout=output)):
                with self.assertRaises(Refusal): repair.quiet(q, {}, {})
                self.assertEqual(native.call_count, 2)


class HostRepairTest(unittest.TestCase):
    def setUp(self):
        self.f = launch_fixtures.PreplayRestartTest('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        # An explicit synthetic completed-certificate boundary. No live native
        # observations or database/admission facts are inferred by this fixture.
        self.f.binding['endpoint']['socket'] = str(Path(self.f.launch['socketDirectory']) / 'host.sock')
        self.f.binding_file.unlink(); write_record(self.f.binding_file, self.f.binding)
        self.f.binding_before = repair.restart.pin(self.f.binding_file)
        self.witness = self.f.root / 'witness'; self.witness.mkdir(mode=0o700)
        write_record(self.witness / 'report.json', {'context': {'bindingFile': str(self.f.binding_file)}})
        self.q = {'workspaceId': 'v3', 'platform': str(self.f.registry.root), 'witness': str(self.witness),
                  'context': {'brainId': self.f.brain, 'checkout': str(self.f.repo), 'root': str(self.f.ledger.root),
                      'oldDevice': self.f.repo.stat().st_dev, 'currentDevice': self.f.repo.stat().st_dev,
                      'bootedAt': time.time() + 60, 'bindingHash': digest(self.f.binding),
                      'startupReviewHash': 'a' * 64, 'sourceEpochs': [],
                      'databases': {'registry': {'path': str(self.f.registry.db)}, 'ledger': {'path': str(self.f.ledger.db)}}}}
        self.certificate = self.f.root / 'certificate.json'; write_record(self.certificate, self.q)
        for p in (patch.object(repair, 'certificate', return_value=(self.q, self.f.registry, self.f.ledger, {})),
                  patch.object(repair, 'quiet')):
            p.start(); self.addCleanup(p.stop)
        self.path = self.f.directory / 'repair.json'

    def prepare(self):
        self.preview = repair.prepare(self.certificate, self.f.old, self.f.sockets, self.f.directory)
        self.spec = repair.load(self.path)
        return self.preview

    def execute(self, error=OSError('private exec diagnostics must not leak')):
        with patch.object(repair.sys, 'platform', 'darwin'), patch.object(repair.platform, 'machine', return_value='arm64'), \
             patch.object(repair.os, 'chdir'), patch.object(repair.os, 'dup2'), \
             patch.object(repair.restart, 'process_identity', return_value='fixture-pid-birth'), \
             patch.object(repair.os, 'execve', side_effect=error) as execute:
            with self.assertRaises((Refusal, KeyboardInterrupt)):
                repair.exec_host(self.path, self.preview['reviewHash'], writers_stopped=True)
        return execute

    def test_prepare_has_no_native_effect_claim_or_binding_change(self):
        result = self.prepare()
        self.assertEqual(result['validUntil'], 'scope_changes'); self.assertFalse(result['startsHost'])
        self.assertFalse(Path(self.spec['journal']).exists())
        self.assertEqual(repair.status(self.path)['status'], 'prepared_not_submitted')
        self.assertFalse(result['boundary']['bindingInstalled']); self.f.conserved()

    def test_credentials_remain_metadata_only_and_backup_excludes_them(self):
        opened = os.open; path_open = Path.open
        def guard(path, *args, **kw):
            self.assertNotEqual(Path(path), self.f.auth); return opened(path, *args, **kw)
        def guard_path(path, *args, **kw):
            self.assertNotEqual(path, self.f.auth); return path_open(path, *args, **kw)
        with patch('os.open', side_effect=guard), patch.object(Path, 'open', guard_path): self.prepare()
        self.assertFalse((self.f.directory / 'native-home-backup/auth.json').exists()); self.f.conserved()

    def test_no_countdown_but_context_drift_invalidates_review(self):
        self.prepare()
        with patch.object(repair.time, 'time', return_value=999999999999):
            self.assertEqual(repair.preview(self.path), self.preview)
        write_record(self.f.ledger.root / 'new-unknown-claim.json', {'unknown': True})
        with self.assertRaises(Refusal): repair.validate(self.path)
        self.assertFalse(Path(self.spec['journal']).exists())

    def test_exact_new_approval_and_stopped_writers_required_before_claim(self):
        self.prepare()
        for confirmation, stopped in (('approved', True), (self.preview['reviewHash'], False)):
            with self.assertRaises(Refusal): repair.exec_host(self.path, confirmation, writers_stopped=stopped)
        self.assertFalse(Path(self.spec['journal']).exists()); self.f.conserved()

    def test_fixed_one_exec_and_permanent_claim_on_failure(self):
        self.prepare(); execute = self.execute(); self.assertEqual(execute.call_count, 1)
        binary = str(self.f.package / 'bin/codex')
        self.assertEqual(execute.call_args.args, (binary, [binary, 'app-server', '--listen',
            'unix://' + str(self.f.sockets / 'host.sock')], repair.launch.environment(self.f.launch)))
        self.assertEqual(repair.status(self.path)['status'], 'exec_failed')
        self.assertNotIn('private exec diagnostics', (Path(self.spec['journal']) / 'status.json').read_text())
        with self.assertRaises(Refusal): repair.exec_host(self.path, self.preview['reviewHash'], writers_stopped=True)
        self.f.conserved()

    def test_unknown_exec_never_retries(self):
        self.prepare(); self.execute(KeyboardInterrupt())
        self.assertEqual(repair.status(self.path)['status'], 'exec_outcome_unknown')
        with self.assertRaises(Refusal): repair.validate(self.path)
        self.f.conserved()

    def test_partial_canonical_owner_fences_alternate_directory_and_socket(self):
        self.prepare(); root = Path(self.spec['journal']); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        self.assertEqual(repair.status(self.path)['status'], 'outcome_unknown')
        other = self.f.root / 'another-review'
        with self.assertRaises(Refusal): repair.prepare(self.certificate, self.f.old, self.f.sockets, other)
        self.f.conserved()

    def test_post_claim_drift_consumes_attempt_without_exec(self):
        self.prepare(); original = repair.validate
        def altered(path, *, claimed=False):
            if claimed: raise Refusal('Synthetic boundary drift')
            return original(path)
        with patch.object(repair, 'validate', side_effect=altered), patch.object(repair.sys, 'platform', 'darwin'), \
             patch.object(repair.platform, 'machine', return_value='arm64'), patch.object(repair.os, 'execve') as execute:
            with self.assertRaises(Refusal): repair.exec_host(self.path, self.preview['reviewHash'], writers_stopped=True)
        execute.assert_not_called(); self.assertEqual(repair.status(self.path)['status'], 'outcome_unknown')
        self.f.conserved()

    def test_backup_credential_package_and_certificate_drift_refuse(self):
        self.prepare(); os.utime(self.f.auth, None)
        with self.assertRaises(Refusal): repair.validate(self.path)
        self.assertFalse(Path(self.spec['journal']).exists()); self.f.conserved()

    def test_original_failed_unknown_or_changed_endpoint_refuses(self):
        path = self.f.old / 'status.json'; value = repair.maintenance.read(path)
        path.unlink(); write_record(path, {**value, 'status': 'exec_outcome_unknown'})
        with self.assertRaises(Refusal): self.prepare()
        self.f.conserved()

    def test_old_or_nested_socket_and_aliases_refuse(self):
        for socket in (Path(self.f.launch['socketDirectory']), self.f.home):
            with self.assertRaises(Refusal): repair.prepare(self.certificate, self.f.old, socket, self.f.directory)
        self.f.conserved()

    def test_status_after_scope_loss_is_historical_and_never_calls_native_or_context(self):
        self.prepare()
        with patch.object(repair, 'certificate', side_effect=AssertionError('No context reconnection in status')), \
             patch.object(repair, 'quiet', side_effect=AssertionError('No liveness assertions in status')):
            self.assertEqual(repair.status(self.path)['status'], 'prepared_not_submitted')

    def test_protected_socket_mapping_is_new_path_not_an_invented_epoch(self):
        native = copy.deepcopy(self.f.launch)
        native['runtimePackage'].update(zip(('sourceCommit', 'sourceTree'), repair.PROTECTED_SOCKET_BUILD))
        a = repair.socket_path(native, self.f.sockets)
        b = repair.socket_path(native, native['socketDirectory'])
        self.assertNotEqual(a, b); self.assertEqual(len(a.name), 64)
        self.assertEqual(a.parent.name, 'codex-daemon-' + str(os.getuid()))
        self.assertFalse(a.exists())

    def test_stale_new_physical_path_or_lock_is_never_unlinked(self):
        self.prepare(); collision = self.f.sockets / 'host.lock'; collision.touch(mode=0o600)
        with self.assertRaises(Refusal): repair.validate(self.path)
        self.assertTrue(collision.exists()); self.assertFalse(Path(self.spec['journal']).exists())

    def test_only_closed_historical_package_device_translation_is_allowed(self):
        pin = copy.deepcopy(self.f.launch['runtimePackage']); root = self.f.package
        old = root.stat().st_dev - 17; c = {**self.q['context'], 'oldDevice': old}
        rows = [{**file_record(root, name, repair.runtime.MAX_BYTES), 'device': old} for name in repair.runtime.FILES]
        dirs = [(old, *stamp(p.stat())[1:]) for p in (root, root / 'bin')]
        pin['inventoryHash'] = digest({'files': rows, 'root': dirs[0], 'bin': dirs[1]})
        actual = repair.package_continuity(pin, c)
        self.assertEqual(actual, self.f.launch['runtimePackage'])
        with self.assertRaises(Refusal): repair.runtime.validate_pin(pin)
        with patch.object(repair.time, 'time', return_value=c['bootedAt'] + 10):
            newer = {**c, 'bootedAt': 1}
            with self.assertRaises(Refusal): repair.package_continuity(pin, newer)

