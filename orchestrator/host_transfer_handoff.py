"""One new-host metadata transfer and same-connection preparation phase.

The disposed canceled Play and every earlier claim remain immutable. This is
not an old transfer/recovery retry, worker Play, cleanup or pilot acceptance.
"""
import argparse
import copy
import hashlib
import math
import os
from pathlib import Path
import stat
import subprocess
import threading
import time

from . import canceled_continuation as planning, successor_phase as phase
from . import public_identity_transfer as transfer, public_host_lifecycle as launch
from . import native_auth_readiness as authentication
from .app_server_wake import WakeProxy, _read_binding, load_binding
from .core import Refusal, canonical, digest, require
from .host_lifecycle import private_file, sync_directory
from .host_runtime import safe_path, stamp
from .native_read_client import ReadProxy, SOURCES, validate_endpoint
from .native_policy_evidence import matches, reported
from .public_host_runtime import inspect_package, PROFILE
from .standard_quarantine import exclusive

KIND=planning.TRANSFER_KIND
TRANSFER='same_project_exact_brain_transfer_v1'
BOUNDARY={**planning.BOUNDARY,'maximumDestinationLoads':1,'maximumProjectRestores':1,
    'maximumAssignments':1,'maximumSubscriptions':1,'maximumNewPreparationTurns':1,
    'sourceBrainReloaded':False,'credentialBytesRead':False,'credentialBytesCopied':False,
    'oldClaimsRearmed':False,'oldPhaseExtended':False,'workerLimit':0,'repositoryWrites':False}
TRANSFER_FIELDS={'kind','sourceFile','sourcePin','sourceBinding','destinationFile','destinationPin',
    'destinationBinding','destinationHost','authenticationHash','snapshot','archivePath','archivePin','boundary'}
HOST_FIELDS={'manifest','attempt','processRecord','pins','spec','process','home','credentialMetadata'}
OWNER_FILES={'intent.json','restore.claim.json','restore.json','load.claim.json','load.json',
    'assign.claim.json','assign.json','transfer.json','subscription.claim.json','subscription.json',
    'handoff.claim.json','planning-outcome.json','failure.json','outcome.json','stop.json'}


def forbidden(file):
    require(Path(file).name not in phase.maintenance.NON_REVIEWS,'Credential paths are not review/evidence inputs')


def read(file):
    forbidden(file)
    return planning._read_private(Path(file))


def transfer_record(q):
    forbidden(q['transferFile']); require(planning.pin(q['transferFile'])==q['transferPin'],'Exact transfer specification changed')
    t=read(q['transferFile'])
    require(isinstance(t,dict) and set(t)==TRANSFER_FIELDS and t['kind']==TRANSFER and t['boundary']==BOUNDARY and
        isinstance(t['destinationHost'],dict) and set(t['destinationHost'])==HOST_FIELDS,
        'Closed separately reviewed transfer specification required')
    for file in (t['sourceFile'],t['destinationFile'],t['archivePath'],t['destinationHost']['manifest'],
        t['destinationHost']['processRecord'],*t['destinationHost']['pins']):
        forbidden(file)
    require(Path(t['archivePath'])==Path(q['transferFile']).parent/'history.jsonl',
        'Only the exact separately retained one-brain history archive may be read')
    require(isinstance(t['authenticationHash'],str) and len(t['authenticationHash'])==64 and
        all(c in '0123456789abcdef' for c in t['authenticationHash']),'Pinned actual native authentication identity required')
    return t


def valid(q):
    return (planning.valid(q) and q['version']==5 and set(q['phase'])==phase.PHASE_FIELDS and
        q['phase']['kind']=='preparation_only' and type(q['phase']['durationHours']) is int and
        1<=q['phase']['durationHours']<=24 and type(q['phase']['workerLimit']) is int and
        q['phase']['workerLimit']==0 and q['phase']['repositoryWrites'] is False and
        q['phase']['maxTokens']==q['maxTokens'] and set(q['phaseLineage'])==phase.LINE_FIELDS and
        all(Path(p).is_absolute() and Path(p).name not in phase.maintenance.NON_REVIEWS for p in
            (q['transferFile'],q['candidateFile'],q['phaseLineage']['maintenanceFile'],*q['phaseLineage']['files'])))


def fixed(argv):
    r=subprocess.run(argv,capture_output=True,timeout=10)
    require(r.returncode==0 and not r.stderr and len(r.stdout)<=1_000_000,'Exact issued-host OS metadata unavailable')
    return r.stdout.decode().strip()


