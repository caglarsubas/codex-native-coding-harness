"""Owner-reviewed local disposition, not cleanup, closeout or continuation.

The original run/commands remain byte-for-byte values. A permanent filesystem
claim and schema marker fence all later writes, including a partial disposition.
No native endpoint is opened and no controller or resource is released.
"""
import copy
import hashlib
import os
from pathlib import Path
import time
from types import SimpleNamespace

from .core import Ledger, canonical, digest, require
from . import effect_capture, standard
from .enrollment import fence_exists, record_in
from .host_lifecycle import private_file, sync_directory
from .native_project_assignment import UUID, _read_registry, _registered
from .native_read_client import decode
from .app_server_wake import _read_binding
from .standard_host_inspection import binding_file

KIND = 'standard_quarantine_v1'
FENCE = 'standard-quarantine.json'
BOUNDARY = {'historicalTerminalSafety': 'unknown', 'currentTerminalSafety': 'unknown',
            'cleanupVerified': False, 'ownershipReleased': False, 'usageReset': False,
            'expiryChanged': False, 'nativeAction': False, 'continuationAuthorized': False,
            'pilotAccepted': False}
FIELDS = {'version', 'kind', 'sourceHash', 'workspaceId', 'ledgerIdentity',
          'registryIdentity', 'catalogHash', 'originalBindingScope', 'state', 'captureHash', 'boundary'}


def source_hash():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def fenced(root, meta):
    return os.path.lexists(Path(root)/FENCE) or meta.get('schemaVersion') == 6 or 'standardQuarantine' in meta


def exclusive(path, value):
    data = canonical(value).encode()
    require(len(data) <= 65536, 'Quarantine record exceeds its bound; no truncation')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    sync_directory(path.parent)


def state_in(ledger, db):
    return {'meta': ledger.get(db, 'meta', 1), **{
        table: sorted(ledger.all(db, table), key=lambda row: row['id'])
        for table in ('repos', 'commands', 'workers', 'queue', 'decisions', 'continuations')}}


