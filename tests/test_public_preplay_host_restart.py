"""Disposable signed-in pre-Play maintenance; no real credentials or native RPC."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator import public_host_lifecycle as launch, public_host_restart as shared
from orchestrator import public_preplay_host_restart as repair, projects, standard, partial_admission
from orchestrator.core import Ledger, Refusal, canonical, digest
from orchestrator.host_lifecycle import write_record
from orchestrator.missions import change
from orchestrator.workspaces import Registry
from test_missions import specification, request
from test_public_host_runtime import package_fixture
from test_public_native_tasks import CONTRACT
from test_native_policy_evidence import CONTRACT as POLICY_CONTRACT


class PreplayRestartTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ppr.',dir='/private/tmp' if Path('/private/tmp').exists() else None)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.root.chmod(0o700)
        self.repo = self.root/'repo'; self.repo.mkdir(mode=0o700)
        subprocess.run(['git','init','-q',str(self.repo)],check=True)
        self.package = self.root/'pkg'; package_fixture(self.package)
        self.home = self.root/'home'; self.home.mkdir(mode=0o700)
        (self.home/'config.toml').write_text(launch.CONFIG); (self.home/'config.toml').chmod(0o600)
        old_ipc = self.root/'old-ipc'; old_ipc.mkdir(mode=0o700)
        self.launch = launch.setup_scope(self.package,self.repo,self.home,old_ipc)
        self.old = self.root/'original'; self.old.mkdir(mode=0o700)
        write_record(self.old/'launch.json',{'spec':self.launch,'manifestHash':digest(self.launch),
            'reviewHash':launch.review_hash(self.launch),'mode':'exec','createdAt':1})
        write_record(self.old/'status.json',{'status':'exec_boundary_issued','profile':launch.PROFILE,'mode':'exec',
            'pid':123456789,'parentPid':2,'observedAt':1,'hostReady':False,'nativeToolsQualified':False,
            'bindingInstalled':False,'terminalSafety':'unknown','restarted':False})
        (self.old/'exec.claim').touch(mode=0o600)
        self.brain, self.project, self.catalog, self.turn = [str(uuid.uuid4()) for _ in range(4)]
        self.registry = Registry(self.root/'platform',create=True)
        original = Ledger(self.repo/'.state')
        original.initialize({'schemaVersion':1,'brainId':self.brain,'repositories':[{'id':'a','path':str(self.repo),
            'projectId':self.catalog,'ref':'HEAD','policyProfile':'standard','mergePolicy':'manual'}]})
        self.registry.register('v3','Disposable V3',original.root); self.ledger = self.registry.ledger('v3')
        mission = change(self.ledger,request(spec=specification(mode='phase_delegated')))['current']
        self.mission = change(self.ledger,request('review',mission['revision'],documentHash=mission['documentHash'],confirmed=True))['current']
        projects.record(self.registry,{'schemaVersion':2,'projects':[{'projectId':self.catalog,'projectKind':'local',
            'label':'Fixture','hostId':'local','path':str(self.repo),'isGitRepository':True}]},time.time())
        projects.bind(self.registry,'v3','local',self.catalog,projects.catalog(self.registry)['hash'])
        self.binding = {'endpoint':{'executable':str(self.package/'bin/codex'),'sha256':self.launch['runtimePackage']['executableHash'],
            'socket':str(old_ipc/'stale.sock'),'serverIdentityHash':'f'*64,
            'socketIdentity':{'device':1,'inode':2,'owner':os.getuid(),'mode':0o600,'changedNs':1}},
            'brains':{self.brain:{'cwd':str(self.repo),'workspaceId':'v3','projectId':self.project,'catalogProjectId':self.catalog,
                'nativePolicy':copy.deepcopy(launch.POLICY),'nativeTaskBackend':copy.deepcopy(CONTRACT),'policyEvidence':copy.deepcopy(POLICY_CONTRACT)}}}
        self.binding_file = self.root/'binding.json'; write_record(self.binding_file,self.binding)
        command = standard.request_catalog_refresh(self.ledger,{'id':str(uuid.uuid4()),'contextHash':standard.read(self.ledger)['contextHash']})
        self.cid = command['id']
        with self.ledger.tx() as db:
            c = self.ledger.get(db,'commands',self.cid)
            c.update(status='failed',catalogError={'code':'native_schema_unavailable','retryable':False})
            c['notification'] = {'status':'accepted','nativeDelivery':'owned_turn_start','brainId':self.brain,
                'nativeTurnId':self.turn,'nativeTurnStatus':'completed',
                'nativeResumeProfile':{'bindingHash':digest(self.binding),'brainId':self.brain,'commandId':self.cid,
                    'nativeTurnId':self.turn,'requested':copy.deepcopy(launch.POLICY),'resumeAcknowledged':True},
                'nativeThreadObservation':{'rootThreadId':self.brain,'nativeTurnId':self.turn,'streamStatus':'closed','complete':False}}
            self.ledger.put(db,'commands',self.cid,c)
        self.auth = self.home/'auth.json'; self.auth.write_bytes(b'DISPOSABLE_SECRET_MUST_NOT_BE_OPENED'); self.auth.chmod(0o600)
        (self.home/'models_cache.json').write_bytes(b'opaque cached model metadata'); (self.home/'models_cache.json').chmod(0o600)
        (self.home/'state_5.sqlite').write_bytes(b'opaque bytes, not a SQLite fixture'); (self.home/'state_5.sqlite').chmod(0o600)
        sessions = self.home/'sessions'; sessions.mkdir(mode=0o700)
        (sessions/('rollout-'+self.brain+'.jsonl')).write_bytes(b'opaque history'); (sessions/('rollout-'+self.brain+'.jsonl')).chmod(0o600)
        self.sockets = self.root/'new-ipc'; self.sockets.mkdir(mode=0o700)
        self.directory = self.root/'repair'; self.path = self.directory/'restart.json'
        patcher = patch.object(shared,'source_tree',return_value='c'*40); patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(shared,'quiescent'); self.quiescent = patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch('socket.socket',side_effect=AssertionError('No native connection during preparation/exec')); patcher.start(); self.addCleanup(patcher.stop)
        self.before = {str(p):partial_admission.database_proof(p) for p in (self.ledger.db,self.registry.db)}
        self.binding_before = shared.pin(self.binding_file)

    def prepare(self):
        report = repair.prepare(self.registry,self.ledger,self.old,self.binding_file,self.sockets,self.directory)
        self.spec = repair.load_spec(self.path); self.hash = report['reviewHash']; return report

    def execute(self, effect=OSError('PRIVATE_EXEC_ERROR')):
        with patch.object(repair.sys,'platform','darwin'),patch.object(repair.platform,'machine',return_value='arm64'),\
             patch.object(repair.os,'chdir'),patch.object(repair.os,'dup2'),patch.object(repair.os,'execve',side_effect=effect) as execute:
            with self.assertRaises((Refusal,KeyboardInterrupt)):
                repair.exec_host(self.registry,self.ledger,self.path,self.hash)
        return execute

    def conserved(self):
        self.assertEqual(self.before,{str(p):partial_admission.database_proof(p) for p in (self.ledger.db,self.registry.db)})
        self.assertEqual(shared.pin(self.binding_file),self.binding_before)

    def mutate_command(self, callback):
        with self.ledger.tx() as db:
            c = self.ledger.get(db,'commands',self.cid); callback(c); self.ledger.put(db,'commands',self.cid,c)

    def test_signed_in_backup_never_opens_hashes_or_copies_credential(self):
        real_open = os.open; real_path_open = Path.open
        def guarded(path,*args,**kwargs):
            self.assertNotEqual(Path(path),self.auth,'Credential bytes must never be opened')
            return real_open(path,*args,**kwargs)
        def path_guard(path,*args,**kwargs):
            self.assertNotEqual(path,self.auth,'Credential bytes must never be opened')
            return real_path_open(path,*args,**kwargs)
        with patch('os.open',side_effect=guarded),patch.object(Path,'open',path_guard): report = self.prepare()
        snapshot = json.loads((self.directory/'home-snapshot.json').read_bytes())
        self.assertNotIn('auth.json',snapshot['files']); self.assertNotIn('sha256',snapshot['credentialMetadata'])
        self.assertEqual(snapshot['credentialMetadata']['bytesRead'],False)
        self.assertFalse((self.directory/'native-home-backup/auth.json').exists())
        self.assertEqual((self.directory/'native-home-backup/models_cache.json').read_bytes(),b'opaque cached model metadata')
        self.assertEqual(report['boundary'],repair.BOUNDARY); self.assertFalse(report['startsHost'])
        self.assertEqual(repair.status(self.path)['status'],'prepared_not_submitted'); self.conserved()

    def test_old_profile_still_refuses_signed_in_home(self):
        with self.assertRaises(Refusal): shared.home_snapshot(self.home,str(self.package/'bin/codex'))
        self.conserved()

    def test_review_has_scope_validity_not_short_timer(self):
        self.prepare()
        with patch.object(repair.time,'time',return_value=999999999999):
            self.assertEqual(repair.preview(self.registry,self.ledger,self.path)['reviewHash'],self.hash)
        self.conserved()

    def test_exact_new_review_and_permanent_claims_before_exec(self):
        self.prepare()
        with patch.object(repair.sys,'platform','darwin'),patch.object(repair.platform,'machine',return_value='arm64'),patch('os.execve') as execute:
            for value in ('wrong',launch.review_hash(self.launch)):
                with self.assertRaises(Refusal): repair.exec_host(self.registry,self.ledger,self.path,value)
            execute.assert_not_called()
        self.assertFalse((self.directory/'attempt').exists())
        execute = self.execute(); self.assertEqual(execute.call_count,1)
        binary = str(self.package/'bin/codex')
        self.assertEqual(execute.call_args.args,(binary,[binary,'app-server','--listen','unix://'+str(self.sockets/'host.sock')],launch.environment(self.launch)))
        self.assertTrue(Path(self.spec['fencePath']).is_file()); self.assertTrue((self.directory/'attempt/exec.claim').is_file())
        self.assertEqual(repair.status(self.path)['status'],'exec_failed')
        self.assertNotIn('PRIVATE_EXEC_ERROR',(self.directory/'attempt/status.json').read_text()); self.conserved()

    def test_another_review_and_touched_original_journal_cannot_retry(self):
        self.prepare(); self.execute(); os.utime(self.old/'status.json',None)
        self.directory = self.root/'another'
        with self.assertRaisesRegex(Refusal,'consumed'): self.prepare()
        self.conserved()

    def test_uncertain_exec_retains_claim_without_fallback(self):
        self.prepare(); self.execute(KeyboardInterrupt())
        self.assertEqual(repair.status(self.path)['status'],'exec_outcome_unknown')
        with self.assertRaises(Refusal): repair.exec_host(self.registry,self.ledger,self.path,self.hash)
        self.conserved()

    def test_credential_metadata_or_backup_drift_refuses(self):
        self.prepare(); os.utime(self.auth,None)
        with self.assertRaises(Refusal): repair.validate(self.registry,self.ledger,self.path)
        self.assertFalse(Path(self.spec['fencePath']).exists()); self.conserved()

    def test_backup_is_complete_private_and_verified(self):
        self.prepare(); (self.directory/'native-home-backup/state_5.sqlite').write_bytes(b'changed')
        with self.assertRaises(Refusal): repair.validate(self.registry,self.ledger,self.path)
        self.conserved()

    def test_pending_unknown_and_permission_requests_refuse(self):
        for update in ({'status':'sending'},{'nativeTurnStatus':'inProgress'},
                       {'nativeThreadObservation':{'streamStatus':'open'}},
                       {'nativeApprovals':[{'status':'pending'}]}):
            with self.subTest(update=update):
                with standard.read_db(self.ledger.db) as db: original = self.ledger.get(db,'commands',self.cid)
                self.mutate_command(lambda c:c['notification'].update(update))
                with self.assertRaises(Refusal): self.prepare()
                with self.ledger.tx() as db: self.ledger.put(db,'commands',self.cid,original)
        self.assertFalse(self.directory.exists())

    def test_missing_receipt_requires_real_retained_disposition(self):
        self.mutate_command(lambda c:c.update(status='queued'))
        with self.assertRaisesRegex(Refusal,'disposition'): self.prepare()
        self.assertFalse(self.directory.exists())

    def test_run_brain_stop_controller_and_binding_changes_refuse(self):
        self.prepare()
        for field,value in (('standardRun',{'status':'paused'}),('controller',{'owner':'new'}),
                            ('brainControl',{'desired':'stopped','phase':'parked'}),('paused',False)):
            with self.ledger.tx() as db:
                meta = self.ledger.get(db,'meta',1); original = copy.deepcopy(meta)
                meta[field] = value; self.ledger.put(db,'meta',1,meta)
            with self.subTest(field=field),self.assertRaises(Refusal): repair.validate(self.registry,self.ledger,self.path)
            with self.ledger.tx() as db: self.ledger.put(db,'meta',1,original)
        self.assertFalse(Path(self.spec['fencePath']).exists())
        self.binding['brains'][self.brain]['projectId'] = str(uuid.uuid4()); self.binding_file.write_text(canonical(self.binding))
        with self.assertRaises(Refusal): repair.validate(self.registry,self.ledger,self.path)

    def test_native_home_aliases_plugins_foreign_history_and_bad_auth_refuse(self):
        for name in ('.env','plugins','other-config.toml'):
            path = self.home/name; path.write_text('never-opened')
            with self.subTest(name=name),self.assertRaises(Refusal): self.prepare()
            path.unlink()
        foreign = self.home/'sessions/foreign.jsonl'; foreign.write_text('foreign')
        with self.assertRaises(Refusal): self.prepare()
        foreign.unlink()
        self.auth.chmod(0o644)
        with self.assertRaises(Refusal): self.prepare()
        self.auth.chmod(0o600)
        link = self.root/'auth-alias'; os.link(self.auth,link)
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists()); self.conserved()

    def test_drift_after_claim_blocks_exec_permanently(self):
        self.prepare(); real = repair.validate
        def validate(*args,**kwargs):
            if kwargs.get('claimed'): os.utime(self.auth,None)
            return real(*args,**kwargs)
        with patch.object(repair,'validate',side_effect=validate): execute = self.execute()
        execute.assert_not_called(); self.assertTrue((self.directory/'attempt/exec.claim').exists())
        self.assertEqual(repair.status(self.path)['status'],'outcome_unknown'); self.conserved()

    def test_new_or_replaced_sidecar_invalidates_review(self):
        self.prepare(); write_record(self.ledger.root/'another-claim.json',{'unresolved':True})
        with self.assertRaises(Refusal): repair.validate(self.registry,self.ledger,self.path)
        self.assertFalse(Path(self.spec['fencePath']).exists()); self.conserved()

    def test_live_old_pid_or_home_handles_fence_before_copy(self):
        self.quiescent.side_effect = Refusal('Previous PID is live, reused or unknown')
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists()); self.conserved()

    def test_cli_routes_are_readonly_and_do_not_construct_writer(self):
        self.prepare()
        with patch('orchestrator.workspaces.Registry',side_effect=AssertionError('No writer construction')):
            registry,ledger = partial_admission.routes(self.registry.root,'v3')
            self.assertEqual(repair.preview(registry,ledger,self.path)['reviewHash'],self.hash)
        self.conserved()

    def test_original_disposed_cancel_and_distinct_failed_request_both_preserved(self):
        from orchestrator import readiness_disposition as disposition
        now = time.time()-10
        with self.ledger.tx() as db:
            c = self.ledger.get(db,'commands',self.cid); c.pop('catalogError'); c['status'] = 'queued'
            n = c['notification']; n['wakeId'] = digest({'commandId':self.cid}); n['nativeTurnStatus'] = 'interrupted'
            n['nativeResumeProfile'].update(version=1,requested=copy.deepcopy(repair.NATIVE_APPROVAL_POLICY))
            n['nativeThreadObservation'].update(version=1,events=[],complete=False,monitoringEndedAt=now)
            n['nativeApprovals'] = [{'turnId':self.turn,'requestHash':'f'*64,'decision':'cancel','status':'resolved',
                'claimedAt':now-3,'observedAt':now-2}]
            n['nativePermissionObservation'] = {'version':1,'turnId':self.turn,'requestHash':'f'*64,
                'reason':'native_resolved','endedAt':now-1}
            self.ledger.put(db,'commands',self.cid,c); original = copy.deepcopy(c)
        p = disposition.prepare(self.registry,self.ledger,self.binding_file,self.cid)
        backup = self.root/'disposition-backup'
        disposition.create_backup(self.registry,self.ledger,p['request'],backup,writers_stopped=True)
        disposition.confirm(self.registry,self.ledger,p['request'],p['reviewHash'],writers_stopped=True,backup_root=backup)
        second = standard.request_catalog_refresh(self.ledger,{'id':str(uuid.uuid4()),'contextHash':standard.read(self.ledger)['contextHash']})
        with self.ledger.tx() as db:
            c = self.ledger.get(db,'commands',second['id']); n = copy.deepcopy(original['notification'])
            n.update(nativeTurnId=str(uuid.uuid4()),nativeTurnStatus='completed',nativeApprovals=[])
            n.pop('nativePermissionObservation'); n['nativeThreadObservation'].update(nativeTurnId=n['nativeTurnId'])
            n['nativeResumeProfile'].update(commandId=c['id'],nativeTurnId=n['nativeTurnId'])
            c.update(status='failed',notification=n,catalogError={'code':'native_schema_unavailable','retryable':False})
            self.ledger.put(db,'commands',c['id'],c)
        self.before = {str(p):partial_admission.database_proof(p) for p in (self.ledger.db,self.registry.db)}
        self.prepare(); self.assertEqual(len(self.spec['scope']['turns']),2)
        with standard.read_db(self.ledger.db) as db: self.assertEqual(self.ledger.get(db,'commands',self.cid),original)
        self.assertEqual(disposition.status(self.ledger)['status'],'disposed_unqualified'); self.conserved()

    def test_foreign_build_policy_or_project_mapping_refuses(self):
        original = copy.deepcopy(self.binding)
        for field,value in (('nativePolicy',{'sandbox':'danger-full-access','approvalPolicy':'never','codeMode':False}),
                            ('nativeTaskBackend',{**CONTRACT,'sourceTree':'d'*40}),('catalogProjectId',str(uuid.uuid4()))):
            self.binding = copy.deepcopy(original); self.binding['brains'][self.brain][field] = value
            self.binding_file.write_text(canonical(self.binding))
            with self.subTest(field=field),self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists())

    def test_historical_status_never_connects_or_revalidates_execution(self):
        self.prepare(); self.execute()
        with patch.object(shared,'source_tree',side_effect=AssertionError('Historical status is not exec validation')),\
             patch.object(shared,'quiescent',side_effect=AssertionError('No live probe on status')):
            row = repair.status(self.path)
        self.assertFalse(row['hostReady']); self.assertEqual(row['boundary'],repair.BOUNDARY); self.conserved()

    def test_socket_identity_paths_and_package_drift_refuse(self):
        self.prepare(); (self.sockets/'unexpected').touch()
        with self.assertRaises(Refusal): repair.validate(self.registry,self.ledger,self.path)
        self.assertFalse(Path(self.spec['fencePath']).exists()); self.conserved()


if __name__ == '__main__': unittest.main()
