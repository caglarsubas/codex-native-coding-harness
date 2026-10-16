"""Separate owner-reviewed lineage to an existing, disjoint standard project.

Never reopen the old ledger. Admission records no native observation or Play;
future delivery must use an already loaded, independently verified target.
"""
import copy
import hashlib
import math
import os
from pathlib import Path
import time
from types import SimpleNamespace

from .core import Ledger, Refusal, canonical, digest, require
from . import missions, resources, standard, standard_quarantine as quarantine
from .host_lifecycle import private_file
from .native_project_assignment import _read_registry, _registered, _scope
from .app_server_wake import _read_binding

KIND = 'standard_successor_v1'
FENCE = 'standard-successor.json'
PROFILE = 'successor_loaded_only_v1'
BOUNDARY = {'oldRunChanged': False, 'oldUsageReset': False, 'repositoryReleased': False,
            'historicalCleanupVerified': False, 'terminalSafetyVerified': False,
            'bindingChanged': False, 'nativeAction': False, 'playAuthorized': False, 'pilotAccepted': False}
FIELDS = {'version', 'kind', 'sourceHash', 'source', 'target', 'bindingFile', 'bindingPin', 'boundary'}
LOCAL_POLICY = 'reviewed_local_git_v1'


def source_hash():
    from . import local_repository_identity, workspaces
    return digest([hashlib.sha256(path.read_bytes()).hexdigest() for path in
                   (Path(__file__), Path(local_repository_identity.__file__), Path(workspaces.__file__))])


