"""Prospective owner-reviewed readiness load and receipt on one connection.

This is not the inspection protocol. Its ledger/brain fence survives every
failure and every new request ID. Only a new signed readiness-start review can
create its original command; old handoffs and claims are never converted.
"""
import contextlib
import copy
import os
from pathlib import Path
import sqlite3
import time

from .core import SHA, canonical, digest, require
from . import partial_admission as partial, standard, standard_preplay as preplay
from .host_lifecycle import sync_directory
from .native_read_client import ReadProxy, validate_endpoint
from .public_pilot_inspection import exclusive, record, load_params

PROTOCOL = 'readiness_owned_load_v1'
WORKFLOW = 'codex_readiness_start'
SECONDS = 900
IMPACT = ('Load the same brain at most once, capture public-host capabilities and start one receipt-only readiness turn '
          'on that same owned connection. Preserve old requests, usage, claims and bindings. No inspection reload, '
          'Play, recovery, workers or terminal-safety assertion.')
FIELDS = {'version','protocol','commandId','workspaceId','brainId','ledgerRoot','ledgerIdentity','registryIdentity',
          'contextHash','bindingHash','sourceHash','local','before','maximumSeconds'}


def fence(ledger):
    identity = preplay._identity(ledger.db)
    return ledger.root/('readiness-owned-'+digest({'workspaceId':ledger.workspace_id,
        'brainId':_brain(ledger), 'ledgerIdentity':identity})+'.claim')


def _brain(ledger):
    with standard.read_db(ledger.db) as db: return ledger.get(db,'meta',1)['brainId']


def admitted(ledger,db):
    """After eligible: pin its validated receipt, never a generic successor."""
    from . import worker_phase_admission as admission, worker_admission_source as continuity
    record=admission._receipt_in(ledger,db)
    require(record['kind']==admission.KIND,'Only qualified post-preparation worker admission supports readiness startup')
    registry,_=partial.routes(ledger.platform_root,ledger.workspace_id)
    admission.successor.other_owners(registry,ledger,record['request']['target']['repositories'])
    path=ledger.root/continuity.FILE
    return {'recordHash':digest(record),'reviewHash':record['reviewHash'],
            'sourceHash':record['request']['sourceHash'],
            'sourceContinuityPin':admission.successor.pin(path) if os.path.lexists(path) else None}


def local(ledger, db, *, own_id=None):
    from .brain_control import stopped
    from .readiness_disposition import retired_in
    meta, mission = standard.eligible(ledger,db)
    require(meta['schemaVersion'] in (1,7) and meta.get('standardRun') is None and meta.get('controller') is None and
            not meta.get('brainHandoff') and not stopped(meta) and
            not any(ledger.all(db,t) for t in ('workers','queue','decisions','continuations')) and
            not os.path.lexists(standard.controller_file(ledger)), 'Empty unowned unstopped first-phase project required')
    lineage=admitted(ledger,db) if meta['schemaVersion']==7 else None
    commands = [c for c in ledger.all(db,'commands') if c['id'] != own_id]
    require(lineage is None or not commands, 'Admitted startup is a new first readiness request, never a retry or disposition fallback')
    require(len(commands) <= 16, 'Bounded original readiness history required')
    for c in commands:
        n = c.get('notification') or {}
        disposed = retired_in(ledger,db,c['id'])
        if not disposed: old_receipt(ledger,c)
        require(c['kind'] == standard.CATALOG_REFRESH_KIND and
                (c['status'] in ('completed','failed') or retired_in(ledger,db,c['id'])) and
                not c.get('needsBrainReceipt') and
                (not n or n.get('status') == 'accepted' and
                 n.get('nativeTurnStatus') in ('completed','failed','interrupted') and
                 n.get('nativeThreadObservation',{}).get('streamStatus') == 'closed') and
                not any(a.get('status') not in ('resolved','resolved_without_response') for a in n.get('nativeApprovals',[])),
                'Every old request must be settled or explicitly disposed; unknown delivery is not safe')
    # Revision changes from this request's durable events are not authority
    # changes. Every other meta field, including all counters, remains pinned.
    stable = copy.deepcopy(meta); stable.pop('revision',None)
    return {'metaHash':digest(stable),'missionHash':mission['documentHash'],
            'reposHash':digest(ledger.all(db,'repos')),'oldCommands':{c['id']:digest(c) for c in commands},
            **({'workerAdmission':lineage} if lineage is not None else {})}


