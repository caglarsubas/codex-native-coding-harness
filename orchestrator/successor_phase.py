"""One new preparation-only phase in the same project; expired history is inert.

This is not another project, retry, clock extension, worker Play or cleanup proof.
The new exact review permits one already-loaded-only subscription and proposal.
"""
import argparse
import contextlib
import copy
import math
import os
from pathlib import Path
import re
import threading
import time

from . import canceled_continuation as planning, maintenance_load as maintenance
from . import same_project_lifecycle as lifecycle, connection_handoff as continuous
from .core import Refusal, canonical, digest, require
from .host_lifecycle import sync_directory
from .standard_quarantine import exclusive

KIND=planning.PHASE_KIND
MAINTENANCE_SOURCE='268ae4a138b48517df3c59ab2ea4521e918615825fa7735b589304ca8a507ac1'
BOUNDARY={**planning.BOUNDARY,'oldPhaseExpired':True,'oldPhaseChanged':False,
    'newPhasePreparationOnly':True,'repositoryHoldsReleased':False,'newProjectCreated':False,
    'workerLimit':0,'loadAuthorized':False,'predecessorOutcome':'unknown_preserved'}
PHASE_FIELDS={'id','kind','durationHours','maxTokens','workerLimit','repositoryWrites',
    'predecessorRunId','carriedUsageHighWater','carriedBrainTokens','priorUsageHash'}
LINE_FIELDS={'maintenanceFile','maintenancePin','maintenanceHash','maintenanceSourceProof',
    'contextHash','files','priorUsagePin'}


def locations(registry,original):
    key=digest({'ledger':original['databases']['target']['identity'],'commandId':original['command']['id']})
    base=registry.root/'same-project-phases'/key
    return base/'planning',Path(original['scope']['checkout'])/'.orchestrator-phase'/key,base/'owner'


def historical(registry,ledger,file,maintenance_source=None):
    require(Path(file).name not in maintenance.NON_REVIEWS,'Credentials are not phase reviews')
    q=maintenance.read_review(file); result=maintenance.status(q)
    require(result['status']=='maintenance_load_observed_idle' and result['connectionClosed'] is True,
        'Complete positive closed maintenance required; unknown/partial attempts cannot become successor authority')
    rows=lifecycle.inventory(q['journal'])
    require({Path(p).name for p in rows}==maintenance.OLD_RECORDS,'Exact complete maintenance inventory required')
    line=q['context']['lineage']; proof=line['sourceProof']
    actual,parent,_=maintenance.context(registry,ledger,line['parentFile'],q['context']['loadFile'],
        None if proof is None else proof['root'])
    require(actual==q['context'] and q['scope']==maintenance.prior.read_review(q['context']['loadFile'])['provenance']['scope'] and
        str(maintenance.location(registry,parent['original']))==q['journal'],'Exact canonical completed maintenance lineage required')
    qualified=None
    if q['sourceHash']!=planning.old.source_hash():
        require(q['sourceHash']==MAINTENANCE_SOURCE and maintenance_source is not None,
            'Historical maintenance requires its qualified immutable PR-179 source')
        qualified=lifecycle.source_proof(maintenance_source)
        require(qualified['sourceHash']==MAINTENANCE_SOURCE,'Only exact qualified PR-179 maintenance source is supported')
    prior=planning.forward_usage.retained(parent,line['priorUsagePin'],fresh=False,active=False)
    files={str(Path(file)):planning.pin(file),**rows,**line['files'],**q['context']['loadInventory'],
        q['context']['loadFile']:q['context']['loadPin'],parent['candidateFile']:parent['candidatePin'],
        parent['original']['bindingFile']:parent['original']['bindingPin']}
    return {'maintenanceFile':str(Path(file)),'maintenancePin':planning.pin(file),'maintenanceHash':digest(q),
        'maintenanceSourceProof':qualified,'contextHash':digest(actual),'files':files,
        'priorUsagePin':line['priorUsagePin']},parent,prior


def phase_spec(parent,prior,duration,max_tokens):
    require(type(duration) is int and 1<=duration<=24 and type(max_tokens) is int and 1<=max_tokens<=100000,
        'Review one explicit 1-24 hour preparation phase and bounded planning allowance')
    run=parent['original']['run']; report=prior['report']
    planning.forward_usage.budget(parent['original'],max_tokens,report,fresh=False,active=False)
    return {'id':'successor-preparation-'+digest({'run':run['id'],'command':parent['original']['command']['id']})[:16],
        'kind':'preparation_only','durationHours':duration,'maxTokens':max_tokens,'workerLimit':0,
        'repositoryWrites':False,'predecessorRunId':run['id'],
        'carriedUsageHighWater':max(run['usageHighWater'],report['tokens']['total_tokens']),
        'carriedBrainTokens':max(run['brainObservedTokens'],sum(r['tokens']['total_tokens'] for r in report['records'])),
        'priorUsageHash':digest(report)}


