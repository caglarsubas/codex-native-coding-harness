"""Exact foreground ownership through review, then same-connection planning.

No load, reconnect, second subscription, replay, controller or background keeper.
Consumed planning attempts cannot use this prospective path.
"""
import argparse
import contextlib
import copy
import hashlib
import os
from pathlib import Path
import secrets
import select
import subprocess
import sys
import threading
import time

from . import canceled_continuation as planning
from .core import Refusal, canonical, digest, require
from .host_lifecycle import sync_directory
from .standard_quarantine import exclusive

KIND='continuous_connection_handoff_v1'
APPROVAL='continuous_planning_authorization_v1'
BOUNDARY={**planning.BOUNDARY,'loadAuthorized':False,'reconnectAuthorized':False,
          'planningRequiresSeparateConfirmation':True}
FIELDS={'version','kind','sourceHash','planningFile','planningPin','planningHash','planning',
        'journal','maxHoldSeconds','boundary'}


def source_hash():
    return digest([planning.old.source_hash(),hashlib.sha256(Path(__file__).read_bytes()).hexdigest()])


def location(registry,q):
    # Same original identity across versions, directories, source and endpoints.
    key=digest({'ledger':q['original']['databases']['target']['identity'],
                'commandId':q['original']['command']['id']})
    return registry.root/'continuous-connections'/key


def unclaimed(q):
    require(not os.path.lexists(q['journal']) and not os.path.lexists(q['mailbox']),
            'Consumed/partial planning attempt cannot acquire a continuous handoff; preserve it, never retry')


def valid(h):
    return (isinstance(h,dict) and set(h)==FIELDS and type(h['version']) is int and h['version']==1 and
        h['kind']==KIND and h['boundary']==BOUNDARY and planning.valid(h['planning']) and
        h['planning']['version']==2 and h['planningHash']==digest(h['planning']) and
        type(h['maxHoldSeconds']) is int and 1<=h['maxHoldSeconds']<=86400)


def current(registry,ledger,h,*,claimed=False):
    require(valid(h) and h['sourceHash']==source_hash(),'Continuous handoff source/scope changed')
    require(planning.pin(h['planningFile'])==h['planningPin'] and
        planning.read_review(h['planningFile'])==h['planning'],'Exact immutable planning review required')
    require(str(location(registry,h['planning']))==h['journal'],'Canonical connection identity changed')
    planning.current(registry,ledger,h['planning'])
    if not claimed: unclaimed(h['planning'])


def prepare(registry,ledger,review_file,max_hold_seconds=86400):
    q=planning.read_review(review_file); unclaimed(q)
    require(q['version']==2,'Explicit prospective usage review required; do not hold stale execution evidence')
    planning.current(registry,ledger,q)
    require(type(max_hold_seconds) is int and 1<=max_hold_seconds<=86400,'Explicit bounded ownership window required')
    root=location(registry,q)
    require(not os.path.lexists(root),'Continuous owner already claimed; never adopt, renew or reconnect')
    h={'version':1,'kind':KIND,'sourceHash':source_hash(),'planningFile':str(Path(review_file)),
        'planningPin':planning.pin(review_file),'planningHash':digest(q),'planning':q,
        'journal':str(root),'maxHoldSeconds':max_hold_seconds,'boundary':dict(BOUNDARY)}
    require(valid(h) and len(canonical(h).encode())<=65536,'Bounded closed continuous review required')
    return {'request':h,'reviewHash':digest(h),'validUntil':'scope_changes','boundary':dict(BOUNDARY),
        'effect':'One already-loaded-only subscription held by the original foreground process; no turn until separate exact planning confirmation'}