def context(registry, ledger, registry_db, db):
    require(record_in(registry_db) is None and not fence_exists(ledger.root), 'Strict enrollment refuses quarantine')
    state = state_in(ledger, db); meta = state['meta']; run = meta.get('standardRun') or {}
    require(not fenced(ledger.root, meta), 'Quarantine already claimed; inspect its retained disposition')
    require(meta.get('schemaVersion') == 4 and meta.get('paused') is True and
            run.get('protocol') == standard.PROTOCOL and run.get('brainId') == meta['brainId'] and
            run.get('status') == 'paused' and time.time() >= run['expiresAt'] and
            not run.get('tasks') and not run.get('merges') and
            not meta.get('controller') and not meta.get('runner') and not meta.get('admissionBinding'),
            'Only an expired empty unowned paused schema-v4 standard run may be quarantined')
    control = meta.get('brainControl') or {'desired': 'running', 'phase': 'ready'}
    require((control.get('desired'), control.get('phase')) == ('running', 'ready') and
            not standard.controller_file(ledger).exists(), 'Brain Stop or a private controller retains ownership')
    require(state['repos'] and all(r['policyProfile'] == 'standard' for r in state['repos']) and
            not state['workers'] and not state['queue'] and
            not any(d.get('status') not in {'resolved', 'superseded'} for d in state['decisions']) and
            not any(c['status'] in {'queued', 'processing'} or
                    (c.get('notification') or {}).get('status') in {'sending', 'uncertain'}
                    for c in state['commands']), 'Pending work or control cannot be disposed of')
    plays = [c for c in state['commands'] if c['kind'] == 'standard_play' and
             c.get('payload', {}).get('runId') == run['id']]
    require(len(plays) == 1 and plays[0]['status'] == 'completed', 'Sole completed original Play required')
    note = plays[0].get('notification') or {}; observed = note.get('nativeThreadObservation') or {}
    require(note.get('status') == 'accepted' and note.get('nativeDelivery') == 'owned_turn_start' and
            note.get('brainId') == meta['brainId'] and note.get('hostRunId') == run['id'] and
            note.get('nativeTurnStatus') in {'completed', 'failed', 'interrupted'} and
            observed.get('streamStatus') == 'closed' and observed.get('rootThreadId') == meta['brainId'] and
            observed.get('nativeTurnId') == note.get('nativeTurnId') and
            observed.get('events') == [] and not note.get('nativeApprovals'),
            'Original delivery/ended observer must be known; approval or descendant uncertainty retains ownership')
    root, inspected, catalog, mappings = _registered(registry, ledger.workspace_id)
    require(root == ledger.root and inspected['brainId'] == meta['brainId'], 'Registered ledger/brain changed')
    binding = note.get('hostBindingHash')
    require(isinstance(binding, str) and len(binding) == 64, 'Original binding hash required')
    original = _read_binding(binding_file(ledger, binding))  # Bytes only; never validate/connect the old endpoint.
    require(digest(original) == binding and set(original['brains']) == {meta['brainId']}, 'Original binding changed')
    brain = original['brains'][meta['brainId']]
    require(isinstance(brain.get('projectId'), str) and UUID.fullmatch(brain['projectId']) and
            isinstance(brain.get('catalogProjectId'), str) and UUID.fullmatch(brain['catalogProjectId']) and
            brain.get('nativePolicy', {}).get('codeMode') is False and
            brain.get('workspaceId') == ledger.workspace_id and
            brain.get('nativePolicy') in ({'approvalPolicy': 'on-request', 'sandbox': 'workspace-write', 'codeMode': False},
                                         {'approvalPolicy': 'on-request', 'sandbox': 'workspace-write', 'codeMode': False, 'approvalsReviewer': 'user'}) and
            any(r['path'] == brain.get('cwd') for r in state['repos']), 'Original restricted identity/scope required')
    linked = [item for item in (catalog or {}).get('projects', []) if item['projectKind'] == 'local' and
              item['projectId'] == brain.get('catalogProjectId', brain.get('projectId')) and
              item['locationHash'] == digest([item['hostId'], brain['cwd']]) and
              (mappings.get(item['key']) or {}).get('workspaceId') == ledger.workspace_id and
              (mappings.get(item['key']) or {}).get('brainId') == meta['brainId']]
    require(len(linked) == 1, 'Both original native identities and catalog mapping must remain pinned')
    # No original endpoint is opened. All existing unknowns stay in the old run.
    require(run.get('identities') and all(isinstance(v, str) and len(v) == 64 for v in run['identities'].values()),
            'Recorded repository identities must remain reserved')
    identities = set(run['identities'].values())
    for other in registry_db.execute('SELECT root FROM workspaces WHERE id<>?', (ledger.workspace_id,)):
        with standard.read_db(Path(other['root'])/'ledger.sqlite3') as foreign:
            foreign_meta = ledger.get(foreign, 'meta', 1)
            foreign_run = foreign_meta.get('standardRun') or {}
            require(not ledger.all(foreign, 'workers') and
                    not any(t.get('repositoryIdentity') in identities and t.get('status') not in standard.TERMINAL
                            for t in foreign_run.get('tasks', [])) and
                    not any(m.get('repositoryIdentity') in identities and m.get('status') in {'prepared', 'issued', 'uncertain'}
                            for m in foreign_run.get('merges', [])), 'Conflicting foreign ownership must be reconciled first')
    capture = effect_capture.retained(ledger, plays[0])
    li, ri = ledger.db.stat(), registry.db.stat()
    return {'version': 1, 'kind': KIND, 'sourceHash': source_hash(), 'workspaceId': ledger.workspace_id,
            'ledgerIdentity': [li.st_dev, li.st_ino], 'registryIdentity': [ri.st_dev, ri.st_ino],
            'originalBindingScope': {k: brain.get(k) for k in ('workspaceId', 'cwd', 'projectId', 'catalogProjectId', 'nativePolicy')},
            'catalogHash': digest({'catalog': catalog, 'mappings': mappings}), 'state': state,
            'captureHash': digest(capture), 'boundary': copy.deepcopy(BOUNDARY)}


def prepare(registry, ledger):
    with _read_registry(registry) as registry_db, standard.read_db(ledger.db) as db:
        request = context(registry, ledger, registry_db, db)
    require(len(canonical(request).encode()) <= 65536, 'Quarantine review exceeds its bound')
    return {'request': request, 'reviewHash': digest(request), 'validUntil': 'scope_changes',
            'outcome': 'quarantined_unqualified', 'runUnchanged': True,
            'next': 'Planning only. Repository holds remain; no Resume, successor Play or native load is granted.'}


def read_request(path):
    path = private_file(path); info = path.stat()
    require(info.st_nlink == 1, 'Quarantine review cannot have write aliases')
    raw = path.read_bytes()
    require(len(raw) <= 65536 and path.stat() == info, 'Quarantine review changed')
    value = decode(raw)
    require(isinstance(value, dict) and set(value) == FIELDS and value['version'] == 1 and
            type(value['version']) is int and value['kind'] == KIND and value['boundary'] == BOUNDARY,
            'Exact closed quarantine review required')
    return value


