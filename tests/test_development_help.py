import copy
import http.client as http_client
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import conversation, missions, standard
from orchestrator.core import Refusal, canonical
from orchestrator.development_help import PREFIX, message, plan
from orchestrator.assistant import context
import test_assistant_journey
from test_missions import request, specification


class DevelopmentHelpTest(unittest.TestCase):
    def setUp(self):
        self.f = test_assistant_journey.AssistantJourneyTest()
        self.f.setUp()
        self.ledger = self.f.ledger

    def tearDown(self):
        self.f.tearDown()

    def test_help_prepares_complete_bounded_prompt_without_mutation(self):
        self.f.pending_creation()
        before = self.f.snapshot()
        self.assertEqual(plan(before)['key'], 'phase_help')
        p = self.f.prepare('phase_help')
        text = p['document']['preview']['message']
        self.assertTrue(text.startswith(PREFIX))
        for required in ('usage/coverage', 'parallel limits', 'scope/authority', 'native readiness',
                         'unresolved identity', 'existing commands', 'do not replace', 'prior consumption',
                         'Do not create a scheduler', 'retain a concise reply'):
            self.assertIn(required.lower(), text.lower())
        self.assertLess(len(text), 8000)
        self.assertEqual(self.f.snapshot()['meta'], before['meta'])
        self.assertEqual(self.f.snapshot()['commands'], before['commands'])
        result, first = self.f.confirm(p)
        self.assertTrue(first)
        self.assertEqual(result['result']['payload']['message'], text)
        self.assertEqual(standard.read(self.ledger)['run'], before['standard']['run'])
        self.assertNotIn(text, canonical(context(self.f.snapshot(), 'roadmap')[0]))

    def test_pending_request_is_followed_and_never_duplicated(self):
        result, _ = self.f.confirm(self.f.prepare('phase_help'))
        value = plan(self.f.snapshot())
        self.assertEqual(value['mode'], 'follow')
        self.assertEqual(value['requestId'], result['id'])
        with self.assertRaises(Refusal): self.f.prepare('phase_help')
        conversation.receive(self.ledger, self.f.fixture.token, result['id'])
        self.assertEqual(plan(self.f.snapshot())['mode'], 'follow')
        with self.ledger.tx() as db:
            c = self.ledger.get(db, 'commands', result['id']); c['status'] = 'completed'
            self.ledger.put(db, 'commands', c['id'], c)
        self.assertEqual(plan(self.f.snapshot())['mode'], 'follow', 'Receipt alone is not a reply')

    def test_reply_reveals_review_then_separate_play_without_auto_approval(self):
        result, _ = self.f.confirm(self.f.prepare('phase_help'))
        conversation.receive(self.ledger, self.f.fixture.token, result['id'])
        spec = specification(mode='phase_delegated'); spec['phase']['id'] = 'next-phase'
        missions.change(self.ledger, request(spec=spec, expectedRevision=missions.read(self.ledger)['revision']))
        conversation.reply(self.ledger, self.f.fixture.token, result['id'], {
            'message':'Checks complete. Draft ready. Review the plan.', 'artifactIds':[], 'decisionIds':[]})
        value = plan(self.f.snapshot())
        self.assertEqual(value['key'], 'phase_review')
        self.assertEqual(value['requestId'], result['id'])
        self.assertEqual(missions.read(self.ledger)['effectiveStatus'], 'draft')
        self.f.confirm(self.f.prepare(value['key']))
        self.assertEqual(plan(self.f.snapshot())['key'], 'phase_play')
        self.assertIsNone(standard.read(self.ledger)['run'])

    def test_missing_readiness_is_prepared_in_same_help_request(self):
        self.f.fixture.remove_catalog()
        self.assertEqual(plan(self.f.snapshot())['key'], 'phase_help')
        self.assertIn('native capability catalog', message(self.f.snapshot()))
        self.assertEqual(self.f.snapshot()['commands'], [])

    def test_help_can_prepare_without_executable_mission_authority(self):
        m = missions.read(self.ledger)
        missions.change(self.ledger, request('revoke', m['revision'], documentHash=m['documentHash'], confirmed=True))
        self.assertEqual(plan(self.f.snapshot())['key'], 'phase_help')
        self.f.confirm(self.f.prepare('phase_help'))
        self.assertIsNone(standard.read(self.ledger)['run'])
        self.assertEqual(missions.read(self.ledger)['effectiveStatus'], 'revoked')

    def test_unresolved_reply_asks_for_short_input_not_repeated_help(self):
        self.f.pending_creation()
        result, _ = self.f.confirm(self.f.prepare('phase_help'))
        conversation.receive(self.ledger, self.f.fixture.token, result['id'])
        conversation.reply(self.ledger, self.f.fixture.token, result['id'], {
            'message':'Need confirmed task link. No retry.', 'artifactIds':[], 'decisionIds':[]})
        s = self.f.snapshot()
        from orchestrator.recovery import describe
        s['recovery'] = describe(s)
        before = copy.deepcopy(s)
        self.assertEqual(plan(s)['mode'], 'needs_input')
        self.assertEqual(s, before)
        followup, _ = self.f.confirm(self.f.prepare('brain_message', 'Follow up the existing guided preparation request '+result['id']+'. Supplied reference.'))
        self.assertEqual(plan(self.f.snapshot())['requestId'], followup['id'])

    def test_previous_phase_reply_is_not_used_as_current_recovery_direction(self):
        self.f.pending_creation()
        result, _ = self.f.confirm(self.f.prepare('phase_help'))
        conversation.receive(self.ledger, self.f.fixture.token, result['id'])
        conversation.reply(self.ledger, self.f.fixture.token, result['id'], {
            'message':'Old run needs evidence.', 'artifactIds':[], 'decisionIds':[]})
        s = self.f.snapshot();s['standard']['run']['id'] = 'another-run'
        self.assertIsNone(plan(s)['requestId'])

    def test_budget_scope_and_identity_stops_do_not_change_limits_or_retry(self):
        self.f.pending_creation()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1)
            meta['standardRun']['usageHighWater'] = 9000000
            meta['standardRun']['expiresAt'] = 1
            self.ledger.put(db, 'meta', 1, meta)
        before = copy.deepcopy(standard.read(self.ledger)['run'])
        p = self.f.prepare('phase_help'); result, _ = self.f.confirm(p)
        self.assertEqual(standard.read(self.ledger)['run'], before)
        self.assertEqual(plan(self.f.snapshot())['requestId'], result['id'])
        replay, first = self.f.confirm(p)
        self.assertFalse(first)
        self.assertEqual(replay['id'], result['id'])

    def test_pause_stop_and_handoff_races_refuse_without_a_saved_request(self):
        for field, value in [('brainControl', {'desired':'stopped'}), ('brainHandoff', {'status':'candidate'})]:
            with self.subTest(field=field):
                p = self.f.prepare('phase_help')
                with self.ledger.tx() as db:
                    meta = self.ledger.get(db, 'meta', 1);meta[field] = value;self.ledger.put(db, 'meta', 1, meta)
                with self.assertRaises(Refusal): self.f.confirm(p)
                self.assertEqual(self.ledger.snapshot()['commands'], [])
                with self.ledger.tx() as db:
                    meta = self.ledger.get(db, 'meta', 1);meta.pop(field);self.ledger.put(db, 'meta', 1, meta)
        self.f.pending_creation()
        p = self.f.prepare('phase_help'); self.f.fixture.control('pause')
        with self.assertRaises(Refusal): self.f.confirm(p)
        self.assertEqual(standard.read(self.ledger)['run']['status'], 'stopping')

    def test_unfinished_native_checkpoint_is_not_another_help_preview(self):
        state = self.f.snapshot()
        state['meta']['brainControl'] = {'desired': 'stopped', 'phase': 'checkpointing',
                                         'protocol': 'workspace_pause_v1'}
        state['workspacePause'] = {'status': 'pausing',
                                   'blockers': [{'code': 'inventory_missing'}]}
        before = copy.deepcopy(state)
        result = plan(state)
        self.assertEqual(result['mode'], 'blocked')
        self.assertIsNone(result['key'])
        self.assertIn('operator capability gap', result['detail'])
        self.assertEqual(state, before)
        state['workspacePause']['blockers'] = [{'code': 'inventory_incomplete'}]
        self.assertEqual(plan(state)['mode'], 'blocked')
        state['workspacePause']['blockers'] = [{'code': 'runner_owned'}]
        self.assertIn('recorded blockers', plan(state)['detail'])

    def test_signature_session_project_expiry_and_strict_boundaries(self):
        p = self.f.prepare('phase_help')
        bad = copy.deepcopy(p);bad['document']['request']['payload']['message'] = 'Play'
        with self.assertRaises(Refusal): self.f.confirm(bad)
        with self.assertRaises(Refusal): self.f.confirm(p, 'another-session')
        with patch('orchestrator.assistant_journey.time.time', return_value=p['document']['expiresAt']+1):
            with self.assertRaises(Refusal): self.f.confirm(p)
        other, _ = self.f.fixture.workspace('beta')
        with self.assertRaises(Refusal):
            self.f.proposals.confirm(other, {'proposal':p,'confirmed':True}, self.f.session)
        s = self.f.snapshot();s['repositories'][0]['policyProfile'] = 'harness'
        self.assertEqual(plan(s)['mode'], 'unavailable')
        self.assertEqual(self.ledger.snapshot()['commands'], [])

    def test_two_tabs_can_only_save_one_preparation(self):
        previews = [self.f.prepare('phase_help'), self.f.prepare('phase_help')]
        def confirm(p):
            try: return self.f.confirm(p)
            except Refusal: return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(confirm, previews))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(len(self.ledger.snapshot()['commands']), 1)

    def test_help_http_read_confirmation_and_reload_progress(self):
        from orchestrator.server import Dashboard, WorkspaceRuntime
        self.f.pending_creation()
        server = Dashboard(self.ledger, 0, registry=self.f.registry, runtime_root=self.f.fixture.root,
                           inference_env=self.f.fixture.root/'absent.env')
        worker = threading.Thread(target=server.serve_forever, daemon=True);worker.start()
        def http(path, body=None, auth=None):
            conn = http_client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            conn.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,
                         {'Content-Type':'application/json','Origin':server.origin,**(auth or {})})
            r=conn.getresponse();result=(r.status,dict(r.getheaders()),json.loads(r.read()));conn.close();return result
        path='/api/workspaces/alpha/assistant/help'
        try:
            self.assertEqual(http(path)[0], 401)
            _, headers, _=http('/api/login', {'token':server.bootstrap})
            auth={'Cookie':headers['Set-Cookie'].split(';')[0]}
            _,_,session=http('/api/workspaces/alpha/session', auth=auth);auth['X-CSRF-Token']=session['csrf']
            before=self.ledger.snapshot()['meta']
            with patch('orchestrator.assistant.Client.request') as inference, patch.object(WorkspaceRuntime,'notify_control',side_effect=lambda c:c) as notify:
                status,_,value=http(path, auth=auth)
                self.assertEqual(status,200,value)
                self.assertEqual(value['mode'],'prepare')
                self.assertEqual(before,self.ledger.snapshot()['meta'])
                self.assertEqual(http(path+'?text=Play',auth=auth)[0],400)
                proposal=value['proposal'];body={'proposal':proposal,'confirmed':True}
                self.assertEqual(http('/api/workspaces/alpha/assistant/confirm',body,{**auth,'X-CSRF-Token':'wrong'})[0],403)
                status,_,saved=http('/api/workspaces/alpha/assistant/confirm',body,auth)
                self.assertEqual(status,200,saved)
                self.assertEqual(notify.call_count,1)
                self.assertEqual(http(path,auth=auth)[2]['requestId'],saved['id'])
                self.assertEqual(http(path,auth=auth)[2]['mode'],'follow')
                self.assertEqual(http('/api/workspaces/alpha/assistant/confirm',body,auth)[0],200)
                self.assertEqual(notify.call_count,1,'Receipt replay must not re-notify')
                inference.assert_not_called()
        finally:
            server.shutdown();server.server_close();worker.join()
