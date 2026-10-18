"""Exact-owner, one-shot forward planning on an already-loaded native brain.

This is not Resume/dispatch or a receipt for the original Play. Its independent
journal and checkout mailbox leave the disposed ledger and binding immutable.
"""
import argparse
import contextlib
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import sys
import time

from . import canceled_play as old, no_reload_transport as transport, partial_admission as partial, standard, forward_usage
from .app_server_wake import WakeProxy, _read_binding
from .core import Refusal, canonical, digest, require
from .host_lifecycle import private_file, sync_directory
from .native_project_assignment import _read_registry
from .native_read_client import decode
from .standard_host_inspection import _read_private, _write_once
from .standard_quarantine import exclusive
from .standard_successor import pin

KIND = 'canceled_play_forward_planning_v1'
USAGE_KIND = 'canceled_play_forward_planning_v2'
SUCCESSOR_KIND = 'same_project_forward_planning_v3'
BOUNDARY = {'originalReceiptReconstructed':False,'brainReloaded':False,'requestReplayed':False,
            'usageReset':False,'bindingChanged':False,'dispatchAuthorized':False,'resumeAuthorized':False,
            'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown','pilotAccepted':False}
FIELDS = {'version','kind','sourceHash','original','candidateFile','candidatePin','candidateBinding',
          'transport','clientHash','interpreter','package','packageEpochs','maxTokens','journal','mailbox','boundary'}
CLIENT = Path(__file__).resolve().parent.parent/'scripts/continuation_client.py'


def client_hash():
    require(CLIENT.is_file() and not CLIENT.is_symlink(),'Fixed prospective mailbox client required')
    return hashlib.sha256(CLIENT.read_bytes()).hexdigest()


def package_epochs(package):
    from .host_runtime import safe_path, stamp
    root=Path(package['root'])
    return {name:list(stamp(safe_path(root/name,directory=name in ('.','bin'))))
        for name in ('.','bin','public-runtime.json','bin/codex','source.bundle')}