def retained_in(ledger, db, meta=None):
    meta = meta or ledger.get(db, 'meta', 1)
    require(fenced(ledger.root, meta), 'No quarantine disposition is retained')
    marker_path = private_file(ledger.root/FENCE)
    require(marker_path.stat().st_nlink == 1, 'Quarantine claim cannot have write aliases')
    marker = decode(marker_path.read_bytes())
    require(isinstance(marker, dict) and set(marker) == {'kind', 'recordHash', 'reviewHash'} and marker['kind'] == KIND,
            'Quarantine claim is incomplete or corrupt; all writes remain fenced')
    key = meta.get('standardQuarantine')
    require(meta.get('schemaVersion') == 6 and meta.get('quarantineLedgerVersion') == 1 and key == marker['recordHash'],
            'Quarantine commit is incomplete; no retry or ownership release')
    record = ledger.get(db, 'snapshots', key)
    require(digest(record) == key and record['reviewHash'] == marker['reviewHash'] == digest(record['request']) and
            record['outcome'] == 'quarantined_unqualified' and record['request']['boundary'] == BOUNDARY,
            'Quarantine history integrity changed')
    old = record['request']['state']; expected_meta = copy.deepcopy(old['meta'])
    expected_meta.update(schemaVersion=6, quarantineLedgerVersion=1, standardQuarantine=key,
                         revision=old['meta']['revision']+1)
    require(meta == expected_meta, 'Original quarantined state changed')
    for table in ('repos', 'commands', 'workers', 'queue', 'decisions', 'continuations'):
        require(sorted(ledger.all(db, table), key=lambda row: row['id']) == old[table], 'Original quarantined records changed')
    return record


def confirm(registry, ledger, request, confirmation_hash):
    require(isinstance(request, dict) and set(request) == FIELDS and confirmation_hash == digest(request) and
            request['kind'] == KIND and request['boundary'] == BOUNDARY, 'Confirm the exact quarantine review hash')
    require(len(canonical(request).encode()) <= 65536, 'Quarantine review exceeds its bound')
    # Repeated confirmation only reads the exact retained receipt, never writes.
    with standard.read_db(ledger.db) as db:
        meta = ledger.get(db, 'meta', 1)
        if fenced(ledger.root, meta):
            record = retained_in(ledger, db, meta)
            require(record['request'] == request, 'Another quarantine already owns this ledger')
            return receipt(record)
    with registry.tx() as registry_db, ledger.tx() as db:
        require(context(registry, ledger, registry_db, db) == request, 'Quarantine scope changed; old review is not authority')
        record = {'kind': KIND, 'request': copy.deepcopy(request), 'reviewHash': confirmation_hash,
                  'outcome': 'quarantined_unqualified', 'recordedAt': time.time()}
        key = digest(record)
        # Permanent file first: interruption never reopens authority or retries.
        exclusive(ledger.root/FENCE, {'kind': KIND, 'recordHash': key, 'reviewHash': confirmation_hash})
        db.execute('INSERT INTO snapshots(id,kind,data) VALUES(?,?,?)', (key, KIND, canonical(record)))
        meta = copy.deepcopy(request['state']['meta'])
        meta.update(schemaVersion=6, quarantineLedgerVersion=1, standardQuarantine=key,
                    revision=meta['revision']+1)
        ledger.put(db, 'meta', 1, meta)
    return receipt(record)


def receipt(record):
    return {'kind': KIND, 'recordHash': digest(record), 'reviewHash': record['reviewHash'],
            'outcome': record['outcome'], 'recordedAt': record['recordedAt'],
            'runId': record['request']['state']['meta']['standardRun']['id'],
            'boundary': copy.deepcopy(BOUNDARY)}


def status(ledger):
    with standard.read_db(ledger.db) as db:
        meta = ledger.get(db, 'meta', 1)
        if not fenced(ledger.root, meta): return {'status': 'not_quarantined'}
        try: return {'status': 'quarantined_unqualified', **receipt(retained_in(ledger, db, meta))}
        except (OSError, ValueError, KeyError, TypeError):
            return {'status': 'quarantine_incomplete_or_changed', 'writesBlocked': True,
                    'boundary': copy.deepcopy(BOUNDARY)}


def repository_holds(root, db, meta):
    # Read-only view over the caller's already locked foreign database, not a
    # Ledger constructor (which would initialize a writer or take another lock).
    reader = SimpleNamespace(root=Path(root), get=Ledger.get, all=Ledger.all)
    record = retained_in(reader, db, meta)
    return set(record['request']['state']['meta']['standardRun']['identities'].values())
