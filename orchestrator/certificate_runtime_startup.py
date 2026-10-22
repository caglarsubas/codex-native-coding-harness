"""One reviewed, zero-turn loaded-runtime session on the issued certificate host.

Preparing/status never connect. Only an exact new confirmation after verified
backups may load once, then retain that SAME foreground connection. No worker,
phase, receipt, replay, reconnect, or normal identity authority is provided.
"""
import argparse
import contextlib
import hashlib
import os
from pathlib import Path
import queue
import sqlite3
import time

from . import certificate_worker_readiness as evidence
from .app_server_wake import WakeProxy
from .core import Refusal, canonical, digest, require
from .host_lifecycle import sync_directory
from .native_read_client import validate_endpoint
from .public_pilot_inspection import load_params
from .standard_quarantine import exclusive

dashboard, worker = evidence.dashboard, evidence.worker
KIND = 'certificate_loaded_runtime_startup_v1'
PR195 = '0b1473ed766746dafcbed053c072e35846282fc62233702b348f1058fd950e0a'
SECONDS = 900
BOUNDARY = {**{k: v for k, v in evidence.BOUNDARY.items() if k not in ('nativeLoadMade', 'subscriptionMade')},
            'newRestrictedLoadAuthorized': True, 'originalConnectionSubscriptionOnly': True,
            'maximumLoads': 1, 'maximumTurns': 0,
            'foregroundConnectionOnly': True, 'reconnectAuthorized': False,
            'workerExecutionAuthorized': False, 'loadedPolicyIsExecutionAuthority': False}
FIELDS = {'version', 'kind', 'sourceHash', 'executionSource', 'repairFile', 'launchedSource',
          'context', 'observationDirectory', 'observationSource', 'observationPins',
          'catalogPin', 'journal', 'maximumSeconds', 'boundary'}


def original_observation(directory, source, context):
    """Read complete PR-195 bytes as historical evidence, never import them.

    Its timestamp is NOT refreshed or used as current load authorization. The
    exact same native scene must be independently repeated at application.
    """
    root = dashboard.repair.launch.isolated_directory(directory)
    require({p.name for p in root.iterdir()} == {'intent.json', 'report.json', 'seal.json'},
            'Complete original observation required; partial observations never authorize startup')
    pins = {n: dashboard.pin(root / n) for n in ('intent.json', 'report.json', 'seal.json')}
    intent, report, seal = (dashboard.read(root / n) for n in ('intent.json', 'report.json', 'seal.json'))
    q = intent['request']
    proof = worker.startup.prior.source_proof(source)
    assets = {n: hashlib.sha256(dashboard.repair.restart.read_file(Path(source) / 'web' / n, 512000)[0]).hexdigest()
              for n in dashboard.WEB_FILES}
    require(q['sourceHash'] == digest({'python': proof['sourceHash'], 'web': assets}) and
            q['sourceHash'] in (PR195, dashboard.source_hash()) and
            set(q) == evidence.FIELDS and q['version'] == 1 and type(q['version']) is int and
            q['kind'] == evidence.KIND and q['context'] == context and q['boundary'] == evidence.BOUNDARY and
            q['directory'] == str(root) and
            intent == {'kind': evidence.KIND, 'reviewHash': digest(q), 'request': q,
                       'startupCatalogPin': intent['startupCatalogPin']} and
            seal == {'kind': evidence.KIND, 'intentPin': pins['intent.json'], 'reportPin': pins['report.json']},
            'Exact immutable qualified observation/source required')
    dashboard.catalog(q['catalogPin']['path'], context['host'])
    require(dashboard.pin(q['catalogPin']['path']) == q['catalogPin'] and
            dashboard.catalog(intent['startupCatalogPin']['path'], context['host']) == intent['startupCatalogPin'],
            'Original dual-project catalog pins changed')
    evidence.check_report(q, report)
    require(report['status'] == 'blocked' and report['blockers'] ==
            ['brain_not_loaded', 'loaded_policy_unknown', 'current_trackers_unknown'],
            'Only a positively observed unloaded, otherwise eligible worker target qualifies')
    return proof, {**pins, 'reviewCatalog': q['catalogPin'], 'collectionCatalog': intent['startupCatalogPin']}


def owner(host):
    # Stable original target/preparation, NOT source/version/request/host/output.
    db = host['databases']['workspace:' + host['workspaceId']]
    platform = Path(host['repairPin']['path'])
    _, _, registry, _ = dashboard.foundation(platform, host['launchedSource']['root'])
    return registry.root / 'certificate-runtime-startups' / digest({'workspace': host['workspaceId'],
        'ledgerInode': Path(db['path']).stat().st_ino, 'originalStartup': host['startupHash']})


