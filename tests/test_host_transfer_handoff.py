"""One new destination, continuous ownership, no old-request/usage rewriting."""
import copy
import json
import os
from pathlib import Path
import threading
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from orchestrator import host_transfer_handoff as api, canceled_continuation as planning
from orchestrator.core import Refusal,digest
from orchestrator.host_lifecycle import write_record
from test_native_policy_evidence import response as policy
from test_public_host_runtime import package_fixture
import test_maintenance_load as fixtures

ProductionDestination=api.DestinationProxy


class HostTransferTest(unittest.TestCase):
    def history_rows(self):
        return [{'type':'session_meta','payload':{'id':self.f.brain,'cwd':str(self.f.repo)}},
            {'type':'event_msg','payload':{'type':'task_complete','turn_id':self.f.turn}}]

    def setUp(self):
        self.m=fixtures.MaintenanceLoadTest('runTest'); self.m.setUp(); self.addCleanup(self.m.doCleanups)
        self.assertEqual(self.m.apply()['status'],'maintenance_load_observed_idle')
        self.registry,self.ledger,self.f=self.m.registry,self.m.ledger,self.m.f
        self.file=self.f.root/'completed-maintenance.json'; write_record(self.file,self.m.q)
        self.maintenance_pins=api.phase.lifecycle.inventory(self.m.q['journal'])
        self.now=self.m.parent['original']['run']['expiresAt']+1
        clock=patch('time.time',side_effect=lambda:self.now); clock.start(); self.addCleanup(clock.stop)
        self.home=self.f.root/'destination-home'; self.home.mkdir(mode=0o700)
        write_record(self.home/'auth.json',{'fixture':'never_read_credentials'})
        (self.home/'config.toml').write_text(api.launch.CONFIG); (self.home/'config.toml').chmod(0o600)
        self.source_home=self.m.l.f.home
        self.history=self.source_home/'sessions'/('export-'+self.f.brain+'.jsonl')
        self.rows=self.history_rows()
        self.history.write_text(''.join(json.dumps(r)+'\n' for r in self.rows)); self.history.chmod(0o600)
        self.original_history=self.history.read_bytes()
        self.source=copy.deepcopy(self.m.parent['candidateBinding'])
        self.destination=copy.deepcopy(self.source); self.destination['endpoint']['socket']=str(self.f.root/'destination.sock')
        record=self.destination['brains'][self.f.brain]
        record['identityTransferEvidence']={'protocol':api.transfer.KIND,
            **{k:self.m.l.h.package[k] for k in ('sourceCommit','sourceTree')}}
        self.candidate=self.f.root/'destination-binding.json'; write_record(self.candidate,self.destination)
        self.manifest=self.f.root/'destination-launch.json'; write_record(self.manifest,{'fixture':'issued launch'})
        self.process_record=self.f.root/'destination-process.json'; write_record(self.process_record,{'fixture':'original process'})
        self.attempt=self.f.root/'destination-attempt'; self.attempt.mkdir(mode=0o700)
        self.host={'manifest':str(self.manifest),'attempt':str(self.attempt),'processRecord':str(self.process_record),
            'pins':{str(p):planning.pin(p) for p in (self.manifest,self.process_record)},
            'spec':{'cwd':str(self.f.repo),'runtimePackage':self.m.l.h.package},
            'process':{'pid':234567891,'parentPid':1,'processIdentity':'234567891 fixture'},
            'home':str(self.home),'credentialMetadata':api.credentials(self.home)}
        self.project={'id':self.f.project,'roots':[{'path':str(self.f.repo)}],'name':'Preserved project',
            'metadata':{},'position':0,'createdAt':1,'updatedAt':1,'recencyAt':None}
        self.thread={'id':self.f.brain,'sessionId':self.f.brain,'projectId':self.f.project,'cwd':str(self.f.repo),
            'status':{'type':'notLoaded'},'path':str(self.history),
            'turns':[{'id':self.f.turn,'status':'interrupted','items':[]}]}
        self.fail_at=None; self.receipt=True; self.permission=False; self.auth=True; self.auth_plan='pro'
        self.bad_policy=False; self.terminals=[]; self.callback=None; self.workers=[]; self.calls=[]
        owner=self
        class Source:
            def __init__(self,binding,brain):
                self.initialization={'codexHome':str(owner.source_home)}; self.binding=binding
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def _rpc(self,method,params):
                owner.calls.append(('source',method,copy.deepcopy(params)))
                if method=='project/read': return {'project':copy.deepcopy(owner.project)}
                if method=='thread/read': return {'thread':copy.deepcopy(owner.thread)}
                raise AssertionError('Source must never load/write/create')
        class Destination:
            instances=[]
            def __init__(self,q):
                self.q=q; self.endpoint=q['candidateBinding']['endpoint']; self.process=SimpleNamespace(poll=lambda:None)
                self.initialization={'codexHome':str(owner.home)}; self.restored=self.loaded=self.assigned=False
                self.target=None; self._early_completion=None; self.turn=str(uuid.uuid4()); self.instances.append(self)
            def __enter__(self): return self
            def __exit__(self,*_): self.process=None
            def allow(self,method,params): pass
            def _rpc(self,method,params):
                owner.calls.append(('destination',method,copy.deepcopy(params)))
                if owner.callback: owner.callback(self,method,params)
                if method==owner.fail_at: raise OSError('Unknown metadata or turn outcome; never retry')
                root=api.phase.owner_root(self.q)
                if method=='account/read': return {'requiresOpenaiAuth':True,'account':{'type':'chatgpt','planType':owner.auth_plan} if owner.auth else None}
                if method in ('thread/loaded/list','thread/list'): return {'data':[],'nextCursor':None}
                if method=='mcpServerStatus/list': return {'data':[],'nextCursor':None}
                if method=='project/list': return {'data':[owner.project] if self.restored else [],'nextCursor':None}
                if method=='project/restoreMetadata':
                    owner.assertTrue((root/'restore.claim.json').exists()); self.restored=True
                    return {'version':1,'project':dict(owner.project,recencyAt=None)}
                if method=='thread/resume':
                    owner.assertTrue((root/'load.claim.json').exists()); self.loaded=True; self.target=Path(params['path'])
                    return {'thread':{'id':owner.f.brain,'cwd':str(owner.f.repo),'status':{'type':'idle'},'turns':[]}}
                if method=='thread/metadata/update':
                    owner.assertTrue((root/'assign.claim.json').exists()); self.assigned=True; return {'thread':{}}
                if method=='project/read': return {'project':copy.deepcopy(owner.project)}
                if method=='thread/read':
                    row=copy.deepcopy(owner.thread); row.update(projectId=owner.f.project if self.assigned else None,
                        path=str(self.target),status={'type':'idle' if self.loaded else 'notLoaded'})
                    return {'thread':row}
                if method=='thread/effectivePolicy/read':
                    value=policy(owner.f.brain,str(owner.f.repo))
                    if owner.bad_policy: value['policy']['codeModeOffEnforced']=False
                    return value
                if method=='thread/backgroundTerminals/list': return {'data':owner.terminals,'nextCursor':None}
                if method=='thread/turns/list': return {'data':[{'id':owner.f.turn,'status':'interrupted'}],'nextCursor':None}
                if method=='thread/subscribe':
                    owner.assertTrue((root/'subscription.claim.json').exists())
                    return {'version':1,'threadId':owner.f.brain,'subscribed':True,'reloaded':False}
                if method=='turn/start':
                    owner.assertTrue((Path(self.q['journal'])/'turn-start.claim.json').exists())
                    if owner.permission: self._early_requests=[{'id':42,'method':'item/commandExecution/requestApproval','params':{}}]
                    if owner.receipt:
                        def client():
                            try:
                                file=Path(self.q['mailbox'])/'handoff.json'
                                planning.submit(file,'receive')
                                planning.submit(file,'proposal',{'summary':'New host, same project','nextSteps':['Review a future bounded mission']})
                            except (Refusal,OSError): pass
                        thread=threading.Thread(target=client,daemon=True); owner.workers.append(thread); thread.start()
                    return {'turn':{'id':self.turn,'status':'inProgress'}}
                raise AssertionError('Unsupported destination operation '+method)
            call=_rpc
            def watch_connection(self): pass
            def _line(self):
                for _ in range(100):
                    self._on_wait_tick()
                    if not owner.receipt or (Path(self.q['mailbox'])/'proposal.reply.json').exists(): break
                    time.sleep(.01)
                return {'method':'turn/completed','params':{'threadId':owner.f.brain,'turn':{'id':self.turn,'status':'completed'}}}
        self.Destination=Destination
        for p in (patch.object(api,'SourceProxy',Source),patch.object(api,'DestinationProxy',Destination),
            patch.object(api,'load_binding',side_effect=lambda p:planning._read_binding(p)),
            patch.object(api,'destination_host',side_effect=lambda *args:copy.deepcopy(self.host))):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(lambda:[t.join(2) for t in self.workers])
        self.directory=self.f.root/'transfer-review'; self.q=self.prepare()['request']
        self.backup=self.f.root/'transfer-backup'; planning.backup(self.registry,self.ledger,self.q,self.backup,writers_stopped=True)
        self.calls.clear(); self.Destination.instances.clear()

    def prepare(self,**kw):
        return api.prepare(self.registry,self.ledger,self.file,self.candidate,self.manifest,self.attempt,
            self.process_record,self.directory,max_tokens=1,duration_hours=1,**kw)
    def apply(self,q=None):
        q=q or self.q
        return api.confirm(self.registry,self.ledger,q,digest(q),writers_stopped=True,backup_root=self.backup)
    def methods(self): return [m for where,m,_ in self.calls if where=='destination']
    def conserved(self):
        self.m.conserved(); self.assertEqual(api.phase.lifecycle.inventory(self.m.q['journal']),self.maintenance_pins)
        self.assertEqual(self.history.read_bytes(),self.original_history)

    def test_transfer_one_load_assignment_subscription_turn_on_one_original_connection(self):
        value=self.apply(); self.assertEqual(value['status'],'planning_completed',value)
        self.assertEqual(api.status(self.q),value); self.assertEqual(len(self.Destination.instances),1)
        for method in ('project/restoreMetadata','thread/resume','thread/metadata/update','thread/subscribe','turn/start'):
            self.assertEqual(self.methods().count(method),1,method)
        for method in ('project/import','thread/start','turn/interrupt','account/login/start','account/logout','approval/respond'):
            self.assertNotIn(method,self.methods())
        self.assertTrue(self.Destination.instances[0].target.read_bytes().startswith(self.original_history))
        self.assertEqual(value['postTurnUsage'],'unknown_not_collected'); self.conserved()

    def test_metadata_unknown_consumes_whole_canonical_lineage_without_retry(self):
        self.fail_at='thread/resume'; value=self.apply(); self.assertEqual(value['status'],'blocked_or_unknown')
        with self.assertRaises((Refusal,OSError)): self.apply()
        self.directory=self.f.root/'another-review'
        with self.assertRaises(Refusal): self.prepare()
        self.assertEqual(self.methods().count('thread/resume'),1); self.assertNotIn('turn/start',self.methods()); self.conserved()

    def test_original_source_turn_or_history_drift_refuses_without_destination_write(self):
        self.thread['turns'][-1]['id']='changed'
        self.assertEqual(self.apply()['status'],'blocked_or_unknown'); self.assertNotIn('project/restoreMetadata',self.methods()); self.conserved()

    def test_archive_tamper_refuses_before_native_connection(self):
        t=api.transfer_record(self.q); file=Path(t['archivePath']); file.chmod(0o600); file.write_bytes(b'changed')
        with self.assertRaises(Refusal): self.apply()
        self.assertEqual(self.calls,[]); self.conserved()

    def test_bad_loaded_policy_does_not_assign_subscribe_or_start(self):
        self.bad_policy=True; self.assertEqual(self.apply()['status'],'blocked_or_unknown')
        self.assertNotIn('thread/metadata/update',self.methods()); self.assertNotIn('turn/start',self.methods()); self.conserved()

    def test_unknown_current_tracker_is_never_treated_as_empty(self):
        self.terminals=None; self.assertEqual(self.apply()['status'],'blocked_or_unknown')
        self.assertNotIn('thread/subscribe',self.methods()); self.assertNotIn('turn/start',self.methods()); self.conserved()

    def test_missing_native_signin_never_starts_login_or_load(self):
        self.auth=False; self.assertEqual(self.apply()['status'],'blocked_or_unknown')
        self.assertNotIn('thread/resume',self.methods()); self.assertNotIn('account/login/start',self.methods()); self.conserved()

    def test_no_credential_bytes_are_read_copied_hashed_or_deleted(self):
        real=Path.open
        def guarded(path,*a,**kw):
            self.assertNotEqual(path.name,'auth.json'); return real(path,*a,**kw)
        original=api.credentials(self.home)
        with patch.object(Path,'open',guarded): self.assertEqual(self.apply()['status'],'planning_completed')
        self.assertEqual(api.credentials(self.home),original); self.assertFalse((self.backup/'auth.json').exists()); self.conserved()

    def test_actual_account_drift_before_next_native_effect_is_not_a_file_ttl(self):
        def changed(proxy,method,params):
            if method=='project/restoreMetadata': self.auth_plan='different-routing'
        self.callback=changed; self.assertEqual(self.apply()['status'],'blocked_or_unknown')
        self.assertNotIn('thread/resume',self.methods()); self.conserved()

    def test_stop_before_a_metadata_stage_fences_next_effect_without_cancel(self):
        def stop(proxy,method,params):
            if method=='project/restoreMetadata': write_record(api.phase.owner_root(self.q)/'stop.json',{'reviewHash':digest(self.q),'nativeCancelSent':False})
        self.callback=stop; self.assertEqual(self.apply()['status'],'blocked_or_unknown')
        self.assertNotIn('thread/resume',self.methods()); self.assertNotIn('turn/interrupt',self.methods()); self.conserved()

    def test_permission_during_new_preparation_is_not_automatically_answered(self):
        self.permission=True; self.receipt=False; self.assertEqual(self.apply()['status'],'incomplete_unknown')
        self.assertEqual(planning.status(self.q)['nativeOutcome'],'native_permission_or_request_requires_separate_review')
        self.assertNotIn('approval/respond',self.methods()); self.assertNotIn('turn/interrupt',self.methods()); self.conserved()

    def test_new_turn_without_explicit_new_receipt_is_not_handoff_success(self):
        self.receipt=False; self.assertEqual(self.apply()['status'],'incomplete_unknown'); self.conserved()

    def test_actual_usage_gap_is_retained_and_blocks_turn_without_resampling(self):
        file=Path(next(iter(planning.forward_usage.inventory(self.q['usageSource'],self.q['original']['run']))))
        file.write_text(file.read_text()+'{\n')
        self.assertEqual(self.apply()['status'],'incomplete_unknown')
        self.assertNotIn('turn/start',self.methods()); self.assertTrue(planning._read_private(Path(self.q['journal'])/'usage.json')['report']['gaps'])
        with self.assertRaises((Refusal,OSError)): self.apply()
        self.conserved()

    def test_old_expiry_is_preserved_while_new_clock_and_freshness_are_enforced(self):
        collect=planning.forward_usage.collect
        def stale(ledger,q): value=collect(ledger,q); self.now+=121; return value
        with patch.object(planning.forward_usage,'collect',stale): self.assertEqual(self.apply()['status'],'incomplete_unknown')
        self.assertNotIn('turn/start',self.methods()); self.conserved()

    def test_elapsed_new_clock_fences_without_renewal_or_old_clock_extension(self):
        def elapsed(proxy,method,params):
            if method=='thread/resume': self.now+=3601
        self.callback=elapsed; self.assertEqual(self.apply()['status'],'blocked_or_unknown')
        with self.assertRaises((Refusal,OSError)): self.apply()
        self.assertNotIn('turn/start',self.methods()); self.conserved()

    def test_status_and_binding_review_are_file_only_and_do_not_renew_evidence(self):
        with patch.object(api,'DestinationProxy',side_effect=AssertionError('No connection')):
            value=api.binding_review(self.q); self.assertFalse(value['prerequisiteSatisfied']); self.assertFalse(value['installsBinding'])
            self.assertEqual(api.status(self.q)['status'],'not_submitted')
        self.assertEqual(self.calls,[]); self.conserved()

    def test_positive_binding_review_requires_exact_complete_new_receipt_and_proposal(self):
        self.apply(); value=api.binding_review(self.q); self.assertTrue(value['prerequisiteSatisfied'])
        self.assertEqual(value['request']['destinationBindingHash'],digest(self.destination))
        self.assertFalse(value['installsBinding']); self.conserved()

    def test_partial_owner_blocks_old_phase_and_transfer_retries(self):
        root=api.phase.owner_root(self.q); root.parent.parent.mkdir(mode=0o700,exist_ok=True); root.parent.mkdir(mode=0o700)
        with self.assertRaises((Refusal,OSError)): self.apply()
        self.assertEqual(self.calls,[]); self.conserved()

    def test_unlisted_records_or_changed_receipt_cannot_be_ignored(self):
        self.apply(); write_record(api.phase.owner_root(self.q)/'foreign.json',{'unknown':True})
        with self.assertRaises(Refusal): api.status(self.q)
        self.conserved()

    def test_wrong_hash_backup_and_standalone_sender_do_not_claim(self):
        with self.assertRaises(Refusal): api.confirm(self.registry,self.ledger,self.q,'f'*64,writers_stopped=True,backup_root=self.backup)
        with self.assertRaises(Refusal): planning.confirm(self.registry,self.ledger,self.q,digest(self.q),writers_stopped=True,backup_root=self.backup)
        (self.backup/'history.jsonl').chmod(0o600); (self.backup/'history.jsonl').write_bytes(b'corrupt')
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(api.phase.owner_root(self.q).exists()); self.assertEqual(self.calls,[]); self.conserved()

    def test_concurrent_confirmations_share_one_permanent_owner(self):
        results=[]; failures=[]
        def work():
            try: results.append(self.apply())
            except (Refusal,OSError) as error: failures.append(type(error).__name__)
        threads=[threading.Thread(target=work) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(30); self.assertFalse(t.is_alive())
        self.assertEqual(len(results),1); self.assertEqual(len(failures),1)
        self.assertEqual(self.methods().count('thread/resume'),1); self.conserved()

    def test_closed_native_proxy_refuses_unclaimed_writes_login_and_old_controls(self):
        proxy=ProductionDestination(self.q)
        with patch.object(api.WakeProxy,'_rpc',return_value={}) as native:
            for method,params in (('thread/resume',{}),('project/restoreMetadata',{}),('thread/metadata/update',{}),
                ('turn/interrupt',{}),('account/login/start',{'type':'chatgpt'}),('account/read',{'refreshToken':True}),
                ('project/create',{}),('thread/read',{'threadId':str(uuid.uuid4()),'includeTurns':True})):
                with self.subTest(method=method),self.assertRaises(Refusal): proxy._rpc(method,params)
            native.assert_not_called()

    def test_native_stage_permit_is_single_use_even_if_native_delivery_fails(self):
        proxy=ProductionDestination(self.q); params={'threadId':self.f.brain}
        proxy.allow('thread/resume',params)
        with patch.object(api.WakeProxy,'_rpc',side_effect=OSError('Unknown delivery')) as native:
            with self.assertRaises(OSError): proxy._rpc('thread/resume',params)
            with self.assertRaises(Refusal): proxy._rpc('thread/resume',params)
        self.assertEqual(native.call_count,1); self.conserved()

    def test_credential_path_in_a_transfer_descriptor_refuses_before_archive_open(self):
        t=api.transfer_record(self.q); t['archivePath']=str(self.home/'auth.json')
        file=Path(self.q['transferFile']); file.write_text(json.dumps(t)); q=copy.deepcopy(self.q); q['transferPin']=planning.pin(file)
        real=Path.open
        def guarded(path,*a,**kw):
            self.assertNotEqual(path.name,'auth.json'); return real(path,*a,**kw)
        with patch.object(Path,'open',guarded),self.assertRaises(Refusal): api.retained_transfer(q)
        self.conserved()


class DestinationHostTest(unittest.TestCase):
    """Production process/launch/config/metadata validator; no native exec/RPC."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='transfer-host.',dir='/private/tmp'); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve(); self.root.chmod(0o700)
        self.package=package_fixture(self.root/'package')
        self.cwd=self.root/'checkout'; self.cwd.mkdir(mode=0o700); (self.cwd/'.git').mkdir(mode=0o700)
        self.home=self.root/'home'; self.home.mkdir(mode=0o700)
        (self.home/'config.toml').write_text(api.launch.CONFIG); (self.home/'config.toml').chmod(0o600)
        self.ipc=self.root/'ipc'; self.ipc.mkdir(mode=0o700)
        self.spec=api.launch.setup_scope(self.package['root'],self.cwd,self.home,self.ipc)
        self.manifest=self.root/'manifest.json'; write_record(self.manifest,self.spec)
        self.attempt=self.root/'attempt'; self.attempt.mkdir(mode=0o700)
        write_record(self.attempt/'launch.json',{'spec':self.spec,'manifestHash':digest(self.spec),
            'reviewHash':api.launch.review_hash(self.spec),'mode':'exec','createdAt':1})
        fd=os.open(self.attempt/'exec.claim',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.close(fd)
        self.state={'status':'exec_boundary_issued','mode':'exec','profile':api.PROFILE,
            'pid':123456789,'parentPid':1,'observedAt':1,'hostReady':False,'nativeToolsQualified':False,
            'bindingInstalled':False,'terminalSafety':'unknown','restarted':False}
        write_record(self.attempt/'status.json',self.state)
        self.process=self.root/'process.json'; self.identity='123456789 Mon Oct 19 10:00:00 2026'
        write_record(self.process,{'pid':123456789,'parentPid':1,'processIdentity':self.identity,
            'manifestPin':planning.pin(self.manifest)})
        # No socket/RPC is needed: validate_endpoint is independently covered by
        # native_read_client tests and compiled fixtures. This fixture pins only
        # the exact original process/alias/config checks under controlled OS rows.
        self.socket=self.root/'actual.sock'; self.socket.write_text('not an RPC endpoint'); self.socket.chmod(0o600)
        (self.ipc/'host.sock').symlink_to(self.socket)
        self.binary=str(Path(self.package['root'])/'bin/codex')
        self.binding={'endpoint':{'executable':self.binary,'sha256':self.package['executableHash'],'socket':str(self.socket)}}
        self.rows={}
        def fixed(argv):
            key=tuple(argv)
            if key in self.rows: return self.rows[key]
            if argv[-1]=='pid=,lstart=': return self.identity
            if argv[-1]=='ppid=': return '1'
            if argv[-1]=='command=': return self.binary+' app-server --listen unix://'+str(self.ipc/'host.sock')
            if 'cwd,txt' in argv: return 'p123456789\nfcwd\nn'+str(self.cwd)+'\nftxt\nn'+self.binary
            if '-U' in argv: return 'p123456789\nn'+str(self.socket)
            raise AssertionError('Unexpected OS command')
        for p in (patch.object(api,'fixed',side_effect=fixed),patch.object(api,'validate_endpoint')):
            p.start(); self.addCleanup(p.stop)

    def observe(self): return api.destination_host(self.manifest,self.attempt,self.process,self.binding)

    def test_positive_issued_scope_and_native_credential_metadata_without_body_reads(self):
        write_record(self.home/'auth.json',{'private':'NEVER_READ'})
        real=Path.open
        def guarded(path,*a,**kw):
            self.assertNotEqual(path.name,'auth.json'); return real(path,*a,**kw)
        with patch.object(Path,'open',guarded): result=self.observe()
        self.assertEqual(result['credentialMetadata'],api.credentials(self.home)); self.assertEqual(result['process']['pid'],123456789)
        self.assertNotIn(str(self.home/'auth.json'),result['pins'])

    def test_failed_or_unknown_original_exec_is_not_a_live_host(self):
        self.state['status']='exec_outcome_unknown'; (self.attempt/'status.json').write_text(json.dumps(self.state))
        with self.assertRaises(Refusal): self.observe()

    def test_missing_exec_claim_never_promotes_intent_into_launch(self):
        (self.attempt/'exec.claim').unlink()
        with self.assertRaises((Refusal,OSError)): self.observe()

    def test_wrong_process_birth_parent_and_argv_refuse(self):
        for suffix,value in (('pid=,lstart=','123456789 reused PID'),('ppid=','99'),('command=','other binary')):
            args=['/bin/ps','-p','123456789','-o',suffix]
            if suffix=='command=': args=['/bin/ps','-ww','-p','123456789','-o',suffix]
            self.rows[tuple(args)]=value
            with self.subTest(field=suffix),self.assertRaises(Refusal): self.observe()
            self.rows.clear()

    def test_changed_socket_alias_is_not_discovered_or_substituted(self):
        alias=self.ipc/'host.sock'; alias.unlink(); alias.symlink_to(self.root/'other.sock')
        with self.assertRaises((Refusal,OSError)): self.observe()

    def test_original_manifest_hash_and_record_must_agree(self):
        value=json.loads(self.process.read_text()); value['manifestPin']['sha256']='f'*64
        self.process.write_text(json.dumps(value))
        with self.assertRaises(Refusal): self.observe()

    def test_unrestricted_configuration_or_inherited_capabilities_refuse(self):
        (self.home/'config.toml').write_text('sandbox_mode="danger-full-access"\n')
        with self.assertRaises(Refusal): self.observe()

    def test_separately_signed_in_credentials_may_not_have_hardlink_aliases(self):
        write_record(self.home/'auth.json',{'never':'read'}); os.link(self.home/'auth.json',self.root/'credential-alias')
        with self.assertRaises(Refusal): self.observe()

    def test_native_managed_credential_rotation_is_not_a_new_host_or_account(self):
        write_record(self.home/'auth.json',{'fake':'initial-token'}); before=self.observe()
        file=self.home/'replacement'; write_record(file,{'fake':'rotated-token'}); os.replace(file,self.home/'auth.json')
        self.assertEqual(self.observe(),before)

    def test_credential_path_cannot_be_used_as_original_process_evidence(self):
        write_record(self.home/'auth.json',{'private':'NEVER_READ'})
        with self.assertRaises(Refusal): api.destination_host(self.manifest,self.attempt,self.home/'auth.json',self.binding)


if __name__=='__main__': unittest.main()
