"""Existing-home maintenance: conservation, exact review, drift and no replay."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from orchestrator.core import Refusal, digest
from orchestrator import public_host_lifecycle as launch, public_host_restart as restart, standard
from orchestrator.host_lifecycle import write_record
from orchestrator.workspaces import fingerprint
from test_public_host_runtime import package_fixture
import test_public_identity_transfer as transfer_fixtures


class RestartTest(unittest.TestCase):
    def setUp(self):
        self.f = transfer_fixtures.TransferTest(methodName='runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.root, self.registry, self.ledger = self.f.root, self.f.registry, self.f.ledger
        self.package = self.root/'package'; package_fixture(self.package)
        self.f.destination['endpoint'] = {'executable':str(self.package/'bin/codex'),
            'sha256':hashlib.sha256((self.package/'bin/codex').read_bytes()).hexdigest(),
            'socket':str(self.root/'old-native.sock'),'serverIdentityHash':'f'*64,
            'socketIdentity':{'device':1,'inode':2,'owner':os.getuid(),'mode':0o600,'changedNs':1}}
        self.home = self.f.destination_home
        self.old_sockets = self.root/'old-ipc'; self.old_sockets.mkdir(mode=0o700)
        self.old_spec = launch.setup_scope(self.package,Path(self.f.cwd),self.home,self.old_sockets)
        self.old = self.root/'old-launch'; self.old.mkdir(mode=0o700)
        write_record(self.old/'launch.json',{'spec':self.old_spec,'manifestHash':digest(self.old_spec),
            'reviewHash':launch.review_hash(self.old_spec),'mode':'exec','createdAt':1})
        write_record(self.old/'status.json',{'status':'exec_boundary_issued','profile':launch.PROFILE,
            'mode':'exec','pid':123456789,'parentPid':2,'observedAt':1,'hostReady':False,
            'nativeToolsQualified':False,'bindingInstalled':False,'terminalSafety':'unknown','restarted':False})
        (self.old/'exec.claim').write_bytes(b''); (self.old/'exec.claim').chmod(0o600)
        # Persist the fixture's actual historical binding dictionaries. No real
        # socket/native connection is used by the restart path.
        for path,value in ((self.f.fixture.paths[1],self.f.source),(self.f.fixture.paths[0],self.f.destination)):
            path.write_text(json.dumps(value)); path.chmod(0o600)
        self.f.prepare(); self.f.apply()
        (self.home/'state_5.sqlite').write_bytes(b'opaque native database fixture, never SQL opened')
        (self.home/'state_5.sqlite').chmod(0o600)
        (self.home/'installation_id').write_text('same-native-home')
        (self.home/'installation_id').chmod(0o600)
        self.sockets = self.root/'new-ipc'; self.sockets.mkdir(mode=0o700)
        self.directory = self.root/'restart-review'
        self.path = self.directory/'restart.json'
        self.before_calls = copy.deepcopy(self.f.calls)
        for item in (patch.object(restart,'source_tree',return_value='c'*40),patch.object(restart,'quiescent')):
            item.start(); self.addCleanup(item.stop)
        with standard.read_db(self.ledger.db) as db: self.before = fingerprint(db)

    def prepare(self):
        report = restart.prepare(self.registry,self.ledger,self.old,self.f.directory,self.sockets,self.directory)
        self.spec = restart.load_spec(self.path); self.hash = report['reviewHash']
        return report

    def execute(self, effect=OSError('PRIVATE_ERROR')):
        with patch.object(restart.sys,'platform','darwin'),patch.object(restart.platform,'machine',return_value='arm64'),\
             patch.object(restart.os,'chdir'),patch.object(restart.os,'dup2'),\
             patch.object(restart.os,'execve',side_effect=effect) as execute:
            with self.assertRaises((Refusal,KeyboardInterrupt)):
                restart.exec_host(self.registry,self.ledger,self.path,self.hash)
        return execute

    def assert_conserved(self):
        with standard.read_db(self.ledger.db) as db: self.assertEqual(self.before,fingerprint(db))
        self.assertEqual(self.before_calls,self.f.calls,'Restart never reconnects either historical endpoint')

    def test_prepare_preserves_complete_home_and_all_original_records_without_native_call(self):
        before = restart.home_snapshot(self.home,str(self.package/'bin/codex'))
        report = self.prepare()
        self.assertEqual(report['validity'],'until_scope_changes')
        self.assertFalse(report['startsHost'] or report['loadsBrain'] or report['turnStarted'] or report['pilotAccepted'])
        self.assertEqual(report['terminalSafety'],'unknown')
        self.assertEqual(before,restart.home_snapshot(self.home,str(self.package/'bin/codex')))
        restart.backup_check(self.spec,before)
        self.assertFalse(Path(self.spec['fencePath']).exists())
        self.assert_conserved()

    def test_reading_time_never_expires_review_or_renews_original_run(self):
        self.prepare()
        with patch.object(restart.time,'time',return_value=999999999999):
            self.assertEqual(restart.preview(self.registry,self.ledger,self.path)['reviewHash'],self.hash)
        self.assert_conserved()

    def test_old_launch_approval_and_wrong_hash_have_no_claim_or_exec(self):
        self.prepare()
        with patch.object(restart.sys,'platform','darwin'),patch.object(restart.platform,'machine',return_value='arm64'),patch('os.execve') as execute:
            for value in ('wrong',launch.review_hash(self.old_spec)):
                with self.assertRaises(Refusal): restart.exec_host(self.registry,self.ledger,self.path,value)
        execute.assert_not_called(); self.assertFalse((self.directory/'attempt').exists()); self.assert_conserved()

    def test_permanent_fence_and_claim_precede_exact_one_exec_without_native_write(self):
        self.prepare(); execute = self.execute()
        self.assertEqual(execute.call_count,1)
        self.assertTrue(Path(self.spec['fencePath']).exists())
        self.assertTrue((self.directory/'attempt/exec.claim').exists())
        binary = str(self.package/'bin/codex')
        self.assertEqual(execute.call_args.args,(binary,[binary,'app-server','--listen','unix://'+str(self.sockets/'host.sock')],launch.environment(self.old_spec)))
        self.assertEqual(json.loads((self.directory/'attempt/status.json').read_text())['status'],'exec_failed')
        self.assertNotIn('PRIVATE_ERROR',(self.directory/'attempt/status.json').read_text())
        with self.assertRaises(Refusal): restart.preview(self.registry,self.ledger,self.path)
        self.assert_conserved()

    def test_another_review_directory_or_touched_original_journal_cannot_relaunch(self):
        self.prepare(); self.execute()
        os.utime(self.old/'status.json',None)
        self.directory = self.root/'another-review'
        with self.assertRaises(Refusal): self.prepare()
        self.assert_conserved()

    def test_interrupted_exec_consumes_claim_and_preserves_unknown(self):
        self.prepare(); self.execute(KeyboardInterrupt())
        row = json.loads((self.directory/'attempt/status.json').read_text())
        self.assertEqual(row['status'],'exec_outcome_unknown'); self.assertEqual(row['terminalSafety'],'unknown')
        with self.assertRaises(Refusal): restart.exec_host(self.registry,self.ledger,self.path,self.hash)
        self.assert_conserved()

    def test_drift_after_claim_has_no_exec_or_fallback(self):
        self.prepare(); real = restart.validate
        def validate(*args,**kwargs):
            if kwargs.get('claimed'): (self.home/'installation_id').write_text('changed')
            return real(*args,**kwargs)
        with patch.object(restart,'validate',side_effect=validate): execute = self.execute()
        execute.assert_not_called(); self.assertTrue((self.directory/'attempt/exec.claim').exists())
        self.assert_conserved()

    def test_new_usage_controller_stop_or_task_invalidates_review_before_claim(self):
        self.prepare()
        for field,value in (('controller',{'owner':'new'}),('paused',False),('brainControl',{'desired':'stopped','phase':'parked'})):
            with self.ledger.tx() as db:
                meta = self.ledger.get(db,'meta',1); original = copy.deepcopy(meta.get(field)); meta[field] = value
                self.ledger.put(db,'meta',1,meta)
            with self.subTest(field=field),self.assertRaises(Refusal): restart.validate(self.registry,self.ledger,self.path)
            with self.ledger.tx() as db:
                meta = self.ledger.get(db,'meta',1)
                if original is None: meta.pop(field,None)
                else: meta[field] = original
                self.ledger.put(db,'meta',1,meta)
        with self.ledger.tx() as db:
            meta = self.ledger.get(db,'meta',1); meta['standardRun']['brainObservedTokens'] += 1; self.ledger.put(db,'meta',1,meta)
        with self.assertRaises(Refusal): restart.validate(self.registry,self.ledger,self.path)
        self.assertFalse(Path(self.spec['fencePath']).exists())

    def test_home_backup_original_claim_config_and_socket_drift_refuse(self):
        self.prepare()
        targets = [self.home/'installation_id',Path(self.spec['backupPath'])/'installation_id',self.old/'exec.claim',self.home/'config.toml']
        for path in targets:
            raw = path.read_bytes(); path.write_bytes(raw+b'changed')
            with self.subTest(path=path),self.assertRaises(Refusal): restart.validate(self.registry,self.ledger,self.path)
            path.write_bytes(raw)
        # Same-byte restoration does not renew file epochs. It stays refused.
        with self.assertRaises(Refusal): restart.validate(self.registry,self.ledger,self.path)
        self.assert_conserved()

    def test_credential_or_unknown_top_level_entry_refuses_without_opening_it(self):
        for name in ('auth.json','.env','plugins','config.extra.toml'):
            path = self.home/name; path.write_text('PRIVATE_MUST_NOT_READ')
            opened = []; real = restart.read_file
            def capture(path,*args,**kwargs): opened.append(str(path)); return real(path,*args,**kwargs)
            with patch.object(restart,'read_file',side_effect=capture),self.subTest(name=name),self.assertRaises(Refusal):
                self.prepare()
            self.assertNotIn(str(path),opened); path.unlink()
        self.assert_conserved()

    def test_only_exact_arg0_links_are_backed_up_without_following_them(self):
        parent = self.home/'tmp/arg0/native'; parent.mkdir(mode=0o700,parents=True)
        target = parent/'apply_patch'; target.symlink_to(self.package/'bin/codex')
        self.prepare()
        copied = Path(self.spec['backupPath'])/target.relative_to(self.home)
        self.assertTrue(copied.is_symlink()); self.assertEqual(os.readlink(copied),str(self.package/'bin/codex'))
        target.unlink(); target.symlink_to(self.f.source_home/'config.toml')
        with self.assertRaises(Refusal): restart.home_snapshot(self.home,str(self.package/'bin/codex'))

    def test_hardlink_fifo_unsafe_owner_parent_and_bounds_fail_closed(self):
        file = self.home/'installation_id'; alias = self.root/'alias'; os.link(file,alias)
        with self.assertRaises(Refusal): self.prepare()
        alias.unlink()
        native_fifo = self.home/'queue_1.sqlite'; os.mkfifo(native_fifo)
        with self.assertRaises(Refusal): self.prepare()
        native_fifo.unlink()
        with patch.object(restart,'MAX_ENTRIES',2),self.assertRaises(Refusal): self.prepare()
        self.home.chmod(0o755)
        with self.assertRaises(Refusal): self.prepare()
        self.home.chmod(0o700)

    def test_incomplete_transfer_or_changed_native_build_cannot_prepare(self):
        (self.f.directory/'attempt/result.json').unlink()
        with self.assertRaises(OSError): self.prepare()
        self.assertFalse(self.directory.exists())

    def test_original_empty_home_profile_still_refuses_populated_home(self):
        with self.assertRaises(Refusal): launch.validate_spec(self.old_spec)

    def test_later_checkout_config_or_foreign_platform_mapping_refuses(self):
        self.prepare()
        extra = Path(self.f.cwd)/'config.toml'; extra.write_text('unsafe override')
        with self.assertRaises(Refusal): restart.validate(self.registry,self.ledger,self.path)
        extra.unlink()
        with patch.object(restart,'_registered',side_effect=Refusal('changed registration')),self.assertRaises(Refusal):
            restart.validate(self.registry,self.ledger,self.path)
        self.assert_conserved()

    def test_archive_alias_or_socket_inside_home_is_not_an_existing_home_restart(self):
        self.prepare()
        value = copy.deepcopy(self.spec); value['backupPath'] = str(self.home)
        self.path.write_text(json.dumps(value))
        with self.assertRaises(Refusal): restart.preview(self.registry,self.ledger,self.path)
        value = copy.deepcopy(self.spec); value['socketDirectory'] = str(self.home)
        self.path.write_text(json.dumps(value))
        with self.assertRaises(Refusal): restart.preview(self.registry,self.ledger,self.path)
        self.assert_conserved()

    def inspect_fixture(self, *, before_read=None, loaded=False, account=None):
        self.prepare()
        with patch.object(restart.sys,'platform','darwin'),patch.object(restart.platform,'machine',return_value='arm64'),\
             patch.object(restart.os,'chdir'),patch.object(restart.os,'dup2'),\
             patch.object(restart.os,'execve',side_effect=SystemExit('fixture exec handoff')):
            with self.assertRaises(SystemExit): restart.exec_host(self.registry,self.ledger,self.path,self.hash)
        (self.sockets/'host.sock').write_bytes(b'fixture rendezvous; real endpoint inspection mocked')
        endpoint = copy.deepcopy(self.f.destination['endpoint'])
        endpoint['socket'] = str(self.sockets/'host.sock'); endpoint['socketIdentity']['inode'] += 100
        self.inspection_calls = []; outer = self
        class Proxy:
            def __init__(self,*args): pass
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def _rpc(self,method,params):
                outer.inspection_calls.append((method,copy.deepcopy(params)))
                if before_read: before_read(method,params)
                if method == 'project/read': return {'project':copy.deepcopy(outer.f.project)}
                if method == 'thread/read': return {'thread':{'id':outer.f.brain,'cwd':outer.f.cwd,'projectId':outer.f.project_id,
                                                            'status':{'type':'idle' if loaded else 'notLoaded'}}}
                if method == 'thread/turns/list': return {'data':[{'id':'owned-turn-1','status':'completed'}],'nextCursor':None}
                if method == 'mcpServerStatus/list': return {'data':[],'nextCursor':None}
                if method == 'account/read': return {'account':account,'requiresOpenaiAuth':True}
                if method == 'thread/effectivePolicy/read':
                    if loaded:
                        import test_native_policy_evidence as policy
                        return policy.response(outer.f.brain,outer.f.cwd)
                    return {'version':1,'threadId':outer.f.brain,'policy':None}
                raise AssertionError('Mutation/unsupported read: '+method)
        with patch.object(restart,'inspect_endpoint',return_value=endpoint),patch.object(restart,'RestartReadProxy',Proxy),\
             patch.object(restart,'process_absent',return_value=True),patch.object(restart,'live_process'):
            return restart.inspect(self.registry,self.ledger,self.path,self.root/'evidence')

    def test_connectivity_does_not_load_unloaded_brain_or_claim_auth_policy_or_terminal_safety(self):
        report = self.inspect_fixture()
        self.assertEqual(report['status'],'connected_read_only')
        self.assertFalse(report['policyVerified']); self.assertFalse(report['authentication']['ready'])
        self.assertEqual(report['observation']['brainActivity'],'notLoaded')
        self.assertEqual(report['currentTerminalSafety'],report['historicalTerminalSafety'])
        self.assertEqual(report['historicalTerminalSafety'],'unknown')
        self.assertEqual((report['nativeWrites'],report['loads'],report['turns']),(0,0,0))
        self.assertFalse(report['bindingInstalled'] or report['pilotAccepted'] or report['migrationQualified'])
        self.assertTrue(all(method not in {'thread/resume','turn/start','account/login/start','turn/interrupt'} for method,_ in self.inspection_calls))
        self.assert_conserved()

    def test_loaded_policy_and_present_account_still_do_not_authorize_execution(self):
        report = self.inspect_fixture(loaded=True,account={'type':'chatgpt','email':'PRIVATE_EMAIL','planType':'PRIVATE_PLAN'})
        self.assertTrue(report['policyVerified']); self.assertTrue(report['authentication']['ready'])
        self.assertFalse(report['authentication']['modelAccessVerified'] or report['authentication']['executionAuthorized'])
        self.assertNotIn('PRIVATE_',json.dumps(report)); self.assert_conserved()

    def test_metadata_or_usage_race_during_connectivity_leaves_no_success_report(self):
        def change(method,params):
            if method == 'thread/read':
                with self.ledger.tx() as db:
                    meta = self.ledger.get(db,'meta',1); meta['standardRun']['brainObservedTokens'] += 1; self.ledger.put(db,'meta',1,meta)
        with self.assertRaises(Refusal): self.inspect_fixture(before_read=change)
        self.assertFalse((self.root/'evidence').exists())

    def test_changed_history_prefix_is_not_repaired_or_overwritten_during_inspection(self):
        def change(method,params):
            if method == 'project/read': self.f.target.write_bytes(b'changed private fixture history')
        with self.assertRaises(Refusal): self.inspect_fixture(before_read=change)
        self.assertEqual(self.f.target.read_bytes(),b'changed private fixture history')
        self.assertFalse((self.root/'evidence').exists()); self.assert_conserved()

    def test_native_connectivity_rejects_failed_or_unclaimed_attempt(self):
        self.prepare(); self.execute()
        with patch.object(restart,'RestartReadProxy') as proxy,self.assertRaises(Refusal):
            restart.inspect(self.registry,self.ledger,self.path,self.root/'evidence')
        proxy.assert_not_called(); self.assert_conserved()

    def test_persistence_failure_is_consumed_before_any_exec(self):
        self.prepare(); original = restart.write_record
        def write(path,value):
            if path.name == 'status.json': raise OSError('fixture persistence interrupted')
            return original(path,value)
        with patch.object(restart,'write_record',side_effect=write),patch.object(restart.sys,'platform','darwin'),\
             patch.object(restart.platform,'machine',return_value='arm64'),patch('os.execve') as execute:
            with self.assertRaises(OSError): restart.exec_host(self.registry,self.ledger,self.path,self.hash)
        execute.assert_not_called(); self.assertTrue(Path(self.spec['fencePath']).exists())
        with self.assertRaises(Refusal): restart.exec_host(self.registry,self.ledger,self.path,self.hash)
        self.assert_conserved()

    def mark_issued(self):
        with patch.object(restart.sys,'platform','darwin'),patch.object(restart.platform,'machine',return_value='arm64'),\
             patch.object(restart.os,'chdir'),patch.object(restart.os,'dup2'),\
             patch.object(restart.os,'execve',side_effect=SystemExit('fixture handoff')):
            with self.assertRaises(SystemExit): restart.exec_host(self.registry,self.ledger,self.path,self.hash)
        state_path = self.directory/'attempt/status.json'
        state = json.loads(state_path.read_text())
        state['pid'] = 123456788; state['parentPid'] = 2; state['processIdentity'] = '123456788 Thu Oct 15 00:00:00 2026'
        state_path.write_text(json.dumps(state))
        return self.directory/'attempt'

    def test_a_genuinely_ended_restart_gets_its_own_review_without_reusing_predecessor(self):
        self.prepare(); old_hash = self.hash; predecessor = self.mark_issued()
        first_scope = copy.deepcopy(self.spec); self.old = predecessor
        self.directory = self.root/'second-review'; self.path = self.directory/'restart.json'
        self.sockets = self.root/'second-ipc'; self.sockets.mkdir(mode=0o700)
        with patch.object(restart,'process_absent',return_value=True): report = self.prepare()
        self.assertNotEqual(report['reviewHash'],old_hash)
        self.assertNotEqual(self.spec['fencePath'],first_scope['fencePath'])
        self.assertFalse(Path(self.spec['fencePath']).exists())
        self.assertTrue(Path(first_scope['fencePath']).exists())
        self.assertGreater(len(self.spec['previousPins']),len(first_scope['previousPins']))
        self.assert_conserved()

    def test_chain_refuses_live_or_reused_predecessor_and_never_touches_it(self):
        self.prepare(); predecessor = self.mark_issued()
        with patch.object(restart,'process_absent',return_value=False),self.assertRaises(Refusal):
            restart.original_launch(predecessor,self.ledger)
        self.assert_conserved()

    def test_chain_failure_or_tampered_parent_claim_is_not_new_restart_authority(self):
        self.prepare(); predecessor = self.mark_issued()
        state = json.loads((predecessor/'status.json').read_text()); state['status'] = 'exec_outcome_unknown'
        (predecessor/'status.json').write_text(json.dumps(state))
        with patch.object(restart,'process_absent',return_value=True),self.assertRaises(Refusal):
            restart.original_launch(predecessor,self.ledger)
        self.assert_conserved()

    def test_chain_depth_and_cycles_refuse(self):
        self.prepare(); predecessor = self.mark_issued()
        with self.assertRaises(Refusal): restart.original_launch(predecessor,self.ledger,(str(predecessor),))
        with self.assertRaises(Refusal): restart.original_launch(predecessor,self.ledger,tuple(str(n) for n in range(8)))

    def test_process_identity_pins_birth_not_only_matching_argv(self):
        self.prepare()
        state = {'pid':123456788,'processIdentity':'123456788 Thu Oct 15 00:00:00 2026'}
        with patch.object(restart,'process_identity',return_value='123456788 Fri Oct 16 00:00:00 2026'),self.assertRaises(Refusal):
            restart.live_process(self.spec,state)

    def test_saved_exact_project_trust_metadata_is_preserved_not_added_by_restart(self):
        config = self.home/'config.toml'
        config.write_text(launch.CONFIG+'\n[projects.'+json.dumps(self.f.cwd)+']\ntrust_level = "trusted"\n')
        before = config.read_bytes(); report = self.prepare()
        self.assertEqual(report['preservedNativeProjectTrust'],'trusted')
        self.assertEqual(config.read_bytes(),before)
        self.assert_conserved()

    def test_extra_project_or_any_policy_change_remains_unsupported(self):
        config = self.home/'config.toml'
        for value in (launch.CONFIG+'\n[projects."/foreign"]\ntrust_level = "trusted"\n',
                      launch.CONFIG.replace('network_access = false','network_access = true'),
                      launch.CONFIG.replace('code_mode = false','code_mode = 0'),
                      launch.CONFIG+'\nmodel_provider = "foreign"\n'):
            config.write_text(value)
            with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists()); self.assert_conserved()

    def test_status_is_file_only_and_never_promotes_failed_or_unknown_to_safe(self):
        self.prepare(); self.execute(KeyboardInterrupt())
        with patch.object(restart,'fixed') as fixed,patch.object(restart,'source_tree',side_effect=Refusal('changed source')),\
             patch.object(restart,'RestartReadProxy') as proxy:
            report = restart.status(self.path)
        self.assertEqual(report['status'],'exec_outcome_unknown')
        self.assertEqual(report['currentTerminalSafety'],'unknown')
        self.assertFalse(report['hostReady'] or report['pilotAccepted'])
        fixed.assert_not_called(); proxy.assert_not_called(); self.assert_conserved()

    def test_status_after_interrupted_persistence_is_unknown_not_nonexecution(self):
        self.prepare(); (self.directory/'attempt').mkdir(mode=0o700)
        report = restart.status(self.path)
        self.assertEqual(report['status'],'outcome_unknown'); self.assertEqual(report['historicalTerminalSafety'],'unknown')

    def test_foreign_session_is_not_read_or_backed_up(self):
        foreign = self.home/'sessions/rollout-foreign.jsonl'; foreign.write_text('FOREIGN_PRIVATE_HISTORY')
        opened = []; real = restart.read_file
        def capture(path,*args,**kwargs): opened.append(str(path)); return real(path,*args,**kwargs)
        with patch.object(restart,'read_file',side_effect=capture),self.assertRaises(Refusal): self.prepare()
        self.assertNotIn(str(foreign),opened); self.assert_conserved()

    def test_evidence_directory_cannot_overlap_any_protected_or_review_tree(self):
        self.prepare()
        with patch.object(restart,'RestartReadProxy') as proxy:
            for parent in (self.home,self.old,self.f.directory,self.directory,self.package,self.sockets):
                with self.subTest(parent=parent),self.assertRaises(Refusal):
                    restart.inspect(self.registry,self.ledger,self.path,parent/'evidence')
        proxy.assert_not_called(); self.assert_conserved()

    def test_nested_credentials_and_custom_skills_refuse_before_contents_are_read(self):
        parent = self.home/'skills'; parent.mkdir(mode=0o700)
        custom = parent/'custom'; custom.mkdir(mode=0o700); (custom/'SKILL.md').write_text('PRIVATE_UNREVIEWED_SKILL')
        with self.assertRaises(Refusal): self.prepare()
        (custom/'SKILL.md').unlink(); custom.rmdir()
        embedded = parent/'.system'; embedded.mkdir(mode=0o700); secret = embedded/'.env'; secret.write_text('PRIVATE_SECRET')
        opened = []; real = restart.read_file
        def capture(path,*args,**kwargs): opened.append(str(path)); return real(path,*args,**kwargs)
        with patch.object(restart,'read_file',side_effect=capture),self.assertRaises(Refusal): self.prepare()
        self.assertNotIn(str(secret),opened); self.assert_conserved()


class QuiescenceTest(unittest.TestCase):
    def setUp(self):
        self.launch = {'runtimePackage':{'root':'/private/fixture/pkg'},'codexHome':'/private/fixture/home'}
        self.status = {'pid':123456789}

    def query(self,argv):
        if argv[0] == '/bin/ps': return subprocess.CompletedProcess(argv,0,b'12 /Applications/Codex.app/Contents/MacOS/Codex\n',b'')
        return subprocess.CompletedProcess(argv,1,b'',b'')

    def test_only_fixed_process_and_scoped_home_metadata_no_kill(self):
        with patch.object(restart,'process_absent',return_value=True),patch.object(restart,'fixed',side_effect=self.query) as query:
            restart.quiescent(self.launch,self.status)
        self.assertEqual(query.call_args_list[1].args[0],['/usr/sbin/lsof','-nP','-t','+D','/private/fixture/home'])

    def test_live_reused_pid_or_unknown_absence_refuses(self):
        with patch.object(restart,'process_absent',return_value=False),patch.object(restart,'fixed') as query,self.assertRaises(Refusal):
            restart.quiescent(self.launch,self.status)
        query.assert_not_called()

    def test_matching_binary_ambiguous_process_or_open_handle_refuses(self):
        for value in (b'22 /private/fixture/pkg/bin/codex\n',b'22 codex\n',b'malformed\n'):
            with patch.object(restart,'process_absent',return_value=True),patch.object(restart,'fixed',return_value=subprocess.CompletedProcess([],0,value,b'')),self.assertRaises(Refusal):
                restart.quiescent(self.launch,self.status)
        def handles(argv):
            return self.query(argv) if argv[0] == '/bin/ps' else subprocess.CompletedProcess(argv,0,b'456\n',b'')
        with patch.object(restart,'process_absent',return_value=True),patch.object(restart,'fixed',side_effect=handles),self.assertRaises(Refusal):
            restart.quiescent(self.launch,self.status)

    def test_timeout_stderr_and_oversized_metadata_remain_unknown(self):
        for result in (subprocess.CompletedProcess([],1,b'',b'Permission denied'),subprocess.CompletedProcess([],0,b'x'*1_000_001,b'')):
            with patch.object(restart.subprocess,'run',return_value=result),self.assertRaises(Refusal): restart.fixed(['/bin/ps'])
        with patch.object(restart.subprocess,'run',side_effect=subprocess.TimeoutExpired(['/bin/ps'],10)),self.assertRaises(Refusal):
            restart.fixed(['/bin/ps'])

    def test_empty_successful_process_metadata_is_unknown(self):
        with patch.object(restart,'fixed',return_value=subprocess.CompletedProcess([],0,b'',b'')),self.assertRaises(Refusal):
            restart.process_identity(123456789)

    def test_native_read_gate_refuses_load_turn_login_targets_and_refresh(self):
        proxy = restart.RestartReadProxy({},'brain','project')
        with patch.object(restart.ReadProxy,'_rpc') as rpc:
            for method,params in (('thread/resume',{'threadId':'brain'}),('turn/start',{}),('account/login/start',{}),
                                  ('thread/read',{'threadId':'foreign','includeTurns':False}),('account/read',{'refreshToken':True})):
                with self.subTest(method=method),self.assertRaises(Refusal): proxy._rpc(method,params)
        rpc.assert_not_called()


if __name__ == '__main__': unittest.main()
