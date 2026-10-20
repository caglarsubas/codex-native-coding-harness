"""Explicit read-only completion evidence for a consumed v5 preparation turn.

Append evidence; never rewrite the original unknown outcome, reconnect its
observer, load/subscribe/start, collect usage, install a binding or grant Play.
"""
import argparse
import copy
import os
from pathlib import Path
import time

from . import host_transfer_handoff as handoff, canceled_continuation as planning
from .core import Refusal, canonical, digest, require
from .native_read_client import ReadProxy
from .standard_quarantine import exclusive

KIND='transferred_preparation_completion_evidence_v1'
PR181_SOURCE='fc52c345ab84a917fe875bd97d12c9bc15c54fcbf5e3bc712583c048647312b3'
PR182_SOURCE='f0c99ec7248045d6c207c8366d8e4d1724b183093f2a601eca5456cc14cc535d'
BOUNDARY={**planning.BOUNDARY,'observerReconnected':False,'subscriptionAttached':False,
    'nativeWrites':False,'usageCollected':False,'postTurnUsage':'unknown_not_collected',
    'oldOutcomeChanged':False,'phaseClockRenewed':False,'repositoryHoldsReleased':False}
REQUIRED_OWNER={'intent.json','restore.claim.json','restore.json','load.claim.json','load.json',
    'assign.claim.json','assign.json','transfer.json','subscription.claim.json','subscription.json',
    'handoff.claim.json','planning-outcome.json'}


def qualified_source(q,root):
    if q['sourceHash']==planning.old.source_hash():
        require(root is None,'Current-source fixture requires no historical-source substitute')
        return None
    require(root is not None and q['sourceHash']==PR181_SOURCE,
        'Historical v5 request requires its exact immutable qualified PR-181 source')
    proof=handoff.phase.lifecycle.source_proof(root)
    require(proof['sourceHash']==PR181_SOURCE,'Only exact qualified PR-181 source bytes are supported')
    return proof  # Read hashes/epochs only; never import historical Python.