def credentials(home):
    """Metadata only; neither open nor hash the credential body."""
    path=Path(home)/'auth.json'
    if not os.path.lexists(path): return None
    info=safe_path(path)
    require(info.st_uid==os.getuid() and not info.st_mode&0o077 and info.st_nlink==1,
        'Private unaliased native credential metadata required')
    # Native managed OAuth can atomically rotate tokens without changing the
    # account. File time/inode is not identity or review expiry. Preserve private
    # owner/mode/no-alias evidence here; compare actual native account/routing
    # hashes on the original connection before EVERY new effect instead.
    return {'owner':info.st_uid,'mode':stat.S_IMODE(info.st_mode),'links':info.st_nlink,
        'store':'native_managed_file','bytesRead':False,'copied':False}


def destination_host(manifest,attempt,process_record,binding):
    """Validate a previously issued public launch, never launch or discover one.

    Its immutable original process record supplies birth identity. The native
    launch intent/exec/status and independent OS/native identity remain distinct
    cooperative local evidence, not vendor attestation or terminal cleanup.
    """
    for file in (manifest,process_record): forbidden(file)
    spec=read(manifest); attempt=launch.isolated_directory(attempt)
    require(set(spec)==launch.FIELDS and spec['profile']==PROFILE and type(spec['schemaVersion']) is int and spec['schemaVersion']==1 and
        spec['nativePolicy']==launch.POLICY and spec['credentialMode']=='unconfigured',
        'Original public empty-home launch specification required; sign-in is a later separate fact')
    issued=read(attempt/'launch.json'); state=launch.status(attempt); record=read(process_record)
    require(set(issued)=={'spec','manifestHash','reviewHash','mode','createdAt'} and
        issued['spec']==spec and issued['manifestHash']==digest(spec) and issued['reviewHash']==launch.review_hash(spec) and
        issued['mode']=='exec' and private_file(attempt/'exec.claim').stat().st_size==0 and
        state['status']=='exec_boundary_issued' and record.get('pid')==state['pid'] and
        record.get('parentPid')==state['parentPid'] and isinstance(record.get('processIdentity'),str) and
        isinstance(record.get('manifestPin'),dict) and record['manifestPin'].get('sha256')==planning.pin(manifest)['sha256'],
        'Original issued exec and pinned process-birth record required; intent alone is not a host')
    package=inspect_package(spec['runtimePackage']['root'])
    require(package==spec['runtimePackage'] and binding['endpoint']['executable']==str(Path(package['root'])/'bin/codex') and
        binding['endpoint']['sha256']==package['executableHash'],'Exact issued native package required')
    binary=binding['endpoint']['executable']; pid=state['pid']; alias=Path(spec['socketDirectory'])/'host.sock'
    validate_endpoint(binding['endpoint'])
    for _ in range(2):
        require(fixed(['/bin/ps','-p',str(pid),'-o','pid=,lstart='])==record['processIdentity'] and
            fixed(['/bin/ps','-p',str(pid),'-o','ppid='])==str(state['parentPid']) and
            fixed(['/bin/ps','-ww','-p',str(pid),'-o','command='])==binary+' app-server --listen unix://'+str(alias),
            'Original issued PID/birth/parent/argv changed')
        require(alias.is_symlink() and alias.lstat().st_uid==os.getuid() and
            str(alias.resolve(strict=True))==binding['endpoint']['socket'],'Exact native socket alias/target required')
        opened=fixed(['/usr/sbin/lsof','-nP','-a','-p',str(pid),'-d','cwd,txt','-Fn'])
        unix=fixed(['/usr/sbin/lsof','-nP','-a','-p',str(pid),'-U','-Fn'])
        require('n'+binary in opened.splitlines() and 'n'+spec['cwd'] in opened.splitlines() and
            any(line=='n'+binding['endpoint']['socket'] or line.startswith('n'+binding['endpoint']['socket']+' ')
                for line in unix.splitlines()),'Issued process must own this exact executable/cwd/socket')
    for key,identity in (('cwd','cwdIdentity'),('codexHome','homeIdentity'),('socketDirectory','socketDirectoryIdentity')):
        require(launch.directory_identity(spec[key])==spec[identity],'Issued directory identity changed')
    home=launch.isolated_directory(spec['codexHome'])
    require(home!=Path.home()/'.codex' and launch.file_record(home,'config.toml',65536)==spec['configPin'] and
        (home/'config.toml').read_bytes()==launch.CONFIG.encode(),'Exact isolated restricted native configuration required')
    require(all(not os.path.lexists(home/name) for name in ('plugins','hooks','managed-config.toml','.credentials.json')),
        'No inherited capabilities/credential store or managed overlay')
    files=[Path(manifest),attempt/'launch.json',attempt/'exec.claim',attempt/'status.json',Path(process_record)]
    return {'manifest':str(manifest),'attempt':str(attempt),'processRecord':str(process_record),
        'pins':{str(p):planning.pin(p) for p in files},'spec':spec,
        'process':{'pid':pid,'parentPid':state['parentPid'],'processIdentity':record['processIdentity']},
        'home':str(home),'credentialMetadata':credentials(home)}


