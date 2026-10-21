"""Non-waking owner disposition of one canceled, unreceived pre-Play check.

The original command stays byte-for-byte intact. This is an unqualified local
outcome, never a catalog/error from the brain or evidence of terminal cleanup.
"""
import contextlib
import math
import os
from pathlib import Path
import sqlite3
import time

from .core import Ledger, Refusal, SHA, canonical, digest, require
from . import missions, partial_admission as partial, standard
from .app_server_wake import _read_binding, NATIVE_APPROVAL_POLICY
from .host_lifecycle import private_file, sync_directory
from .native_project_assignment import _registered, _read_registry, UUID
from .native_read_client import decode
from .standard_quarantine import exclusive
from .standard_successor import pin
from .workspaces import private_path, private_database

KIND = 'standard_readiness_disposition_v1'
FENCE = 'standard-readiness-disposition.json'
OUTCOME = 'canceled_readiness_unqualified'
BOUNDARY = {'brainReceiptReconstructed': False, 'catalogRecorded': False,
            'nativeAction': False, 'brainReloaded': False, 'requestReplayed': False,
            'playAuthorized': False, 'usageReset': False, 'bindingChanged': False,
            'terminalSafety': 'unknown', 'pilotAccepted': False}
FIELDS = {'version', 'kind', 'sourceHash', 'workspaceId', 'brainId', 'root',
          'command', 'metaHash', 'missionHash', 'reviewHash', 'bindingFile',
          'bindingPin', 'bindingEpoch', 'bindingHash', 'scope', 'databaseProofs', 'boundary'}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def source_hash():
    from .standard_preplay import source_hash as implementation_hash
    return implementation_hash()  # Pin every orchestrator module, including CLI and validators.


def original_in(ledger, db, command_id):
    """Only retained original-owned metadata; no native inspection or safety claim."""
    from .brain_control import stopped
    from .enrollment import fence_exists
    meta = ledger.get(db, 'meta', 1)
    require(not any(os.path.lexists(ledger.root/name) for name in (
                'standard-successor.json', 'standard-forward-continuation.json',
                'standard-partial-admission-disposition.json', 'standard-quarantine.json')) and
            not any(name in meta for name in ('standardSuccessor', 'standardQuarantine',
                                              'forwardContinuationVersion', 'successorLedgerVersion')),
            'Admission, successor and quarantine claims cannot use first-phase readiness disposition')
    require(meta.get('schemaVersion') == 1 and meta.get('paused') is True and
            meta.get('standardRun') is None and meta.get('controller') is None and
            meta.get('runner') is None and not stopped(meta) and not meta.get('brainHandoff') and
            not meta.get('admissionBinding') and not fence_exists(ledger.root) and
            not os.path.lexists(standard.controller_file(ledger)),
            'Only an empty, unowned, unstopped first-phase standard project qualifies')
    require(all(not ledger.all(db, table) for table in ('workers', 'queue', 'decisions', 'continuations')),
            'Existing task, packet or decision ownership cannot be disposed of')
    repos = ledger.all(db, 'repos')
    require(repos and all(r['policyProfile'] == 'standard' for r in repos), 'Strict Harness is unchanged')
    mission = missions.state_in(ledger, db)
    require(mission['effectiveStatus'] == 'reviewed' and
            mission['document']['spec']['authority']['approvalMode'] == 'phase_delegated',
            'The exact reviewed first-phase mission is required')
    commands = ledger.all(db, 'commands')
    require(len(commands) == 1 and commands[0]['id'] == command_id,
            'Only the single original readiness request is covered')
    command = commands[0]
    require(command.get('kind') == standard.CATALOG_REFRESH_KIND and command.get('status') == 'queued' and
            command.get('actor') in ('dashboard', 'assistant_owner_confirmed') and
            set(command.get('payload', {})) == {'brainId', 'contextHash', 'missionHash'} and
            command['payload']['brainId'] == meta['brainId'] and
            command['payload']['missionHash'] == mission['documentHash'] and
            not any(k in command for k in ('catalogReceipt', 'catalogError', 'receivedAt', 'completedAt')) and
            not command.get('notificationHistory'), 'Exact original unreceived readiness request required')
    n = command.get('notification') or {}
    observer = n.get('nativeThreadObservation') or {}
    approvals = n.get('nativeApprovals') or []
    permission = n.get('nativePermissionObservation') or {}
    profile = n.get('nativeResumeProfile') or {}
    turn = n.get('nativeTurnId')
    require(n.get('status') == 'accepted' and n.get('nativeDelivery') == 'owned_turn_start' and
            n.get('brainId') == meta['brainId'] and n.get('wakeId') == digest({'commandId': command_id}) and
            isinstance(turn, str) and UUID.fullmatch(turn) and n.get('nativeTurnStatus') == 'interrupted' and
            not n.get('preplayCatalog') and not n.get('turnRecovery') and
            observer.get('version') == 1 and observer.get('rootThreadId') == meta['brainId'] and
            observer.get('nativeTurnId') == turn and observer.get('streamStatus') == 'closed' and
            observer.get('events') == [] and observer.get('complete') is False and
            finite(observer.get('monitoringEndedAt')) and
            0 < observer['monitoringEndedAt'] <= time.time() and
            len(approvals) == 1 and approvals[0].get('turnId') == turn and
            approvals[0].get('decision') == 'cancel' and approvals[0].get('status') == 'resolved' and
            permission.get('version') == 1 and permission.get('turnId') == turn and
            permission.get('reason') == 'native_resolved' and
            isinstance(permission.get('requestHash'), str) and SHA.fullmatch(permission['requestHash']) and
            permission['requestHash'] == approvals[0].get('requestHash') and
            profile.get('version') == 1 and profile.get('brainId') == meta['brainId'] and
            profile.get('commandId') == command_id and profile.get('nativeTurnId') == turn and
            profile.get('requested') == NATIVE_APPROVAL_POLICY and profile.get('resumeAcknowledged') is True,
            'Require resolved owner Cancel, interrupted exact turn, closed original observer and restricted profile')
    require(all(finite(v) for v in (approvals[0].get('claimedAt'), approvals[0].get('observedAt'),
                                   permission.get('endedAt'))) and
            0 < approvals[0]['claimedAt'] <= approvals[0]['observedAt'] <= permission['endedAt'] <=
            observer['monitoringEndedAt'], 'Original Cancel resolution and observer-close ordering required')
    return meta, mission, command


