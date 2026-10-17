"""Forward-only local disposition and non-executing continuation assessment.

No receipt reconstruction, native write/load, replay, cleanup or new authority.
The original run and all original rows survive. An incomplete claim fences writes.
"""
import contextlib
import copy
import hashlib
import os
from pathlib import Path
import sqlite3
import time

from .core import Refusal, SHA, canonical, digest, require
from . import effect_capture, partial_admission as partial, readiness_disposition as prior, standard
from .app_server_wake import _read_binding, NATIVE_APPROVAL_POLICY
from .enrollment import fence_exists, record_in
from .host_lifecycle import private_file, sync_directory
from .native_project_assignment import _read_registry, UUID
from .native_read_client import decode, file_identity
from .standard_quarantine import exclusive
from .standard_successor import pin
from .workspaces import fingerprint, private_path

KIND = 'canceled_play_disposition_v1'
FENCE = 'standard-canceled-play.json'
OUTCOME = 'canceled_play_unqualified'
BOUNDARY = {'nativeAction': False, 'brainReloaded': False, 'requestReplayed': False,
            'brainReceiptReconstructed': False, 'runClosed': False, 'checkpointCreated': False,
            'ownershipReleased': False, 'usageReset': False, 'bindingChanged': False,
            'continuationAuthorized': False, 'terminalSafety': 'unknown', 'pilotAccepted': False}
FIELDS = {'version', 'kind', 'sourceHash', 'workspaceId', 'root', 'brainId', 'command',
          'run', 'bindingFile', 'bindingPin', 'bindingEpoch', 'bindingHash', 'scope',
          'databaseProofs', 'sidecars', 'captureHash', 'boundary'}


def source_hash():
    from .standard_preplay import source_hash as implementation_hash
    return implementation_hash()


def exists_in(ledger, db):
    return os.path.lexists(ledger.root/FENCE) or bool(
        db.execute('SELECT 1 FROM snapshots WHERE kind=? LIMIT 1', (KIND,)).fetchone())


def sidecars(ledger):
    paths = []
    def failed(error): raise error
    for directory, dirs, files in os.walk(ledger.root,followlinks=False,onerror=failed):
        root = Path(directory); info = root.lstat()
        require(root.resolve(strict=True) == root and root.is_dir() and info.st_uid == os.getuid() and
                not info.st_mode & 0o077, 'Every sidecar directory must be canonical, private and readable')
        for name in dirs:
            child = root/name
            require(not child.is_symlink(), 'Sidecar directories cannot have aliases')
        paths.extend(root/name for name in files)
    paths = [p for p in paths if p.name not in ('ledger.sqlite3', 'ledger.sqlite3-wal', 'ledger.sqlite3-shm')
             and p != ledger.root/FENCE]
    require(len(paths) <= 256 and sum(p.lstat().st_size for p in paths) <= 8_000_000,
            'Canceled Play sidecar bound exceeded; nothing is truncated')
    result = {}
    for path in sorted(paths):
        before = path.lstat()
        require(path.resolve(strict=True) == path and path.is_file() and not path.is_symlink() and
                before.st_uid == os.getuid() and not before.st_mode & 0o077 and before.st_nlink == 1,
                'Private unchanged sidecars without aliases required')
        with path.open('rb') as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
            require(file_identity(before) == file_identity(os.fstat(stream.fileno())) == file_identity(path.lstat()),
                    'Sidecar changed during disposition inspection')
        result[str(path.relative_to(ledger.root))] = {'sha256': sha, 'epoch': list(file_identity(before))}
    return result


