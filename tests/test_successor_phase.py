"""A distinct clock, one original connection and no refund/replay of history."""
import copy
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from orchestrator import successor_phase as api, canceled_continuation as planning, maintenance_load
from orchestrator.core import Refusal,digest
from orchestrator.host_lifecycle import write_record
from test_native_policy_evidence import response as policy
from test_no_reload_transport import Proxy as BaseProxy
import test_maintenance_load as fixtures


class SuccessorPhaseTest(unittest.TestCase):
    def setUp(self):
        self.m=fixtures.MaintenanceLoadTest('runTest'); self.m.setUp(); self.addCleanup(self.m.doCleanups)
        self.registry,self.ledger,self.f=self.m.registry,self.m.ledger,self.m.f
        self.now=self.m.parent['original']['run']['expiresAt']+1
        self.clock=patch('time.time',side_effect=lambda:self.now); self.clock.start(); self.addCleanup(self.clock.stop)
        self.assertEqual(self.m.apply()['status'],'maintenance_load_observed_idle')
        self.file=self.f.root/'maintenance.json'; write_record(self.file,self.m.q)
        self.maintenance_pins=api.lifecycle.inventory(self.m.q['journal'])
        self.q=self.prepare()['request']; self.backup=self.f.root/'phase-backup'
        planning.backup(self.registry,self.ledger,self.q,self.backup,writers_stopped=True)
        self.receipt=True; self.fail_start=False; self.permission=False; self.workers=[]
        owner=self
        class Proxy(BaseProxy):
            instances=[]
            def __init__(self,endpoint):
                super().__init__(); self.process=SimpleNamespace(poll=lambda:None); self.endpoint=endpoint
                self.thread={'id':owner.f.brain,'projectId':owner.f.project,'cwd':str(owner.f.repo),'status':{'type':'idle'}}
                self.policy=policy(owner.f.brain,str(owner.f.repo)); self.reply.update(threadId=owner.f.brain)
                self.turn=str(uuid.uuid4()); self._early_completion=None; self.instances.append(self)
            def __enter__(self): return self
            def __exit__(self,*_): self.process=None
            def _rpc(self,method,params):
                if method=='project/read':
                    self.calls.append((method,params)); return {'project':{'id':owner.f.project,'roots':[{'path':str(owner.f.repo)}]}}
                if method=='thread/turns/list':
                    self.calls.append((method,params)); return {'data':[{'id':owner.f.turn,'status':'interrupted'}],'nextCursor':None}
                if method=='turn/start':
                    self.calls.append((method,params))
                    if owner.fail_start: raise OSError('Lost exact acknowledgement')
                    if owner.permission: self._early_requests=[{'id':42,'method':'item/commandExecution/requestApproval','params':{}}]
                    if owner.receipt:
                        def client():
                            try:
                                file=Path(owner.q['mailbox'])/'handoff.json'
                                planning.submit(file,'receive')
                                planning.submit(file,'proposal',{'summary':'New preparation phase only','nextSteps':['Exact future mission review; no Play']})
                            except (Refusal,OSError): pass
                        worker=threading.Thread(target=client,daemon=True); owner.workers.append(worker); worker.start()
                    return {'turn':{'id':self.turn,'status':'inProgress'}}
                return super()._rpc(method,params)
            def watch_connection(self): pass
            def _line(self):
                for _ in range(100):
                    self._on_wait_tick()
                    if not owner.receipt or (Path(owner.q['mailbox'])/'proposal.reply.json').exists(): break
                    time.sleep(.01)
                return {'method':'turn/completed','params':{'threadId':owner.f.brain,'turn':{'id':self.turn,'status':'completed'}}}
        self.Proxy=Proxy; p=patch.object(planning,'Proxy',Proxy); p.start(); self.addCleanup(p.stop)
        self.addCleanup(lambda:[w.join(2) for w in self.workers])

    def prepare(self,**kw): return api.prepare(self.registry,self.ledger,self.file,max_tokens=1,duration_hours=1,**kw)
    def apply(self,q=None):
        q=q or self.q
        return api.confirm(self.registry,self.ledger,q,digest(q),writers_stopped=True,backup_root=self.backup)
    def conserved(self):
        self.m.conserved()
        self.assertEqual(api.lifecycle.inventory(self.m.q['journal']),self.maintenance_pins)
    def methods(self): return [m for p in self.Proxy.instances for m,_ in p.calls]

    def test_new_expired_successor_phase_one_connection_and_no_old_run_changes(self):
        value=self.apply(); self.assertEqual(value['status'],'planning_completed',value)
        self.assertEqual(api.status(self.registry,self.q),value)
        self.assertEqual(len(self.Proxy.instances),1); methods=self.methods()
        self.assertEqual(methods.count('thread/subscribe'),1); self.assertEqual(methods.count('turn/start'),1)
        for method in ('thread/resume','thread/start','turn/interrupt','approval/respond'): self.assertNotIn(method,methods)
        clock=api.phase_clock(self.q)
        self.assertEqual(clock['startedAt'],self.now); self.assertEqual(clock['expiresAt'],self.now+3600)
        self.assertLess(self.q['original']['run']['expiresAt'],clock['startedAt'])
        self.assertEqual(self.q['phase']['workerLimit'],0); self.assertFalse(self.q['phase']['repositoryWrites'])
        prompt=next(p for m,p in self.Proxy.instances[0].calls if m=='turn/start')['input'][0]['text']
        self.assertIn(self.q['phase']['id'],prompt); self.assertIn('does not renew',prompt)
        self.assertTrue(value['connectionClosed']); self.conserved()

    def test_prepare_backup_status_never_connect_collect_or_start_clock(self):
        with patch.object(planning,'Proxy',side_effect=AssertionError('No connection')),\
             patch.object(planning.forward_usage,'collect',side_effect=AssertionError('No sample')):
            self.assertEqual(self.prepare()['request'],self.q)
            planning.backup(self.registry,self.ledger,self.q,self.f.root/'extra-backup',writers_stopped=True)
            self.assertEqual(api.status(self.registry,self.q)['status'],'not_submitted')
        self.assertFalse(api.owner_root(self.q).parent.exists()); self.conserved()

    def test_review_wait_has_no_timer_and_does_not_start_phase_clock(self):
        self.now+=86400*10
        self.assertEqual(self.prepare()['request'],self.q)
        self.assertFalse(api.owner_root(self.q).parent.exists()); self.conserved()

    def test_old_planning_and_standard_writes_remain_fenced(self):
        with self.assertRaisesRegex(Refusal,'Maintenance load claim'):
            planning.current(self.registry,self.ledger,self.m.parent)
        with self.assertRaises(Refusal):
            with self.ledger.tx() as db: self.ledger.get(db,'meta',1)['paused']=False
        self.conserved()

    def test_wrong_confirmation_missing_backup_and_quiescence_do_not_claim(self):
        with self.assertRaises(Refusal): api.confirm(self.registry,self.ledger,self.q,'f'*64,writers_stopped=True,backup_root=self.backup)
        with self.assertRaises(Refusal): api.confirm(self.registry,self.ledger,self.q,digest(self.q),backup_root=self.backup)
        (self.backup/'private-0.bin').write_text('{}')
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(api.owner_root(self.q).parent.exists()); self.assertEqual(self.Proxy.instances,[]); self.conserved()

    def test_bad_phase_scope_budget_duration_and_worker_authority_are_not_accepted(self):
        for key,value in (('workerLimit',1),('repositoryWrites',True),('durationHours',0),
                ('durationHours',25),('carriedUsageHighWater',0),('id','another-id'),('predecessorRunId','changed')):
            q=copy.deepcopy(self.q); q['phase'][key]=value
            with self.subTest(key=key),self.assertRaises(Refusal): planning.current(self.registry,self.ledger,q)
        q=copy.deepcopy(self.q); q['maxTokens']=100000; q['phase']['maxTokens']=100000
        with self.assertRaises(Refusal): self.apply(q)
        self.assertFalse(api.owner_root(self.q).parent.exists()); self.conserved()

    def test_active_original_phase_cannot_be_relabelled_new_clock(self):
        self.now=self.q['original']['run']['expiresAt']-1
        with self.assertRaises(Refusal): self.prepare()
        with self.assertRaises(Refusal): self.apply()
        self.assertEqual(self.Proxy.instances,[]); self.conserved()

    def test_unknown_or_partial_maintenance_cannot_be_a_successor_fallback(self):
        root=Path(self.m.q['journal']); write_record(root/'failure.json',{'unknown':True})
        with self.assertRaises(Refusal): self.prepare()
        with self.assertRaises(Refusal): self.apply()
        self.assertEqual(self.Proxy.instances,[])

    def test_no_standalone_old_owner_or_version_switch_can_send_new_phase(self):
        with self.assertRaises(Refusal): planning.confirm(self.registry,self.ledger,self.q,digest(self.q),writers_stopped=True,backup_root=self.backup)
        q=copy.deepcopy(self.q); q['version']=3; q['kind']=planning.SUCCESSOR_KIND
        with self.assertRaises(Refusal): self.apply(q)
        self.assertEqual(self.Proxy.instances,[]); self.conserved()

    def test_lost_ack_is_one_shot_and_cannot_be_renamed_or_chained(self):
        self.fail_start=True; value=self.apply(); self.assertEqual(value['status'],'incomplete_unknown')
        with self.assertRaises((Refusal,OSError)): self.apply()
        with self.assertRaises(Refusal): self.prepare()
        q=copy.deepcopy(self.q); q['journal']+='-new'; q['phase']['id']='new'
        with self.assertRaises(Refusal): self.apply(q)
        self.assertEqual(self.methods().count('turn/start'),1); self.conserved()

    def test_unloaded_observation_never_becomes_reload_or_usage_authority(self):
        with patch.object(planning.transport.Subscription,'_sample',side_effect=Refusal(api.lifecycle.REFUSAL)),\
             patch.object(planning.forward_usage,'collect',side_effect=AssertionError('No sample before subscription')):
            value=self.apply()
        self.assertEqual(value['status'],'blocked_or_unknown')
        self.assertNotIn('turn/start',self.methods()); self.assertNotIn('thread/resume',self.methods())
        self.assertFalse(Path(self.q['journal']).exists()); self.conserved()

    def test_native_permission_has_no_automatic_response_or_cancel(self):
        self.permission=True; self.receipt=False; value=self.apply()
        self.assertEqual(value['status'],'incomplete_unknown')
        self.assertEqual(planning.status(self.q)['nativeOutcome'],'native_permission_or_request_requires_separate_review')
        for method in ('turn/interrupt','approval/respond','thread/resume'): self.assertNotIn(method,self.methods())
        self.conserved()

    def test_completion_without_explicit_new_receipt_is_not_success(self):
        self.receipt=False; value=self.apply(); self.assertEqual(value['status'],'incomplete_unknown')
        self.assertFalse(planning.status(self.q)['newReceiptRetained']); self.conserved()

    def test_stop_before_subscription_wins_and_sends_no_cancel(self):
        original=planning.transport.Subscription.attach
        def stopped(sub,claim): api.stop(self.registry,self.q,digest(self.q)); return original(sub,claim)
        with patch.object(planning.transport.Subscription,'attach',stopped): value=self.apply()
        self.assertEqual(value['status'],'blocked_or_unknown')
        self.assertNotIn('thread/subscribe',self.methods()); self.assertNotIn('turn/start',self.methods()); self.conserved()

    def test_new_phase_expiry_fences_turn_without_resetting_original_clock(self):
        original=planning.forward_usage.collect
        def expired(ledger,q):
            value=original(ledger,q); self.now+=3601; return value
        with patch.object(planning.forward_usage,'collect',expired): value=self.apply()
        self.assertEqual(value['status'],'incomplete_unknown'); self.assertNotIn('turn/start',self.methods())
        with self.assertRaises(Refusal): self.apply()
        self.conserved()

    def test_same_freshness_limit_still_applies_with_fresh_phase_clock(self):
        original=planning.forward_usage.collect
        def stale(ledger,q): value=original(ledger,q); self.now+=121; return value
        with patch.object(planning.forward_usage,'collect',stale): value=self.apply()
        self.assertEqual(value['status'],'incomplete_unknown'); self.assertNotIn('turn/start',self.methods()); self.conserved()

    def test_actual_usage_gaps_are_retained_never_reset_or_resampled(self):
        file=Path(next(iter(planning.forward_usage.inventory(self.q['usageSource'],self.q['original']['run']))))
        file.write_text(file.read_text()+'{\n')
        value=self.apply(); self.assertEqual(value['status'],'incomplete_unknown')
        self.assertTrue(planning._read_private(Path(self.q['journal'])/'usage.json')['report']['gaps'])
        self.assertNotIn('turn/start',self.methods())
        with self.assertRaises((Refusal,OSError)): self.apply()
        self.conserved()

    def test_partial_owner_never_gets_a_new_phase_id_or_second_connection(self):
        root=api.owner_root(self.q); root.parent.parent.mkdir(mode=0o700,exist_ok=True); root.parent.mkdir(mode=0o700)
        with self.assertRaises((Refusal,OSError)): self.apply()
        with self.assertRaises(Refusal): self.prepare()
        with self.assertRaises((Refusal,OSError)): api.status(self.registry,self.q)
        self.assertEqual(self.Proxy.instances,[]); self.conserved()

    def test_changed_candidate_package_source_or_old_rows_fail_before_connection(self):
        for key,value in (('sourceHash','f'*64),('candidatePin',{}),('packageEpochs',{}),('original',{})):
            q=copy.deepcopy(self.q); q[key]=value
            with self.subTest(key=key),self.assertRaises((Refusal,KeyError)): self.apply(q)
        self.assertEqual(self.Proxy.instances,[]); self.conserved()

    def test_changed_clock_during_subscription_is_not_adopted(self):
        original=planning.transport.Subscription.attach
        def changed(sub,claim):
            value=original(sub,claim); path=api.owner_root(self.q)/'intent.json'; row=json.loads(path.read_bytes())
            row['phaseClock']['startedAt']+=1; row['phaseClock']['expiresAt']+=1
            path.write_text(json.dumps(row)); return value
        with patch.object(planning.transport.Subscription,'attach',changed): value=self.apply()
        self.assertEqual(value['status'],'blocked_or_unknown'); self.assertNotIn('turn/start',self.methods()); self.conserved()

    def test_positive_status_is_historical_and_no_connection_is_reopened(self):
        value=self.apply(); self.now+=86400
        with patch.object(planning,'Proxy',side_effect=AssertionError('No reconnect')),\
             patch.object(planning.old,'source_hash',return_value='f'*64):
            self.assertEqual(api.status(self.registry,self.q),value)
        self.conserved()

    def test_corrupted_receipt_and_unlisted_owner_or_consumer_records_fail_status(self):
        self.apply(); write_record(api.owner_root(self.q)/'unexpected.json',{'unknown':True})
        with self.assertRaises(Refusal): api.status(self.registry,self.q)
        self.conserved()

    def test_backup_cannot_overlap_any_protected_original_or_native_scope(self):
        for root in (self.registry.root,self.ledger.root,self.f.repo,self.m.l.h.directory,self.m.l.f.home):
            with self.subTest(path=root),self.assertRaises(Refusal):
                planning.backup(self.registry,self.ledger,self.q,root/'invalid-backup',writers_stopped=True)
            self.assertFalse((root/'invalid-backup').exists())
        self.conserved()

    def test_diagnostic_unloaded_is_actionable_but_grants_no_turn_or_claim(self):
        base=self.Proxy
        class Cold(base):
            def __init__(self,endpoint): super().__init__(endpoint); self.thread['status']={'type':'notLoaded'}
        with patch.object(api.lifecycle,'InspectionProxy',Cold): value=api.inspect(self.registry,self.ledger,self.q)
        self.assertEqual(value['blockers'],['brain_not_loaded_no_reload_authorized'])
        self.assertEqual(value['policy'],'unknown'); self.assertEqual(value['trackedTerminals'],'unknown')
        self.assertFalse(api.owner_root(self.q).parent.exists()); self.assertNotIn('thread/subscribe',self.methods()); self.conserved()

    def test_concurrent_confirmations_have_one_phase_one_subscription_one_turn(self):
        results=[]; errors=[]
        def run():
            try: results.append(self.apply())
            except (Refusal,OSError) as error: errors.append(type(error).__name__)
        workers=[threading.Thread(target=run) for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(15); self.assertFalse(worker.is_alive())
        self.assertEqual(len(results),1); self.assertEqual(len(errors),1)
        self.assertEqual(results[0]['status'],'planning_completed'); self.assertEqual(len(self.Proxy.instances),1); self.conserved()

    def test_credential_paths_refuse_before_private_bytes_are_read(self):
        q=copy.deepcopy(self.q); q['phaseLineage']['maintenanceFile']=str(self.f.root/'auth.json')
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No credential read')):
            with self.assertRaises(Refusal): api.status(self.registry,q)
        q=copy.deepcopy(self.q); q['phaseLineage']['files'][str(self.f.root/'auth.json')]={}
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No credential read')):
            with self.assertRaises(Refusal): api.status(self.registry,q)
        self.conserved()

    def test_unlisted_consumer_record_and_changed_receipt_never_pass_status(self):
        self.apply(); write_record(Path(self.q['journal'])/'unlisted.json',{'unknown':True})
        with self.assertRaises(Refusal): api.status(self.registry,self.q)
        self.conserved()


if __name__=='__main__': unittest.main()
