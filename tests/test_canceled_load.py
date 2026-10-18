"""One new reviewed load; old Play/usage/claims/bindings are immutable."""
import copy
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from orchestrator import canceled_load as api, public_pilot_inspection as inspection
from orchestrator import canceled_host_review as host
from orchestrator.core import Refusal, canonical, digest
from orchestrator.host_lifecycle import write_record
from orchestrator.partial_admission import database_proof
from test_native_policy_evidence import response as policy
import test_canceled_host_review as hosts
import test_standard_run_mailbox as mailbox


class CanceledLoadTest(unittest.TestCase):
    def setUp(self):
        base = mailbox.RunMailboxTest.setUp
        def setup(f):
            base(f)
            f.binding['endpoint'].update(socket=str(f.root/'old-ipc/host.sock'),
                socketIdentity={'fixture':'old'},serverIdentityHash='d'*64)
        with patch.object(mailbox.RunMailboxTest,'setUp',setup):
            self.h = hosts.CanceledHostTest('runTest'); self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.f,self.registry,self.ledger = self.h.f,self.h.registry,self.h.ledger
        self.h.prepare(); self.launch = host.load(self.h.file)
        q = self.launch; claim = Path(q['fencePath']); claim.parent.mkdir(mode=0o700); claim.mkdir(mode=0o700)
        write_record(claim/'intent.json',{'kind':host.KIND,'reviewHash':host.review_hash(q)})
        identity = '234567890 Sun Oct 18 15:00:00 2026'
        write_record(claim/'exec.claim.json',{'kind':host.KIND,'reviewHash':host.review_hash(q),
            'pid':234567890,'processIdentity':identity,'at':1})
        binary = str(Path(q['launchSpec']['runtimePackage']['root'])/'bin/codex')
        write_record(claim/'issued.json',{'kind':host.KIND,'status':'exec_boundary_issued',
            'pid':234567890,'processIdentity':identity,'reviewHash':host.review_hash(q),
            'argv':[binary,'app-server','--listen','unix://'+str(self.h.sockets/'host.sock')],
            'cwd':str(self.f.repo),'boundary':dict(host.BOUNDARY)})
        (self.h.sockets/'host.sock').write_bytes(b'fake socket metadata only')
        self.endpoint={'executable':binary,'sha256':q['launchSpec']['runtimePackage']['executableHash'],
            'socket':str(self.h.sockets/'host.sock'),'socketIdentity':{'fixture':'new'},'serverIdentityHash':'d'*64}
        for p in (patch.object(api.shared,'process_absent',return_value=True),
                  patch.object(api.shared,'live_process'),patch.object(api,'inspect_endpoint',return_value=self.endpoint)):
            p.start(); self.addCleanup(p.stop)
        self.candidate=self.f.root/'load-candidate.json'
        write_record(self.candidate,api.provenance(self.registry,self.ledger,self.h.file)['scope']['binding'])
        self.q=api.prepare(self.registry,self.ledger,self.h.file,self.candidate)['request']
        self.backup=self.f.root/'load-backup'; api.backup(self.registry,self.ledger,self.q,self.backup,writers_stopped=True)
        self.baseline=[database_proof(p) for p in (self.registry.db,self.ledger.db)]
        self.sidecars=api.control.old.sidecars(self.ledger)
        self.binding_epoch=api.control.old.prior.file_epoch(self.h.old.binding_file)
        self.calls=[]; self.loaded=False; self.fail_load=False; self.bad_policy=False; self.terminals=[]
        self.activity=None; self.turn=None; self.auth=True; self.mcp=[]; self.callback=None
        outer=self
        def rpc(proxy,method,params):
            outer.calls.append((method,copy.deepcopy(params)))
            if outer.callback: outer.callback(method,params)
            scope=outer.q['provenance']['scope']
            if method=='project/read': return {'project':{'id':scope['projectId'],'roots':[{'path':scope['cwd']}]}}
            if method=='thread/read': return {'thread':{'id':scope['brainId'],'projectId':scope['projectId'],
                'cwd':scope['cwd'],'status':outer.activity or {'type':'idle' if outer.loaded else 'notLoaded'}}}
            if method=='thread/turns/list': return {'data':[{'id':outer.turn or scope['latestTurnId'],'status':'interrupted'}],'nextCursor':None}
            if method=='mcpServerStatus/list': return {'data':outer.mcp,'nextCursor':None}
            if method=='account/read': return {'account':{'type':'chatgpt'} if outer.auth else None,'requiresOpenaiAuth':True}
            if method=='thread/backgroundTerminals/list': return {'data':outer.terminals,'nextCursor':None}
            if method=='thread/effectivePolicy/read':
                if not outer.loaded: return {'version':1,'threadId':scope['brainId'],'policy':None}
                value=policy(scope['brainId'],scope['cwd'])
                if outer.bad_policy: value['policy']['codeModeOffEnforced']=False
                return value
            if method=='thread/resume':
                outer.loaded=True
                outer.assertTrue((Path(outer.q['journal'])/'load.claim.json').exists())
                if outer.fail_load: raise OSError('Lost acknowledgement; private body must not leak')
                return {'thread':{'id':scope['brainId'],'cwd':scope['cwd'],'turns':[]}}
            raise AssertionError('Forbidden native method '+method)
        def enter(p): p.process=object(); return p
        def close(p,*_): p.process=None
        for p in (patch.object(inspection.ReadProxy,'__enter__',enter),
                  patch.object(inspection.ReadProxy,'__exit__',close),patch.object(inspection.ReadProxy,'_rpc',rpc)):
            p.start(); self.addCleanup(p.stop)

    def apply(self,q=None,confirmation=None):
        q=q or self.q
        return api.confirm(self.registry,self.ledger,q,confirmation or digest(q),writers_stopped=True,backup_root=self.backup)

    def conserved(self):
        self.assertEqual(self.baseline,[database_proof(p) for p in (self.registry.db,self.ledger.db)])
        self.assertEqual(self.sidecars,api.control.old.sidecars(self.ledger))
        self.assertEqual(self.binding_epoch,api.control.old.prior.file_epoch(self.h.old.binding_file))
        self.assertEqual(api.control.old.status(self.ledger)['status'],'not_recorded')

    def test_exact_new_load_once_with_actual_policy_tracker_and_unchanged_originals(self):
        result=self.apply(); self.assertEqual(result['status'],'load_observed_idle')
        self.assertEqual(api.status(self.q),result)
        methods=[m for m,_ in self.calls]; self.assertEqual(methods.count('thread/resume'),1)
        self.assertFalse(any(m in methods for m in ('turn/start','turn/interrupt','thread/subscribe')))
        self.assertEqual(next(p for m,p in self.calls if m=='thread/resume'),inspection.load_params(self.q['provenance']['scope']))
        self.assertEqual(result['boundary'],api.BOUNDARY); self.conserved()

    def test_canonical_parent_is_flushed_before_any_native_connection(self):
        flushed=[]; actual=api.sync_directory
        def flush(path): flushed.append(Path(path)); return actual(path)
        enter=inspection.ReadProxy.__enter__
        def checked(p):
            root=Path(self.q['journal'])
            self.assertIn(root.parent.parent,flushed); self.assertIn(root.parent,flushed)
            self.assertTrue((root/'intent.json').exists()); return enter(p)
        with patch.object(api,'sync_directory',flush),patch.object(inspection.ReadProxy,'__enter__',checked):
            self.assertEqual(self.apply()['status'],'load_observed_idle')
        self.conserved()

    def test_prepare_and_status_are_file_only_without_countdown(self):
        with patch.object(inspection,'InspectionProxy',side_effect=AssertionError('No native connection')):
            out=api.prepare(self.registry,self.ledger,self.h.file,self.candidate)
            self.assertEqual(out['validUntil'],'scope_changes'); self.assertEqual(out['request'],self.q)
            self.assertEqual(api.status(self.q)['status'],'not_submitted')
        self.assertEqual(self.calls,[]); self.conserved()

    def test_wrong_hash_or_missing_backup_cannot_claim(self):
        with self.assertRaises(Refusal): self.apply(confirmation='f'*64)
        with self.assertRaises(Refusal): api.confirm(self.registry,self.ledger,self.q,digest(self.q))
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.calls,[]); self.conserved()

    def test_unknown_ack_consumes_canonical_load_without_retry_or_migration(self):
        self.fail_load=True
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        with self.assertRaises((Refusal,OSError)): self.apply()
        with self.assertRaises(Refusal): api.prepare(self.registry,self.ledger,self.h.file,self.candidate)
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1)
        self.assertNotIn('private body',canonical(api.status(self.q))); self.conserved()

    def test_native_active_unloaded_policy_and_changed_latest_turn_refuse(self):
        self.activity={'type':'active','activeFlags':['waitingOnApproval']}
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.calls]); self.conserved()

    def test_already_loaded_is_not_adopted_or_reloaded(self):
        self.loaded=True
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.calls]); self.conserved()

    def test_changed_latest_ended_turn_never_loads(self):
        self.turn='foreign-ended-turn'
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.calls]); self.conserved()

    def test_unknown_tracker_after_load_is_not_qualified(self):
        self.terminals=None
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown'); self.conserved()

    def test_wrong_policy_after_load_is_not_qualified_or_retried(self):
        self.bad_policy=True
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown'); self.conserved()

    def test_missing_authentication_never_logs_in_or_loads(self):
        self.auth=False
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.calls]); self.conserved()

    def test_unknown_mcp_inventory_refuses_without_load(self):
        self.mcp=[{'name':'unreviewed-server'}]
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.calls]); self.conserved()

    def test_candidate_or_package_epoch_drift_refuses_before_claim(self):
        os.utime(self.candidate,None)
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(Path(self.q['journal']).exists()); self.conserved()

    def test_corrupt_backup_refuses_before_claim(self):
        (self.backup/'private-0.bin').write_bytes(b'changed')
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(Path(self.q['journal']).exists()); self.conserved()

    def test_backup_cannot_write_inside_original_ledger_home_or_checkout(self):
        for root in (self.ledger.root,self.registry.root,self.f.home,self.f.repo,self.h.directory):
            target=root/'forbidden-backup'
            with self.subTest(root=root),self.assertRaises(Refusal):
                api.backup(self.registry,self.ledger,self.q,target,writers_stopped=True)
            self.assertFalse(target.exists())
        self.conserved()

    def test_archive_path_substitution_and_credential_candidate_refuse_before_read(self):
        q=copy.deepcopy(self.launch); q['homeSnapshotPin']['path']=str(self.f.home/'auth.json')
        self.h.file.write_text(canonical(q))
        with self.assertRaises(Refusal): api.provenance(self.registry,self.ledger,self.h.file)
        self.h.file.write_text(canonical(self.launch))
        with self.assertRaises(Refusal): api.prepare(self.registry,self.ledger,self.h.file,self.f.home/'auth.json')
        self.assertEqual(self.calls,[]); self.conserved()

    def test_actual_process_or_package_drift_refuses_without_native_connection(self):
        with patch.object(api.shared,'live_process',side_effect=Refusal('PID epoch changed')):
            with self.assertRaises(Refusal): self.apply()
        os.utime(self.f.root/'new-package/source.bundle',None)
        with self.assertRaises(Refusal): self.apply()
        self.assertEqual(self.calls,[]); self.conserved()

    def test_interrupted_proxy_close_never_claims_current_connection_closed(self):
        def close(p,*_): raise OSError('unknown proxy exit')
        with patch.object(inspection.ReadProxy,'__exit__',close): result=self.apply()
        self.assertEqual(result['status'],'consumed_outcome_unknown')
        self.assertFalse(result['connectionClosed']); self.assertEqual(api.status(self.q),result)
        self.conserved()

    def test_alternate_journal_cannot_bypass_canonical_claim(self):
        q=copy.deepcopy(self.q); q['journal']+='different'
        with self.assertRaises(Refusal): self.apply(q)
        self.assertEqual(self.calls,[]); self.conserved()

    def test_partial_journal_is_not_repaired_or_removed(self):
        root=Path(self.q['journal']); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        with self.assertRaises(OSError): self.apply()
        with self.assertRaises(OSError): api.status(self.q)
        self.assertEqual(self.calls,[]); self.conserved()

    def test_issued_host_identity_failure_and_failed_exec_refuse(self):
        claim=Path(self.launch['fencePath'])
        write_record(claim/'failed-or-unknown.json',{'status':'unknown'})
        with self.assertRaises(Refusal): api.prepare(self.registry,self.ledger,self.h.file,self.candidate)
        self.assertEqual(self.calls,[]); self.conserved()

    def test_native_credentials_are_metadata_only(self):
        original=Path.open
        def guarded(path,*args,**kw):
            self.assertNotEqual(path,self.f.home/'auth.json'); return original(path,*args,**kw)
        with patch.object(Path,'open',guarded): self.assertEqual(self.apply()['status'],'load_observed_idle')
        self.conserved()

    def test_changed_retained_observation_cannot_claim_success(self):
        self.apply(); (Path(self.q['journal'])/'observation.json').write_text('{}')
        with self.assertRaises(Refusal): api.status(self.q)
        self.conserved()

    def test_missing_original_load_claim_cannot_retain_a_qualified_outcome(self):
        self.apply(); (Path(self.q['journal'])/'load.claim.json').unlink()
        with self.assertRaises((Refusal,OSError)): api.status(self.q)
        with self.assertRaises((Refusal,OSError)): self.apply()
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1); self.conserved()

    def test_external_stop_before_load_wins_without_cancel_or_replay(self):
        def stop(method,params):
            self.callback=None
            write_record(Path(self.q['journal'])/'stop.json',{'ownerStop':True})
        self.callback=stop
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.calls]); self.conserved()

    def test_concurrent_confirmations_have_only_one_load_owner(self):
        results=[]
        def run():
            try: results.append(self.apply()['status'])
            except (OSError,Refusal): results.append('refused')
        threads=[threading.Thread(target=run) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(15); self.assertFalse(thread.is_alive())
        self.assertCountEqual(results,['load_observed_idle','refused'])
        self.assertEqual([m for m,_ in self.calls].count('thread/resume'),1); self.conserved()


if __name__=='__main__': unittest.main()