class SourceProxy(ReadProxy):
    def __init__(self,binding,brain):
        super().__init__(binding['endpoint']); self.record=binding['brains'][brain]; self.brain=brain
    def _rpc(self,method,params):
        self.deadline=time.monotonic()+15
        require(method=='initialize' or method=='project/read' and params=={'projectId':self.record['projectId']} or
            method=='thread/read' and params=={'threadId':self.brain,'includeTurns':True},
            'Only the exact source brain/project may be read; no source load, write or discovery')
        result=super()._rpc(method,params)
        if method=='initialize': self.initialization=copy.deepcopy(result)
        return result


class DestinationProxy(WakeProxy):
    request_limit=32000
    def __init__(self,q):
        self.q=q; self.permit=None; self.turn_attempted=False
        super().__init__(q['candidateBinding']['endpoint'])
    def allow(self,method,params):
        require(self.permit is None and method in ('project/restoreMetadata','thread/resume','thread/metadata/update'),
            'One claimed metadata stage at a time')
        self.permit=(method,digest(params))
    def _rpc(self,method,params):
        self.deadline=time.monotonic()+15
        brain=self.q['original']['brainId']; bound=self.q['candidateBinding']['brains'][brain]
        if method in ('project/restoreMetadata','thread/resume','thread/metadata/update'):
            require(self.permit==(method,digest(params)),'Exact pre-claimed metadata stage required')
            self.permit=None  # Before uncertain native delivery; never resend.
        elif method=='turn/start':
            root=Path(self.q['journal']); claim=read(root/'turn-start.claim.json')
            require(not self.turn_attempted and set(params)=={'threadId','input','approvalPolicy','approvalsReviewer'} and
                params['threadId']==brain and params['approvalPolicy']=='on-request' and params['approvalsReviewer']=='user' and
                len(params['input'])==1 and params['input'][0].get('type')=='text' and
                claim=={'reviewHash':digest(self.q),'promptHash':digest(params['input'][0]['text'])},
                'Only the existing newly claimed preparation sender may start one turn')
            self.turn_attempted=True
        else:
            allowed={
                'initialize':None,'account/read':[{'refreshToken':False}],
                'mcpServerStatus/list':[{'detail':'toolsAndAuthOnly'}],
                'project/list':[{'limit':100}], 'project/read':[{'projectId':bound['projectId']}],
                'thread/loaded/list':[{'cursor':None,'limit':64}],
                'thread/list':[{'limit':100,'archived':a,'sourceKinds':SOURCES} for a in (False,True)],
                'thread/read':[{'threadId':brain,'includeTurns':turns} for turns in (False,True)],
                'thread/effectivePolicy/read':[{'threadId':brain}],
                'thread/turns/list':[{'threadId':brain,'cursor':None,'limit':1,'sortDirection':'desc','itemsView':'notLoaded'}],
                'thread/backgroundTerminals/list':[{'threadId':brain,'cursor':None,'limit':64}],
                planning.transport.METHOD:[{'threadId':brain}]}
            require(method in allowed and (method=='initialize' or params in allowed[method]),
                'No login, refresh, cancellation, permission response, other load or native task creation')
        result=super()._rpc(method,params)
        if method=='initialize': self.initialization=copy.deepcopy(result)
        return result


def empty_destination(proxy,t):
    host=t['destinationHost']; home=host['home']
    require(proxy.initialization['codexHome']==home and home!=t['snapshot']['sourceHome'],
        'Exact disjoint destination native home required')
    auth=authentication.require_ready(proxy)
    require(not auth['requiresOpenaiAuth'] or host['credentialMetadata'] is not None,
        'Managed native sign-in must already exist; this control never logs in')
    for method,params in [('project/list',{'limit':100}),('thread/loaded/list',{'cursor':None,'limit':64}),
        ('mcpServerStatus/list',{'detail':'toolsAndAuthOnly'}),
        *[('thread/list',{'limit':100,'archived':a,'sourceKinds':SOURCES}) for a in (False,True)]]:
        value=proxy._rpc(method,params)
        require(isinstance(value,dict) and value.get('data')==[] and value.get('nextCursor') is None and
            set(value)<={'data','nextCursor','backwardsCursor'} and value.get('backwardsCursor') is None,
            'Complete empty destination catalogs/tracker required; missing pages are unknown')
    return auth


def check_authentication(proxy,q):
    t=transfer_record(q); auth=authentication.require_ready(proxy)
    require(auth['responseHash']==t['authenticationHash'],'Native account or routing changed; no effect/retry')
    return auth