def prepare(repair_file, launched_source, observation_directory, observation_source, catalog_file):
    context = evidence.scope(repair_file, launched_source)
    proof, pins = original_observation(observation_directory, observation_source, context)
    host = context['host']; journal = owner(host)
    require(not os.path.lexists(journal), 'Loaded-runtime startup already claimed or partial; never retry')
    q = {'version': 1, 'kind': KIND, 'sourceHash': dashboard.source_hash(),
         'executionSource': worker.startup.prior.source_proof(worker.startup.owned.preplay.SOURCE),
         'repairFile': str(repair_file), 'launchedSource': str(launched_source), 'context': context,
         'observationDirectory': str(observation_directory), 'observationSource': proof,
         'observationPins': pins, 'catalogPin': dashboard.catalog(catalog_file, host),
         'journal': str(journal), 'maximumSeconds': SECONDS, 'boundary': dict(BOUNDARY)}
    require(len(canonical(q).encode()) <= 64000, 'Bounded exact loaded-runtime review required')
    return {'request': q, 'reviewHash': digest(q), 'validUntil': 'scope_changes',
        'effect': 'One restricted metadata-only load and zero-turn original foreground session, at most 900 seconds; no Play',
        'executionReviewAvailable': False}


def validate(q, *, claimed=False):
    require(isinstance(q, dict) and set(q) == FIELDS and type(q['version']) is int and q['version'] == 1 and
            q['kind'] == KIND and q['sourceHash'] == dashboard.source_hash() and q['boundary'] == BOUNDARY and
            type(q['maximumSeconds']) is int and q['maximumSeconds'] == SECONDS and
            q['executionSource'] == worker.startup.prior.source_proof(worker.startup.owned.preplay.SOURCE),
            'Exact current startup implementation and execution directory required')
    context = evidence.scope(q['repairFile'], q['launchedSource'])
    proof, pins = original_observation(q['observationDirectory'], q['observationSource']['root'], context)
    require(context == q['context'] and (proof, pins) == (q['observationSource'], q['observationPins']) and
            dashboard.catalog(q['catalogPin']['path'], context['host']) == q['catalogPin'] and
            str(owner(context['host'])) == q['journal'], 'Startup scope, accounting, source or identities changed')
    root = Path(q['journal'])
    if claimed:
        require(dashboard.read(root / 'intent.json') == {'kind': KIND, 'reviewHash': digest(q), 'request': q} and
                not os.path.lexists(root / 'stop.json'), 'Startup stopped or original intent changed')
    else:
        require(not os.path.lexists(root), 'Any prior claim is permanent; no reload or source/host successor')


def inputs(q):
    c = q['context']['host']
    projection = {'context': c, 'evidencePins': q['observationPins']}
    return {**dashboard.backup_inputs(projection), q['catalogPin']['path']: q['catalogPin']}


