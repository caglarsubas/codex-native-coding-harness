"""Prospective checkout-local standard run control on the original observer.

Closed data operations only. No arbitrary command/RPC, socket credential,
permission response, native load, new owner authority or historical backfill.
"""
import contextlib
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time

from .core import Refusal, canonical, digest, require
from .standard_preplay import SOURCE, source_hash, _identity
from .standard_host_inspection import _read_private, _write_once

TRANSPORT = 'standard_run_observer_v1'
KINDS = {'standard_play', 'standard_pause', 'standard_resume'}
OPERATIONS = {'state', 'acquire', 'receive', 'usage', 'host_inspect', 'journal',
              'seed', 'task', 'task_status', 'release'}
JOURNAL = {'claim', 'cancel_unissued', 'preserve', 'finish', 'checkpoint'}
LIMIT = 256
BOUNDARY = {'nativePermissionResponse': False, 'nativeReload': False, 'controlReplay': False,
            'usageReset': False, 'bindingChange': False, 'terminalSafety': 'unknown'}


def path(root, command_id, kind, sequence=None):
    from .standard_preplay import path as directory_check
    directory_check(root, command_id, 'handoff')
    require(kind in ('handoff', 'turn', 'request', 'claim', 'reply'), 'Closed run mailbox kind required')
    require((kind in ('handoff', 'turn') and sequence is None) or
            (kind in ('request', 'claim', 'reply') and type(sequence) is int and 1 <= sequence <= LIMIT),
            'Bounded run mailbox sequence required')
    return Path(root) / ('standard-run-' + digest(command_id) + '-' + kind +
                        (('-' + str(sequence)) if sequence is not None else '') + '.json')


def prepare(ledger, db, command, binding):
    """Called only before the original notification is claimed or sent."""
    from . import standard
    from .brain_control import stopped
    from .public_native_tasks import validate_contract
    require(ledger.get(db, 'commands', command['id']) == command and not command.get('notification') and
            not command.get('notificationHistory') and command['kind'] in KINDS and
            command['status'] == 'queued' and command['actor'] in ('dashboard', 'assistant_owner_confirmed'),
            'Run mailbox cannot be added to an attempted or historical control')
    meta, mission = standard.eligible(ledger, db)
    run = meta.get('standardRun') or {}
    brain = meta['brainId']
    record = binding['brains'].get(brain, {})
    backend = validate_contract(record.get('nativeTaskBackend'), record.get('policyEvidence'))
    require(not stopped(meta) and run.get('protocol') == standard.PROTOCOL and
            run.get('brainId') == brain and command['payload'].get('runId') == run.get('id') and
            run.get('missionHash') == mission['documentHash'] and
            run.get('reviewHash') == mission['receiptHash'] and
            standard.worktrees.repository_mode(run) == 'repo_exclusive', 'Exact reviewed public standard run required')
    checkout = Path(record.get('cwd', '/'))
    require(record.get('workspaceId') == ledger.workspace_id and checkout.resolve(strict=True) == checkout and
            ledger.root.is_relative_to(checkout) and ledger.root != checkout,
            'Run mailbox must be inside the exact bound checkout')
    value = {'version': 1, 'transport': TRANSPORT, 'workspaceId': ledger.workspace_id,
             'brainId': brain, 'commandId': command['id'], 'runId': run['id'],
             'missionHash': run['missionHash'], 'reviewHash': run['reviewHash'],
             'ownerReceiptHash': digest(run['ownerReceipt']), 'bindingHash': digest(binding),
             'backendHash': digest(backend), 'ledgerIdentity': _identity(ledger.db),
             'registryIdentity': _identity(Path(ledger.platform_root) / 'platform.sqlite3'),
             'source': str(SOURCE), 'sourceHash': source_hash(), 'boundary': BOUNDARY}
    _write_once(path(ledger.root, command['id'], 'handoff'), value)
    return {'version': 1, 'transport': TRANSPORT, 'handoffHash': digest(value)}