def source_snapshot(proxy,q):
    t=transfer_record(q); brain=q['original']['brainId']; bound=t['sourceBinding']['brains'][brain]
    snapshot,raw=transfer.source_snapshot(proxy,{'brainId':brain,'projectId':bound['projectId'],'cwd':bound['cwd']})
    require(snapshot==t['snapshot'] and snapshot['latestTurnId']==q['original']['command']['notification']['nativeTurnId'] and
        snapshot['latestTurnStatus']=='interrupted','Exact unchanged source history/latest canceled turn required')
    return raw


def prepare(registry,ledger,maintenance_file,destination_file,manifest,attempt,process_record,directory,
        *,maintenance_source=None,duration_hours=24,max_tokens=10000):
    line,parent,prior=phase.historical(registry,ledger,maintenance_file,maintenance_source)
    require(time.time()>=parent['original']['run']['expiresAt'],'New phase cannot extend an unexpired predecessor')
    journal,mailbox,root=phase.locations(registry,parent['original'])
    require(not os.path.lexists(root.parent) and not os.path.lexists(mailbox),'A phase/transfer owner already consumed this lineage')
    source=load_binding(parent['candidateFile']); destination=load_binding(destination_file); brain=parent['original']['brainId']
    require(source==parent['candidateBinding'] and set(source['brains'])==set(destination['brains'])=={brain} and
        all(source['brains'][brain].get(k)==destination['brains'][brain].get(k) for k in transfer.IDENTITY_FIELDS) and
        source['endpoint']!=destination['endpoint'],'Same single brain/dual IDs/policy and a different reviewed host required')
    backend=destination['brains'][brain].get('nativeTaskBackend')
    transfer.validate_contract(destination['brains'][brain].get('identityTransferEvidence'),backend)
    package=inspect_package(Path(destination['endpoint']['executable']).parent.parent)
    contract={'protocol':planning.transport.PROTOCOL,'method':planning.transport.METHOD,
        'sourceCommit':package['sourceCommit'],'sourceTree':package['sourceTree'],'executableSha256':package['executableHash']}
    planning.transport.validate_contract(contract,destination,brain)
    host=destination_host(manifest,attempt,process_record,destination)
    require(host['spec']['cwd']==parent['original']['scope']['checkout'] and host['spec']['runtimePackage']==package,
        'Issued host must retain the exact original checkout and reviewed package')
    with SourceProxy(source,brain) as proxy:
        scope={'brainId':brain,'projectId':source['brains'][brain]['projectId'],'cwd':source['brains'][brain]['cwd']}
        first,raw=transfer.source_snapshot(proxy,scope); second,_=transfer.source_snapshot(proxy,scope)
    require(first==second and first['latestTurnId']==parent['original']['command']['notification']['nativeTurnId'] and
        first['latestTurnStatus']=='interrupted' and first['sourceHome']!=host['home'],
        'Repeated original canceled-turn history and disjoint native home required')
    q=copy.deepcopy(parent); q.update(version=5,kind=KIND,sourceHash=planning.old.source_hash(),clientHash=planning.client_hash(),
        candidateFile=str(destination_file),candidatePin=planning.pin(destination_file),candidateBinding=destination,
        transport=contract,interpreter=planning.interpreter(),package=package,packageEpochs=planning.package_epochs(package),
        maxTokens=max_tokens,journal=str(journal),mailbox=str(mailbox),phaseLineage=line,
        phase=phase.phase_spec(parent,prior,duration_hours,max_tokens))
    directory=Path(directory); planning.old.private_path(directory.parent,existing=True)
    require(directory.is_absolute() and directory.resolve()==directory and not os.path.lexists(directory) and
        all(not directory.is_relative_to(p) and not p.is_relative_to(directory) for p in
            (registry.root,ledger.root,Path(first['sourceHome']),Path(host['home']),Path(scope['cwd']),Path(package['root']))),
        'New disjoint owner-private transfer review directory required')
    directory.mkdir(mode=0o700); sync_directory(directory.parent)
    archive=directory/'history.jsonl'
    with os.fdopen(os.open(archive,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400),'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    t={'kind':TRANSFER,'sourceFile':parent['candidateFile'],'sourcePin':parent['candidatePin'],'sourceBinding':source,
        'destinationFile':str(destination_file),'destinationPin':planning.pin(destination_file),'destinationBinding':destination,
        'destinationHost':host,'authenticationHash':None,'snapshot':first,'archivePath':str(archive),
        'archivePin':transfer.archive_pin(archive),'boundary':dict(BOUNDARY)}
    with DestinationProxy(q) as proxy:
        auth=empty_destination(proxy,t)
    t['authenticationHash']=auth['responseHash']
    exclusive(directory/'transfer.json',t)
    q.update(transferFile=str(directory/'transfer.json'),transferPin=planning.pin(directory/'transfer.json'))
    require(valid(q),'Bounded closed transfer/preparation review required')
    current(registry,ledger,q)
    exclusive(directory/'request.json',q)
    return {'request':q,'reviewHash':digest(q),'validUntil':'scope_changes','boundary':dict(BOUNDARY),
        'effect':'One exact project/brain history transfer, one restricted destination load/assignment/subscription and one NEW preparation receipt/proposal on that same foreground connection; no old-request replay or binding installation'}


