"""Separately reviewed one-shot inspection loading, never phase continuation.

The current host's tracker cannot establish historical cleanup. An expired run,
its original policy gap and every consumed effect remain unchanged. Status is
file-only; reconcile can only read the same reviewed host after the claim.
"""
import argparse
import hashlib
import os
from pathlib import Path
import time
import uuid

from . import public_host_restart as restart
from .app_server_wake import load_binding
from .core import Refusal, canonical, digest, require
from .host_lifecycle import private_file, sync_directory, write_record
from .native_auth_readiness import require_ready
from .native_policy_evidence import matches, reported
from .native_read_client import ReadProxy, decode, inspect_endpoint
from .public_host_lifecycle import directory_identity, isolated_directory
from .standard_native_observation import _terminals

KIND = 'public_pilot_inspection_v1'
FIELDS = {'version', 'kind', 'reviewDirectory', 'sourceTree', 'restartPath',
          'bindingPath', 'provenance', 'before', 'action', 'fencePath'}
BOUNDARY = {'turnStarts': 0, 'playOrRecoveryReplayed': False, 'bindingInstalled': False,
            'originalPolicyGuardChanged': False, 'usageReset': False, 'expiryChanged': False,
            'controllerAcquired': False, 'ownershipReleased': False,
            'historicalTerminalSafety': 'unknown', 'historicalEffectsReconciled': False,
            'currentTerminalSafety': 'unknown', 'migrationQualified': False,
            'resumeAuthorized': False, 'closeoutAuthorized': False, 'pilotAccepted': False}


def record(path, maximum=65536):
    private_file(path) if maximum <= 65536 else restart.pin(path, maximum)
    return decode(restart.read_file(path, maximum)[0])


def provenance(registry, ledger, restart_path, binding_path):
    """Validate an issued *live* restart, without executing its old source.

    Original endpoints are bytes only. The historical implementation tree may
    differ from this protocol's separately pinned clean tree. This grants no
    restart, transfer or old inspection-load replay.
    """
    spec = record(restart_path)
    require(isinstance(spec, dict) and set(spec) == restart.FIELDS and
            type(spec['version']) is int and spec['version'] == 1 and spec['kind'] == restart.KIND and
            Path(restart_path) == Path(spec['reviewDirectory'])/'restart.json' and
            isinstance(spec['sourceTree'], str) and len(spec['sourceTree']) == 40 and
            all(c in '0123456789abcdef' for c in spec['sourceTree']), 'Exact issued restart provenance required')
    directory = isolated_directory(spec['reviewDirectory'])
    require(spec['backupPath'] == str(directory/'native-home-backup') and
            spec['homeSnapshotPin']['path'] == str(directory/'home-snapshot.json'), 'Closed original backup locations required')
    values = restart.inputs(registry, ledger, spec['previousAttempt'], spec['transferDirectory'])
    launch, previous, earlier_pins, transfer, source, transfer_pins, scope = values
    require((launch, earlier_pins, source, transfer_pins, scope) ==
            (spec['launchSpec'], spec['previousPins'], spec['sourceBinding'], spec['transferPins'], spec['scope']),
            'Original transfer, paused run, usage, receipts or expiry changed')
    attempt = directory/'attempt'
    intent, state = record(attempt/'intent.json'), record(attempt/'status.json')
    restart.validate_status(state, spec, execution_boundary=True)
    require(intent.get('kind') == restart.KIND and intent.get('specHash') == digest(spec) and
            intent.get('reviewHash') == restart.review_hash(spec) and
            restart.pin(attempt/'exec.claim')['bytes'] == 0, 'Issued restart intent/claim required')
    fence = restart.restart_fence(ledger, launch, transfer, previous)
    require(str(fence) == spec['fencePath'] and record(fence) ==
            {'kind': restart.KIND, 'specHash': digest(spec), 'reviewDirectory': str(directory)}, 'Restart fence changed')
    for _ in range(2):
        require(restart.process_absent(previous['pid']), 'Predecessor PID is live, reused or unknown')
        restart.live_process(spec, state)
    require(restart.pin(spec['homeSnapshotPin']['path'], 1_000_000) == spec['homeSnapshotPin'], 'Original backup pin changed')
    snapshot = record(spec['homeSnapshotPin']['path'], 1_000_000)
    restart.backup_check(spec, snapshot)
    config = restart.restricted_config(launch['codexHome'], launch['cwd'])
    # No home enumeration, SQL access or auth.json read. Only previously pinned
    # installation/history prefixes and the fixed restricted config are read.
    for relative, pin in snapshot['files'].items():
        if relative.startswith('sessions/') or relative == 'installation_id':
            raw, _ = restart.read_file(Path(launch['codexHome'])/relative)
            require(len(raw) >= pin['bytes'] and hashlib.sha256(raw[:pin['bytes']]).hexdigest() == pin['sha256'],
                    'Original history prefix or installation identity changed')
    binding = load_binding(binding_path)
    brain = transfer['brainId']
    old = record(transfer['destinationBindingPath'])
    require(set(binding['brains']) == {brain} and binding['brains'] == old['brains'],
            'Exact transferred brain, both project IDs and native policy required')
    sockets = isolated_directory(spec['socketDirectory'])
    require(directory_identity(sockets) == spec['socketDirectoryIdentity'], 'Reviewed socket directory changed')
    alias = sockets/'host.sock'
    require(alias.lstat().st_uid == os.getuid(), 'Socket rendezvous owner changed')
    actual = inspect_endpoint(str(Path(launch['runtimePackage']['root'])/'bin/codex'),
                              str(alias.resolve(strict=True)), old['endpoint']['serverIdentityHash'])
    require(binding['endpoint'] == actual and actual['socket'] != old['endpoint']['socket'] and
            actual['socketIdentity'] != old['endpoint']['socketIdentity'], 'Exact current socket epoch required; no old reconnect')
    pins = [restart.pin(p) for p in (Path(restart_path), attempt/'intent.json', attempt/'status.json',
                                   attempt/'exec.claim', fence, Path(binding_path))]
    return {'restartHash': digest(spec), 'pins': pins, 'scope': scope, 'config': config,
            'host': state, 'binding': binding, 'home': launch['codexHome'], 'cwd': launch['cwd'],
            'brainId': brain, 'projectId': transfer['snapshot']['project']['id'],
            'catalogProjectId': transfer['catalogProjectId'], 'latestTurnId': transfer['snapshot']['latestTurnId'],
            'latestTurnStatus': transfer['snapshot']['latestTurnStatus']}