def interpreter():
    from .host_runtime import stamp
    file=Path(sys.executable).resolve(strict=True)
    before=file.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_uid in (0,os.getuid()) and
        not before.st_mode & 0o022 and before.st_nlink==1 and 0<before.st_size<=100_000_000,
        'Exact owner/system non-writable interpreter required')
    with os.fdopen(os.open(file,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
        require(stamp(os.fstat(stream.fileno()))==stamp(before),'Interpreter changed')
        sha=hashlib.file_digest(stream,'sha256').hexdigest()
        require(stamp(os.fstat(stream.fileno()))==stamp(before)==stamp(file.lstat()),'Interpreter changed')
    return {'absolutePath':str(file),'epoch':list(stamp(before)),'sha256':sha,
        'ancestors':{str(p):list(stamp(p.lstat()))[:6] for p in file.parents}}


def original_context(registry, ledger, binding_file, command_id, *, disposed=False):
    from .enrollment import record_in
    with _read_registry(registry) as db: require(record_in(db) is None,'Strict enrollment is outside this control')
    with standard.read_db(ledger.db) as db:
        retained=old.retained_in(ledger,db) if old.exists_in(ledger,db) else None
        if retained:
            # retained_in validates every original row and sidecar against the
            # separately confirmed pre-disposition capture. Never bypass the
            # ordinary standard.eligible fence or reinterpret this as Resume.
            request=retained['request']; meta=ledger.get(db,'meta',1)
            run,command=request['run'],request['command']
            require(command['id']==command_id and meta['standardRun']==run and
                meta['brainId']==request['brainId'],'Exact disposed original required')
        else:
            meta,run,command=old.original_in(ledger,db,command_id)
        report=run.get('usageReport')
        row=db.execute("SELECT data FROM snapshots WHERE id=? AND kind='standard_usage'",(digest(report),)).fetchone() if report else None
        usage_hash=digest(report) if row and decode(row[0].encode())==report else None
    require(not disposed or retained is not None,'A complete separately confirmed canceled-Play disposition is required')
    file=private_file(binding_file); binding=_read_binding(file)
    scope=old.prior.binding_scope(registry,ledger,binding)
    require(digest(binding) == command['notification']['hostBindingHash'],'Preserve the original binding, never replace it')
    return {'workspaceId':ledger.workspace_id,'root':str(ledger.root),'brainId':meta['brainId'],
        'command':command,'run':run,'bindingFile':str(file),'bindingPin':pin(file),
        'bindingEpoch':old.prior.file_epoch(file),'scope':scope,'sidecars':old.sidecars(ledger),
        'dispositionHash':digest(retained) if retained else None,'usageReceiptHash':usage_hash,
        'databases':{'target':partial.database_proof(ledger.db),'registry':partial.database_proof(registry.db)}}


def locations(registry, original):
    key=digest({'ledger':original['databases']['target']['identity'],'commandId':original['command']['id']})
    journal=registry.root/'canceled-followups'/key
    checkout=Path(original['scope']['checkout'])
    mailbox=checkout/'.orchestrator-followup'/key
    require(not mailbox.is_relative_to(Path(original['root'])) and mailbox != checkout,
            'Prospective mailbox must not change the immutable old ledger sidecars')
    return journal,mailbox


def review_locations(registry,q):
    if q['version']==3:
        from .same_project_lifecycle import locations as successor_locations
        return successor_locations(registry,q['original'])
    return locations(registry,q['original'])


def budget(original, maximum, *, fresh=True):
    from .brain_memory import scope
    run=original['run']; report=run.get('usageReport') or {}
    require(type(maximum) is int and 1 <= maximum <= 100000,'Explicit bounded planning allowance required')
    require(time.time() < run['expiresAt'],'Original phase clock expired; continuation cannot extend it')
    require(report and original['usageReceiptHash']==digest(report) and report.get('runId')==run['id'] and
            report.get('scopeHash')==scope(run) and report.get('gaps') == [] and report.get('coverage') == 'observed_local' and
            type(report.get('collectedAt')) in (int,float) and
            (not fresh or 0 <= time.time()-report['collectedAt'] < 120),
            'Fresh gap-free registered-session usage measurement required; a gap is not zero or a billing total')
    total=report.get('tokens',{}).get('total_tokens'); high=run.get('usageHighWater')
    require(type(total) is int and type(high) is int and 0 <= total <= high and
            run.get('brainUsageCoverage') != 'not_observed' and type(run.get('brainObservedTokens')) is int,
            'Retained cumulative usage/high-water evidence required')
    require(maximum <= min(run['brainAllowance']-run['brainObservedTokens'],
        run['limits']['tokenBudget']-high-run['limits']['checkpointReserveTokens']),
        'Planning allowance does not fit unchanged phase/brain/reserve limits')


def prepare(registry, ledger, original_binding, command_id, candidate_file, contract, max_tokens, *, forward_usage_evidence=False):
    original=original_context(registry,ledger,original_binding,command_id,disposed=True)
    require(type(forward_usage_evidence) is bool,'Explicit prospective usage selection required')
    budget(original,max_tokens,fresh=not forward_usage_evidence)
    if forward_usage_evidence: forward_usage.baseline(original)
    candidate_file=private_file(candidate_file); candidate=_read_binding(candidate_file)
    brain=original['brainId']; previous=_read_binding(original_binding)['brains'][brain]
    transport.validate_contract(contract,candidate,brain)
    from .public_host_runtime import inspect_package
    package=inspect_package(Path(candidate['endpoint']['executable']).parent.parent)
    require(package['executableHash']==contract['executableSha256'] and
            all(package[k]==contract[k] for k in ('sourceCommit','sourceTree')),'Independently pinned public runtime package required')
    require(candidate['brains'][brain]['nativePolicy'] == previous['nativePolicy'] and
            all(candidate['brains'][brain].get(k) == previous.get(k) for k in
                ('cwd','workspaceId','projectId','catalogProjectId')),
            'New endpoint must preserve the exact brain, checkout and both project identities/policy')
    journal,mailbox=locations(registry,original)
    require(not os.path.lexists(journal) and not os.path.lexists(mailbox),'Original attempt has a permanent prospective claim')
    request={'version':2 if forward_usage_evidence else 1,'kind':USAGE_KIND if forward_usage_evidence else KIND,
        'sourceHash':old.source_hash(),'original':original,
        'candidateFile':str(candidate_file),'candidatePin':pin(candidate_file),'candidateBinding':candidate,
        'transport':contract,'clientHash':client_hash(),'interpreter':interpreter(),
        'package':package,'packageEpochs':package_epochs(package),'maxTokens':max_tokens,
        'journal':str(journal),'mailbox':str(mailbox),'boundary':dict(BOUNDARY)}
    if forward_usage_evidence: request['usageSource']=forward_usage.source(ledger)
    require(valid(request),'Closed continuation review exceeds its bound')
    return {'request':request,'reviewHash':digest(request),'validUntil':'scope_changes',
        'effect':('One actual local usage collection at confirmation; immutable baseline; ' if forward_usage_evidence else '')+
            'One new forward-planning instruction, its explicit receipt and inert proposal; no Resume or dispatch',
        'boundary':dict(BOUNDARY)}


def valid(q):
    return (isinstance(q,dict) and type(q.get('version')) is int and
        ((q['version']==1 and q.get('kind')==KIND and set(q)==FIELDS) or
         (q['version']==2 and q.get('kind')==USAGE_KIND and set(q)==FIELDS|{'usageSource'} and
          isinstance(q['usageSource'],dict) and set(q['usageSource'])==forward_usage.FIELDS) or
         (q['version']==3 and q.get('kind')==SUCCESSOR_KIND and set(q)==FIELDS|{'usageSource','lineage'} and
          isinstance(q['lineage'],dict) and
          isinstance(q['usageSource'],dict) and set(q['usageSource'])==forward_usage.FIELDS)) and
        q['boundary']==BOUNDARY and isinstance(q['original'],dict) and
        type(q['maxTokens']) is int and 1<=q['maxTokens']<=100000 and len(canonical(q).encode())<=62000)


def read_review(file):
    first=pin(file); q=decode(private_file(file).read_bytes())
    require(pin(file)==first and valid(q),'Exact private closed continuation review required')
    return q


def current(registry, ledger, q, *, started=False, usage_pin=None):
    require(valid(q) and q['sourceHash']==old.source_hash() and q['clientHash']==client_hash(),'Continuation implementation changed')
    require(q['interpreter']==interpreter(),'Prospective data-client interpreter changed')
    o=q['original']
    require(original_context(registry,ledger,o['bindingFile'],o['command']['id'],disposed=True)==o,
            'Original requests, run, usage, claims, Pause or binding changed')
    require(tuple(map(str,review_locations(registry,q)))==(q['journal'],q['mailbox']), 'Canonical attempt locations changed')
    require(pin(q['candidateFile'])==q['candidatePin'] and _read_binding(q['candidateFile'])==q['candidateBinding'],
            'Candidate binding bytes/epoch changed')
    transport.validate_contract(q['transport'],q['candidateBinding'],o['brainId'])
    from .public_host_runtime import validate_pin
    if not started: validate_pin(q['package'])
    require(package_epochs(q['package'])==q['packageEpochs'],'Reviewed native package epoch changed')
    budget(o,q['maxTokens'],fresh=not started and q['version']==1)
    if q['version'] in (2,3):
        forward_usage.baseline(o); forward_usage.check_source(ledger,q['usageSource'])
        if usage_pin is not None: forward_usage.retained(q,usage_pin,fresh=not started)
    if q['version']==3:
        from . import same_project_lifecycle
        same_project_lifecycle.check_lineage(registry,ledger,q)
        if usage_pin is not None: same_project_lifecycle.check_usage(q,usage_pin,fresh=not started)
    require(not os.path.lexists(Path(q['journal'])/'stop.json'),'Owner stop fences this new control')


def backup_files(q):
    files=[q['original']['bindingFile'],q['candidateFile']]+[
        str(Path(q['original']['root'])/p) for p in sorted(q['original']['sidecars'])]+[
        str(Path(q['original']['root'])/old.FENCE)]
    if q['version']==3: files+=list(q['lineage']['files'])
    return files


def archive_pin(file):
    before=old.prior.file_epoch(file)
    info=Path(file).lstat()
    require(info.st_nlink==1 and info.st_size<=8_000_000,'Bounded private archive without aliases required')
    with Path(file).open('rb') as stream: sha=hashlib.file_digest(stream,'sha256').hexdigest()
    require(old.prior.file_epoch(file)==before,'Archive changed during read')
    return {'sha256':sha,'epoch':before}


def backup(registry, ledger, q, destination, *, writers_stopped=False):
    require(writers_stopped is True,'Quiesce older writers before the separate backup')
    current(registry,ledger,q)
    root=Path(destination); old.private_path(root.parent,existing=True)
    require(root.is_absolute() and root.resolve()==root and not os.path.lexists(root),'New private backup required')
    root.mkdir(mode=0o700); result={}
    for key,file in (('target',ledger.db),('registry',registry.db)):
        target=root/(key+'.sqlite3'); os.close(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        with standard.read_db(file) as source,contextlib.closing(sqlite3.connect(target)) as copy:
            source.backup(copy); require(copy.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Backup integrity failed')
        require(partial.database_proof(target)['fingerprint']==q['original']['databases'][key]['fingerprint'],'Backup differs')
        with target.open('rb') as stream: os.fsync(stream.fileno())
        result[key+'.sqlite3']=old.prior.database_epoch(target)
    for i,file in enumerate(backup_files(q)):
        before=archive_pin(file); raw=private_file(file).read_bytes(); name='private-'+str(i)+'.bin'
        fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        require(archive_pin(file)==before and archive_pin(root/name)['sha256']==before['sha256'],'Original changed during backup')
        result[name]=archive_pin(root/name)
    current(registry,ledger,q)
    exclusive(root/'manifest.json',{'kind':q['kind'],'reviewHash':digest(q),'files':result})
    return {'backup':str(root),'reviewHash':digest(q),'verified':True}


def verify_backup(q, root):
    root=old.private_path(root,existing=True); m=_read_private(root/'manifest.json')
    count=len(backup_files(q))
    require(set(m)=={'kind','reviewHash','files'} and m['kind']==q['kind'] and m['reviewHash']==digest(q) and
            set(m['files'])=={'target.sqlite3','registry.sqlite3'}|{'private-'+str(i)+'.bin' for i in range(count)},
            'Complete exact backup required')
    for name,expected in m['files'].items():
        actual=old.prior.database_epoch(root/name) if name.endswith('.sqlite3') else archive_pin(root/name)
        require(actual==expected,'Backup changed')
    for key in ('target','registry'):
        proof=partial.database_proof(root/(key+'.sqlite3'))
        require(proof['fingerprint']==q['original']['databases'][key]['fingerprint'] and
                proof['identity']!=q['original']['databases'][key]['identity'],'Aliased or changed database backup')
    for i,file in enumerate(backup_files(q)):
        require(archive_pin(root/('private-'+str(i)+'.bin'))['sha256']==archive_pin(file)['sha256'],
            'Backup must preserve each actual original binding, claim and capture byte')


class Proxy(WakeProxy):
    def _rpc(self, method, params):
        require(method in {'initialize','project/read','thread/read','thread/effectivePolicy/read',
            'thread/backgroundTerminals/list','thread/turns/list',transport.METHOD,'turn/start'},'No load, cancel, discovery or permission response')
        return super()._rpc(method,params)


def latest_original(proxy, q):
    expected=q['original']['command']['notification']['nativeTurnId']
    page=proxy._rpc('thread/turns/list',{'threadId':q['original']['brainId'],'cursor':None,
        'limit':1,'sortDirection':'desc','itemsView':'notLoaded'})
    turns=page.get('data') if isinstance(page,dict) else None
    require(isinstance(turns,list) and len(turns)==1 and isinstance(turns[0],dict) and
        turns[0].get('id')==expected and turns[0].get('status')=='interrupted',
        'Exact original canceled turn must remain latest; no intervening native work')
    return digest(page)


def _mailbox(file):
    q=_read_private(Path(file)); require(set(q)=={'kind','requestHash','source','sourceHash','brainId','mailbox'} and
        q['kind']==KIND and q['sourceHash']==old.source_hash() and
        q['source']==str(Path(__file__).resolve().parent.parent) and Path(file)==Path(q['mailbox'])/'handoff.json',
        'Exact prospective checkout mailbox required')
    return q


def submit(file, operation, result=None):
    q=_mailbox(file); root=Path(q['mailbox'])
    require(operation in ('receive','proposal'),'Closed continuation data operation required')
    value={'requestHash':q['requestHash'],'operation':operation,'result':result}
    require((operation=='receive' and result is None) or
        (operation=='proposal' and isinstance(result,dict) and set(result)=={'summary','nextSteps'} and
         isinstance(result['summary'],str) and 0<len(result['summary'])<=4000 and
         isinstance(result['nextSteps'],list) and 1<=len(result['nextSteps'])<=8 and
         all(isinstance(s,str) and 0<len(s)<=1000 for s in result['nextSteps'])), 'Bounded inert proposal required')
    _write_once(root/(operation+'.request.json'),value)
    until=time.monotonic()+30
    while time.monotonic()<until:
        reply=root/(operation+'.reply.json')
        if reply.exists(): return _read_private(reply)
        time.sleep(.1)
    return {'status':'unknown_waiting_for_original_observer','requestHash':q['requestHash']}


def status(q):
    require(valid(q),'Closed continuation review required'); root=Path(q['journal'])
    if q['version']==3:
        from .same_project_lifecycle import retained_lineage
        retained_lineage(q)
    if not os.path.lexists(root): return {'status':'not_submitted','boundary':dict(BOUNDARY)}
    require(_read_private(root/'intent.json')=={'kind':q['kind'],'reviewHash':digest(q)},'Partial/changed intent; never retry')
    final=root/'outcome.json'
    if not final.exists(): return {'status':'claimed_outcome_unknown','boundary':dict(BOUNDARY)}
    result=_read_private(final)
    require(isinstance(result,dict) and set(result)=={'status','nativeOutcome','nativeTurnId',
        'newReceiptRetained','proposalRetained','reviewHash','boundary','records'} and
        result['reviewHash']==digest(q) and result['boundary']==BOUNDARY and
        result['status'] in ('planning_completed','incomplete_unknown') and
        all(type(result[k]) is bool for k in ('newReceiptRetained','proposalRetained')) and
        isinstance(result['records'],dict),'Changed continuation outcome; retain unknown')
    names={'native-ack.json','receive.json','proposal.json'}
    if q['version'] in (2,3): names|={'usage.json','usage.claim.json'}
    names.add('lifecycle.json')
    require(set(result['records'])<=names and all(pin(root/name)==value for name,value in result['records'].items()),
        'Retained prospective receipt/result changed')
    for op,key in (('receive','newReceiptRetained'),('proposal','proposalRetained')):
        require(result[key]==(op+'.json' in result['records']),'Receipt flag is not a receipt')
        if result[key]:
            value=_read_private(root/(op+'.json'))
            require(value.get('requestHash')==digest(q) and value.get('nativeTurnId')==result['nativeTurnId'] and
                value.get('boundary')==BOUNDARY,'Foreign prospective receipt')
    require(result['status']!='planning_completed' or (result['nativeOutcome']=='completed' and
        result['newReceiptRetained'] and result['proposalRetained'] and 'native-ack.json' in result['records']),
        'Native completion alone is not retained planning completion')
    if q['version'] in (2,3) and result['status']=='planning_completed':
        require({'usage.json','usage.claim.json'}<=set(result['records']),'Completed planning requires prospective usage evidence')
        forward_usage.retained(q,result['records']['usage.json'],fresh=False,active=False)
        if q['version']==3:
            from .same_project_lifecycle import check_usage
            check_usage(q,result['records']['usage.json'],fresh=False,active=False)
    return result


def stop(q, confirmation_hash):
    require(valid(q) and confirmation_hash==digest(q),'Exact owner review hash required to stop this control')
    root=Path(q['journal']); require(_read_private(root/'intent.json')=={'kind':q['kind'],'reviewHash':digest(q)},'Exact claimed control required')
    exclusive(root/'stop.json',{'kind':q['kind'],'reviewHash':digest(q),'nativeCancelSent':False})
    return {'status':'stop_requested','nativeCancelSent':False,'boundary':dict(BOUNDARY)}


def confirm(registry, ledger, q, confirmation_hash, *, writers_stopped=False, backup_root=None, _handoff=None):
    from . import connection_handoff
    def guard(**kwargs):
        current(registry,ledger,q,**kwargs)
        if _handoff is not None: _handoff.check()
    require(valid(q) and confirmation_hash==digest(q) and writers_stopped is True and backup_root is not None,
            'New exact owner confirmation, quiesced writers and verified backup required')
    if q['version']==3:
        from .same_project_lifecycle import SuccessorOwner
        require(isinstance(_handoff,SuccessorOwner),'Same-project successor requires its combined original owner; no standalone fallback')
    guard(); verify_backup(q,backup_root)
    connection_handoff.check_consumer(registry,q,_handoff)
    root,mailbox=Path(q['journal']),Path(q['mailbox'])
    with partial.lock(registry.db),partial.lock(ledger.db):
        guard()
        connection_handoff.check_consumer(registry,q,_handoff)
        root.parent.mkdir(mode=0o700,exist_ok=True); old.private_path(root.parent,existing=True)
        sync_directory(root.parent.parent); root.mkdir(mode=0o700)
        sync_directory(root.parent)
        exclusive(root/'intent.json',{'kind':q['kind'],'reviewHash':digest(q)})
    # Any error from this point permanently consumes this canonical attempt.
    outcome='unknown'; turn_id=None; received=False; proposed=False; key=secrets.token_bytes(32); usage_pin=None
    phase='local_preparation'; proxy=None; preflight_refused=False
    try:
        if _handoff is not None: _handoff.admit(q)
        if q['version'] in (2,3):
            phase='usage_collection'
            observed_usage=forward_usage.collect(ledger,q)
            usage_pin=pin(root/'usage.json')
            require(_read_private(root/'usage.json')==observed_usage,'Collected usage changed before pinning')
            guard(usage_pin=usage_pin)
        mailbox.parent.mkdir(mode=0o700,exist_ok=True); old.private_path(mailbox.parent,existing=True)
        mailbox.mkdir(mode=0o700)
        handoff={'kind':KIND,'requestHash':digest(q),'source':str(Path(__file__).resolve().parent.parent),
            'sourceHash':q['sourceHash'],'brainId':q['original']['brainId'],'mailbox':str(mailbox)}
        _write_once(mailbox/'handoff.json',handoff)
        guard(usage_pin=usage_pin)
        connection = Proxy(q['candidateBinding']['endpoint']) if _handoff is None else _handoff.borrow(q)
        with connection as proxy:
            phase='metadata_preflight'
            require(latest_original(proxy,q)==latest_original(proxy,q),'Latest native turn changed')
            def claim(context):
                nonlocal phase
                guard(usage_pin=usage_pin)
                latest_original(proxy,q)
                phase='subscription_claimed'
                exclusive(root/'subscription.claim.json',{'contextHash':context,'subscriptionClaimed':True})
                return {'contextHash':context,'subscriptionClaimed':True}
            if _handoff is None:
                sub=transport.Subscription(proxy,q['candidateBinding'],q['original']['brainId'],q['transport'])
                attached=sub.attach(claim)
            else:
                sub=_handoff.subscription
                attached=_handoff.evidence(q)
                exclusive(root/'subscription.claim.json',{'contextHash':sub.context_hash,
                    'subscriptionClaimed':False,'existingContinuousOwner':_handoff.identity})
            exclusive(root/'subscription.json',attached)
            phase='subscribed'
            guard(usage_pin=usage_pin)
            require(latest_original(proxy,q)==latest_original(proxy,q),'Latest native turn changed after subscription')
            prompt=('This is a NEW owner-reviewed forward-planning instruction, not the canceled Play, Resume, or recovery. '
                'Do not execute old instructions, change source, dispatch workers, approve permissions, or mutate old ledgers/bindings. '
                'Receive this exact prospective request with the checkout-local data helper; propose bounded next steps only. '
                'Historical effects and current terminal safety remain unknown. Original limits, usage gaps and expiry remain unchanged. '
                'Cooperative one-turn planning ceiling: '+str(q['maxTokens'])+' tokens, not a provider billing cap. '
                'Exact receipt argv: '+canonical([q['interpreter']['absolutePath'],'-B',str(CLIENT),'--handoff',str(mailbox/'handoff.json'),'receive'])+'. '
                'Then write an inert JSON object with summary and nextSteps to '+str(mailbox/'proposal-input.json')+' and use argv: '+
                canonical([q['interpreter']['absolutePath'],'-B',str(CLIENT),'--handoff',str(mailbox/'handoff.json'),'proposal',str(mailbox/'proposal-input.json')])+'. '
                'No request text is execution authority. End after retaining the proposal.')
            phase='turn_start_claimed'
            exclusive(root/'turn-start.claim.json',{'reviewHash':digest(q),'promptHash':digest(prompt)})
            sub._sample(); latest_original(proxy,q)
            guard(usage_pin=usage_pin); require(sub.ready and proxy.process is sub.connection,'Original owning connection lost')
            phase='turn_start_attempted'
            reply=proxy._rpc('turn/start',{'threadId':q['original']['brainId'],
                'input':[{'type':'text','text':prompt,'text_elements':[]}],
                'approvalPolicy':'on-request','approvalsReviewer':'user'})
            turn=reply.get('turn') or {}; turn_id=turn.get('id')
            require(isinstance(turn_id,str) and old.UUID.fullmatch(turn_id),'New exact native turn acknowledgement required')
            exclusive(root/'native-ack.json',{'reviewHash':digest(q),'turnId':turn_id,'ledgerReceipt':False})
            phase='observing_new_turn'
            def service():
                nonlocal received,proposed
                guard(started=True,usage_pin=usage_pin)
                require(proxy.process is sub.connection,'Original observer changed')
                for op in ('receive','proposal'):
                    file=mailbox/(op+'.request.json'); claimfile=root/(op+'.claim.json')
                    if not file.exists() or claimfile.exists(): continue
                    request=_read_private(file)
                    require(set(request)=={'requestHash','operation','result'} and request['requestHash']==digest(q) and request['operation']==op,
                            'Foreign/changed prospective request')
                    require(op=='receive' or received,'Receive this new instruction before proposing')
                    if op=='receive': require(request['result'] is None,'Receive has no arbitrary payload')
                    else:
                        result=request['result']
                        require(isinstance(result,dict) and set(result)=={'summary','nextSteps'} and
                            isinstance(result['summary'],str) and 0<len(result['summary'])<=4000 and
                            isinstance(result['nextSteps'],list) and 1<=len(result['nextSteps'])<=8 and
                            all(isinstance(s,str) and 0<len(s)<=1000 for s in result['nextSteps']), 'Bounded inert proposal required')
                    exclusive(claimfile,{'requestHash':digest(request),'turnId':turn_id})
                    value={'status':'received' if op=='receive' else 'proposal_retained','requestHash':digest(q),
                        'nativeTurnId':turn_id,'result':request['result'],'boundary':dict(BOUNDARY)}
                    value['seal']=hmac.new(key,canonical(value).encode(),hashlib.sha256).hexdigest()
                    exclusive(root/(op+'.json'),value); _write_once(mailbox/(op+'.reply.json'),value)
                    if op=='receive': received=True
                    else: proposed=True
            proxy._on_wait_tick=service
            proxy.deadline=time.monotonic()+q['original']['run']['expiresAt']-time.time()
            proxy.watch_connection(); early=list(getattr(proxy,'_early_requests',[])); completion=getattr(proxy,'_early_completion',None)
            for i in range(2048):
                service()
                if not early and completion and completion[:2]==(q['original']['brainId'],turn_id):
                    outcome=completion[2]; break
                row=early.pop(0) if early else proxy._line()
                require(isinstance(row,dict) and len(canonical(row).encode())<=65536,'Bounded original observer event required')
                exclusive(root/('event-'+str(i)+'.json'),{'turnId':turn_id,'row':row})
                if 'id' in row and 'method' in row:
                    outcome='native_permission_or_request_requires_separate_review'; break  # Never answer or cancel.
                params=row.get('params') or {}
                if row.get('method')=='turn/completed' and params.get('threadId')==q['original']['brainId']:
                    observed=params.get('turn') or {}; require(observed.get('id')==turn_id,'Foreign completion')
                    outcome=observed.get('status'); break
            else: outcome='event_bound_exceeded_unknown'
            guard(started=True,usage_pin=usage_pin)
    except (OSError,Refusal,ValueError,KeyError,TypeError) as error:
        preflight_refused=(phase=='metadata_preflight' and type(error) is Refusal and
            str(error)=='Already-loaded idle brain required; never reload')
        exclusive(root/'failure.json',{'errorType':type(error).__name__,'detail':str(error)[:512],
            'reviewHash':digest(q),'retryPermitted':False})
        outcome='unknown'  # Retain all claims; no reconnect, second subscribe/start or fallback.
    exclusive(root/'lifecycle.json',{'reviewHash':digest(q),'phase':phase,
        'connectionClosed':proxy is not None and proxy.process is None,
        'preflightRefusalRecorded':preflight_refused,'terminalSafety':'unknown'})
    result={'status':'planning_completed' if outcome=='completed' and received and proposed else 'incomplete_unknown',
        'nativeOutcome':outcome,'nativeTurnId':turn_id,'newReceiptRetained':received,'proposalRetained':proposed,
        'reviewHash':digest(q),'boundary':dict(BOUNDARY),'records':{
            name:pin(root/name) for name in ('native-ack.json','receive.json','proposal.json','lifecycle.json')+
                (('usage.claim.json','usage.json') if q['version'] in (2,3) else ()) if (root/name).exists()}}
    exclusive(root/'outcome.json',result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform'); p.add_argument('--workspace'); p.add_argument('--handoff')
    sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare'); a.add_argument('original_binding'); a.add_argument('command_id'); a.add_argument('candidate_binding'); a.add_argument('contract'); a.add_argument('--max-tokens',type=int,required=True)
    a.add_argument('--forward-usage-evidence',action='store_true',help='New exact review: collect once into a prospective journal, never refresh the old ledger')
    for name in ('backup','confirm','status','stop'):
        a=sub.add_parser(name); a.add_argument('review')
        if name in ('confirm','stop'): a.add_argument('--confirm-hash',required=True)
        if name=='backup': a.add_argument('destination')
        if name in ('backup','confirm'): a.add_argument('--writers-stopped',action='store_true')
        if name=='confirm': a.add_argument('--backup',required=True)
    sub.add_parser('receive'); a=sub.add_parser('proposal'); a.add_argument('result')
    args=p.parse_args()
    if args.handoff:
        require(args.action in ('receive','proposal') and not args.platform and not args.workspace,'Sandbox mailbox only')
        out=submit(args.handoff,args.action,None if args.action=='receive' else _read_private(Path(args.result)))
    else:
        require(args.platform and args.workspace,'Exact registered workspace required')
        registry,ledger=partial.routes(args.platform,args.workspace)
        if args.action=='prepare': out=prepare(registry,ledger,args.original_binding,args.command_id,args.candidate_binding,
                                               _read_private(Path(args.contract)),args.max_tokens,
                                               forward_usage_evidence=args.forward_usage_evidence)
        else:
            q=read_review(args.review)
            if args.action=='backup': out=backup(registry,ledger,q,args.destination,writers_stopped=args.writers_stopped)
            elif args.action=='confirm': out=confirm(registry,ledger,q,args.confirm_hash,writers_stopped=args.writers_stopped,backup_root=args.backup)
            elif args.action=='stop': out=stop(q,args.confirm_hash)
            else: out=status(q)
    print(canonical(out))


if __name__=='__main__':
    try: main()
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
