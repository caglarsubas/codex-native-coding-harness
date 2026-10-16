"""Owner disposition of an uncommitted successor, never admission completion.

Preserve both original claims and every database. A new exclusive file records
an unqualified failure and keeps the target fenced. No native transport exists.
"""
import contextlib
import hashlib
import os
from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace

from .core import Ledger, Refusal, canonical, digest, require
from . import standard, standard_successor as successor
from .host_lifecycle import private_file, sync_directory
from .native_project_assignment import _registered, _read_registry, UUID
from .app_server_wake import _read_binding
from .workspaces import private_path, private_database, fingerprint

KIND = 'partial_admission_disposition_v1'
FENCE = 'standard-partial-admission-disposition.json'
OUTCOME = 'partial_admission_disposed_unqualified'
BOUNDARY = {'admissionCompleted': False, 'admissionRetryAuthorized': False,
            'claimsRemoved': False, 'oldRunChanged': False, 'usageReset': False,
            'ownershipReleased': False, 'nativeAction': False, 'bindingChanged': False,
            'terminalSafetyVerified': False, 'playAuthorized': False, 'pilotAccepted': False}
FIELDS = {'version', 'kind', 'sourceHash', 'originalRequestFile', 'originalRequestPin',
          'originalRequestHash', 'source', 'target', 'claims', 'databaseProofs', 'boundary'}
MAX_DATABASE = 64 * 1024 * 1024


def source_hash():
    from . import workspaces
    return digest([hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                   for module in (workspaces, successor)] + [hashlib.sha256(Path(__file__).read_bytes()).hexdigest()])


def reader(root, workspace, platform):
    root = private_path(root, existing=True)
    return SimpleNamespace(root=root, db=private_database(root/'ledger.sqlite3'),
                           workspace_id=workspace, platform_root=platform, get=Ledger.get, all=Ledger.all)


def routes(platform, workspace):
    """CLI reads must not instantiate a Registry/Ledger writer on live state."""
    from .workspaces import identity
    identity(workspace)
    root = private_path(platform, existing=True)
    registry = SimpleNamespace(root=root, db=private_database(root/'platform.sqlite3'))
    source_root, _, _, _ = _registered(registry, workspace)
    return registry, reader(source_root, workspace, root)


def database_proof(path):
    path = private_database(path)
    before = path.stat()
    # A disposition is a bounded metadata operation, not a general database exporter.
    require(before.st_size <= MAX_DATABASE and
            (not Path(str(path)+'-wal').exists() or Path(str(path)+'-wal').stat().st_size <= MAX_DATABASE),
            'Disposition database exceeds its explicit bound')
    with standard.read_db(path) as db:
        names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        require(len(names) <= 32 and sum(db.execute('SELECT COUNT(*) FROM "'+name.replace('"', '""')+'"').fetchone()[0]
                                      for name in names) <= 10000, 'Disposition row bound exceeded')
        schema = [list(row) for row in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        proof = {'schemaHash': digest(schema), 'tables': fingerprint(db)}
    after = private_database(path).stat()
    require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino), 'Database identity changed')
    return {'identity': [after.st_dev, after.st_ino], 'fingerprint': proof}


def existing_scope(registry, target, binding, original):
    """Saved catalog/binding bytes only: never validate or connect an endpoint."""
    root, inspected, catalog, mappings = _registered(registry, target.workspace_id)
    meta_brain = inspected['brainId']
    require(set(binding) == {'endpoint', 'brains'} and set(binding['brains']) == {meta_brain},
            'Exact unchanged single-brain binding required')
    brain = binding['brains'][meta_brain]
    require(brain.get('workspaceId') == target.workspace_id and
            brain.get('nativePolicy') in (
                {'sandbox': 'workspace-write', 'approvalPolicy': 'on-request', 'codeMode': False},
                {'sandbox': 'workspace-write', 'approvalPolicy': 'on-request', 'codeMode': False, 'approvalsReviewer': 'user'}) and
            UUID.fullmatch(brain.get('projectId', '')) and UUID.fullmatch(meta_brain),
            'Original restricted project/brain policy changed')
    from .native_policy_evidence import validate_contract
    validate_contract(brain.get('policyEvidence'))
    catalog_id = brain.get('catalogProjectId', brain['projectId'])
    linked = [item for item in (catalog or {}).get('projects', []) if
              item['projectId'] == catalog_id and item['projectKind'] == 'local' and
              (mappings.get(item['key']) or {}).get('workspaceId') == target.workspace_id and
              (mappings.get(item['key']) or {}).get('brainId') == meta_brain and
              (mappings.get(item['key']) or {}).get('databaseIdentity') == inspected['databaseIdentity'] and
              (mappings.get(item['key']) or {}).get('locationHash') == item['locationHash']]
    require(len(linked) == 1 and linked[0]['locationHash'] == digest([linked[0]['hostId'], brain['cwd']]),
            'Both original project identities and exact catalog mapping required')
    scope = {'root': str(root), 'brainId': meta_brain, 'projectId': brain['projectId'],
             'catalogProjectId': catalog_id, 'cwd': brain['cwd'], 'hostId': linked[0]['hostId'],
             'ledgerIdentity': inspected['databaseIdentity'], 'ledgerRevision': inspected['revision'],
             'endpointHash': digest(binding['endpoint']), 'bindingHash': digest(binding),
             'catalogHash': catalog['hash'], 'locationHash': linked[0]['locationHash']}
    require(scope == original['scope'], 'Original saved binding/catalog scope changed')