def valid(q):
    if not planning.valid(q) or q['version']!=4: return False
    p=q['phase']; line=q['phaseLineage']
    return (set(p)==PHASE_FIELDS and p['kind']=='preparation_only' and type(p['durationHours']) is int and
        1<=p['durationHours']<=24 and type(p['maxTokens']) is int and p['maxTokens']==q['maxTokens'] and type(p['workerLimit']) is int and
        p['workerLimit']==0 and p['repositoryWrites'] is False and set(line)==LINE_FIELDS and
        all(type(p[k]) is int and p[k]>=0 for k in ('carriedUsageHighWater','carriedBrainTokens')) and
        isinstance(line['files'],dict) and len(line['files'])<=256 and
        all(isinstance(path,str) and Path(path).is_absolute() and Path(path).name not in maintenance.NON_REVIEWS
            for path in [line['maintenanceFile'],*line['files']]))


def prepare(registry,ledger,maintenance_file,*,duration_hours=24,max_tokens=10000,maintenance_source=None):
    line,parent,prior=historical(registry,ledger,maintenance_file,maintenance_source)
    require(time.time()>=parent['original']['run']['expiresAt'],'Successor phase requires the original expired disposition; never extend an active phase')
    q=copy.deepcopy(parent); journal,mailbox,owner=locations(registry,q['original'])
    require(not os.path.lexists(owner.parent) and not os.path.lexists(mailbox),'One canonical successor phase already claimed; no new ID/version retry')
    q.update(version=4,kind=KIND,sourceHash=planning.old.source_hash(),clientHash=planning.client_hash(),
        maxTokens=max_tokens,journal=str(journal),mailbox=str(mailbox),phaseLineage=line,
        phase=phase_spec(parent,prior,duration_hours,max_tokens))
    require(valid(q),'Closed same-project preparation phase review required')
    current(registry,ledger,q)
    return {'request':q,'reviewHash':digest(q),'validUntil':'scope_changes','boundary':dict(BOUNDARY),
        'effect':'One NEW preparation-only phase, its own confirmation-started clock, one already-loaded-only subscription, one cumulative usage collection and one inert receipt/proposal; no worker Play, reload, old-clock extension or replay'}


def retained_lineage(q):
    require(valid(q),'Exact phase review required'); line=q['phaseLineage']
    m=maintenance.read_review(line['maintenanceFile'])
    require(planning.pin(line['maintenanceFile'])==line['maintenancePin'] and digest(m)==line['maintenanceHash'] and
        maintenance.status(m)['status']=='maintenance_load_observed_idle' and
        all(planning.pin(path)==pin for path,pin in line['files'].items()),'Retained maintenance or original claims changed')
    proof=line['maintenanceSourceProof']
    if proof is not None:
        require(proof['sourceHash']==MAINTENANCE_SOURCE and lifecycle.source_proof(proof['root'])==proof,
            'Historical qualified maintenance source changed')


def current(registry,ledger,q,*,started=False,usage_pin=None):
    require(valid(q),'Exact new preparation-only phase required')
    line=q['phaseLineage']; proof=line['maintenanceSourceProof']
    actual,parent,prior=historical(registry,ledger,line['maintenanceFile'],None if proof is None else proof['root'])
    require(actual==line and q['original']==parent['original'] and all(q[k]==parent[k] for k in
        ('candidateFile','candidatePin','candidateBinding','transport','interpreter','package','packageEpochs','usageSource')),
        'Same existing project/brain/package/source/usage/bindings required; no migration')
    require(time.time()>=q['original']['run']['expiresAt'] and
        q['phase']==phase_spec(parent,prior,q['phase']['durationHours'],q['maxTokens']),
        'Old expired phase and carried cumulative accounting must remain exact')
    require(tuple(map(str,locations(registry,q['original'])[:2]))==(q['journal'],q['mailbox']),
        'Canonical new phase locations changed')
    planning.forward_usage.check_source(ledger,q['usageSource'])
    root=locations(registry,q['original'])[2]
    require(not os.path.lexists(root/'stop.json') and not os.path.lexists(Path(q['journal'])/'stop.json'),
        'Owner Stop fences the new phase without native cancellation')
    if root.parent.exists(): phase_clock(q)
    if usage_pin is not None: check_usage(q,usage_pin,fresh=not started)