def backup(registry,ledger,h,destination,*,writers_stopped=False):
    require(writers_stopped is True,'Quiesce older writers before backup')
    current(registry,ledger,h)
    root=planning.old.private_path(Path(destination).parent,existing=True)/Path(destination).name
    require(not os.path.lexists(root),'New disjoint private backup required')
    root.mkdir(mode=0o700)
    result=planning.backup(registry,ledger,h['planning'],root/'planning',writers_stopped=True)
    exclusive(root/'review.json',h)
    exclusive(root/'manifest.json',{'kind':KIND,'reviewHash':digest(h),'planningBackup':result,
                                  'reviewPin':planning.pin(root/'review.json')})
    current(registry,ledger,h)
    return {'backup':str(root),'reviewHash':digest(h),'verified':True}


def verify_backup(h,root):
    root=planning.old.private_path(root,existing=True); m=planning._read_private(root/'manifest.json')
    require(set(m)=={'kind','reviewHash','planningBackup','reviewPin'} and m['kind']==KIND and
        m['reviewHash']==digest(h) and planning._read_private(root/'review.json')==h and
        planning.pin(root/'review.json')==m['reviewPin'] and
        m['planningBackup']=={'backup':str(root/'planning'),'reviewHash':h['planningHash'],'verified':True},
        'Complete exact continuous backup required')
    planning.verify_backup(h['planning'],root/'planning')


def process_identity(pid):
    require(type(pid) is int and pid>0,'Exact foreground process required')
    result=subprocess.run(['/bin/ps','-p',str(pid),'-o','pid=,lstart='],capture_output=True,text=True,timeout=5)
    require(result.returncode==0 and not result.stderr and result.stdout.strip(),'Foreground owner is unavailable; never reconnect')
    return result.stdout.strip()


def ready(h):
    require(valid(h),'Exact handoff review required'); root=Path(h['journal'])
    require(not os.path.lexists(root/'outcome.json') and not os.path.lexists(root/'stop.json'),
            'Original owner closed/stopped; never renew or reconnect')
    require(planning._read_private(root/'intent.json')=={'kind':KIND,'reviewHash':digest(h)},'Exact owner intent required')
    r=planning._read_private(root/'ready.json')
    require(planning._read_private(root/'ready-pin.json')==planning.pin(root/'ready.json'),
            'Original ready record changed; never adopt or renew')
    require(set(r)=={'reviewHash','planningHash','pid','processIdentity','nonce','subscription','openedAt'} and
        r['reviewHash']==digest(h) and r['planningHash']==h['planningHash'] and
        isinstance(r['nonce'],str) and len(r['nonce'])==64 and
        process_identity(r['pid'])==r['processIdentity'],'Original foreground owner changed')
    require(0<=time.time()-r['openedAt']<h['maxHoldSeconds'] and
        time.time()<h['planning']['original']['run']['expiresAt'],'Original ownership window/phase ended; never extend')
    return r


def planning_review(registry,ledger,h):
    current(registry,ledger,h); r=ready(h)
    a={'kind':APPROVAL,'handoffHash':digest(h),'planningHash':h['planningHash'],
       'readyPin':planning.pin(Path(h['journal'])/'ready.json'),'ownerNonce':r['nonce'],
       'sourceHash':source_hash(),'boundary':dict(BOUNDARY)}
    return {'request':a,'reviewHash':digest(a),'validUntil':'scope_changes',
        'effect':'One actual usage collection and one inert receipt/proposal turn on this same original connection; no reload, resubscribe, Resume or dispatch'}


def authorize(registry,ledger,h,approval,confirmation_hash):
    require(approval==planning_review(registry,ledger,h)['request'] and confirmation_hash==digest(approval),
            'Exact new owner-bound planning confirmation required')
    exclusive(Path(h['journal'])/'authorization.json',approval)
    return {'status':'planning_confirmation_retained','nativeActions':0,'boundary':dict(BOUNDARY)}


def stop(h,confirmation_hash):
    require(valid(h) and confirmation_hash==digest(h),'Exact continuous-owner stop review required')
    require(planning._read_private(Path(h['journal'])/'intent.json')=={'kind':KIND,'reviewHash':digest(h)},
            'Exact original owner required')
    exclusive(Path(h['journal'])/'stop.json',{'reviewHash':digest(h),'nativeCancelSent':False})
    return {'status':'stop_requested','nativeCancelSent':False}


