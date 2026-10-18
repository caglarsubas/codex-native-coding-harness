"""Subscribe-only native transport, not a continuation authority adapter.

Internal building block for a separately reviewed, prospectively claimed control.
No CLI/browser route, binding modification, turn/start, resume or reconnect exists.
The caller must retain this SAME connection for its separately authorized observer.
"""
import copy
import re
import threading
import time

from .core import digest, require
from .native_policy_evidence import matches, reported, validate_contract as policy_contract

PROTOCOL = 'already_loaded_subscription_v1'
METHOD = 'thread/subscribe'
FIELDS = {'protocol', 'method', 'sourceCommit', 'sourceTree', 'executableSha256'}
BOUNDARY = {'brainReloaded': False, 'turnStarted': False, 'requestReplayed': False,
            'bindingChanged': False, 'usageReset': False, 'executionAuthorized': False,
            'currentTerminalSafety': 'unknown', 'historicalTerminalSafety': 'unknown',
            'pilotAccepted': False}


def validate_contract(contract, binding, brain_id):
    require(isinstance(brain_id,str) and re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',brain_id),
            'Exact confirmed native brain identity required')
    require(isinstance(contract,dict) and set(contract) == FIELDS and
            contract['protocol'] == PROTOCOL and contract['method'] == METHOD and
            all(isinstance(contract[k],str) and re.fullmatch(r'[0-9a-f]{40}',contract[k])
                for k in ('sourceCommit','sourceTree')) and
            isinstance(contract['executableSha256'],str) and re.fullmatch(r'[0-9a-f]{64}',contract['executableSha256']),
            'Exact independently qualified subscribe-only build required')
    require(isinstance(binding,dict) and set(binding) == {'endpoint','brains'} and
            set(binding['brains']) == {brain_id} and
            binding['endpoint']['sha256'] == contract['executableSha256'],
            'No fallback host or inherited subscribe capability')
    policy = policy_contract(binding['brains'][brain_id].get('policyEvidence'))
    require(all(policy[k] == contract[k] for k in ('sourceCommit','sourceTree')),
            'Subscription and policy builds differ; never change an existing binding implicitly')
    return contract


class Subscription:
    """One attempt on an already-open pinned connection, with a claim callback.

    The callback is the caller's durable exact-owner intent, not an approval
    inferred by this transport. No production caller/control is supplied here.
    Every error consumes this object; callers must never reconnect or reissue.
    """
    def __init__(self, proxy, binding, brain_id, contract):
        validate_contract(contract,binding,brain_id)
        require(proxy.endpoint == binding['endpoint'] and proxy.process is not None,
                'Original open reviewed connection required')
        self.proxy = proxy
        self.connection = proxy.process
        self.binding = copy.deepcopy(binding)
        self.brain_id, self.contract = brain_id, copy.deepcopy(contract)
        self.lock, self.attempted, self.ready = threading.Lock(), False, False
        self.context_hash = digest({'binding':binding,'brainId':brain_id,'contract':contract})

    def _sample(self):
        record = self.binding['brains'][self.brain_id]
        project = self.proxy._rpc('project/read',{'projectId':record['projectId']}).get('project')
        require(isinstance(project,dict) and project.get('id') == record['projectId'] and
                project.get('roots') == [{'path':record['cwd']}], 'Exact project metadata required')
        thread = self.proxy.call('thread/read',{'threadId':self.brain_id,'includeTurns':False}).get('thread')
        require(isinstance(thread,dict) and thread.get('id') == self.brain_id and
                thread.get('projectId') == record['projectId'] and thread.get('cwd') == record['cwd'] and
                thread.get('status') == {'type':'idle'}, 'Already-loaded idle brain required; never reload')
        policy = self.proxy._rpc('thread/effectivePolicy/read',{'threadId':self.brain_id})
        require(matches(reported(policy,self.brain_id,record['cwd'])), 'Actual restricted native policy required')
        page = self.proxy.call('thread/backgroundTerminals/list',
                               {'threadId':self.brain_id,'cursor':None,'limit':64})
        require(isinstance(page,dict) and set(page) == {'data','nextCursor'} and
                isinstance(page['data'],list) and page['data'] == [] and page['nextCursor'] is None,
                'Complete closed known-empty current tracker required; unknown is not empty')
        # metadata only: no full history/messages or refreshed usage assertions.
        return {'identity':{'id':thread['id'],'projectId':thread['projectId'],'cwd':thread['cwd'],
                            'status':thread['status']},'policyHash':digest(policy),'trackedTerminals':[]}

    def attach(self, claim):
        with self.lock:
            require(not self.attempted, 'Subscribe-only attempt consumed; no reconnect or retry')
            self.attempted = True  # Before any I/O, even a rejected preflight.
            require(self.proxy.endpoint == self.binding['endpoint'] and self.proxy.process is self.connection,
                    'Pinned original connection changed')
            first, second = self._sample(), self._sample()
            require(first == second, 'Native metadata changed before subscription')
            # Must commit the exact prospective owner's claim BEFORE the RPC.
            permit = claim(self.context_hash)
            require(isinstance(permit,dict) and set(permit) == {'contextHash','subscriptionClaimed'} and
                    permit['contextHash'] == self.context_hash and permit['subscriptionClaimed'] is True and
                    self.proxy.endpoint == self.binding['endpoint'] and self.proxy.process is self.connection,
                    'Exact durable owner-control claim required; transport grants no authority')
            response = self.proxy._rpc(METHOD,{'threadId':self.brain_id})
            require(isinstance(response,dict) and set(response) == {'version','threadId','subscribed','reloaded'} and
                    type(response['version']) is int and response['version'] == 1 and
                    response['threadId'] == self.brain_id and response['subscribed'] is True and
                    response['reloaded'] is False, 'Native subscribe-only acknowledgement is unknown or unsupported')
            third, fourth = self._sample(), self._sample()
            require(first == third == fourth and self.proxy.endpoint == self.binding['endpoint'] and
                    self.proxy.process is self.connection,
                    'Native identity, policy or current tracker changed across subscription')
            self.ready = True
            return {'protocol':PROTOCOL,'brainId':self.brain_id,'contextHash':self.context_hash,
                    'observedAt':time.time(),'responseHash':digest(response),'snapshotHash':digest(fourth),
                    'subscriptionAttached':True,'connectionMustRemainOpen':True,'boundary':dict(BOUNDARY)}
