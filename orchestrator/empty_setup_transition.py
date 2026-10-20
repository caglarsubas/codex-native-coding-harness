"""Reviewed pre-phase registration transition; no native write or execution.

An acknowledged creation is never repeated. This local maintenance control can
adopt an ALREADY created durable empty identity for an unused standard target.
Original mappings, configuration epochs and consumed setup records are retained.
Native readback is mandatory but is not policy, cleanup or Play authority.
"""
import argparse
import contextlib
import copy
import hashlib
import os
from pathlib import Path
import sqlite3
import time
import uuid

from .core import Ledger, Refusal, canonical, digest, require
from . import missions, projects, standard
from .host_lifecycle import private_file, sync_directory
from .native_read_client import ReadProxy, decode, validate_endpoint, file_identity
from .native_policy_evidence import reported, matches
from .public_host_lifecycle import CONFIG
from .public_host_restart import pin, read_file
from .standard_quarantine import exclusive
from .workspace_identity_recovery import (read_database, checked_fingerprint,
    dashboard_lock, backup_database)
from .workspaces import Registry, private_path

KIND = 'empty_standard_setup_transition_v1'
FENCE = 'empty-setup-transition.claim.json'
RECEIPT = 'empty-setup-transition.receipt.json'
HISTORY = 'empty_setup_transitions'
BOUNDARY = {'nativeWrite': False, 'brainLoaded': False, 'bindingInstalled': False,
    'playAuthorized': False, 'usageReset': False, 'oldClaimsRearmed': False,
    'terminalSafetyVerified': False, 'pilotAccepted': False}
SPEC_FIELDS = {'version', 'kind', 'workspaceId', 'oldBrainId', 'brainId',
    'nativeProjectId', 'catalogProjectId', 'checkout', 'endpoint', 'configFile',
    'originalConfigPin', 'setupRecords', 'catalogObservation'}
RECORDS = {'ownerApproval', 'setupRequest', 'applicationIntent', 'projectClaim',
    'projectResult', 'brainClaim', 'brainResult', 'creatorObservations'}
INIT = {'clientInfo': {'name': 'codex_orchestrator_observer', 'version': '1'},
    'capabilities': {'experimentalApi': True}}


def source_hash():
    from . import core, workspaces, native_policy_evidence, native_read_client
    return digest([hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
        for m in (core, workspaces, missions, projects, native_policy_evidence,
                  native_read_client)] + [hashlib.sha256(Path(__file__).read_bytes()).hexdigest()])


def read(path):
    before = pin(path)
    result = decode(private_file(path).read_bytes())
    require(pin(path) == before, 'Setup record changed during read')
    return result


def input_pin(path):
    """Original reviewed source inputs may be 644; never loosen private records."""
    path = Path(path)
    before = path.lstat(); _, record = read_file(path, 65536)
    require(file_identity(before) == file_identity(path.lstat()), 'Original setup input epoch changed')
    return {'path': str(path), 'sha256': record['sha256'], 'identity': list(file_identity(before))}


def preserved_pin(value):
    require(isinstance(value, dict) and isinstance(value.get('path'), str), 'Retained setup file pin required')
    inspect = input_pin if set(value) == {'path', 'sha256', 'identity'} else pin
    require(inspect(value['path']) == value, 'Original consumed setup file epoch changed')
    return value


def identifier(value):
    try: valid = isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError: valid = False
    require(valid, 'Exact returned native UUID required')
    return value