def original_in(ledger, db, command_id):
    from .brain_control import stopped
    from .readiness_owned import old_receipt
    meta, mission = standard.eligible(ledger, db)
    run = meta.get('standardRun') or {}
    require(meta['schemaVersion'] == 4 and meta.get('controller') is None and meta.get('runner') is None and
            not meta.get('brainHandoff') and not stopped(meta) and not meta.get('admissionBinding') and
            not fence_exists(ledger.root) and not os.path.lexists(standard.controller_file(ledger)) and
            run.get('protocol') == standard.PROTOCOL and run.get('brainId') == meta['brainId'] and
            run.get('status') == 'running' and run.get('checkpoint') is None and not run.get('tasks') and
            not run.get('merges') and not run.get('recovery') and not run.get('ownerCloseout'),
            'Only an empty unowned running schema-v4 standard attempt is covered; no ownership is released')
    require(not any(os.path.lexists(ledger.root/name) for name in (
        'standard-successor.json', 'standard-forward-continuation.json', 'standard-quarantine.json',
        'standard-partial-admission-disposition.json')), 'Other dispositions and claims retain their existing gates')
    require(all(not ledger.all(db, table) for table in ('workers','queue','decisions','continuations')),
            'Task, packet, decision or continuation ownership must be reconciled separately')
    commands = ledger.all(db, 'commands')
    require(1 <= len(commands) <= 32, 'Bounded original history required')
    plays = [c for c in commands if c.get('kind') == 'standard_play']
    require(len(plays) == 1 and plays[0]['id'] == command_id, 'Sole original Play required')
    c = plays[0]
    require(c.get('status') == 'queued' and c.get('actor') in ('dashboard','assistant_owner_confirmed') and
            c.get('payload') == {'runId': run.get('id')} and
            not any(k in c for k in ('receivedAt','completedAt')) and not c.get('notificationHistory') and
            run.get('ownerReceipt',{}).get('id') == c['id'] and
            run['ownerReceipt'].get('operation') == 'play' and
            run.get('missionHash') == mission['documentHash'] and run.get('reviewHash') == mission['receiptHash'],
            'Exact accepted, unreceived original Play and unchanged reviewed run required')
    for old in commands:
        if old['id'] == command_id: continue
        require(old.get('kind') == standard.CATALOG_REFRESH_KIND, 'Another run control cannot be silently retired')
        if not prior.retired_in(ledger, db, old['id']): old_receipt(ledger, old)
        require(not old.get('needsBrainReceipt') and not old.get('notificationHistory') and
                (old.get('notification') or {}).get('nativeThreadObservation',{}).get('streamStatus') == 'closed' and
                not any(a.get('status') not in ('resolved','resolved_without_response')
                        for a in (old.get('notification') or {}).get('nativeApprovals',[])),
                'Every earlier request must retain its own receipt or disposition and closed observer')
    n = c.get('notification') or {}; observer = n.get('nativeThreadObservation') or {}
    approvals = n.get('nativeApprovals') or []; permission = n.get('nativePermissionObservation') or {}
    profile = n.get('nativeResumeProfile') or {}; turn = n.get('nativeTurnId')
    require(n.get('status') == 'accepted' and n.get('nativeDelivery') == 'owned_turn_start' and
            n.get('brainId') == meta['brainId'] and n.get('hostRunId') == run['id'] and
            n.get('wakeId') == digest({'commandId': c['id']}) and isinstance(turn,str) and UUID.fullmatch(turn) and
            n.get('nativeTurnStatus') == 'interrupted' and not n.get('runControl') and not n.get('turnRecovery') and
            observer.get('version') == 1 and observer.get('rootThreadId') == meta['brainId'] and
            observer.get('nativeTurnId') == turn and observer.get('streamStatus') == 'closed' and
            observer.get('events') == [] and observer.get('complete') is False and
            len(approvals) == 1 and approvals[0].get('decision') == 'cancel' and approvals[0].get('status') == 'resolved' and
            approvals[0].get('turnId') == turn and approvals[0].get('method') == 'item/commandExecution/requestApproval' and
            permission.get('version') == 1 and permission.get('turnId') == turn and
            permission.get('reason') == 'native_resolved' and
            isinstance(permission.get('requestHash'),str) and SHA.fullmatch(permission['requestHash']) and
            permission['requestHash'] == approvals[0].get('requestHash') and
            profile.get('version') == 1 and profile.get('brainId') == meta['brainId'] and
            profile.get('commandId') == c['id'] and profile.get('nativeTurnId') == turn and
            profile.get('requested') == NATIVE_APPROVAL_POLICY and profile.get('resumeAcknowledged') is True,
            'Resolved exact owner Cancel, interrupted original turn, closed observer and restricted original profile required')
    ordered = [approvals[0].get('claimedAt'), approvals[0].get('observedAt'),
               permission.get('endedAt'), observer.get('monitoringEndedAt')]
    require(all(prior.finite(v) and 0 < v <= time.time() for v in ordered) and ordered == sorted(ordered),
            'Original cancellation/observer chronology is unknown')
    require(prior.finite(run.get('startedAt')) and prior.finite(run.get('expiresAt')) and
            run['expiresAt'] > run['startedAt'] and run.get('identities'), 'Original duration and repository holds required')
    return meta, run, c


