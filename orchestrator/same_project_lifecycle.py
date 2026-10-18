"""One separately reviewed same-project successor, never a reset or replay.

Keep the predecessor unknown and immutable. Only an already-loaded exact brain
can receive one new inert receipt/proposal on the same foreground connection.
"""
import argparse
import contextlib
import copy
import hashlib
import os
from pathlib import Path
import stat
import threading
import time

from . import canceled_continuation as planning, connection_handoff as continuous
from .core import Refusal, canonical, digest, require
from .host_lifecycle import sync_directory
from .standard_quarantine import exclusive

LINEAGE='same_project_preflight_lineage_v1'
# Source-qualified PR-176 implementation, not a hash supplied by an evidence file.
LEGACY_SOURCE='bbea56bd8960eeaf8023af39a7243ad41415b7f81b569b2c8618e66d44369c72'
BOUNDARY={**planning.BOUNDARY,'predecessorOutcome':'unknown_preserved',
    'originalClaimRearmed':False,'newProjectCreated':False,'loadAuthorized':False}
REFUSAL='Already-loaded idle brain required; never reload'


def locations(registry,original):
    key=digest({'ledger':original['databases']['target']['identity'],'commandId':original['command']['id']})
    return registry.root/'same-project-followups'/key,Path(original['scope']['checkout'])/'.orchestrator-successor'/key