def configuration(path, checkout, original_pin):
    """Accept no config repair: only the exact known base + one trust append.

    This is a new scope-bound review of both epochs, NOT retroactive approval of
    the old whole-file guard. Additional project/global config is refused.
    """
    path = private_file(path)
    raw, current = read_file(path, 65536)
    original = CONFIG.encode()
    require(isinstance(original_pin, dict) and original_pin.get('sha256') ==
        hashlib.sha256(original).hexdigest() and original_pin.get('bytes') == len(original)
        and original_pin.get('mode') == 0o600, 'Original fixed restricted configuration required')
    # json quoting handles quotes/backslashes without broadening TOML keys.
    suffix = ('\n[projects.' + canonical(str(checkout)) + ']\ntrust_level = "trusted"\n').encode()
    require(raw == original + suffix,
        'Only the exact native-created checkout trust append is supported; other drift refuses')
    for extra in (Path(checkout)/'config.toml', Path(checkout)/'.codex/config.toml',
        Path('/etc/codex/config.toml'), Path('/etc/codex/requirements.toml'),
        Path('/etc/codex/managed_config.toml'), Path('/Library/Preferences/com.openai.codex.plist')):
        require(not os.path.lexists(extra), 'Additional native configuration needs separate qualification')
    return {'path': str(path), 'original': copy.deepcopy(original_pin),
        'current': current, 'originalGuardPassed': False,
        'delta': 'one_exact_checkout_trust_append', 'executionPolicyQualified': False}


def provenance(spec):
    records = spec['setupRecords']
    require(isinstance(records, dict) and set(records) == RECORDS,
        'Complete consumed creation lineage required')
    values = {key: read(path) for key, path in records.items()}
    request = values['setupRequest']; intent = values['applicationIntent']
    review = digest(request)
    require(request.get('kind') == 'prospective_disjoint_v1_native_identity_setup_v1'
        and request.get('version') == 1 and
        request.get('target', {}).get('workspaceId') == spec['workspaceId'] and
        request['target'].get('root') == spec['checkout'] and
        request.get('predecessor', {}).get('brainId') == spec['oldBrainId'],
        'Exact originally reviewed prospective setup required, never an old creation retry')
    require(values['ownerApproval'].get('reviewHash') == intent.get('reviewHash') == review and
        values['ownerApproval'].get('exactHumanApproval') == 'Approve prospective v1 native setup '+review and
        intent.get('maximumProjectCreates') == intent.get('maximumBrainCreates') == 1 and
        intent.get('maximumLoads') == intent.get('maximumTurns') == 0,
        'Retained exact original approval and two consumed metadata-only claims required')
    require(all(type(intent.get(key)) is int for key in
        ('maximumProjectCreates', 'maximumBrainCreates', 'maximumLoads', 'maximumTurns')),
        'Exact integer creation/load/turn limits required')
    request_pin = intent.get('requestPin', {})
    require(request_pin.get('path') == records['setupRequest'], 'Original setup request was replaced')
    preserved_pin(request_pin)
    operator = intent.get('operatorSource', {})
    require(isinstance(operator.get('path'), str) and Path(operator['path']).suffix == '.py',
        'Preserve the original consumed operator implementation')
    preserved_pin(operator)
    require(request['reviewedHost']['endpoint'] == spec['endpoint'], 'Original issued endpoint must stay unchanged')
    from .public_host_runtime import validate_pin
    package = request['reviewedHost']['runtimePackage']
    validate_pin(package)
    require(str(Path(package['root'])/'bin/codex') == spec['endpoint']['executable'], 'Original reviewed package differs')
    manifests = [value for value in request.get('immutableInputs', [])
        if Path(value.get('path', '')).name == 'launch-manifest.exact.json']
    require(len(manifests) == 1, 'Original issued launch/configuration provenance required')
    preserved_pin(manifests[0])
    launch = read(manifests[0]['path'])
    require(launch.get('configPin') == spec['originalConfigPin'] and launch.get('runtimePackage') == package and
        launch.get('cwd') == spec['checkout'] and
        Path(launch.get('codexHome', ''))/'config.toml' == Path(spec['configFile']),
        'Original configuration epoch/home/checkout/package differs; no revised historical pin')
    setup = request['prospectiveNativeSetup']
    require(setup['threadStartParameters'] == {'cwd': spec['checkout'], 'ephemeral': False,
        'sandbox': 'workspace-write', 'approvalPolicy': 'on-request', 'approvalsReviewer': 'user',
        'config': {'features': {'code_mode': {'enabled': False}}}}, 'Original creation policy is outside this restricted setup profile')
    for name, method, params in (
        ('project', 'project/create', setup['projectCreate']),
        ('brain', 'thread/start', {**setup['threadStartParameters'], 'projectId': spec['nativeProjectId']})):
        claim = values[name+'Claim']
        require(claim.get('reviewHash') == review and claim.get('method') == method and
            claim.get('params') == params and claim.get('maximumAttempts') == 1 and
            type(claim.get('maximumAttempts')) is int and
            claim.get('retryPermitted') is False and
            claim.get('endpointHash') == digest(spec['endpoint']) and
            claim.get('operatorSource') == intent.get('operatorSource'),
            'Original consumed creation claim changed or delivery is uncertain')
    project = values['projectResult'].get('project', {})
    thread = values['brainResult'].get('thread', {})
    require(project.get('id') == spec['nativeProjectId'] and
        project.get('roots') == [{'path': spec['checkout']}] and
        thread.get('id') == spec['brainId'] and thread.get('projectId') == spec['nativeProjectId'] and
        thread.get('cwd') == spec['checkout'] and thread.get('ephemeral') is False,
        'Only actual returned new durable identities may be adopted')
    samples = values['creatorObservations'].get('samples')
    require(isinstance(samples, list) and len(samples) == 2,
        'Preserve both original creator observations, never backfill missing independent evidence')
    for sample in samples:
        empty_identity(spec, sample['project'], sample['thread'], sample['policy'])
    return {key: pin(path) for key, path in records.items()}


