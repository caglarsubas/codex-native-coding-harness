"""Disposable canceled-Play disposition; no live host or model requests."""
import copy
import io
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator import canceled_play as cp, effect_capture, projects, standard
from orchestrator.core import Ledger, Refusal, canonical, digest
from orchestrator.partial_admission import database_proof
from orchestrator.standard_run_mailbox import continuation
import test_standard_run_mailbox as fixtures


class CanceledPlayTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.RunMailboxTest('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.ledger, self.registry, self.cid = self.f.ledger, self.f.registry, self.f.cid
        self.catalog = str(uuid.uuid4())
        self.binding = copy.deepcopy(self.f.binding)
        self.binding['brains'][self.f.brain]['catalogProjectId'] = self.catalog
        self.binding_file = self.f.root/'reviewed-binding.json'
        self.binding_file.write_text(canonical(self.binding)); self.binding_file.chmod(0o600)
        projects.record(self.registry, {'schemaVersion':2,'projects':[{'projectId':self.catalog,
            'projectKind':'local','hostId':'local','label':'Disposable','path':str(self.f.repo),
            'isGitRepository':True}]}, time.time())
        projects.bind(self.registry,'v3','local',self.catalog,projects.catalog(self.registry)['hash'])
        # Disposable history fixture, not a live mailbox conversion: represent an
        # original Play sent by the older release before this protocol existed.
        for path in self.ledger.root.glob('standard-run-*.json'): path.unlink()
        with self.ledger.tx() as db:
            c = self.ledger.get(db,'commands',self.cid); n = c['notification']; n.pop('runControl',None)
            n.update(status='sending',hostBindingHash=digest(self.binding),hostRunId=self.f.run_id,
                     brainId=self.f.brain,hostInspectionTransport='owned_observer_v1')
            n['nativeResumeProfile']['bindingHash'] = digest(self.binding)
            n['nativeEffectivePolicy']['bindingHash'] = digest(self.binding)
            n['nativeEffectCapture'] = effect_capture.begin(self.ledger,self.binding,c,self.ledger.get(db,'meta',1))
            for method,status in (('item/started','inProgress'),('item/completed','failed')):
                effect_capture.append(self.ledger,self.cid,self.f.brain,{'method':method,'params':{
                    'threadId':self.f.brain,'turnId':self.f.turn,'item':{'id':'fixed-local-read',
                    'type':'commandExecution','status':status,'exitCode':1 if status == 'failed' else None}}})
            effect_capture.append(self.ledger,self.cid,self.f.brain,{'method':'turn/completed','params':{
                'threadId':self.f.brain,'turn':{'id':self.f.turn,'status':'interrupted'}}})
            now = time.time()-.000001
            n.update(status='accepted',nativeTurnStatus='interrupted',
                nativeApprovals=[{'method':'item/commandExecution/requestApproval','turnId':self.f.turn,
                    'requestHash':'f'*64,'decision':'cancel','status':'resolved','claimedAt':now-2,'observedAt':now-1}],
                nativePermissionObservation={'version':1,'turnId':self.f.turn,'requestHash':'f'*64,
                    'reason':'native_resolved','endedAt':now},
                nativeThreadObservation={'version':1,'rootThreadId':self.f.brain,'nativeTurnId':self.f.turn,
                    'streamStatus':'closed','monitoringEndedAt':now,'events':[],'complete':False,
                    'gaps':['owned_stream_not_exhaustive']})
            effect_capture.seal(self.ledger,c,self.f.turn,'interrupted')
            self.ledger.put(db,'commands',self.cid,c)
        self.before = self.ledger.snapshot(); self.proof = database_proof(self.ledger.db)
        self.registry_proof = database_proof(self.registry.db)
        self.pins = cp.sidecars(self.ledger); self.binding_bytes = self.binding_file.read_bytes()

    def prepare(self): return cp.prepare(self.registry,self.ledger,self.binding_file,self.cid)

    def backup(self,p):
        root = self.f.root/'backup'
        cp.create_backup(self.registry,self.ledger,p['request'],root,writers_stopped=True)
        return root

    def apply(self):
        p = self.prepare(); backup = self.backup(p)
        result = cp.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],writers_stopped=True,backup_root=backup)
        return p,backup,result

    def conserved(self):
        self.assertEqual(database_proof(self.registry.db),self.registry_proof)
        self.assertEqual(self.binding_file.read_bytes(),self.binding_bytes)
        self.assertEqual(cp.sidecars(self.ledger),self.pins)
        after = self.ledger.snapshot()
        self.assertEqual(after['meta'],self.before['meta'])
        for name in ('commands','repositories','workers','queue','decisions'):
            self.assertEqual(after[name],self.before[name])
        self.assertEqual(after['meta']['standardRun']['brainUsageCoverage'],'not_observed')
        self.assertIsNone(after['meta']['standardRun'].get('usageHighWater'))

    def mutate(self,fn):
        with self.ledger.tx() as db:
            c = self.ledger.get(db,'commands',self.cid); fn(c); self.ledger.put(db,'commands',self.cid,c)

    def test_preview_and_continuation_are_read_only_and_do_not_expire_by_timer(self):
        p = self.prepare(); self.assertEqual(p['validUntil'],'scope_changes')
        with patch('time.time',return_value=time.time()+100000): self.assertEqual(p,self.prepare())
        self.assertFalse(p['continuation']['executionAvailable'])
        self.assertEqual(cp.continuation(self.ledger)['status'],'blocked_no_reload_transport')
        self.assertEqual(database_proof(self.ledger.db),self.proof)
        self.conserved()

    def test_disposition_preserves_original_rows_and_only_adds_one_local_record(self):
        _,_,r = self.apply()
        self.assertEqual(r['status'],'disposed_unqualified'); self.assertEqual(r['brainReceipt'],'missing')
        self.assertEqual(r['originalRunStatus'],'running'); self.assertTrue(r['writesBlocked'])
        self.assertEqual(cp.status(self.ledger),r)
        self.assertEqual(self.ledger.snapshot()['workflow']['pendingRequests'],0)
        from orchestrator.decisions import inbox
        self.assertEqual(inbox(self.ledger.snapshot())['commands'],[])
        s = standard.read(self.ledger)
        self.assertFalse(s['available']); self.assertEqual(s['parallelEligibility']['currentlyEligible'],0)
        self.conserved()

    def test_lost_confirmation_result_reads_original_local_record_only(self):
        p,backup,r = self.apply(); before = database_proof(self.ledger.db)
        with patch('time.time',return_value=time.time()+100000):
            self.assertEqual(cp.confirm(self.registry,self.ledger,p['request'],p['reviewHash']),r)
        self.assertEqual(database_proof(self.ledger.db),before); self.conserved()

    def test_wrong_review_quiescence_or_missing_backup_refuses_before_claim(self):
        p = self.prepare()
        for kw in ({},{'writers_stopped':True},{'backup_root':self.f.root/'absent'}):
            with self.assertRaises(Refusal): cp.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],**kw)
        with self.assertRaises(Refusal): cp.confirm(self.registry,self.ledger,p['request'],'a'*64)
        self.assertFalse((self.ledger.root/cp.FENCE).exists()); self.conserved()

    def test_changed_backup_scope_binding_or_claim_epoch_refuses(self):
        p = self.prepare(); root = self.backup(p)
        (root/'sidecar-0').write_bytes(b'changed')
        with self.assertRaises(Refusal): cp.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],writers_stopped=True,backup_root=root)
        self.assertFalse((self.ledger.root/cp.FENCE).exists())
        self.binding_file.touch()
        with self.assertRaises(Refusal): cp.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],writers_stopped=True,backup_root=root)

    def test_only_exact_resolved_cancel_and_closed_interrupted_original_qualify(self):
        original = self.before['commands'][0]
        edits = [lambda c:c.update(status='completed'),lambda c:c.update(receivedAt=1),
            lambda c:c['notification'].update(status='uncertain'),
            lambda c:c['notification'].update(nativeTurnStatus='unconfirmed'),
            lambda c:c['notification'].update(nativeTurnStatus='completed'),
            lambda c:c['notification'].update(runControl={'transport':'standard_run_observer_v1'}),
            lambda c:c['notification']['nativeApprovals'][0].update(status='uncertain'),
            lambda c:c['notification']['nativeApprovals'][0].update(decision='accept'),
            lambda c:c['notification']['nativeApprovals'][0].update(turnId=str(uuid.uuid4())),
            lambda c:c['notification']['nativeApprovals'][0].update(claimedAt=True),
            lambda c:c['notification']['nativePermissionObservation'].update(requestHash='a'*64),
            lambda c:c['notification']['nativePermissionObservation'].update(reason='connection_lost'),
            lambda c:c['notification']['nativeThreadObservation'].update(streamStatus='open'),
            lambda c:c['notification']['nativeThreadObservation'].update(events=[{'unknown':'child'}]),
            lambda c:c['notification']['nativeThreadObservation'].update(monitoringEndedAt=0),
            lambda c:c['notification']['nativeResumeProfile'].update(resumeAcknowledged=False)]
        for edit in edits:
            with self.subTest(edit=edit):
                self.mutate(edit)
                with self.assertRaises(Refusal): self.prepare()
                with self.ledger.tx() as db: self.ledger.put(db,'commands',self.cid,original)

    def test_owned_workers_pending_controls_strict_and_usage_drift_do_not_become_free_scope(self):
        old = self.before['meta']
        for field,value in (('controller',{'owner':'unknown'}),('runner',{'unknown':True}),
                            ('brainControl',{'desired':'stopped'}),('schemaVersion',3)):
            with self.subTest(field=field):
                with self.ledger.tx() as db: self.ledger.put(db,'meta',1,{**old,field:value})
                with self.assertRaises(Refusal): self.prepare()
                with self.ledger.tx() as db: self.ledger.put(db,'meta',1,old)
        p = self.prepare(); backup = self.backup(p)
        with self.ledger.tx() as db:
            meta = self.ledger.get(db,'meta',1); meta['standardRun']['brainObservedTokens']=10
            self.ledger.put(db,'meta',1,meta)
        with self.assertRaises(Refusal): cp.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],writers_stopped=True,backup_root=backup)

    def test_partial_claim_survives_failure_and_fences_all_normal_writes(self):
        p = self.prepare(); backup = self.backup(p)
        with patch.object(cp,'retained_in',side_effect=Refusal('fixture interruption')):
            with self.assertRaises(Refusal): cp.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],writers_stopped=True,backup_root=backup)
        self.assertEqual(cp.status(self.ledger)['status'],'incomplete_or_changed')
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass
        with self.assertRaises(Refusal): cp.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],writers_stopped=True,backup_root=backup)
        self.assertEqual(database_proof(self.ledger.db),self.proof)

    def test_deleted_claim_or_corrupt_record_never_unfences_writes(self):
        self.apply(); (self.ledger.root/cp.FENCE).unlink()  # Explicit disposable corruption test only.
        self.assertEqual(cp.status(self.ledger)['status'],'incomplete_or_changed')
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass
        self.assertFalse(standard.read(self.ledger)['available'])

    def test_every_normal_control_and_brain_receipt_is_fenced(self):
        self.apply()
        with self.assertRaises(Refusal): self.ledger.acquire(self.f.brain+':not-authorized')
        with self.assertRaises(Refusal):
            self.ledger.submit({'id':str(uuid.uuid4()),'kind':'reconcile',
                'expectedRevision':self.before['meta']['revision'],'payload':{}})
        from orchestrator.assistant_journey import catalog
        state = self.ledger.snapshot(); state['standard'] = standard.read(self.ledger)
        state['workspace'] = {'name':'fixture'}; state['brainNotification'] = {'transport':'owned_app_server'}
        self.assertTrue(all(not a['available'] for a in catalog(state).values()))
        self.conserved()

    def test_cancel_resolution_assessment_never_asks_for_another_cancel(self):
        before = continuation(self.ledger,self.cid)
        self.assertEqual(before['status'],'canceled_original_requires_forward_disposition')
        self.assertFalse(before['permissionResponseRequiredSeparately'])
        self.apply(); after = continuation(self.ledger,self.cid)
        self.assertEqual(after['status'],'canceled_play_disposed_unqualified')
        self.assertFalse(after['permissionResponseRequiredSeparately'])
        self.assertEqual(after['actionsTaken'],[])

    def test_cli_uses_existing_read_only_routes_and_no_native_client(self):
        from orchestrator.cli import main
        args = ['orchestrator','--platform',str(self.registry.root),'--workspace','v3',
                'canceled-play-preview',str(self.binding_file),self.cid]
        with (patch('sys.argv',args),patch('sys.stdout',new_callable=io.StringIO) as out,
              patch('orchestrator.native_read_client.ReadProxy.__enter__',side_effect=AssertionError('no native connection'))):
            main(); p = json.loads(out.getvalue())
        self.assertEqual(p,self.prepare()); self.assertEqual(database_proof(self.ledger.db),self.proof)

    def test_concurrent_confirmations_write_at_most_one_disposition(self):
        p = self.prepare(); backup = self.backup(p); results = []; errors = []
        def one():
            try: results.append(cp.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],
                                           writers_stopped=True,backup_root=backup))
            except Refusal as e: errors.append(str(e))
        threads = [threading.Thread(target=one) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(20); self.assertFalse(t.is_alive())
        self.assertTrue(results); self.assertTrue(all(r == results[0] for r in results))
        with standard.read_db(self.ledger.db) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM snapshots WHERE kind=?',(cp.KIND,)).fetchone()[0],1)
        self.conserved()

    def test_other_live_claims_runs_and_usage_are_never_touched(self):
        other = Ledger(self.f.root/'other-preserved')
        with other.tx() as db:
            m = other.get(db,'meta',1); m['standardRun'] = {'id':'old','status':'paused',
                'brainObservedTokens':1049625,'usageHighWater':1049625,'expiresAt':1,'gaps':['preserved-unknown']}
            other.put(db,'meta',1,m)
        claims = [self.f.root/('prior-claim-'+str(i)) for i in range(2)]
        for p in claims: p.write_bytes(b'preserved consumed original claim'); p.chmod(0o600)
        before = database_proof(other.db)
        self.apply()
        self.assertEqual(database_proof(other.db),before)
        self.assertTrue(all(p.read_bytes() == b'preserved consumed original claim' for p in claims))

    def test_task_pending_control_or_run_change_prevents_review(self):
        old = self.before['meta']
        for field,value in (('tasks',[{'id':'uncertain'}]),('merges',[{'status':'issued'}]),
                            ('status','stopping'),('checkpoint',{'outcome':'unknown'}),('recovery',{'id':'old'})):
            with self.subTest(field=field):
                changed = copy.deepcopy(old); changed['standardRun'][field] = value
                with self.ledger.tx() as db: self.ledger.put(db,'meta',1,changed)
                with self.assertRaises(Refusal): self.prepare()
                with self.ledger.tx() as db: self.ledger.put(db,'meta',1,old)
        with self.ledger.tx() as db:
            self.ledger.put(db,'commands','other',{'id':'other','kind':'standard_pause','status':'queued'})
        with self.assertRaises(Refusal): self.prepare()

    def test_scope_changes_and_source_changes_invalidate_review_without_claim(self):
        p = self.prepare(); backup = self.backup(p)
        with patch.object(cp,'source_hash',return_value='a'*64):
            with self.assertRaises(Refusal): cp.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],
                                                      writers_stopped=True,backup_root=backup)
        self.assertFalse((self.ledger.root/cp.FENCE).exists())
        self.conserved()

    def test_sidecar_alias_or_changed_schema_never_counts_as_preserved(self):
        alias = self.ledger.root/'alias'
        os.symlink(self.f.home,alias)
        with self.assertRaises(Refusal): self.prepare()
        alias.unlink()  # Disposable fixture corruption only.
        self.apply()
        with sqlite3.connect(self.ledger.db) as db: db.execute('CREATE TABLE changed_schema (id TEXT)')
        self.assertEqual(cp.status(self.ledger)['status'],'incomplete_or_changed')
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass

    def test_unsupported_or_inaccessible_sidecar_is_not_silently_skipped(self):
        fifo = self.ledger.root/'unsupported-pipe'
        os.mkfifo(fifo,0o600)
        try:
            with self.assertRaises(Refusal): self.prepare()
        finally: fifo.unlink()  # Disposable fixture only.
        directory = self.ledger.root/'not-private'; directory.mkdir(mode=0o755)
        try:
            with self.assertRaises(Refusal): self.prepare()
        finally: directory.rmdir()  # Disposable fixture only.

    def test_malformed_private_review_never_reaches_the_claim_boundary(self):
        p = self.prepare()
        for name,value in (('command',[]),('run',None),('bindingEpoch',False),('databaseProofs',{})):
            q = copy.deepcopy(p['request']); q[name] = value
            with self.assertRaises((Refusal,TypeError)):
                cp.confirm(self.registry,self.ledger,q,digest(q),writers_stopped=True,backup_root=self.f.root/'absent')
        self.assertFalse((self.ledger.root/cp.FENCE).exists())

    def test_boundary_fields_cannot_authorize_execution_or_hide_unknowns(self):
        p = self.prepare()
        for field,value in (('continuationAuthorized',True),('terminalSafety','safe'),
                            ('brainReloaded',True),('brainReceiptReconstructed',True)):
            changed = copy.deepcopy(p['request']); changed['boundary'][field] = value
            with self.assertRaises(Refusal): cp.confirm(self.registry,self.ledger,changed,digest(changed))
        self.assertFalse((self.ledger.root/cp.FENCE).exists()); self.conserved()


if __name__ == '__main__': unittest.main()