def check_consumer(registry,q,owner):
    root=location(registry,q)
    if owner is None:
        require(not os.path.lexists(root),'Continuous ownership fences standalone planning; no fallback')
    else:
        require(isinstance(owner,Owner) and owner.registry.root==registry.root and
            owner.h['planning']==q and owner.authorized and not owner.used,
            'Exact original continuous owner and new planning approval required')
        owner.check()


class Owner:
    """Process-local connection ownership, never serializable/adoptable."""
    def __init__(self,registry,ledger,h,proxy,subscription):
        self.registry,self.ledger,self.h=registry,ledger,h
        self.proxy,self.subscription=proxy,subscription
        self.connection=proxy.process; self.used=self.authorized=self.claimed=False
        self.thread_id=threading.get_ident()
        self.opened=ready(h); self.ready_pin=planning.pin(Path(h['journal'])/'ready.json')
        self.identity=digest({'handoffHash':digest(h),'nonce':self.opened['nonce']})

    def alive(self):
        root=Path(self.h['journal'])
        require(not os.path.lexists(root/'stop.json') and not os.path.lexists(root/'outcome.json') and
            planning.pin(root/'ready.json')==self.ready_pin,'Original owner stopped or ready record changed')
        require(0<=time.time()-self.opened['openedAt']<self.h['maxHoldSeconds'] and
            time.time()<self.h['planning']['original']['run']['expiresAt'],'Original ownership window/phase ended; never extend')
        require(threading.get_ident()==self.thread_id and
            self.proxy.process is self.connection is self.subscription.connection and
            self.connection.poll() is None,'Original connection lost; never reconnect')

    def check(self):
        current(self.registry,self.ledger,self.h,claimed=self.claimed)
        r=ready(self.h)
        require(r['pid']==os.getpid() and threading.get_ident()==self.thread_id and
            self.proxy.process is self.connection is self.subscription.connection and
            self.proxy.endpoint==self.h['planning']['candidateBinding']['endpoint'] and
            self.connection.poll() is None and self.subscription.ready,'Original connection lost; never reconnect')

    def admit(self,q):
        require(self.authorized and not self.claimed and not self.used and q==self.h['planning'] and
            planning._read_private(Path(q['journal'])/'intent.json')=={'kind':q['kind'],'reviewHash':digest(q)},
            'Exact original consumer claim required before handoff')
        self.claimed=True; self.check()

    def evidence(self,q):
        require(q==self.h['planning'] and self.used,'Handoff must be consumed once')
        self.check(); first=self.subscription._sample(); second=self.subscription._sample()
        require(first==second,'Native drift during continuous handoff')
        return {**ready(self.h)['subscription'],'continuousOwner':self.identity,
                'handoffObservedAt':time.time(),'handoffSnapshotHash':digest(second)}

    @contextlib.contextmanager
    def borrow(self,q):
        require(self.authorized and self.claimed and not self.used and q==self.h['planning'],'Continuous handoff already consumed')
        self.used=True; self.check()
        exclusive(Path(self.h['journal'])/'handoff.claim.json',{'owner':self.identity,'planningHash':digest(q)})
        self.subscription._sample(); self.check()
        yield self.proxy  # Outer original owner, not the consumer, closes it.
        self.check()

    def wait(self):
        root=Path(self.h['journal']); next_check=0
        while True:
            self.alive()
            if time.monotonic()>=next_check:
                self.check(); next_check=time.monotonic()+5
            file=root/'authorization.json'
            if file.exists():
                require(planning._read_private(file)==planning_review(self.registry,self.ledger,self.h)['request'],
                        'Changed/foreign owner approval')
                self.authorized=True; return
            # Passive observation only; no telemetry or native/model keepalive.
            if self.proxy.buffer or select.select([self.connection.stdout],[],[],1)[0]:
                deadline=self.proxy.deadline
                try:
                    self.proxy.deadline=min(deadline,time.monotonic()+15); event=self.proxy._line()
                finally: self.proxy.deadline=deadline
                require(isinstance(event,dict) and 'id' not in event and
                    (event.get('method')=='account/rateLimits/updated' or
                     event.get('method')=='thread/status/changed' and event.get('params')=={
                         'threadId':self.h['planning']['original']['brainId'],'status':{'type':'idle'}}),
                        'Native event/permission or ownership drift while awaiting review; no response or cancel')


