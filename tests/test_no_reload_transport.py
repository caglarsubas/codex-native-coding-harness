"""Transport-only fixtures; never a live continuation permit or native load."""
import copy
import threading
import unittest

from orchestrator import no_reload_transport as api
from orchestrator.core import Refusal, digest
from test_native_policy_evidence import response as policy_response

BRAIN = '00000000-0000-4000-8000-000000000001'
PROJECT = '00000000-0000-4000-8000-000000000002'
CWD = '/fixture/brain'
CONTRACT = {'protocol':api.PROTOCOL,'method':api.METHOD,'sourceCommit':'a'*40,'sourceTree':'b'*40,
            'executableSha256':'c'*64}
BINDING = {'endpoint':{'sha256':'c'*64},'brains':{BRAIN:{'cwd':CWD,'projectId':PROJECT,
           'policyEvidence':{'protocol':'loaded_thread_policy_v1','sourceCommit':'a'*40,'sourceTree':'b'*40}}}}


class Proxy:
    def __init__(self):
        self.endpoint = copy.deepcopy(BINDING['endpoint']); self.process = object()
        self.calls = []; self.hook = lambda method, params: None
        self.thread = {'id':BRAIN,'projectId':PROJECT,'cwd':CWD,'status':{'type':'idle'}}
        self.policy = policy_response(BRAIN,CWD)
        self.terminals = {'data':[],'nextCursor':None}
        self.reply = {'version':1,'threadId':BRAIN,'subscribed':True,'reloaded':False}

    def _rpc(self, method, params):
        self.calls.append((method,copy.deepcopy(params))); self.hook(method,params)
        if method == 'project/read': return {'project':{'id':PROJECT,'roots':[{'path':CWD}]}}
        if method == 'thread/read': return {'thread':copy.deepcopy(self.thread)}
        if method == 'thread/effectivePolicy/read': return copy.deepcopy(self.policy)
        if method == 'thread/backgroundTerminals/list': return copy.deepcopy(self.terminals)
        if method == api.METHOD: return copy.deepcopy(self.reply)
        raise AssertionError('Forbidden RPC: '+method)
    call = _rpc