def old_receipt(ledger,c):
    """Hash-correlate existing mailboxes without executing historical source."""
    saved = c.get('preplayReceipt') or {}
    require(c.get('status') in ('completed','failed') and isinstance(c.get('preplayReceipt'),dict),
            'Failed status alone is not a historical readiness receipt')
    h = record(preplay.path(ledger.root,c['id'],'handoff'))
    q = record(preplay.path(ledger.root,c['id'],'request'))
    r = record(preplay.path(ledger.root,c['id'],'reply'))
    require(h['commandId'] == c['id'] and h['brainId'] == c['payload']['brainId'] and
            h['workspaceId'] == ledger.workspace_id and h['ledgerIdentity'] == preplay._identity(ledger.db) and
            saved.get('requestHash') == digest(q) and saved.get('handoffHash') == digest(h) and
            saved.get('bindingHash') == h['bindingHash'] and saved.get('nativeTurnId') == c.get('notification',{}).get('nativeTurnId') and
            q.get('handoffHash') == digest(h) and q.get('result',{}).get('requestId') == c['id'] and
            r.get('requestHash') == digest(q) and r.get('status') == 'completed', 'Historical receipt correlation changed')
    if c['status'] == 'failed':
        result = q['result']
        require(result.get('operation') == 'catalog_error' and c.get('catalogError') ==
                {'code':result.get('code'),'retryable':result.get('retryable')}, 'Original catalog error receipt required')
    else:
        require(isinstance(c.get('catalogReceipt'),dict),'Original successful catalog receipt required')


def sidecars(ledger):
    from .public_preplay_host_restart import sidecars as pins, PREFIX
    from .public_host_restart import pin
    found = pins(ledger)
    found.update({p.name:pin(p,1_000_000) for p in ledger.root.iterdir() if p.name.startswith(PREFIX)})
    with standard.read_db(ledger.db) as db:
        meta=ledger.get(db,'meta',1)
        if meta.get('schemaVersion')==7:
            from . import worker_phase_admission as admission
            # Backup inventory, not an eligibility shortcut. Every caller
            # separately validates local() at its authority/effect boundary.
            saved=admission._receipt_in(ledger,db)
            registry,_=partial.routes(ledger.platform_root,ledger.workspace_id)
            require(not {'admitted-source-claim','admitted-binding'} & set(found), 'Admission backup keys cannot hide an original sidecar')
            found['admitted-source-claim']=pin(admission.successor.source_claim(registry.root,
                saved['request']['source']['workspaceId']),1_000_000)
            found['admitted-binding']=pin(saved['request']['bindingFile'],1_000_000)
    return found


def claims(ledger):
    return [p for p in ledger.root.iterdir() if p.name.startswith('readiness-owned-') and p.name.endswith('.claim')]