def context(registry, source, original_path, *, allow_record=False):
    from .enrollment import record_in, fence_exists
    from . import missions
    original_path = private_file(original_path)
    file_pin = successor.pin(original_path)
    original = successor.read_request(original_path)
    require(original['source']['workspaceId'] == source.workspace_id and original['source']['root'] == str(source.root),
            'Exact source route of the original attempted admission required')
    target_id = original['target']['workspaceId']
    root, inspected, _, _ = _registered(registry, target_id)
    target = reader(root, target_id, registry.root)
    require(target_id != source.workspace_id and inspected['brainId'] != original['source']['brainId'],
            'Separate original source and target required')
    require(allow_record or not os.path.lexists(root/FENCE), 'Disposition already claimed; inspect its exact receipt')
    with _read_registry(registry) as rd:
        require(record_in(rd) is None, 'Strict enrollment refuses partial admission disposition')
    local = original.get('identityPolicy') == successor.LOCAL_POLICY
    require(successor.original(source.root, source.workspace_id, local_only=local) == original['source'],
            'Original quarantine, run, usage, gap, expiry or repository identity changed')
    marker_path = root/successor.FENCE
    outgoing_path = successor.source_claim(registry.root, source.workspace_id)
    from .native_read_client import decode
    marker = decode(private_file(marker_path).read_bytes())
    outgoing = decode(private_file(outgoing_path).read_bytes())
    require(isinstance(marker, dict) and set(marker) == {'kind', 'recordHash', 'reviewHash'} and marker['kind'] == successor.KIND and
            isinstance(marker['recordHash'], str) and len(marker['recordHash']) == 64 and
            all(c in '0123456789abcdef' for c in marker['recordHash']) and
            marker['reviewHash'] == digest(original) and
            outgoing == {'kind': successor.KIND, 'target': target_id, 'recordHash': marker['recordHash']},
            'Both matching original partial claims required; missing or ambiguous is not absence')
    with standard.read_db(target.db) as db:
        meta = target.get(db, 'meta', 1)
        require(meta.get('schemaVersion') == 1 and digest(meta) == original['target']['metaHash'] and
                meta.get('paused') is True and not meta.get('standardRun') and not meta.get('standardSuccessor') and
                not meta.get('controller') and not meta.get('runner') and not meta.get('admissionBinding') and
                not os.path.lexists(standard.controller_file(target)) and not fence_exists(root),
                'Only the unchanged empty unowned pre-admission target qualifies')
        require((meta.get('brainControl') or {'desired': 'running', 'phase': 'ready'}) ==
                {'desired': 'running', 'phase': 'ready'} and
                all(not target.all(db, name) for name in ('workers', 'queue', 'commands', 'decisions', 'continuations')),
                'Pending work, stop or controller cannot be disposed of')
        require(not db.execute("SELECT 1 FROM snapshots WHERE kind='standard_successor_v1' OR id=?",
                               (marker['recordHash'],)).fetchone(), 'A committed or ambiguous admission cannot use this path')
        mission = missions.state_in(target, db)
        require(mission['effectiveStatus'] == 'reviewed' and mission['documentHash'] == original['target']['missionHash'] and
                mission['receiptHash'] == original['target']['missionReviewHash'], 'Original reviewed mission changed')
        require(successor.repositories(target.all(db, 'repos'), local_only=local) == original['target']['repositories'],
                'Original target repository scope changed')
    binding_path = private_file(original['bindingFile'])
    require(successor.pin(binding_path) == original['bindingPin'], 'Original binding file epoch changed')
    binding = _read_binding(binding_path)
    require(digest(binding) == original['target']['bindingHash'], 'Original binding bytes changed')
    existing_scope(registry, target, binding, original['target'])
    proofs = {name: database_proof(path) for name, path in
              (('source', source.db), ('target', target.db), ('registry', registry.db))}
    require(proofs['target']['identity'] == original['target']['ledgerIdentity'] and
            proofs['registry']['identity'] == original['target']['registryIdentity'], 'Original database identities changed')
    require(successor.pin(original_path) == file_pin, 'Original attempted review changed during inspection')
    return {'version': 1, 'kind': KIND, 'sourceHash': source_hash(),
            'originalRequestFile': str(original_path), 'originalRequestPin': file_pin,
            'originalRequestHash': digest(original), 'source': original['source'], 'target': original['target'],
            'claims': {'target': {'path': str(marker_path), 'pin': successor.pin(marker_path), 'value': marker},
                       'outgoing': {'path': str(outgoing_path), 'pin': successor.pin(outgoing_path), 'value': outgoing}},
            'databaseProofs': proofs, 'boundary': dict(BOUNDARY)}