def owner_root(q):
    return Path(q['journal']).parent/'owner'


def phase_clock(q,*,active=True):
    row=planning._read_private(owner_root(q)/'intent.json')
    require(set(row)=={'kind','reviewHash','phaseClock'} and row['kind']==KIND and row['reviewHash']==digest(q),
        'Exact original phase intent required; no partial adoption')
    clock=row['phaseClock']; p=q['phase']
    require(isinstance(clock,dict) and set(clock)=={'phaseId','startedAt','expiresAt','durationHours'} and
        clock['phaseId']==p['id'] and clock['durationHours']==p['durationHours'] and
        all(type(clock[k]) in (int,float) and math.isfinite(clock[k]) for k in ('startedAt','expiresAt')) and
        clock['expiresAt']==clock['startedAt']+p['durationHours']*3600 and
        (not active or clock['startedAt']<=time.time()<clock['expiresAt']),'New phase clock expired/changed; no renewal or old-phase extension')
    return clock


def lineage_files(q):
    m=maintenance.read_review(q['phaseLineage']['maintenanceFile'])
    files=sorted(set(maintenance.backup_files(m))|set(q['phaseLineage']['files']))
    require(len(files)<=256 and all(Path(p).name not in maintenance.NON_REVIEWS for p in files),
        'Bounded non-credential original records required')
    return files


def backup_destination(registry,q,root):
    m=maintenance.read_review(q['phaseLineage']['maintenanceFile']); old=maintenance.prior.read_review(m['context']['loadFile'])
    protected=[registry.root,Path(q['original']['root']),Path(old['provenance']['home']),Path(q['original']['scope']['checkout']),
        Path(old['provenance']['launchFile']).parent,Path(q['package']['root'])]
    require(all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in protected),
        'Phase backup cannot overlap the registry, ledger, native home, checkout, package or launch evidence')


def check_usage(q,pin,*,fresh,active=True):
    report=planning.forward_usage.retained(q,pin,fresh=fresh,active=False)['report']
    m=maintenance.read_review(q['phaseLineage']['maintenanceFile']); parent=planning.read_review(m['context']['lineage']['parentFile'])
    prior=planning.forward_usage.retained(parent,q['phaseLineage']['priorUsagePin'],fresh=False,active=False)['report']
    original=copy.deepcopy(q['original']); run=original['run']
    run.update(usageReport=prior,usageHighWater=q['phase']['carriedUsageHighWater'],brainObservedTokens=q['phase']['carriedBrainTokens'])
    original['usageReceiptHash']=digest(prior)
    planning.forward_usage.budget(original,q['maxTokens'],report,fresh=fresh,active=False)
    if active: phase_clock(q)


def prompt_prefix(q):
    return ('This is separately reviewed NEW preparation-only phase '+q['phase']['id']+'. '
        'Its own '+str(q['phase']['durationHours'])+'-hour clock does not renew the expired original phase. '
        'Cumulative consumption is carried forward, not refunded. Zero workers and no repository edits are authorized. ')


class PhaseOwner(lifecycle.SuccessorOwner):
    def __init__(self,registry,ledger,q,proxy,subscription,root):
        super().__init__(registry,ledger,q,proxy,subscription,root)
        self.intent_pin=planning.pin(root/'intent.json')
    def check(self):
        q=self.h['planning']; planning.current(self.registry,self.ledger,q)
        require(planning.pin(self.root/'intent.json')==self.intent_pin and
            not os.path.lexists(self.root/'stop.json') and not os.path.lexists(self.root/'outcome.json') and
            self.proxy.process is self.connection is self.subscription.connection and self.connection.poll() is None and
            threading.get_ident()==self.thread_id and self.subscription.ready,
            'Original new-phase owner/clock lost or changed; no adoption, reconnect or renewal')