class NoReloadTransportTest(unittest.TestCase):
    def setUp(self):
        self.proxy = Proxy(); self.transport = api.Subscription(self.proxy,BINDING,BRAIN,CONTRACT)
        self.claims = []

    def claim(self, context):
        self.assertNotIn(api.METHOD,[m for m,_ in self.proxy.calls])
        self.claims.append(context)
        return {'contextHash':context,'subscriptionClaimed':True}

    def test_same_open_connection_and_claim_precede_one_fixed_subscribe(self):
        value = self.transport.attach(self.claim)
        self.assertEqual(self.claims,[self.transport.context_hash])
        self.assertTrue(value['subscriptionAttached'])
        self.assertEqual(value['boundary'],api.BOUNDARY)
        self.assertFalse(value['boundary']['executionAuthorized'])
        self.assertEqual(value['boundary']['currentTerminalSafety'],'unknown')
        self.assertEqual([x for x in self.proxy.calls if x[0] == api.METHOD],[(api.METHOD,{'threadId':BRAIN})])
        for method in ('thread/resume','thread/start','turn/start','turn/interrupt'):
            self.assertNotIn(method,[m for m,_ in self.proxy.calls])

    def test_retry_is_local_refusal_not_second_rpc(self):
        self.transport.attach(self.claim); before = copy.deepcopy(self.proxy.calls)
        with self.assertRaises(Refusal): self.transport.attach(self.claim)
        self.assertEqual(before,self.proxy.calls)

    def test_unloaded_active_unknown_and_permission_states_never_subscribe(self):
        for status in ({'type':'notLoaded'},{'type':'systemError'},{'type':'active','activeFlags':['waitingOnApproval']},
                       {'type':'idle','activeFlags':[]},None):
            proxy = Proxy(); proxy.thread['status'] = status
            transport = api.Subscription(proxy,BINDING,BRAIN,CONTRACT)
            with self.subTest(status=status), self.assertRaises(Refusal): transport.attach(self.claim)
            self.assertNotIn(api.METHOD,[m for m,_ in proxy.calls])

    def test_unknown_running_and_incomplete_terminal_pages_never_subscribe(self):
        for terminals in ({}, {'data':None,'nextCursor':None},
                          {'data':[],'nextCursor':None,'coverage':'unknown'},
                          {'data':[{'processId':'p','itemId':'i'}],'nextCursor':None},
                          {'data':[],'nextCursor':'loop'}):
            proxy = Proxy(); proxy.terminals = terminals
            transport = api.Subscription(proxy,BINDING,BRAIN,CONTRACT)
            with self.subTest(terminals=terminals), self.assertRaises(Refusal): transport.attach(self.claim)
            self.assertNotIn(api.METHOD,[m for m,_ in proxy.calls])

    def test_actual_policy_not_requested_defaults(self):
        for key,value in (('codeModeOffEnforced',False),('approvalPolicy','never'),('approvalsReviewer','auto_review')):
            proxy = Proxy(); proxy.policy['policy'][key] = value
            with self.subTest(key=key), self.assertRaises(Refusal):
                api.Subscription(proxy,BINDING,BRAIN,CONTRACT).attach(self.claim)
            self.assertNotIn(api.METHOD,[m for m,_ in proxy.calls])

    def test_contract_source_binary_and_unknown_fields_cannot_be_inherited(self):
        for edit in (lambda x:x.update(sourceCommit='d'*40),lambda x:x.update(executableSha256='e'*64),
                     lambda x:x.update(method='thread/resume'),lambda x:x.update(reloadAllowed=False),
                     lambda x:x.update(protocol='config_echo'),lambda x:x.update(sourceTree=True)):
            value = dict(CONTRACT); edit(value)
            with self.assertRaises(Refusal): api.Subscription(self.proxy,BINDING,BRAIN,value)
        self.assertEqual(self.proxy.calls,[])

    def test_exact_brain_project_and_checkout_are_observed(self):
        for key,value in (('id','foreign'),('projectId','foreign'),('cwd','/elsewhere')):
            proxy = Proxy(); proxy.thread[key] = value
            with self.subTest(key=key), self.assertRaises(Refusal):
                api.Subscription(proxy,BINDING,BRAIN,CONTRACT).attach(self.claim)
            self.assertNotIn(api.METHOD,[m for m,_ in proxy.calls])

    def test_missing_claim_never_calls_native_subscription(self):
        for result in (None,{}, {'contextHash':'wrong','subscriptionClaimed':True},
                       {'contextHash':self.transport.context_hash,'subscriptionClaimed':1}):
            proxy = Proxy(); transport = api.Subscription(proxy,BINDING,BRAIN,CONTRACT)
            with self.subTest(result=result), self.assertRaises(Refusal): transport.attach(lambda _:result)
            self.assertNotIn(api.METHOD,[m for m,_ in proxy.calls])

    def test_lost_response_permanently_consumes_attempt(self):
        def lost(method, params):
            if method == api.METHOD: raise OSError('Lost native response')
        self.proxy.hook = lost
        with self.assertRaises(OSError): self.transport.attach(self.claim)
        self.assertFalse(self.transport.ready)
        with self.assertRaises(Refusal): self.transport.attach(self.claim)
        self.assertEqual(len(self.claims),1)

    def test_unload_race_is_not_a_resume_fallback(self):
        def unloaded(method,params):
            if method == api.METHOD: raise Refusal('not loaded')
        self.proxy.hook = unloaded
        with self.assertRaises(Refusal): self.transport.attach(self.claim)
        self.assertNotIn('thread/resume',[m for m,_ in self.proxy.calls])

    def test_ack_is_closed_actual_native_response(self):
        for edit in (lambda r:r.update(version=True),lambda r:r.update(threadId='foreign'),
                     lambda r:r.update(reloaded=True),lambda r:r.update(subscribed=False),
                     lambda r:r.update(extra='opaque')):
            proxy = Proxy(); edit(proxy.reply)
            with self.assertRaises(Refusal): api.Subscription(proxy,BINDING,BRAIN,CONTRACT).attach(self.claim)

    def test_post_subscription_policy_drift_consumes_without_ready(self):
        def drift(method,params):
            if method == api.METHOD: self.proxy.policy['policy']['codeModeOffEnforced'] = False
        self.proxy.hook = drift
        with self.assertRaises(Refusal): self.transport.attach(self.claim)
        self.assertFalse(self.transport.ready)

    def test_connection_replacement_is_not_an_owning_subscription(self):
        self.proxy.process = object()
        with self.assertRaises(Refusal): self.transport.attach(self.claim)
        self.assertEqual(self.proxy.calls,[])

    def test_owner_stop_or_claim_failure_prevents_subscription(self):
        def stopped(_): raise Refusal('Owner Pause or continuation review changed')
        with self.assertRaises(Refusal): self.transport.attach(stopped)
        self.assertFalse(self.transport.ready)
        self.assertNotIn(api.METHOD,[m for m,_ in self.proxy.calls])
        with self.assertRaises(Refusal): self.transport.attach(self.claim)

    def test_endpoint_change_at_claim_boundary_refuses(self):
        def changed(context):
            self.proxy.endpoint = {'sha256':'d'*64}
            return {'contextHash':context,'subscriptionClaimed':True}
        with self.assertRaises(Refusal): self.transport.attach(changed)
        self.assertNotIn(api.METHOD,[m for m,_ in self.proxy.calls])

    def test_parallel_callers_cannot_issue_two_subscriptions(self):
        results = []
        def run():
            try: results.append(self.transport.attach(self.claim))
            except Refusal: results.append('refused')
        workers = [threading.Thread(target=run) for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join()
        self.assertEqual(sum(isinstance(v,dict) for v in results),1)
        self.assertEqual(sum(m == api.METHOD for m,_ in self.proxy.calls),1)

    def test_source_context_is_exact_and_input_binding_not_mutated(self):
        before = copy.deepcopy(BINDING); contract = copy.deepcopy(CONTRACT)
        result = self.transport.attach(self.claim)
        self.assertEqual(BINDING,before); self.assertEqual(CONTRACT,contract)
        self.assertEqual(result['contextHash'],digest({'binding':before,'brainId':BRAIN,'contract':contract}))