def handoff(file):
    file = Path(file)
    value = _read_private(file)
    fields = {'version', 'transport', 'workspaceId', 'brainId', 'commandId', 'runId', 'missionHash',
              'reviewHash', 'ownerReceiptHash', 'bindingHash', 'backendHash', 'ledgerIdentity',
              'registryIdentity', 'source', 'sourceHash', 'boundary'}
    require(file.is_absolute() and isinstance(value, dict) and set(value) == fields and
            type(value['version']) is int and value['version'] == 1 and value['transport'] == TRANSPORT and
            value['boundary'] == BOUNDARY and value['source'] == str(SOURCE) and
            value['sourceHash'] == source_hash() and file == path(file.parent, value['commandId'], 'handoff'),
            'Original run handoff or source changed')
    return value


def bind_turn(ledger, command_id, brain_id, turn_id, *, host):
    file = path(ledger.root, command_id, 'handoff')
    value = handoff(file)
    require(value['brainId'] == brain_id and isinstance(turn_id, str) and 0 < len(turn_id) <= 128,
            'Exact original run turn required')
    _write_once(path(ledger.root, command_id, 'turn'), {'handoffHash': digest(value), 'nativeTurnId': turn_id})
    keys = getattr(host, '_run_control_keys', None)
    if keys is None:
        keys = host._run_control_keys = {}
    require(command_id not in keys, 'Original run session already bound')
    keys[command_id] = secrets.token_bytes(32)


def _turn(file, value):
    turn = _read_private(path(file.parent, value['commandId'], 'turn'))
    require(set(turn) == {'handoffHash', 'nativeTurnId'} and turn['handoffHash'] == digest(value) and
            isinstance(turn['nativeTurnId'], str), 'Original turn binding changed')
    return turn['nativeTurnId']


def _previous(file, value, sequence):
    if sequence == 1:
        return digest(value)
    previous = status(file, sequence - 1)
    require(previous['status'] == 'completed' and previous['continuationAllowed'] is True,
            'Previous run request is pending, interrupted, closed or unknown; never advance or retry')
    return digest(previous)


def status(file, sequence):
    """File-only progress. Never service, collect, reopen or republish a request."""
    file = Path(file)
    value = handoff(file)
    request_file = path(file.parent, value['commandId'], 'request', sequence)
    if not request_file.exists():
        return {'status': 'not_submitted', 'boundary': BOUNDARY}
    request = _read_private(request_file)
    require(request.get('handoffHash') == digest(value) and request.get('sequence') == sequence,
            'Run request changed')
    reply_file = path(file.parent, value['commandId'], 'reply', sequence)
    if not reply_file.exists():
        return {'status': 'claimed_outcome_unknown' if path(file.parent, value['commandId'], 'claim', sequence).exists()
                else 'waiting_for_original_observer', 'boundary': BOUNDARY}
    reply = _read_private(reply_file)
    require(isinstance(reply, dict) and set(reply) == {'requestHash', 'status', 'result', 'continuationAllowed', 'boundary', 'seal'} and
            reply['requestHash'] == digest(request) and reply['status'] in ('completed', 'unavailable') and
            type(reply['continuationAllowed']) is bool and reply['boundary'] == BOUNDARY and
            isinstance(reply['seal'], str) and len(reply['seal']) == 64,
            'Run reply changed')
    return reply


def submit(file, result_file):
    """Publish one explicit sequential call inside the checkout; no database access."""
    file = Path(file)
    value = handoff(file)
    call = _read_private(Path(result_file))
    require(isinstance(call, dict) and set(call) == {'sequence', 'operation', 'payload'} and
            call['operation'] in OPERATIONS and isinstance(call['payload'], dict), 'Closed run call required')
    sequence = call['sequence']
    request_file = path(file.parent, value['commandId'], 'request', sequence)
    request = {'version': 1, 'handoffHash': digest(value), 'nativeTurnId': _turn(file, value),
               'previousReplyHash': _previous(file, value, sequence), **call}
    try:
        _write_once(request_file, request)
    except FileExistsError:
        require(_read_private(request_file) == request, 'Run call already exists with different bytes; never replace')
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = status(file, sequence)
        if result['status'] not in ('waiting_for_original_observer', 'claimed_outcome_unknown'):
            return result
        time.sleep(.1)
    return status(file, sequence)