def retained_in(ledger,db):
    """A partial canonical intent fences replacements, even across upgrades."""
    found = claims(ledger)
    if not found: return
    require(found == [fence(ledger)],'Ambiguous readiness-owned claims; preserve and reconcile')
    claim = record(found[0]); value = ledger.get(db,'commands',claim.get('commandId'))
    require(isinstance(value,dict) and value.get('kind') == standard.CATALOG_REFRESH_KIND,
            'Partial readiness-owned intent; never create a replacement request')
    review = validate_review(value.get('payload',{}).get('readinessStart'))
    require(set(claim) == {'protocol','commandId','reviewHash','bindingHash','backup'} and
            claim['protocol'] == PROTOCOL and claim['commandId'] == review['commandId'] == value['id'] and
            claim['reviewHash'] == digest(review) and claim['bindingHash'] == review['bindingHash'] and
            review['ledgerIdentity'] == preplay._identity(ledger.db) and review['ledgerRoot'] == str(ledger.root) and
            review['brainId'] == ledger.get(db,'meta',1)['brainId'] and review['workspaceId'] == ledger.workspace_id,
            'Original readiness-owned intent changed')


def scene(proxy, binding, brain):
    """Metadata only, including honest unloaded policy/tracker unknowns."""
    from .native_auth_readiness import require_ready
    from .native_policy_evidence import reported, matches
    from .standard_native_observation import _terminals
    from .public_readiness import environment
    r = binding['brains'][brain]
    p = proxy._rpc('project/read',{'projectId':r['projectId']}).get('project')
    t = proxy._rpc('thread/read',{'threadId':brain,'includeTurns':False}).get('thread')
    require(isinstance(p,dict) and p.get('id') == r['projectId'] and p.get('roots') == [{'path':r['cwd']}] and
            isinstance(t,dict) and t.get('id') == brain and t.get('projectId') == r['projectId'] and
            t.get('cwd') == r['cwd'] and t.get('status',{}).get('type') in ('idle','notLoaded') and
            t['status'].get('activeFlags') in (None,[]), 'Exact inactive native brain and project required')
    page = proxy._rpc('thread/turns/list',{'threadId':brain,'cursor':None,'limit':1,
        'sortDirection':'desc','itemsView':'notLoaded'})
    turns = page.get('data') if isinstance(page,dict) else None
    require(isinstance(turns,list) and len(turns) <= 1 and all(isinstance(v,dict) and
            isinstance(v.get('id'),str) and v.get('status') in ('completed','failed','interrupted') for v in turns),
            'Exact latest ended turn or materialized empty brain required')
    policy = reported(proxy._rpc('thread/effectivePolicy/read',{'threadId':brain}),brain,r['cwd'])
    loaded = t['status']['type'] == 'idle'
    require(matches(policy) if loaded else policy is None, 'Current policy is unverified; no configured-policy substitution')
    terminals = _terminals(proxy,brain) if loaded else None
    require(not loaded or terminals == [], 'Complete current empty tracked terminals required')
    auth = require_ready(proxy)
    if loaded:
        env = environment(proxy,brain)
    else:
        global_mcp = proxy._rpc('mcpServerStatus/list',{'detail':'toolsAndAuthOnly'})
        require(global_mcp == {'data':[],'nextCursor':None},'Complete empty global MCP metadata required before loading')
        env = digest(global_mcp)
    require(not getattr(proxy,'_early_requests',[]), 'Native permission/input remains unresolved')
    return {'activity':t['status']['type'],'latestTurn':{'id':turns[0]['id'],'status':turns[0]['status']} if turns else None,
            'policy':policy,'trackedTerminals':terminals,'authenticationHash':auth['responseHash'],'environmentHash':env,
            'environmentScope':'thread' if loaded else 'host_global'}


def repeated(proxy,binding,brain):
    first, second = scene(proxy,binding,brain), scene(proxy,binding,brain)
    require(first == second,'Native readiness scope changed; no load or retry')
    return second