def backup(q, destination, *, writers_stopped=False):
    require(writers_stopped is True, 'Independently stopped operational writers required')
    validate(q); host = q['context']['host']; dashboard.quiet(host['databases'])
    root = dashboard.disjoint(destination, host)
    protected = [Path(q['observationDirectory']), Path(q['observationSource']['root']),
                 Path(q['executionSource']['root'])]
    require(all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in protected), 'Disjoint private backup required')
    root.mkdir(mode=0o700); files = {}
    exclusive(root / 'review.json', q)
    for i, (key, value) in enumerate(sorted(host['databases'].items())):
        path = root / ('database-' + str(i) + '.sqlite3')
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
        with dashboard.repair.maintenance.startup.standard.read_db(value['path']) as src, contextlib.closing(sqlite3.connect(path)) as dst:
            src.backup(dst)
            require(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Backup integrity failed')
            dst.execute('PRAGMA journal_mode=DELETE')
        require(dashboard.repair.maintenance.partial.database_proof(path)['fingerprint'] == value['fingerprint'], 'Backup differs')
        with path.open('rb') as stream: os.fsync(stream.fileno())
        files[path.name] = {'key': key, 'pin': dashboard.repair.restart.pin(path, dashboard.repair.restart.MAX_FILE)}
    for i, (path, expected) in enumerate(sorted(inputs(q).items())):
        require(dashboard.pin(path) == expected, 'Preserved input changed')
        dest = root / ('input-' + str(i) + '.json')
        raw = dashboard.repair.restart.read_file(path)[0]
        with os.fdopen(os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        require(dashboard.pin(path) == expected and dashboard.pin(dest)['sha256'] == expected['sha256'], 'Backup differs')
        files[dest.name] = {'original': expected, 'pin': dashboard.pin(dest)}
    exclusive(root / 'manifest.json', {'kind': KIND, 'reviewHash': digest(q), 'files': files})
    sync_directory(root); validate(q); verify_backup(q, root); dashboard.quiet(host['databases'])
    return {'backup': str(root), 'verified': True, 'reviewHash': digest(q)}


def verify_backup(q, directory):
    root = dashboard.repair.launch.isolated_directory(directory)
    m = dashboard.read(root / 'manifest.json'); originals = inputs(q); dbs = q['context']['host']['databases']
    require(set(m) == {'kind', 'reviewHash', 'files'} and m['kind'] == KIND and m['reviewHash'] == digest(q) and
            dashboard.read(root / 'review.json') == q and {p.name for p in root.iterdir()} ==
            set(m['files']) | {'review.json', 'manifest.json'}, 'Complete exact private backup required')
    expected = {'database-' + str(i) + '.sqlite3' for i in range(len(dbs))} | {'input-' + str(i) + '.json' for i in range(len(originals))}
    require(set(m['files']) == expected, 'Missing or additional backup files')
    keys, paths = [], []
    for name, row in m['files'].items():
        if 'key' in row:
            keys.append(row['key'])
            require(set(row) == {'key', 'pin'} and dashboard.repair.restart.pin(root / name, dashboard.repair.restart.MAX_FILE) == row['pin'] and
                    dashboard.repair.maintenance.partial.database_proof(root / name)['fingerprint'] == dbs[row['key']]['fingerprint'],
                    'Original database backup changed')
        else:
            path = row['original']['path']; paths.append(path)
            require(set(row) == {'original', 'pin'} and row['original'] == originals[path] == dashboard.pin(path) and
                    dashboard.pin(root / name) == row['pin'] and row['pin']['sha256'] == row['original']['sha256'], 'Original backup input changed')
    require(sorted(keys) == sorted(dbs) and sorted(paths) == sorted(originals), 'All originals must be backed up once')


class RuntimeProxy(worker.WorkerReadProxy, WakeProxy):
    """Closed metadata vocabulary plus ONE exact claimed restricted load.

    The inherited original-pipe reader handles control frames, not authority.
    No turn, arbitrary RPC, subscribe, permission response or cancel exists.
    """
    def __init__(self, host):
        self.host = host; self.load_permitted = self.load_used = False
        super().__init__(host['endpoint'], host['brainId'], host['record']['projectId'])

    def _rpc(self, method, params):
        if method == 'thread/resume':
            require(self.load_permitted and not self.load_used and canonical(params) == canonical(load_params(
                {'brainId': self.brain, 'cwd': self.host['checkout']})), 'One exact claimed restricted load only')
            self.load_used = True  # Before I/O; uncertainty never rearms.
            return WakeProxy._rpc(self, method, params)
        return super()._rpc(method, params)


def sample(proxy, q):
    host = q['context']['host']
    scene = worker.startup.owned.repeated(proxy, {'endpoint': host['endpoint'],
        'brains': {host['brainId']: host['record']}}, host['brainId'])
    require(scene['latestTurn'] == {'id': host['latestTurnId'], 'status': 'completed'}, 'Original preparation must remain latest')
    return scene


def no_events(proxy):
    stream = getattr(proxy, '_event_stream', None)
    if stream is None: return  # Only synthetic fixtures have no actual process.
    stream.check()
    for _ in range(65):
        try:
            row, size = stream.events.get_nowait()
            with stream.lock: stream.bytes -= size
        except queue.Empty: return
        require(isinstance(row, dict) and 'id' not in row and row.get('method') in
                ('thread/started', 'thread/status/changed') and isinstance(row.get('params'), dict),
                'Unsolicited request, input or work refuses; never respond or cancel')
        params = row['params']
        if row['method'] == 'thread/status/changed':
            require(params.get('threadId') == proxy.brain and params.get('status') == {'type': 'idle'}, 'Native activity changed')
        else:
            require(params.get('thread', {}).get('id') == proxy.brain, 'Foreign native event')
    raise Refusal('Native notification flood; never reconnect')


def hold(proxy, q, deadline):
    """Original foreground only; no JSON RPC/model keepalive or dispatch loop."""
    next_check = time.monotonic()
    while time.monotonic() < deadline:
        no_events(proxy)
        if os.path.lexists(Path(q['journal']) / 'stop.json'): return 'owner_stopped'
        if time.monotonic() >= next_check:
            validate(q, claimed=True)  # Files/OS only, never native metadata polling.
            next_check = time.monotonic() + 5
        time.sleep(min(.25, max(0, deadline - time.monotonic())))
    return 'window_ended'


def start(q, confirmation, backup_root, catalog_file, *, writers_stopped=False):
    require(writers_stopped is True and confirmation == digest(q), 'Exact new startup approval and stopped writers required')
    validate(q); host = q['context']['host']; verify_backup(q, backup_root); dashboard.quiet(host['databases'])
    catalog = dashboard.catalog(catalog_file, host, fresh=True)
    root = Path(q['journal']); root.parent.mkdir(mode=0o700, exist_ok=True)
    dashboard.repair.launch.isolated_directory(root.parent)
    root.mkdir(mode=0o700); sync_directory(root.parent)  # Canonical permanent ownership before any native connection.
    exclusive(root / 'intent.json', {'kind': KIND, 'reviewHash': digest(q), 'request': q})
    result = 'incomplete_unknown'; attempted = False; stage = 'scope_recheck'; proxy = None
    try:
        validate(q, claimed=True); verify_backup(q, backup_root); dashboard.quiet(host['databases'])
        require(dashboard.catalog(catalog_file, host, fresh=True) == catalog, 'Fresh catalog changed')
        stage = 'original_connection'; proxy = RuntimeProxy(host); proxy.__enter__(); proxy.begin_readiness(SECONDS)
        deadline = proxy._readiness_owned_deadline
        before_at = time.time(); before = sample(proxy, q); checked = time.monotonic()
        prior = dashboard.read(Path(q['observationDirectory']) / 'report.json')['native']
        require(before == prior and before['activity'] == 'notLoaded', 'Fresh native scene differs from exact startup review')
        validate(q, claimed=True); verify_backup(q, backup_root); dashboard.quiet(host['databases'])
        require(dashboard.catalog(catalog_file, host, fresh=True) == catalog and
                0 <= time.monotonic() - checked <= 120, 'Startup scope stale before load; no retry')
        no_events(proxy); validate_endpoint(host['endpoint'])
        exclusive(root / 'load.claim.json', {'reviewHash': digest(q), 'purpose': KIND})
        stage = 'restricted_load'; proxy.load_permitted = True; attempted = True
        response = proxy._rpc('thread/resume', load_params({'brainId': host['brainId'], 'cwd': host['checkout']}))
        require(response.get('thread', {}).get('id') == host['brainId'], 'Load acknowledgment unknown; do not retry')
        stage = 'post_load_verification'; after = sample(proxy, q)
        require(after['activity'] == 'idle' and worker.policy_matches(after['policy']) and after['trackedTerminals'] == [] and
                after['authenticationHash'] == before['authenticationHash'], 'Actual loaded policy/account/trackers required')
        models, pages = worker.public.models(proxy); models2, pages2 = worker.public.models(proxy)
        require(models == models2 and pages == pages2 and sample(proxy, q) == after, 'Loaded metadata/model drift')
        validate(q, claimed=True); dashboard.quiet(host['databases']); no_events(proxy)
        require(0 <= time.time() - before_at <= 120, 'Loaded startup evidence stale before retention')
        exclusive(root / 'loaded.json', {'kind': KIND, 'reviewHash': digest(q), 'observedAt': before_at,
            'throughAt': time.time(), 'native': after, 'models': models, 'modelPageHashes': pages,
            'ownerPid': os.getpid(), 'processIdentity': dashboard.repair.restart.process_identity(os.getpid()),
            'maximumSeconds': SECONDS, 'boundary': dict(BOUNDARY), 'executionReviewAvailable': False})
        print(canonical({'status': 'loaded_runtime_observed_not_activated', 'journal': str(root),
            'reviewHash': digest(q), 'maximumSeconds': SECONDS, 'executionReviewAvailable': False}), flush=True)
        stage = 'foreground_session'; result = hold(proxy, q, deadline)
    finally:
        if proxy is not None: proxy.__exit__(None, None, None)
        exclusive(root / 'closed.json', {'kind': KIND, 'reviewHash': digest(q), 'status': result,
            'lastStage': stage, 'loadAttempted': attempted, 'connectionClosed': True,
            'reconnectAllowed': False, 'terminalSafety': 'unknown', 'pilotAccepted': False})
    return status(q)


def status(q):
    """Saved facts only. No native connection, live-ownership assertion or renewal."""
    require(isinstance(q, dict) and set(q) == FIELDS and q['kind'] == KIND and q['boundary'] == BOUNDARY,
            'Closed exact startup review required')
    root = Path(q['journal']); intent = dashboard.read(root / 'intent.json')
    require(intent == {'kind': KIND, 'reviewHash': digest(q), 'request': q}, 'Original startup intent changed')
    names = {p.name for p in root.iterdir()}
    require(names <= {'intent.json', 'load.claim.json', 'loaded.json', 'stop.json', 'closed.json'}, 'Unlisted startup artifact')
    loaded = dashboard.read(root / 'loaded.json') if 'loaded.json' in names else None
    closed = dashboard.read(root / 'closed.json') if 'closed.json' in names else None
    if loaded:
        require(set(loaded) == {'kind', 'reviewHash', 'observedAt', 'throughAt', 'native', 'models', 'modelPageHashes',
                'ownerPid', 'processIdentity', 'maximumSeconds', 'boundary', 'executionReviewAvailable'} and
                loaded['kind'] == KIND and loaded['reviewHash'] == digest(q) and loaded['boundary'] == BOUNDARY and
                loaded['executionReviewAvailable'] is False and loaded['maximumSeconds'] == SECONDS and
                loaded['native']['activity'] == 'idle' and worker.policy_matches(loaded['native']['policy']) and
                loaded['native']['trackedTerminals'] == [] and worker.finite(loaded['observedAt']) and
                loaded['observedAt'] <= loaded['throughAt'] <= time.time(), 'Changed loaded-runtime saved report')
    if closed:
        require(set(closed) == {'kind', 'reviewHash', 'status', 'lastStage', 'loadAttempted', 'connectionClosed',
            'reconnectAllowed', 'terminalSafety', 'pilotAccepted'} and closed['kind'] == KIND and
            closed['reviewHash'] == digest(q) and closed['connectionClosed'] is True and
            closed['reconnectAllowed'] is False and closed['terminalSafety'] == 'unknown' and closed['pilotAccepted'] is False and
            closed['status'] in ('incomplete_unknown', 'owner_stopped', 'window_ended'), 'Changed original close record')
    return {'status': closed['status'] if closed else 'claimed_connection_unverified',
        'savedLoadedObservation': loaded is not None, 'observedAt': loaded['observedAt'] if loaded else None,
        'connectionCurrentlyVerified': False, 'executionReviewAvailable': False,
        'normalWritesBlocked': True, 'boundary': dict(BOUNDARY)}


def stop(q, confirmation):
    require(confirmation == digest(q), 'Exact original startup scope required for Stop')
    status(q); root = Path(q['journal'])
    require(not os.path.lexists(root / 'closed.json'), 'Original session already closed; never reload')
    exclusive(root / 'stop.json', {'kind': KIND, 'reviewHash': digest(q)})
    return {'status': 'stop_requested', 'nativeCancelSent': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    for n in ('repair', 'launched_source', 'observation', 'observation_source', 'catalog'): p.add_argument(n)
    for action in ('backup', 'start', 'status', 'stop'):
        p = sub.add_parser(action); p.add_argument('review')
        if action in ('backup', 'start'): p.add_argument('backup'); p.add_argument('--writers-stopped', action='store_true')
        if action in ('start', 'stop'): p.add_argument('--confirm-hash', required=True)
        if action == 'start': p.add_argument('--catalog', required=True)
    a = parser.parse_args()
    if a.action == 'prepare': value = prepare(a.repair, a.launched_source, a.observation, a.observation_source, a.catalog)
    else:
        q = dashboard.read(a.review)
        if a.action == 'backup': value = backup(q, a.backup, writers_stopped=a.writers_stopped)
        elif a.action == 'start': value = start(q, a.confirm_hash, a.backup, a.catalog, writers_stopped=a.writers_stopped)
        elif a.action == 'stop': value = stop(q, a.confirm_hash)
        else: value = status(q)
    print(canonical(value))


if __name__ == '__main__':
    try: main()
    except (Refusal, OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        print(canonical({'error': 'Loaded-runtime startup refused; preserve permanent claims, never retry', 'boundary': BOUNDARY}))
        raise SystemExit(2)