def _context(host, command_id, brain_id, turn_id):
    from . import standard
    from .workspaces import Registry
    from .enrollment import record_in
    ledger = host.ledger
    value = handoff(path(ledger.root, command_id, 'handoff'))
    require(not host._closed and command_id in getattr(host, '_run_control_keys', {}) and
            host.configured(brain_id) and value['bindingHash'] == digest(host.binding) and
            value['brainId'] == brain_id and value['workspaceId'] == ledger.workspace_id and
            value['ledgerIdentity'] == _identity(ledger.db) and
            value['registryIdentity'] == _identity(Path(ledger.platform_root) / 'platform.sqlite3') and
            _turn(path(ledger.root, command_id, 'handoff'), value) == turn_id, 'Run observer identity changed')
    registry = Registry(ledger.platform_root)
    require(registry.root_for(ledger.workspace_id) == ledger.root, 'Registered run target changed')
    with registry.tx() as rdb, standard.read_db(ledger.db) as db:
        require(record_in(rdb) is None, 'Strict enrollment fences the run mailbox')
        meta, mission = standard.eligible(ledger, db)
        run = meta.get('standardRun') or {}
        command = ledger.get(db, 'commands', command_id)
        note = command.get('notification') or {}
        marker = {'version': 1, 'transport': TRANSPORT, 'handoffHash': digest(value)}
        require(command['kind'] in KINDS and note.get('runControl') == marker and
                note.get('status') == 'accepted' and note.get('nativeDelivery') == 'owned_turn_start' and
                note.get('nativeTurnId') == turn_id and note.get('brainId') == brain_id and
                note.get('hostBindingHash') == value['bindingHash'] and note.get('hostRunId') == value['runId'] and
                note.get('nativeTurnStatus') in (None, 'inProgress') and
                (note.get('nativeThreadObservation') or {}).get('streamStatus') == 'open' and
                (note.get('nativeThreadObservation') or {}).get('rootThreadId') == brain_id and
                digest(note.get('nativeTaskContract')) == value['backendHash'], 'Original open subscribed run required')
        require(meta['brainId'] == brain_id == run.get('brainId') and run.get('id') == value['runId'] and
                run.get('protocol') == standard.PROTOCOL and run.get('missionHash') == mission['documentHash'] == value['missionHash'] and
                run.get('reviewHash') == mission['receiptHash'] == value['reviewHash'] and
                digest(run.get('ownerReceipt')) == value['ownerReceiptHash'], 'Reviewed run authority changed')
        owned = [c for c in ledger.all(db, 'commands') if (c.get('notification') or {}).get('brainId') == brain_id and
                 (c.get('notification') or {}).get('status') in ('accepted', 'sending', 'uncertain')]
        require(max(owned, key=lambda c: c['notification'].get('attemptedAt', 0))['id'] == command_id,
                'Newer owned turn fences this mailbox')
        owner = brain_id + ':run-mailbox:' + command_id + ':' + turn_id
        controller = meta.get('controller')
        require(controller is None or controller['owner'] == owner, 'Another controller owns the run')
    return registry, value, owner


def _seal(host, command_id, reply):
    key = getattr(host, '_run_control_keys', {}).get(command_id)
    require(isinstance(key, bytes) and len(key) == 32, 'Original observer session unavailable; no reconnect')
    return hmac.new(key, canonical({k:v for k,v in reply.items() if k != 'seal'}).encode(), hashlib.sha256).hexdigest()