def source_proof(root):
    """Read immutable legacy Python bytes; never import/execute historical code."""
    root=Path(root); require(root.is_absolute() and root.resolve(strict=True)==root,'Canonical predecessor source required')
    directory=root/'orchestrator'
    require(directory.resolve(strict=True)==directory and not directory.is_symlink(),'Canonical complete source directory required')
    rows={}; epochs={}; files=sorted(directory.glob('*.py'))
    require(1<=len(files)<=512,'Complete bounded predecessor source required')
    for file in files:
        info=file.lstat()
        require(stat.S_ISREG(info.st_mode) and not file.is_symlink() and info.st_uid==os.getuid() and
            not info.st_mode&0o022 and info.st_nlink==1 and info.st_size<=2_000_000,'Unchanged non-writable source without aliases required')
        with os.fdopen(os.open(file,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
            raw=stream.read(2_000_001); after=os.fstat(stream.fileno())
        stamp=lambda x:[x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns,x.st_mode,x.st_uid,x.st_nlink]
        require(len(raw)==info.st_size and stamp(info)==stamp(after)==stamp(file.lstat()),'Predecessor source changed')
        rows[file.name]=hashlib.sha256(raw).hexdigest(); epochs[file.name]=stamp(info)
    require(files==sorted(directory.glob('*.py')) and all(
        epochs[f.name]==stamp(f.lstat()) for f in files),'Predecessor source inventory changed')
    return {'root':str(root),'sourceHash':digest(rows),'epochHash':digest(epochs)}


def inventory(root):
    root=planning.old.private_path(root,existing=True); out={}
    # No ignored/unlisted effects, nested records, aliases or partial inventories.
    for file in sorted(root.iterdir()):
        require(file.is_file() and not file.is_symlink(),'Closed flat predecessor journal/mailbox required')
        out[str(file)]=planning.pin(file)
    require(len(out)<=16,'Bounded complete predecessor inventory required')
    return out


def predecessor(registry,ledger,review_file,legacy_source=None):
    q=planning.read_review(review_file)
    require(q['version']==2,'Only the original version-2 preflight refusal is supported; no successor chains')
    original=planning.original_context(registry,ledger,q['original']['bindingFile'],q['original']['command']['id'],disposed=True)
    require(q['original']==original and tuple(map(str,planning.locations(registry,original)))==(q['journal'],q['mailbox']),
        'Exact same-project original context and canonical predecessor required')
    result=planning.status(q); root=Path(q['journal']); files=inventory(root); mail=inventory(q['mailbox'])
    names={Path(p).name for p in files}
    required={'intent.json','usage.claim.json','usage.json','failure.json','outcome.json'}
    require(names in (required,required|{'lifecycle.json'}) and
        {Path(p).name for p in mail}=={'handoff.json'},'Partial, subscription/turn/receipt/stop or unlisted predecessor records fence succession')
    require(result['status']=='incomplete_unknown' and result['nativeOutcome']=='unknown' and result['nativeTurnId'] is None and
        result['newReceiptRetained'] is False and result['proposalRetained'] is False,
        'Preserve unknown predecessor; an acknowledged, received or completed attempt is outside this path')
    failure=planning._read_private(root/'failure.json')
    require(set(failure)=={'errorType','detail','reviewHash','retryPermitted'} and failure=={
        'errorType':'Refusal','detail':REFUSAL,'reviewHash':digest(q),'retryPermitted':False},'Only the exact recorded pre-subscription refusal is supported')
    proof=None
    if 'lifecycle.json' in names:
        require(q['sourceHash']==planning.old.source_hash(),'Instrumented predecessor must use the qualified current implementation')
        require(result['records'].get('lifecycle.json')==planning.pin(root/'lifecycle.json') and
            planning._read_private(root/'lifecycle.json')=={'reviewHash':digest(q),'phase':'metadata_preflight',
                'connectionClosed':True,'preflightRefusalRecorded':True,'terminalSafety':'unknown'},
            'Positive closed preflight-stage record required; missing markers alone prove nothing')
    else:
        require(legacy_source is not None and q['sourceHash']==LEGACY_SOURCE,'Uninstrumented predecessors need their qualified immutable implementation')
        proof=source_proof(legacy_source)
        require(proof['sourceHash']==LEGACY_SOURCE,'Only qualified original PR-176 bytes may explain the legacy refusal')
    handoff=planning._read_private(Path(q['mailbox'])/'handoff.json')
    require(handoff=={'kind':planning.KIND,'requestHash':digest(q),
        'source':proof['root'] if proof else str(Path(planning.__file__).resolve().parent.parent),
        'sourceHash':q['sourceHash'],'brainId':q['original']['brainId'],'mailbox':q['mailbox']},
        'Exact original prospective mailbox context required')
    prior=planning.forward_usage.retained(q,result['records']['usage.json'],fresh=False,active=False)
    # This validates local failure lineage, not historical native non-execution,
    # process cleanup or the current loaded state. All remain separate facts.
    output={'kind':LINEAGE,'parentFile':str(Path(review_file)),'parentPin':planning.pin(review_file),
        'parentHash':digest(q),'files':{str(Path(review_file)):planning.pin(review_file),**files,**mail},
        'sourceProof':proof,'priorUsagePin':planning.pin(root/'usage.json'),'boundary':dict(BOUNDARY)}
    require(len(canonical(output).encode())<=12000,'Bounded complete lineage required')
    return output,q,prior


def prepare(registry,ledger,review_file,*,legacy_source=None):
    lineage,parent,_=predecessor(registry,ledger,review_file,legacy_source)
    q=copy.deepcopy(parent)
    q.update(version=3,kind=planning.SUCCESSOR_KIND,sourceHash=planning.old.source_hash(),
        clientHash=planning.client_hash(),lineage=lineage)
    q['journal'],q['mailbox']=map(str,locations(registry,q['original']))
    require(not os.path.lexists(q['journal']) and not os.path.lexists(q['mailbox']) and
        not os.path.lexists(continuous.location(registry,q)),'Same-project successor/owner already consumed; no new version or chain')
    planning.current(registry,ledger,q)
    return {'request':q,'reviewHash':digest(q),'validUntil':'scope_changes','boundary':dict(BOUNDARY),
        'effect':'One combined exact review: same-project already-loaded-only subscription, one actual cumulative usage collection and one NEW inert receipt/proposal turn; no predecessor retry, load, Play, recovery or binding change'}


class InspectionProxy(planning.Proxy):
    def _rpc(self,method,params):
        require(method in {'initialize','project/read','thread/read','thread/turns/list',
            'thread/effectivePolicy/read','thread/backgroundTerminals/list'},'Diagnostic connection cannot subscribe, load, start or answer')
        return super()._rpc(method,params)


def inspect(registry,ledger,q):
    """Explicit diagnostic only. Never consume an execution claim or collect usage."""
    require(planning.valid(q) and q['version']==3,'Exact prospective same-project scope required')
    planning.current(registry,ledger,q); samples=[]
    with InspectionProxy(q['candidateBinding']['endpoint']) as proxy:
        for _ in range(2):
            planning.latest_original(proxy,q)
            brain=q['original']['brainId']; bound=q['candidateBinding']['brains'][brain]
            project=proxy._rpc('project/read',{'projectId':bound['projectId']}).get('project')
            thread=proxy._rpc('thread/read',{'threadId':brain,'includeTurns':False}).get('thread')
            require(isinstance(project,dict) and project.get('id')==bound['projectId'] and project.get('roots')==[{'path':bound['cwd']}] and
                isinstance(thread,dict) and thread.get('id')==brain and thread.get('projectId')==bound['projectId'] and thread.get('cwd')==bound['cwd'],
                'Exact current project/brain/cwd required')
            status=thread.get('status')
            require(status in ({'type':'idle'},{'type':'notLoaded'}),'Active, permission-wait or unknown state is not ready')
            sample={'nativeStatus':status,'identityHash':digest([brain,bound['projectId'],bound['cwd']]),
                'policy':'unknown','trackedTerminals':'unknown'}
            if status=={'type':'idle'}:
                data=planning.transport.Subscription(proxy,q['candidateBinding'],brain,q['transport'])._sample()
                sample.update(policy=data['policyHash'],trackedTerminals='known_empty_current_only')
            samples.append(sample); planning.current(registry,ledger,q)
        require(samples[0]==samples[1],'Changing native state remains unknown')
    return {'kind':'same_project_lifecycle_diagnostic_v1','reviewHash':digest(q),'observedAt':time.time(),
        **samples[0],'blockers':[] if samples[0]['nativeStatus']=={'type':'idle'} else ['brain_not_loaded_no_reload_authorized'],
        'executionAuthorized':False,'subscriptionAttached':False,'usageCollected':False,'boundary':dict(BOUNDARY)}


def check_lineage(registry,ledger,q):
    line=q['lineage']; require(isinstance(line,dict) and line.get('kind')==LINEAGE,'Closed same-project lineage required')
    proof=line.get('sourceProof')
    actual,parent,_=predecessor(registry,ledger,line['parentFile'],None if proof is None else proof['root'])
    require(actual==line and q['original']==parent['original'] and all(q[k]==parent[k] for k in
        ('candidateFile','candidatePin','candidateBinding','transport','interpreter','package','packageEpochs','maxTokens','usageSource')),
        'Predecessor evidence, unchanged binding/package/scope/accounting or ceiling changed')


def retained_lineage(q):
    line=q['lineage']; parent=planning.read_review(line['parentFile'])
    actual={str(Path(line['parentFile'])):planning.pin(line['parentFile']),
        **inventory(parent['journal']),**inventory(parent['mailbox'])}
    require(actual==line['files'] and digest(parent)==line['parentHash'] and
        planning.pin(line['parentFile'])==line['parentPin'],'Retained predecessor records changed')
    if line['sourceProof'] is not None:
        require(source_proof(line['sourceProof']['root'])==line['sourceProof'],'Legacy implementation changed')


def check_usage(q,usage_pin,*,fresh,active=True):
    line=q['lineage']; parent=planning.read_review(line['parentFile'])
    prior=planning.forward_usage.retained(parent,line['priorUsagePin'],fresh=False,active=False)['report']
    report=planning.forward_usage.retained(q,usage_pin,fresh=fresh,active=active)['report']
    original=copy.deepcopy(q['original']); run=original['run']
    run['usageReport']=prior; original['usageReceiptHash']=digest(prior)
    run['usageHighWater']=max(run['usageHighWater'],prior['tokens']['total_tokens'])
    run['brainObservedTokens']=max(run['brainObservedTokens'],prior['tokens']['total_tokens'])
    planning.forward_usage.budget(original,q['maxTokens'],report,fresh=fresh,active=active)


class SuccessorOwner(continuous.Owner):
    """Same-process, single-use transport capability for the combined NEW review."""
    def __init__(self,registry,ledger,q,proxy,subscription,root):
        self.registry,self.ledger=registry,ledger; self.h={'planning':q}
        self.proxy,self.subscription,self.root=proxy,subscription,root
        self.connection=proxy.process; self.thread_id=threading.get_ident()
        self.authorized=True; self.used=self.claimed=False
        self.identity=digest({'reviewHash':digest(q),'process':continuous.process_identity(os.getpid())})
    def check(self):
        q=self.h['planning']; planning.current(self.registry,self.ledger,q)
        require(planning._read_private(self.root/'intent.json')=={'kind':planning.SUCCESSOR_KIND,'reviewHash':digest(q)} and
            not os.path.lexists(self.root/'stop.json') and not os.path.lexists(self.root/'outcome.json') and
            self.proxy.process is self.connection is self.subscription.connection and self.connection.poll() is None and
            threading.get_ident()==self.thread_id and self.subscription.ready,'Original successor owner lost/stopped; no adoption or reconnect')
    def admit(self,q):
        require(q==self.h['planning'] and not self.claimed and not self.used,'Single original consumer required')
        self.claimed=True; self.check()
    @contextlib.contextmanager
    def borrow(self,q):
        require(q==self.h['planning'] and self.claimed and not self.used,'Original successor handoff consumed')
        self.used=True; self.check(); exclusive(self.root/'handoff.claim.json',{'reviewHash':digest(q),'owner':self.identity})
        yield self.proxy
        self.check()
    def evidence(self,q):
        require(q==self.h['planning'] and self.used,'Original successor consumer required'); self.check()
        first,second=self.subscription._sample(),self.subscription._sample()
        require(first==second,'Native drift at same-project handoff')
        return {'owner':self.identity,'observedAt':time.time(),'snapshotHash':digest(second),'sameConnection':True}


def confirm(registry,ledger,q,confirmation_hash,*,writers_stopped=False,backup_root=None):
    require(planning.valid(q) and q['version']==3 and confirmation_hash==digest(q) and
        writers_stopped is True and backup_root is not None,'Exact combined successor confirmation, stopped writers and verified backup required')
    q=copy.deepcopy(q); planning.current(registry,ledger,q); planning.verify_backup(q,backup_root)
    root=continuous.location(registry,q)
    require(not os.path.lexists(q['journal']) and not os.path.lexists(q['mailbox']),'Successor planning already consumed')
    with planning.partial.lock(registry.db),planning.partial.lock(ledger.db):
        planning.current(registry,ledger,q)
        root.parent.mkdir(mode=0o700,exist_ok=True); planning.old.private_path(root.parent,existing=True)
        root.mkdir(mode=0o700); sync_directory(root.parent)
        exclusive(root/'intent.json',{'kind':planning.SUCCESSOR_KIND,'reviewHash':digest(q)})
    proxy=None; result=None
    try:
        with planning.Proxy(q['candidateBinding']['endpoint']) as proxy:
            require(not os.path.lexists(root/'stop.json'),'Owner Stop fences successor subscription')
            require(planning.latest_original(proxy,q)==planning.latest_original(proxy,q),'Original native turn changed')
            sub=planning.transport.Subscription(proxy,q['candidateBinding'],q['original']['brainId'],q['transport'])
            def claim(context):
                planning.current(registry,ledger,q)
                require(not os.path.lexists(root/'stop.json'),'Owner Stop fences successor subscription')
                exclusive(root/'subscription.claim.json',{'contextHash':context,'subscriptionClaimed':True})
                return {'contextHash':context,'subscriptionClaimed':True}
            attached=sub.attach(claim)
            exclusive(root/'subscription.json',attached)
            owner=SuccessorOwner(registry,ledger,q,proxy,sub,root)
            result=planning.confirm(registry,ledger,q,digest(q),writers_stopped=True,backup_root=backup_root,_handoff=owner)
            exclusive(root/'planning-outcome.json',result)
    except (Refusal,OSError,ValueError,KeyError,TypeError,KeyboardInterrupt) as error:
        exclusive(root/'failure.json',{'errorType':type(error).__name__,'detail':str(error)[:512],'retryPermitted':False})
    closed=proxy is not None and proxy.process is None
    value={'status':result['status'] if result and closed else 'blocked_or_unknown','reviewHash':digest(q),
        'connectionClosed':closed,'boundary':dict(BOUNDARY),'records':{name:planning.pin(root/name) for name in
        ('subscription.claim.json','subscription.json','handoff.claim.json','planning-outcome.json','failure.json','stop.json') if (root/name).exists()}}
    exclusive(root/'outcome.json',value); return value


def status(registry,q):
    require(planning.valid(q) and q['version']==3,'Exact successor review required'); root=continuous.location(registry,q)
    retained_lineage(q)
    if not os.path.lexists(root): return {'status':'not_submitted','boundary':dict(BOUNDARY)}
    require(planning._read_private(root/'intent.json')=={'kind':planning.SUCCESSOR_KIND,'reviewHash':digest(q)},'Changed/partial successor owner')
    if not (root/'outcome.json').exists(): return {'status':'claimed_current_connection_unknown','boundary':dict(BOUNDARY)}
    value=planning._read_private(root/'outcome.json')
    require(set(value)=={'status','reviewHash','connectionClosed','boundary','records'} and value['reviewHash']==digest(q) and
        value['boundary']==BOUNDARY and type(value['connectionClosed']) is bool and
        value['status'] in ('blocked_or_unknown','incomplete_unknown','planning_completed') and
        set(value['records'])<= {'subscription.claim.json','subscription.json','handoff.claim.json','planning-outcome.json','failure.json','stop.json'} and
        all(planning.pin(root/name)==pin for name,pin in value['records'].items()),'Changed successor outcome')
    if value['status']=='planning_completed':
        require(value['connectionClosed'] and {'subscription.claim.json','subscription.json','handoff.claim.json','planning-outcome.json'}<=set(value['records']) and
            planning.status(q)==planning._read_private(root/'planning-outcome.json') and planning.status(q)['status']=='planning_completed',
            'Native completion alone is not the new receipt/proposal')
    return value


def stop(registry,q,confirmation_hash):
    require(planning.valid(q) and q['version']==3 and confirmation_hash==digest(q),'Exact successor stop required')
    root=continuous.location(registry,q)
    require(planning._read_private(root/'intent.json')=={'kind':planning.SUCCESSOR_KIND,'reviewHash':digest(q)},'Exact original successor owner required')
    exclusive(root/'stop.json',{'reviewHash':digest(q),'nativeCancelSent':False})
    return {'status':'stop_requested','nativeCancelSent':False}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare'); a.add_argument('predecessor_review'); a.add_argument('--legacy-source')
    for name in ('backup','confirm','inspect','status','stop'):
        a=sub.add_parser(name); a.add_argument('review')
        if name=='backup': a.add_argument('destination')
        if name in ('confirm','stop'): a.add_argument('--confirm-hash',required=True)
        if name in ('backup','confirm'): a.add_argument('--writers-stopped',action='store_true')
        if name=='confirm': a.add_argument('--backup',required=True)
    args=p.parse_args(); registry,ledger=planning.partial.routes(args.platform,args.workspace)
    if args.action=='prepare': result=prepare(registry,ledger,args.predecessor_review,legacy_source=args.legacy_source)
    else:
        q=planning.read_review(args.review); require(q['version']==3,'Separate same-project review required')
        if args.action=='backup': result=planning.backup(registry,ledger,q,args.destination,writers_stopped=args.writers_stopped)
        elif args.action=='confirm': result=confirm(registry,ledger,q,args.confirm_hash,writers_stopped=args.writers_stopped,backup_root=args.backup)
        elif args.action=='stop': result=stop(registry,q,args.confirm_hash)
        elif args.action=='inspect': result=inspect(registry,ledger,q)
        else: result=status(registry,q)
    print(canonical(result))


if __name__=='__main__':
    from .same_project_lifecycle import main as entrypoint
    try: entrypoint()
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