def validate_review(value):
    base={'metaHash','missionHash','reposHash','oldCommands','databaseProofs','sidecars'}
    require(isinstance(value,dict) and set(value) == FIELDS and value['version'] in (1,2) and
            type(value['version']) is int and value['protocol'] == PROTOCOL and value['maximumSeconds'] == SECONDS and
            type(value['maximumSeconds']) is int and isinstance(value['before'],dict) and
            value['before'].get('activity') in ('idle','notLoaded') and isinstance(value['local'],dict) and
            set(value['local']) == (base if value['version']==1 else base|{'workerAdmission'}),
            'Closed readiness-owned review required')
    if value['version']==2:
        lineage=value['local']['workerAdmission']
        require(isinstance(lineage,dict) and set(lineage)=={'recordHash','reviewHash','sourceHash','sourceContinuityPin'} and
                all(isinstance(lineage[k],str) and SHA.fullmatch(lineage[k]) for k in ('recordHash','reviewHash','sourceHash')) and
                value['local']['oldCommands']=={}, 'Exact complete admission-bound first readiness review required')
        pin=lineage['sourceContinuityPin']
        require(pin is None or isinstance(pin,dict) and set(pin)=={'identity','sha256'} and
                isinstance(pin['identity'],list) and len(pin['identity'])==4 and
                all(type(v) is int and v>=0 for v in pin['identity']) and
                isinstance(pin['sha256'],str) and SHA.fullmatch(pin['sha256']), 'Exact historical source qualification pin required')
    before = value['before']; latest = before.get('latestTurn')
    require(set(before) == {'activity','latestTurn','policy','trackedTerminals','authenticationHash',
                            'environmentHash','environmentScope'} and
            all(isinstance(value[k],str) and SHA.fullmatch(value[k]) for k in ('sourceHash','bindingHash','contextHash')) and
            all(isinstance(before[k],str) and SHA.fullmatch(before[k]) for k in ('authenticationHash','environmentHash')) and
            (latest is None or isinstance(latest,dict) and set(latest) == {'id','status'} and
             isinstance(latest['id'],str) and 0 < len(latest['id']) <= 128 and
             latest['status'] in ('completed','failed','interrupted')), 'Closed original readiness metadata required')
    from .native_policy_evidence import matches
    require((before['activity'] == 'notLoaded' and before['policy'] is None and before['trackedTerminals'] is None and
             before['environmentScope'] == 'host_global') or
            (before['activity'] == 'idle' and matches(before['policy']) and before['trackedTerminals'] == [] and
             before['environmentScope'] == 'thread'), 'Unloaded policy/terminals remain unknown')
    return value


def browser_request(value):
    """Carry exact file epochs as text across JavaScript's JSON number limit.

    The inner review is still the original closed authority record. Never round,
    omit or normalize its native/private pins to make a signature verify.
    """
    validate_review(value)
    return {'id':value['commandId'],'contextHash':value['contextHash'],
            'readinessStartJson':canonical(value)}


def browser_review(request):
    """Decode only the exact canonical review after outer signature validation."""
    from .native_read_client import decode
    require(isinstance(request,dict) and set(request) == {'id','contextHash','readinessStartJson'} and
            isinstance(request['readinessStartJson'],str) and 0 < len(request['readinessStartJson']) <= 30000,
            'Exact canonical readiness browser request required')
    raw = request['readinessStartJson']
    value = validate_review(decode(raw))
    require(canonical(value) == raw and request['id'] == value['commandId'] and
            request['contextHash'] == value['contextHash'], 'Readiness browser scope differs')
    return value


