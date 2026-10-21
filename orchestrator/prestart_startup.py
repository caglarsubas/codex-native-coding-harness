"""One new preparation-only startup after a positively proved pre-load failure.

No readiness retry, catalog/error receipt, worker Play, recovery or binding write.
Every original database row and claim remains immutable; one canonical new
attempt owns its load/turn/receipt on the same foreground connection only.
"""
import argparse
import contextlib
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import time

from . import readiness_prestart_resolution as prior, readiness_owned as owned, standard
from . import startup_mailbox as mailbox
from .core import Refusal, canonical, digest, require
from .app_server_wake import WakeProxy, _read_binding
from .native_read_client import ReadProxy, validate_endpoint
from .host_lifecycle import private_file
from .public_pilot_inspection import load_params, exclusive
from .standard_successor import pin

KIND='prestart_startup_preparation_v1'
FENCE='prestart-startup.claim.json'
ANCHOR='prestart-startup.intent.json'
SECONDS=900
BOUNDARY={'newPreparationOnly':True,'maximumLoads':1,'maximumTurns':1,'workerLimit':0,
    'repositoryWrites':False,'privateMailboxWritesOnly':True,'playAuthorized':False,'recoveryAuthorized':False,
    'readinessAllowanceRestored':False,'originalReceiptReconstructed':False,'bindingChanged':False,
    'usageReset':False,'ownershipReleased':False,'reconnectAuthorized':False,
    'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown','pilotAccepted':False}
FIELDS={'version','kind','sourceHash','executionSource','predecessor','databases','repository','phase',
        'before','journal','mailbox','boundary'}

def location(registry,ledger):
    s=ledger.db.stat()
    return registry.root/'prestart-startups'/digest({'workspaceId':ledger.workspace_id,'ledgerIdentity':[s.st_dev,s.st_ino]})

def blocked(ledger):
    if any(os.path.lexists(ledger.root/name) for name in (FENCE,ANCHOR,'post-reboot-maintenance.claim.json')): return True
    root=getattr(ledger,'platform_root',None)
    if root:
        from types import SimpleNamespace
        return os.path.lexists(location(SimpleNamespace(root=Path(root)),ledger))
    return False

def require_open(ledger,db):
    require(not blocked(ledger),'New startup owns this target; normal writes and old controls remain fenced')
    root=getattr(ledger,'platform_root',None)
    if root:
        from types import SimpleNamespace
        require(not os.path.lexists(location(SimpleNamespace(root=Path(root)),ledger)),
            'Partial canonical startup remains fenced; no fallback or replay')

def databases(registry):
    values={'registry':prior.partial.database_proof(registry.db)}
    with prior._read_registry(registry) as db: rows=db.execute('SELECT id,root FROM workspaces ORDER BY id').fetchall()
    require(1<=len(rows)<=32,'Bounded complete registered database inventory required')
    paths={'registry':str(registry.db)}
    for row in rows:
        key='workspace:'+row['id']; path=Path(row['root'])/'ledger.sqlite3'
        paths[key]=str(path); values[key]=prior.partial.database_proof(path)
    return {k:{'path':paths[k],**v} for k,v in values.items()}

def git_view(checkout,control_root):
    checkout=Path(checkout); control_root=Path(control_root)
    require(control_root.is_relative_to(checkout) and control_root!=checkout,'Exact checkout-local control root required')
    paths=['.',':(exclude)'+str(control_root.relative_to(checkout))]
    env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_OPTIONAL_LOCKS':'0'}
    def call(*args):
        r=subprocess.run(['/usr/bin/git','--no-optional-locks','-c','core.fsmonitor=false','-c','core.untrackedCache=false',
            '-C',str(checkout),*args],env=env,capture_output=True,timeout=10)
        require(r.returncode==0 and len(r.stdout)<=1000000,'Exact bounded repository metadata required'); return r.stdout
    others=call('ls-files','--others','--exclude-standard','-z','--',*paths).split(b'\0'); untracked={}
    require(len(others)<=65,'Bounded untracked source inventory required')
    for name in filter(None,others):
        p=checkout/os.fsdecode(name); require(p.resolve()==p and p.is_file() and p.stat().st_size<=1000000,
            'Untracked source must be bounded regular files without symlinks')
        untracked[os.fsdecode(name)]=hashlib.sha256(p.read_bytes()).hexdigest()
    return {'head':call('rev-parse','HEAD').decode().strip(),
        'statusHash':hashlib.sha256(call('status','--porcelain=v1','-z','--untracked-files=all','--',*paths)).hexdigest(),
        'diffHash':hashlib.sha256(call('diff','--no-ext-diff','--no-textconv','HEAD','--binary','--',*paths)).hexdigest(),
        'untrackedHash':digest(untracked)}

