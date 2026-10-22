"""Real repair/package/home inputs with explicit synthetic OS/certificate seams.

No Codex process, native database, credential bytes or RPC is used. The full
completed-certificate reader has separate real SQLite/Git lineage coverage.
"""
import copy
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orchestrator import post_reboot_dashboard as api
from orchestrator.core import Refusal, digest
from orchestrator.host_lifecycle import write_record
import test_post_reboot_host_repair as fixtures


class FoundationTest(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.HostRepairTest('runTest'); self.h.setUp(); self.addCleanup(self.h.doCleanups)
        self.f = self.h.f
        self.h.q['context'].update(files={}, originalUsage={'preserved': 'synthetic fixture'},
            originalReadinessCommand=self.f.cid, historicalObservedAt=1, bootSessionUuid='fixture-boot')
        report = self.h.witness / 'report.json'
        report.unlink(); write_record(report, {'context': {'bindingFile': str(self.f.binding_file), 'nativeTurnId': self.f.turn}})
        self.h.prepare(); self.s = self.h.spec
        root = Path(self.s['journal']); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        write_record(root / 'intent.json', {'kind': api.repair.KIND, 'specHash': digest(self.s),
                                           'reviewHash': api.repair.review_hash(self.s)})
        (root / 'exec.claim').touch(mode=0o600)
        self.state = {'kind': api.repair.KIND, 'specHash': digest(self.s), 'status': 'exec_boundary_issued',
            'pid': 987654321, 'parentPid': 2, 'processIdentity': '987654321 fixture-birth', 'at': 1, 'boundary': api.repair.BOUNDARY}
        write_record(root / 'status.json', self.state)
        # Synthetic kernel socket inspection: a symlink relationship plus a
        # fixed OS result. inspect_endpoint's real socket privacy tests remain
        # in test_native_read_client and the separate review/socket fixture.
        self.physical = self.f.sockets / 'physical.sock'; self.physical.touch(mode=0o600)
        (self.f.sockets / 'host.sock').symlink_to(self.physical)
        original_map = api.repair.socket_path
        patches = [patch.object(api.repair, 'socket_path', side_effect=lambda s, d:
                    self.physical if Path(d) == self.f.sockets else original_map(s, d)),
            patch.object(api.repair.restart, 'live_process'), patch.object(api.repair.restart, 'process_absent', return_value=True),
            patch.object(api.repair.restart, 'fixed', return_value=SimpleNamespace(returncode=0, stdout=('n' + str(self.physical) + '\n').encode())),
            patch.object(api, 'inspect_endpoint', return_value={**self.f.binding['endpoint'], 'socket': str(self.physical),
                'socketIdentity': {'device': 1, 'inode': 9, 'owner': os.getuid(), 'mode': 0o600, 'changedNs': 1}})]
        for p in patches: p.start(); self.addCleanup(p.stop)
        self.source = Path(api.__file__).resolve().parent.parent

    def foundation(self):
        return api.foundation(self.h.path, self.source)

    def test_full_repair_and_history_relationship_is_revalidated_without_a_native_client(self):
        with patch.object(api.repair.restart, 'RestartReadProxy', side_effect=AssertionError('No native connection in foundation')):
            c, q, _, ledger = self.foundation()
        self.assertEqual(c['brainId'], self.f.brain); self.assertEqual(q, self.h.q)
        self.assertEqual(ledger, self.f.ledger); self.assertEqual(c['latestTurnId'], self.f.turn)
        self.f.conserved()

    def test_credential_bytes_never_opened_and_epoch_drift_refuses(self):
        opened, path_open = os.open, Path.open
        def guard(path, *args, **kw):
            self.assertNotEqual(Path(path), self.f.auth); return opened(path, *args, **kw)
        def guard_path(path, *args, **kw):
            self.assertNotEqual(path, self.f.auth); return path_open(path, *args, **kw)
        with patch('os.open', side_effect=guard), patch.object(Path, 'open', guard_path): self.foundation()
        os.utime(self.f.auth, None)
        with self.assertRaises(Refusal): self.foundation()
        self.f.conserved()

    def test_failed_unknown_or_partial_launch_never_becomes_dashboard_authority(self):
        path = Path(self.s['journal']) / 'status.json'
        for outcome in ('exec_failed', 'exec_outcome_unknown'):
            write_record(path, {**self.state, 'status': outcome})
            with self.assertRaises(Refusal): self.foundation()
        path.unlink()
        with self.assertRaises(Refusal): self.foundation()
        self.f.conserved()

    def test_extra_claim_record_or_wrong_launch_intent_refuses(self):
        root = Path(self.s['journal']); write_record(root / 'unknown.json', {'partial': True})
        with self.assertRaises(Refusal): self.foundation()
        (root / 'unknown.json').unlink(); write_record(root / 'intent.json', {'foreign': True})
        with self.assertRaises(Refusal): self.foundation()
        self.f.conserved()

    def test_pid_reuse_or_retired_pid_present_never_signals_any_process(self):
        with patch.object(api.repair.restart, 'live_process', side_effect=Refusal('Synthetic reused PID')):
            with self.assertRaises(Refusal): self.foundation()
        with patch.object(api.repair.restart, 'process_absent', return_value=False):
            with self.assertRaises(Refusal): self.foundation()
        self.f.conserved()

    def test_missing_process_socket_ownership_or_changed_alias_refuses(self):
        with patch.object(api.repair.restart, 'fixed', return_value=SimpleNamespace(returncode=0, stdout=b'foreign')):
            with self.assertRaises(Refusal): self.foundation()
        alias = self.f.sockets / 'host.sock'; alias.unlink(); alias.symlink_to(self.f.auth)
        with self.assertRaises(Refusal): self.foundation()
        self.f.conserved()

    def test_reviewed_socket_directory_epoch_cannot_be_replaced_or_weakened(self):
        self.f.sockets.chmod(0o755)
        with self.assertRaises(Refusal): self.foundation()
        self.f.sockets.chmod(0o700)
        self.f.conserved()

    def test_original_source_bytes_must_be_explicitly_qualified_not_imported(self):
        with patch.object(api.repair.maintenance.startup.prior, 'source_proof', return_value={
                'root': str(self.source), 'sourceHash': 'f' * 64, 'epochHash': 'f' * 64}):
            with self.assertRaises(Refusal): self.foundation()
        self.f.conserved()

    def test_native_home_backup_and_original_config_or_history_drift_refuse(self):
        original = self.f.home / 'config.toml'; original.write_text('changed')
        with self.assertRaises(Refusal): self.foundation()
        self.f.conserved()


if __name__ == '__main__': unittest.main()