def context(registry, ledger, binding_file, command_id):
    with _read_registry(registry) as db:
        require(record_in(db) is None, 'Strict enrollment is not covered')
    with standard.read_db(ledger.db) as db:
        require(not exists_in(ledger,db), 'Disposition already claimed; inspect, never recreate')
        meta, run, c = original_in(ledger, db, command_id)
    binding_file = private_file(binding_file)
    binding_pin, binding_epoch = pin(binding_file), prior.file_epoch(binding_file)
    binding = _read_binding(binding_file)
    scope = prior.binding_scope(registry, ledger, binding)
    require(digest(binding) == c['notification'].get('hostBindingHash') ==
            c['notification']['nativeResumeProfile'].get('bindingHash'), 'Original host binding cannot change')
    from .public_native_tasks import validate_contract
    brain = binding['brains'][meta['brainId']]
    backend = validate_contract(brain.get('nativeTaskBackend'), brain.get('policyEvidence'))
    require(backend == c['notification'].get('nativeTaskContract'), 'Original public backend required')
    capture = effect_capture.retained(ledger, c)
    require(capture['status'] == 'observed' and c['notification']['nativeEffectCapture']['status'] == 'sealed',
            'Retain the original sealed capture, including all recorded effects; no replacement capture')
    proofs = {'target':partial.database_proof(ledger.db),'registry':partial.database_proof(registry.db)}
    pins = sidecars(ledger)
    require(pin(binding_file) == binding_pin and prior.file_epoch(binding_file) == binding_epoch,
            'Binding changed during disposition inspection')
    return {'version':1,'kind':KIND,'sourceHash':source_hash(),'workspaceId':ledger.workspace_id,
        'root':str(ledger.root),'brainId':meta['brainId'],'command':c,'run':run,
        'bindingFile':str(binding_file),'bindingPin':binding_pin,'bindingEpoch':binding_epoch,
        'bindingHash':digest(binding),'scope':scope,
        'databaseProofs':proofs,'sidecars':pins,'captureHash':digest(capture),'boundary':dict(BOUNDARY)}


def valid(value):
    return (isinstance(value,dict) and set(value) == FIELDS and type(value['version']) is int and value['version'] == 1 and
            value['kind'] == KIND and value['boundary'] == BOUNDARY and
            all(isinstance(value[k],dict) for k in ('command','run','bindingPin','scope','databaseProofs','sidecars')) and
            set(value['databaseProofs']) == {'target','registry'} and
            all(isinstance(value[k],str) and SHA.fullmatch(value[k]) for k in ('sourceHash','bindingHash','captureHash')) and
            all(isinstance(value[k],str) and value[k] for k in ('workspaceId','brainId','root','bindingFile')) and
            len(canonical(value).encode()) <= 58000)


def prepare(registry, ledger, binding_file, command_id):
    request = context(registry,ledger,binding_file,command_id)
    require(valid(request), 'Closed canceled-Play review exceeds its bound')
    return {'request':request,'reviewHash':digest(request),'validUntil':'scope_changes',
            'effect':'Record the canceled Play as unqualified; preserve its missing receipt, original run and repository holds',
            'continuation':plan(None),'boundary':dict(BOUNDARY)}


def read_request(file):
    before = pin(file); value = decode(private_file(file).read_bytes())
    require(pin(file) == before and valid(value), 'Closed private canceled-Play review required')
    return value