def load_params(scope):
    return {'threadId': scope['brainId'], 'cwd': scope['cwd'], 'excludeTurns': True,
            'approvalPolicy': 'on-request', 'approvalsReviewer': 'user', 'sandbox': 'workspace-write',
            'config': {'features': {'code_mode': {'enabled': False}, 'goals': False,
                                    'apps': False, 'plugins': False, 'hooks': False}}}


class InspectionProxy(ReadProxy):
    """One fixed optional resume; all other methods/parameters are metadata-only."""
    def __init__(self, scope):
        self.scope, self.load_permitted, self.load_used = scope, False, False
        super().__init__(scope['binding']['endpoint'])

    def _rpc(self, method, params):
        brain = self.scope['brainId']
        allowed = {'initialize': {'clientInfo': {'name': 'codex_orchestrator_observer', 'version': '1'},
                                  'capabilities': {'experimentalApi': True}},
                   'project/read': {'projectId': self.scope['projectId']},
                   'thread/read': {'threadId': brain, 'includeTurns': False},
                   'thread/turns/list': {'threadId': brain, 'cursor': None, 'limit': 1,
                                         'sortDirection': 'desc', 'itemsView': 'notLoaded'},
                   'thread/effectivePolicy/read': {'threadId': brain},
                   'mcpServerStatus/list': {'detail': 'toolsAndAuthOnly'},
                   'account/read': {'refreshToken': False}}
        if method == 'thread/resume':
            require(self.load_permitted and not self.load_used and canonical(params) == canonical(load_params(self.scope)),
                    'Only one claimed exact metadata inspection load is permitted')
            self.load_used = True  # Claim before I/O; even a lost response consumes it.
        elif method == 'thread/backgroundTerminals/list':
            require(isinstance(params, dict) and set(params) == {'threadId', 'cursor', 'limit'} and
                    params['threadId'] == brain and type(params['limit']) is int and params['limit'] == 64 and
                    (params['cursor'] is None or isinstance(params['cursor'], str) and 0 < len(params['cursor']) <= 256),
                    'Exact bounded current tracked-terminal metadata required')
        else:
            require(method in allowed and canonical(params) == canonical(allowed[method]),
                    'Inspection refuses non-metadata methods or changed parameters')
        return super()._rpc(method, params)

    def call(self, method, params):
        return self._rpc(method, params)