def context(registry,ledger,file,source=None,*,live=False,setup_transition=None):
    require(setup_transition is None or live is False, 'Historical registration continuity cannot authorize a native connection')
    q=planning.read_review(file); require(handoff.valid(q),'Only the exact version-5 transfer is supported')
    proof=qualified_source(q,source); old=handoff.status(q); result=planning.status(q)
    require(old['status']=='incomplete_unknown' and old['connectionClosed'] is True and
        result['nativeOutcome']=='unknown' and result['newReceiptRetained'] is True and
        result['proposalRetained'] is True and REQUIRED_OWNER<=set(old['records']),
        'Complete transfer plus original new receipt/proposal and closed lost observer required')
    root=Path(q['journal']); owner=handoff.phase.owner_root(q)
    ack=handoff.read(root/'native-ack.json'); turn=result['nativeTurnId']
    require(isinstance(turn,str) and planning.old.UUID.fullmatch(turn) and ack=={
        'reviewHash':digest(q),'turnId':turn,'ledgerReceipt':False},'Exact original new-turn acknowledgement required')
    failure=handoff.read(root/'failure.json'); life=handoff.read(root/'lifecycle.json')
    require(set(failure) in ({'errorType','detail','reviewHash','retryPermitted'},
        {'errorType','detail','reviewHash','retryPermitted','connectionLossReason'}) and
        failure['errorType']=='NativeConnectionLost' and failure['reviewHash']==digest(q) and
        failure['retryPermitted'] is False and failure['detail']==str(planning.NativeConnectionLost('fixture')) and
        failure.get('connectionLossReason') in (None,'heartbeat_missing','proxy_unavailable','websocket_closed',
            'observer_backpressure','observer_reader_failed') and
        life=={'reviewHash':digest(q),'phase':'observing_new_turn','connectionClosed':False,
            'preflightRefusalRecorded':False,'terminalSafety':'unknown'},
        'Only the closed original transfer observer loss is eligible; no permission/preflight/Stop fallback')
    for path in root.glob('event-*.json'):
        row=handoff.read(path)['row']; params=row.get('params') or {}
        require(not ('id' in row and 'method' in row) and params.get('threadId',q['original']['brainId'])==q['original']['brainId'] and
            params.get('turnId',turn)==turn,'A native permission or foreign event remains fenced')
    for op in ('receive','proposal'):
        saved=handoff.read(root/(op+'.json')); request={'requestHash':digest(q),'operation':op,'result':saved['result']}
        require(saved['status']==('received' if op=='receive' else 'proposal_retained') and
            handoff.read(root/(op+'.claim.json'))=={'requestHash':digest(request),'turnId':turn},
            'Preserve both original explicit receipt claims, not flags or reconstructed replies')
    proposal=handoff.read(root/'proposal.json')['result']
    require(handoff.read(root/'receive.json')['result'] is None and isinstance(proposal,dict) and
        set(proposal)=={'summary','nextSteps'} and isinstance(proposal['summary'],str) and 0<len(proposal['summary'])<=4000 and
        isinstance(proposal['nextSteps'],list) and 1<=len(proposal['nextSteps'])<=8 and
        all(isinstance(v,str) and 0<len(v)<=1000 for v in proposal['nextSteps']),'Bounded original inert proposal required')
    original=planning.original_context(registry,ledger,q['original']['bindingFile'],q['original']['command']['id'],disposed=True)
    if setup_transition is not None:
        from .admission_continuity import original_relation
        require(isinstance(setup_transition,dict) and set(setup_transition)=={'targetId','setupSource'},
            'Closed explicit registration continuity input required')
        original_relation(registry,ledger,q['original'],original,setup_transition['targetId'],
            setup_source=setup_transition['setupSource'])
    else: require(original==q['original'], 'Original rows, usage, claims, bindings and canonical identity must remain unchanged')
    require(tuple(map(str,handoff.phase.locations(registry,original)[:2]))==(q['journal'],q['mailbox']),
        'Original rows, usage, claims, bindings and canonical identity must remain unchanged')
    handoff.phase_clock(q,active=False)
    handoff.check_usage(q,result['records']['usage.json'],fresh=False,active=False)
    t=handoff.retained_transfer(q); host=t['destinationHost']
    require(planning.pin(q['candidateFile'])==q['candidatePin'] and
        planning._read_binding(q['candidateFile'])==q['candidateBinding'] and
        handoff.inspect_package(q['package']['root'])==q['package'] and
        planning.package_epochs(q['package'])==q['packageEpochs'] and
        planning.interpreter()==q['interpreter'] and planning.client_hash()==q['clientHash'] and
        all(planning.pin(p)==v for p,v in host['pins'].items()),'Exact original candidate/package/interpreter/provenance required')
    if live:
        require(handoff.destination_host(host['manifest'],host['attempt'],host['processRecord'],q['candidateBinding'])==host,
            'Only the same originally issued destination host may be inspected')
    row=handoff.read(owner/'transfer.json')
    require(row['status']=='metadata_transferred' and row['reviewHash']==digest(q) and
        row['brainId']==original['brainId'] and row['projectId']==original['scope']['projectId'] and
        row['historySha256']==t['archivePin']['sha256'],'Original positive metadata transfer required')
    # Hash complete old inventories; never adopt, rewrite or add to either one.
    old_pin=planning.pin(owner/'outcome.json')
    preserved=digest({'original':q['original'],'owner':old,'outcomePin':old_pin,
        'consumer':handoff.phase.consumer_inventory(q),'transfer':t,'sourceProof':proof})
    return q,{'reviewFile':str(file),'reviewPin':planning.pin(file),'reviewHash':digest(q),
        'originalSource':proof,'preservedHash':preserved,'originalOutcomePin':old_pin,'nativeTurnId':turn,
        'currentSourceHash':planning.old.source_hash(),'boundary':dict(BOUNDARY)}


class Probe(ReadProxy):
    """Independent read only, not an observer reconnect or a subscription."""
    def __init__(self,q):
        self.q=q; super().__init__(q['candidateBinding']['endpoint'])
    def _rpc(self,method,params):
        brain=self.q['original']['brainId']; bound=self.q['candidateBinding']['brains'][brain]
        allowed={'initialize':None,'account/read':[{'refreshToken':False}],
            'project/read':[{'projectId':bound['projectId']}],
            'thread/read':[{'threadId':brain,'includeTurns':True}],
            'thread/turns/list':[{'threadId':brain,'cursor':None,'limit':1,'sortDirection':'desc','itemsView':'notLoaded'}]}
        require(method in allowed and (method=='initialize' or params in allowed[method]),
            'No load, subscription, start, permission response, cancel, refresh, discovery or foreign target')
        value=super()._rpc(method,params)
        if method=='initialize': self.initialization=copy.deepcopy(value)
        return value