def serve(registry,ledger,h,confirmation_hash,*,writers_stopped=False,backup_root=None):
    require(valid(h) and confirmation_hash==digest(h) and writers_stopped is True and backup_root is not None,
            'Exact new handoff confirmation, quiesced writers and private backup required')
    h=copy.deepcopy(h)
    current(registry,ledger,h); verify_backup(h,backup_root); root=Path(h['journal']); outcome='unknown'; proxy=None
    with planning.partial.lock(registry.db),planning.partial.lock(ledger.db):
        current(registry,ledger,h)
        root.parent.mkdir(mode=0o700,exist_ok=True); planning.old.private_path(root.parent,existing=True)
        root.mkdir(mode=0o700); sync_directory(root.parent)
        exclusive(root/'intent.json',{'kind':KIND,'reviewHash':digest(h)})
    try:
        q=h['planning']
        with planning.Proxy(q['candidateBinding']['endpoint']) as proxy:
            require(planning.latest_original(proxy,q)==planning.latest_original(proxy,q),'Native latest turn changed')
            sub=planning.transport.Subscription(proxy,q['candidateBinding'],q['original']['brainId'],q['transport'])
            def claim(context):
                current(registry,ledger,h)
                exclusive(root/'subscription.claim.json',{'contextHash':context,'subscriptionClaimed':True})
                return {'contextHash':context,'subscriptionClaimed':True}
            attached=sub.attach(claim)
            proxy.deadline=time.monotonic()+min(h['maxHoldSeconds'],q['original']['run']['expiresAt']-time.time())
            exclusive(root/'ready.json',{'reviewHash':digest(h),'planningHash':h['planningHash'],
                'pid':os.getpid(),'processIdentity':process_identity(os.getpid()),'nonce':secrets.token_hex(32),
                'subscription':attached,'openedAt':time.time()})
            exclusive(root/'ready-pin.json',planning.pin(root/'ready.json'))
            owner=Owner(registry,ledger,h,proxy,sub); owner.wait()
            result=planning.confirm(registry,ledger,q,h['planningHash'],writers_stopped=True,
                backup_root=Path(backup_root)/'planning',_handoff=owner)
            exclusive(root/'planning-outcome.json',result); outcome=result['status']
    except (Refusal,OSError,ValueError,KeyError,TypeError,KeyboardInterrupt) as error:
        exclusive(root/'failure.json',{'errorType':type(error).__name__,'detail':str(error)[:512],'retryPermitted':False})
    closed=proxy is not None and proxy.process is None
    final={'status':outcome if closed else 'unknown','reviewHash':digest(h),'connectionClosed':closed,'boundary':dict(BOUNDARY),
           'records':{name:planning.pin(root/name) for name in ('subscription.claim.json','ready.json','ready-pin.json',
                       'authorization.json','handoff.claim.json','planning-outcome.json','failure.json','stop.json') if (root/name).exists()}}
    exclusive(root/'outcome.json',final); return final


