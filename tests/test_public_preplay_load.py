"""New pre-Play load scope, permanent claims and immutable original requests."""
import copy
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from orchestrator import public_preplay_load as load, public_preplay_host_restart as fresh
from orchestrator import public_host_restart as restart, public_pilot_inspection as inspection, standard
from orchestrator.core import Refusal, digest
from orchestrator.host_lifecycle import write_record
from orchestrator.native_read_client import ReadProxy
import test_public_preplay_host_restart as fixtures
from test_native_policy_evidence import response


class PreplayLoadTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PreplayRestartTest(methodName='runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.root, self.registry, self.ledger = self.f.root,self.f.registry,self.f.ledger
        self.fixture_receipt()
        self.f.prepare()
        self.restart_path = self.f.path; spec = self.f.spec
        attempt = self.f.directory/'attempt'; attempt.mkdir(mode=0o700)
        write_record(attempt/'intent.json',{'kind':fresh.KIND,'specHash':digest(spec),'reviewHash':self.f.hash,'at':1})
        (attempt/'exec.claim').touch(mode=0o600)
        write_record(attempt/'status.json',{'kind':fresh.KIND,'specHash':digest(spec),'status':'exec_boundary_issued',
            'pid':234567890,'parentPid':2,'processIdentity':'234567890 Sat Oct 17 10:36:46 2026','at':1})
        write_record(Path(spec['fencePath']),{'kind':fresh.KIND,'specHash':digest(spec),'reviewDirectory':spec['reviewDirectory']})
        self.alias = self.f.sockets/'host.sock'; self.alias.write_bytes(b'fixture socket'); self.alias.chmod(0o600)
        self.binding = copy.deepcopy(self.f.binding)
        self.binding['endpoint'].update(socket=str(self.alias),socketIdentity={'fixture':'current-socket'})
        self.binding_path = self.root/'current-binding.json'; write_record(self.binding_path,self.binding)
        self.directory = self.root/'load-review'; self.path = self.directory/'load.json'
        self.loaded, self.fail_load, self.policy_wrong, self.auth_missing = False,False,False,False
        self.terminals, self.mcp, self.calls = [],[],[]
        self.thread_override, self.turn_override, self.callback = {},{},None
        outer = self
        def rpc(proxy,method,params):
            outer.calls.append((method,copy.deepcopy(params)))
            if outer.callback: outer.callback(method,params)
            if method == 'project/read': return {'project':{'id':outer.f.project,'roots':[{'path':str(outer.f.repo)}]}}
            if method == 'thread/read': return {'thread':dict({'id':outer.f.brain,'projectId':outer.f.project,
                'cwd':str(outer.f.repo),'status':{'type':'idle' if outer.loaded else 'notLoaded'}},**outer.thread_override)}
            if method == 'thread/turns/list': return {'data':[dict({'id':outer.f.turn,'status':'completed'},**outer.turn_override)],'nextCursor':None}
            if method == 'thread/effectivePolicy/read':
                if not outer.loaded: return {'version':1,'threadId':outer.f.brain,'policy':None}
                value = response(outer.f.brain,str(outer.f.repo))
                if outer.policy_wrong: value['policy']['codeModeOffEnforced'] = False
                return value
            if method == 'mcpServerStatus/list': return {'data':outer.mcp,'nextCursor':None}
            if method == 'account/read': return {'account':None if outer.auth_missing else {'type':'chatgpt'},'requiresOpenaiAuth':True}
            if method == 'thread/backgroundTerminals/list': return {'data':outer.terminals,'nextCursor':None}
            if method == 'thread/resume':
                outer.loaded = True
                if outer.fail_load: raise Refusal('Synthetic lost response PRIVATE_NATIVE_BODY')
                return {'thread':{'id':outer.f.brain,'projectId':outer.f.project,'cwd':str(outer.f.repo),'turns':[]}}
            raise AssertionError('Unexpected method '+method)
        for item in (patch.object(load,'load_binding',return_value=copy.deepcopy(self.binding)),
                     patch.object(load,'inspect_endpoint',return_value=copy.deepcopy(self.binding['endpoint'])),
                     patch.object(restart,'process_absent',return_value=True),patch.object(restart,'live_process'),
                     patch.object(restart,'fixed',return_value=subprocess.CompletedProcess([],0,('n'+str(self.alias)+'\n').encode(),b'')),
                     patch.object(ReadProxy,'__enter__',lambda p:p),patch.object(ReadProxy,'__exit__',lambda *_:None),
                     patch.object(ReadProxy,'_rpc',rpc),patch.object(load.SubscriptionOwner,'hold')):
            item.start(); self.addCleanup(item.stop)
        self.before = {str(p):load.partial.database_proof(p) for p in (self.ledger.db,self.registry.db)}
        self.old_binding = restart.pin(self.f.binding_file); self.current_binding = restart.pin(self.binding_path)

    def fixture_receipt(self):
        # Synthetic original capture, created before the fixture restart review.
        # Never use this construction on a real delivered request.
        from orchestrator.standard_preplay import path, BOUNDARY, TRANSPORT
        with self.ledger.tx() as db:
            command = self.ledger.get(db,'commands',self.f.cid)
            handoff = {'version':1,'transport':TRANSPORT,'brainId':self.f.brain,'workspaceId':'v3',
                'commandId':self.f.cid,'bindingHash':digest(self.f.binding),
                'missionHash':command['payload']['missionHash'],'contextHash':command['payload']['contextHash'],
                'ledgerIdentity':dict(zip(('device','inode'),load.partial.database_proof(self.ledger.db)['identity'])),
                'source':'/synthetic-original-source','sourceHash':'e'*64,'boundary':BOUNDARY}
            command['result'] = 'Synthetic original missing schema receipt'
            request = {'version':1,'handoffHash':digest(handoff),'result':{'operation':'catalog_error',
                'requestId':self.f.cid,'code':'native_schema_unavailable','detail':command['result'],'retryable':False}}
            values = {'handoff':handoff,'request':request,'claim':{'requestHash':digest(request)},
                'reply':{'requestHash':digest(request),'status':'completed','boundary':BOUNDARY}}
            for name,value in values.items(): write_record(path(self.ledger.root,self.f.cid,name),value)
            command['notification']['preplayCatalog'] = {'version':1,'transport':TRANSPORT,'handoffHash':digest(handoff)}
            command['preplayReceipt'] = {'requestHash':digest(request),'handoffHash':digest(handoff),
                'brainId':self.f.brain,'nativeTurnId':self.f.turn,'bindingHash':digest(self.f.binding)}
            self.ledger.put(db,'commands',self.f.cid,command)

    def prepare(self):
        result = load.prepare(self.registry,self.ledger,self.restart_path,self.binding_path,self.directory)
        self.spec = load.load_spec(self.path); self.hash = result['reviewHash']; return result

    def apply(self): return load.apply(self.registry,self.ledger,self.path,self.hash)

    def conserved(self):
        self.assertEqual(self.before,{str(p):load.partial.database_proof(p) for p in (self.ledger.db,self.registry.db)})
        self.assertEqual(self.old_binding,restart.pin(self.f.binding_file))
        self.assertEqual(self.current_binding,restart.pin(self.binding_path))
        self.assertFalse(any(m in {'turn/start','turn/interrupt','thread/start','thread/metadata/update',
                                  'account/login/start','account/logout','model/list'} for m,_ in self.calls))
        self.assertTrue(all(p == {'refreshToken':False} for m,p in self.calls if m == 'account/read'))

    def test_review_is_nonloading_and_has_no_wall_clock_expiry(self):
        result = self.prepare(); self.assertEqual(result['maximumLoads'],1)
        self.assertEqual(result['validity'],'until_scope_changes'); self.assertEqual(result['boundary'],load.BOUNDARY)
        with patch.object(load.time,'time',return_value=999999999999):
            self.assertEqual(load.preview(self.registry,self.ledger,self.path)['reviewHash'],self.hash)
        self.assertFalse(self.loaded); self.assertFalse(any(m == 'thread/resume' for m,_ in self.calls)); self.conserved()

    def test_one_fixed_claimed_load_backup_and_actual_policy_without_turn(self):
        self.prepare(); result = self.apply()
        self.assertEqual(result['loadDelivery'],'acknowledged')
        self.assertEqual(result['observation']['activity'],'idle')
        self.assertEqual(result['observation']['trackedTerminals'],[])
        self.assertTrue(result['observation']['policy']['codeModeOffEnforced'])
        self.assertEqual([p for m,p in self.calls if m == 'thread/resume'],[inspection.load_params(self.spec['provenance'])])
        self.assertTrue((self.directory/'backup/manifest.json').is_file())
        self.assertTrue((self.directory/'attempt/subscription-close.json').is_file())
        self.assertEqual(load.status(self.path)['subscription'],'window_completed'); self.conserved()

    def test_wrong_hash_or_original_launch_approval_does_not_claim(self):
        self.prepare()
        for value in ('yes','a'*64,self.f.hash):
            with self.assertRaises(Refusal): load.apply(self.registry,self.ledger,self.path,value)
        self.assertFalse((self.directory/'attempt').exists()); self.assertFalse((self.directory/'backup').exists())
        self.conserved()

    def test_consumed_claim_blocks_same_or_other_review_directory(self):
        self.prepare(); self.apply()
        with self.assertRaises(Refusal): self.apply()
        with self.assertRaisesRegex(Refusal,'claimed'):
            load.prepare(self.registry,self.ledger,self.restart_path,self.binding_path,self.root/'another')
        self.assertEqual(sum(m == 'thread/resume' for m,_ in self.calls),1); self.conserved()

    def test_unknown_load_never_replays_or_invents_an_ack_on_reconcile(self):
        self.prepare(); self.fail_load = True
        with self.assertRaises(Refusal): self.apply()
        self.fail_load = False
        result = load.reconcile(self.registry,self.ledger,self.path)
        self.assertEqual(result['loadDelivery'],'unknown'); self.assertTrue(result['reconciledReadOnly'])
        self.assertFalse(load.status(self.path)['loadAcknowledged'])
        with self.assertRaises(Refusal): self.apply()
        self.assertEqual(sum(m == 'thread/resume' for m,_ in self.calls),1); self.conserved()

    def test_partial_intent_is_fenced_across_directories_before_load(self):
        self.prepare(); original = load.exclusive
        def interrupt(path,value):
            if Path(path).name == 'intent.json': raise KeyboardInterrupt()
            return original(path,value)
        with patch.object(load,'exclusive',side_effect=interrupt),self.assertRaises(KeyboardInterrupt): self.apply()
        self.assertTrue(Path(self.spec['fencePath']).exists())
        self.assertEqual(load.status(self.path)['status'],'consumed_outcome_not_inferred')
        with self.assertRaises(Refusal): load.prepare(self.registry,self.ledger,self.restart_path,self.binding_path,self.root/'other')
        self.assertFalse(self.loaded); self.conserved()

    def test_already_loaded_active_or_foreign_identity_never_resumes(self):
        for override in ({'status':{'type':'idle'}},{'status':{'type':'active'}},{'projectId':'foreign'},
                         {'cwd':'/foreign'},{'status':{'type':'notLoaded','activeFlags':['waitingOnApproval']}}):
            with self.subTest(override=override):
                self.thread_override = override
                with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(any(m == 'thread/resume' for m,_ in self.calls)); self.conserved()

    def test_loaded_matching_brain_is_not_adopted(self):
        self.loaded = True
        with self.assertRaisesRegex(Refusal,'unloaded'): self.prepare()
        self.assertFalse(self.directory.exists()); self.conserved()

    def test_missing_auth_nonempty_mcp_or_changed_latest_turn_refuses(self):
        self.auth_missing = True
        with self.assertRaises(Refusal): self.prepare()
        self.auth_missing = False; self.mcp = [{'name':'foreign'}]
        with self.assertRaises(Refusal): self.prepare()
        self.mcp = []; self.turn_override = {'id':'foreign'}
        with self.assertRaises(Refusal): self.prepare()
        self.assertFalse(self.directory.exists()); self.conserved()

    def test_source_or_reviewed_scope_drift_refuses_without_load(self):
        self.prepare()
        with patch.object(restart,'source_tree',return_value='d'*40),self.assertRaises(Refusal): self.apply()
        self.f.mutate_command(lambda c:c.update(result='changed'))
        with self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.loaded)

    def test_pid_socket_or_package_drift_refuses(self):
        self.prepare()
        with patch.object(restart,'process_absent',return_value=False),self.assertRaises(Refusal): self.apply()
        with patch.object(load,'inspect_endpoint',return_value={}),self.assertRaises(Refusal): self.apply()
        with patch.object(restart,'live_process',side_effect=Refusal('dead host')),self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.loaded); self.conserved()

    def test_postload_policy_or_tracker_gaps_do_not_qualify(self):
        self.prepare(); self.policy_wrong = True
        with self.assertRaises(Refusal): self.apply()
        self.assertTrue(load.status(self.path)['loadAcknowledged'])
        self.assertEqual(load.status(self.path)['boundary']['currentTerminalSafety'],'unknown')
        self.policy_wrong = False; self.terminals = [{'id':'terminal'}]
        with self.assertRaises(Refusal): load.reconcile(self.registry,self.ledger,self.path)
        self.assertEqual(sum(m == 'thread/resume' for m,_ in self.calls),1); self.conserved()

    def test_unloaded_reconciliation_never_loads(self):
        self.prepare(); self.apply(); self.loaded = False
        with self.assertRaises(Refusal): load.reconcile(self.registry,self.ledger,self.path)
        self.assertEqual(sum(m == 'thread/resume' for m,_ in self.calls),1); self.conserved()

    def test_original_binding_credential_and_history_are_not_opened_beyond_pins(self):
        original_open = Path.open
        def guarded(path,*args,**kwargs):
            self.assertNotEqual(path,self.f.auth,'Credential bytes must never be opened')
            return original_open(path,*args,**kwargs)
        with patch.object(Path,'open',guarded): self.prepare(); self.apply()
        self.assertFalse(any(p.name == 'auth.json' for p in (self.directory/'backup').rglob('*'))); self.conserved()

    def test_status_is_file_only_even_if_source_host_or_state_changed(self):
        self.prepare(); self.apply()
        with (patch.object(load,'provenance',side_effect=AssertionError('No native/state inspection')),
              patch.object(restart,'source_tree',side_effect=AssertionError('No current source check'))):
            result = load.status(self.path)
        self.assertTrue(result['historical']); self.assertTrue(result['claimRetained']); self.conserved()

    def test_foreground_duration_is_explicit_and_changes_review(self):
        for value in (True,14,301,30.0,None):
            with self.subTest(value=value),self.assertRaises(Refusal):
                load.prepare(self.registry,self.ledger,self.restart_path,self.binding_path,self.directory,subscription_seconds=value)
        self.prepare(); self.spec['subscription']['maximumSeconds'] = 299
        self.assertNotEqual(load.review_hash(self.spec),self.hash); self.conserved()

    def test_proxy_cannot_load_twice_or_send_turns_foreign_targets_or_prompts(self):
        self.prepare(); proxy = inspection.InspectionProxy(self.spec['provenance'])
        for method,params in (('turn/start',{}),('thread/resume',inspection.load_params(self.spec['provenance'])),
                              ('thread/read',{'threadId':'foreign','includeTurns':False}),('account/read',{'refreshToken':True})):
            with self.assertRaises(Refusal): proxy._rpc(method,params)
        proxy.load_permitted = True
        proxy._rpc('thread/resume',inspection.load_params(self.spec['provenance']))
        with self.assertRaises(Refusal): proxy._rpc('thread/resume',inspection.load_params(self.spec['provenance']))
        self.conserved()

    def test_partial_receipt_or_native_permission_cannot_be_substituted(self):
        with standard.read_db(self.ledger.db) as db: original = self.ledger.get(db,'commands',self.f.cid)
        for mutate in (lambda c:c.pop('preplayReceipt'),
                       lambda c:c['notification'].update(nativeApprovals=[{'status':'pending'}]),
                       lambda c:c['preplayReceipt'].update(requestHash='f'*64)):
            value = copy.deepcopy(original); mutate(value)
            with self.ledger.tx() as db: self.ledger.put(db,'commands',self.f.cid,value)
            with self.assertRaises(Refusal): self.prepare()
        with self.ledger.tx() as db: self.ledger.put(db,'commands',self.f.cid,original)
        self.conserved()

    def test_pause_race_at_final_boundary_consumes_without_loading(self):
        self.prepare(); original = load.exclusive
        def race(path,value):
            result = original(path,value)
            if Path(path).name == 'subscription-open.json':
                with self.ledger.tx() as db:
                    meta = self.ledger.get(db,'meta',1); meta['brainControl'] = {'desired':'stopped','phase':'checkpointing'}
                    self.ledger.put(db,'meta',1,meta)
            return result
        with patch.object(load,'exclusive',side_effect=race),self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.loaded); self.assertTrue((self.directory/'attempt/load.claim').exists())
        self.assertEqual(load.status(self.path)['subscription'],'interrupted_or_failed')

    def test_lost_subscription_close_is_unknown_not_an_active_lease(self):
        self.prepare(); self.apply(); (self.directory/'attempt/subscription-close.json').unlink()
        self.assertEqual(load.status(self.path)['subscription'],'unknown_not_reconnectable'); self.conserved()

    def test_incomplete_ack_consumes_proxy_without_second_load(self):
        self.prepare(); scope = self.spec['provenance']
        for thread in ({'id':self.f.brain,'cwd':str(self.f.repo)},
                       {'id':self.f.brain,'projectId':'foreign','cwd':str(self.f.repo)},
                       {'id':self.f.brain,'projectId':self.f.project,'cwd':str(self.f.repo),'turns':[{'secret':'not allowed'}]}):
            proxy = inspection.InspectionProxy(scope); proxy.load_permitted = True
            with patch.object(ReadProxy,'_rpc',return_value={'thread':thread}) as rpc:
                with self.assertRaises(Refusal): load.load_once(proxy,scope)
                with self.assertRaises(Refusal): load.load_once(proxy,scope)
                self.assertEqual(rpc.call_count,1)
        self.conserved()

    def test_native_drift_after_claim_never_reloads_or_starts_work(self):
        self.prepare(); original = load.exclusive
        def race(path,value):
            result = original(path,value)
            if Path(path).name == 'load.claim': self.thread_override = {'status':{'type':'active'}}
            return result
        with patch.object(load,'exclusive',side_effect=race),self.assertRaises(Refusal): self.apply()
        self.assertFalse(self.loaded); self.assertTrue(Path(self.spec['fencePath']).exists()); self.conserved()

    def test_backup_corruption_refuses_before_canonical_or_native_claim(self):
        self.prepare()
        with patch.object(load.partial,'database_proof',wraps=load.partial.database_proof) as proof:
            original = proof.side_effect
            real = proof._mock_wraps
            def changed(path):
                result = real(path)
                if Path(path).parent.name == 'backup': result['fingerprint'] = {'changed':True}
                return result
            proof.side_effect = changed
            with self.assertRaises(Refusal): self.apply()
        self.assertFalse(Path(self.spec['fencePath']).exists()); self.assertFalse(self.loaded); self.conserved()


if __name__ == '__main__': unittest.main()