def inspect(registry,ledger,q):
    """Non-authorizing diagnostic, no owner claim, subscription, usage or load."""
    planning.current(registry,ledger,q); samples=[]
    with lifecycle.InspectionProxy(q['candidateBinding']['endpoint']) as proxy:
        for _ in range(2):
            planning.latest_original(proxy,q); brain=q['original']['brainId']; bound=q['candidateBinding']['brains'][brain]
            project=proxy._rpc('project/read',{'projectId':bound['projectId']}).get('project')
            thread=proxy._rpc('thread/read',{'threadId':brain,'includeTurns':False}).get('thread')
            require(isinstance(project,dict) and project.get('id')==bound['projectId'] and project.get('roots')==[{'path':bound['cwd']}] and
                isinstance(thread,dict) and thread.get('id')==brain and thread.get('projectId')==bound['projectId'] and
                thread.get('cwd')==bound['cwd'],'Exact unchanged native identity required')
            activity=thread.get('status'); require(activity in ({'type':'idle'},{'type':'notLoaded'}),'Active/permission/unknown is not ready')
            value={'nativeStatus':activity,'policy':'unknown','trackedTerminals':'unknown'}
            if activity=={'type':'idle'}:
                sample=planning.transport.Subscription(proxy,q['candidateBinding'],brain,q['transport'])._sample()
                value.update(policy=sample['policyHash'],trackedTerminals='known_empty_current_only')
            samples.append(value); planning.current(registry,ledger,q)
    require(samples[0]==samples[1],'Changing native observation stays unknown')
    return {'observedAt':time.time(),**samples[0],'blockers':[] if samples[0]['nativeStatus']=={'type':'idle'} else ['brain_not_loaded_no_reload_authorized'],
        'executionAuthorized':False,'subscriptionAttached':False,'usageCollected':False,'boundary':dict(BOUNDARY)}


def consumer_inventory(q):
    root=Path(q['journal'])
    if not root.exists(): return {}
    allowed={'intent.json','subscription.claim.json','subscription.json','turn-start.claim.json','native-ack.json',
        'receive.claim.json','receive.json','proposal.claim.json','proposal.json','usage.claim.json','usage.json',
        'lifecycle.json','failure.json','outcome.json','stop.json'}
    files=sorted(root.iterdir()); require(len(files)<=2064,'Bounded complete phase inventory required')
    for file in files:
        match=re.fullmatch(r'event-(\d+)\.json',file.name)
        require(file.is_file() and not file.is_symlink() and (file.name in allowed or match and int(match[1])<2048),
            'Unlisted or partial new-phase records stay unknown')
    return {str(file):planning.pin(file) for file in files}


def confirm(registry,ledger,q,confirmation_hash,*,writers_stopped=False,backup_root=None):
    require(valid(q) and confirmation_hash==digest(q) and writers_stopped is True and backup_root is not None,
        'Exact new phase review, stopped writers and verified private backup required')
    planning.current(registry,ledger,q); planning.verify_backup(q,backup_root)
    journal,mailbox,root=locations(registry,q['original'])
    with planning.partial.lock(registry.db),planning.partial.lock(ledger.db):
        planning.current(registry,ledger,q)
        require(not os.path.lexists(root.parent) and not os.path.lexists(mailbox),'New phase already consumed; no recursive successor')
        root.parent.parent.mkdir(mode=0o700,exist_ok=True); planning.old.private_path(root.parent.parent,existing=True)
        root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700); sync_directory(root.parent.parent)
        start=time.time(); clock={'phaseId':q['phase']['id'],'startedAt':start,'expiresAt':start+q['phase']['durationHours']*3600,
            'durationHours':q['phase']['durationHours']}
        exclusive(root/'intent.json',{'kind':KIND,'reviewHash':digest(q),'phaseClock':clock})
    intent_pin=planning.pin(root/'intent.json'); proxy=None; result=None
    try:
        with planning.Proxy(q['candidateBinding']['endpoint']) as proxy:
            require(planning.latest_original(proxy,q)==planning.latest_original(proxy,q),'Original native turn changed')
            sub=planning.transport.Subscription(proxy,q['candidateBinding'],q['original']['brainId'],q['transport'])
            def claim(context):
                planning.current(registry,ledger,q)
                require(planning.pin(root/'intent.json')==intent_pin,'Original phase clock changed')
                exclusive(root/'subscription.claim.json',{'contextHash':context,'subscriptionClaimed':True})
                return {'contextHash':context,'subscriptionClaimed':True}
            attached=sub.attach(claim); exclusive(root/'subscription.json',attached)
            require(planning.pin(root/'intent.json')==intent_pin,'Original phase clock changed')
            owner=PhaseOwner(registry,ledger,q,proxy,sub,root)
            result=planning.confirm(registry,ledger,q,digest(q),writers_stopped=True,backup_root=backup_root,_handoff=owner)
            exclusive(root/'planning-outcome.json',result)
    except (Refusal,OSError,ValueError,KeyError,TypeError,KeyboardInterrupt) as error:
        exclusive(root/'failure.json',{'errorType':type(error).__name__,'detail':str(error)[:512],'retryPermitted':False})
    closed=proxy is not None and proxy.process is None
    value={'status':result['status'] if result and closed else 'blocked_or_unknown','reviewHash':digest(q),
        'connectionClosed':closed,'boundary':dict(BOUNDARY),'records':{name:planning.pin(root/name) for name in
            ('intent.json','subscription.claim.json','subscription.json','handoff.claim.json','planning-outcome.json','failure.json','stop.json') if (root/name).exists()},
        'consumerInventory':consumer_inventory(q)}
    exclusive(root/'outcome.json',value); return value