def original_inputs(spec):
    values = read(spec['setupRecords']['setupRequest']).get('immutableInputs')
    require(isinstance(values, list) and 1 <= len(values) <= 128, 'Preserve the complete original setup input inventory')
    seen = set()
    for value in values:
        require(isinstance(value, dict) and set(value) == {'path', 'sha256', 'identity'} and
            value['path'] not in seen and Path(value['path']).name not in
            ('auth.json', 'credentials.json', '.credentials.json', '.env'), 'Closed unique non-credential setup inputs required')
        seen.add(value['path'])
        require(input_pin(value['path']) == value, 'An immutable predecessor/setup input changed; never rewrite its pin')
    return copy.deepcopy(values)


def validate_spec(spec):
    require(isinstance(spec, dict) and set(spec) == SPEC_FIELDS and spec['kind'] == KIND and
        type(spec['version']) is int and spec['version'] == 1, 'Closed unused-target setup specification required')
    for field in ('oldBrainId', 'brainId', 'nativeProjectId', 'catalogProjectId'): identifier(spec[field])
    require(spec['oldBrainId'] != spec['brainId'], 'Creation cannot be replayed or relabelled')
    checkout = Path(spec['checkout'])
    require(checkout.is_absolute() and checkout.resolve(strict=True) == checkout and checkout.is_dir(),
        'Canonical existing checkout required')
    validate_endpoint(spec['endpoint'])
    require(Path(spec['configFile']).name == 'config.toml', 'Only the exact isolated config file may be inspected')
    return spec


def empty_identity(spec, project_result, thread_result, policy_result):
    project = project_result.get('project', {})
    thread = thread_result.get('thread', {})
    require(project.get('id') == spec['nativeProjectId'] and project.get('roots') == [{'path': spec['checkout']}] and
        thread.get('id') == spec['brainId'] and thread.get('projectId') == spec['nativeProjectId'] and
        thread.get('cwd') == spec['checkout'] and thread.get('ephemeral') is False and thread.get('turns') == [] and
        thread.get('status') in ({'type': 'idle'}, {'type': 'notLoaded'}),
        'Exact durable zero-turn new identity required; unavailable/active is not empty')
    policy = reported(policy_result, spec['brainId'], spec['checkout'])
    require(policy is None if thread['status'] == {'type': 'notLoaded'} else matches(policy),
        'Unloaded policy stays unknown; a loaded mismatch refuses')
    return thread['status']['type']


