"""New maintenance attempt; old positive load and unknown planning stay intact."""
import copy
import contextlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

from orchestrator import maintenance_load as api, canceled_continuation as planning
from orchestrator import brain_memory, canceled_play, canceled_load
from orchestrator.core import Refusal, canonical, digest
from orchestrator.host_lifecycle import write_record
from orchestrator.partial_admission import database_proof
import test_canceled_load as fixture


class MaintenanceLoadTest(unittest.TestCase):
    def setUp(self):
        self.l=fixture.CanceledLoadTest('runTest'); self.l.setUp(); self.addCleanup(self.l.doCleanups)
        self.f,self.registry,self.ledger=self.l.f,self.l.registry,self.l.ledger
        self.assertEqual(self.l.apply()['status'],'load_observed_idle')
        self.old_file=self.f.root/'old-load.json'; write_record(self.old_file,self.l.q)
        # Actual local numeric fixture, before the separate disposition. The
        # older load's pre-accounting snapshot is not modified or backfilled.
        for file in (self.f.root/'usage-home').rglob('*.jsonl'): file.chmod(0o600)
        with self.ledger.tx() as db:
            meta=self.ledger.get(db,'meta',1); run=meta['standardRun']
            report=brain_memory.collect(self.ledger,run)
            run.update(brainObservedTokens=report['tokens']['total_tokens'],brainUsageCoverage='observed_partial',
                usageHighWater=report['tokens']['total_tokens'],usageReport=report)
            self.ledger.put(db,'meta',1,meta)
            db.execute('INSERT INTO snapshots VALUES(?,?,?)',(digest(report),'standard_usage',canonical(report)))
        self.l.h.old.apply()
        candidate=self.l.q['provenance']['scope']['binding']; package=self.l.h.package
        contract={'protocol':planning.transport.PROTOCOL,'method':planning.transport.METHOD,
            'sourceCommit':package['sourceCommit'],'sourceTree':package['sourceTree'],
            'executableSha256':package['executableHash']}
        self.parent=planning.prepare(self.registry,self.ledger,self.l.h.old.binding_file,self.l.h.old.cid,
            self.l.candidate,contract,1,forward_usage_evidence=True)['request']
        archive=self.f.root/'parent-backup'; planning.backup(self.registry,self.ledger,self.parent,archive,writers_stopped=True)
        outer=self
        class ParentProxy:
            def __init__(self,endpoint): self.process=object(); self.endpoint=endpoint
            def __enter__(self): return self
            def __exit__(self,*_): self.process=None
            def _rpc(self,method,params):
                outer.assertEqual(method,'thread/turns/list')
                return {'data':[{'id':outer.f.turn,'status':'interrupted'}],'nextCursor':None}
        with patch.object(planning,'Proxy',ParentProxy),patch.object(planning.transport.Subscription,'_sample',
                side_effect=Refusal(api.lifecycle.REFUSAL)):
            result=planning.confirm(self.registry,self.ledger,self.parent,digest(self.parent),writers_stopped=True,backup_root=archive)
        self.assertEqual(result['status'],'incomplete_unknown')
        self.parent_file=self.f.root/'parent.json'; write_record(self.parent_file,self.parent)
        self.q=self.prepare()['request']; self.backup=self.f.root/'maintenance-backup'
        api.backup(self.registry,self.ledger,self.q,self.backup,writers_stopped=True)
        self.before=[database_proof(p) for p in (self.registry.db,self.ledger.db)]
        self.sidecars=canceled_play.sidecars(self.ledger)
        self.old_pins=api.lifecycle.inventory(self.l.q['journal'])
        self.parent_pins=api.lifecycle.inventory(self.parent['journal'])
        self.l.loaded=False; self.l.calls.clear()
        def at_rpc(method,params):
            if method=='thread/resume': self.assertTrue((Path(self.q['journal'])/'load.claim.json').is_file())
        self.l.callback=at_rpc

    def prepare(self): return api.prepare(self.registry,self.ledger,self.parent_file,self.old_file)
    def apply(self,q=None,**kw):
        q=q or self.q
        return api.confirm(self.registry,self.ledger,q,digest(q),writers_stopped=True,backup_root=self.backup,**kw)
    def conserved(self):
        self.assertEqual([database_proof(p) for p in (self.registry.db,self.ledger.db)],self.before)
        self.assertEqual(canceled_play.sidecars(self.ledger),self.sidecars)
        self.assertEqual(api.lifecycle.inventory(self.l.q['journal']),self.old_pins)
        self.assertEqual(api.lifecycle.inventory(self.parent['journal']),self.parent_pins)
        self.assertEqual(canceled_load.status(self.l.q)['status'],'load_observed_idle')
        self.assertEqual(planning.status(self.parent)['nativeOutcome'],'unknown')
        self.assertEqual(canceled_play.status(self.ledger)['status'],'disposed_unqualified')

    def test_one_new_metadata_load_no_turn_replay_or_safety_inference(self):
        result=self.apply(); self.assertEqual(result['status'],'maintenance_load_observed_idle',result)
        self.assertEqual(api.status(self.q),result)
        methods=[m for m,_ in self.l.calls]; self.assertEqual(methods.count('thread/resume'),1)
        self.assertNotIn('turn/start',methods); self.assertNotIn('turn/interrupt',methods)
        self.assertNotIn('thread/subscribe',methods)
        self.assertEqual(next(p for m,p in self.l.calls if m=='thread/resume'),api.prior.inspection.load_params(self.q['scope']))
        self.assertEqual(result['boundary']['historicalTerminalSafety'],'unknown')
        self.assertFalse(result['boundary']['resumeAuthorized']); self.conserved()

    def test_prepare_backup_status_are_file_only_and_scope_bound_not_time_bound(self):
        with patch.object(api.prior.inspection,'InspectionProxy',side_effect=AssertionError('No native connection')):
            with patch('time.time',return_value=self.parent['original']['run']['expiresAt']+100):
                value=self.prepare(); self.assertEqual(value['request'],self.q); self.assertEqual(value['validUntil'],'scope_changes')
                api.backup(self.registry,self.ledger,self.q,self.f.root/'expired-backup',writers_stopped=True)
                self.assertEqual(api.status(self.q)['status'],'not_submitted')
        self.assertEqual(self.l.calls,[]); self.conserved()

    def test_expired_phase_allows_only_maintenance_and_keeps_planning_expired(self):
        with patch('time.time',return_value=self.parent['original']['run']['expiresAt']+1):
            with self.assertRaisesRegex(Refusal,'clock expired'): planning.current(self.registry,self.ledger,self.parent)
            self.assertEqual(self.apply()['status'],'maintenance_load_observed_idle')
            with self.assertRaisesRegex(Refusal,'Maintenance load claim'): planning.current(self.registry,self.ledger,self.parent)
        self.assertFalse(api.BOUNDARY['phaseExpiryChanged']); self.conserved()

    def test_wrong_confirmation_quiescence_or_backup_cannot_claim(self):
        with self.assertRaises(Refusal): api.confirm(self.registry,self.ledger,self.q,'f'*64,writers_stopped=True,backup_root=self.backup)
        with self.assertRaises(Refusal): api.confirm(self.registry,self.ledger,self.q,digest(self.q))
        (self.backup/'private-0.bin').write_bytes(b'corrupt disposable backup')
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.l.calls,[]); self.conserved()

    def test_unknown_ack_is_consumed_without_new_id_source_or_host_retry(self):
        self.l.fail_load=True; result=self.apply(); self.assertEqual(result['status'],'consumed_outcome_unknown')
        with self.assertRaises((Refusal,OSError)): self.apply()
        with self.assertRaises(Refusal): self.prepare()
        changed=copy.deepcopy(self.q); changed['journal']+='-new-id'
        with self.assertRaises(Refusal): self.apply(changed)
        self.assertEqual([m for m,_ in self.l.calls].count('thread/resume'),1); self.conserved()

    def test_partial_original_load_never_becomes_a_new_maintenance_attempt(self):
        extra=Path(self.l.q['journal'])/'failure.json'; write_record(extra,{'unknown':True})
        with self.assertRaises(Refusal): self.prepare()
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.l.calls,[])

    def test_partial_planning_unknown_turn_or_new_effect_is_not_a_load_lineage(self):
        write_record(Path(self.parent['journal'])/'turn-start.claim.json',{'unknown':True})
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.l.calls,[])

    def test_loaded_active_and_native_permission_wait_are_not_adopted(self):
        self.l.activity={'type':'active','activeFlags':['waitingOnApproval']}
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.l.calls]); self.conserved()

    def test_already_loaded_is_not_loaded_again(self):
        self.l.loaded=True
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.l.calls]); self.conserved()

    def test_latest_turn_identity_drift_does_not_load(self):
        self.l.turn='different-interrupted-turn'
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.l.calls]); self.conserved()

    def test_bad_post_load_policy_and_unknown_trackers_stay_unknown(self):
        self.l.terminals=None
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown'); self.conserved()

    def test_post_load_policy_must_be_actually_reported(self):
        self.l.bad_policy=True
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown'); self.conserved()

    def test_auth_or_mcp_gap_never_starts_sign_in_or_load(self):
        self.l.auth=False
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.l.calls]); self.conserved()

    def test_unreviewed_mcp_inventory_never_loads(self):
        self.l.mcp=[{'name':'unexpected-tools'}]
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.l.calls]); self.conserved()

    def test_unknown_original_connection_close_cannot_authorize_new_load(self):
        file=Path(self.l.q['journal'])/'outcome.json'; row=planning._read_private(file)
        row['connectionClosed']=False; file.write_text(canonical(row))
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.l.calls,[])

    def test_old_rows_or_usage_mutation_fences_before_maintenance_claim(self):
        # Deliberate disposable corruption: the production writer correctly
        # refuses this mutation even before the maintenance control sees it.
        with contextlib.closing(sqlite3.connect(self.ledger.db)) as db:
            meta=json.loads(db.execute('SELECT data FROM meta WHERE id=1').fetchone()[0])
            meta['standardRun']['usageHighWater']+=1
            db.execute('UPDATE meta SET data=? WHERE id=1',(canonical(meta),)); db.commit()
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.l.calls,[])

    def test_partial_new_intent_never_rearms_or_reconnects(self):
        root=Path(self.q['journal']); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        write_record(root/'intent.json',{'kind':api.KIND,'reviewHash':digest(self.q)})
        self.assertEqual(api.status(self.q)['status'],'consumed_outcome_unknown')
        with self.assertRaises((Refusal,OSError)): self.apply()
        with self.assertRaises(Refusal): self.prepare()
        self.assertEqual(self.l.calls,[]); self.conserved()

    def test_status_is_historical_and_file_only_after_source_or_time_changes(self):
        result=self.apply(); calls=copy.deepcopy(self.l.calls)
        with patch.object(api.prior.inspection,'InspectionProxy',side_effect=AssertionError('No connection')),\
             patch.object(planning.old,'source_hash',return_value='f'*64):
            self.assertEqual(api.status(self.q),result)
        self.assertEqual(calls,self.l.calls); self.conserved()

    def test_unlisted_new_journal_records_are_not_silently_ignored(self):
        self.apply(); write_record(Path(self.q['journal'])/'unlisted-effect.json',{'unknown':True})
        with self.assertRaises(Refusal): api.status(self.q)
        self.conserved()

    def test_old_original_load_control_still_refuses_disposed_state(self):
        with self.assertRaises(Refusal): canceled_load.prepare(self.registry,self.ledger,self.l.h.file,self.l.candidate)
        self.assertEqual(self.l.calls,[]); self.conserved()

    def test_historical_host_review_does_not_require_or_execute_its_old_source(self):
        with patch.object(api.prior.shared,'source_tree',side_effect=AssertionError('No historical source execution')):
            self.assertEqual(self.prepare()['request'],self.q)
            self.assertEqual(self.apply()['status'],'maintenance_load_observed_idle')
        self.conserved()

    def test_changed_historical_host_review_cannot_replace_issued_pin(self):
        file=self.l.h.file; row=json.loads(file.read_bytes()); row['sourceTree']='f'*40
        file.write_text(canonical(row))
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.l.calls,[])

    def test_successor_or_continuous_owner_retains_exclusion(self):
        root=api.continuous.location(self.registry,self.parent); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.l.calls,[]); self.conserved()

    def test_maintenance_claim_fences_competing_planning_at_the_same_database_lock(self):
        root=Path(self.q['journal']); root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700)
        write_record(root/'intent.json',{'kind':api.KIND,'reviewHash':digest(self.q)})
        with self.assertRaisesRegex(Refusal,'Maintenance load claim'): planning.current(self.registry,self.ledger,self.parent)
        with self.assertRaisesRegex(Refusal,'Maintenance load claim'):
            api.lifecycle.prepare(self.registry,self.ledger,self.parent_file)
        self.assertEqual(self.l.calls,[]); self.conserved()

    def test_bound_host_pid_package_and_candidate_epochs_cannot_change(self):
        with patch.object(api.prior.shared,'live_process',side_effect=Refusal('Changed PID')):
            with self.assertRaises(Refusal): self.apply()
        os.utime(self.l.candidate,None)
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.l.calls,[])

    def test_wrong_source_interpreter_or_alternate_journal_refuses_before_connect(self):
        for key in ('sourceHash','interpreter','journal'):
            q=copy.deepcopy(self.q); q[key]='changed'
            with self.subTest(key=key),self.assertRaises(Refusal): self.apply(q)
        self.assertFalse(Path(self.q['journal']).exists()); self.assertEqual(self.l.calls,[]); self.conserved()

    def test_backup_cannot_overlap_ledger_registry_native_home_or_checkout(self):
        for p in (self.ledger.root,self.registry.root,self.f.home,self.f.repo,self.l.h.directory):
            with self.subTest(path=p),self.assertRaises(Refusal):
                api.backup(self.registry,self.ledger,self.q,p/'forbidden',writers_stopped=True)
            self.assertFalse((p/'forbidden').exists())
        self.conserved()

    def test_no_native_credential_bytes_are_read_or_copied(self):
        real=Path.open
        def guarded(path,*a,**kw):
            self.assertNotEqual(path,self.f.home/'auth.json'); return real(path,*a,**kw)
        with patch.object(Path,'open',guarded):
            self.assertEqual(self.apply()['status'],'maintenance_load_observed_idle')
        self.conserved()

    def test_credential_paths_refuse_before_any_review_bytes_are_opened(self):
        real=Path.open; secret=self.f.home/'auth.json'
        def guarded(path,*a,**kw):
            self.assertNotEqual(path,secret); return real(path,*a,**kw)
        with patch.object(Path,'open',guarded):
            with self.assertRaises(Refusal): api.prepare(self.registry,self.ledger,secret,self.old_file)
            with self.assertRaises(Refusal): api.prepare(self.registry,self.ledger,self.parent_file,secret)
            with self.assertRaises(Refusal): api.read_review(secret)
        self.assertEqual(self.l.calls,[]); self.conserved()

    def test_stop_at_pre_load_boundary_wins_without_native_cancel(self):
        def callback(method,params):
            if method=='account/read': api.stop(self.q,digest(self.q))
        self.l.callback=callback
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.l.calls]); self.conserved()

    def test_changed_own_intent_prevents_load_even_when_old_scope_is_unchanged(self):
        def callback(method,params):
            if method=='account/read':
                (Path(self.q['journal'])/'intent.json').write_text(canonical({'kind':api.KIND,'reviewHash':'f'*64}))
        self.l.callback=callback
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        self.assertNotIn('thread/resume',[m for m,_ in self.l.calls]); self.conserved()

    def test_corrupt_new_ack_cannot_produce_a_positive_result_or_another_load(self):
        def callback(method,params):
            if method=='thread/backgroundTerminals/list':
                (Path(self.q['journal'])/'load-ack.json').write_text(canonical({'acknowledged':False}))
        self.l.callback=callback
        self.assertEqual(self.apply()['status'],'consumed_outcome_unknown')
        with self.assertRaises((Refusal,OSError)): self.apply()
        self.assertEqual([m for m,_ in self.l.calls].count('thread/resume'),1); self.conserved()

    def test_unknown_proxy_exit_preserves_consumed_unknown(self):
        with patch.object(api.prior.inspection.ReadProxy,'__exit__',side_effect=OSError('Lost close')):
            result=self.apply()
        self.assertEqual(result['status'],'consumed_outcome_unknown'); self.assertFalse(result['connectionClosed'])
        self.assertEqual(api.status(self.q),result); self.conserved()

    def test_concurrent_confirmations_have_one_permanent_owner(self):
        results=[]
        def run():
            try: results.append(self.apply()['status'])
            except (Refusal,OSError): results.append('refused')
        workers=[threading.Thread(target=run) for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(15); self.assertFalse(worker.is_alive())
        self.assertEqual(sorted(results),['maintenance_load_observed_idle','refused'])
        self.assertEqual([m for m,_ in self.l.calls].count('thread/resume'),1); self.conserved()


if __name__=='__main__': unittest.main()