def phase(ledger,max_tokens):
    require(type(max_tokens) is int and 1<=max_tokens<=100000,'Explicit bounded startup reservation required')
    with standard.read_db(ledger.db) as db:
        m=standard.missions.state_in(ledger,db)
        a=m['document']['spec']['authority']; ceiling=a['tokenBudget']; carried=None
        if ledger.get(db,'meta',1)['schemaVersion']==7:
            from .worker_phase_admission import _receipt_in
            source=_receipt_in(ledger,db)['request']['source']
            ceiling=source['phaseTokenCeiling']; carried=source['postPreparationTokens']
    require(max_tokens+a['checkpointReserveTokens']<min(ceiling,a['tokenBudget']),
        'Startup must fit inside carried/reviewed allocation; no new budget or reset')
    return {'id':'startup-preparation-'+digest({'workspace':ledger.workspace_id,'ledger':prior.old.database_identity(ledger.db)})[:16],
        'purpose':mailbox.PURPOSE,'maxTokens':max_tokens,'maximumSeconds':SECONDS,'workerLimit':0,'repositoryWrites':False,
        'carriedPostPreparationTokens':carried,'carriedPhaseCeiling':ceiling,
        'reservedStartupCharge':max_tokens,'futurePhaseCeilingBeforeActualUsage':ceiling-max_tokens,
        'usageCoverage':'new_startup_unobserved','mission':m['document']['spec']}

def valid(q):
    try:
        return isinstance(q,dict) and set(q)==FIELDS and type(q['version']) is int and q['version']==1 and \
            q['kind']==KIND and canonical(q['boundary'])==canonical(BOUNDARY) and prior.valid(q['predecessor']) and \
            set(q['phase'])=={'id','purpose','maxTokens','maximumSeconds','workerLimit','repositoryWrites',
                'carriedPostPreparationTokens','carriedPhaseCeiling','reservedStartupCharge',
                'futurePhaseCeilingBeforeActualUsage','usageCoverage','mission'} and \
            q['phase']['purpose']==mailbox.PURPOSE and q['phase']['maximumSeconds']==SECONDS and \
            q['phase']['workerLimit']==0 and q['phase']['repositoryWrites'] is False and \
            type(q['phase']['maxTokens']) is int and 1<=q['phase']['maxTokens']<=100000 and \
            set(q['executionSource'])=={'root','sourceHash','epochHash'} and \
            q['executionSource']['sourceHash']==q['sourceHash'] and \
            set(q['repository'])=={'head','statusHash','diffHash','untrackedHash'} and isinstance(q['before'],dict) and \
            isinstance(q['databases'],dict) and 2<=len(q['databases'])<=33 and \
            all(set(v)=={'path','identity','fingerprint'} for v in q['databases'].values()) and \
            len(canonical(q).encode())<=60000
    except (KeyError,TypeError): return False

def context(registry,ledger,binding_file,command,original_source,max_tokens):
    require(not blocked(ledger) and not os.path.lexists(location(registry,ledger)),
        'One canonical new startup only; consumed/partial attempts never retry')
    p=prior.context(registry,ledger,binding_file,command,original_source)
    checkout=Path(p['scope']['checkout']); root=location(registry,ledger)
    return p,checkout,root,phase(ledger,max_tokens),databases(registry),git_view(checkout,ledger.root)