def retained_transfer(q):
    require(valid(q),'Closed new-host phase required'); t=transfer_record(q)
    require(transfer.archive_pin(t['archivePath'])==t['archivePin'] and
        t['snapshot']['rollout']['sha256']==t['archivePin']['sha256'] and
        t['destinationFile']==q['candidateFile'] and t['destinationPin']==q['candidatePin'] and
        t['destinationBinding']==q['candidateBinding'],'Pinned exact one-brain archive/destination changed')
    return t


def retained_lineage(q):
    require(valid(q),'Closed transfer phase required'); t=retained_transfer(q); line=q['phaseLineage']
    m=phase.maintenance.read_review(line['maintenanceFile'])
    require(planning.pin(line['maintenanceFile'])==line['maintenancePin'] and digest(m)==line['maintenanceHash'] and
        phase.maintenance.status(m)['status']=='maintenance_load_observed_idle' and
        all(planning.pin(p)==pin for p,pin in line['files'].items()),'Original positive maintenance/claims changed')
    proof=line['maintenanceSourceProof']
    if proof is not None:
        require(phase.lifecycle.source_proof(proof['root'])==proof and proof['sourceHash']==phase.MAINTENANCE_SOURCE,
            'Exact qualified historical maintenance source required')
    return t


def phase_clock(q,*,active=True):
    require(valid(q),'Closed transfer phase required'); row=read(phase.owner_root(q)/'intent.json'); clock=row.get('phaseClock')
    require(set(row)=={'kind','reviewHash','phaseClock'} and row['kind']==KIND and row['reviewHash']==digest(q) and
        isinstance(clock,dict) and set(clock)=={'phaseId','startedAt','expiresAt','durationHours'} and
        clock['phaseId']==q['phase']['id'] and clock['durationHours']==q['phase']['durationHours'] and
        all(type(clock[k]) in (int,float) and math.isfinite(clock[k]) for k in ('startedAt','expiresAt')) and
        clock['expiresAt']==clock['startedAt']+clock['durationHours']*3600 and
        (not active or clock['startedAt']<=time.time()<clock['expiresAt']),
        'Original new-phase clock/intent changed or expired; never renew')
    return clock


def current(registry,ledger,q,*,started=False,usage_pin=None):
    require(valid(q) and q['sourceHash']==planning.old.source_hash() and q['clientHash']==planning.client_hash() and
        q['interpreter']==planning.interpreter(),'Exact transfer source/client/interpreter required')
    t=retained_transfer(q); line=q['phaseLineage']; proof=line['maintenanceSourceProof']
    actual,parent,prior=phase.historical(registry,ledger,line['maintenanceFile'],None if proof is None else proof['root'])
    require(actual==line and q['original']==parent['original'] and q['usageSource']==parent['usageSource'] and
        t['sourceFile']==parent['candidateFile'] and t['sourcePin']==parent['candidatePin'] and
        t['sourceBinding']==parent['candidateBinding'] and q['phase']==phase.phase_spec(parent,prior,q['phase']['durationHours'],q['maxTokens']),
        'Preserve exact source lineage, old usage and claims; no migration of an old attempt')
    require(time.time()>=q['original']['run']['expiresAt'] and
        tuple(map(str,phase.locations(registry,q['original'])[:2]))==(q['journal'],q['mailbox']),
        'Original expiry and canonical new-phase identity required')
    require(planning.pin(q['candidateFile'])==q['candidatePin'] and load_binding(q['candidateFile'])==q['candidateBinding'] and
        inspect_package(q['package']['root'])==q['package'] and planning.package_epochs(q['package'])==q['packageEpochs'],
        'Exact new endpoint/package/binding changed')
    planning.transport.validate_contract(q['transport'],q['candidateBinding'],q['original']['brainId'])
    host=t['destinationHost']
    require(destination_host(host['manifest'],host['attempt'],host['processRecord'],q['candidateBinding'])==host,
        'Original issued destination process/config/auth metadata changed')
    require(transfer.rollout(t['snapshot']['rollout']['path'],t['snapshot']['sourceHome'],q['original']['brainId'],
        q['original']['scope']['checkout'])[1]==t['snapshot']['rollout'],'Original source history bytes/epoch changed')
    planning.forward_usage.check_source(ledger,q['usageSource'])
    root=phase.owner_root(q)
    require(not os.path.lexists(root/'stop.json') and not os.path.lexists(Path(q['journal'])/'stop.json'),
        'Owner Stop fences transfer and preparation without native cancellation')
    require(not os.path.lexists(transfer.fence_path(ledger,{'runId':q['original']['run']['id'],
        'originalPlayId':q['original']['command']['id']})),'An original identity-transfer claim cannot be retried here')
    if root.parent.exists(): phase_clock(q)
    if usage_pin is not None: check_usage(q,usage_pin,fresh=not started)