def sample(proxy, scope):
    project_response = proxy._rpc('project/read', {'projectId': scope['projectId']})
    project = project_response.get('project') if isinstance(project_response, dict) else None
    require(isinstance(project, dict) and project.get('id') == scope['projectId'] and
            project.get('roots') == [{'path': scope['cwd']}], 'Native project identity/root changed')
    thread_params = {'threadId': scope['brainId'], 'includeTurns': False}
    thread_response = proxy._rpc('thread/read', thread_params)
    thread = thread_response.get('thread') if isinstance(thread_response, dict) else None
    require(isinstance(thread, dict) and thread.get('id') == scope['brainId'] and
            thread.get('projectId') == scope['projectId'] and thread.get('cwd') == scope['cwd'] and
            isinstance(thread.get('status'), dict) and thread['status'].get('type') in {'notLoaded', 'idle'} and
            thread['status'].get('activeFlags') in (None, []), 'Exact inactive brain required; unknown is not idle')
    turn_params = {'threadId': scope['brainId'], 'cursor': None, 'limit': 1,
                   'sortDirection': 'desc', 'itemsView': 'notLoaded'}
    page = proxy._rpc('thread/turns/list', turn_params)
    turns = page.get('data') if isinstance(page, dict) else None
    require(isinstance(turns, list) and len(turns) == 1 and isinstance(turns[0], dict) and
            turns[0].get('id') == scope['latestTurnId'] and turns[0].get('status') == scope['latestTurnStatus'] and
            scope['latestTurnStatus'] in {'completed', 'interrupted', 'failed'}, 'Original latest ended turn changed')
    require(proxy._rpc('mcpServerStatus/list', {'detail': 'toolsAndAuthOnly'}) == {'data': [], 'nextCursor': None},
            'Complete empty MCP inventory required')
    policy = reported(proxy._rpc('thread/effectivePolicy/read', {'threadId': scope['brainId']}),
                      scope['brainId'], scope['cwd'])
    loaded = thread['status']['type'] == 'idle'
    require(matches(policy) if loaded else policy is None,
            'Actual loaded restricted policy required; unloaded policy must remain unknown')
    auth = require_ready(proxy)
    terminals = _terminals(proxy, scope['brainId']) if loaded else None
    after_response = proxy._rpc('thread/read', thread_params)
    after = after_response.get('thread') if isinstance(after_response, dict) else None
    after_turns = proxy._rpc('thread/turns/list', turn_params)
    require(isinstance(after, dict) and all(after.get(k) == thread.get(k) for k in ('id', 'projectId', 'cwd', 'status')) and
            isinstance(after_turns, dict) and isinstance(after_turns.get('data'), list) and len(after_turns['data']) == 1 and
            isinstance(after_turns['data'][0], dict) and
            all(after_turns['data'][0].get(k) == turns[0].get(k) for k in ('id', 'status')),
            'Brain activity or latest turn changed across metadata/terminal reads')
    return {'activity': thread['status']['type'], 'latestTurnId': scope['latestTurnId'],
            'latestTurnStatus': scope['latestTurnStatus'], 'policy': policy,
            'authentication': {k: v for k, v in auth.items() if k != 'checkedAt'},
            'trackedTerminals': terminals}


def repeated(proxy, scope):
    first, second = sample(proxy, scope), sample(proxy, scope)
    require(first == second, 'Native identity, activity, policy, authentication or terminals changed')
    return second


def fence_path(ledger, scope):
    # Canonical original ownership, not review directory, endpoint or timestamps.
    context = scope['scope']['context']
    key = digest({'workspaceId': ledger.workspace_id, 'brainId': scope['brainId'],
                  'runId': context['runId'], 'originalPlayId': context['originalPlayId']})
    return ledger.root/('public-pilot-inspection-'+key+'.claim')


def fence_record(spec):
    return {'kind': KIND, 'specHash': digest(spec), 'reviewHash': review_hash(spec),
            'reviewDirectory': spec['reviewDirectory']}


def review_hash(spec):
    return digest({'kind': KIND, 'specHash': digest(spec), 'action': spec['action']})