def _server_previous(host, value, sequence):
    file = path(host.ledger.root, value['commandId'], 'handoff')
    previous_hash = _previous(file, value, sequence)
    if sequence > 1:
        prior = status(file, sequence-1)
        claimed = _read_private(path(file.parent, value['commandId'], 'claim', sequence-1))
        require(claimed == {'requestHash': prior['requestHash']} and
                hmac.compare_digest(prior['seal'], _seal(host, value['commandId'], prior)),
                'Previous outcome lacks its original observer seal; never skip an unknown call')
    return previous_hash


def _state(ledger):
    from .standard import read
    value = read(ledger)
    # Scope to this run. Do not leak controller credentials or unrelated history.
    return {k: v for k, v in value.items() if k not in ('catalogRefresh', 'history', 'closeoutUsage')}


def _permission_held(host, brain):
    check = getattr(host, 'has_pending_permission', None)
    return check(brain) if callable(check) else host.pending_approval(brain) is not None


class _ObserverLedger:
    """Recheck original ownership inside every existing ledger write boundary."""
    def __init__(self, host, value, owner):
        self.host, self.value, self.owner = host, value, owner

    def __getattr__(self, name):
        return getattr(self.host.ledger, name)

    def _guard(self, db):
        host, value = self.host, self.value
        require(not host._closed and value['commandId'] in getattr(host, '_run_control_keys', {}) and
                digest(host.binding) == value['bindingHash'] and source_hash() == value['sourceHash'] and
                not _permission_held(host, value['brainId']), 'Original observer closed or native permission remains held')
        meta = self.get(db, 'meta', 1)
        run = meta.get('standardRun') or {}
        controller = meta.get('controller') or {}
        command = self.get(db, 'commands', value['commandId'])
        note = command.get('notification') or {}
        owned = [c for c in self.all(db, 'commands') if (c.get('notification') or {}).get('brainId') == value['brainId'] and
                 (c.get('notification') or {}).get('status') in ('accepted', 'sending', 'uncertain')]
        from .brain_control import stopped
        require(not stopped(meta) and meta['brainId'] == value['brainId'] == run.get('brainId') and
                run.get('id') == value['runId'] and run.get('missionHash') == value['missionHash'] and
                run.get('reviewHash') == value['reviewHash'] and digest(run.get('ownerReceipt')) == value['ownerReceiptHash'] and
                (not controller or controller.get('owner') == self.owner) and
                note.get('status') == 'accepted' and note.get('nativeTurnStatus') in (None, 'inProgress') and
                (note.get('nativeThreadObservation') or {}).get('streamStatus') == 'open' and
                max(owned, key=lambda c: c['notification'].get('attemptedAt', 0))['id'] == value['commandId'],
                'Run/controller/observer changed at the write boundary')

    @contextlib.contextmanager
    def tx(self):
        with self.host.ledger.tx() as db:
            self._guard(db)
            yield db
            self._guard(db)


