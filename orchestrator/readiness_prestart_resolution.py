"""Exact file-only disposition of a consumed pre-load readiness deadline failure.

Never a new readiness allowance, native client, receipt, cleanup or retry path.
The old command, canonical claim, handoff and all databases' original rows remain.
"""
import argparse
import contextlib
import hashlib
import os
from pathlib import Path
import sqlite3
import time

from .core import Ledger, Refusal, canonical, digest, require
from . import partial_admission as partial, readiness_disposition as old, readiness_owned as owned, standard
from . import standard_preplay as preplay
from .app_server_wake import _read_binding
from .host_lifecycle import private_file, sync_directory
from .native_project_assignment import _read_registry
from .same_project_lifecycle import source_proof
from .standard_quarantine import exclusive
from .standard_successor import pin

KIND = 'readiness_prestart_resolution_v1'
FENCE = 'readiness-prestart-resolution.claim.json'
OUTCOME = 'preload_deadline_unqualified'
PR187_SOURCE = 'ae5f9193dbb894de6a545fc800cbeae5473408fe377f18428fa4938a9e3808ef'
BOUNDARY = {**old.BOUNDARY, 'readinessAllowanceRestored': False, 'ownershipReleased': False}
FIELDS = old.FIELDS | {'originalSource', 'sidecarPins'}


def command_in(ledger, db, ident):
    from .brain_control import stopped
    meta, mission = standard.eligible(ledger, db)
    require(meta['schemaVersion'] in (1, 7) and meta['paused'] and
            not any(meta.get(k) for k in ('standardRun','controller','runner','brainHandoff','admissionBinding')) and
            not stopped(meta) and not os.path.lexists(standard.controller_file(ledger)) and
            all(not ledger.all(db,k) for k in ('workers','queue','decisions','continuations')),
            'Only the unchanged empty unowned first-phase standard project qualifies')
    commands = ledger.all(db, 'commands')
    require(len(commands) == 1 and commands[0]['id'] == ident, 'Only one original readiness-owned request is covered')
    c = commands[0]; review = owned.validate_review(c.get('payload',{}).get('readinessStart'))
    n = c.get('notification') or {}
    require(set(c) == {'id','kind','actor','status','createdAt','payload','result','notification'} and
            c['kind'] == standard.CATALOG_REFRESH_KIND and c['status'] == 'queued' and
            c['actor'] in ('dashboard','assistant_owner_confirmed') and
            set(c['payload']) == {'brainId','contextHash','missionHash','readinessStart'} and
            c['payload']['brainId'] == meta['brainId'] == review['brainId'] and
            c['payload']['contextHash'] == review['contextHash'] and
            c['payload']['missionHash'] == mission['documentHash'] == review['local']['missionHash'] and
            review['commandId'] == ident and review['before']['activity'] == 'notLoaded' and
            set(n) == {'attemptedAt','brainId','detail','finishedAt','nativeFailure','preplayCatalog','status','wakeId'} and
            n['status'] == 'unavailable' and n['brainId'] == meta['brainId'] and
            n['wakeId'] == digest({'commandId':ident}) and
            n['nativeFailure'] == {'version':1,'stage':'authentication_check','reason':'deadline_exceeded',
                                  'resumeAttempted':False,'turnStartAttempted':False} and
            all(old.finite(v) for v in (c['createdAt'],n['attemptedAt'],n['finishedAt'])) and
            0 < c['createdAt'] <= n['attemptedAt'] <= n['finishedAt'] <= time.time(),
            'Positive exact pre-load/pre-turn deadline failure required; unknown or executed delivery stays fenced')
    stable = dict(meta); stable.pop('revision',None)
    require(digest(stable) == review['local']['metaHash'], 'Original usage, mission or ownership changed')
    owned.retained_in(ledger, db)
    claim = owned.record(owned.fence(ledger))
    owned.validate_backup(ledger,review,claim['backup'])
    require(claim['reviewHash'] == digest(review) and claim['bindingHash'] == review['bindingHash'],
            'Original canonical claim and verified backup required')
    # Absence alone is not proof: it corroborates the positive original diagnostic.
    require(not any(owned.journal(ledger,ident,k).exists() for k in ('load-claim','load-ack')),
            'Any load claim or acknowledgment is outside pre-load resolution')
    close = owned.journal(ledger,ident,'close')
    if os.path.lexists(close):
        require(owned.record(close) == {'protocol':owned.PROTOCOL,'commandId':ident,'nativeTurnId':None,
            'status':'no_turn_started','connectionClosed':True,'reconnectAllowed':False,'terminalSafety':'unknown'},
            'Only an exact original pre-start close may corroborate the positive failure')
    hpath = preplay.path(ledger.root,ident,'handoff'); h = owned.record(hpath)
    require(set(h) == {'version','transport','workspaceId','brainId','commandId','missionHash','contextHash',
            'bindingHash','ledgerIdentity','source','sourceHash','boundary','publicBackendHash','readinessStartHash'} and
            h['version'] == 3 and h['transport'] == preplay.TRANSPORT and h['boundary'] == preplay.BOUNDARY and
            all(h[k] == review[k] for k in ('workspaceId','brainId','commandId','contextHash','bindingHash','ledgerIdentity','sourceHash')) and
            h['missionHash'] == mission['documentHash'] and h['readinessStartHash'] == digest(review) and
            n['preplayCatalog'] == {'version':3,'transport':preplay.TRANSPORT,'handoffHash':digest(h)} and
            not any(preplay.path(ledger.root,ident,k).exists() for k in
                    ('request','claim','reply','capabilities','capabilities-claim')),
            'Exact prospective handoff, no capture, receipt or native-start evidence required')
    return meta, mission, c, h, hpath