def status(h):
    require(valid(h),'Closed continuous review required'); root=Path(h['journal'])
    if not os.path.lexists(root): return {'status':'not_submitted','boundary':dict(BOUNDARY)}
    require(planning._read_private(root/'intent.json')=={'kind':KIND,'reviewHash':digest(h)},'Partial/changed owner; never retry')
    if not (root/'outcome.json').exists(): return {'status':'claimed_current_connection_unknown','boundary':dict(BOUNDARY)}
    value=planning._read_private(root/'outcome.json')
    require(set(value)=={'status','reviewHash','connectionClosed','boundary','records'} and
        value['reviewHash']==digest(h) and value['boundary']==BOUNDARY and type(value['connectionClosed']) is bool and
        value['status'] in ('unknown','incomplete_unknown','planning_completed') and
        set(value['records'])<= {'subscription.claim.json','ready.json','ready-pin.json','authorization.json','handoff.claim.json',
                               'planning-outcome.json','failure.json','stop.json'} and
        all(planning.pin(root/name)==p for name,p in value['records'].items()),'Changed retained continuous outcome')
    if value['status']=='planning_completed':
        require(value['connectionClosed'] is True and
            {'subscription.claim.json','ready.json','ready-pin.json','authorization.json','handoff.claim.json','planning-outcome.json'}<=set(value['records']) and
            planning.status(h['planning'])==planning._read_private(root/'planning-outcome.json') and
            planning.status(h['planning'])['status']=='planning_completed','Native completion is not a retained receipt/proposal')
    return value


def assess(registry,ledger,review_file):
    """Exact file-only blockers, not a new authority review or native read."""
    q=planning.read_review(review_file)
    original=planning.original_context(registry,ledger,q['original']['bindingFile'],
        q['original']['command']['id'],disposed=True)
    require(original==q['original'],'Original rows, usage, scope or historical binding changed')
    consumed=os.path.lexists(q['journal']) or os.path.lexists(q['mailbox'])
    observed=planning.status(q)
    blockers=[]
    if consumed: blockers.append('original_planning_attempt_consumed_no_rearm')
    if q['sourceHash']!=planning.old.source_hash(): blockers.append('historical_review_implementation_not_current')
    if time.time()>=original['run']['expiresAt']: blockers.append('original_phase_expired_no_extension')
    result={'kind':'continuous_handoff_assessment_v1','planningFile':str(Path(review_file)),
        'planningPin':planning.pin(review_file),'planningHash':digest(q),'sourceHash':source_hash(),
        'originalHash':digest(original),'planningStatus':observed,'blockers':blockers,
        'executableReviewAvailable':False,'currentConnection':'unknown_not_collected',
        'boundary':dict(BOUNDARY)}
    return {**result,'assessmentHash':digest(result),'authorityGranted':False}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare'); a.add_argument('planning_review'); a.add_argument('--max-hold-seconds',type=int,default=86400)
    a=sub.add_parser('assess'); a.add_argument('planning_review')
    for name in ('backup','serve','planning-review','authorize','status','stop'):
        a=sub.add_parser(name); a.add_argument('review')
        if name=='backup': a.add_argument('destination')
        if name in ('backup','serve'): a.add_argument('--writers-stopped',action='store_true')
        if name=='serve': a.add_argument('--backup',required=True)
        if name in ('serve','authorize','stop'): a.add_argument('--confirm-hash',required=True)
        if name=='authorize': a.add_argument('approval')
    args=p.parse_args(); registry,ledger=planning.partial.routes(args.platform,args.workspace)
    if args.action=='prepare': result=prepare(registry,ledger,args.planning_review,args.max_hold_seconds)
    elif args.action=='assess': result=assess(registry,ledger,args.planning_review)
    else:
        h=planning._read_private(Path(args.review)); require(valid(h),'Closed private continuous review required')
        if args.action=='backup': result=backup(registry,ledger,h,args.destination,writers_stopped=args.writers_stopped)
        elif args.action=='serve': result=serve(registry,ledger,h,args.confirm_hash,writers_stopped=args.writers_stopped,backup_root=args.backup)
        elif args.action=='planning-review': result=planning_review(registry,ledger,h)
        elif args.action=='authorize': result=authorize(registry,ledger,h,planning._read_private(Path(args.approval)),args.confirm_hash)
        elif args.action=='stop': result=stop(h,args.confirm_hash)
        else: result=status(h)
    print(canonical(result))


if __name__=='__main__':
    # Keep the process-local Owner type canonical when invoked through -m.
    # A second __main__.Owner must never masquerade as an adoptable owner.
    from .connection_handoff import main as entrypoint
    try: entrypoint()
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
