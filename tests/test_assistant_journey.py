import copy
import http.client
import json
import subprocess
import time
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator import brain_memory, conversation, missions, standard
from orchestrator.assistant import context
from orchestrator.assistant_actions import catalog, resolve_action
from orchestrator.assistant_journey import JourneyProposals
from orchestrator.core import Refusal, canonical
import test_standard
from test_missions import request, specification


class AssistantJourneyTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_standard.StandardTest()
        self.fixture.setUp()
        self.ledger, self.registry = self.fixture.ledger, self.fixture.registry
        self.runtime = SimpleNamespace(ledger=self.ledger, registry=self.registry, standard_controls=standard.Controls())
        self.proposals = JourneyProposals(self.runtime)
        self.session = 'browser-session'
        subprocess.run(['git', '-C', str(self.fixture.repo), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                        'commit', '--allow-empty', '-qm', 'Fixture'], check=True)
        logs = self.fixture.root/'logs'; logs.mkdir()
        (self.ledger.root/'observations.json').write_text(json.dumps({'codexHome':str(logs)}))

    def tearDown(self):
        self.fixture.tearDown()

    def snapshot(self):
        s = self.ledger.snapshot()
        s.update(workspace={'id':'alpha','name':'Alpha'}, standard=standard.read(self.ledger), mission=missions.read(self.ledger))
        return s

    def prepare(self, key, text=None):
        s = self.snapshot()
        actions = catalog(s, {})
        action = resolve_action({'key':key, **({'text':text} if text else {})}, actions, text or key)
        return self.proposals.prepare(action, s, self.session)

    def confirm(self, p, session=None):
        return self.proposals.confirm(self.ledger, {'proposal':p,'confirmed':True}, session or self.session)

    def test_preparation_receipt_and_review_do_not_start_play(self):
        p = self.prepare('phase_prepare')
        self.assertEqual(self.ledger.snapshot()['commands'], [])
        result, first = self.confirm(p)
        self.assertTrue(first)
        c = result['result']
        self.assertEqual(c['kind'], 'reconcile')
        self.assertEqual(c['actor'], 'dashboard')
        self.assertIn('Do not start Play', c['payload']['message'])
        with self.assertRaises(Refusal): self.prepare('phase_prepare')
        conversation.receive(self.ledger, self.fixture.token, c['id'])
        conversation.reply(self.ledger, self.fixture.token, c['id'], {'message':'Draft prepared','artifactIds':[],'decisionIds':[]})
        with patch('orchestrator.assistant_journey.time.time', return_value=p['document']['expiresAt']+1):
            replay, first = self.confirm(p)
        self.assertFalse(first)
        self.assertEqual(replay['result']['conversationReply']['message'], 'Draft prepared')
        m = missions.read(self.ledger)
        missions.change(self.ledger, request(spec=specification(mode='phase_delegated'), expectedRevision=m['revision']))
        review = self.prepare('phase_review')
        self.assertIn('scope', review['document']['preview']['mission']['spec']['phase'])
        r, first = self.confirm(review)
        self.assertFalse(first)
        self.assertEqual(r['result']['current']['effectiveStatus'], 'reviewed')
        self.assertIsNone(standard.read(self.ledger)['run'])
        self.assertFalse(self.confirm(review)[1])

    def test_play_pause_and_resume_use_existing_controls_and_preserve_budget(self):
        p = self.prepare('phase_play')
        self.assertTrue(p['document']['request']['preview']['measureUsage'])
        result, _ = self.confirm(p)
        self.assertEqual(result['result']['kind'], 'standard_play')
        run = standard.read(self.ledger)['run']
        self.assertEqual(run['usageGuardVersion'], 1)
        pause = self.prepare('phase_pause')
        self.confirm(pause)
        self.assertEqual(standard.read(self.ledger)['run']['status'], 'stopping')
        replay, first = self.confirm(p)
        self.assertFalse(first)
        self.assertEqual(replay['result']['id'], result['result']['id'])
        self.assertEqual(standard.read(self.ledger)['run']['status'], 'stopping')
        self.assertEqual(standard.read(self.ledger)['run']['limits'], run['limits'])
        with self.assertRaises(Refusal): self.prepare('phase_resume')
        self.fixture.call('checkpoint', outcome='paused', summary='Safe checkpoint', brainObservedTokens=None)
        with self.assertRaises(Refusal): self.prepare('phase_resume')
        usage = self.prepare('usage_check')
        current = standard.read(self.ledger)['run']
        from test_brain_memory import vector
        report = {'scopeHash':brain_memory.scope(current), 'runId':current['id'], 'collectedAt':time.time(),
                  'through':time.time(), 'records':[], 'tokens':vector(123), 'gaps':[], 'coverage':'observed_local'}
        with patch.object(brain_memory, 'collect', return_value=report) as collect:
            self.confirm(usage)
            with patch('orchestrator.assistant_journey.time.time', return_value=usage['document']['expiresAt']+1):
                self.assertFalse(self.confirm(usage)[1])
            self.assertEqual(collect.call_count, 1)
        resume = self.prepare('phase_resume')
        self.assertEqual(resume['document']['preview']['retainedRun']['expiresAt'], run['expiresAt'])
        self.confirm(resume)
        continued = standard.read(self.ledger)['run']
        self.assertEqual(continued['status'], 'running')
        for key in ('id', 'limits', 'expiresAt', 'brainAllowance', 'usageGuardVersion'):
            self.assertEqual(continued[key], run[key])
        self.assertEqual(continued['usageHighWater'], 123)

    def test_pause_preview_does_not_require_current_mission_and_survives_progress(self):
        self.confirm(self.prepare('phase_play'))
        s = self.snapshot();s['mission'] = {}
        action = resolve_action({'key':'phase_pause'}, catalog(s, {}), 'Pause')
        p = self.proposals.prepare(action, s, self.session)
        self.fixture.call('receive')
        m = missions.read(self.ledger)
        missions.change(self.ledger, request('revoke', m['revision'], documentHash=m['documentHash'], confirmed=True))
        self.confirm(p)
        self.assertEqual(standard.read(self.ledger)['run']['status'], 'stopping')

    def test_malformed_confirmation_refuses_without_effect(self):
        for body in (None, [], ['preview'], {'proposal':[]}, {'proposal':{'document':[]}}):
            with self.assertRaises(Refusal): self.proposals.confirm(self.ledger, body, self.session)
        self.assertIsNone(standard.read(self.ledger)['run'])

    def test_usage_gaps_are_retained_and_never_unlock_resume(self):
        self.confirm(self.prepare('phase_play'))
        self.confirm(self.prepare('phase_pause'))
        self.fixture.call('checkpoint', outcome='paused', summary='Safe checkpoint', brainObservedTokens=None)
        result, first = self.confirm(self.prepare('usage_check'))
        self.assertFalse(first)
        self.assertTrue(result['result']['gaps'])
        self.assertIn('unknown', result['message'])
        self.assertIsNone(standard.read(self.ledger)['measuredUsage']['remainingMeasured'])
        with self.assertRaises(Refusal): self.prepare('phase_resume')

    def test_tamper_cross_session_cross_project_stale_and_expired_refuse(self):
        p = self.prepare('phase_play')
        bad = copy.deepcopy(p);bad['document']['request']['preview']['brainAllowance'] = 1
        with self.assertRaises(Refusal): self.confirm(bad)
        with self.assertRaises(Refusal): self.confirm(p, 'other-browser')
        other, _ = self.fixture.workspace('beta')
        with self.assertRaises(Refusal): self.proposals.confirm(other, {'proposal':p,'confirmed':True}, self.session)
        with patch('orchestrator.assistant_journey.time.time', return_value=p['document']['expiresAt']+1), self.assertRaises(Refusal): self.confirm(p)
        with self.ledger.tx() as db:
            meta = self.ledger.get(db,'meta',1);meta['standardCatalog']['source']='changed';self.ledger.put(db,'meta',1,meta)
        with self.assertRaises(Refusal): self.confirm(p)
        self.assertIsNone(standard.read(self.ledger)['run'])

    def test_instruction_is_exact_and_never_sent_to_inference_context(self):
        text = 'Revise the plan: use 200000 tokens.'
        p = self.prepare('brain_message', text)
        self.confirm(p)
        self.assertEqual(self.ledger.snapshot()['commands'][0]['payload']['message'], text)
        self.assertNotIn(text, canonical(context(self.snapshot(), 'roadmap')[0]))
        with self.assertRaises(Refusal):
            resolve_action({'key':'brain_message','text':'invented'}, catalog(self.snapshot(),{}), 'actual text')

    def test_catalog_and_strict_project_boundaries(self):
        self.fixture.remove_catalog()
        p = self.prepare('codex_check');c,_ = self.confirm(p)
        self.assertEqual(c['result']['kind'], 'standard_catalog_refresh')
        self.assertFalse(self.confirm(p)[1])
        with self.assertRaises(Refusal): self.prepare('codex_check')
        s = self.snapshot();s['repositories'][0]['policyProfile']='harness'
        self.assertNotIn('phase_play', catalog(s,{}))
        self.assertNotIn('phase_review', catalog(s,{}))
        strict_facts = {f['id']:f['data'] for f in context(s,'roadmap')[0]['facts']}
        self.assertNotIn('F42', strict_facts)
        self.assertEqual(strict_facts['F31']['activation'], s['mission']['activation'])
        self.assertFalse(catalog(self.snapshot(),{})['dispatch_resume']['available'])

    def test_blocked_phase_prepares_exact_recovery_request_not_play(self):
        self.confirm(self.prepare('phase_play'))
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, 'meta', 1)
            run = meta['standardRun'];run['status'] = 'blocked'
            run['checkpoint'] = {'at': time.time(), 'summary': 'Usage evidence incomplete'}
            run['usageHighWater'] = 954236
            run['usageReport'] = {'records': [{'role': 'brain'}], 'tokens': {
                'total_tokens': 954236, 'input_tokens': 952942,
                'cached_input_tokens': 778368, 'output_tokens': 1294},
                'coverage': 'gapped', 'gaps': ['invalid_token_record'], 'collectedAt': time.time(), 'through': time.time()}
            run['usageReport']['scopeHash'] = brain_memory.scope(run)
            self.ledger.put(db, 'meta', 1, meta)
        preview = self.prepare('phase_prepare')
        self.assertEqual(preview['document']['preview']['title'], 'Prepare a recovery proposal')
        message = preview['document']['preview']['message']
        self.assertIn('954236 total tokens', message)
        self.assertIn('Do not waive a gap', message)
        self.assertIn('Do not review the mission, start Play', message)
        facts = {f['id']:f['data'] for f in context(self.snapshot(), 'roadmap')[0]['facts']}
        self.assertEqual(facts['F43']['observedTotal'], 954236)
        self.assertEqual(facts['F43']['gapLabels'], ['A Codex token record could not be validated.'])
        self.assertIsNone(facts['F43']['remainingMeasured'])
        self.assertEqual(standard.read(self.ledger)['run']['status'], 'blocked')
        receipt, first = self.confirm(preview)
        self.assertTrue(first)
        self.assertEqual(receipt['result']['payload']['message'], message)
        self.assertEqual(standard.read(self.ledger)['run']['status'], 'blocked')
        conversation.receive(self.ledger, self.fixture.token, receipt['result']['id'])
        conversation.reply(self.ledger, self.fixture.token, receipt['result']['id'],
                           {'message':'Reconciled evidence and prepared a bounded successor.', 'artifactIds':[], 'decisionIds':[]})
        next_spec = specification(mode='phase_delegated')
        next_spec['phase']['id'] = 'phase-two'
        next_spec['authority']['tokenBudget'] = 1200000
        saved = missions.change(self.ledger, request(spec=next_spec, expectedRevision=missions.read(self.ledger)['revision']))
        self.assertEqual(saved['current']['effectiveStatus'], 'draft')
        self.assertEqual(standard.read(self.ledger)['run']['status'], 'blocked')
        review = self.prepare('phase_review')
        self.confirm(review)
        self.assertEqual(standard.read(self.ledger)['run']['status'], 'blocked', 'Review alone never restarts work')
        self.assertEqual(self.prepare('phase_play')['document']['preview']['mission']['spec']['phase']['id'], 'phase-two')

    def test_context_exposes_current_play_not_obsolete_activation_claim(self):
        data, _ = context(self.snapshot(), 'roadmap')
        facts = {f['id']:f['data'] for f in data['facts']}
        self.assertTrue(facts['F42']['playAvailable'])
        self.assertEqual(facts['F31']['activation']['protocol'], 'standard_cooperative_v1')
        self.assertNotIn(str(self.fixture.root), canonical(data))

    def test_http_scoped_preview_confirm_and_receipt_replay(self):
        from orchestrator.server import Dashboard
        server = Dashboard(self.ledger, 0, registry=self.registry, runtime_root=self.fixture.root,
                           inference_env=self.fixture.root/'.env')
        worker = threading.Thread(target=server.serve_forever, daemon=True);worker.start()
        def send_http(path, body=None, auth=None):
            conn = http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            conn.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,
                         {'Content-Type':'application/json','Origin':server.origin,**(auth or {})})
            res=conn.getresponse();value=(res.status,dict(res.getheaders()),json.loads(res.read()));conn.close();return value
        prefix='/api/workspaces/alpha'
        try:
            self.assertEqual(send_http(prefix+'/assistant/preview',{'key':'phase_play'})[0],403)
            _, headers, _ = send_http('/api/login',{'token':server.bootstrap})
            auth={'Cookie':headers['Set-Cookie'].split(';')[0]}
            _, _, session=send_http(prefix+'/session',auth=auth);auth['X-CSRF-Token']=session['csrf']
            self.assertEqual(send_http(prefix+'/assistant/preview',{'key':'phase_play'},{**auth,'X-CSRF-Token':'wrong'})[0],403)
            status,_,p=send_http(prefix+'/assistant/preview',{'key':'phase_play'},auth)
            self.assertEqual(status,200,p)
            self.assertIsNone(standard.read(self.ledger)['run'])
            self.assertEqual(send_http(prefix+'/assistant/preview',{'key':'phase_play','payload':{}},auth)[0],409)
            body={'proposal':p,'confirmed':True}
            self.assertEqual(send_http(prefix+'/assistant/confirm',{**body,'confirmed':False},auth)[0],409)
            status,_,result=send_http(prefix+'/assistant/confirm',body,auth)
            self.assertEqual(status,200,result)
            self.assertEqual(result['result']['kind'],'standard_play')
            status,_,replay=send_http(prefix+'/assistant/confirm',body,auth)
            self.assertEqual(status,200,replay)
            self.assertEqual(replay['result']['id'],result['result']['id'])
            self.assertEqual(len(self.ledger.snapshot()['commands']),1)
        finally:
            server.shutdown();server.server_close();worker.join()