def status(registry,q):
    require(valid(q),'Exact new phase review required'); retained_lineage(q); root=owner_root(q)
    if not os.path.lexists(root.parent): return {'status':'not_submitted','boundary':dict(BOUNDARY)}
    phase_clock(q,active=False)
    if not (root/'outcome.json').exists(): return {'status':'claimed_current_connection_unknown','boundary':dict(BOUNDARY)}
    r=planning._read_private(root/'outcome.json')
    require(set(r)=={'status','reviewHash','connectionClosed','boundary','records','consumerInventory'} and r['reviewHash']==digest(q) and
        r['boundary']==BOUNDARY and type(r['connectionClosed']) is bool and r['status'] in ('blocked_or_unknown','incomplete_unknown','planning_completed') and
        set(r['records'])<={'intent.json','subscription.claim.json','subscription.json','handoff.claim.json','planning-outcome.json','failure.json','stop.json'} and
        'intent.json' in r['records'] and all(planning.pin(root/name)==pin for name,pin in r['records'].items()) and
        r['consumerInventory']==consumer_inventory(q),'Changed/partial phase outcome stays unknown')
    require({p.name for p in root.iterdir()}==set(r['records'])|{'outcome.json'}|({'stop.json'} if (root/'stop.json').exists() else set()),
        'Unlisted owner records cannot be ignored')
    if (root/'stop.json').exists():
        require(planning._read_private(root/'stop.json')=={'reviewHash':digest(q),'nativeCancelSent':False},'Changed owner Stop')
    if r['status']=='planning_completed':
        require(r['connectionClosed'] and {'intent.json','subscription.claim.json','subscription.json','handoff.claim.json','planning-outcome.json'}<=set(r['records']) and
            planning.status(q)==planning._read_private(root/'planning-outcome.json') and planning.status(q)['status']=='planning_completed',
            'Native completion alone is not a phase receipt/proposal')
    return r


def stop(registry,q,confirmation_hash):
    require(valid(q) and confirmation_hash==digest(q),'Exact phase stop review required')
    phase_clock(q,active=False); exclusive(owner_root(q)/'stop.json',{'reviewHash':digest(q),'nativeCancelSent':False})
    return {'status':'stop_requested','nativeCancelSent':False}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare'); a.add_argument('maintenance_review'); a.add_argument('--maintenance-source')
    a.add_argument('--duration-hours',type=int,default=24); a.add_argument('--max-tokens',type=int,default=10000)
    for name in ('backup','confirm','inspect','status','stop'):
        a=sub.add_parser(name); a.add_argument('review')
        if name=='backup': a.add_argument('destination')
        if name in ('confirm','stop'): a.add_argument('--confirm-hash',required=True)
        if name in ('backup','confirm'): a.add_argument('--writers-stopped',action='store_true')
        if name=='confirm': a.add_argument('--backup',required=True)
    args=p.parse_args(); registry,ledger=planning.partial.routes(args.platform,args.workspace)
    if args.action=='prepare': out=prepare(registry,ledger,args.maintenance_review,duration_hours=args.duration_hours,
        max_tokens=args.max_tokens,maintenance_source=args.maintenance_source)
    else:
        q=planning.read_review(args.review); require(valid(q),'Separate successor phase review required')
        if args.action=='backup': out=planning.backup(registry,ledger,q,args.destination,writers_stopped=args.writers_stopped)
        elif args.action=='confirm': out=confirm(registry,ledger,q,args.confirm_hash,writers_stopped=args.writers_stopped,backup_root=args.backup)
        elif args.action=='inspect': out=inspect(registry,ledger,q)
        elif args.action=='stop': out=stop(registry,q,args.confirm_hash)
        else: out=status(registry,q)
    print(canonical(out))


if __name__=='__main__':
    try: main()
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