class SetupReadProxy(ReadProxy):
    """Only one exact new project/brain. No inventory discovery, load or subscribe."""
    def __init__(self, spec):
        self.spec = spec
        super().__init__(spec['endpoint'])

    def _rpc(self, method, params):
        allowed = {'initialize': INIT, 'project/read': {'projectId': self.spec['nativeProjectId']},
            'thread/read': {'threadId': self.spec['brainId'], 'includeTurns': False},
            'thread/turns/list': {'threadId': self.spec['brainId'], 'cursor': None,
                'limit': 1, 'sortDirection': 'desc', 'itemsView': 'notLoaded'},
            'thread/effectivePolicy/read': {'threadId': self.spec['brainId']}}
        require(method in allowed and canonical(params) == canonical(allowed[method]),
            'Only exact new-brain setup metadata reads permitted')
        self.deadline = time.monotonic()+15
        result = super()._rpc(method, params)
        if method == 'initialize':
            require(result.get('codexHome') == str(Path(self.spec['configFile']).parent),
                'Reviewed config must belong to this actual isolated native home')
        return result


def observe(spec):
    statuses = []
    with SetupReadProxy(spec) as proxy:
        for _ in range(2):
            statuses.append(empty_identity(spec,
                proxy._rpc('project/read', {'projectId': spec['nativeProjectId']}),
                proxy._rpc('thread/read', {'threadId': spec['brainId'], 'includeTurns': False}),
                proxy._rpc('thread/effectivePolicy/read', {'threadId': spec['brainId']})))
            history = proxy._rpc('thread/turns/list', {'threadId': spec['brainId'], 'cursor': None,
                'limit': 1, 'sortDirection': 'desc', 'itemsView': 'notLoaded'})
            require(history == {'data': [], 'nextCursor': None}, 'Complete empty native turn history required')
    require(statuses[0] == statuses[1], 'New brain activity changed during registration readback')
    return {'status': statuses[0], 'samples': 2, 'currentPolicyQualified': False,
        'independentLoadedPolicyPreviouslyMissing': True, 'currentTerminalSafety': 'unknown',
        'historicalTerminalSafety': 'unknown'}


def database(path):
    with read_database(path) as db: proof = checked_fingerprint(db)
    info = Path(path).stat()
    return {'identity': [info.st_dev, info.st_ino], 'proof': proof}