def prepare(registry,ledger,binding,ident):
    from .enrollment import record_in
    from .native_project_assignment import _read_registry, _registered
    from .public_native_tasks import validate_contract
    require(not claims(ledger), 'Readiness-owned allowance already claimed; never recreate it')
    brain = _brain(ledger); r = binding['brains'][brain]
    root, inspected, _, _ = _registered(registry,ledger.workspace_id)
    require(set(binding['brains']) == {brain} and root == ledger.root and inspected['brainId'] == brain and
            r['workspaceId'] == ledger.workspace_id and ledger.root.is_relative_to(Path(r['cwd'])) and
            ledger.root != Path(r['cwd']), 'Exact checkout-local standard brain required')
    validate_contract(r.get('nativeTaskBackend'),r.get('policyEvidence'))
    with _read_registry(registry) as db: require(record_in(db) is None, 'Strict enrollment fences readiness loading')
    with standard.read_db(ledger.db) as db:
        state = local(ledger,db); context = standard.projection(ledger,db)['contextHash']
        if 'workerAdmission' in state:
            from .worker_phase_admission import _receipt_in as admission_record
            require(admission_record(ledger,db)['request']['target']['bindingHash']==digest(binding),
                    'Readiness must keep the exact admitted target binding')
    proof = {'registry':partial.database_proof(registry.db),'ledger':partial.database_proof(ledger.db)}
    pins = sidecars(ledger)
    validate_endpoint(binding['endpoint'])
    with ReadProxy(binding['endpoint']) as proxy: before = repeated(proxy,binding,brain)
    with standard.read_db(ledger.db) as db: require(local(ledger,db) == state,'Local readiness scope changed')
    require(proof == {'registry':partial.database_proof(registry.db),'ledger':partial.database_proof(ledger.db)} and
            sidecars(ledger) == pins,'Private scope changed during review')
    return {'version':2 if 'workerAdmission' in state else 1,'protocol':PROTOCOL,'commandId':ident,'workspaceId':ledger.workspace_id,
            'brainId':brain,'ledgerRoot':str(ledger.root),'ledgerIdentity':preplay._identity(ledger.db),
            'registryIdentity':preplay._identity(registry.db),'contextHash':context,'bindingHash':digest(binding),
            'sourceHash':preplay.source_hash(),'local':{**state,'databaseProofs':proof,'sidecars':pins},
            'before':before,'maximumSeconds':SECONDS}


def check_review(registry,ledger,binding,value):
    validate_review(value)
    require(value['workspaceId'] == ledger.workspace_id and value['brainId'] == _brain(ledger) and
            value['ledgerRoot'] == str(ledger.root) and value['ledgerIdentity'] == preplay._identity(ledger.db) and
            value['registryIdentity'] == preplay._identity(registry.db) and value['bindingHash'] == digest(binding) and
            value['sourceHash'] == preplay.source_hash() and not claims(ledger),
            'Readiness review source, binding, identity or claim changed')
    with standard.read_db(ledger.db) as db:
        require(local(ledger,db) == {k:v for k,v in value['local'].items() if k not in ('databaseProofs','sidecars')} and
                standard.projection(ledger,db)['contextHash'] == value['contextHash'], 'Reviewed local scope changed')
    require(value['local']['databaseProofs'] == {'registry':partial.database_proof(registry.db),
            'ledger':partial.database_proof(ledger.db)} and value['local']['sidecars'] == sidecars(ledger),
            'Reviewed private state changed')
    validate_endpoint(binding['endpoint'])