def prepare(registry, ledger, restart_path, binding_path, directory):
    tree = restart.source_tree()
    scope = provenance(registry, ledger, restart_path, binding_path)
    directory = Path(directory); isolated_directory(directory.parent)
    # No writes under the checkout, home, package, socket, ledger or prior journals.
    original = record(restart_path)
    roots = [ledger.root, Path(scope['home']), Path(scope['cwd']), Path(original['socketDirectory']),
             Path(original['launchSpec']['runtimePackage']['root']), Path(original['reviewDirectory']),
             Path(original['previousAttempt']), Path(original['transferDirectory'])]
    require(directory.is_absolute() and not directory.exists() and not directory.is_symlink() and
            all(not directory.is_relative_to(p) and not p.is_relative_to(directory) for p in roots),
            'New private disjoint inspection review directory required')
    fence = fence_path(ledger, scope)
    require(not fence.exists() and not fence.is_symlink(), 'Original pilot inspection is already consumed; never reload')
    with InspectionProxy(scope) as proxy:
        before = repeated(proxy, scope)
    require(before['trackedTerminals'] in (None, []), 'Existing tracked terminals require separate supervision')
    require(provenance(registry, ledger, restart_path, binding_path) == scope and restart.source_tree() == tree,
            'Protected state changed during preparation')
    spec = {'version': 1, 'kind': KIND, 'reviewDirectory': str(directory), 'sourceTree': tree,
            'restartPath': str(restart_path), 'bindingPath': str(binding_path), 'provenance': scope,
            'before': before, 'action': 'load_for_inspection' if before['activity'] == 'notLoaded' else 'observe_only',
            'fencePath': str(fence)}
    directory.mkdir(mode=0o700); sync_directory(directory.parent)
    write_record(directory/'inspection.json', spec)
    return preview(registry, ledger, directory/'inspection.json')


def load_spec(path):
    spec = record(path)
    require(isinstance(spec, dict) and set(spec) == FIELDS and type(spec['version']) is int and spec['version'] == 1 and
            spec['kind'] == KIND and Path(path) == Path(spec['reviewDirectory'])/'inspection.json' and
            spec['action'] in {'load_for_inspection', 'observe_only'} and
            spec['action'] == ('load_for_inspection' if spec['before']['activity'] == 'notLoaded' else 'observe_only'),
            'Closed exact pilot inspection specification required')
    isolated_directory(spec['reviewDirectory'])
    return spec


def validate(registry, ledger, path, *, claimed=False):
    spec = load_spec(path)
    require(restart.source_tree() == spec['sourceTree'], 'Inspection implementation changed')
    scope = provenance(registry, ledger, spec['restartPath'], spec['bindingPath'])
    require(scope == spec['provenance'] and str(fence_path(ledger, scope)) == spec['fencePath'],
            'Reviewed inspection host, original scope or canonical fence changed')
    fence = Path(spec['fencePath'])
    if claimed:
        require(record(fence) == fence_record(spec) and record(Path(spec['reviewDirectory'])/'attempt/intent.json') ==
                fence_record(spec), 'Exact durable inspection intent/fence required')
        if spec['action'] == 'load_for_inspection':
            require(record(Path(spec['reviewDirectory'])/'attempt/inspection-load.claim') == {'specHash': digest(spec)},
                    'Original inspection load claim required; never recreate it')
    else:
        require(not fence.exists() and not fence.is_symlink() and
                not (Path(spec['reviewDirectory'])/'attempt').exists(), 'Inspection consumed; only read-only reconciliation remains')
    return spec


def preview(registry, ledger, path):
    spec = validate(registry, ledger, path)
    with InspectionProxy(spec['provenance']) as proxy:
        require(repeated(proxy, spec['provenance']) == spec['before'], 'Reviewed native state changed')
    require(validate(registry, ledger, path) == spec, 'Scope changed during preview')
    return {'kind': KIND, 'reviewHash': review_hash(spec), 'validity': 'until_scope_changes',
            'action': spec['action'], 'brainId': spec['provenance']['brainId'],
            'runId': spec['provenance']['scope']['context']['runId'],
            'maximumInspectionLoads': 1 if spec['action'] == 'load_for_inspection' else 0,
            'loadsMade': 0, 'boundary': BOUNDARY}


def exclusive(path, value):
    with os.fdopen(os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600), 'w') as stream:
        stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
    sync_directory(path.parent)


def retain(registry, ledger, path, spec, proxy, *, reconciled):
    observation = repeated(proxy, spec['provenance'])
    require(observation['activity'] == 'idle' and observation['trackedTerminals'] == [],
            'Current loaded-idle and complete empty tracked-terminal observations required')
    require(validate(registry, ledger, path, claimed=True) == spec, 'Scope changed after native boundary')
    attempt = Path(spec['reviewDirectory'])/'attempt'
    ack_path = attempt/'load-ack.json'
    acknowledged = False
    if ack_path.exists():
        ack = record(ack_path)
        require(ack == {'specHash': digest(spec), 'acknowledged': True}, 'Inspection acknowledgment changed')
        acknowledged = True
    result = {'kind': KIND, 'specHash': digest(spec), 'checkedAt': time.time(),
              'status': 'current_inspection_retained', 'reconciledReadOnly': reconciled,
              'loadDelivery': 'not_requested' if spec['action'] == 'observe_only' else
                              'acknowledged' if acknowledged else 'unknown',
              'currentObservation': observation, 'boundary': BOUNDARY}
    # Append new observations, never overwrite a failure/unknown outcome or
    # pretend a later read acknowledged an uncertain load response.
    write_record(attempt/('observation-'+str(uuid.uuid4())+'.json'), result)
    return result