def binding_scope(registry, ledger, binding):
    """Validate saved catalog/checkout pins without touching a socket or process."""
    root, inspected, catalog, mappings = _registered(registry, ledger.workspace_id)
    brain_id = inspected['brainId']
    require(root == ledger.root and set(binding['brains']) == {brain_id}, 'Exact registered single-brain route required')
    brain = binding['brains'][brain_id]
    cwd = brain.get('cwd')
    require(brain.get('workspaceId') == ledger.workspace_id and brain.get('nativePolicy') in (
            NATIVE_APPROVAL_POLICY, {**NATIVE_APPROVAL_POLICY, 'approvalsReviewer': 'user'}) and
            UUID.fullmatch(brain.get('projectId', '')) and UUID.fullmatch(brain_id) and
            isinstance(cwd, str) and Path(cwd).is_absolute() and str(Path(cwd).resolve(strict=True)) == cwd and
            ledger.root.is_relative_to(Path(cwd)) and ledger.root != Path(cwd),
            'Unchanged restricted policy, native project and exact checkout required')
    catalog_id = brain.get('catalogProjectId', brain['projectId'])
    linked = [item for item in (catalog or {}).get('projects', []) if
              item['projectId'] == catalog_id and item['projectKind'] == 'local' and
              (mappings.get(item['key']) or {}).get('workspaceId') == ledger.workspace_id and
              (mappings.get(item['key']) or {}).get('brainId') == brain_id and
              (mappings.get(item['key']) or {}).get('databaseIdentity') == inspected['databaseIdentity'] and
              (mappings.get(item['key']) or {}).get('locationHash') == item['locationHash']]
    require(len(linked) == 1 and linked[0]['hostId'] == 'local' and
            linked[0]['locationHash'] == digest(['local', cwd]), 'Both exact saved native project identities are required')
    return {'projectId': brain['projectId'], 'catalogProjectId': catalog_id, 'checkout': cwd,
            'ledgerIdentity': inspected['databaseIdentity'], 'catalogHash': catalog['hash'],
            'locationHash': linked[0]['locationHash']}


