import copy
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator.core import Ledger, Refusal, canonical
from orchestrator.workspaces import Registry
from orchestrator.missions import change
from orchestrator.standard import Controls, brain, read
from test_missions import specification, request


class StandardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root/'repo'; self.repo.mkdir()
        subprocess.run(['git','init','-q',str(self.repo)], check=True)
        self.registry = Registry(self.root/'platform', create=True)
        self.ledger, self.token = self.workspace('alpha')
        self.controls = Controls()

    def tearDown(self):
        self.tmp.cleanup()

    def workspace(self, wid):
        ledger = Ledger(self.root/wid)
        ledger.initialize({'schemaVersion':1, 'brainId':str(uuid.uuid4()), 'repositories':[
            {'id':'a','path':str(self.repo),'projectId':'projectless','ref':'HEAD','policyProfile':'standard','mergePolicy':'manual'}]})
        self.registry.register(wid, wid, ledger.root)
        ledger = self.registry.ledger(wid)
        m = change(ledger, request(spec=specification(mode='phase_delegated')))['current']
        change(ledger, request('review',m['revision'],documentHash=m['documentHash'],confirmed=True))
        token = ledger.acquire(ledger.snapshot()['meta']['brainId']+':test')
        brain(self.registry, ledger, token, {'operation':'catalog','models':[{'model':'fixture','efforts':['low','high']}],'source':'Fixture native catalog'})
        return ledger, token

    def control(self, op='play', ledger=None):
        ledger = ledger or self.ledger
        p = self.controls.preview(ledger, {'operation':op,'contextHash':read(ledger)['contextHash'],'brainAllowance':10000,'durationHours':8}, 'session')
        return self.controls.confirm(self.registry, ledger, {**p,'confirmed':True}, 'session')

    def call(self, operation, ledger=None, token=None, **values):
        ledger = ledger or self.ledger
        return brain(self.registry, ledger, token or self.token, {'operation':operation,'runId':read(ledger)['run']['id'],**values})

    def claim(self, ident='task-1', **overrides):
        return self.call('claim', id=ident,repository='a',title='Implement fixture',paths=['tests/test_fixture.py'],
                         instructions='Implement only the fixture. No network.',acceptance=['Offline unit test passes'],
                         model='fixture',effort='low',rationale='Small bounded task',allowance=10000,**overrides)

    def activate(self):
        self.control(); self.call('receive'); self.claim(); self.call('issue',taskId='task-1')
        self.call('bind',taskId='task-1',threadId=str(uuid.uuid4()),clientThreadId=None,hostId='local')

    def observe(self, **changes):
        data={'taskId':'task-1','nativeStatus':'completed','observedTokens':None,'trackedTerminals':'none','observedAt':time.time(),'source':'Native fixture observation'}
        self.call('observe',**{**data,**changes})

    def finish(self, outcome='completed'):
        return self.call('finish',taskId='task-1',outcome=outcome,evidence={'source':'Commit checked','tests':'Local tests passed','artifacts':[], 'preservation':'Retained local checkout and native task','summary':'Independent verification'})

    def test_owner_preview_bound_to_session_content_and_stale_state(self):
        p=self.controls.preview(self.ledger,{'operation':'play','contextHash':read(self.ledger)['contextHash'],'brainAllowance':10000,'durationHours':8},'session')
        with self.assertRaises(Refusal): self.controls.confirm(self.registry,self.ledger,{**p,'confirmed':True},'other')
        bad=copy.deepcopy(p);bad['preview']['brainAllowance']=1
        with self.assertRaises(Refusal): self.controls.confirm(self.registry,self.ledger,{**bad,'confirmed':True},'session')
        result=self.controls.confirm(self.registry,self.ledger,{**p,'confirmed':True},'session')
        self.assertEqual(result,self.controls.confirm(self.registry,self.ledger,{**p,'confirmed':True},'session'))
        self.assertTrue(self.ledger.snapshot()['meta']['paused'])

    def test_workspace_conversation_receive_and_pause_boundary(self):
        from test_conversation import envelope
        from orchestrator.conversation import read as messages, reply
        self.control()
        cmd = self.ledger.submit(envelope(self.ledger, brainId=self.ledger.snapshot()['meta']['brainId']))
        self.call('receive')
        self.assertIsNotNone(messages(self.ledger)['messages'][0]['receivedAt'])
        reply(self.ledger,self.token,cmd['id'],{'message':'Scoped answer','artifactIds':[],'decisionIds':[]})
        self.control('pause')
        self.ledger.submit(envelope(self.ledger, brainId=self.ledger.snapshot()['meta']['brainId']))
        self.call('receive')
        self.assertIsNone(messages(self.ledger)['messages'][-1]['receivedAt'])
        self.assertEqual(self.ledger.snapshot()['meta']['schemaVersion'],4)

    def test_decision_answers_use_standard_receipt_and_never_resume_pause(self):
        from orchestrator.decisions import publish, resolve
        from orchestrator.observations import capture
        from orchestrator.notification import BrainNotifier
        from test_decisions import envelope
        self.control()
        with self.ledger.tx() as db:
            artifact=capture(db,'design',b'Bounded input evidence',{'repository':'a','name':'design.md','orderAt':time.time(),'references':[]})
        spec={'key':'INPUT','repository':'a','title':'Clarify fixture','question':'Which spelling?',
              'context':'Bounded input','scope':'Existing phase only','nextStep':'Retain answer',
              'options':[{'id':'keep','label':'Keep','implications':'Keep spelling','requiresNote':False},
                         {'id':'revise','label':'Revise','implications':'Request input','requiresNote':True}],
              'recommendedOptionId':None,'artifactIds':[artifact['id']]}
        decision=publish(self.ledger,self.token,spec)
        self.control('pause')
        command=self.ledger.submit(envelope(self.ledger,decision,optionId=None,note='Keep Unicode'),actor='dashboard')
        notifier=BrainNotifier(self.ledger,Path('/Applications/ChatGPT.app/Contents/Resources/codex'))
        with patch('orchestrator.notification.subprocess.run') as send:
            notifier.notify(command['id']);send.assert_not_called()
        self.call('receive')
        self.assertEqual(self.ledger.snapshot()['decisions'][0]['status'],'answered')
        self.call('checkpoint',outcome='paused',summary='Parked awaiting explicit Resume',brainObservedTokens=None)
        self.control('resume')
        from types import SimpleNamespace
        brain_id=self.ledger.snapshot()['meta']['brainId']
        with patch.object(notifier,'status',return_value={'status':'configured'}), patch('orchestrator.notification.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=f'Queued message {uuid.uuid4()} for thread {brain_id}.')) as send:
            notifier.notify(command['id'])
            self.assertIn('standard-cycle.md',send.call_args.args[0][-1])
            self.assertNotIn('Keep Unicode',send.call_args.args[0][-1])
        self.call('receive')
        self.assertEqual(self.ledger.snapshot()['decisions'][0]['status'],'received')
        resolve(self.ledger,self.token,decision['id'],{'commandId':command['id'],'outcome':'applied','summary':'Spelling retained within phase','artifactIds':[artifact['id']]})
        self.assertEqual(next(c for c in self.ledger.snapshot()['commands'] if c['id']==command['id'])['status'],'completed')
        self.assertEqual(read(self.ledger)['run']['tasks'],[])

    def test_complete_cycle_usage_gap_and_immutable_seed(self):
        self.activate(); task=read(self.ledger)['run']['tasks'][0]
        seed=self.ledger.document(task['seedHash'])
        self.assertNotIn('effectIssued',seed['task'])
        self.observe(); self.finish()
        self.call('checkpoint',outcome='completed',summary='Phase complete, owner checkpoint',brainObservedTokens=None)
        state=read(self.ledger)
        self.assertEqual(state['run']['status'],'completed')
        self.assertEqual(state['unmeasuredTasks'],1)
        self.assertEqual(state['chargedAllowance'],20000)
        self.assertEqual(state['run']['brainUsageCoverage'],'not_observed')
        summary=self.registry.summary()
        self.assertEqual(summary['aggregate']['cooperativeTasks'],1)
        self.assertEqual(summary['aggregate']['cooperativeCompletedTasks'],1)
        self.assertEqual(summary['workspaces'][0]['cooperative']['status'],'completed')
        with self.assertRaises(Refusal): self.control()

    def test_pause_blocks_new_effect_and_resume_requires_terminal_checkpoint(self):
        self.control(); self.claim(); self.control('pause')
        with self.assertRaises(Refusal): self.call('issue',taskId='task-1')
        with self.assertRaises(Refusal): self.control('resume')
        self.call('cancel_unissued',taskId='task-1')
        self.call('checkpoint',outcome='paused',summary='No native effect issued',brainObservedTokens=None)
        self.control('resume')
        self.assertEqual(read(self.ledger)['chargedAllowance'],20000)

    def test_issued_unknown_is_never_retried_or_released(self):
        self.control(); self.claim(); self.call('issue',taskId='task-1')
        for op in ('issue','cancel_unissued'):
            with self.assertRaises(Refusal): self.call(op,taskId='task-1')
        with self.assertRaises(Refusal): self.call('checkpoint',outcome='paused',summary='Unknown',brainObservedTokens=None)
        self.assertEqual(read(self.registry.ledger('alpha'))['run']['tasks'][0]['status'],'creating')

    def test_pending_id_is_not_a_confirmed_task(self):
        self.control(); self.claim(); self.call('issue',taskId='task-1')
        self.call('bind',taskId='task-1',threadId=None,clientThreadId=str(uuid.uuid4()),hostId='local')
        with self.assertRaises(Refusal): self.observe()

    def test_fresh_terminal_observation_required(self):
        self.activate()
        with self.assertRaises(Refusal): self.finish()
        self.observe(trackedTerminals='unknown')
        with self.assertRaises(Refusal): self.finish()
        with self.assertRaises(Refusal): self.observe(observedAt=time.time()-400)

    def test_observed_overrun_stops_run_and_no_counter_reset(self):
        self.activate(); self.observe(observedTokens=100000)
        self.assertEqual(read(self.ledger)['run']['status'],'stopping')
        with self.assertRaises(Refusal): self.observe(observedTokens=1)

    def test_cross_workspace_repository_exclusion(self):
        second,token=self.workspace('beta')
        self.control(); self.claim(); self.control(ledger=second)
        with self.assertRaisesRegex(Refusal,'Repository is owned'):
            brain(self.registry,second,token,{'operation':'claim','runId':read(second)['run']['id'], 'id':'b','repository':'a','title':'B','paths':['tests/test_fixture.py'],'instructions':'Fixture','acceptance':['Pass'],'model':'fixture','effort':'low','rationale':'Small','allowance':10000})

    def test_out_of_scope_model_and_path_refused(self):
        self.control()
        base={'operation':'claim','runId':read(self.ledger)['run']['id'],'id':'x','repository':'a','title':'X','paths':['escape.py'],'instructions':'Fixture','acceptance':['Pass'],'model':'fixture','effort':'low','rationale':'Small','allowance':10000}
        with self.assertRaises(Refusal): brain(self.registry,self.ledger,self.token,base)
        with self.assertRaises(Refusal): brain(self.registry,self.ledger,self.token,{**base,'paths':['tests/test_fixture.py'],'model':'foreign'})

    def test_harness_strict_and_enrolled_never_opt_in(self):
        for mutate in ('harness','strict','fence'):
            with self.subTest(mutate=mutate), self.ledger.tx() as db:
                if mutate=='harness':
                    repo=self.ledger.get(db,'repos','a');repo['policyProfile']='harness';self.ledger.put(db,'repos','a',repo)
                else:
                    m=self.ledger.get(db,'meta',1);m['schemaVersion']=3 if mutate=='strict' else 1
                    if mutate=='fence':m['admissionBinding']={}
                    self.ledger.put(db,'meta',1,m)
            self.assertFalse(read(self.ledger)['available'])

    def test_recovery_fences_and_legacy_controls_cannot_resume(self):
        self.control();self.claim()
        owner=self.ledger.snapshot()['meta']['controller']['owner']
        self.ledger.recover(owner,'Fresh native observation: no effect issued in this test')
        self.assertEqual(read(self.ledger)['run']['status'],'stopping')
        with self.assertRaises(Refusal):
            self.ledger.submit({'id':str(uuid.uuid4()),'kind':'resume','payload':{},'expectedRevision':self.ledger.snapshot()['meta']['revision']})

    def test_mission_change_fences_issue_and_keeps_existing_task(self):
        self.control();self.claim()
        m=self.ledger.snapshot()['mission']
        change(self.ledger,request('save',m['revision'],spec=specification(mode='phase_delegated')))
        self.assertTrue(read(self.ledger)['blockers'])
        with self.assertRaises(Refusal):self.call('issue',taskId='task-1')
        self.assertEqual(len(read(self.ledger)['run']['tasks']),1)

    def test_wrong_brain_and_read_no_side_effects(self):
        before=self.ledger.snapshot()
        read(self.ledger);read(self.ledger)
        after=self.ledger.snapshot()
        before.pop('serverTime');after.pop('serverTime')
        self.assertEqual(before,after)
        self.ledger.release(self.token,'Before wrong controller test')
        token=self.ledger.acquire('another-brain')
        with self.assertRaises(Refusal):brain(self.registry,self.ledger,token,{'operation':'catalog','models':[],'source':'x'})

    def test_http_auth_scoped_confirmation_and_one_notification(self):
        from http.client import HTTPConnection
        import threading
        from orchestrator.server import Dashboard
        server=Dashboard(self.ledger,0,self.root/'missing.env',registry=self.registry,
                         notification_cli='/Applications/ChatGPT.app/Contents/Resources/codex')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def http(path,body=None,headers=None):
            conn=HTTPConnection('127.0.0.1',server.server_port)
            conn.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,
                         {'Origin':server.origin,'Content-Type':'application/json',**(headers or {})})
            response=conn.getresponse();result=(response.status,dict(response.getheaders()),json.loads(response.read()));conn.close();return result
        try:
            _,headers,_=http('/api/login',{'token':server.bootstrap})
            auth={'Cookie':headers['Set-Cookie'].split(';')[0]}
            auth['X-CSRF-Token']=http('/api/workspaces/alpha/session',headers=auth)[2]['csrf']
            body={'operation':'play','contextHash':read(self.ledger)['contextHash'],'brainAllowance':10000,'durationHours':8}
            path='/api/workspaces/alpha/standard/'
            self.assertEqual(http(path+'preview',body)[0],403)
            self.assertEqual(http(path+'preview',body,{**auth,'Origin':'https://evil.example'})[0],403)
            status,_,preview=http(path+'preview',body,auth);self.assertEqual(status,200)
            reply={'preview':preview['preview'],'signature':preview['signature'],'confirmed':True}
            brain_id=self.ledger.snapshot()['meta']['brainId']
            from types import SimpleNamespace
            real_run=subprocess.run
            def native_send(argv, **kwargs):
                if argv[0]=='git':return real_run(argv,**kwargs)
                return SimpleNamespace(returncode=0,stdout=f'Queued message {uuid.uuid4()} for thread {brain_id}.')
            with patch('orchestrator.notification.subprocess.run',side_effect=native_send) as send:
                self.assertEqual(http(path+'confirm',reply,auth)[0],200)
                self.assertEqual(http(path+'confirm',reply,auth)[0],200)
                native=[c for c in send.call_args_list if c.args[0][0]!='git']
                self.assertEqual(len(native),1)
                self.assertIn('standard-cycle.md',native[0].args[0][-1])
            state=http('/api/workspaces/alpha/state',headers=auth)[2]
            self.assertEqual(state['standard']['run']['status'],'running')
            self.assertNotIn(self.token,json.dumps(state))
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_unknown_fields_expiry_limits_and_no_not_created_escape(self):
        with self.assertRaises(Refusal): self.controls.preview(self.ledger,{'operation':'play'},'session')
        self.control();self.claim()
        with self.assertRaises(Refusal):self.claim()
        with self.ledger.tx() as db:
            m=self.ledger.get(db,'meta',1);m['standardRun']['expiresAt']=time.time()-1;self.ledger.put(db,'meta',1,m)
        with self.assertRaises(Refusal):self.call('issue',taskId='task-1')
        self.call('cancel_unissued',taskId='task-1')
        self.assertEqual(read(self.ledger)['run']['tasks'][0]['status'],'not_created')

    def test_private_controller_survives_separate_cli_calls_without_disclosure(self):
        from orchestrator.standard import acquire_private, private_token, release_private, controller_file
        self.ledger.release(self.token,'Switch to private persistence')
        owner=self.ledger.snapshot()['meta']['brainId']+':private'
        result=acquire_private(self.ledger,owner)
        token=private_token(self.ledger)
        self.assertNotIn(token,json.dumps(result))
        self.assertEqual(controller_file(self.ledger).stat().st_mode & 0o777,0o600)
        self.assertEqual(private_token(self.registry.ledger('alpha')),token)
        with self.assertRaises(Refusal):acquire_private(self.ledger,owner)
        release_private(self.ledger,'Safe private checkpoint')
        self.assertFalse(controller_file(self.ledger).exists())

    def test_pause_review_survives_progress_but_resume_is_exact(self):
        self.control()
        p=self.controls.preview(self.ledger,{'operation':'pause','contextHash':read(self.ledger)['contextHash'],'brainAllowance':10000,'durationHours':8},'session')
        self.claim()
        self.controls.confirm(self.registry,self.ledger,{**p,'confirmed':True},'session')
        self.assertEqual(read(self.ledger)['run']['status'],'stopping')

    def test_reacquire_for_cleanup_after_mission_revocation(self):
        from orchestrator.standard import acquire_private, release_private
        self.control()
        m=self.ledger.snapshot()['mission']
        change(self.ledger,request('revoke',m['revision'],documentHash=m['documentHash'],confirmed=True))
        self.ledger.release(self.token,'Controller released for fixture recovery')
        acquire_private(self.ledger,self.ledger.snapshot()['meta']['brainId']+':cleanup')
        release_private(self.ledger,'Cleanup controller remains available after revocation')

    def test_scoped_artifacts_need_no_broad_root_and_preserve_versions(self):
        self.activate()
        # Fixture's declared test path is not an artifact format; use an exact
        # task-scoped Markdown path to exercise the byte-retention boundary.
        with self.ledger.tx() as db:
            m=self.ledger.get(db,'meta',1);m['standardRun']['tasks'][0]['paths'].append('RESULT.md');self.ledger.put(db,'meta',1,m)
        path=self.repo/'RESULT.md';path.write_text('Version one')
        self.call('preserve',taskId='task-1',path=str(path),createdAt=None)
        self.call('preserve',taskId='task-1',path=str(path),createdAt=None)
        path.write_text('Version two')
        self.call('preserve',taskId='task-1',path=str(path),createdAt=None)
        state=self.ledger.snapshot()
        self.assertEqual(len(state['observations']['artifacts']),2)
        self.assertEqual(len(read(self.ledger)['run']['tasks'][0]['artifacts']),2)
        foreign=self.root/'foreign.md';foreign.write_text('Not in this task')
        with self.assertRaises(Refusal):self.call('preserve',taskId='task-1',path=str(foreign),createdAt=None)