def create_backup(registry, ledger, request, destination, *, writers_stopped=False):
    require(writers_stopped is True and valid(request), 'Quiesced older writers and exact review required')
    require(context(registry,ledger,request['bindingFile'],request['command']['id']) == request, 'Reviewed scope changed')
    root = Path(destination); private_path(root.parent,existing=True)
    require(root.is_absolute() and root.resolve() == root and not os.path.lexists(root), 'New canonical private backup required')
    root.mkdir(mode=0o700); files = {}
    for key, file in (('target',ledger.db),('registry',registry.db)):
        target = root/(key+'.sqlite3')
        os.close(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        with standard.read_db(file) as src, contextlib.closing(sqlite3.connect(target)) as dst:
            src.backup(dst); require(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok','Backup integrity failed')
        require(partial.database_proof(target)['fingerprint'] == request['databaseProofs'][key]['fingerprint'], 'Backup differs')
        with target.open('rb') as stream: os.fsync(stream.fileno())
        files[key+'.sqlite3'] = prior.database_epoch(target)
    for name, raw in [('binding.json',private_file(request['bindingFile']).read_bytes()),
                      ('review.json',canonical(request).encode())] + [
                          ('sidecar-'+str(i), (ledger.root/name).read_bytes()) for i,name in enumerate(sorted(request['sidecars']))]:
        fd = os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        files[name] = {'sha256':hashlib.sha256(raw).hexdigest(),'epoch':prior.file_epoch(root/name)}
    require(context(registry,ledger,request['bindingFile'],request['command']['id']) == request,'Scope changed during backup')
    exclusive(root/'manifest.json',{'kind':KIND+'_backup','reviewHash':digest(request),'files':files})
    return {'backup':str(root),'reviewHash':digest(request),'verified':True}


def verify_backup(request, root):
    root = private_path(root,existing=True); m = decode(private_file(root/'manifest.json').read_bytes())
    names = {'target.sqlite3','registry.sqlite3','binding.json','review.json'} | {
        'sidecar-'+str(i) for i in range(len(request['sidecars']))}
    require(m.get('kind') == KIND+'_backup' and m.get('reviewHash') == digest(request) and
            set(m.get('files',{})) == names, 'Exact complete private backup required')
    for name, expected in m['files'].items():
        file = root/name
        actual = prior.database_epoch(file) if name.endswith('.sqlite3') else {
            'sha256':hashlib.sha256(private_file(file).read_bytes()).hexdigest(),'epoch':prior.file_epoch(file)}
        require(actual == expected, 'Backup epoch or bytes changed')
    for key, proof in request['databaseProofs'].items():
        p = partial.database_proof(root/(key+'.sqlite3'))
        require(p['fingerprint'] == proof['fingerprint'] and p['identity'] != proof['identity'],'Aliased or changed database backup')
    require((root/'binding.json').read_bytes() == private_file(request['bindingFile']).read_bytes() and
            decode((root/'review.json').read_bytes()) == request, 'Backup binding/review changed')
    for i,name in enumerate(sorted(request['sidecars'])):
        require(hashlib.sha256((root/('sidecar-'+str(i))).read_bytes()).hexdigest() == request['sidecars'][name]['sha256'],
                'Backup omits or changes an original claim/capture')


def retained_in(ledger, db):
    rows = db.execute('SELECT id,data FROM snapshots WHERE kind=?',(KIND,)).fetchall()
    if not os.path.lexists(ledger.root/FENCE):
        require(not rows,'Canceled-Play disposition claim is missing; all writes remain fenced')
        return None
    claim = decode(private_file(ledger.root/FENCE).read_bytes())
    require(len(rows) == 1,'Partial canceled-Play intent; never retry, remove or reopen it')
    r = decode(rows[0]['data'].encode()); q = r.get('request') or {}
    require(set(r) == {'kind','request','reviewHash','recordedAt','claimPin','outcome'} and
            r['kind'] == KIND and r['outcome'] == OUTCOME and valid(q) and
            digest(r) == rows[0]['id'] and r['reviewHash'] == digest(q) and
            claim == {'kind':KIND,'reviewHash':digest(q)} and pin(ledger.root/FENCE) == r['claimPin'] and
            q['root'] == str(ledger.root) and q['workspaceId'] == getattr(ledger,'workspace_id',None) and
            q['databaseProofs']['target']['identity'] == prior.database_identity(ledger.db),
            'Disposition identity, claim or immutable record changed')
    tables = fingerprint(db); old = q['databaseProofs']['target']['fingerprint']['tables']
    schema = [list(row) for row in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
    require(digest(schema) == q['databaseProofs']['target']['fingerprint']['schemaHash'],'Original schema changed')
    require(set(tables) == set(old),'Original schema changed')
    for table in tables:
        if table == 'snapshots':
            values = sorted(canonical(list(row)) for row in db.execute('SELECT * FROM snapshots WHERE kind<>?',(KIND,)))
            actual = {'rows':len(values),'sha256':digest(values)}
        else: actual = tables[table]
        require(actual == old[table], 'Original ledger rows changed: '+table)
    require(sidecars(ledger) == q['sidecars'] and pin(q['bindingFile']) == q['bindingPin'] and
            prior.file_epoch(q['bindingFile']) == q['bindingEpoch'], 'Original sidecars or binding epoch changed')
    return r


def plan(record):
    return {'status':'blocked_no_reload_transport','executionAvailable':False,
        'dispositionRecorded':record is not None,'nativeAction':False,'brainReloaded':False,
        'blockers':([] if record is not None else [{'code':'exact_disposition_required',
                     'detail':'No complete owner-reviewed disposition is retained. An incomplete claim must be inspected, never retried or removed.'}])+[{'code':'no_reload_owned_subscription_unavailable',
                     'detail':'The pinned public protocol establishes an owned subscription through thread/resume. turn/start alone is not an owned observer; no reload or substitute send is permitted.'},
                    {'code':'new_continuation_authority_required',
                     'detail':'Disposition records an unqualified outcome only. Any future continuation needs a distinct exact owner review, unchanged run limits/expiry, actual usage and current tracked-terminal/policy evidence.'}],
        'historicalEffects':'preserved_unknown','currentTerminalSafety':'unknown',
        'historicalTerminalSafety':'unknown','boundary':dict(BOUNDARY)}


def public(record):
    return {'status':'disposed_unqualified','commandId':record['request']['command']['id'],
        'runId':record['request']['run']['id'],'recordHash':digest(record),'recordedAt':record['recordedAt'],
        'brainReceipt':'missing','originalRunStatus':record['request']['run']['status'],
        'writesBlocked':True,'continuation':plan(record),'boundary':dict(BOUNDARY)}


def status_in(ledger, db):
    try:
        r = retained_in(ledger,db)
        return public(r) if r else {'status':'not_recorded','boundary':dict(BOUNDARY)}
    except (OSError,Refusal,ValueError,KeyError,TypeError,sqlite3.Error):
        return {'status':'incomplete_or_changed','writesBlocked':True,'continuation':plan(None),'boundary':dict(BOUNDARY)}


def status(ledger):
    with standard.read_db(ledger.db) as db: return status_in(ledger,db)


def confirm(registry, ledger, request, confirmation_hash, *, writers_stopped=False, backup_root=None):
    require(valid(request) and confirmation_hash == digest(request) and request['root'] == str(ledger.root) and
            request['workspaceId'] == ledger.workspace_id, 'Confirm the exact new canceled-Play disposition hash')
    with standard.read_db(ledger.db) as db:
        if exists_in(ledger,db):
            r = retained_in(ledger,db)
            require(r is not None and r['request'] == request,'Different disposition owns this ledger')
            return public(r)  # Read an original local receipt, never reapply an intent.
    require(writers_stopped is True and backup_root is not None,'Quiesced older writers and verified backup required')
    with partial.lock(registry.db), partial.lock(ledger.db) as db:
        require(context(registry,ledger,request['bindingFile'],request['command']['id']) == request,'Reviewed scope changed')
        verify_backup(request,backup_root)
        exclusive(ledger.root/FENCE,{'kind':KIND,'reviewHash':confirmation_hash})
        r = {'kind':KIND,'request':copy.deepcopy(request),'reviewHash':confirmation_hash,'recordedAt':time.time(),
             'claimPin':pin(ledger.root/FENCE),'outcome':OUTCOME}
        require(len(canonical(r).encode()) <= 62000,'Disposition exceeds its closed bound')
        db.execute('INSERT INTO snapshots VALUES(?,?,?)',(digest(r),KIND,canonical(r)))
        retained_in(ledger,db); db.commit(); sync_directory(ledger.root)
    return public(r)


def continuation(ledger):
    result = status(ledger)
    return {**result.get('continuation',plan(None)),'disposition':result['status']}
