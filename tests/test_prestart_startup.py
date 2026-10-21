"""New preparation authority, not an old readiness retry. Disposable state only."""
import copy
import contextlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import unittest
from unittest.mock import patch

from orchestrator import prestart_startup as startup, startup_mailbox as mailbox
from orchestrator import readiness_prestart_resolution as prior, standard, readiness_owned as owned
from orchestrator.core import Refusal, canonical, digest
from orchestrator.public_pilot_inspection import exclusive
import test_readiness_deadline_resolution as predecessor_fixture


class StartupTest(unittest.TestCase):
    def setUp(self):
        name='test_admitted_resolution_preserves_both_claims_and_original_source_lineage' if 'admitted' in self._testMethodName else 'runTest'
        self.f=predecessor_fixture.PrestartResolutionTest(name); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.r=self.f.r; self.registry=self.f.registry; self.ledger=self.f.ledger
        self.r.callback=None
        # One actual fixture Git identity; the native fixtures normally need
        # only a directory, but this new control also binds its repository view.
        repo=self.f.r.f.repo
        if subprocess.run(['git','-C',str(repo),'rev-parse','--verify','HEAD'],capture_output=True).returncode:
            subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@localhost',
                'commit','--allow-empty','-qm','fixture'],check=True,capture_output=True)
        self.calls=[]; self.mode='ok'; self.usage=123; outer=self
        base=self.r.Proxy
        class Proxy(base):
            def _rpc(self,method,params):
                outer.calls.append(method)
                if method=='turn/start' and outer.mode=='early_permission':
                    self._early_requests=[{'id':9,'method':'item/commandExecution/requestApproval','params':{}}]
                return super()._rpc(method,params)
            def _line(self):
                if outer.mode=='permission': return {'id':1,'method':'item/commandExecution/requestApproval','params':{}}
                if outer.mode=='stop':
                    startup.stop(outer.ledger,outer.q['reviewHash']); return {'method':'fixture/tick'}
                if outer.mode=='disconnect': raise OSError('Synthetic lost original connection')
                if outer.mode=='repository_drift':
                    (outer.r.f.repo/'unapproved-fixture-change.txt').write_text('Detected, never repaired or accepted')
                box=Path(outer.q['request']['mailbox']); h=box/'handoff.json'
                if outer.mode!='missing_receipt':
                    schema=mailbox.state(h)['resultSchema']; schema['proposal']={'objective':'Propose bounded pilot',
                        'steps':['Review exact new phase'],'checks':['Verify policy and usage'],
                        'stoppingCheckpoint':'Stop before Play'}
                    exclusive(box/'fixture-result.json',schema); mailbox.complete(h,box/'fixture-result.json')
                if outer.usage is not None:
                    self._on_effect_event({'method':'thread/tokenUsage/updated','params':{
                        'threadId':outer.r.f.brain,'tokenUsage':{'last':{'totalTokens':outer.usage}}}})
                row={'method':'turn/completed','params':{'threadId':outer.r.f.brain,
                    'turn':{'id':outer.r.turn,'status':'completed'}}}
                self._on_effect_event(row); return row
        for p in (patch.object(startup,'ReadProxy',Proxy),patch.object(startup,'WakeProxy',Proxy),
                  patch.object(startup,'validate_endpoint')):
            p.start(); self.addCleanup(p.stop)
        self.before=startup.databases(self.registry)

    def prepare(self):
        self.q=startup.prepare(self.registry,self.ledger,self.f.binding_file,self.f.cid,self.f.source,
            max_tokens=100 if self.f.a else 10000)
        return self.q

    def apply(self):
        self.prepare(); self.b=self.r.f.root/'startup-backup'
        startup.backup(self.registry,self.ledger,self.q['request'],self.b,writers_stopped=True)
        return startup.confirm(self.registry,self.ledger,self.q['request'],self.q['reviewHash'],
            writers_stopped=True,backup_root=self.b)

    def conserved(self):
        self.assertEqual(startup.databases(self.registry),self.before)
        with standard.read_db(self.ledger.db) as db:
            self.assertEqual(self.ledger.get(db,'commands',self.f.cid),self.f.original)
        for name,raw in self.f.pins.items(): self.assertEqual((self.ledger.root/name).read_bytes(),raw)

    def test_prepare_is_new_purpose_read_only_no_timer(self):
        q=self.prepare(); self.assertEqual(q['validUntil'],'scope_changes')
        self.assertEqual(q['request']['phase']['purpose'],'new_startup_preparation')
        self.assertEqual(q,self.prepare()); self.assertNotIn('thread/resume',self.calls); self.assertNotIn('turn/start',self.calls)
        self.assertFalse(startup.blocked(self.ledger)); self.conserved()

    def test_one_new_load_turn_receipt_and_usage_without_catalog_or_old_receipt(self):
        s=self.apply(); self.assertEqual(s['status'],'startup_preparation_completed')
        self.assertFalse(s['originalReadinessReceived']); self.assertTrue(s['newReceiptRecorded'])
        self.assertEqual(self.calls.count('thread/resume'),1); self.assertEqual(self.calls.count('turn/start'),1)
        root=Path(self.q['request']['journal']); usage=mailbox.read(root/'usage.json')
        self.assertEqual(usage['observedLastTurnTokens'],self.usage)
        self.assertEqual(usage['chargedReservationFloor'],max(self.usage,self.q['request']['phase']['maxTokens']))
        self.assertEqual(usage['futurePhaseCeiling'],self.q['request']['phase']['carriedPhaseCeiling']-usage['chargedReservationFloor'])
        self.assertFalse(standard.read(self.ledger)['available']); self.assertTrue(self.r.proxies[-1].closed)
        self.assertEqual(startup.status_in(self.ledger),s)
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass
        with self.assertRaises(Refusal): self.r.deliver()
        with self.assertRaises(Refusal): prior.prepare(self.registry,self.ledger,self.f.binding_file,self.f.cid,self.f.source)
        old=self.calls.copy()
        with self.assertRaises(Refusal): startup.confirm(self.registry,self.ledger,self.q['request'],self.q['reviewHash'],writers_stopped=True,backup_root=self.b)
        with self.assertRaises(Refusal): self.prepare()
        self.assertEqual(self.calls,old); self.conserved()

    def test_admitted_same_project_preserves_both_claims_and_carried_usage(self):
        self.usage=23
        self.test_one_new_load_turn_receipt_and_usage_without_catalog_or_old_receipt()
        self.assertIsNotNone(self.q['request']['phase']['carriedPostPreparationTokens'])

    def test_missing_usage_is_not_zero_and_does_not_enable_play(self):
        self.usage=None; self.apply(); u=mailbox.read(Path(self.q['request']['journal'])/'usage.json')
        self.assertIsNone(u['observedLastTurnTokens']); self.assertIn('startup_usage_missing_or_incomplete',u['gaps'])
        self.assertEqual(u['chargedReservationFloor'],10000); self.conserved()

    def test_over_budget_retains_actual_charge_and_checkpoint(self):
        self.usage=12000; self.assertEqual(self.apply()['status'],'startup_budget_checkpoint')
        self.assertEqual(mailbox.read(Path(self.q['request']['journal'])/'usage.json')['chargedReservationFloor'],12000)
        self.conserved()

    def test_lost_load_ack_consumes_no_turn_no_retry(self):
        self.r.lost_ack=True; s=self.apply(); self.assertEqual(s['status'],'pre_turn_stopped')
        self.assertEqual(self.calls.count('thread/resume'),1); self.assertNotIn('turn/start',self.calls); self.conserved()

    def test_lost_turn_ack_stays_unknown_no_retry(self):
        self.r.lost_turn=True; s=self.apply(); self.assertEqual(s['status'],'incomplete_unknown')
        self.assertEqual(self.calls.count('turn/start'),1); self.conserved()

    def test_permission_requests_never_answered_or_canceled(self):
        self.mode='permission'; s=self.apply(); self.assertEqual(s['status'],'incomplete_unknown')
        self.assertFalse(s['newReceiptRecorded']); self.assertTrue((Path(self.q['request']['journal'])/'attention.json').exists())
        self.assertFalse(any('respond' in m or 'interrupt' in m for m in self.calls)); self.conserved()

    def test_early_permission_is_fenced_before_completion(self):
        self.mode='early_permission'; self.assertEqual(self.apply()['status'],'incomplete_unknown'); self.conserved()

    def test_stop_is_cooperative_and_never_cancel_or_retry(self):
        self.mode='stop'; s=self.apply(); self.assertEqual(s['status'],'incomplete_unknown')
        self.assertTrue((Path(self.q['request']['journal'])/'stop.json').exists()); self.conserved()

    def test_connection_loss_never_reconnects(self):
        self.mode='disconnect'; s=self.apply(); self.assertEqual(s['status'],'incomplete_unknown')
        self.assertEqual(self.calls.count('turn/start'),1); self.conserved()

    def test_completed_without_receipt_remains_unknown(self):
        self.mode='missing_receipt'; self.assertEqual(self.apply()['status'],'incomplete_unknown'); self.conserved()

    def test_old_approval_no_backup_or_corrupt_backup_never_claims(self):
        q=self.prepare()
        with self.assertRaises(Refusal): startup.confirm(self.registry,self.ledger,q['request'],self.f.original['payload']['readinessStart']['sourceHash'])
        with self.assertRaises(Refusal): startup.confirm(self.registry,self.ledger,q['request'],q['reviewHash'])
        b=self.r.f.root/'startup-backup'; startup.backup(self.registry,self.ledger,q['request'],b,writers_stopped=True)
        (b/'review.json').write_text('{}')
        with self.assertRaises(Refusal): startup.confirm(self.registry,self.ledger,q['request'],q['reviewHash'],writers_stopped=True,backup_root=b)
        self.assertFalse(startup.blocked(self.ledger)); self.conserved()

    def test_drift_between_review_and_claim_refuses_without_native_effect(self):
        q=self.prepare(); b=self.r.f.root/'startup-backup'
        startup.backup(self.registry,self.ledger,q['request'],b,writers_stopped=True)
        binding=json.loads(self.f.binding_file.read_text()); binding['brains'][self.r.f.brain]['workspaceId']='foreign'
        self.f.binding_file.write_text(canonical(binding)); old=self.calls.copy()
        with self.assertRaises(Refusal): startup.confirm(self.registry,self.ledger,q['request'],q['reviewHash'],writers_stopped=True,backup_root=b)
        self.assertEqual(self.calls,old); self.assertFalse(startup.blocked(self.ledger))

    def test_partial_claim_and_missing_fence_never_restore_writes(self):
        q=self.prepare(); root=Path(q['request']['journal']); root.parent.mkdir(mode=0o700,exist_ok=True)
        root.mkdir(mode=0o700)
        self.assertEqual(startup.status_in(self.ledger)['status'],'incomplete_or_changed')
        with self.assertRaises(Refusal):
            with self.ledger.tx(): pass
        with self.assertRaises(Refusal): self.prepare()
        self.conserved()

    def test_sandbox_helper_is_standalone_and_closed(self):
        self.apply(); box=Path(self.q['request']['mailbox']); helper=Path(mailbox.__file__)
        result=subprocess.run(['python3','-I','-B',str(helper),'--handoff',str(box/'handoff.json'),'state'],
            cwd=self.r.f.repo,capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout)['purpose'],'new_startup_preparation')
        h=mailbox.handoff(box/'handoff.json'); value=mailbox.state(box/'handoff.json')['resultSchema']; value['catalog']={}
        with self.assertRaises(ValueError): mailbox.validate_result(h,value)
        with patch('sqlite3.connect',side_effect=AssertionError('SQL forbidden')),patch('socket.socket',side_effect=AssertionError('Socket forbidden')):
            mailbox.state(box/'handoff.json')
        self.conserved()

    def test_changed_old_row_cannot_be_hidden_by_startup_status(self):
        self.apply()
        with contextlib.closing(sqlite3.connect(self.ledger.db,isolation_level=None)) as db: db.execute("UPDATE commands SET data='{}'")
        self.assertEqual(startup.status_in(self.ledger)['status'],'incomplete_or_changed')

    def test_bad_loaded_policy_stops_before_new_turn(self):
        self.r.policy_bad=True; self.assertEqual(self.apply()['status'],'pre_turn_stopped')
        self.assertEqual(self.calls.count('thread/resume'),1); self.assertNotIn('turn/start',self.calls); self.conserved()

    def test_changed_native_scope_consumes_attempt_without_loading(self):
        self.prepare(); b=self.r.f.root/'startup-backup'
        startup.backup(self.registry,self.ledger,self.q['request'],b,writers_stopped=True)
        self.r.latest={'id':'another-native-turn','status':'completed'}
        s=startup.confirm(self.registry,self.ledger,self.q['request'],self.q['reviewHash'],writers_stopped=True,backup_root=b)
        self.assertEqual(s['status'],'pre_turn_stopped'); self.assertNotIn('thread/resume',self.calls); self.conserved()

    def test_source_drift_refuses_before_claim(self):
        self.prepare(); b=self.r.f.root/'startup-backup'
        startup.backup(self.registry,self.ledger,self.q['request'],b,writers_stopped=True)
        with patch.object(owned.preplay,'source_hash',return_value='a'*64):
            with self.assertRaises(Refusal): startup.confirm(self.registry,self.ledger,self.q['request'],self.q['reviewHash'],writers_stopped=True,backup_root=b)
        self.assertFalse(startup.blocked(self.ledger)); self.assertNotIn('thread/resume',self.calls); self.conserved()

    def test_fence_race_rolls_back_ordinary_writer(self):
        with self.assertRaises(Refusal):
            with self.ledger.tx() as db:
                meta=self.ledger.get(db,'meta',1); meta['paused']=False; self.ledger.put(db,'meta',1,meta)
                exclusive(self.ledger.root/startup.FENCE,{'partial':'intent'})
        self.assertEqual(startup.status_in(self.ledger)['status'],'incomplete_or_changed'); self.conserved()

    def test_completed_status_never_opens_native_client_or_renews_time(self):
        self.apply()
        with patch.object(startup,'ReadProxy',side_effect=AssertionError('No native inspection')), \
             patch.object(startup,'WakeProxy',side_effect=AssertionError('No native effects')):
            first=startup.status_in(self.ledger); self.assertEqual(startup.status_in(self.ledger),first)
        self.conserved()

    def test_missing_target_marker_is_fenced_on_raw_state_route(self):
        self.apply(); (self.ledger.root/startup.FENCE).unlink()  # disposable corruption
        from orchestrator.core import Ledger
        raw=Ledger(self.ledger.root)
        self.assertEqual(startup.status_in(raw)['status'],'incomplete_or_changed')
        with self.assertRaises(Refusal):
            with raw.tx(): pass
        self.conserved()

    def test_repository_change_fences_result_without_reverting_or_accepting_it(self):
        self.mode='repository_drift'; self.assertEqual(self.apply()['status'],'incomplete_unknown')
        self.assertTrue((self.r.f.repo/'unapproved-fixture-change.txt').exists()); self.conserved()

    def test_execution_helper_must_be_current_reviewed_implementation(self):
        q=self.prepare()['request']; wrong=copy.deepcopy(q); wrong['executionSource']['sourceHash']='f'*64
        self.assertFalse(startup.valid(wrong))
        wrong=copy.deepcopy(q); wrong['executionSource']['root']=str(self.r.f.root)
        with self.assertRaises(Refusal): startup.current(self.registry,self.ledger,wrong)
        self.assertNotIn('thread/resume',self.calls); self.conserved()

    def test_repository_metadata_never_runs_configured_diff_helper(self):
        repo=self.r.f.repo; f=repo/'tracked.txt'; f.write_text('before')
        subprocess.run(['git','-C',str(repo),'add','tracked.txt'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@localhost',
            'commit','-qm','tracked fixture'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(repo),'config','diff.external','/usr/bin/false'],check=True,capture_output=True)
        f.write_text('after')
        self.prepare(); self.assertNotIn('thread/resume',self.calls); self.conserved()
