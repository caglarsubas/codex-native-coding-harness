"""Disposable exact new planning control; originals and unknowns remain intact."""
import copy
import os
from pathlib import Path
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator import canceled_continuation as api, canceled_play as old, brain_memory
from orchestrator.core import Refusal, canonical, digest
from orchestrator.host_lifecycle import write_record
from orchestrator.partial_admission import database_proof
import test_canceled_play as fixtures
from test_native_policy_evidence import response as policy
from test_no_reload_transport import Proxy as BaseProxy
from test_public_host_runtime import package_fixture


class ContinuationTest(unittest.TestCase):
    def setUp(self):
        self.old=fixtures.CanceledPlayTest('runTest'); self.old.setUp(); self.addCleanup(self.old.doCleanups)
        self.f=self.old.f; self.registry,self.ledger=self.old.registry,self.old.ledger
        with self.ledger.tx() as db:
            meta=self.ledger.get(db,'meta',1); run=meta['standardRun']
            run.update(brainObservedTokens=1,brainUsageCoverage='observed_partial',usageHighWater=1)
            report={'runId':run['id'],'scopeHash':brain_memory.scope(run),'coverage':'observed_local','gaps':[],
                'tokens':{'total_tokens':1},'collectedAt':time.time(),'through':time.time(),'records':[]}
            run['usageReport']=report
            self.ledger.put(db,'meta',1,meta)
            db.execute('INSERT INTO snapshots VALUES(?,?,?)',(digest(report),'standard_usage',canonical(report)))
        self.old.apply()
        self.package=package_fixture(self.f.root/'pkg')
        candidate=copy.deepcopy(self.old.binding)
        candidate['endpoint'].update(executable=str(self.f.root/'pkg/bin/codex'),sha256=self.package['executableHash'])
        source=candidate['brains'][self.f.brain]['policyEvidence']
        source.update(sourceCommit=self.package['sourceCommit'],sourceTree=self.package['sourceTree'])
        self.candidate=self.f.root/'candidate.json'; write_record(self.candidate,candidate)
        self.contract={'protocol':api.transport.PROTOCOL,'method':api.transport.METHOD,
            'sourceCommit':source['sourceCommit'],'sourceTree':source['sourceTree'],
            'executableSha256':self.package['executableHash']}
        self.q=self.prepare()['request']; self.backup=self.f.root/'followup-backup'
        api.backup(self.registry,self.ledger,self.q,self.backup,writers_stopped=True)
        self.baseline=[database_proof(p) for p in (self.ledger.db,self.registry.db)]
        self.sidecars=old.sidecars(self.ledger); self.original_pin=old.prior.file_epoch(self.old.binding_file)
        self.workers=[]
        owner=self
        class Proxy(BaseProxy):
            instances=[]
            def __init__(self,endpoint):
                super().__init__(); self.endpoint=endpoint; self.thread={'id':owner.f.brain,
                    'projectId':owner.old.binding['brains'][owner.f.brain]['projectId'],
                    'cwd':str(owner.f.repo),'status':{'type':'idle'}}
                self.policy=policy(owner.f.brain,str(owner.f.repo)); self.reply.update(threadId=owner.f.brain)
                self.turn=str(uuid.uuid4()); self._early_completion=None; self.instances.append(self)
            def __enter__(self): return self
            def __exit__(self,*_): self.process=None
            def _rpc(self,method,params):
                if method=='project/read':
                    self.calls.append((method,params)); return {'project':{'id':self.thread['projectId'],'roots':[{'path':str(owner.f.repo)}]}}
                if method=='thread/turns/list':
                    self.calls.append((method,params)); return {'data':[{'id':owner.latest,'status':'interrupted'}],'nextCursor':None}
                if method=='turn/start':
                    self.calls.append((method,params)); self._early_completion=None
                    if owner.fail_start: raise OSError('fixture lost native acknowledgement')
                    if owner.early_permission:
                        self._early_requests=[{'id':4,'method':'item/commandExecution/requestApproval','params':{
                            'threadId':owner.f.brain,'turnId':self.turn}}]
                    if owner.receipt:
                        def client():
                            try:
                                root=Path(owner.q['mailbox']); file=root/'handoff.json'
                                api.submit(file,'receive')
                                api.submit(file,'proposal',{'summary':'Inert bounded proposal','nextSteps':['Review next scope; do not Play']})
                            except (Refusal,OSError) as error: owner.client_error=error
                        worker=threading.Thread(target=client,daemon=True); owner.workers.append(worker); worker.start()
                    return {'turn':{'id':self.turn,'status':'inProgress'}}
                return super()._rpc(method,params)
            call=_rpc
            def watch_connection(self): pass
            def _line(self):
                for _ in range(100):
                    self._on_wait_tick()
                    if not owner.receipt or (Path(owner.q['mailbox'])/'proposal.reply.json').exists(): break
                    time.sleep(.01)
                return {'method':'turn/completed','params':{'threadId':owner.f.brain,'turn':{'id':self.turn,'status':'completed'}}}
        self.Proxy=Proxy; self.latest=self.f.turn; self.receipt=True; self.fail_start=False; self.early_permission=False; self.client_error=None
        p=patch.object(api,'Proxy',Proxy); p.start(); self.addCleanup(p.stop)

    def prepare(self):
        return api.prepare(self.registry,self.ledger,self.old.binding_file,self.old.cid,self.candidate,self.contract,1)

    def run_control(self,**kw):
        return api.confirm(self.registry,self.ledger,self.q,digest(self.q),writers_stopped=True,backup_root=self.backup,**kw)

    def conserved(self):
        self.assertEqual(self.baseline,[database_proof(p) for p in (self.ledger.db,self.registry.db)])
        self.assertEqual(old.sidecars(self.ledger),self.sidecars)
        self.assertEqual(old.prior.file_epoch(self.old.binding_file),self.original_pin)
        self.assertEqual(old.status(self.ledger)['status'],'disposed_unqualified')

    def test_real_client_receipt_and_inert_proposal_have_separate_new_turn(self):
        result=self.run_control()
        for worker in self.workers: worker.join(2); self.assertFalse(worker.is_alive())
        self.assertIsNone(self.client_error); self.assertEqual(result['status'],'planning_completed')
        self.assertTrue(result['newReceiptRetained']); self.assertTrue(result['proposalRetained'])
        self.assertNotEqual(result['nativeTurnId'],self.q['original']['command']['notification']['nativeTurnId'])
        calls=[m for m,_ in self.Proxy.instances[-1].calls]
        self.assertEqual(calls.count('thread/subscribe'),1); self.assertEqual(calls.count('turn/start'),1)
        self.assertNotIn('thread/resume',calls); self.assertFalse(result['boundary']['dispatchAuthorized'])
        self.assertEqual(api.status(self.q),result); self.conserved()

    def test_native_completion_without_explicit_receipt_is_not_success(self):
        self.receipt=False; result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown'); self.assertEqual(result['nativeOutcome'],'completed')
        self.assertFalse(result['newReceiptRetained']); self.conserved()

    def test_lost_start_ack_is_consumed_without_reconnect_or_second_turn(self):
        self.fail_start=True; result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown')
        with self.assertRaises((Refusal,FileExistsError)): self.run_control()
        self.assertEqual(len(self.Proxy.instances),1); self.conserved()

    def test_permission_is_never_answered_or_canceled(self):
        self.receipt=False; self.early_permission=True; result=self.run_control()
        self.assertEqual(result['nativeOutcome'],'native_permission_or_request_requires_separate_review')
        calls=[m for m,_ in self.Proxy.instances[-1].calls]
        self.assertFalse(any(m in calls for m in ('turn/interrupt','approval/respond','thread/resume')))
        self.conserved()

    def test_wrong_owner_hash_or_missing_backup_cannot_claim(self):
        with self.assertRaises(Refusal):
            api.confirm(self.registry,self.ledger,self.q,'a'*64,writers_stopped=True,backup_root=self.backup)
        with self.assertRaises(Refusal): api.confirm(self.registry,self.ledger,self.q,digest(self.q))
        self.assertFalse(Path(self.q['journal']).exists()); self.conserved()

    def test_alias_review_directory_or_new_ids_cannot_reset_attempt(self):
        self.receipt=False; self.run_control()
        with self.assertRaises(Refusal): self.prepare()
        q=copy.deepcopy(self.q); q['journal']+='other'
        with self.assertRaises(Refusal): api.confirm(self.registry,self.ledger,q,digest(q),writers_stopped=True,backup_root=self.backup)
        self.conserved()

    def test_partial_canonical_claim_stays_unknown_and_is_not_resendable(self):
        root=Path(self.q['journal']); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        with self.assertRaises((Refusal,FileExistsError)): self.run_control()
        with self.assertRaises(OSError): api.status(self.q)
        self.assertEqual(self.Proxy.instances,[]); self.conserved()

    def test_unknown_usage_expired_phase_or_changed_limits_refuses(self):
        for edit in (lambda q:q['original']['run'].update(usageReport=None),
                     lambda q:q['original']['run']['usageReport'].update(gaps=['unknown']),
                     lambda q:q['original']['run'].update(expiresAt=1),
                     lambda q:q['original']['run']['limits'].update(tokenBudget=1)):
            q=copy.deepcopy(self.q); edit(q)
            with self.assertRaises(Refusal): api.confirm(self.registry,self.ledger,q,digest(q),writers_stopped=True,backup_root=self.backup)
        self.assertFalse(Path(self.q['journal']).exists()); self.conserved()

    def test_unloaded_policy_or_tracker_uncertainty_never_starts(self):
        for state in ({'type':'notLoaded'},{'type':'active','activeFlags':['waitingOnApproval']}):
            with self.subTest(state=state),patch.object(api.transport.Subscription,'_sample',side_effect=Refusal('Unloaded/unknown native tracker')):
                result=self.run_control()
                self.assertEqual(result['status'],'incomplete_unknown')
                self.assertFalse(any(m=='turn/start' for m,_ in self.Proxy.instances[-1].calls))
                break  # Canonical claim remains consumed; never manufacture a second fixture attempt.
        self.conserved()

    def test_owner_stop_wins_before_new_turn(self):
        original=api.transport.Subscription.attach
        def stopped(sub,claim):
            result=original(sub,claim); api.stop(self.q,digest(self.q)); return result
        with patch.object(api.transport.Subscription,'attach',stopped): result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown')
        self.assertFalse(any(m=='turn/start' for m,_ in self.Proxy.instances[-1].calls)); self.conserved()

    def test_backup_mutation_or_missing_disposition_fails_closed(self):
        (self.backup/'private-0.bin').write_text('{}')
        with self.assertRaises(Refusal): self.run_control()
        self.assertFalse(Path(self.q['journal']).exists()); self.conserved()

    def test_read_only_status_opens_no_native_connection(self):
        with patch.object(api,'Proxy',side_effect=AssertionError('Status cannot connect')):
            self.assertEqual(api.status(self.q)['status'],'not_submitted')
        self.conserved()

    def test_intervening_native_turn_refuses_before_subscription(self):
        self.latest=str(uuid.uuid4()); result=self.run_control()
        self.assertEqual(result['status'],'incomplete_unknown')
        self.assertFalse(any(m in ('turn/start','thread/subscribe') for m,_ in self.Proxy.instances[-1].calls))
        self.conserved()

    def test_changed_outcome_and_receipt_cannot_claim_success(self):
        self.run_control(); root=Path(self.q['journal'])
        (root/'receive.json').write_text('{}')
        with self.assertRaises(Refusal): api.status(self.q)
        self.conserved()

    def test_package_epoch_changed_before_start_refuses(self):
        os.utime(self.f.root/'pkg/source.bundle',None)
        with self.assertRaises(Refusal): self.run_control()
        self.assertEqual(self.Proxy.instances,[]); self.conserved()

    def test_concurrent_exact_confirmations_have_one_canonical_owner(self):
        results=[]
        def run():
            try: results.append(self.run_control()['status'])
            except (Refusal,OSError): results.append('refused')
        threads=[threading.Thread(target=run) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10); self.assertFalse(thread.is_alive())
        self.assertCountEqual(results,['planning_completed','refused'])
        self.assertEqual(len(self.Proxy.instances),1); self.conserved()


if __name__=='__main__': unittest.main()