def pin(path):
    path = private_file(path); info = path.stat()
    require(info.st_nlink == 1 and info.st_size <= 65536, 'Private immutable bounded file required')
    raw = path.read_bytes()
    after = path.stat()
    require(all(getattr(after, key) == getattr(info, key) for key in
                ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_mode', 'st_uid', 'st_nlink')),
            'Private file changed during read')
    return {'identity': [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns],
            'sha256': hashlib.sha256(raw).hexdigest()}


def source_claim(registry_root, workspace):
    from .workspaces import identity
    return Path(registry_root)/('standard-successor-'+identity(workspace)+'.claim')


def repositories(rows, *, local_only=False):
    result = []
    for row in sorted(rows, key=lambda r: r['id']):
        root = Path(row['path'])
        require(root.is_absolute() and str(root.resolve(strict=True)) == str(root), 'Canonical repository required')
        if local_only:
            from .local_repository_identity import inspect
            proof = inspect(root, allow_origin=True)
            value = {'keys': proof['keys']}
        else:
            proof = None
            value = resources.repository_identity(root)
            require(value['status'] == 'observed' and len(value['keys']) == 2,
                    'Complete local and conventional remote identity required; unknown is not disjoint')
        result.append({'id': row['id'], 'root': str(root), 'keys': value['keys'], 'recordHash': digest(row),
                       **({'localIdentity': proof} if proof else {})})
    require(result, 'Registered repository scope required')
    return result


def disjoint(left, right):
    for old in left:
        a = Path(old['root'])
        for new in right:
            b = Path(new['root'])
            require(not (a.is_relative_to(b) or b.is_relative_to(a)) and
                    not set(old['keys']) & set(new['keys']),
                    'Successor must not share a checkout, Git common directory or remote with held scope')


def other_owners(registry, target, scopes):
    local_only = any('localIdentity' in scope for scope in scopes)
    with _read_registry(registry) as rd:
        rows = list(rd.execute('SELECT id,root FROM workspaces WHERE id<>?', (target.workspace_id,)))
    require(len(rows) <= 32, 'Successor registered ownership bound exceeded')
    for row in rows:
        root = Path(row['root'])
        with standard.read_db(root/'ledger.sqlite3') as db:
            meta = Ledger.get(db, 'meta', 1); run = meta.get('standardRun') or {}
            held = quarantine.fenced(root, meta)
            if held: quarantine.repository_holds(root, db, meta)
            active = (meta.get('runner') or Ledger.all(db, 'workers') or
                      any(t.get('status') not in standard.TERMINAL for t in run.get('tasks', [])) or
                      any(m.get('status') in {'prepared', 'issued', 'uncertain'} for m in run.get('merges', [])))
            if held or active: disjoint(repositories(Ledger.all(db, 'repos'), local_only=local_only), scopes)


def original(root, workspace, *, local_only=False):
    root = Path(root)
    reader = SimpleNamespace(root=root, get=Ledger.get, all=Ledger.all)
    with standard.read_db(root/'ledger.sqlite3') as db:
        record = quarantine.retained_in(reader, db)
    request = record['request']; meta = request['state']['meta']; run = meta['standardRun']
    require(request['workspaceId'] == workspace, 'Original registered workspace changed')
    info = (root/'ledger.sqlite3').stat()
    return {'workspaceId': workspace, 'root': str(root), 'brainId': meta['brainId'],
            'ledgerIdentity': [info.st_dev, info.st_ino], 'quarantineHash': digest(record),
            'quarantinePin': pin(root/quarantine.FENCE), 'runId': run['id'], 'runHash': digest(run),
            'observedTokens': run.get('brainObservedTokens'), 'usageHighWater': run.get('usageHighWater'),
            'usageCoverage': run.get('brainUsageCoverage'), 'usageReportHash': digest(run.get('usageReport')),
            'expiresAt': run['expiresAt'], 'historicalTerminalSafety': 'unknown',
            'repositories': repositories(request['state']['repos'], local_only=local_only)}


def context(registry, source, target, binding_path, db, *, local_only=False):
    from .enrollment import record_in, fence_exists
    from .workspaces import private_database
    for path in (registry.db, source.db, target.db):
        private_database(path)  # Same database checks before either permanent claim.
    with _read_registry(registry) as rd:
        require(record_in(rd) is None, 'Strict enrollment cannot admit a standard successor')
    old_root, old_inspected, _, _ = _registered(registry, source.workspace_id)
    new_root, inspected, _, _ = _registered(registry, target.workspace_id)
    require(old_root == source.root and new_root == target.root and source.workspace_id != target.workspace_id and
            old_inspected['brainId'] != inspected['brainId'], 'Separate existing registered source and target required')
    require(not os.path.lexists(source_claim(registry.root, source.workspace_id)) and
            not os.path.lexists(target.root/FENCE), 'Successor already claimed; inspect its receipt, never retry')
    old = original(source.root, source.workspace_id, local_only=local_only)
    meta = target.get(db, 'meta', 1)
    require(meta['schemaVersion'] == 1 and not meta.get('standardRun') and meta.get('paused') is True and
            not meta.get('controller') and not meta.get('runner') and not meta.get('admissionBinding') and
            not fence_exists(target.root) and not os.path.lexists(standard.controller_file(target)),
            'Successor target must be an empty unowned pre-phase standard ledger')
    control = meta.get('brainControl') or {'desired': 'running', 'phase': 'ready'}
    require((control.get('desired'), control.get('phase')) == ('running', 'ready') and
            all(not target.all(db, table) for table in ('workers', 'queue', 'commands', 'decisions', 'continuations')),
            'Pending work, control, stop or prior attempts cannot be relabelled as a successor')
    _, mission = standard.eligible(target, db)
    rows = target.all(db, 'repos'); new_repos = repositories(rows, local_only=local_only); disjoint(old['repositories'], new_repos)
    other_owners(registry, target, new_repos)
    binding_path = private_file(binding_path); binding = _read_binding(binding_path)
    scope = _scope(registry, target.workspace_id, binding)
    brain = binding['brains'][meta['brainId']]
    require(set(binding['brains']) == {meta['brainId']} and scope['root'] == target.root and
            brain.get('nativePolicy') in (
                {'sandbox': 'workspace-write', 'approvalPolicy': 'on-request', 'codeMode': False},
                {'sandbox': 'workspace-write', 'approvalPolicy': 'on-request', 'codeMode': False, 'approvalsReviewer': 'user'}) and
            any(row['path'] == scope['cwd'] for row in rows), 'Exact unchanged restricted target binding required')
    from .native_policy_evidence import validate_contract
    validate_contract(brain.get('policyEvidence'))
    info, registry_info = target.db.stat(), registry.db.stat()
    return {'version': 1, 'kind': KIND, 'sourceHash': source_hash(), 'source': old,
            **({'identityPolicy': LOCAL_POLICY} if local_only else {}),
            'target': {'workspaceId': target.workspace_id, 'root': str(target.root), 'brainId': meta['brainId'],
                'ledgerIdentity': [info.st_dev, info.st_ino], 'registryIdentity': [registry_info.st_dev, registry_info.st_ino],
                'metaHash': digest(meta), 'repositories': new_repos, 'missionHash': mission['documentHash'],
                'missionReviewHash': mission['receiptHash'], 'bindingHash': digest(binding),
                'scope': {k: str(v) if isinstance(v, Path) else v for k, v in scope.items()}},
            'bindingFile': str(binding_path), 'bindingPin': pin(binding_path), 'boundary': copy.deepcopy(BOUNDARY)}


def prepare(registry, source, target_id, binding_path, *, local_only=False):
    target = registry.ledger(target_id)
    with standard.read_db(target.db) as db:
        request = context(registry, source, target, binding_path, db, local_only=local_only)
    require(len(canonical(request).encode()) <= 65536, 'Successor scope exceeds its closed bound')
    return {'request': request, 'reviewHash': digest(request), 'validUntil': 'scope_changes',
            'effect': 'Record disjoint successor lineage only; separate target mission Review and fresh Play remain required',
            'nativeCollection': False, 'oldRunUnchanged': True}


def read_request(path):
    path = private_file(path); before = pin(path); raw = path.read_bytes()
    from .native_read_client import decode
    value = decode(raw)
    require(pin(path) == before and isinstance(value, dict) and valid_fields(value) and
            type(value['version']) is int and value['version'] == 1 and value['kind'] == KIND and
            value['boundary'] == BOUNDARY, 'Exact closed private successor review required')
    return value


def valid_fields(value):
    return (set(value) == FIELDS or set(value) == FIELDS | {'identityPolicy'} and
            value['identityPolicy'] == LOCAL_POLICY)


def retained_in(ledger, db, meta=None):
    meta = meta or ledger.get(db, 'meta', 1)
    path = ledger.root/FENCE
    if not os.path.lexists(path) and meta.get('schemaVersion') != 7 and 'standardSuccessor' not in meta:
        return None
    from .native_read_client import decode
    require(path.is_file() and not path.is_symlink(), 'Successor claim is missing or invalid; writes remain fenced')
    pin(path)
    marker = decode(private_file(path).read_bytes())
    require(set(marker) == {'kind', 'recordHash', 'reviewHash'} and marker['kind'] == KIND and
            meta.get('schemaVersion') == 7 and meta.get('successorLedgerVersion') == 1 and
            meta.get('standardSuccessor') == marker['recordHash'], 'Partial successor admission remains fenced')
    record = ledger.get(db, 'snapshots', marker['recordHash']); req = record['request']; target = req['target']
    require(digest(record) == marker['recordHash'] and record['reviewHash'] == marker['reviewHash'] == digest(req) and
            valid_fields(req) and req['kind'] == KIND and req['sourceHash'] == source_hash() and
            req['boundary'] == BOUNDARY, 'Successor receipt or source changed')
    require(ledger.workspace_id == target['workspaceId'] and str(ledger.root) == target['root'] and
            meta['brainId'] == target['brainId'], 'Successor target identity changed')
    info = ledger.db.stat()
    require([info.st_dev, info.st_ino] == target['ledgerIdentity'] and
            repositories(ledger.all(db, 'repos'), local_only=req.get('identityPolicy') == LOCAL_POLICY) ==
            target['repositories'], 'Successor repository/ledger changed')
    from .workspaces import private_database
    private_database(ledger.db)
    registry_path = private_database(Path(ledger.platform_root)/'platform.sqlite3')
    registry = SimpleNamespace(root=Path(ledger.platform_root), db=registry_path)
    registry_info = registry_path.stat()
    require(registry_info.st_nlink == 1, 'Successor registry hard link refused')
    require([registry_info.st_dev, registry_info.st_ino] == target['registryIdentity'], 'Successor registry identity changed')
    for workspace, root in ((req['source']['workspaceId'], req['source']['root']),
                            (target['workspaceId'], target['root'])):
        registered_root, _, _, _ = _registered(registry, workspace)
        require(str(registered_root) == root, 'Successor registered routing changed')
    require(original(req['source']['root'], req['source']['workspaceId'],
                     local_only=req.get('identityPolicy') == LOCAL_POLICY) == req['source'],
            'Original quarantined attempt changed')
    require(pin(req['bindingFile']) == req['bindingPin'] and digest(_read_binding(req['bindingFile'])) == target['bindingHash'],
            'Existing successor binding changed; no rebind or fallback')
    claim = source_claim(ledger.platform_root, req['source']['workspaceId'])
    pin(claim)
    outgoing = decode(private_file(claim).read_bytes())
    require(outgoing == {'kind': KIND, 'target': target['workspaceId'], 'recordHash': marker['recordHash']},
            'Original successor claim changed or incomplete')
    mission = missions.state_in(ledger, db)
    require(mission['documentHash'] == target['missionHash'] and mission['receiptHash'] == target['missionReviewHash'] and
            mission['effectiveStatus'] == 'reviewed', 'Successor mission changed; no inherited or replacement authority')
    run = meta.get('standardRun')
    if run:
        require(run.get('successorHash') == marker['recordHash'] and
                run.get('ownerReceipt', {}).get('successorHash') == marker['recordHash'], 'Run is not the separately confirmed successor')
    return record


def confirm(registry, source, request, confirmed_hash):
    require(isinstance(request, dict) and valid_fields(request) and digest(request) == confirmed_hash and
            request['boundary'] == BOUNDARY, 'Confirm the exact separately displayed successor review hash')
    require(source.workspace_id == request['source']['workspaceId'] and
            str(source.root) == request['source']['root'], 'Exact original registered successor route required')
    target = registry.ledger(request['target']['workspaceId'])
    with standard.read_db(target.db) as db:
        if os.path.lexists(target.root/FENCE):
            previous = retained_in(target, db)
            require(previous['request'] == request, 'A different successor already owns this target')
            return public(previous)
    with registry.tx(), target.tx() as db:
        require(context(registry, source, target, request['bindingFile'], db,
                        local_only=request.get('identityPolicy') == LOCAL_POLICY) == request, 'Successor scope changed')
        record = {'kind': KIND, 'request': copy.deepcopy(request), 'reviewHash': confirmed_hash,
                  'recordedAt': time.time(), 'outcome': 'lineage_recorded_play_not_started'}
        key = digest(record)
        quarantine.exclusive(target.root/FENCE, {'kind': KIND, 'recordHash': key, 'reviewHash': confirmed_hash})
        quarantine.exclusive(source_claim(registry.root, source.workspace_id),
                             {'kind': KIND, 'target': target.workspace_id, 'recordHash': key})
        db.execute('INSERT INTO snapshots(id,kind,data) VALUES(?,?,?)', (key, KIND, canonical(record)))
        meta = target.get(db, 'meta', 1)
        meta.update(schemaVersion=7, successorLedgerVersion=1, standardSuccessor=key, revision=meta['revision']+1)
        target.put(db, 'meta', 1, meta)
    return public(record)


def public(record):
    req = record['request']; old = req['source']
    return {'recordHash': digest(record), 'outcome': record['outcome'], 'recordedAt': record['recordedAt'],
            'sourceWorkspaceId': old['workspaceId'], 'sourceRunId': old['runId'],
            'priorObservedTokens': old['observedTokens'], 'priorUsageHighWater': old['usageHighWater'],
            'priorUsageCoverage': old['usageCoverage'], 'priorTerminalSafety': 'unknown',
            'targetWorkspaceId': req['target']['workspaceId'], 'nativeStartup': 'already_loaded_only',
            'boundary': copy.deepcopy(BOUNDARY)}


def loaded_profile(host, proxy, command_id, brain_id):
    """Exact current target only. Never resume, load, subscribe, refresh or start."""
    from .native_project_assignment import _scope
    from .standard_native_observation import _brain_identity, _terminals
    from .native_policy_evidence import collect, matches
    from .workspaces import Registry
    ledger = host.ledger; registry = Registry(ledger.platform_root)
    with standard.read_db(ledger.db) as db:
        meta = ledger.get(db, 'meta', 1); record = retained_in(ledger, db, meta)
        command = ledger.get(db, 'commands', command_id); run = meta.get('standardRun') or {}
        require(record and brain_id == meta['brainId'] and command['kind'] in
                {'standard_play', 'standard_pause', 'standard_resume'} and
                command['payload']['runId'] == run.get('id') and
                run.get('status') == ('stopping' if command['kind'] == 'standard_pause' else 'running') and
                command['payload'].get('successorHash') == meta['standardSuccessor'] and
                command.get('notification', {}).get('status') == 'sending', 'Exact fresh successor control required; no recovery or ordinary wake')
        require(command['kind'] == 'standard_pause' or time.time() < run['expiresAt'],
                'Successor phase expired; no clock renewal or recovery fallback')
        before_hash = digest(meta)
        other_owners(registry, ledger, record['request']['target']['repositories'])
    require(digest(host.binding) == record['request']['target']['bindingHash'], 'Successor host binding differs')
    scope = _scope(registry, ledger.workspace_id, host.binding)
    client = SimpleNamespace(call=proxy._rpc)
    first = _brain_identity(client, scope, include_flags=True, idle_without_flags=True)
    require(first['nativeStatus'] == 'idle' and first['activeFlags'] == [], 'Successor brain must already be loaded idle; no load is permitted')
    require(_terminals(client, brain_id) == [], 'Successor current tracked terminals must be known empty')
    observed_at = time.time(); evidence = collect(proxy, host.binding, brain_id, command_id)
    require(matches(evidence['reported']), 'Successor loaded policy is unknown or differs; no resume is permitted')
    require(_terminals(client, brain_id) == [] and
            _brain_identity(client, scope, include_flags=True, idle_without_flags=True) == first,
            'Successor loaded identity/activity/terminals changed')
    with standard.read_db(ledger.db) as db:
        require(digest(ledger.get(db, 'meta', 1)) == before_hash, 'Pause or successor state changed during preflight')
        retained_in(ledger, db)
    return {'version': 1, 'protocol': PROFILE, 'sourceHash': source_hash(),
            'successorHash': digest(record), 'bindingHash': digest(host.binding), 'brainId': brain_id,
            'commandId': command_id, 'runId': run['id'], 'observedAt': observed_at}, evidence


def valid_profile(profile, note, run, command_id):
    fields = {'version', 'protocol', 'sourceHash', 'successorHash', 'bindingHash', 'brainId',
              'commandId', 'runId', 'observedAt', 'nativeTurnId'}
    return (isinstance(profile, dict) and set(profile) == fields and type(profile['version']) is int and
            profile['version'] == 1 and profile['protocol'] == PROFILE and profile['sourceHash'] == source_hash() and
            profile['successorHash'] == run.get('successorHash') == note.get('successorHash') and
            profile['runId'] == run['id'] and profile['brainId'] == run['brainId'] == note.get('brainId') and
            profile['commandId'] == command_id and profile['bindingHash'] == note.get('hostBindingHash') and
            type(profile['observedAt']) in (int, float) and math.isfinite(profile['observedAt']) and
            profile['nativeTurnId'] == note.get('nativeTurnId'))