def sample(proxy,q,turn):
    t=handoff.transfer_record(q); brain=q['original']['brainId']; bound=q['candidateBinding']['brains'][brain]
    require(proxy.initialization['codexHome']==t['destinationHost']['home'],'Exact original destination home required')
    auth=handoff.authentication.require_ready(proxy)
    require(auth['responseHash']==t['authenticationHash'],'Native account/routing changed; no refresh permitted')
    project,thread=handoff.transfer.source_projection(proxy,{'brainId':brain,'projectId':bound['projectId'],'cwd':bound['cwd']})
    turns=thread['turns']
    require(len(turns)>=2 and turns[-1]['id']==turn and turns[-1]['status']=='completed' and
        turns[-2]['id']==q['original']['command']['notification']['nativeTurnId'] and turns[-2]['status']=='interrupted' and
        digest(turns[:-1])==t['snapshot']['turnsHash'],'Exact one new completed turn after the unchanged original history required')
    latest=proxy._rpc('thread/turns/list',{'threadId':brain,'cursor':None,'limit':1,'sortDirection':'desc','itemsView':'notLoaded'})
    require(isinstance(latest,dict) and isinstance(latest.get('data'),list) and len(latest['data'])==1 and
        latest['data'][0].get('id')==turn and latest['data'][0].get('status')=='completed',
        'Independent native latest-turn metadata must agree')
    target=handoff.read(handoff.phase.owner_root(q)/'transfer.json')['destinationPath']
    require(thread['path']==target,'Only the exact originally transferred native history may be read')
    raw,history=handoff.transfer.rollout(target,t['destinationHost']['home'],brain,bound['cwd'])
    require(raw.startswith(handoff.transfer.read_archive(t['archivePath'])),'Original transferred history prefix changed')
    rows=[planning.decode(line) for line in raw.splitlines()]; boundaries=[]
    for row in rows:
        payload=row.get('payload') or {}
        if row.get('type')=='event_msg' and payload.get('type') in ('task_started','task_complete','turn_aborted'):
            boundaries.append((payload['type'],payload.get('turn_id')))
    require(boundaries[-2:]==[('task_started',turn),('task_complete',turn)] and
        sum(v==('task_started',turn) for v in boundaries)==1 and
        sum(v==('task_complete',turn) for v in boundaries)==1,'Correlated exact persisted native start/completion required')
    return {'projectHash':digest(project),'threadHash':digest(thread),'latestPageHash':digest(latest),
        'authenticationHash':auth['responseHash'],'nativeStatus':thread['status'],'history':history,
        'nativeTurnId':turn,'nativeTurnStatus':'completed','currentPolicy':'unknown_not_collected',
        'currentTrackedTerminals':'unknown_not_collected'}


def collect(registry,ledger,file,directory,*,source=None):
    q,before=context(registry,ledger,file,source,live=True); t=handoff.transfer_record(q)
    root=Path(directory); planning.old.private_path(root.parent,existing=True)
    protected=(registry.root,ledger.root,Path(q['mailbox']),Path(q['transferFile']).parent,
        Path(t['snapshot']['sourceHome']),Path(t['destinationHost']['home']),Path(q['original']['scope']['checkout']),Path(q['package']['root']),
        Path(__file__).resolve().parent.parent,
        *([] if before['originalSource'] is None else [Path(before['originalSource']['root'])]))
    require(root.is_absolute() and root.resolve()==root and not os.path.lexists(root) and
        all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in protected),
        'New disjoint private evidence directory required; preserve every original claim')
    root.mkdir(mode=0o700); handoff.sync_directory(root.parent)
    exclusive(root/'intent.json',before)
    stage='native_metadata'
    try:
        with Probe(q) as proxy:
            first=sample(proxy,q,before['nativeTurnId']); second=sample(proxy,q,before['nativeTurnId'])
        require(first==second,'Changing native completion/identity/history remains unknown')
        stage='preservation_check'
        _,after=context(registry,ledger,file,source,live=True)
        require(before==after,'Original scope or outcome changed during independent inspection')
        evidence={'kind':KIND,'status':'preparation_completion_observed','context':before,'observedAt':time.time(),
            'native':first,'repeatHash':digest(second),'boundary':dict(BOUNDARY)}
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        # An interrupted evidence collection may be explicitly inspected later,
        # but cannot create/rearm any native effect or manufacture an outcome.
        evidence={'kind':KIND,'status':'unknown','context':before,'observedAt':time.time(),
            'errorType':type(error).__name__,'stage':stage,'boundary':dict(BOUNDARY)}
    exclusive(root/'evidence.json',evidence)
    return evidence