def prepare(registry,ledger,binding_file,command,original_source,*,max_tokens=10000):
    p,checkout,root,spec,dbs,git=context(registry,ledger,binding_file,command,original_source,max_tokens)
    binding=_read_binding(binding_file); validate_endpoint(binding['endpoint'])
    with ReadProxy(binding['endpoint']) as proxy: before=owned.repeated(proxy,binding,p['brainId'])
    require(before['latestTurn']==p['command']['payload']['readinessStart']['before']['latestTurn'],
        'Native turn history changed since the original pre-load failure')
    require(context(registry,ledger,binding_file,command,original_source,max_tokens)==(p,checkout,root,spec,dbs,git),
        'Startup review changed during native inspection')
    q={'version':1,'kind':KIND,'sourceHash':owned.preplay.source_hash(),
        'executionSource':prior.source_proof(owned.preplay.SOURCE),'predecessor':p,'databases':dbs,
        'repository':git,'phase':spec,'before':before,'journal':str(root),
        'mailbox':str(ledger.root/('startup-preparation-'+root.name[:24])),'boundary':dict(BOUNDARY)}
    require(valid(q) and not os.path.lexists(q['mailbox']),'Bounded exact new startup review required')
    return {'request':q,'reviewHash':digest(q),'validUntil':'scope_changes','boundary':dict(BOUNDARY),
        'effect':'One NEW preparation-only phase: at most one restricted load and one receipt/proposal turn. '
                 'The old readiness remains unqualified and consumed. No catalog backfill, worker Play or recovery.'}

def read_review(file):
    file=private_file(file); before=pin(file); q=mailbox.read(file)
    require(valid(q) and pin(file)==before,'Exact private startup review required'); return q

def current(registry,ledger,q,*,claimed=False):
    require(valid(q) and q['sourceHash']==owned.preplay.source_hash() and
        q['executionSource']['root']==str(owned.preplay.SOURCE) and
        prior.source_proof(q['executionSource']['root'])==q['executionSource'],
        'New startup source changed; no historical Python execution or fallback')
    p=q['predecessor']; actual=prior.context(registry,ledger,p['bindingFile'],p['command']['id'],p['originalSource']['root'])
    require(actual==p and q['journal']==str(location(registry,ledger)) and
        q['mailbox']==str(ledger.root/('startup-preparation-'+Path(q['journal']).name[:24])) and
        canonical(q['phase'])==canonical(phase(ledger,q['phase']['maxTokens'])) and databases(registry)==q['databases'] and
        git_view(p['scope']['checkout'],ledger.root)==q['repository'],'Original scope, databases, accounting or repository changed')
    root=Path(q['journal'])
    if claimed:
        require(mailbox.read(ledger.root/FENCE)=={'kind':KIND,'reviewHash':digest(q),'journal':str(root)} and
            mailbox.read(ledger.root/ANCHOR)=={'kind':KIND,'reviewHash':digest(q),'journal':str(root)} and
            mailbox.read(root/'intent.json')=={'kind':KIND,'reviewHash':digest(q),'request':q},
            'Original new-startup owner changed; no adoption or retry')
        require(not os.path.lexists(root/'stop.json'),'Startup Stop takes priority; no cancellation or retry')
    else:
        require(not blocked(ledger) and not os.path.lexists(root) and not os.path.lexists(q['mailbox']),
            'New startup already claimed or partial; inspect, never reapply')