def context(registry, ledger, binding_file, command_id):
    from .enrollment import record_in
    require(not os.path.lexists(ledger.root/FENCE), 'Readiness disposition already claimed; inspect, never reapply')
    with _read_registry(registry) as db:
        require(record_in(db) is None, 'Strict enrollment refuses readiness disposition')
    with standard.read_db(ledger.db) as db:
        meta, mission, command = original_in(ledger, db, command_id)
    binding_file = private_file(binding_file)
    binding_pin = pin(binding_file)
    binding_epoch = file_epoch(binding_file)
    binding = _read_binding(binding_file)
    scope = binding_scope(registry, ledger, binding)
    require(command['notification']['nativeResumeProfile'].get('bindingHash') == digest(binding),
            'Original reviewed binding changed; no migration is included')
    proofs = {name: partial.database_proof(path) for name, path in
              (('target', ledger.db), ('registry', registry.db))}
    require(pin(binding_file) == binding_pin and file_epoch(binding_file) == binding_epoch, 'Binding file changed during review')
    return {'version': 1, 'kind': KIND, 'sourceHash': source_hash(),
            'workspaceId': ledger.workspace_id, 'brainId': meta['brainId'], 'root': str(ledger.root),
            'command': command, 'metaHash': digest(meta), 'missionHash': mission['documentHash'],
            'reviewHash': mission['receiptHash'], 'bindingFile': str(binding_file), 'bindingPin': binding_pin,
            'bindingEpoch': binding_epoch,
            'bindingHash': digest(binding), 'scope': scope, 'databaseProofs': proofs, 'boundary': dict(BOUNDARY)}


def valid_request(value):
    return (isinstance(value, dict) and set(value) == FIELDS and type(value['version']) is int and
            value['version'] == 1 and value['kind'] == KIND and value['boundary'] == BOUNDARY and
            len(canonical(value).encode()) <= 58000)


def prepare(registry, ledger, binding_file, command_id):
    request = context(registry, ledger, binding_file, command_id)
    require(valid_request(request), 'Readiness disposition review exceeds its closed bound')
    return {'request': request, 'reviewHash': digest(request), 'validUntil': 'scope_changes',
            'effect': 'Retire this canceled readiness check as unqualified, without reconstructing its missing brain receipt',
            'boundary': dict(BOUNDARY)}


def read_request(file):
    before = pin(file)
    value = decode(private_file(file).read_bytes())
    require(pin(file) == before and valid_request(value), 'Closed private readiness disposition review required')
    return value