def context(registry, workspace_id, spec, *, claimed=False):
    validate_spec(spec)
    require(spec['workspaceId'] == workspace_id, 'Select the exact prospective target')
    # A context read must not nest a second registry writer while confirmation
    # owns its write transaction. This view never initializes any tables.
    reader_registry = Registry(registry.root, read_only=True)
    root = reader_registry.root_for(workspace_id)
    require(claimed or not os.path.lexists(root/FENCE), 'Setup transition already claimed; never rearm or retry')
    with read_database(registry.db) as db:
        from .enrollment import require_registration_open
        require_registration_open(db)
        rows = [dict(row) for row in db.execute('SELECT * FROM workspaces ORDER BY id')]
        require(1 <= len(rows) <= 32, 'Complete bounded registry required')
        selected = next(row for row in rows if row['id'] == workspace_id)
        require(selected['brain'] == spec['oldBrainId'] and
            not any(row['brain'] == spec['brainId'] for row in rows), 'Original registered brain or new uniqueness changed')
        saved, bindings = projects._read(db)
    with read_database(root/'ledger.sqlite3') as db:
        meta = Ledger.get(db, 'meta', 1)
        require(meta.get('schemaVersion') == 1 and meta.get('brainId') == spec['oldBrainId'] and
            meta.get('paused') is True and meta.get('controller') is None and meta.get('runner') is None and
            not any(key in meta for key in ('standardRun', 'admissionBinding', 'brainHandoff', 'emptySetupTransition')) and
            meta.get('heartbeat', {}).get('status') in (None, 'not_configured', 'paused'),
            'Only an unused paused first-phase target without controller or run qualifies')
        require(all(not Ledger.all(db, name) for name in ('commands', 'workers', 'queue', 'decisions', 'continuations')),
            'Requests and task history must remain empty; no disposition or retry is supported')
        repos = Ledger.all(db, 'repos')
        require(len(repos) == 1 and repos[0]['policyProfile'] == 'standard' and repos[0]['path'] == spec['checkout'],
            'One unchanged all-standard target checkout required')
        reader = type('Reader', (), {'get': staticmethod(Ledger.get), 'all': staticmethod(Ledger.all),
            'workspace_id': workspace_id})()
        mission = missions.state_in(reader, db)
        require(mission['effectiveStatus'] in ('not_configured', 'draft'), 'Reviewed mission cannot change brains through setup')
    from .enrollment import fence_exists
    require(not fence_exists(root) and not any(os.path.lexists(root/name) for name in (
        'standard-successor.json', 'standard-forward-continuation.json', 'standard-quarantine.json',
        'standard-canceled-play.json', 'standard-partial-admission-disposition.json',
        'standard-readiness-disposition.json')), 'Existing claims and ownership holds refuse setup migration')
    observation = read(spec['catalogObservation'])
    require(observation.get('source') == 'codex_app.list_projects' and
        type(observation.get('observedAt')) in (int, float) and 0 < observation['observedAt'] <= time.time()+30,
        'Retain a complete actual native app catalog with its original time')
    normalized = projects.normalize(observation['completeResult'])
    candidates = [p for p in normalized if p['projectId'] == spec['catalogProjectId'] and p['hostId'] == 'local'
        and p['projectKind'] == 'local' and p['locationHash'] == digest(['local', spec['checkout']])]
    require(len(candidates) == 1, 'Both actual native identities need explicit review; matching paths do not substitute IDs')
    project = candidates[0]
    require(project['key'] not in bindings or bindings[project['key']]['workspaceId'] == workspace_id,
        'New catalog project belongs to another workspace')
    require(saved is None or observation['observedAt'] >= saved['observedAt'], 'Older catalog cannot replace a newer observation')
    previous = [(key, value) for key, value in bindings.items() if value['workspaceId'] == workspace_id]
    require(len(previous) == 1 and previous[0][1]['brainId'] == spec['oldBrainId'] and
        previous[0][1]['databaseIdentity'] == decode(selected['data'])['databaseIdentity'] and
        previous[0][1]['locationHash'] == digest(['local', spec['checkout']]) and saved and
        any(p['key'] == previous[0][0] and p['projectId'] == repos[0]['projectId'] and
            p['locationHash'] == previous[0][1]['locationHash'] for p in saved['projects']),
        'Preserve one intact original registration/catalog mapping; never hide an existing identity mismatch')
    lineage = provenance(spec)
    immutable = original_inputs(spec)
    config = configuration(spec['configFile'], spec['checkout'], spec['originalConfigPin'])
    result = {'kind': KIND, 'version': 1, 'sourceHash': source_hash(), 'workspaceId': workspace_id,
        'spec': copy.deepcopy(spec), 'setupPins': lineage, 'catalogPin': pin(spec['catalogObservation']),
        'immutableSetupInputs': immutable,
        'configTransition': config, 'registration': selected, 'oldCatalog': saved, 'oldBindings': bindings,
        'newCatalogProject': project, 'originalMeta': meta, 'draftHash': mission['documentHash'],
        'databases': {str(path): database(path) for path in [registry.db, *[Path(r['root'])/'ledger.sqlite3' for r in rows]]},
        'boundary': dict(BOUNDARY)}
    holds = {}
    for row in rows:
        for name in ('standard-quarantine.json', 'standard-successor.json', 'standard-canceled-play.json',
            'standard-readiness-disposition.json', 'standard-forward-continuation.json',
            'standard-partial-admission-disposition.json'):
            path = Path(row['root'])/name
            if os.path.lexists(path): holds[str(path)] = pin(path)
        path = registry.root/('standard-successor-'+row['id']+'.claim')
        if os.path.lexists(path): holds[str(path)] = pin(path)
    result['preservedHoldPins'] = holds
    require(len(canonical(result).encode()) <= 58000, 'Bounded setup review required; never prune history')
    return result