def status(registry,ledger,directory,*,completion_source=None,setup_transition=None):
    root=Path(directory); evidence=handoff.read(root/'evidence.json'); before=handoff.read(root/'intent.json')
    require({p.name for p in root.iterdir()}=={'intent.json','evidence.json'} and evidence.get('kind')==KIND and
        evidence.get('context')==before and evidence.get('boundary')==BOUNDARY and
        evidence.get('status') in ('preparation_completion_observed','unknown'),'Complete unmodified independent evidence required')
    source=before['originalSource']; _,now=context(registry,ledger,before['reviewFile'],None if source is None else source['root'],
        setup_transition=setup_transition)
    if before['currentSourceHash']!=now['currentSourceHash']:
        require(completion_source is not None and before['currentSourceHash']==PR182_SOURCE,
            'Historical completion requires its exact immutable qualified PR-182 source')
        proof=handoff.phase.lifecycle.source_proof(completion_source)
        require(proof['sourceHash']==PR182_SOURCE,'Only qualified PR-182 completion source bytes are supported')
        now={**now,'currentSourceHash':proof['sourceHash']}
    else: require(completion_source is None,'Current-source completion requires no historical-source substitute')
    require(before==now,'Original claims, evidence provenance or implementation changed')
    common={'kind','status','context','observedAt','boundary'}
    if evidence['status']=='preparation_completion_observed':
        require(set(evidence)==common|{'native','repeatHash'} and evidence['repeatHash']==digest(evidence['native']) and
            set(evidence['native'])=={'projectHash','threadHash','latestPageHash','authenticationHash','nativeStatus','history',
                'nativeTurnId','nativeTurnStatus','currentPolicy','currentTrackedTerminals'} and
            evidence['native']['nativeTurnId']==before['nativeTurnId'] and evidence['native']['nativeTurnStatus']=='completed',
            'Independent completion evidence changed')
        require(evidence['native']['nativeStatus'] in ({'type':'idle'},{'type':'notLoaded'}) and
            evidence['native']['currentPolicy']==evidence['native']['currentTrackedTerminals']=='unknown_not_collected',
            'No native activity, policy or terminal-safety promotion follows this evidence')
    else: require(set(evidence)==common|{'errorType','stage'} and evidence['stage'] in ('native_metadata','preservation_check'),
        'Closed unknown evidence required')
    return evidence  # No native call, file re-read of telemetry, or renewed timestamp.


def binding_review(registry,ledger,directory):
    evidence=status(registry,ledger,directory)
    require(evidence['status']=='preparation_completion_observed','Unknown completion cannot prepare a cutover review')
    q=planning.read_review(evidence['context']['reviewFile']); value=handoff.binding_review(q)
    request={**value['request'],'kind':'reconciled_preparation_binding_review_v1',
        'requiredOriginalOutcome':'incomplete_unknown','requiredOutcome':'preparation_completion_observed',
        'reconciliationFile':str(Path(directory)/'evidence.json'),
        'reconciliationPin':planning.pin(Path(directory)/'evidence.json'),
        'reconciliationHash':digest(evidence),'boundary':dict(BOUNDARY)}
    return {'request':request,'reviewHash':digest(request),'validUntil':'scope_changes',
        'prerequisiteSatisfied':True,'installsBinding':False,
        'effect':'Conditional proposal only: a separately reviewed/quiesced installation must revalidate this exact evidence and native host/membership; no new turn, load, replay, phase authority or safety inference'}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('collect'); c.add_argument('review'); c.add_argument('directory'); c.add_argument('--handoff-source')
    for name in ('status','binding-review'): c=sub.add_parser(name); c.add_argument('directory')
    args=p.parse_args(); registry,ledger=planning.partial.routes(args.platform,args.workspace)
    if args.action=='collect': out=collect(registry,ledger,args.review,args.directory,source=args.handoff_source)
    elif args.action=='status': out=status(registry,ledger,args.directory)
    else: out=binding_review(registry,ledger,args.directory)
    print(canonical(out))


if __name__=='__main__':
    try: main()
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