def prepare(registry, source, original_path):
    request = context(registry, source, original_path)
    require(len(canonical(request).encode()) <= 60000, 'Disposition review exceeds its closed bound')
    return {'request': request, 'reviewHash': digest(request), 'validUntil': 'scope_changes',
            'outcome': OUTCOME, 'effect': 'Record failed admission as unqualified; preserve both claims and keep target fenced',
            'nativeCollection': False, 'playAuthorized': False}


def read_request(path):
    from .native_read_client import decode
    before = successor.pin(path)
    value = decode(private_file(path).read_bytes())
    require(successor.pin(path) == before and isinstance(value, dict) and set(value) == FIELDS and type(value['version']) is int and
            value['version'] == 1 and value['kind'] == KIND and value['boundary'] == BOUNDARY,
            'Exact closed private disposition review required')
    return value


def backup_files(request):
    return {'source.sqlite3': Path(request['source']['root'])/'ledger.sqlite3',
            'target.sqlite3': Path(request['target']['root'])/'ledger.sqlite3',
            'registry.sqlite3': Path(request['claims']['outgoing']['path']).parent/'platform.sqlite3',
            'original-request.json': Path(request['originalRequestFile']),
            'target-claim.json': Path(request['claims']['target']['path']),
            'outgoing-claim.json': Path(request['claims']['outgoing']['path']),
            'binding.json': Path(successor.read_request(request['originalRequestFile'])['bindingFile'])}