def preview(registry, workspace_id, spec):
    before = context(registry, workspace_id, spec)
    native = observe(spec)
    require(context(registry, workspace_id, spec) == before, 'Setup scope changed during native readback')
    return {'request': before, 'reviewHash': digest(before), 'validUntil': 'scope_changes', 'native': native,
        'effect': 'Adopt existing empty identity in registration only; separate binding, readiness, mission Review and Play required'}


def retained(root):
    """File-only completion fence. A missing/partial claim never becomes authority."""
    root = Path(root)
    if not os.path.lexists(root/FENCE):
        require(not os.path.lexists(root/RECEIPT), 'Orphaned setup receipt refuses writes')
        return None
    try: claim, receipt = read(root/FENCE), read(root/RECEIPT)
    except (OSError, ValueError) as error:
        raise Refusal('Partial setup transition stays fenced; no retry or assumed safety') from error
    require(claim.get('kind') == KIND and receipt.get('kind') == KIND and
        claim.get('reviewHash') == receipt.get('reviewHash') == digest(receipt.get('request')) and
        receipt.get('outcome') == 'registration_changed_execution_not_authorized',
        'Partial or changed setup transition stays fenced')
    return receipt


def require_complete(ledger, db):
    receipt = retained(ledger.root)
    meta = Ledger.get(db, 'meta', 1)
    require(receipt is not None or 'emptySetupTransition' not in meta, 'Setup receipt is missing')
    if receipt:
        require(meta.get('brainId') == receipt['request']['spec']['brainId'] and
            meta.get('emptySetupTransition') == receipt['reviewHash'], 'Setup identity or receipt changed')


