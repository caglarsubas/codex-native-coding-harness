"""New prospective lineage after an uncommitted admission, never its retry.

One new owner review can include recording the unqualified disposition. Both old
claims stay immutable. Nothing loads, connects, starts Play or releases old scope.
"""
import contextlib
import copy
import hashlib
import math
import os
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace

from .core import Ledger, Refusal, canonical, digest, require
from . import partial_admission as partial, standard, standard_successor as successor, missions
from .host_lifecycle import private_file, sync_directory
from .native_read_client import decode
from .native_project_assignment import _registered
from .workspaces import private_path, private_database

KIND = 'standard_forward_continuation_v1'
FENCE = 'standard-forward-continuation.json'
OUTCOME = 'forward_lineage_recorded_play_not_started'
BOUNDARY = {**successor.BOUNDARY, 'originalAdmissionRetried': False, 'originalReceiptReconstructed': False,
            'claimsRemoved': False, 'brainReloaded': False}
FIELDS = {'version', 'kind', 'sourceHash', 'source', 'target', 'bindingFile', 'bindingPin', 'boundary',
          'partialRequest', 'existingDispositionPin', 'originalMeta', 'preservedRows', 'fileEpochs'}


def source_hash():
    from . import core, workspaces, local_repository_identity, native_project_assignment, native_policy_evidence
    return digest([hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
                   for m in (core, workspaces, partial, successor, standard, missions,
                             local_repository_identity, native_project_assignment, native_policy_evidence)] +
                  [hashlib.sha256(Path(__file__).read_bytes()).hexdigest()])


def valid_request(request):
    return (isinstance(request, dict) and set(request) == FIELDS and type(request['version']) is int and
            request['version'] == 1 and request['kind'] == KIND and request['boundary'] == BOUNDARY and
            all(isinstance(request[name], dict) for name in ('source', 'target', 'partialRequest', 'originalMeta', 'preservedRows', 'fileEpochs')) and
            len(canonical(request).encode()) <= 58000)


def read_request(path):
    before = successor.pin(path)
    value = decode(private_file(path).read_bytes())
    require(successor.pin(path) == before and valid_request(value), 'Closed private forward review required')
    return value


def read_disposition(path, p):
    before = successor.pin(path)
    record = decode(private_file(path).read_bytes())
    require(successor.pin(path) == before and isinstance(record, dict) and
            set(record) == {'kind', 'request', 'reviewHash', 'recordedAt', 'outcome'} and
            isinstance(record['request'], dict) and
            record['kind'] == partial.KIND and record['outcome'] == partial.OUTCOME and
            type(record['recordedAt']) in (int, float) and math.isfinite(record['recordedAt']) and
            record['reviewHash'] == digest(record['request']) and
            record['request'] == {**p, 'sourceHash': record['request'].get('sourceHash')},
            'Exact historical unqualified disposition required; no cleanup inference')
    return record


def rows(db):
    names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('meta','sqlite_sequence') ORDER BY name")]
    result = {name: sorted(digest(list(row)) for row in db.execute('SELECT * FROM "'+name.replace('"', '""')+'"'))
              for name in names}
    require(sum(map(len, result.values())) <= 100, 'Empty target history exceeds forward review bound')
    return result


def file_epochs(p, binding_file):
    paths = [p['originalRequestFile'], binding_file, *(item['path'] for item in p['claims'].values())]
    result = {}
    for path in paths:
        successor.pin(path)
        info = Path(path).lstat()
        result[path] = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                        info.st_uid, info.st_mode, info.st_nlink]
    return result