def backup(registry,ledger,q,destination,*,writers_stopped=False):
    require(writers_stopped is True,'Stop older writers and verify their exit before backup')
    current(registry,ledger,q); root=Path(destination)
    prior.old.private_path(root.parent,existing=True)
    protected=[registry.root,*[Path(v['path']).parent for v in q['databases'].values()],
        Path(q['executionSource']['root']),Path(q['predecessor']['originalSource']['root']),
        Path(q['predecessor']['scope']['checkout'])]
    endpoint=_read_binding(q['predecessor']['bindingFile'])['endpoint']
    for key in ('executable','socket'):
        if endpoint.get(key): protected.append(Path(endpoint[key]).parent)
    require(root.is_absolute() and root.resolve()==root and not os.path.lexists(root) and
        all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in protected),
        'New private backup disjoint from operational, native and source roots required')
    root.mkdir(mode=0o700); files={}
    for i,(key,proof) in enumerate(sorted(q['databases'].items())):
        path=root/('database-'+str(i)+'.sqlite3')
        os.close(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        with standard.read_db(proof['path']) as src,contextlib.closing(sqlite3.connect(path)) as dst:
            src.backup(dst); require(dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Backup integrity failed')
            require(dst.execute('PRAGMA journal_mode=DELETE').fetchone()[0]=='delete',
                'Self-contained backup required; never copy a live WAL')
        require(prior.partial.database_proof(path)['fingerprint']==proof['fingerprint'],'Exact logical backup required')
        with path.open('rb') as stream: os.fsync(stream.fileno())
        files[path.name]={'databaseKey':key,'pin':prior.old.database_epoch(path)}
    inputs={'review.json':canonical(q).encode(),'binding.json':private_file(q['predecessor']['bindingFile']).read_bytes()}
    for i,p in enumerate(sorted(q['predecessor']['sidecarPins'])):
        inputs['original-'+str(i)+'.json']=private_file(p).read_bytes()
    for name,raw in inputs.items():
        with os.fdopen(os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        files[name]={'pin':pin(root/name)}
    current(registry,ledger,q); exclusive(root/'manifest.json',{'kind':KIND,'reviewHash':digest(q),'files':files})
    return {'backup':str(root),'reviewHash':digest(q),'verified':True}

def verify_backup(q,root):
    root=prior.old.private_path(root,existing=True); m=mailbox.read(root/'manifest.json')
    names={'review.json','binding.json',*['original-'+str(i)+'.json' for i in range(len(q['predecessor']['sidecarPins']))],
        *['database-'+str(i)+'.sqlite3' for i in range(len(q['databases']))]}
    require(set(m)=={'kind','reviewHash','files'} and m['kind']==KIND and m['reviewHash']==digest(q) and
        set(m['files'])==names and {p.name for p in root.iterdir()}==names|{'manifest.json'},'Complete closed startup backup required')
    for name,value in m['files'].items():
        require((prior.old.database_epoch(root/name) if name.endswith('.sqlite3') else pin(root/name))==value['pin'],
            'Startup backup epoch changed')
        if name.endswith('.sqlite3'):
            proof=q['databases'][value['databaseKey']]
            require(prior.partial.database_proof(root/name)['fingerprint']==proof['fingerprint'] and
                prior.old.database_identity(root/name)!=proof['identity'],'Exact disjoint database copy required')
    require(mailbox.read(root/'review.json')==q and (root/'binding.json').read_bytes()==
        private_file(q['predecessor']['bindingFile']).read_bytes(),'Exact review/binding backup required')
    for i,p in enumerate(sorted(q['predecessor']['sidecarPins'])):
        require((root/('original-'+str(i)+'.json')).read_bytes()==private_file(p).read_bytes(),'Original sidecar backup changed')

def prompt(q,handoff):
    import shlex
    # Standalone standard-library helper; no cwd change or package import.
    command=' '.join(shlex.quote(v) for v in ['python3','-B',
        str(Path(q['executionSource']['root'])/'orchestrator'/'startup_mailbox.py'),'--handoff',str(handoff)])
    return ('NEW STARTUP PREPARATION ONLY. This is not the old readiness request, Play, recovery or permission to edit source. '
        'Keep every old request/usage/claim/binding unchanged. Do not use shared-registry/controller commands, '
        'native task tools, approvals, a socket, or any other project. Zero workers and source edits. '
        'First read this exact checkout-local handoff with '+command+' state. Stay in the reviewed checkout. '
        'Produce one inert bounded pilot proposal and acknowledge ONLY this new startupId/phaseId/purpose using '
        'the receipt/proposal schema shown by the helper. Write a private result JSON in that mailbox, then invoke '
        +command+' complete EXACT_LOCAL_RESULT_FILE once. Do not change directory/source to bypass a refusal. '
        'The planning reservation is '+str(q['phase']['maxTokens'])+' tokens, cooperative, not a provider billing cap. '
        'No model catalog or old receipt may be supplied. Stop after the new receipt/proposal; terminal safety remains unknown.')

def service(registry,ledger,q,turn_id,*,completion_pin=None):
    root=Path(q['journal']); box=Path(q['mailbox']); file=box/'request.json'
    if not os.path.lexists(file): return False
    if os.path.lexists(root/'receipt.claim.json'):
        claim=mailbox.read(root/'receipt.claim.json'); receipt=mailbox.read(root/'receipt.json')
        require(claim=={'reviewHash':digest(q),'nativeTurnId':turn_id,'requestPin':pin(file)} and
            receipt['reviewHash']==digest(q) and receipt['nativeTurnId']==turn_id and receipt['requestPin']==pin(file),
            'Partial or changed startup receipt stays consumed')
        return True
    current(registry,ledger,q,claimed=True)
    require(pin(box/'handoff.json')==mailbox.read(root/'handoff-pin.json') and
        pin(box/'turn.json')==mailbox.read(root/'turn-pin.json'),'Original startup mailbox owner changed')
    require(mailbox.state(box/'handoff.json')['nativeTurnId']==turn_id,'Only the original new startup turn may receive')
    before=pin(file); value=mailbox.read(file); h=mailbox.handoff(box/'handoff.json')
    require(completion_pin is None or before==completion_pin,'Late/replaced startup result cannot be received')
    require(set(value)=={'protocol','handoffHash','result'} and value['protocol']==mailbox.PROTOCOL and
        value['handoffHash']==digest(h),'Exact new-startup handoff result required')
    result=mailbox.validate_result(h,value['result']); require(pin(file)==before,'Startup result changed while reading')
    exclusive(root/'receipt.claim.json',{'reviewHash':digest(q),'nativeTurnId':turn_id,'requestPin':before})
    exclusive(root/'receipt.json',{'reviewHash':digest(q),'nativeTurnId':turn_id,'result':result,'requestPin':before,
        'recordedAt':time.time(),'originalReadinessReceived':False})
    exclusive(box/'reply.json',{'startupId':h['startupId'],'status':'new_startup_result_recorded',
        'receiptHash':digest(mailbox.read(root/'receipt.json')),'playAuthorized':False})
    return True

def confirm(registry,ledger,q,confirmation_hash,*,writers_stopped=False,backup_root=None):
    require(valid(q) and confirmation_hash==digest(q),'Exact NEW startup owner approval required')
    require(writers_stopped is True and backup_root is not None,'Stopped writers and verified private backups required')
    with prior.partial.lock(registry.db),prior.partial.lock(ledger.db):
        current(registry,ledger,q); verify_backup(q,backup_root)
        root=Path(q['journal']); root.parent.mkdir(mode=0o700,exist_ok=True)
        prior.old.private_path(root.parent,existing=True)
        exclusive(ledger.root/ANCHOR,{'kind':KIND,'reviewHash':digest(q),'journal':str(root)})
        exclusive(ledger.root/FENCE,{'kind':KIND,'reviewHash':digest(q),'journal':str(root)})
        root.mkdir(mode=0o700); exclusive(root/'intent.json',{'kind':KIND,'reviewHash':digest(q),'request':q})
    # No transaction holds a database lock during native I/O; original rows never change.
    proxy=None; turn_id=None; attempted=False; status='incomplete_unknown'; completed=None
    request_at_completion=None; usage_hashes=[]; usage_known=None; usage_gap=False; stage='scope_validation'
    try:
        current(registry,ledger,q,claimed=True); binding=_read_binding(q['predecessor']['bindingFile'])
        stage='connection'; proxy=WakeProxy(binding['endpoint'],timeout=15); proxy.__enter__()
        proxy.begin_readiness(SECONDS)  # shared fixed-window/reader transport, not a readiness request
        stage='native_before'; before=owned.repeated(proxy,binding,q['predecessor']['brainId']); checked=time.monotonic()
        require(before==q['before'],'Fresh new-startup native scope differs from its exact review')
        current(registry,ledger,q,claimed=True)
        load_required=before['activity']=='notLoaded'
        exclusive(root/'load.claim.json',{'reviewHash':digest(q),'loadRequired':load_required})
        require(0<=time.monotonic()-checked<=120,'Native startup load scope stale; no retry')
        if load_required:
            stage='restricted_load'
            result=proxy._rpc('thread/resume',load_params({'brainId':q['predecessor']['brainId'],
                'cwd':q['predecessor']['scope']['checkout']}))
            t=result.get('thread') if isinstance(result,dict) else None
            require(isinstance(t,dict) and t.get('id')==q['predecessor']['brainId'],'New startup load acknowledgment missing')
        stage='native_after_load'; after=owned.repeated(proxy,binding,q['predecessor']['brainId']); checked=time.monotonic()
        require(after['activity']=='idle' and after['latestTurn']==before['latestTurn'] and
            after['authenticationHash']==before['authenticationHash'],'Loaded new-startup scope changed')
        exclusive(root/'load.json',{'reviewHash':digest(q),'loadedByThisStartup':load_required,
            'observedAt':time.time(),'scope':after,'terminalSafety':'unknown'})
        current(registry,ledger,q,claimed=True)
        box=Path(q['mailbox']); box.mkdir(mode=0o700)
        h={'protocol':mailbox.PROTOCOL,'purpose':mailbox.PURPOSE,'startupId':root.name,'reviewHash':digest(q),
            'brainId':q['predecessor']['brainId'],'phase':{k:v for k,v in q['phase'].items() if k!='mission'},
            'mission':q['phase']['mission'],'source':q['executionSource']['root'],'sourceHash':q['sourceHash'],
            'mailbox':str(box),'boundary':dict(BOUNDARY)}
        exclusive(box/'handoff.json',h); exclusive(root/'handoff-pin.json',pin(box/'handoff.json'))
        def capture(row):
            nonlocal completed,request_at_completion,usage_known,usage_gap
            if not isinstance(row,dict): return
            p=row.get('params')
            if not isinstance(p,dict) or p.get('threadId')!=q['predecessor']['brainId']: return
            if row.get('method')=='turn/completed':
                completed=p.get('turn'); f=box/'request.json'
                request_at_completion=pin(f) if os.path.lexists(f) else None
            if row.get('method')=='thread/tokenUsage/updated':
                if p.get('turnId') not in (None,turn_id): usage_gap=True; return
                value=(p.get('tokenUsage') or {}).get('last')
                if not isinstance(value,dict): usage_gap=True; return
                n=value.get('totalTokens')
                if type(n) is not int or n<0 or n>1000000000: usage_gap=True; return
                if usage_known is not None and n<usage_known: usage_gap=True
                usage_known=max(usage_known or 0,n)
                if len(usage_hashes)<32: usage_hashes.append(digest(value))
                else: usage_gap=True
        proxy._on_effect_event=capture
        exclusive(root/'turn.claim.json',{'reviewHash':digest(q),'purpose':mailbox.PURPOSE})
        proxy._readiness_scope_checked_at=checked
        stage='new_turn_start'; attempted=True
        started=proxy._rpc('turn/start',{'threadId':q['predecessor']['brainId'],
            'cwd':q['predecessor']['scope']['checkout'],'input':[{'type':'text','text':prompt(q,box/'handoff.json')}]})
        turn=(started or {}).get('turn'); require(isinstance(turn,dict) and isinstance(turn.get('id'),str) and
            0<len(turn['id'])<=128,'New startup turn delivery unconfirmed; never retry')
        turn_id=turn['id']; exclusive(root/'turn.json',{'reviewHash':digest(q),'nativeTurnId':turn_id})
        exclusive(box/'turn.json',{'startupId':root.name,'reviewHash':digest(q),'nativeTurnId':turn_id})
        exclusive(root/'turn-pin.json',pin(box/'turn.json'))
        for early in getattr(proxy,'_early_requests',[]):
            if isinstance(early,dict) and 'id' in early and isinstance(early.get('method'),str):
                exclusive(root/'attention.json',{'reviewHash':digest(q),'nativeTurnId':turn_id,
                    'method':early['method'],'requestHash':digest(early),'responseSent':False})
                raise Refusal('Early native permission request; no automatic response or cancellation')
        stage='original_connection_observation'; proxy.deadline=proxy._readiness_owned_deadline
        for _ in range(100000):
            require(not os.path.lexists(root/'stop.json'),'Owner Stop fences startup; no cancellation or replay')
            if completed is not None:
                require(completed.get('id')==turn_id and completed.get('status')=='completed','New startup turn did not complete')
                if not os.path.lexists(root/'receipt.json'):
                    require(request_at_completion is not None,'New startup ended without its own receipt; preserve the gap')
                    service(registry,ledger,q,turn_id,completion_pin=request_at_completion)
                break
            service(registry,ledger,q,turn_id)
            row=proxy._line()
            require(isinstance(row,dict),'Original startup connection ended; no reconnect')
            require(not getattr(proxy,'_effect_capture_error',False),'Startup lifecycle capture incomplete; no retry')
            if 'id' in row and isinstance(row.get('method'),str):
                exclusive(root/'attention.json',{'reviewHash':digest(q),'nativeTurnId':turn_id,
                    'method':row['method'],'requestHash':digest(row),'responseSent':False})
                raise Refusal('Native attention requires separate owner handling; no automatic response')
            if row.get('method')=='thread/started' and (row.get('params') or {}).get('thread',{}).get('id')!=q['predecessor']['brainId']:
                raise Refusal('Unexpected native task; preserve uncertainty')
        else: raise Refusal('Bounded startup event count exhausted')
        current(registry,ledger,q,claimed=True)
        require(os.path.lexists(root/'receipt.json'),'New startup receipt missing')
        status='startup_preparation_completed' if usage_known is None or usage_known<=q['phase']['maxTokens'] else 'startup_budget_checkpoint'
    except (OSError,Refusal,ValueError,KeyError,TypeError,sqlite3.Error):
        status='incomplete_unknown' if attempted else 'pre_turn_stopped'
    finally:
        if proxy is not None: proxy.__exit__(None,None,None)
        # Even an uncertain/failed turn keeps its observed charge and explicit
        # missing coverage. A reservation floor is never a measured zero.
        charge=max(q['phase']['maxTokens'],usage_known or 0)
        exclusive(root/'usage.json',{'observedLastTurnTokens':usage_known,'coverage':'per_turn_not_lifetime',
            'gaps':(['startup_usage_missing_or_incomplete'] if usage_gap or usage_known is None or
                status=='incomplete_unknown' else [])+['lifetime_coverage_not_asserted'],
            'sampleHashes':usage_hashes,'chargedReservationFloor':charge,
            'carriedPhaseCeiling':q['phase']['carriedPhaseCeiling'],
            'futurePhaseCeiling':max(0,q['phase']['carriedPhaseCeiling']-charge),'oldUsageChanged':False})
        exclusive(root/'outcome.json',{'kind':KIND,'reviewHash':digest(q),'status':status,'nativeTurnId':turn_id,
            'lastStage':stage,'turnStartAttempted':attempted,'connectionClosed':True,'reconnectAllowed':False,
            'originalReadinessOutcome':'unqualified_preserved','terminalSafety':'unknown','pilotAccepted':False})
    return status_in(ledger)

def status_in(ledger,db=None):
    if not blocked(ledger): return None
    try:
        f=mailbox.read(ledger.root/FENCE); root=Path(f['journal']); intent=mailbox.read(root/'intent.json'); q=intent['request']
        require(valid(q) and intent=={'kind':KIND,'reviewHash':digest(q),'request':q} and
            f=={'kind':KIND,'reviewHash':digest(q),'journal':str(root)} and mailbox.read(ledger.root/ANCHOR)==f and
            q['predecessor']['root']==str(ledger.root),
            'Incomplete or changed new startup intent')
        require(q['journal']==str(root) and root.name==digest({'workspaceId':ledger.workspace_id,
            'ledgerIdentity':[ledger.db.stat().st_dev,ledger.db.stat().st_ino]}),
            'Canonical same-target startup required')
        platform=getattr(ledger,'platform_root',None)
        if platform:
            from types import SimpleNamespace
            require(root==location(SimpleNamespace(root=Path(platform)),ledger),'Original registry startup location required')
        # Cheap file/row-only projection: no full export, native reads or renewal
        # during dashboard polling. Full immutable checks belong at effect boundaries.
        def original(connection):
            require(ledger.get(connection,'commands',q['predecessor']['command']['id'])==q['predecessor']['command'] and
                digest(ledger.get(connection,'meta',1))==q['predecessor']['metaHash'],
                'Original request/accounting changed; preserve uncertainty')
        if db is not None: original(db)
        else:
            with standard.read_db(ledger.db) as connection: original(connection)
        out=mailbox.read(root/'outcome.json') if os.path.lexists(root/'outcome.json') else None
        if out: require(out['kind']==KIND and out['reviewHash']==digest(q),'Changed startup outcome')
        receipt=None
        if os.path.lexists(root/'receipt.json'):
            receipt=mailbox.read(root/'receipt.json'); box=Path(q['mailbox'])
            require(set(receipt)=={'reviewHash','nativeTurnId','result','requestPin','recordedAt','originalReadinessReceived'} and
                receipt['reviewHash']==digest(q) and receipt['originalReadinessReceived'] is False and
                receipt['requestPin']==pin(box/'request.json') and
                pin(box/'handoff.json')==mailbox.read(root/'handoff-pin.json') and
                pin(box/'turn.json')==mailbox.read(root/'turn-pin.json'), 'Changed separate startup receipt')
            mailbox.validate_result(mailbox.handoff(box/'handoff.json'),receipt['result'])
        if out and out['status'] in ('startup_preparation_completed','startup_budget_checkpoint'):
            require(receipt is not None,'Completed preparation lost its own receipt; preserve uncertainty')
        return {'kind':KIND,'status':out['status'] if out else 'startup_claimed_outcome_unconfirmed',
            'reviewHash':digest(q),'originalCommandId':q['predecessor']['command']['id'],
            'recordedLoadClaim':os.path.lexists(root/'load.claim.json'),
            'recordedTurnClaim':os.path.lexists(root/'turn.claim.json'),
            'newReceiptRecorded':receipt is not None,'proposal':receipt['result']['proposal'] if receipt else None,
            'recordedAt':receipt['recordedAt'] if receipt else None,
            'usage':mailbox.read(root/'usage.json') if os.path.lexists(root/'usage.json') else None,
            'originalReadinessReceived':False,'normalWritesBlocked':True,'boundary':dict(BOUNDARY)}
    except (OSError,Refusal,ValueError,KeyError,TypeError,sqlite3.Error):
        return {'kind':KIND,'status':'incomplete_or_changed','normalWritesBlocked':True,'boundary':dict(BOUNDARY)}

def stop(ledger,review_hash):
    s=status_in(ledger); require(s and s.get('reviewHash')==review_hash,'Exact current startup owner required')
    root=Path(mailbox.read(ledger.root/FENCE)['journal']); exclusive(root/'stop.json',{'reviewHash':review_hash,'nativeCancelSent':False})
    return {'status':'startup_stop_requested','nativeCancelSent':False}

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare'); a.add_argument('binding'); a.add_argument('command'); a.add_argument('original_source'); a.add_argument('--max-tokens',type=int,default=10000)
    a=sub.add_parser('backup'); a.add_argument('review'); a.add_argument('destination'); a.add_argument('--writers-stopped',action='store_true')
    a=sub.add_parser('confirm'); a.add_argument('review'); a.add_argument('--confirm-hash',required=True); a.add_argument('--backup',required=True); a.add_argument('--writers-stopped',action='store_true')
    sub.add_parser('status'); a=sub.add_parser('stop'); a.add_argument('--review-hash',required=True)
    a=p.parse_args(); registry,ledger=prior.partial.routes(a.platform,a.workspace)
    if a.action=='prepare': result=prepare(registry,ledger,a.binding,a.command,a.original_source,max_tokens=a.max_tokens)
    elif a.action=='backup': result=backup(registry,ledger,read_review(a.review),a.destination,writers_stopped=a.writers_stopped)
    elif a.action=='confirm': result=confirm(registry,ledger,read_review(a.review),a.confirm_hash,writers_stopped=a.writers_stopped,backup_root=a.backup)
    elif a.action=='stop': result=stop(ledger,a.review_hash)
    else: result=status_in(ledger) or {'status':'not_recorded'}
    print(canonical(result))

if __name__=='__main__':
    try: main()
    except (OSError,Refusal,ValueError,KeyError,TypeError,sqlite3.Error) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