def _execute(host, registry, value, owner, request):
    from . import standard
    from .brain_control import stopped
    ledger = _ObserverLedger(host, value, owner)
    operation, payload = request['operation'], request['payload']
    if operation == 'state':
        require(payload == {}, 'State accepts no extra fields')
        return _state(ledger)
    require(not _permission_held(host, value['brainId']), 'Native permission remains held; no automatic response or bypass')
    with standard.read_db(ledger.db) as db:
        meta = ledger.get(db, 'meta', 1)
        require(not stopped(meta), 'Brain Stop fences run operations')
        controller = meta.get('controller') or {}
    if operation == 'acquire':
        require(payload == {} and not controller, 'One exact unowned controller required')
        with registry.tx(), ledger.tx() as db:
            meta = ledger.get(db, 'meta', 1)
            require(not meta.get('controller') and not stopped(meta) and
                    (meta.get('standardRun') or {}).get('id') == value['runId'], 'Controller/run changed before acquisition')
            meta['controller'] = {'owner': owner, 'token': secrets.token_hex(24), 'since': time.time()}
            ledger.put(db, 'meta', 1, meta)
            ledger.event(db, 'standard_controller_acquired', {'owner': owner})
        return {'acquired': True, 'credentialExposed': False}
    require(controller.get('owner') == owner and isinstance(controller.get('token'), str), 'Exact mailbox-owned controller required')
    token = controller['token']
    if operation in ('receive', 'usage', 'host_inspect'):
        require(payload == {}, 'Exact run operation accepts no extra fields')
        if operation == 'receive':
            return standard.brain(registry, ledger, token, {'operation': 'receive_control',
                'runId': value['runId'], 'commandId': value['commandId']})
        if operation == 'usage':
            from .brain_memory import refresh
            return refresh(ledger, value['runId'])
        from .standard_host_inspection import inspect
        return inspect(registry, ledger, token, value['runId'], value['commandId'])
    if operation == 'journal':
        require(payload.get('operation') in JOURNAL and 'runId' not in payload, 'Closed standard journal operation required')
        return standard.brain(registry, ledger, token, {**payload, 'runId': value['runId']})
    if operation in ('task', 'task_status', 'seed'):
        require(set(payload) == {'taskId'}, 'Exact existing scoped task required')
        if operation == 'seed':
            with standard.read_db(ledger.db) as db:
                task = standard.find_task(ledger.get(db, 'meta', 1)['standardRun'], payload)
                row = db.execute('SELECT kind,data FROM snapshots WHERE id=?', (task['seedHash'],)).fetchone()
                require(row and row['kind'] == 'standard_seed', 'Exact task seed missing')
                seed = json.loads(row['data'])
                require(digest(seed) == task['seedHash'], 'Task seed changed')
                return seed
        from .public_native_tasks import request as public_task
        return public_task(registry, ledger, token, value['runId'], value['commandId'], payload['taskId'],
                           read_existing_only=operation == 'task_status')
    require(operation == 'release' and set(payload) == {'summary'} and
            isinstance(payload['summary'], str) and 0 < len(payload['summary']) <= 8000, 'Closed release summary required')
    with registry.tx(), ledger.tx() as db:
        meta = ledger.authorize(db, token)
        run = meta['standardRun']
        require(run['id'] == value['runId'] and run['status'] in ('paused', 'blocked', 'completed') and
                run.get('checkpoint') and all(t['status'] in standard.TERMINAL for t in run['tasks']),
                'Retained checkpoint and settled registered tasks required before release')
        meta.update(controller=None, lastReconciled=time.time(), checkpoint=payload['summary'])
        ledger.put(db, 'meta', 1, meta)
        ledger.event(db, 'reconciled', {'checkpoint': payload['summary']})
    return {'released': True, 'terminalSafety': 'unknown'}


def service(host, command_id, brain_id, turn_id, sequence):
    """Claim one explicit request before any effect. Never reapply after interruption."""
    ledger = host.ledger
    request_file = path(ledger.root, command_id, 'request', sequence)
    if not request_file.exists():
        return
    request = _read_private(request_file)
    try:
        _write_once(path(ledger.root, command_id, 'claim', sequence), {'requestHash': digest(request)})
    except FileExistsError:
        return
    reply = {'requestHash': digest(request), 'status': 'unavailable', 'result': None,
             'continuationAllowed': False, 'boundary': BOUNDARY}
    try:
        registry, value, owner = _context(host, command_id, brain_id, turn_id)
        require(set(request) == {'version', 'handoffHash', 'nativeTurnId', 'previousReplyHash', 'sequence', 'operation', 'payload'} and
                type(request['version']) is int and request['version'] == 1 and
                request['handoffHash'] == digest(value) and request['nativeTurnId'] == turn_id and
                type(request['sequence']) is int and request['sequence'] == sequence and
                request['operation'] in OPERATIONS and isinstance(request['payload'], dict) and
                request['previousReplyHash'] == _server_previous(host, value, sequence),
                'Closed original sequential run request required')
        result = _execute(host, registry, value, owner, request)
        reply.update(status='completed', result=result, continuationAllowed=request['operation'] != 'release')
        require(len(canonical(reply).encode()) <= 65536, 'Run reply exceeds its qualified bound')
    except (OSError, sqlite3.Error, Refusal, ValueError, KeyError, TypeError):
        # An operation may have committed before a later output/persistence gap.
        # No error is permission to repeat it or skip its consumed sequence.
        reply.update(status='unavailable', result=None, continuationAllowed=False)
    reply['seal'] = _seal(host, command_id, reply)
    _write_once(path(ledger.root, command_id, 'reply', sequence), reply)