def context(registry, source, original_path):
    original = successor.read_request(original_path)
    target = partial.reader(original['target']['root'], original['target']['workspaceId'], registry.root)
    require(not os.path.lexists(target.root/FENCE), 'Forward continuation already claimed; never retry')
    existing = os.path.lexists(target.root/partial.FENCE)
    p = partial.context(registry, source, original_path, allow_record=existing)
    if existing: read_disposition(target.root/partial.FENCE, p)
    # Repeat exclusion under the new authority; the old claims are not free capacity.
    successor.disjoint(p['source']['repositories'], p['target']['repositories'])
    successor.other_owners(registry, target, p['target']['repositories'])
    with standard.read_db(target.db) as db:
        meta = target.get(db, 'meta', 1)
        require(not db.execute('SELECT 1 FROM snapshots WHERE kind=?', (KIND,)).fetchone(),
                'A prior forward snapshot cannot be relabelled as new')
        require(all(r['policyProfile'] == 'standard' for r in target.all(db, 'repos')), 'Harness is unchanged')
        mission = missions.state_in(target, db)
        require(mission['document']['spec']['authority']['approvalMode'] == 'phase_delegated',
                'Exact reviewed standard delegation required')
        preserved = rows(db)
    value = {'version': 1, 'kind': KIND, 'sourceHash': source_hash(), 'source': p['source'], 'target': p['target'],
             'bindingFile': original['bindingFile'], 'bindingPin': original['bindingPin'], 'boundary': dict(BOUNDARY),
             'partialRequest': p, 'existingDispositionPin': successor.pin(target.root/partial.FENCE) if existing else None,
             'originalMeta': meta, 'preservedRows': preserved, 'fileEpochs': file_epochs(p, original['bindingFile'])}
    require(valid_request(value), 'Forward review exceeds its closed bound')
    return value


def prepare(registry, source, original_path):
    request = context(registry, source, original_path)
    return {'request': request, 'reviewHash': digest(request), 'validUntil': 'scope_changes',
            'effect': 'Retain original failure as unqualified and record NEW prospective lineage; separate fresh Play required',
            'recordsUnqualifiedDisposition': request['existingDispositionPin'] is None,
            'nativeCollection': False, 'playAuthorized': False, 'originalAdmissionRetried': False,
            'currentTerminalSafety': 'unknown', 'historicalTerminalSafety': 'unknown'}


def backup_files(request):
    files = partial.backup_files(request['partialRequest'])
    if request['existingDispositionPin'] is not None:
        files['prior-disposition.json'] = Path(request['target']['root'])/partial.FENCE
    return files


