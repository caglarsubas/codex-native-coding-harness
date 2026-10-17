"""Disposable forward-only maintenance lineage; no native host/RPC or credentials."""
import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from orchestrator import public_host_restart as shared, public_preplay_host_restart as repair
from orchestrator import public_preplay_host_lineage as lineage
from orchestrator.core import Refusal,canonical,digest
from orchestrator.host_lifecycle import write_record
import test_public_preplay_host_restart as fixtures


class ExecBoundary(BaseException): pass


class PreplayLineageTest(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PreplayRestartTest('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.f.prepare(); self.first=copy.deepcopy(self.f.spec)
        self.issue(self.f.path,self.f.hash,222222221)
        self.previous=self.f.directory/'attempt'
        self.current=self.f.root/'current-binding.json'
        current=copy.deepcopy(self.f.binding); current['endpoint']['socket']=str(self.f.sockets/'retired.sock')
        write_record(self.current,current)
        self.directory=self.f.root/'successor'; self.path=self.directory/'restart.json'
        self.sockets=self.f.root/'successor-ipc'; self.sockets.mkdir(mode=0o700)
        self.absence=patch.object(shared,'process_absent',return_value=True); self.absence_mock=self.absence.start()
        self.addCleanup(self.absence.stop)

    def issue(self,path,review,pid):
        with patch.object(repair.sys,'platform','darwin'),patch.object(repair.platform,'machine',return_value='arm64'),\
             patch.object(repair.os,'chdir'),patch.object(repair.os,'dup2'),patch.object(repair.os,'getpid',return_value=pid),\
             patch.object(shared,'process_identity',return_value=str(pid)+' disposable-born'),\
             patch.object(repair.os,'execve',side_effect=ExecBoundary) as execute:
            with self.assertRaises(ExecBoundary): repair.exec_host(self.f.registry,self.f.ledger,path,review)
        self.assertEqual(execute.call_count,1)
        return execute

    def prepare(self):
        report=repair.prepare(self.f.registry,self.f.ledger,self.previous,self.current,self.sockets,self.directory,successor=True)
        self.spec=repair.load_spec(self.path); self.hash=report['reviewHash']; return report

    def test_explicit_new_mode_preserves_original_claim_and_uses_actual_predecessor(self):
        original=shared.pin(self.first['fencePath']); report=self.prepare()
        self.assertEqual(report['kind'],repair.SUCCESSOR_KIND); self.assertEqual(report['validity'],'until_scope_changes')
        self.assertFalse(report['startsHost']); self.assertEqual(report['boundary'],repair.BOUNDARY)
        self.assertEqual(self.spec['scope']['predecessorProcess']['pid'],222222221)
        self.assertNotEqual(self.spec['fencePath'],self.first['fencePath'])
        self.assertEqual(shared.pin(self.first['fencePath']),original); self.f.conserved()

    def test_v1_never_automatically_adopts_a_successor(self):
        with self.assertRaisesRegex(Refusal,'initial fresh'):
            repair.prepare(self.f.registry,self.f.ledger,self.previous,self.current,self.sockets,self.directory)
        with self.assertRaisesRegex(Refusal,'issued restart'):
            repair.prepare(self.f.registry,self.f.ledger,self.f.old,self.current,self.sockets,self.directory,successor=True)
        self.assertFalse(self.directory.exists())

    def test_exact_new_review_required_and_exec_is_still_fixed_launch_only(self):
        self.prepare()
        with self.assertRaises(Refusal): repair.exec_host(self.f.registry,self.f.ledger,self.path,self.f.hash)
        execute=self.issue(self.path,self.hash,222222222)
        binary=str(self.f.package/'bin/codex')
        self.assertEqual(execute.call_args.args,(binary,[binary,'app-server','--listen','unix://'+str(self.sockets/'host.sock')],
            fixtures.launch.environment(self.f.launch)))
        self.assertEqual(repair.status(self.path)['status'],'exec_boundary_issued'); self.f.conserved()

    def test_failed_unknown_and_missing_status_are_never_predecessor_authority(self):
        path=self.previous/'status.json'; original=lineage.read(path)
        for status in ('exec_failed','exec_outcome_unknown','made_up'):
            value={**original,'status':status}; path.write_text(canonical(value))
            with self.subTest(status=status),self.assertRaises(Refusal): self.prepare()
        path.write_text(canonical(original)); path.unlink()
        with self.assertRaises(OSError): self.prepare()
        self.assertFalse(self.directory.exists())

    def test_missing_intent_claim_or_corrupt_archive_refuses(self):
        (self.previous/'exec.claim').unlink()
        with self.assertRaises(OSError): self.prepare()
        (self.previous/'exec.claim').touch(mode=0o600)
        (self.f.directory/'native-home-backup/state_5.sqlite').write_bytes(b'changed')
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists())

    def test_touched_ancestor_cannot_reset_or_rebind_lineage(self):
        self.prepare(); os.utime(self.f.old/'status.json',None)
        with self.assertRaises(Refusal): repair.validate(self.f.registry,self.f.ledger,self.path)
        self.assertFalse(Path(self.spec['fencePath']).exists()); self.f.conserved()

    def test_live_reused_or_unknown_pid_and_home_handles_refuse_before_copy(self):
        self.absence_mock.return_value=False
        with self.assertRaisesRegex(Refusal,'PID'): self.prepare()
        self.absence_mock.return_value=True; self.f.quiescent.side_effect=Refusal('Unknown home handles')
        with self.assertRaisesRegex(Refusal,'home handles'): self.prepare()
        self.assertFalse(self.directory.exists())

    def test_current_binding_brain_policy_and_package_cannot_change(self):
        current=lineage.read(self.current); changed=copy.deepcopy(current)
        changed['brains'][self.f.brain]['projectId']='foreign'; self.current.write_text(canonical(changed))
        with self.assertRaises(Refusal): self.prepare()
        self.current.write_text(canonical(current)); self.prepare(); os.utime(self.current,None)
        with self.assertRaises(Refusal): repair.validate(self.f.registry,self.f.ledger,self.path)

    def test_preserve_consumed_inspection_but_refuse_partial_readiness_or_restart_claims(self):
        inspection=self.f.ledger.root/'public-preplay-load-existing.claim'
        write_record(inspection,{'consumed':True,'terminalSafety':'unknown'}); old=shared.pin(inspection)
        self.prepare(); self.assertEqual(shared.pin(inspection),old)
        write_record(self.f.ledger.root/'readiness-owned-partial.claim',{'unresolved':True})
        with self.assertRaises(Refusal): repair.validate(self.f.registry,self.f.ledger,self.path)
        self.assertEqual(shared.pin(inspection),old)

    def test_unrelated_restart_fence_cannot_be_hidden_by_sidecar_filter(self):
        write_record(self.f.ledger.root/(repair.PREFIX+'foreign.json'),{'partial':True})
        with self.assertRaisesRegex(Refusal,'unrelated or partial'): self.prepare()
        self.assertFalse(self.directory.exists())

    def test_changed_original_request_database_or_stop_fences_maintenance(self):
        self.prepare(); self.f.mutate_command(lambda c:c.update(result='changed'))
        with self.assertRaises(Refusal): repair.validate(self.f.registry,self.f.ledger,self.path)
        self.assertFalse(Path(self.spec['fencePath']).exists())

    def test_credential_bytes_never_opened_and_metadata_drift_fences_exec(self):
        real=os.open
        def guard(path,*args,**kwargs):
            self.assertNotEqual(Path(path),self.f.auth); return real(path,*args,**kwargs)
        with patch('os.open',side_effect=guard): self.prepare()
        self.assertFalse((self.directory/'native-home-backup/auth.json').exists())
        os.utime(self.f.auth,None)
        with self.assertRaises(Refusal): repair.validate(self.f.registry,self.f.ledger,self.path)
        self.f.conserved()

    def test_scope_bound_review_is_not_a_timer_and_historical_status_is_file_only(self):
        self.prepare()
        with patch.object(repair.time,'time',return_value=999999999999):
            self.assertEqual(repair.preview(self.f.registry,self.f.ledger,self.path)['reviewHash'],self.hash)
        self.issue(self.path,self.hash,222222222)
        with patch.object(shared,'source_tree',side_effect=AssertionError('No upgrade on history')):
            self.assertFalse(repair.status(self.path)['hostReady'])

    def test_an_issued_successor_can_be_next_predecessor_but_an_ancestor_cannot_replay(self):
        self.prepare(); self.issue(self.path,self.hash,222222222)
        with self.assertRaisesRegex(Refusal,'consumed'):
            repair.prepare(self.f.registry,self.f.ledger,self.previous,self.current,self.sockets,self.f.root/'another',successor=True)
        self.previous=self.directory/'attempt'; self.directory=self.f.root/'third'; self.path=self.directory/'restart.json'
        self.sockets=self.f.root/'third-ipc'; self.sockets.mkdir(mode=0o700)
        self.prepare(); self.assertEqual(self.spec['scope']['predecessorProcess']['pid'],222222222)
        self.f.conserved()

    def test_partial_new_claim_and_failure_never_enable_another_review(self):
        self.prepare()
        write_record(Path(self.spec['fencePath']),{'kind':repair.SUCCESSOR_KIND,'partial':True})
        with self.assertRaises(Refusal): repair.validate(self.f.registry,self.f.ledger,self.path)
        with self.assertRaisesRegex(Refusal,'consumed'):
            repair.prepare(self.f.registry,self.f.ledger,self.previous,self.current,self.sockets,self.f.root/'another',successor=True)

    def test_historical_binding_and_snapshot_pins_are_not_renewed(self):
        self.prepare(); os.utime(self.f.binding_file,None)
        with self.assertRaises(Refusal): repair.validate(self.f.registry,self.f.ledger,self.path)
        self.assertFalse(Path(self.spec['fencePath']).exists())

    def test_cycle_and_depth_bounds_are_checked_without_native_connection(self):
        with self.assertRaisesRegex(Refusal,'cycle/depth'):
            lineage.issued(self.previous,self.f.ledger,tuple('node'+str(i) for i in range(7)))
        original=lineage.read(self.f.path)
        cyclic={**original,'version':2,'kind':repair.SUCCESSOR_KIND,'previousAttempt':str(self.previous)}
        self.f.path.write_text(canonical(cyclic))
        with self.assertRaisesRegex(Refusal,'cycle/depth'): self.prepare()
        self.assertFalse(self.directory.exists())

    def test_old_socket_or_review_location_is_not_reusable(self):
        with self.assertRaises(Refusal):
            repair.prepare(self.f.registry,self.f.ledger,self.previous,self.current,self.f.sockets,self.directory,successor=True)
        with self.assertRaises(Refusal):
            repair.prepare(self.f.registry,self.f.ledger,self.previous,self.current,self.sockets,self.f.directory/'nested',successor=True)
        self.assertFalse(self.directory.exists())

    def test_failed_successor_exec_stays_consumed_and_cannot_become_next_predecessor(self):
        self.prepare()
        with patch.object(repair.sys,'platform','darwin'),patch.object(repair.platform,'machine',return_value='arm64'),\
             patch.object(repair.os,'chdir'),patch.object(repair.os,'dup2'),\
             patch.object(repair.os,'execve',side_effect=OSError('fixture failure')):
            with self.assertRaises(Refusal): repair.exec_host(self.f.registry,self.f.ledger,self.path,self.hash)
        self.assertEqual(repair.status(self.path)['status'],'exec_failed')
        with self.assertRaises(Refusal): lineage.issued(self.directory/'attempt',self.f.ledger)
        self.assertTrue(Path(self.spec['fencePath']).exists()); self.f.conserved()

    def test_drift_after_permanent_claim_never_executes_or_rearms(self):
        self.prepare(); original=repair.validate
        def drift(*args,**kwargs):
            if kwargs.get('claimed'): os.utime(self.f.auth,None)
            return original(*args,**kwargs)
        with patch.object(repair,'validate',side_effect=drift),patch.object(repair.sys,'platform','darwin'),\
             patch.object(repair.platform,'machine',return_value='arm64'),patch.object(repair.os,'execve') as execute:
            with self.assertRaises(Refusal): repair.exec_host(self.f.registry,self.f.ledger,self.path,self.hash)
        execute.assert_not_called(); self.assertTrue((self.directory/'attempt/exec.claim').exists())
        self.assertEqual(repair.status(self.path)['status'],'outcome_unknown'); self.f.conserved()


if __name__=='__main__': unittest.main()