def context(registry, ledger, binding_file, ident, original_source):
    from .enrollment import record_in
    require(not os.path.lexists(ledger.root/FENCE), 'Resolution already claimed; inspect, never reapply')
    with _read_registry(registry) as db: require(record_in(db) is None, 'Strict enrollment remains fenced')
    with standard.read_db(ledger.db) as db: meta, mission, c, h, hp = command_in(ledger,db,ident)
    source = source_proof(original_source)
    require(source['root'] == h['source'] and source['sourceHash'] == h['sourceHash'] and
            source['sourceHash'] in (PR187_SOURCE,preplay.source_hash()),
            'Explicit immutable qualified original source required; never execute historical Python')
    file = private_file(binding_file); binding = _read_binding(file)
    require(digest(binding) == c['payload']['readinessStart']['bindingHash'], 'Original binding only; no migration')
    scope = old.binding_scope(registry,ledger,binding)
    require(h['publicBackendHash'] == digest(binding['brains'][meta['brainId']]['nativeTaskBackend']),
            'Original public native backend changed')
    original_pins = c['payload']['readinessStart']['local']['sidecars']
    from .public_host_restart import pin as full_pin
    require(all(full_pin(v['path'],1_000_000) == v for v in original_pins.values()), 'Original sidecar changed')
    files = [owned.fence(ledger),hp,*[Path(v['path']) for v in original_pins.values()]]
    close = owned.journal(ledger,ident,'close')
    if os.path.lexists(close): files.append(close)
    pins = {str(p):pin(p) for p in files}
    # No unknown mailbox, approval or hidden lifecycle file can be ignored.
    expected = {owned.fence(ledger).name,hp.name}
    if os.path.lexists(close): expected.add(close.name)
    actual = {p.name for p in ledger.root.iterdir() if p.name.startswith(('readiness-owned-','preplay-catalog-'))}
    require(actual == expected, 'Partial or unlisted readiness lifecycle remains fenced')
    return {'version':1,'kind':KIND,'sourceHash':preplay.source_hash(),'workspaceId':ledger.workspace_id,
        'brainId':meta['brainId'],'root':str(ledger.root),'command':c,'metaHash':digest(meta),
        'missionHash':mission['documentHash'],'reviewHash':mission['receiptHash'],
        'bindingFile':str(file),'bindingPin':pin(file),'bindingEpoch':old.file_epoch(file),
        'bindingHash':digest(binding),'scope':scope,'originalSource':source,'sidecarPins':pins,
        'databaseProofs':{'target':partial.database_proof(ledger.db),'registry':partial.database_proof(registry.db)},
        'boundary':dict(BOUNDARY)}


def valid(q):
    return isinstance(q,dict) and set(q) == FIELDS and type(q['version']) is int and q['version'] == 1 and \
        q['kind'] == KIND and q['boundary'] == BOUNDARY and len(canonical(q).encode()) <= 58000


def prepare(registry, ledger, binding_file, ident, original_source):
    q = context(registry,ledger,binding_file,ident,original_source)
    require(valid(q),'Closed bounded resolution review required')
    return {'request':q,'reviewHash':digest(q),'validUntil':'scope_changes',
        'effect':'Record this consumed pre-load failure as unqualified; no readiness, load or retry allowance',
        'boundary':dict(BOUNDARY)}