def confirm(registry, workspace_id, request, confirm_hash, *, confirmed=False, writers_stopped=False,
            fresh_catalog=None):
    require(confirmed is True and writers_stopped is True and request.get('kind') == KIND and
        request.get('workspaceId') == workspace_id and digest(request) == confirm_hash,
        'Exact new setup review and stopped-writer acknowledgment required; original creation approval is consumed')
    # Read historical success before old-identity context; it never reapplies a
    # mapping, recollects evidence or repairs a later change.
    with read_database(registry.db) as db:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (HISTORY,)).fetchone():
            row = db.execute('SELECT data FROM '+HISTORY+' WHERE workspace=?', (workspace_id,)).fetchone()
            if row:
                old = decode(row[0]); require(old['request'] == request, 'Another setup transition owns this target')
                require(retained(Path(request['registration']['root'])) == old, 'Incomplete local setup receipt')
                return old
    require(fresh_catalog is not None, 'A fresh actual app-catalog recheck is required, not a new owner approval')
    recheck = read(fresh_catalog)
    original_catalog = read(request['spec']['catalogObservation'])
    require(recheck.get('source') == 'codex_app.list_projects' and
        type(recheck.get('observedAt')) in (int, float) and 0 <= time.time()-recheck['observedAt'] <= 120 and
        projects.normalize(recheck['completeResult']) == projects.normalize(original_catalog['completeResult']),
        'Actual app catalog changed or stale; the original review is not silently retargeted')
    require(context(registry, workspace_id, request['spec']) == request, 'Reviewed setup context changed')
    native = observe(request['spec'])
    root = Path(request['registration']['root'])
    with contextlib.ExitStack() as stack:
        registry_db = stack.enter_context(registry.tx())
        # Registry -> every registered dashboard/ledger, in canonical order.
        # All old databases are backed up while their writers are fenced too.
        local = None
        for path in sorted(Path(p) for p in request['databases'] if Path(p) != registry.db):
            stack.enter_context(dashboard_lock(path.parent))
            db = stack.enter_context(contextlib.closing(sqlite3.connect(
                path.as_uri()+'?mode=rw', uri=True, isolation_level=None, timeout=5)))
            db.row_factory = sqlite3.Row
            db.execute('BEGIN IMMEDIATE'); stack.callback(db.rollback)
            if path == root/'ledger.sqlite3': local = db
        require(local is not None, 'Selected target lock missing')
        require(context(registry, workspace_id, request['spec']) == request, 'Setup changed at write boundary')
        backup_id = 'empty-setup-'+str(uuid.uuid4())
        backups = registry.root/'backups'; backups.mkdir(mode=0o700, exist_ok=True)
        private_path(backups, existing=True)
        destination = backups/backup_id; destination.mkdir(mode=0o700)
        for index, (path, proof) in enumerate(request['databases'].items()):
            backup_database(Path(path), destination/(str(index)+'.sqlite3'), digest(proof['proof']))
        # Preserve every immutable creation/config/catalog input as private bytes.
        originals = {**{value['path']: value for value in request['setupPins'].values()},
            request['catalogPin']['path']: request['catalogPin'],
            request['spec']['configFile']: pin(request['spec']['configFile']),
            **request['preservedHoldPins'],
            **{value['path']: value for value in request['immutableSetupInputs']}}
        file_backups = []
        for index, (path, proof) in enumerate(originals.items()):
            inspect = input_pin if set(proof) == {'path', 'sha256', 'identity'} else pin
            require(inspect(path) == proof, 'Consumed setup input changed before backup')
            raw, _ = read_file(path, 65536)
            copied = destination/('record-'+str(index)+'.json')
            with os.fdopen(os.open(copied, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'wb') as output:
                output.write(raw); output.flush(); os.fsync(output.fileno())
            require(pin(copied)['sha256'] == proof['sha256'] and inspect(path) == proof, 'Setup backup changed')
            file_backups.append({'original': path, 'pin': proof, 'copy': copied.name})
        exclusive(destination/'manifest.json', {'kind': KIND, 'reviewHash': confirm_hash,
            'databases': [{'original': path, 'proof': proof, 'copy': str(index)+'.sqlite3'}
                for index, (path, proof) in enumerate(request['databases'].items())], 'files': file_backups})
        exclusive(destination/'request.json', request); sync_directory(destination)
        require(context(registry, workspace_id, request['spec']) == request, 'Setup drifted during backup')
        native = observe(request['spec'])
        require(context(registry, workspace_id, request['spec']) == request and
            0 <= time.time()-recheck['observedAt'] <= 120,
            'Fresh unchanged native identity/catalog required at the claim boundary; approval itself has no timer')
        exclusive(root/FENCE, {'kind': KIND, 'reviewHash': confirm_hash, 'at': time.time()})
        receipt = {'kind': KIND, 'request': copy.deepcopy(request), 'reviewHash': confirm_hash,
            'recordedAt': time.time(), 'backupId': backup_id, 'native': native,
            'outcome': 'registration_changed_execution_not_authorized', 'boundary': dict(BOUNDARY)}
        # Local then registry commit is intentionally NOT called cross-DB atomic.
        # The external claim fences every partial state until both commits and
        # the final receipt exist; it cannot rearm a create/load or be retried.
        meta = copy.deepcopy(request['originalMeta'])
        meta.update(brainId=request['spec']['brainId'], emptySetupTransition=confirm_hash,
                    revision=meta['revision']+1)
        repo = Ledger.all(local, 'repos')[0]
        repo.update(projectId=request['spec']['catalogProjectId'])
        Ledger.put(local, 'repos', repo['id'], repo)
        # Old draft/receipt rows stay byte-identical. Create an unreviewed
        # successor draft for the new identity and repository mapping.
        if request['draftHash'] is not None:
            old = Ledger.get(local, 'snapshots', request['draftHash'])
            draft = {**old, 'brainId': request['spec']['brainId'], 'version': old['version']+1,
                'createdAt': time.time(), 'actor': 'dashboard_owner', 'previousHash': request['draftHash'],
                'repositoryBindings': missions.bindings([repo], old['spec']['phase']['scope'])}
            key = digest(draft)
            local.execute('INSERT INTO snapshots VALUES(?,?,?)', (key, 'mission_configuration', canonical(draft)))
            current = meta['missionConfiguration']
            meta['missionConfiguration'] = {'documentHash': key, 'revision': current['revision']+1,
                'version': draft['version'], 'status': 'draft'}
        Ledger.put(local, 'meta', 1, meta)
        data = decode(request['registration']['data'])
        data.update(brainId=request['spec']['brainId'], emptySetupTransition=confirm_hash)
        registry_db.execute('UPDATE workspaces SET brain=?,data=? WHERE id=?', (data['brainId'], canonical(data), workspace_id))
        registry_db.execute('CREATE TABLE IF NOT EXISTS '+HISTORY+'(workspace TEXT PRIMARY KEY,data TEXT NOT NULL)')
        registry_db.execute('INSERT INTO '+HISTORY+' VALUES(?,?)', (workspace_id, canonical(receipt)))
        project = request['newCatalogProject']
        observation = read(request['spec']['catalogObservation'])
        catalog = {'source': projects.SOURCE, 'observedAt': observation['observedAt'], 'recordedAt': time.time(),
            'hash': digest(projects.normalize(observation['completeResult'])), 'projects': projects.normalize(observation['completeResult'])}
        registry_db.execute('CREATE TABLE IF NOT EXISTS project_catalog(id INTEGER PRIMARY KEY CHECK(id=1),data TEXT NOT NULL)')
        registry_db.execute('CREATE TABLE IF NOT EXISTS project_bindings(project_key TEXT PRIMARY KEY,workspace TEXT UNIQUE NOT NULL,data TEXT NOT NULL)')
        registry_db.execute('INSERT OR REPLACE INTO project_catalog VALUES(1,?)', (canonical(catalog),))
        registry_db.execute('DELETE FROM project_bindings WHERE workspace=?', (workspace_id,))
        mapping = {'workspaceId': workspace_id, 'brainId': data['brainId'], 'databaseIdentity': data['databaseIdentity'],
            'locationHash': project['locationHash']}
        registry_db.execute('INSERT INTO project_bindings VALUES(?,?,?)', (project['key'], workspace_id, canonical(mapping)))
        local.commit()
    # The registry transaction has committed. Nothing can execute before this
    # exclusive completion receipt; a persistence failure remains fail-closed.
    exclusive(root/RECEIPT, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', type=Path, required=True)
    parser.add_argument('--workspace', required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('preview'); p.add_argument('spec', type=Path)
    p = sub.add_parser('confirm'); p.add_argument('review', type=Path); p.add_argument('--confirm-hash', required=True)
    p.add_argument('--confirm', action='store_true'); p.add_argument('--writers-stopped', action='store_true')
    p.add_argument('--catalog-recheck', type=Path, required=True)
    sub.add_parser('status')
    args = parser.parse_args()
    registry = Registry(args.platform, read_only=args.action != 'confirm')
    if args.action == 'preview': out = preview(registry, args.workspace, read(args.spec))
    elif args.action == 'confirm':
        value = read(args.review)
        require(set(value) == {'request', 'reviewHash', 'validUntil', 'native', 'effect'} and
            value['reviewHash'] == args.confirm_hash == digest(value['request']), 'Exact saved preview required')
        out = confirm(registry, args.workspace, value['request'], args.confirm_hash,
            confirmed=args.confirm, writers_stopped=args.writers_stopped, fresh_catalog=args.catalog_recheck)
    else:
        with read_database(registry.db) as db:
            row = db.execute('SELECT root FROM workspaces WHERE id=?', (args.workspace,)).fetchone()
            require(row is not None, 'Exact registered target required')
        out = retained(Path(row['root'])) or {'status': 'not_started', 'nativeAction': False}
    print(canonical(out))


if __name__ == '__main__':
    try: main()
    except Refusal as error: raise SystemExit(str(error)) from None