def create_backup(registry, source, request, destination, *, writers_stopped=False):
    require(writers_stopped is True, 'Separately quiesce writers before the explicit backup')
    require(context(registry, source, request['originalRequestFile']) == request, 'Reviewed disposition scope changed')
    destination = Path(destination)
    private_path(destination.parent, existing=True)
    require(destination.is_absolute() and destination.resolve() == destination and not os.path.lexists(destination),
            'New canonical private backup directory required; no overwrite')
    destination.mkdir(mode=0o700)
    files = {}
    for name, path in backup_files(request).items():
        copied = destination/name
        if name.endswith('.sqlite3'):
            os.close(os.open(copied, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
            with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as src:
                with contextlib.closing(sqlite3.connect(copied)) as dst:
                    src.backup(dst)
                    require(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Backup integrity failed')
            proof = database_proof(copied)['fingerprint']
            require(proof == request['databaseProofs'][name[:-8]]['fingerprint'], 'Backup database differs')
            files[name] = {'fingerprint': proof}
        else:
            raw = private_file(path).read_bytes()
            fd = os.open(copied, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            files[name] = {'sha256': hashlib.sha256(raw).hexdigest()}
        with copied.open('rb') as stream: os.fsync(stream.fileno())
    require(context(registry, source, request['originalRequestFile']) == request, 'Scope changed during backup')
    manifest = {'kind': KIND+'_backup', 'reviewHash': digest(request), 'files': files}
    from .standard_quarantine import exclusive
    exclusive(destination/'manifest.json', manifest)
    sync_directory(destination)
    verify_backup(request, destination)
    return {'backup': str(destination), 'reviewHash': digest(request), 'verified': True}


def verify_backup(request, root):
    from .native_read_client import decode
    root = private_path(root, existing=True)
    manifest = decode(private_file(root/'manifest.json').read_bytes())
    paths = backup_files(request)
    require(set(manifest) == {'kind', 'reviewHash', 'files'} and manifest['kind'] == KIND+'_backup' and
            manifest['reviewHash'] == digest(request) and set(manifest['files']) == set(paths), 'Exact verified backup required')
    for name, original in paths.items():
        copied = root/name
        require(copied.resolve() != original.resolve() and copied.stat().st_ino != original.stat().st_ino,
                'Backup cannot alias original state')
        if name.endswith('.sqlite3'):
            require(database_proof(copied)['fingerprint'] ==
                    manifest['files'][name]['fingerprint'] == request['databaseProofs'][name[:-8]]['fingerprint'],
                    'Backup database contents changed')
        else:
            require(successor.pin(copied)['sha256'] == hashlib.sha256(private_file(original).read_bytes()).hexdigest() ==
                    manifest['files'][name]['sha256'], 'Backup claim, request or binding differs')


@contextlib.contextmanager
def lock(path):
    private_database(path)
    with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=rw', uri=True)) as db:
        db.execute('BEGIN IMMEDIATE')
        try: yield
        finally: db.rollback()  # No SQL mutation/commit in the disposition adapter.


def public(record):
    return {'status': OUTCOME, 'recordHash': digest(record), 'reviewHash': record['reviewHash'],
            'recordedAt': record['recordedAt'], 'originalReviewHash': record['request']['originalRequestHash'],
            'targetWorkspaceId': record['request']['target']['workspaceId'], 'writesBlocked': True,
            'currentTerminalSafety': 'unknown', 'historicalTerminalSafety': 'unknown', 'boundary': dict(BOUNDARY)}


def retained(registry, source, request):
    from .native_read_client import decode
    path = Path(request['target']['root'])/FENCE
    record = decode(private_file(path).read_bytes())
    require(isinstance(record, dict) and set(record) == {'kind', 'request', 'reviewHash', 'recordedAt', 'outcome'} and
            record['kind'] == KIND and record['request'] == request and record['reviewHash'] == digest(request) and
            record['outcome'] == OUTCOME and context(registry, source, request['originalRequestFile'], allow_record=True) == request,
            'Disposition is incomplete or changed; all original claims remain fenced')
    return record


def confirm(registry, source, request, confirmation_hash, *, writers_stopped=False, backup_root=None):
    require(isinstance(request, dict) and set(request) == FIELDS and type(request['version']) is int and
            request['version'] == 1 and request['kind'] == KIND and request['boundary'] == BOUNDARY and
            len(canonical(request).encode()) <= 60000 and
            confirmation_hash == digest(request), 'Confirm only the separately displayed exact disposition review')
    path = Path(request['target']['root'])/FENCE
    if os.path.lexists(path): return public(retained(registry, source, request))
    require(writers_stopped is True and backup_root is not None, 'Stopped writers and verified private backup required')
    with lock(registry.db), lock(Path(request['target']['root'])/'ledger.sqlite3'):
        require(context(registry, source, request['originalRequestFile']) == request, 'Disposition scope changed')
        verify_backup(request, backup_root)
        record = {'kind': KIND, 'request': request, 'reviewHash': confirmation_hash,
                  'recordedAt': time.time(), 'outcome': OUTCOME}
        from .standard_quarantine import exclusive
        exclusive(path, record)
        # Never reconstruct the original admission, its missing timestamp or receipt.
        require(retained(registry, source, request) == record, 'Post-disposition state changed; no retry')
    return public(record)


def status(registry, target):
    path = target.root/FENCE
    if not os.path.lexists(path): return {'status': 'not_recorded'}
    try:
        from .native_read_client import decode
        record = decode(private_file(path).read_bytes())
        request = record['request']
        source = reader(request['source']['root'], request['source']['workspaceId'], registry.root)
        require(request['target']['workspaceId'] == target.workspace_id and
                request['target']['root'] == str(target.root), 'Foreign disposition file')
        return public(retained(registry, source, request))
    except (OSError, Refusal, ValueError, KeyError, TypeError, sqlite3.Error):
        return {'status': 'partial_disposition_incomplete_or_changed', 'writesBlocked': True,
                'playAuthorized': False, 'terminalSafety': 'unknown'}