def create_backup(registry, ledger, request, destination, *, writers_stopped=False):
    require(writers_stopped is True and valid_request(request), 'Quiesced writers and exact readiness review required')
    require(context(registry, ledger, request['bindingFile'], request['command']['id']) == request, 'Reviewed scope changed')
    destination = Path(destination)
    private_path(destination.parent, existing=True)
    require(destination.is_absolute() and destination.resolve() == destination and not os.path.lexists(destination),
            'New canonical private backup directory required')
    destination.mkdir(mode=0o700)
    files = {}
    for name, original in (('target.sqlite3', ledger.db), ('registry.sqlite3', registry.db)):
        copied = destination/name
        os.close(os.open(copied, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
        with standard.read_db(original) as src, contextlib.closing(sqlite3.connect(copied)) as dst:
            src.backup(dst)
            require(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Backup integrity failed')
        require(partial.database_proof(copied)['fingerprint'] == request['databaseProofs'][name[:-8]]['fingerprint'],
                'Backup does not preserve reviewed rows')
        with copied.open('rb') as stream: os.fsync(stream.fileno())
        files[name] = database_epoch(copied)
    for name, raw in (('binding.json', private_file(request['bindingFile']).read_bytes()),
                      ('review.json', canonical(request).encode())):
        fd = os.open(destination/name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        files[name] = pin(destination/name)
    require(context(registry, ledger, request['bindingFile'], request['command']['id']) == request, 'Scope changed during backup')
    manifest = {'kind': KIND+'_backup', 'reviewHash': digest(request), 'files': files}
    exclusive(destination/'manifest.json', manifest)
    return {'backup': str(destination), 'reviewHash': digest(request), 'verified': True}


def verify_backup(request, root):
    root = private_path(root, existing=True)
    manifest = decode(private_file(root/'manifest.json').read_bytes())
    require(manifest.get('kind') == KIND+'_backup' and manifest.get('reviewHash') == digest(request) and
            set(manifest.get('files', {})) == {'target.sqlite3', 'registry.sqlite3', 'binding.json', 'review.json'},
            'Exact verified private backup required')
    for name, saved_pin in manifest['files'].items():
        actual = database_epoch(root/name) if name.endswith('.sqlite3') else pin(root/name)
        require(actual == saved_pin, 'Backup file epoch changed')
    for name, proof in request['databaseProofs'].items():
        require(partial.database_proof(root/(name+'.sqlite3'))['fingerprint'] == proof['fingerprint'] and
                database_identity(root/(name+'.sqlite3')) != proof['identity'], 'Backup differs or aliases original')
    require((root/'binding.json').read_bytes() == private_file(request['bindingFile']).read_bytes() and
            decode((root/'review.json').read_bytes()) == request, 'Backup binding or review changed')


def database_identity(path):
    info = private_database(path).stat()
    return [info.st_dev, info.st_ino]


def database_epoch(path):
    info = private_database(path).stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def file_epoch(path):
    info = private_file(path).stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_mode, info.st_uid, info.st_nlink]


def retained_in(ledger, db):
    """Permanent original-ID fence. A partial/corrupt claim never permits writes."""
    rows = db.execute('SELECT id,data FROM snapshots WHERE kind=?', (KIND,)).fetchall()
    if not os.path.lexists(ledger.root/FENCE):
        require(not rows, 'Readiness disposition claim missing; no downgrade or replay')
        return None
    claim = decode(private_file(ledger.root/FENCE).read_bytes())
    require(len(rows) == 1, 'Readiness disposition incomplete; never reapply its claim')
    record = decode(rows[0]['data'].encode())
    request = record.get('request') or {}
    require(set(record) == {'kind', 'request', 'reviewHash', 'recordedAt', 'claimPin', 'outcome'} and
            record['kind'] == KIND and record['outcome'] == OUTCOME and valid_request(request) and
            digest(record) == rows[0]['id'] and record['reviewHash'] == digest(request) and
            claim == {'kind': KIND, 'reviewHash': digest(request)} and
            pin(ledger.root/FENCE) == record['claimPin'] and request['root'] == str(ledger.root) and
            request['workspaceId'] == getattr(ledger, 'workspace_id', None) and
            request['databaseProofs']['target']['identity'] == database_identity(ledger.db) and
            ledger.get(db, 'meta', 1)['brainId'] == request['brainId'] and
            ledger.get(db, 'commands', request['command']['id']) == request['command'],
            'Readiness disposition or original command changed; no retry or receipt reconstruction')
    return record


def public(record):
    return {'status': 'disposed_unqualified', 'commandId': record['request']['command']['id'],
            'recordHash': digest(record), 'recordedAt': record['recordedAt'],
            'originalStatus': record['request']['command']['status'], 'brainReceipt': 'missing',
            'boundary': dict(BOUNDARY)}


def retired_in(ledger, db, command_id):
    record = retained_in(ledger, db)
    if record and record['request']['command']['id'] == command_id:
        return True
    from .readiness_prestart_resolution import retained_in as prestart_retained
    record = prestart_retained(ledger, db)
    return bool(record and record['request']['command']['id'] == command_id)


def confirm(registry, ledger, request, confirmation_hash, *, writers_stopped=False, backup_root=None):
    require(valid_request(request) and confirmation_hash == digest(request) and
            request['workspaceId'] == ledger.workspace_id and request['root'] == str(ledger.root),
            'Confirm this exact readiness disposition, not a prior approval')
    if os.path.lexists(ledger.root/FENCE):
        with standard.read_db(ledger.db) as db: record = retained_in(ledger, db)
        require(record['request'] == request, 'Different disposition already claimed')
        return public(record)  # Lost response: read original receipt, never reapply.
    require(writers_stopped is True and backup_root is not None, 'Quiesced writers and verified backup required')
    with partial.lock(registry.db), partial.lock(ledger.db) as db:
        require(context(registry, ledger, request['bindingFile'], request['command']['id']) == request, 'Reviewed scope changed')
        verify_backup(request, backup_root)
        exclusive(ledger.root/FENCE, {'kind': KIND, 'reviewHash': confirmation_hash})
        record = {'kind': KIND, 'request': request, 'reviewHash': confirmation_hash, 'recordedAt': time.time(),
                  'claimPin': pin(ledger.root/FENCE), 'outcome': OUTCOME}
        require(len(canonical(record).encode()) <= 62000, 'Disposition record exceeds its closed bound')
        db.execute('INSERT INTO snapshots VALUES(?,?,?)', (digest(record), KIND, canonical(record)))
        # No original command, meta/run, usage, registry, binding or receipt edit.
        retained_in(ledger, db)
        sync_directory(ledger.root)
        db.commit()
    return public(record)


def status(ledger):
    try:
        with standard.read_db(ledger.db) as db: record = retained_in(ledger, db)
        return public(record) if record else {'status': 'not_recorded'}
    except (OSError, Refusal, ValueError, KeyError, TypeError, sqlite3.Error):
        return {'status': 'incomplete_or_changed', 'writesBlocked': True, 'boundary': dict(BOUNDARY)}