def apply(registry, ledger, path, confirm_hash):
    spec = validate(registry, ledger, path)
    require(confirm_hash == review_hash(spec), 'Exact new inspection-only review required')
    with InspectionProxy(spec['provenance']) as proxy:
        require(repeated(proxy, spec['provenance']) == spec['before'], 'Reviewed native state changed before claim')
        require(validate(registry, ledger, path) == spec, 'Inspection scope changed before claim')
        attempt = Path(spec['reviewDirectory'])/'attempt'
        attempt.mkdir(mode=0o700); sync_directory(attempt.parent)
        write_record(attempt/'intent.json', fence_record(spec))
        exclusive(Path(spec['fencePath']), fence_record(spec))
        if spec['action'] == 'load_for_inspection':
            exclusive(attempt/'inspection-load.claim', {'specHash': digest(spec)})
        require(validate(registry, ledger, path, claimed=True) == spec, 'Scope drift after claim; attempt remains consumed')
        require(repeated(proxy, spec['provenance']) == spec['before'], 'Native drift after claim; attempt remains consumed')
        if spec['action'] == 'load_for_inspection':
            proxy.load_permitted = True
            reply = proxy._rpc('thread/resume', load_params(spec['provenance']))
            thread = reply.get('thread') if isinstance(reply, dict) else None
            require(isinstance(thread, dict) and thread.get('id') == spec['provenance']['brainId'] and
                    thread.get('cwd') == spec['provenance']['cwd'] and thread.get('turns', []) == [],
                    'Inspection load acknowledgment is incomplete; do not retry')
            write_record(attempt/'load-ack.json', {'specHash': digest(spec), 'acknowledged': True})
        return retain(registry, ledger, path, spec, proxy, reconciled=False)


def reconcile(registry, ledger, path):
    spec = validate(registry, ledger, path, claimed=True)
    if spec['action'] == 'load_for_inspection':
        require(record(Path(spec['reviewDirectory'])/'attempt/inspection-load.claim') == {'specHash': digest(spec)},
                'Original inspection claim required; reconciliation never creates it')
    with InspectionProxy(spec['provenance']) as proxy:
        return retain(registry, ledger, path, spec, proxy, reconciled=True)


def status(path):
    """Saved intent only. No process, endpoint, ledger, source or native query."""
    spec = load_spec(path)
    attempt = Path(spec['reviewDirectory'])/'attempt'
    claimed = (attempt/'intent.json').exists()
    if claimed:
        require(record(attempt/'intent.json') == fence_record(spec), 'Saved inspection intent changed')
    return {'kind': KIND, 'specHash': digest(spec), 'historical': True,
            'status': 'consumed_outcome_not_inferred' if claimed else 'prepared_not_submitted',
            'claimRetained': claimed, 'boundary': BOUNDARY}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', type=Path, required=True)
    parser.add_argument('--workspace', required=True)
    sub = parser.add_subparsers(dest='operation', required=True)
    setup = sub.add_parser('prepare')
    for name in ('restart_manifest', 'binding', 'review_directory'): setup.add_argument(name, type=Path)
    for operation in ('preview', 'apply', 'reconcile', 'status'):
        item = sub.add_parser(operation); item.add_argument('manifest', type=Path)
        if operation == 'apply': item.add_argument('--confirm-hash', required=True)
    args = parser.parse_args()
    from .workspaces import Registry
    try:
        if args.operation == 'status': value = status(args.manifest)
        else:
            registry = Registry(args.platform); ledger = registry.ledger(args.workspace)
            if args.operation == 'prepare': value = prepare(registry, ledger, args.restart_manifest, args.binding, args.review_directory)
            elif args.operation == 'apply': value = apply(registry, ledger, args.manifest, args.confirm_hash)
            elif args.operation == 'reconcile': value = reconcile(registry, ledger, args.manifest)
            else: value = preview(registry, ledger, args.manifest)
        print(canonical(value))
    except (Refusal, OSError, KeyError, ValueError, TypeError) as error:
        parser.exit(1, 'Pilot inspection refused: '+(str(error) if isinstance(error, Refusal) else 'private state unavailable')+'\n')


if __name__ == '__main__': main()