def backup(registry,ledger,value):
    # Disjoint private archive, not inside either operational root. A partial
    # archive stays fenced; never overwrite it to manufacture a fresh attempt.
    parent = registry.root.parent/'readiness-owned-backups'
    parent.mkdir(mode=0o700,exist_ok=True)
    require(parent.resolve(strict=True) == parent and not parent.stat().st_mode & 0o077,'Private backup parent required')
    root = parent/digest({'ledger':value['ledgerIdentity'],'id':value['commandId']})
    root.mkdir(mode=0o700)
    pins = {}
    from .public_host_restart import pin, read_file
    for key,path in (('registry',registry.db),('ledger',ledger.db)):
        target = root/(key+'.sqlite3')
        os.close(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        with standard.read_db(path) as src, contextlib.closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            require(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok','Readiness backup integrity failed')
        require(partial.database_proof(target)['fingerprint'] == value['local']['databaseProofs'][key]['fingerprint'],
                'Readiness private backup differs')
        with target.open('rb') as stream: os.fsync(stream.fileno())
        pins[key] = pin(target,partial.MAX_DATABASE)
    for number,p in enumerate(value['local']['sidecars'].values()):
        require(pin(p['path'],1_000_000) == p,'Original claim changed during backup')
        raw,_ = read_file(p['path'],1_000_000)
        target = root/('private-'+str(number)+'.record')
        fd = os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        require(read_file(target,1_000_000)[0] == raw and pin(p['path'],1_000_000) == p,
                'Private claim backup changed')
        pins['private-'+str(number)] = pin(target,1_000_000)
    exclusive(root/'manifest.json',{'reviewHash':digest(value),'files':pins})
    return {'path':str(root/'manifest.json'),'hash':digest({'reviewHash':digest(value),'files':pins})}


def validate_backup(ledger,value,archive):
    from .public_host_restart import pin
    expected = Path(ledger.platform_root).parent/'readiness-owned-backups'/digest(
        {'ledger':value['ledgerIdentity'],'id':value['commandId']})/'manifest.json'
    require(isinstance(archive,dict) and set(archive) == {'path','hash'} and archive['path'] == str(expected),
            'Exact disjoint readiness backup location required')
    manifest = record(expected,1_000_000)
    require(set(manifest) == {'reviewHash','files'} and manifest['reviewHash'] == digest(value) and
            digest(manifest) == archive['hash'] and
            set(manifest['files']) == {'registry','ledger',*['private-'+str(i) for i in range(len(value['local']['sidecars']))]},
            'Original readiness backup manifest changed')
    for name,p in manifest['files'].items():
        require(Path(p['path']).parent == expected.parent and pin(p['path'],partial.MAX_DATABASE) == p,
                'Verified private readiness backup changed')
    return archive


def confirm(registry,ledger,binding,value):
    check_review(registry,ledger,binding,value)
    with ReadProxy(binding['endpoint']) as proxy:
        require(repeated(proxy,binding,value['brainId']) == value['before'],'Reviewed native state changed')
    archive = backup(registry,ledger,value)
    check_review(registry,ledger,binding,value)
    from .enrollment import record_in
    with registry.tx() as db:
        require(record_in(db) is None,'Strict enrollment raced readiness confirmation')
        require(partial.database_proof(registry.db) == value['local']['databaseProofs']['registry'],
                'Registry changed at readiness creation boundary')
        return standard.request_catalog_refresh(ledger,{'id':value['commandId'],'contextHash':value['contextHash']},
            readiness_start={'review':value,'backup':archive})


def authorize_in(ledger,db,start,request):
    value = validate_review(start['review'])
    require(request == {'id':value['commandId'],'contextHash':value['contextHash']} and
            value['sourceHash'] == preplay.source_hash() and value['ledgerRoot'] == str(ledger.root) and
            value['ledgerIdentity'] == preplay._identity(ledger.db) and
            partial.database_proof(ledger.db) == value['local']['databaseProofs']['ledger'] and
            local(ledger,db) == {k:v for k,v in value['local'].items() if k not in ('databaseProofs','sidecars')} and
            sidecars(ledger) == value['local']['sidecars'], 'Exact original readiness creation scope required')
    validate_backup(ledger,value,start['backup'])
    require(not claims(ledger),'Readiness-owned intent already exists; no replacement')
    exclusive(fence(ledger),{'protocol':PROTOCOL,'commandId':request['id'],'reviewHash':digest(value),
        'bindingHash':value['bindingHash'],'backup':start['backup']})


def journal(ledger,command_id,kind):
    require(kind in ('load-claim','load-ack','close'),'Closed readiness lifecycle record required')
    return ledger.root/('readiness-owned-'+digest(command_id)+'-'+kind+'.json')


def check(ledger,binding,command_id):
    registry,_ = partial.routes(ledger.platform_root,ledger.workspace_id)
    from .native_project_assignment import _read_registry
    from .enrollment import record_in
    with _read_registry(registry) as db:
        require(record_in(db) is None,'Strict enrollment raced readiness send')
    with standard.read_db(ledger.db) as db:
        c = ledger.get(db,'commands',command_id); preplay._eligible(ledger,db,c)
        value = validate_review(c['payload'].get('readinessStart'))
        require(value['commandId'] == command_id and value['bindingHash'] == digest(binding) and
                value['sourceHash'] == preplay.source_hash() and value['ledgerIdentity'] == preplay._identity(ledger.db) and
                value['ledgerRoot'] == str(ledger.root) and value['workspaceId'] == ledger.workspace_id and
                value['registryIdentity'] == preplay._identity(registry.db) and
                local(ledger,db,own_id=command_id) == {k:v for k,v in value['local'].items() if k not in ('databaseProofs','sidecars')},
                'Original readiness-owned request changed')
        claim = record(fence(ledger))
        require(claim['protocol'] == PROTOCOL and claim['commandId'] == command_id and claim['reviewHash'] == digest(value) and
                claim['bindingHash'] == digest(binding),'Exact canonical readiness claim required')
        validate_backup(ledger,value,claim['backup'])
        pins = sidecars(ledger)
        allowed = {fence(ledger).name,*[journal(ledger,command_id,k).name for k in ('load-claim','load-ack','close')],
                   *[preplay.path(ledger.root,command_id,k).name for k in
                     ('handoff','request','claim','reply','capabilities','capabilities-claim')]}
        require({k:v for k,v in pins.items() if k not in allowed} == value['local']['sidecars'],
                'Original sidecars or unrelated controls changed')
        require((c.get('notification') or {}).get('status') == 'sending','Original sending readiness required')
    validate_endpoint(binding['endpoint'])
    return value


def start(ledger,binding,command_id,proxy):
    """Called once by the existing notifier on its original owned connection."""
    value = check(ledger,binding,command_id)
    require(repeated(proxy,binding,value['brainId']) == value['before'],'Native readiness start state changed')
    native_checked_at = time.monotonic()
    require(not os.path.lexists(journal(ledger,command_id,'load-claim')),'Readiness load already consumed; no retry')
    exclusive(journal(ledger,command_id,'load-claim'),{'reviewHash':digest(value),
        'loadRequired':value['before']['activity'] == 'notLoaded'})
    # The original notifier starts this window on opening its owned connection.
    # Never move it forward after slow local validation or load preparation.
    if not hasattr(proxy, '_readiness_owned_deadline'):
        proxy._readiness_owned_deadline = time.monotonic()+SECONDS
    require(time.monotonic() < proxy._readiness_owned_deadline, 'Original readiness window ended; no retry')
    proxy.deadline = min(proxy._readiness_owned_deadline,time.monotonic()+120)
    check(ledger,binding,command_id)
    loaded = value['before']['activity'] == 'notLoaded'
    if loaded:
        r = binding['brains'][value['brainId']]
        require(0 <= time.monotonic()-native_checked_at <= 120, 'Readiness native load scope is stale; no retry')
        proxy._readiness_resume_attempted = True
        result = proxy._rpc('thread/resume',load_params({'brainId':value['brainId'],'cwd':r['cwd']}))
        t = result.get('thread') if isinstance(result,dict) else None
        require(isinstance(t,dict) and t.get('id') == value['brainId'] and t.get('projectId') == r['projectId'] and
                t.get('cwd') == r['cwd'] and t.get('turns',[]) == [],'Exact readiness-only load acknowledgment required; never retry')
    exclusive(journal(ledger,command_id,'load-ack'),{'reviewHash':digest(value),'nativeLoadMade':loaded})
    current = repeated(proxy,binding,value['brainId'])
    require(current['activity'] == 'idle' and current['trackedTerminals'] == [] and
            current['latestTurn'] == value['before']['latestTurn'], 'Loaded readiness policy/tracker/turn changed')
    check(ledger,binding,command_id)
    return {'version':1,'protocol':PROTOCOL,'reviewHash':digest(value),'nativeLoadMade':loaded,
            'maximumSeconds':SECONDS,'connection': 'original_readiness_connection','before':value['before'],
            'loaded':current,'terminalSafety':'unknown'}


def catalog_proof(command):
    """Historical validation only, no native reads, load or receipt backfill."""
    value = validate_review(command.get('payload',{}).get('readinessStart'))
    note = command.get('notification') or {}; proof = note.get('nativeReadinessLifecycle') or {}
    require(value['commandId'] == command['id'] and proof.get('protocol') == PROTOCOL and
            proof.get('reviewHash') == digest(value) and proof.get('maximumSeconds') == SECONDS and
            proof.get('connection') == 'original_readiness_connection' and proof.get('terminalSafety') == 'unknown' and
            proof.get('nativeLoadMade') is (value['before']['activity'] == 'notLoaded') and
            proof.get('loaded',{}).get('activity') == 'idle' and proof.get('loaded',{}).get('trackedTerminals') == [] and
            proof['loaded'].get('latestTurn') == value['before']['latestTurn'], 'Original readiness lifecycle proof required')
    from types import SimpleNamespace
    ledger = SimpleNamespace(root=Path(value['ledgerRoot']))
    canonical = ledger.root/('readiness-owned-'+digest({'workspaceId':value['workspaceId'],
        'brainId':value['brainId'],'ledgerIdentity':value['ledgerIdentity']})+'.claim')
    claim = record(canonical)
    h = record(preplay.path(ledger.root,command['id'],'handoff'))
    require(set(claim) == {'protocol','commandId','reviewHash','bindingHash','backup'} and
            claim['protocol'] == PROTOCOL and claim['commandId'] == command['id'] and
            claim['reviewHash'] == digest(value) and claim['bindingHash'] == value['bindingHash'] and
            h.get('version') == 3 and h.get('readinessStartHash') == digest(value) and
            h.get('bindingHash') == value['bindingHash'] and h.get('sourceHash') == value['sourceHash'] and
            h.get('ledgerIdentity') == value['ledgerIdentity'] and h.get('brainId') == value['brainId'] and
            h.get('workspaceId') == value['workspaceId'] and h.get('commandId') == command['id'] and
            note.get('preplayCatalog',{}).get('handoffHash') == digest(h),
            'Original canonical readiness claim and handoff required')
    require(set(proof) == {'version','protocol','reviewHash','nativeLoadMade','maximumSeconds','connection',
                           'before','loaded','terminalSafety'} and proof['version'] == 1 and proof['before'] == value['before'] and
            proof['loaded']['environmentScope'] == 'thread' and
            proof['loaded']['authenticationHash'] == value['before']['authenticationHash'],
            'Original loaded readiness observation changed')
    from .native_policy_evidence import matches
    require(matches(proof['loaded'].get('policy')), 'Original loaded policy must be independently reported')
    require(record(journal(ledger,command['id'],'load-claim')) ==
            {'reviewHash':digest(value),'loadRequired':value['before']['activity'] == 'notLoaded'} and
            record(journal(ledger,command['id'],'load-ack')) ==
            {'reviewHash':digest(value),'nativeLoadMade':proof['nativeLoadMade']}, 'Original load claim/acknowledgment required')
    return proof


def send_ready(ledger,binding,command_id,proxy):
    """Repeat actual state after capture, then recheck Pause and private pins."""
    value = check(ledger,binding,command_id)
    with standard.read_db(ledger.db) as db: proof = catalog_proof(ledger.get(db,'commands',command_id))
    require(repeated(proxy,binding,value['brainId']) == proof['loaded'],
            'Loaded brain, ended turn, policy or tracker changed before readiness send')
    proxy._readiness_scope_checked_at = time.monotonic()
    check(ledger,binding,command_id)
    require(time.monotonic() < proxy._readiness_owned_deadline,'Readiness connection window ended; no retry')