def service_pending(host, proxy, command_id, brain_id, turn_id):
    if host._closed or command_id not in getattr(host, '_run_control_keys', {}):
        return
    if getattr(proxy, '_run_mailbox_worker', None) is not None and proxy._run_mailbox_worker.is_alive():
        return
    with contextlib.closing(host.ledger.connect()) as db:
        note = host.ledger.get(db, 'commands', command_id).get('notification') or {}
    if (note.get('runControl') or {}).get('transport') != TRANSPORT or note.get('status') != 'accepted':
        return
    for sequence in range(1, LIMIT + 1):
        if path(host.ledger.root, command_id, 'claim', sequence).exists():
            # Claimed but missing reply is permanently unknown, never skipped.
            reply_file = path(host.ledger.root, command_id, 'reply', sequence)
            if not reply_file.exists() or not _read_private(reply_file).get('continuationAllowed'):
                return
            continue
        if not path(host.ledger.root, command_id, 'request', sequence).exists():
            return
        def relay(selected=sequence):
            try:
                service(host, command_id, brain_id, turn_id, selected)
            except (OSError, sqlite3.Error, Refusal, ValueError):
                pass  # Consumed claims are not automatically recovered.
        proxy._run_mailbox_worker = threading.Thread(target=relay, daemon=True, name='standard-run-mailbox')
        proxy._run_mailbox_worker.start()
        return


def continuation(ledger, command_id):
    """Read-only forward assessment for a held original; no attach/backfill/apply."""
    from .standard import read_db
    with read_db(ledger.db) as db:
        command = ledger.get(db, 'commands', command_id)
        run = ledger.get(db, 'meta', 1).get('standardRun') or {}
    note = command.get('notification') or {}
    require(command['kind'] in KINDS and run.get('id') == command['payload'].get('runId'), 'Exact original run control required')
    prospective = (note.get('runControl') or {}).get('transport') == TRANSPORT
    canceled = (note.get('nativeApprovals') or [])
    permission = note.get('nativePermissionObservation') or {}
    cancel_resolved = (note.get('nativeTurnStatus') == 'interrupted' and
                       (note.get('nativeThreadObservation') or {}).get('streamStatus') == 'closed' and
                       len(canceled) == 1 and canceled[0].get('decision') == 'cancel' and
                       canceled[0].get('status') == 'resolved' and
                       canceled[0].get('turnId') == note.get('nativeTurnId') and
                       permission.get('turnId') == note.get('nativeTurnId') and
                       permission.get('reason') == 'native_resolved' and
                       permission.get('requestHash') == canceled[0].get('requestHash'))
    from .canceled_play import status as disposition_status
    disposition = disposition_status(ledger)
    return {'commandId': command_id, 'runId': run['id'], 'nativeTurnId': note.get('nativeTurnId'),
            'originalCommandHash': digest(command), 'originalRunHash': digest(run),
            'prospectiveMailbox': prospective,
            'status': 'follow_original_mailbox' if prospective else
                      'canceled_play_disposed_unqualified' if disposition['status'] == 'disposed_unqualified' else
                      'canceled_original_requires_forward_disposition' if cancel_resolved else 'held_original_requires_owner_resolution',
            'blocker': None if prospective else 'Original observer has no run mailbox; do not attach one or restart its connection',
            'actionsTaken': [], 'permissionResponseRequiredSeparately': not cancel_resolved,
            'disposition': disposition, 'boundary': BOUNDARY}