def check_usage(q,pin,*,fresh,active=True):
    phase.check_usage(q,pin,fresh=fresh,active=False)
    if active: phase_clock(q)


def backup_files(q):
    t=retained_transfer(q)
    files=set(phase.lineage_files(q))|{q['transferFile'],q['candidateFile'],t['sourceFile']}|set(t['destinationHost']['pins'])
    require(len(files)<=256 and all(Path(p).name not in phase.maintenance.NON_REVIEWS for p in files),'Bounded non-credential backup inventory required')
    return sorted(files)


def backup_destination(registry,q,root):
    phase.backup_destination(registry,q,root); t=retained_transfer(q)
    for p in (Path(t['destinationHost']['home']),Path(t['snapshot']['sourceHome']),Path(q['transferFile']).parent):
        require(not root.is_relative_to(p) and not p.is_relative_to(root),'Transfer backup must be disjoint from both native homes and review archive')


def backup_history(q,root):
    t=retained_transfer(q); target=Path(root)/'history.jsonl'
    with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o400),'wb') as stream:
        stream.write(transfer.read_archive(t['archivePath'])); stream.flush(); os.fsync(stream.fileno())
    exclusive(Path(root)/'transfer-history.json',{'reviewHash':digest(q),'archivePin':transfer.archive_pin(target)})


def verify_backup_history(q,root):
    t=retained_transfer(q); value=read(Path(root)/'transfer-history.json')
    require(set(value)=={'reviewHash','archivePin'} and value['reviewHash']==digest(q) and
        transfer.archive_pin(Path(root)/'history.jsonl')==value['archivePin'] and
        value['archivePin']['sha256']==t['archivePin']['sha256'],'Complete private immutable history backup required')


class TransferOwner(phase.PhaseOwner):
    """Only the process which loaded/assigned/subscribed may lend this pipe."""
    def check(self):
        super().check(); q=self.h['planning']; row=read(self.root/'transfer.json')
        require(row['reviewHash']==digest(q) and row['status']=='metadata_transferred' and
            row['historySha256']==transfer_record(q)['archivePin']['sha256'],'Exact positively retained transfer required before preparation')