def create_backup(registry, source, request, destination, *, writers_stopped=False):
    require(writers_stopped is True, 'Quiesced writers required before forward backup')
    require(valid_request(request) and context(registry, source, request['partialRequest']['originalRequestFile']) == request,
            'Forward review changed')
    destination = Path(destination); private_path(destination.parent, existing=True)
    require(destination.is_absolute() and destination.resolve() == destination and not os.path.lexists(destination),
            'New canonical private backup required; never overwrite')
    destination.mkdir(mode=0o700)
    entries = {}
    for name, path in backup_files(request).items():
        copied = destination/name
        fd = os.open(copied, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
        if name.endswith('.sqlite3'):
            os.close(fd)
            with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as src:
                with contextlib.closing(sqlite3.connect(copied)) as dst:
                    src.backup(dst)
                    require(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Forward backup integrity failed')
            entries[name] = {'fingerprint': partial.database_proof(copied)['fingerprint']}
        else:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(private_file(path).read_bytes()); stream.flush(); os.fsync(stream.fileno())
            entries[name] = {'sha256': successor.pin(copied)['sha256']}
        with copied.open('rb') as stream: os.fsync(stream.fileno())
    from .standard_quarantine import exclusive
    exclusive(destination/'forward-request.json', request)
    entries['forward-request.json'] = {'sha256': successor.pin(destination/'forward-request.json')['sha256']}
    require(context(registry, source, request['partialRequest']['originalRequestFile']) == request, 'Scope changed during backup')
    exclusive(destination/'manifest.json', {'kind': KIND+'_backup', 'reviewHash': digest(request), 'files': entries})
    sync_directory(destination); verify_backup(request, destination)
    return {'backup': str(destination), 'verified': True, 'reviewHash': digest(request)}


def verify_backup(request, destination):
    destination = private_path(destination, existing=True)
    manifest = decode(private_file(destination/'manifest.json').read_bytes())
    files = backup_files(request)
    require(set(manifest) == {'kind', 'reviewHash', 'files'} and manifest['kind'] == KIND+'_backup' and
            manifest['reviewHash'] == digest(request) and set(manifest['files']) == set(files)|{'forward-request.json'}, 'Exact forward backup required')
    require(read_request(destination/'forward-request.json') == request and
            successor.pin(destination/'forward-request.json')['sha256'] == manifest['files']['forward-request.json']['sha256'],
            'Backed-up exact forward review changed')
    for name, path in files.items():
        copied = destination/name
        require(copied.resolve() != path.resolve() and copied.stat().st_ino != path.stat().st_ino,
                'Backup aliases original state')
        if name.endswith('.sqlite3'):
            require(partial.database_proof(copied)['fingerprint'] == manifest['files'][name]['fingerprint'] ==
                    request['partialRequest']['databaseProofs'][name[:-8]]['fingerprint'], 'Forward backup database changed')
        else:
            require(successor.pin(copied)['sha256'] == successor.pin(path)['sha256'] == manifest['files'][name]['sha256'],
                    'Forward backup claim, binding or original request changed')


def retained_in(ledger, db, meta=None):
    meta = meta or ledger.get(db, 'meta', 1)
    require(meta.get('schemaVersion') == 7 and meta.get('successorLedgerVersion') == 1 and
            type(meta.get('forwardContinuationVersion')) is int and meta['forwardContinuationVersion'] == 1,
            'Incomplete forward continuation stays fenced')
    marker = decode(private_file(ledger.root/FENCE).read_bytes()); marker_pin = successor.pin(ledger.root/FENCE)
    require(set(marker) == {'kind', 'reviewHash', 'claimedAt'} and marker['kind'] == KIND,
            'Forward intent is incomplete or foreign')
    key = meta.get('standardSuccessor'); record = ledger.get(db, 'snapshots', key); request = record['request']
    require(set(record) == {'kind', 'request', 'reviewHash', 'recordedAt', 'claimPin', 'dispositionPin', 'outcome'} and
            record['kind'] == KIND and record['outcome'] == OUTCOME and valid_request(request) and
            digest(record) == key and record['reviewHash'] == marker['reviewHash'] == digest(request) and
            record['claimPin'] == marker_pin and request['sourceHash'] == source_hash(), 'Forward receipt or source changed')
    target = request['target']; p = request['partialRequest']; old = request['source']
    require(target == p['target'] and old == p['source'] and request['originalMeta']['schemaVersion'] == 1 and
            digest(request['originalMeta']) == target['metaHash'] and
            ledger.workspace_id == target['workspaceId'] and str(ledger.root) == target['root'] and
            meta['brainId'] == target['brainId'], 'Forward target or original scope changed')
    require([ledger.db.stat().st_dev, ledger.db.stat().st_ino] == target['ledgerIdentity'], 'Forward ledger identity changed')
    registry_root = Path(ledger.platform_root)
    registry = SimpleNamespace(root=registry_root, db=private_database(registry_root/'platform.sqlite3'))
    info = registry.db.stat()
    require([info.st_dev, info.st_ino] == target['registryIdentity'] and
            partial.database_proof(Path(old['root'])/'ledger.sqlite3') == p['databaseProofs']['source'],
            'Original source or registry identity changed; old ownership remains held')
    schema = [list(row) for row in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
    require(digest(schema) == p['databaseProofs']['target']['fingerprint']['schemaHash'], 'Original target schema changed')
    original_path = Path(p['originalRequestFile'])
    require(successor.pin(original_path) == p['originalRequestPin'], 'Original attempted review changed')
    original = successor.read_request(original_path)
    require(file_epochs(p, request['bindingFile']) == request['fileEpochs'], 'Original file epoch changed')
    require(digest(original) == p['originalRequestHash'] and request['bindingFile'] == original['bindingFile'] and
            request['bindingPin'] == original['bindingPin'], 'Original request or binding provenance changed')
    local = original.get('identityPolicy') == successor.LOCAL_POLICY
    require(successor.original(old['root'], old['workspaceId'], local_only=local) == old,
            'Old quarantine/run/usage/gap/expiry/holds changed')
    for name, claim in p['claims'].items():
        require(successor.pin(Path(claim['path'])) == claim['pin'] and
                decode(private_file(claim['path']).read_bytes()) == claim['value'], 'Original partial claim changed')
    require(successor.pin(request['bindingFile']) == request['bindingPin'], 'Binding epoch changed; no rebind')
    binding = successor._read_binding(request['bindingFile'])
    # Only the target ledger revision is prospective. Every original native and
    # catalog identity, checkout, binding and policy stays identical.
    scope_target = copy.deepcopy(target)
    _, inspected, _, _ = _registered(registry, ledger.workspace_id)
    scope_target['scope']['ledgerRevision'] = inspected['revision']
    partial.existing_scope(registry, ledger, binding, {'scope': scope_target['scope']})
    registered_root, _, _, _ = _registered(registry, old['workspaceId'])
    require(str(registered_root) == old['root'], 'Original routing changed')
    require(successor.repositories(ledger.all(db, 'repos'), local_only=local) == target['repositories'], 'Target repository changed')
    mission = missions.state_in(ledger, db)
    require(mission['effectiveStatus'] == 'reviewed' and mission['documentHash'] == target['missionHash'] and
            mission['receiptHash'] == target['missionReviewHash'], 'Forward mission changed')
    require(successor.pin(ledger.root/partial.FENCE) == record['dispositionPin'], 'Unqualified disposition changed')
    read_disposition(ledger.root/partial.FENCE, p)
    for name, hashes in request['preservedRows'].items():
        current = [digest(list(row)) for row in db.execute('SELECT * FROM "'+name.replace('"', '""')+'"')]
        require(all(current.count(value) >= hashes.count(value) for value in hashes), 'Original target history changed')
    require(not db.execute('SELECT 1 FROM snapshots WHERE kind=? OR id=?',
                           (successor.KIND, p['claims']['target']['value']['recordHash'])).fetchone(),
            'Original admission must stay uncommitted; no reconstructed success')
    run = meta.get('standardRun')
    if run:
        require(run.get('successorHash') == key and run.get('ownerReceipt', {}).get('successorHash') == key,
                'Only separately confirmed fresh forward Play may own this run')
    return record


def disposition_record(registry, source, request):
    target = partial.reader(request['target']['root'], request['target']['workspaceId'], registry.root)
    with standard.read_db(target.db) as db: record = retained_in(target, db)
    require(record['request']['partialRequest']['source'] == request['source'] and
            source.workspace_id == request['source']['workspaceId'], 'Wrong disposition source route')
    value = read_disposition(target.root/partial.FENCE, record['request']['partialRequest'])
    require(value['request'] == request, 'Different disposition review; never reapply')
    return value


def confirm(registry, source, request, confirmation_hash, *, writers_stopped=False, backup_root=None):
    require(valid_request(request) and confirmation_hash == digest(request), 'Confirm exact NEW forward review, never old admission approval')
    require(source.workspace_id == request['source']['workspaceId'] and str(source.root) == request['source']['root'],
            'Exact original source route required')
    target = partial.reader(request['target']['root'], request['target']['workspaceId'], registry.root)
    if os.path.lexists(target.root/FENCE):
        with standard.read_db(target.db) as db: record = retained_in(target, db)
        require(record['request'] == request, 'Different forward review already claimed')
        return successor.public(record)
    require(writers_stopped is True and backup_root is not None, 'Stopped writers and verified forward backup required')
    with partial.lock(registry.db), partial.lock(target.db) as db:
        require(context(registry, source, request['partialRequest']['originalRequestFile']) == request, 'Forward review scope changed')
        verify_backup(request, backup_root)
        from .standard_quarantine import exclusive
        exclusive(target.root/FENCE, {'kind': KIND, 'reviewHash': confirmation_hash, 'claimedAt': time.time()})
        p = request['partialRequest']
        if request['existingDispositionPin'] is None:
            partial.record_under_locks(registry, source, p)
        else:
            require(successor.pin(target.root/partial.FENCE) == request['existingDispositionPin'], 'Prior disposition changed')
        read_disposition(target.root/partial.FENCE, p)
        record = {'kind': KIND, 'request': request, 'reviewHash': confirmation_hash, 'recordedAt': time.time(),
                  'claimPin': successor.pin(target.root/FENCE), 'dispositionPin': successor.pin(target.root/partial.FENCE),
                  'outcome': OUTCOME}
        key = digest(record)
        require(len(canonical(record).encode()) <= 62000, 'Forward record exceeds its bound')
        db.execute('INSERT INTO snapshots(id,kind,data) VALUES(?,?,?)', (key, KIND, canonical(record)))
        meta = copy.deepcopy(request['originalMeta'])
        meta.update(schemaVersion=7, successorLedgerVersion=1, forwardContinuationVersion=1,
                    standardSuccessor=key, revision=meta['revision']+1)
        Ledger.put(db, 'meta', 1, meta)
        retained_in(target, db, meta)  # Validate the complete new record before commit.
        db.commit()
    return successor.public(record)


def status(registry, target):
    if not os.path.lexists(target.root/FENCE): return {'status': 'not_recorded'}
    try:
        with standard.read_db(target.db) as db: value = successor.public(retained_in(target, db))
        return {'status': 'forward_lineage_recorded', **value}
    except (OSError, Refusal, ValueError, KeyError, TypeError, sqlite3.Error):
        return {'status': 'forward_continuation_incomplete_or_changed', 'writesBlocked': True,
                'playAuthorized': False, 'terminalSafety': 'unknown'}
