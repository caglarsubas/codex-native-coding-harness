"""End-to-end disposable admission; old source/claims remain immutable."""
import copy
import contextlib
import os
from pathlib import Path
import subprocess
import sqlite3
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator import worker_phase_admission as api, standard, projects, missions
from orchestrator import standard_successor as successor
from orchestrator.core import Ledger, Refusal, canonical
from orchestrator.core import digest
from orchestrator.app_server_wake import AppServerWake
from orchestrator.workspaces import fingerprint
import test_post_preparation_usage as fixtures
import test_standard_run_mailbox as original_fixture
from test_missions import specification, request
from test_native_policy_evidence import CONTRACT
import test_standard_successor as target_fixtures


class AdmissionTest(unittest.TestCase):
    def setUp(self):
        state={}; original_setup=original_fixture.RunMailboxTest.setUp; record=projects.record
        def setup(f):
            original_setup(f)
            subprocess.run(['git','-C',str(f.repo),'remote','add','origin','https://github.com/fixture/source.git'],check=True,capture_output=True)
            repo=f.root/'worker-checkout'; repo.mkdir(mode=0o700)
            subprocess.run(['git','init','-q',str(repo)],check=True,capture_output=True)
            subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=f@example.invalid',
                '-c','commit.gpgsign=false','commit','--allow-empty','-qm','Separate base'],check=True,capture_output=True)
            subprocess.run(['git','-C',str(repo),'remote','add','origin','https://github.com/fixture/target.git'],check=True,capture_output=True)
            target=Ledger(f.root/'worker-ledger'); brain=str(uuid.uuid4()); catalog=str(uuid.uuid4()); project=str(uuid.uuid4())
            target.initialize({'schemaVersion':1,'brainId':brain,'repositories':[{'id':'a','path':str(repo),
                'projectId':'projectless','ref':'HEAD','policyProfile':'standard','mergePolicy':'manual'}]})
            f.registry.register('worker','Existing target fixture',target.root); target=f.registry.ledger('worker')
            foreign=Ledger(f.root/'foreign-ledger')
            foreign.initialize({'schemaVersion':1,'brainId':str(uuid.uuid4()),'repositories':[{'id':'a','path':str(repo),
                'projectId':'projectless','ref':'HEAD','policyProfile':'standard','mergePolicy':'manual'}]})
            f.registry.register('foreign','Existing inactive owner fixture',foreign.root)
            state['foreign']=f.registry.ledger('foreign')
            spec=specification(mode='phase_delegated'); spec['phase']['durationHours']=24
            spec['authority'].update(tokenBudget=1000,checkpointReserveTokens=100,maxTasks=1,maxParallelTasks=1)
            saved=missions.change(target,request(spec=spec))['current']
            missions.change(target,request('review',saved['revision'],documentHash=saved['documentHash'],confirmed=True))
            key=target.acquire(brain+':catalog')
            standard.brain(f.registry,target,key,{'operation':'catalog','models':[{'model':'fixture','efforts':['low']}],'source':'Synthetic actual-tool schema'})
            target.release(key,'Fixture setup complete')
            binding={'endpoint':{'fixture':'target-owned','sha256':'a'*64},'brains':{brain:{'workspaceId':'worker',
                'cwd':str(repo),'projectId':project,'catalogProjectId':catalog,'policyEvidence':CONTRACT,
                'nativePolicy':{'sandbox':'workspace-write','approvalPolicy':'on-request','codeMode':False}}}}
            file=f.root/'target-binding.json'; file.write_text(canonical(binding)); file.chmod(0o600)
            state.update(target=target,repo=repo,binding=file,catalog=catalog,entry={'projectId':catalog,
                'projectKind':'local','hostId':'local','path':str(repo),'isGitRepository':True,'label':'Existing worker fixture'})
        def catalog(registry,value,at):
            if state:
                value=copy.deepcopy(value); value['projects'].append(state['entry'])
            result=record(registry,value,at)
            if state: projects.bind(registry,'worker','local',state['catalog'],projects.catalog(registry)['hash'])
            return result
        self.u=fixtures.UsageTest('runTest')
        self.addCleanup(self.u.doCleanups)
        with patch.object(original_fixture.RunMailboxTest,'setUp',setup),patch.object(projects,'record',catalog): self.u.setUp()
        self.registry=self.u.registry; self.source=self.u.ledger
        self.target=state['target']; self.repo=state['repo']; self.binding=state['binding']
        self.foreign=state['foreign']
        self.binding_data=api.successor._read_binding(self.binding)
        self.brain=next(iter(self.binding_data['brains'])); self.project=self.binding_data['brains'][self.brain]['projectId']
        self.new_repo=self.repo
        endpoint=patch('orchestrator.native_project_assignment.validate_endpoint')
        endpoint.start(); self.addCleanup(endpoint.stop)  # Explicit synthetic endpoint; no native process.
        self.assertEqual(self.u.collect()['status'],'usage_observed')
        with standard.read_db(self.source.db) as db: self.before=fingerprint(db)
        self.backup_root=self.u.f.f.f.root/'worker-backup'
        self.controls=standard.Controls()

    def prepare(self): return api.prepare(self.registry,self.source,'worker',self.binding,self.u.out)
    def confirm(self,p=None):
        p=p or self.prepare()
        api.backup(self.registry,self.source,p['request'],self.backup_root,writers_stopped=True)
        return api.confirm(self.registry,self.source,p['request'],p['reviewHash'],writers_stopped=True,backup_root=self.backup_root)
    def conserved(self):
        with standard.read_db(self.source.db) as db: self.assertEqual(fingerprint(db),self.before)
        self.u.conserved()
    def play(self):
        p=self.controls.preview(self.target,{'operation':'play','contextHash':standard.read(self.target)['contextHash'],
            'brainAllowance':100,'durationHours':24},'owner')
        return self.controls.confirm(self.registry,self.target,{**p,'confirmed':True},'owner')

    def test_preview_and_backup_do_not_admit_play_or_mutate_source(self):
        p=self.prepare(); calls=list(self.u.f.calls)
        api.backup(self.registry,self.source,p['request'],self.backup_root,writers_stopped=True)
        self.assertFalse((self.target.root/successor.FENCE).exists()); self.assertEqual(self.target.snapshot()['commands'],[])
        self.assertEqual(calls,self.u.f.calls); self.assertEqual(p['validUntil'],'scope_changes'); self.conserved()

    def test_admission_then_separate_fresh_play_carries_original_and_post_usage(self):
        receipt=self.confirm(); self.assertFalse(receipt['boundary']['playAuthorized'])
        self.assertEqual(receipt['priorUsageHighWater'],200); self.assertEqual(receipt['priorPostPreparationTokens'],400)
        self.assertEqual(receipt['priorTerminalSafety'],'unknown'); self.assertIsNone(self.target.snapshot()['meta'].get('standardRun'))
        self.assertEqual(standard.read(self.target)['successor']['recordHash'],receipt['recordHash'])
        command=self.play(); self.assertEqual(command['payload']['successorHash'],receipt['recordHash'])
        self.assertNotEqual(standard.read(self.target)['run']['id'],self.u.q['original']['run']['id']); self.conserved()

    def test_no_automatic_play_when_confirming_same_request_again(self):
        p=self.prepare(); receipt=self.confirm(p)
        self.assertEqual(api.confirm(self.registry,self.source,p['request'],p['reviewHash'],writers_stopped=True,
            backup_root=self.backup_root),receipt)
        self.assertEqual(self.target.snapshot()['commands'],[]); self.conserved()

    def test_held_original_same_or_shared_repository_cannot_be_admitted(self):
        with self.assertRaises(Refusal): api.prepare(self.registry,self.source,self.source.workspace_id,self.binding,self.u.out)
        subprocess.run(['git','-C',str(self.repo),'remote','set-url','origin','https://github.com/fixture/source.git'],check=True,capture_output=True)
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse((self.target.root/successor.FENCE).exists()); self.conserved()

    def test_target_mission_above_carried_ceiling_is_refused(self):
        with self.target.tx() as db:
            meta=self.target.get(db,'meta',1); state=missions.state_in(self.target,db)
        spec=copy.deepcopy(state['document']['spec']); spec['authority']['tokenBudget']=100000
        saved=missions.change(self.target,request(revision=state['revision'],spec=spec))['current']
        missions.change(self.target,request('review',saved['revision'],documentHash=saved['documentHash'],confirmed=True))
        with self.assertRaisesRegex(Refusal,'ceiling'): self.prepare()
        self.conserved()

    def test_stopped_writers_backup_and_exact_review_are_mandatory(self):
        p=self.prepare()
        for kwargs in ({},{'writers_stopped':True},{'writers_stopped':True,'backup_root':self.backup_root}):
            with self.assertRaises((Refusal,OSError)):
                api.confirm(self.registry,self.source,p['request'],'0'*64,**kwargs)
        with self.assertRaises(Refusal): api.backup(self.registry,self.source,p['request'],self.backup_root)
        self.assertFalse((self.target.root/successor.FENCE).exists()); self.conserved()

    def test_partial_commit_preserves_both_claims_and_can_never_retry(self):
        p=self.prepare(); api.backup(self.registry,self.source,p['request'],self.backup_root,writers_stopped=True)
        put=Ledger.put
        def failed(db,table,key,value):
            if table=='meta' and value.get('schemaVersion')==7: raise OSError('Synthetic commit interruption')
            return put(db,table,key,value)
        with patch.object(Ledger,'put',failed):
            with self.assertRaises(OSError): api.confirm(self.registry,self.source,p['request'],p['reviewHash'],writers_stopped=True,backup_root=self.backup_root)
        self.assertTrue((self.target.root/successor.FENCE).exists())
        self.assertTrue(successor.source_claim(self.registry.root,self.source.workspace_id).exists())
        with self.assertRaises(Refusal): api.confirm(self.registry,self.source,p['request'],p['reviewHash'],writers_stopped=True,backup_root=self.backup_root)
        with self.assertRaises(Refusal):
            with self.target.tx(): pass
        self.conserved()

    def test_failure_between_claims_cannot_retarget_or_retry_source(self):
        p=self.prepare(); api.backup(self.registry,self.source,p['request'],self.backup_root,writers_stopped=True)
        write=api.exclusive
        def interrupted(path,value):
            if path==self.target.root/successor.FENCE: raise OSError('Synthetic interruption before target marker')
            return write(path,value)
        with patch.object(api,'exclusive',interrupted):
            with self.assertRaises(OSError): api.confirm(self.registry,self.source,p['request'],p['reviewHash'],
                writers_stopped=True,backup_root=self.backup_root)
        self.assertTrue(successor.source_claim(self.registry.root,self.source.workspace_id).exists())
        self.assertFalse((self.target.root/successor.FENCE).exists())
        with self.assertRaisesRegex(Refusal,'already claimed'): self.prepare()
        with self.assertRaises(Refusal): api.confirm(self.registry,self.source,p['request'],p['reviewHash'],
            writers_stopped=True,backup_root=self.backup_root)
        self.conserved()

    def test_deleted_marker_or_foreign_binding_cannot_downgrade_admitted_target(self):
        self.confirm(); marker=self.target.root/successor.FENCE
        marker.unlink()  # Disposable corruption only.
        self.assertFalse(standard.read(self.target)['available'])
        with self.assertRaises(Refusal):
            with self.target.tx(): pass
        self.conserved()

    def test_usage_source_growth_after_admission_fences_fresh_play(self):
        self.confirm()
        with self.u.f.target.open('a') as stream: stream.write(canonical(fixtures.token(self.u.f.f.now+1,600,100))+'\n')
        self.assertFalse(standard.read(self.target)['available'])
        with self.assertRaises(Refusal): self.play()
        self.conserved()

    def test_no_new_read_or_timer_reconfirmation_for_immutable_completed_accounting(self):
        p=self.prepare(); self.u.f.f.now+=10000
        calls=list(self.u.f.calls); self.confirm(p)
        self.assertEqual(calls,self.u.f.calls); self.assertTrue(standard.read(self.target)['available']); self.conserved()

    def test_changed_target_invalidates_review_before_any_claim(self):
        p=self.prepare()
        with self.target.tx() as db:
            meta=self.target.get(db,'meta',1); meta['revision']+=1; self.target.put(db,'meta',1,meta)
        with self.assertRaises(Refusal): api.backup(self.registry,self.source,p['request'],self.backup_root,writers_stopped=True)
        self.assertFalse((self.target.root/successor.FENCE).exists()); self.conserved()

    def test_unlisted_backup_contents_never_admit(self):
        p=self.prepare(); api.backup(self.registry,self.source,p['request'],self.backup_root,writers_stopped=True)
        (self.backup_root/'unlisted').write_bytes(b'not a reviewed backup')
        with self.assertRaisesRegex(Refusal,'Unlisted'): api.confirm(self.registry,self.source,p['request'],p['reviewHash'],
            writers_stopped=True,backup_root=self.backup_root)
        self.assertFalse((self.target.root/successor.FENCE).exists()); self.conserved()

    def test_changed_registered_database_after_backup_refuses_before_claim(self):
        p=self.prepare(); api.backup(self.registry,self.source,p['request'],self.backup_root,writers_stopped=True)
        with self.target.tx() as db:
            meta=self.target.get(db,'meta',1); meta['revision']+=1; self.target.put(db,'meta',1,meta)
        with self.assertRaises(Refusal): api.confirm(self.registry,self.source,p['request'],p['reviewHash'],
            writers_stopped=True,backup_root=self.backup_root)
        self.assertFalse((self.target.root/successor.FENCE).exists()); self.conserved()

    def sending(self):
        self.confirm(); command=self.play()
        with self.target.tx() as db:
            command=self.target.get(db,'commands',command['id'])
            command['notification']={'status':'sending','brainId':self.brain,'hostRunId':command['payload']['runId'],
                'hostBindingHash':digest(self.binding_data),'successorHash':command['payload']['successorHash'],
                'attemptedAt':time.time(),'hostInspectionTransport':'owned_observer_v1'}
            self.target.put(db,'commands',command['id'],command)
        return command

    def test_target_loaded_only_transport_refuses_unknown_then_starts_exactly_once(self):
        command=self.sending(); host=AppServerWake(self.binding_data,self.target)
        for options in ({'loaded':False},{'terminals':[{'itemId':'not-known-empty','processId':'handle'}]}):
            native=target_fixtures.SuccessorTest.fake(self,**options)
            with self.assertRaises(Refusal): successor.loaded_profile(host,native,command['id'],self.brain)
            self.assertNotIn('thread/resume',native.calls); self.assertNotIn('turn/start',native.calls)
        native=target_fixtures.SuccessorTest.fake(self)
        with patch.object(host,'configured',return_value=True),patch('orchestrator.app_server_wake.validate_endpoint'),\
             patch('orchestrator.app_server_wake.WakeProxy',return_value=native),\
             patch('orchestrator.app_server_wake.threading.Thread',target_fixtures.FakeThread):
            result=host.send(self.brain,'Fixture fixed pointer',command['id'])
        self.assertEqual(result['status'],'accepted',result)
        self.assertEqual(native.calls.count('turn/start'),1); self.assertNotIn('thread/resume',native.calls); self.conserved()

    def test_pause_race_stops_loaded_only_preflight_without_load_or_turn(self):
        command=self.sending(); host=AppServerWake(self.binding_data,self.target); fired=False
        def pause(method):
            nonlocal fired
            if method=='thread/effectivePolicy/read' and not fired:
                fired=True
                with self.target.tx() as db:
                    meta=self.target.get(db,'meta',1); meta['standardRun']['status']='stopping'
                    self.target.put(db,'meta',1,meta)
        native=target_fixtures.SuccessorTest.fake(self,callback=pause)
        with self.assertRaisesRegex(Refusal,'Pause or successor state changed'):
            successor.loaded_profile(host,native,command['id'],self.brain)
        self.assertNotIn('thread/resume',native.calls); self.assertNotIn('turn/start',native.calls); self.conserved()

    def test_late_foreign_owner_blocks_native_send_without_blocking_local_pause(self):
        command=self.sending(); host=AppServerWake(self.binding_data,self.target)
        with self.foreign.tx() as db:
            meta=self.foreign.get(db,'meta',1); meta['runner']={'owner':'foreign-fixture'}
            self.foreign.put(db,'meta',1,meta)
        native=target_fixtures.SuccessorTest.fake(self)
        with self.assertRaisesRegex(Refusal,'must not share'): successor.loaded_profile(host,native,command['id'],self.brain)
        self.assertEqual(native.calls,[])
        p=self.controls.preview(self.target,{'operation':'pause','contextHash':standard.read(self.target)['contextHash'],
            'brainAllowance':100,'durationHours':24},'owner')
        self.controls.confirm(self.registry,self.target,{**p,'confirmed':True},'owner')
        self.assertEqual(standard.read(self.target)['run']['status'],'stopping'); self.conserved()

    def test_incomplete_foreign_canceled_hold_is_unknown_even_with_disjoint_current_metadata(self):
        from orchestrator import canceled_play
        # Deliberate disposable corruption, not an ordinary ledger operation.
        with contextlib.closing(sqlite3.connect(self.foreign.db)) as db, db:
            db.row_factory=sqlite3.Row
            row=self.foreign.get(db,'repos','a'); row['path']=str(self.source.root.parent)
            self.foreign.put(db,'repos','a',row)
            db.execute('INSERT INTO snapshots(id,kind,data) VALUES(?,?,?)',('unknown-canceled',canceled_play.KIND,'{}'))
        with self.assertRaisesRegex(Refusal,'claim is missing'): self.prepare()
        self.assertFalse((self.target.root/successor.FENCE).exists()); self.conserved()

    def test_uncommitted_foreign_successor_marker_holds_scope_without_workers_or_run(self):
        marker=self.foreign.root/successor.FENCE
        raw=canonical({'kind':successor.KIND,'recordHash':'0'*64,'reviewHash':'1'*64})
        marker.write_text(raw); marker.chmod(0o600)
        with self.assertRaisesRegex(Refusal,'must not share'): self.prepare()
        self.assertEqual(marker.read_text(),raw)
        self.assertFalse((self.target.root/successor.FENCE).exists()); self.conserved()

    def test_partial_hold_cannot_be_released_by_changed_current_repository_metadata(self):
        from orchestrator import partial_admission
        with standard.read_db(self.foreign.db) as db:
            scopes=successor.repositories(self.foreign.all(db,'repos')); meta=self.foreign.get(db,'meta',1)
        old={'target':{'workspaceId':self.foreign.workspace_id,'root':str(self.foreign.root),
            'brainId':meta['brainId'],'repositories':scopes}}
        marker=self.foreign.root/partial_admission.FENCE
        marker.write_text(canonical({'kind':partial_admission.KIND,'request':old,'reviewHash':digest(old),
            'recordedAt':time.time(),'outcome':partial_admission.OUTCOME})); marker.chmod(0o600)
        with contextlib.closing(sqlite3.connect(self.foreign.db)) as db, db:
            db.row_factory=sqlite3.Row
            row=self.foreign.get(db,'repos','a'); row['path']=str(self.source.root.parent)
            self.foreign.put(db,'repos','a',row)
        with self.assertRaisesRegex(Refusal,'partial repository holds changed'): self.prepare()
        self.assertFalse((self.target.root/successor.FENCE).exists()); self.conserved()


if __name__=='__main__': unittest.main()