def copy_history(q,t):
    root=Path(t['destinationHost']['home'])/'sessions'; root.mkdir(mode=0o700,exist_ok=True)
    transfer.safe_path(str(root),directory=True); target_dir=root/('transfer-'+q['original']['brainId'])
    target_dir.mkdir(mode=0o700); target=target_dir/Path(t['snapshot']['rollout']['path']).name
    pending=target_dir/'history.pending'
    with os.fdopen(os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as stream:
        stream.write(transfer.read_archive(t['archivePath'])); stream.flush(); os.fsync(stream.fileno())
    os.link(pending,target,follow_symlinks=False); pending.unlink(); sync_directory(target_dir)
    return target


def confirm(registry,ledger,q,confirmation_hash,*,writers_stopped=False,backup_root=None):
    require(valid(q) and confirmation_hash==digest(q) and writers_stopped is True and backup_root is not None,
        'Exact new transfer/handoff review, stopped writers and verified private backups required')
    planning.current(registry,ledger,q); planning.verify_backup(q,backup_root)
    root=phase.owner_root(q); t=transfer_record(q); brain=q['original']['brainId']; proxy=None; result=None
    with planning.partial.lock(registry.db),planning.partial.lock(ledger.db):
        planning.current(registry,ledger,q)
        require(not os.path.lexists(root.parent) and not os.path.lexists(q['mailbox']),'Transfer/phase already consumed; no second host, ID or retry')
        root.parent.parent.mkdir(mode=0o700,exist_ok=True); planning.old.private_path(root.parent.parent,existing=True)
        root.parent.mkdir(mode=0o700); root.mkdir(mode=0o700); sync_directory(root.parent.parent)
        now=time.time(); exclusive(root/'intent.json',{'kind':KIND,'reviewHash':digest(q),
            'phaseClock':{'phaseId':q['phase']['id'],'startedAt':now,'expiresAt':now+q['phase']['durationHours']*3600,
                'durationHours':q['phase']['durationHours']}})
    try:
        with SourceProxy(t['sourceBinding'],brain) as source,DestinationProxy(q) as proxy:
            require(source_snapshot(source,q)==source_snapshot(source,q),'Source native history changed')
            empty_destination(proxy,t); check_authentication(proxy,q)
            def claim(method,name,params):
                planning.current(registry,ledger,q); source_snapshot(source,q); check_authentication(proxy,q)
                exclusive(root/(name+'.claim.json'),{'reviewHash':digest(q),'paramsHash':digest(params)})
                planning.current(registry,ledger,q); proxy.allow(method,params)
                return proxy._rpc(method,params)
            restored=claim('project/restoreMetadata','restore',{'version':1,'project':t['snapshot']['project']})
            require(restored=={'version':1,'project':dict(t['snapshot']['project'],recencyAt=None)},'Exact native project restore acknowledgement required')
            exclusive(root/'restore.json',{'reviewHash':digest(q),'responseHash':digest(restored)})
            target=copy_history(q,t)
            params={'threadId':brain,'path':str(target),'cwd':q['original']['scope']['checkout'],'excludeTurns':True,
                'approvalPolicy':'on-request','approvalsReviewer':'user','sandbox':'workspace-write',
                'config':{'features':{'code_mode':{'enabled':False},'goals':False,'apps':False,'plugins':False,'hooks':False}}}
            loaded=claim('thread/resume','load',params); thread=loaded.get('thread') or {}
            require(thread.get('id')==brain and thread.get('cwd')==params['cwd'] and thread.get('status')=={'type':'idle'} and
                thread.get('turns',[])==[],'Exact metadata-only load acknowledgement required; no retry')
            policies=[proxy._rpc('thread/effectivePolicy/read',{'threadId':brain}) for _ in range(2)]
            require(policies[0]==policies[1] and matches(reported(policies[0],brain,params['cwd'])),'Actual restricted loaded policy required')
            exclusive(root/'load.json',{'reviewHash':digest(q),'policyHash':digest(policies[0]),'metadataOnly':True})
            assigned=claim('thread/metadata/update','assign',{'threadId':brain,'projectId':t['snapshot']['project']['id']})
            exclusive(root/'assign.json',{'reviewHash':digest(q),'responseHash':digest(assigned)})
            for _ in range(2):
                thread=proxy._rpc('thread/read',{'threadId':brain,'includeTurns':True})['thread']
                require(thread['id']==brain and thread['projectId']==t['snapshot']['project']['id'] and thread['cwd']==params['cwd'] and
                    thread['status']=={'type':'idle'} and digest(thread['turns'])==t['snapshot']['turnsHash'],
                    'Transferred membership/history projection mismatch')
            require(transfer.read_archive(target).startswith(transfer.read_archive(t['archivePath'])),'Native load changed the immutable history prefix')
            source_snapshot(source,q); authentication.require_ready(proxy)
            exclusive(root/'transfer.json',{'status':'metadata_transferred','reviewHash':digest(q),
                'historySha256':t['archivePin']['sha256'],'brainId':brain,'projectId':t['snapshot']['project']['id'],
                'destinationPath':str(target),'policyHash':digest(policies[0]),'boundary':dict(BOUNDARY)})
            sub=planning.transport.Subscription(proxy,q['candidateBinding'],brain,q['transport'])
            def subscribe(context):
                planning.current(registry,ledger,q); source_snapshot(source,q); check_authentication(proxy,q)
                exclusive(root/'subscription.claim.json',{'contextHash':context,'subscriptionClaimed':True})
                return {'contextHash':context,'subscriptionClaimed':True}
            attached=sub.attach(subscribe); exclusive(root/'subscription.json',attached)
            owner=TransferOwner(registry,ledger,q,proxy,sub,root)
            result=planning.confirm(registry,ledger,q,digest(q),writers_stopped=True,backup_root=backup_root,_handoff=owner)
            exclusive(root/'planning-outcome.json',result)
    except (Refusal,OSError,ValueError,KeyError,TypeError,KeyboardInterrupt) as error:
        exclusive(root/'failure.json',{'errorType':type(error).__name__,'retryPermitted':False})
    closed=proxy is not None and proxy.process is None
    value={'status':result['status'] if result and closed else 'blocked_or_unknown','reviewHash':digest(q),
        'connectionClosed':closed,'boundary':dict(BOUNDARY),'postTurnUsage':'unknown_not_collected',
        'records':{p.name:planning.pin(p) for p in root.iterdir() if p.is_file()},
        'consumerInventory':phase.consumer_inventory(q)}
    exclusive(root/'outcome.json',value); return value


def status(q):
    """Retained history only: no live process check, reconnect or new collection."""
    retained_lineage(q); root=phase.owner_root(q)
    if not os.path.lexists(root.parent): return {'status':'not_submitted','boundary':dict(BOUNDARY)}
    phase_clock(q,active=False)
    if not (root/'outcome.json').exists(): return {'status':'claimed_current_connection_unknown','boundary':dict(BOUNDARY)}
    value=read(root/'outcome.json')
    require(set(value)=={'status','reviewHash','connectionClosed','boundary','postTurnUsage','records','consumerInventory'} and
        value['reviewHash']==digest(q) and value['boundary']==BOUNDARY and type(value['connectionClosed']) is bool and
        value['status'] in ('blocked_or_unknown','incomplete_unknown','planning_completed') and
        value['postTurnUsage']=='unknown_not_collected' and set(value['records'])<=OWNER_FILES-{'outcome.json'} and
        'intent.json' in value['records'] and all(planning.pin(root/n)==p for n,p in value['records'].items()) and
        {p.name for p in root.iterdir()}==set(value['records'])|{'outcome.json'} and
        phase.consumer_inventory(q)==value['consumerInventory'],'Changed/partial/unlisted transfer/handoff outcome stays unknown')
    if value['status']=='planning_completed':
        required={'intent.json','restore.claim.json','restore.json','load.claim.json','load.json','assign.claim.json','assign.json',
            'transfer.json','subscription.claim.json','subscription.json','handoff.claim.json','planning-outcome.json'}
        require(value['connectionClosed'] and required<=set(value['records']) and
            planning.status(q)==read(root/'planning-outcome.json') and planning.status(q)['status']=='planning_completed',
            'Native completion is not a positive transfer and new explicit receipt/proposal')
    return value


def binding_review(q):
    """Exact conditional cutover scope, never startup installation or a wake.

    Preparing this before transfer is allowed. Its explicit prerequisite is the
    same complete transfer/handoff result, revalidated at later application.
    """
    require(valid(q),'Exact transfer/handoff review required'); t=retained_transfer(q)
    request={'kind':'transferred_brain_binding_review_v1','transferReviewHash':digest(q),
        'destinationFile':q['candidateFile'],'destinationPin':q['candidatePin'],
        'destinationBindingHash':digest(q['candidateBinding']),'originalBindingFile':q['original']['bindingFile'],
        'originalBindingPin':q['original']['bindingPin'],'workspaceId':q['original']['workspaceId'],
        'brainId':q['original']['brainId'],'requiredOutcome':'planning_completed',
        'requiredHostProcess':t['destinationHost']['process'],'boundary':dict(BOUNDARY)}
    return {'request':request,'reviewHash':digest(request),'validUntil':'scope_changes',
        'prerequisiteSatisfied':status(q)['status']=='planning_completed','installsBinding':False,
        'effect':'Only a later separately installed/quiesced dashboard cutover after this exact complete transfer/handoff; no native turn, old-request replay or phase activation'}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare')
    for n in ('maintenance_review','destination_binding','launch_manifest','launch_attempt','process_record','directory'): a.add_argument(n)
    a.add_argument('--maintenance-source'); a.add_argument('--duration-hours',type=int,default=24); a.add_argument('--max-tokens',type=int,default=10000)
    for name in ('backup','confirm','status','stop','binding-review'):
        a=sub.add_parser(name); a.add_argument('review')
        if name=='backup': a.add_argument('destination')
        if name in ('backup','confirm'): a.add_argument('--writers-stopped',action='store_true')
        if name in ('confirm','stop'): a.add_argument('--confirm-hash',required=True)
        if name=='confirm': a.add_argument('--backup',required=True)
    args=p.parse_args()
    if args.action in ('status','stop','binding-review'):
        q=planning.read_review(args.review); require(valid(q),'New-host transfer review required')
        if args.action=='status': out=status(q)
        elif args.action=='binding-review': out=binding_review(q)
        else:
            require(args.confirm_hash==digest(q),'Exact Stop review hash required'); phase_clock(q,active=False)
            exclusive(phase.owner_root(q)/'stop.json',{'reviewHash':digest(q),'nativeCancelSent':False})
            out={'status':'stop_requested','nativeCancelSent':False}
    else:
        registry,ledger=planning.partial.routes(args.platform,args.workspace)
        if args.action=='prepare': out=prepare(registry,ledger,args.maintenance_review,args.destination_binding,args.launch_manifest,
            args.launch_attempt,args.process_record,args.directory,maintenance_source=args.maintenance_source,
            duration_hours=args.duration_hours,max_tokens=args.max_tokens)
        else:
            q=planning.read_review(args.review)
            if args.action=='backup': out=planning.backup(registry,ledger,q,args.destination,writers_stopped=args.writers_stopped)
            else: out=confirm(registry,ledger,q,args.confirm_hash,writers_stopped=args.writers_stopped,backup_root=args.backup)
    print(canonical(out))


if __name__=='__main__':
    # Keep the original process-local owner type canonical under python -m.
    from .host_transfer_handoff import main as entrypoint
    try: entrypoint()
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