def read_request(file):
    before = pin(file); q = owned.record(file)
    require(pin(file) == before and valid(q),'Exact private resolution review required')
    return q


def same(registry,ledger,q):
    require(valid(q) and context(registry,ledger,q['bindingFile'],q['command']['id'],q['originalSource']['root']) == q,
            'Reviewed resolution scope changed')


def backup(registry,ledger,q,destination,*,writers_stopped=False):
    require(writers_stopped is True,'Stop older writers before the separate local disposition')
    same(registry,ledger,q)
    root = Path(destination); old.private_path(root.parent,existing=True)
    require(root.is_absolute() and root.resolve() == root and not os.path.lexists(root) and
            all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in (ledger.root,registry.root)),
            'New private backup disjoint from operational roots required')
    root.mkdir(mode=0o700); files = {}
    for key,source in (('target',ledger.db),('registry',registry.db)):
        dest = root/(key+'.sqlite3')
        os.close(os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        with standard.read_db(source) as src, contextlib.closing(sqlite3.connect(dest)) as dst:
            src.backup(dst); require(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok','Backup integrity failed')
        require(partial.database_proof(dest)['fingerprint'] == q['databaseProofs'][key]['fingerprint'],'Backup changed')
        with dest.open('rb') as stream: os.fsync(stream.fileno())
        files[dest.name] = old.database_epoch(dest)
    inputs = {'review.json':canonical(q).encode(),'binding.json':private_file(q['bindingFile']).read_bytes()}
    inputs.update({'sidecar-'+str(i)+'.json':private_file(p).read_bytes() for i,p in enumerate(sorted(q['sidecarPins']))})
    for name,raw in inputs.items():
        with os.fdopen(os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        files[name] = pin(root/name)
    same(registry,ledger,q)
    exclusive(root/'manifest.json',{'kind':KIND,'reviewHash':digest(q),'files':files})
    return {'backup':str(root),'verified':True,'reviewHash':digest(q)}


def verify_backup(q,root):
    root = old.private_path(root,existing=True); m = owned.record(root/'manifest.json')
    expected = {'target.sqlite3','registry.sqlite3','binding.json','review.json',
                *['sidecar-'+str(i)+'.json' for i in range(len(q['sidecarPins']))]}
    require(set(m) == {'kind','reviewHash','files'} and m['kind'] == KIND and m['reviewHash'] == digest(q) and
            set(m['files']) == expected,'Complete exact resolution backup required')
    for name,p in m['files'].items():
        require((old.database_epoch(root/name) if name.endswith('.sqlite3') else pin(root/name)) == p,'Backup epoch changed')
    for name,p in q['databaseProofs'].items():
        require(partial.database_proof(root/(name+'.sqlite3'))['fingerprint'] == p['fingerprint'] and
            old.database_identity(root/(name+'.sqlite3')) != p['identity'],'Backup differs or aliases original')
    require(owned.record(root/'review.json') == q and
        (root/'binding.json').read_bytes() == private_file(q['bindingFile']).read_bytes(),'Review/binding backup changed')
    for i,p in enumerate(sorted(q['sidecarPins'])):
        require((root/('sidecar-'+str(i)+'.json')).read_bytes() == private_file(p).read_bytes(),'Original sidecar backup changed')


def retained_in(ledger,db):
    rows = db.execute('SELECT id,data FROM snapshots WHERE kind=?',(KIND,)).fetchall()
    if not os.path.lexists(ledger.root/FENCE):
        require(not rows,'Resolution claim missing; no downgrade or replay'); return None
    claim = owned.record(ledger.root/FENCE)
    require(len(rows) == 1,'Partial resolution intent stays fenced; never reapply')
    record = old.decode(rows[0]['data'].encode()); q = record.get('request',{})
    require(set(record) == {'kind','request','reviewHash','recordedAt','claimPin','outcome'} and valid(q) and
            record['kind'] == KIND and record['outcome'] == OUTCOME and digest(record) == rows[0]['id'] and
            record['reviewHash'] == digest(q) and claim == {'kind':KIND,'reviewHash':digest(q)} and
            pin(ledger.root/FENCE) == record['claimPin'] and q['root'] == str(ledger.root) and
            q['workspaceId'] == ledger.workspace_id and old.database_identity(ledger.db) == q['databaseProofs']['target']['identity'] and
            digest(ledger.get(db,'meta',1)) == q['metaHash'] and
            ledger.get(db,'commands',q['command']['id']) == q['command'] and
            all(pin(p) == v for p,v in q['sidecarPins'].items()), 'Resolution/original intent changed; no receipt or retry')
    # Only this new snapshot may differ. Detect edits to any old row, mission,
    # observation, usage or history without granting a writer or native client.
    from .workspaces import fingerprint
    current = fingerprint(db)
    rows = sorted(canonical([{'blobSHA256':hashlib.sha256(v).hexdigest(),'bytes':len(v)}
                             if isinstance(v,bytes) else v for v in row])
                  for row in db.execute('SELECT * FROM snapshots WHERE id<>?',(digest(record),)))
    current['snapshots'] = {'rows':len(rows),'sha256':digest(rows)}
    require(current == q['databaseProofs']['target']['fingerprint']['tables'] and
            pin(q['bindingFile']) == q['bindingPin'] and old.file_epoch(q['bindingFile']) == q['bindingEpoch'],
            'Original database rows or binding changed; resolution grants no mutation authority')
    return record


def require_open(ledger,db):
    require(retained_in(ledger,db) is None,
            'Consumed pre-load readiness resolved as unqualified; no reload, receipt reconstruction or retry')


def public(record):
    return {'status':'disposed_unqualified','kind':KIND,'commandId':record['request']['command']['id'],
        'recordHash':digest(record),'recordedAt':record['recordedAt'],'originalStatus':'queued',
        'brainReceipt':'missing','boundary':dict(BOUNDARY)}


def confirm(registry,ledger,q,confirmation_hash,*,writers_stopped=False,backup_root=None):
    require(valid(q) and confirmation_hash == digest(q) and q['workspaceId'] == ledger.workspace_id and
            q['root'] == str(ledger.root),'Exact new resolution owner review required')
    if os.path.lexists(ledger.root/FENCE):
        with standard.read_db(ledger.db) as db: saved = retained_in(ledger,db)
        require(saved['request'] == q,'A different resolution is already claimed'); return public(saved)
    require(writers_stopped is True and backup_root is not None,'Stopped writers and private verified backup required')
    with partial.lock(registry.db), partial.lock(ledger.db) as db:
        same(registry,ledger,q); verify_backup(q,backup_root)
        exclusive(ledger.root/FENCE,{'kind':KIND,'reviewHash':digest(q)})
        record = {'kind':KIND,'request':q,'reviewHash':digest(q),'recordedAt':time.time(),
                  'claimPin':pin(ledger.root/FENCE),'outcome':OUTCOME}
        require(len(canonical(record).encode()) <= 62000,'Bounded resolution record required')
        db.execute('INSERT INTO snapshots VALUES(?,?,?)',(digest(record),KIND,canonical(record)))
        retained_in(ledger,db); sync_directory(ledger.root); db.commit()
    return public(record)


def status(ledger):
    try:
        with standard.read_db(ledger.db) as db: saved = retained_in(ledger,db)
        return public(saved) if saved else {'status':'not_recorded'}
    except (OSError,Refusal,ValueError,KeyError,TypeError,sqlite3.Error):
        return {'status':'incomplete_or_changed','writesBlocked':True,'boundary':dict(BOUNDARY)}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    preview=sub.add_parser('preview'); preview.add_argument('binding'); preview.add_argument('command'); preview.add_argument('original_source')
    b=sub.add_parser('backup'); b.add_argument('review'); b.add_argument('destination'); b.add_argument('--writers-stopped',action='store_true')
    c=sub.add_parser('confirm'); c.add_argument('review'); c.add_argument('--confirm-hash',required=True)
    c.add_argument('--backup',required=True); c.add_argument('--writers-stopped',action='store_true'); sub.add_parser('status')
    a=p.parse_args(); registry,ledger=partial.routes(a.platform,a.workspace)
    if a.action=='preview': result=prepare(registry,ledger,a.binding,a.command,a.original_source)
    elif a.action=='status': result=status(ledger)
    elif a.action=='backup': result=backup(registry,ledger,read_request(a.review),a.destination,writers_stopped=a.writers_stopped)
    else: result=confirm(registry,ledger,read_request(a.review),a.confirm_hash,writers_stopped=a.writers_stopped,backup_root=a.backup)
    print(canonical(result))


if __name__ == '__main__':
    try: main()
    except (Refusal,OSError,ValueError,KeyError,TypeError,sqlite3.Error) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
