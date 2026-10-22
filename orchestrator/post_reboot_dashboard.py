"""Explicit certificate-aware, read-only dashboard; never an identity override.

Only this separate operator consumes a completed maintenance certificate and
issued host repair. Normal Registry, Ledger, server and effect routes are intact.
"""
import argparse
import contextlib
import copy
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import time

from . import post_reboot_host_repair as repair
from . import native_auth_readiness as auth, native_policy_evidence as policy
from .app_server_wake import _read_binding, load_binding
from .core import Refusal, canonical, digest, require
from .host_lifecycle import sync_directory
from .native_read_client import inspect_endpoint, validate_endpoint
from .standard_quarantine import exclusive

KIND = 'post_reboot_dashboard_v1'
PR193 = '4680869d1b6eccf6cb92b58410f48b8712494f111d0f4459e3b12680a8d2ed1f'
BOUNDARY = {**repair.BOUNDARY, 'dashboardReadOnly': True, 'operationalControlsAvailable': False,
            'nativeMetadataCollectedOnPoll': False, 'historicalEvidenceRefreshed': False}
FIELDS = {'version', 'kind', 'sourceHash', 'repairFile', 'launchedSource', 'evidenceDirectory',
          'evidencePins', 'context', 'port', 'viewDirectory', 'journal', 'boundary'}
WEB_FILES = ('maintenance.html', 'maintenance.js', 'maintenance.css', 'style.css')


def asset(name):
    require(name in WEB_FILES, 'Closed recovery asset required')
    root = Path(__file__).resolve().parent.parent
    path = root / 'web' / name; before = repair.restart.safe_path(path)
    require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and before.st_nlink == 1 and
            not before.st_mode & 0o022 and before.st_size <= 512000, 'Bounded unchanged recovery asset required')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        raw = stream.read(512001)
        require(repair.restart.stamp(os.fstat(stream.fileno())) == repair.restart.stamp(before), 'Recovery asset changed')
    require(len(raw) == before.st_size and repair.restart.stamp(path.lstat()) == repair.restart.stamp(before), 'Recovery asset changed')
    return raw


def source_hash():
    return digest({'python': repair.maintenance.startup.owned.preplay.source_hash(),
                   'web': {n: hashlib.sha256(asset(n)).hexdigest() for n in WEB_FILES}})


def pin(path):
    return repair.maintenance.pin(path)


def read(path):
    return repair.maintenance.read(path)


def quiet(databases):
    for value in databases.values():
        r = repair.restart.fixed(['/usr/sbin/lsof', '-nP', '-t', value['path']])
        require(r.returncode == 1 and not r.stdout, 'Operational database handles remain open or unknown')


def history(spec):
    snapshot = repair.maintenance.decode(repair.restart.read_file(spec['homeSnapshotPin']['path'], 1_000_000)[0])
    require(repair.restart.pin(spec['homeSnapshotPin']['path'], 1_000_000) == spec['homeSnapshotPin'],
            'Original native-home snapshot changed')
    repair.restart.backup_check(spec, snapshot)
    home = Path(spec['launchSpec']['codexHome'])
    for name, record in snapshot['files'].items():
        if name == 'config.toml':
            require(repair.restart.read_file(home / name, 65536)[1] == record, 'Restricted configuration changed')
        elif name.startswith('sessions/') or name == 'installation_id':
            raw, _ = repair.restart.read_file(home / name)
            require(len(raw) >= record['bytes'] and hashlib.sha256(raw[:record['bytes']]).hexdigest() == record['sha256'],
                    'Original history prefix or installation identity changed')
    # Credentials are metadata-only, never opened, hashed or copied.
    credential = snapshot['credentialMetadata']
    require(credential['bytesRead'] is False and credential['copied'] is False and
            list(repair.restart.stamp(repair.restart.safe_path(home / 'auth.json'))) == credential['identity'],
            'Credential metadata changed; no sign-in or refresh is included')


def foundation(repair_file, launched_source):
    """Full current certificate/old-record checks, no native connection or write."""
    s = repair.load(repair_file)
    proof = repair.maintenance.startup.prior.source_proof(launched_source)
    require(proof['sourceHash'] == s['sourceHash'] and s['sourceHash'] in
            (PR193, repair.maintenance.startup.owned.preplay.source_hash()), 'Qualified original launch source bytes required')
    q, registry, ledger, original, previous, pins, package, scope = repair.inputs(s['certificateFile'], s['previousAttempt'])
    require((s['launchSpec'], s['previousStatus'], s['previousPins'], s['runtimePin'], s['scope']) ==
            (original, previous, pins, package, scope) and s['certificatePin'] == pin(s['certificateFile']) and
            s['journal'] == str(repair.owner(q, registry, ledger)), 'Original completed repair scope changed')
    root = Path(s['journal']); state = repair.status(repair_file)
    require(state['status'] == 'exec_boundary_issued' and
            {p.name for p in root.iterdir()} == {'intent.json', 'exec.claim', 'status.json'} and
            read(root / 'intent.json') == {'kind': repair.KIND, 'specHash': digest(s), 'reviewHash': repair.review_hash(s)} and
            pin(root / 'exec.claim')['epoch'][5] == 0, 'Complete issued canonical host repair required; no retry')
    repair.restart.live_process(s, state)
    for _ in range(2):
        require(repair.restart.process_absent(previous['pid']), 'Original PID must remain absent; never signal it')
    require(repair.launch.directory_identity(s['socketDirectory']) == s['socketDirectoryIdentity'],
            'Originally reviewed socket directory identity changed')
    alias = Path(s['socketDirectory']) / 'host.sock'
    physical = repair.socket_path(original, s['socketDirectory'])
    require(alias.is_symlink() and alias.lstat().st_uid == os.getuid() and
            alias.resolve(strict=True) == physical, 'Exact issued advertised/physical socket relationship required')
    handles = repair.restart.fixed(['/usr/sbin/lsof', '-nP', '-a', '-p', str(state['pid']), '-U', '-Fn'])
    require(handles.returncode == 0 and 'n' + str(physical) in handles.stdout.decode().splitlines(),
            'Exact issued process must own the new socket')
    witness = read(Path(q['witness']) / 'report.json')['context']
    old_file = witness['bindingFile']; old = _read_binding(old_file); brain = q['context']['brainId']
    require(set(old['brains']) == {brain} and old['brains'][brain]['workspaceId'] == q['workspaceId'] and
            old['brains'][brain]['cwd'] == original['cwd'] and digest(old) == q['context']['bindingHash'],
            'Exact original single-brain binding required')
    endpoint = inspect_endpoint(old['endpoint']['executable'], str(physical), old['endpoint']['serverIdentityHash'])
    require(endpoint['socket'] != old['endpoint']['socket'] and endpoint['socketIdentity'] != old['endpoint']['socketIdentity'] and
            endpoint['sha256'] == package['executableHash'], 'Only the actual new private socket may be used')
    history(s)
    context = {'workspaceId': q['workspaceId'], 'brainId': brain, 'checkout': original['cwd'], 'nativeHome': original['codexHome'],
        'startupHash': q['context']['startupReviewHash'], 'bootSessionUuid': q['context']['bootSessionUuid'],
        'repairPin': pin(repair_file), 'certificatePin': pin(s['certificateFile']), 'certificatePins': scope['certificatePins'],
        'launchedSource': proof, 'launchPins': {n: pin(root / n) for n in ('intent.json', 'exec.claim', 'status.json')},
        'oldBindingFile': old_file, 'oldBindingPin': pin(old_file), 'oldBindingHash': digest(old),
        'databases': q['context']['databases'], 'historicalPins': q['context']['files'],
        'originalUsage': q['context']['originalUsage'], 'originalReadinessId': q['context']['originalReadinessCommand'],
        'historicalObservedAt': q['context']['historicalObservedAt'], 'latestTurnId': witness['nativeTurnId'],
        'pid': state['pid'], 'processIdentity': state['processIdentity'], 'endpoint': endpoint,
        'record': old['brains'][brain]}
    return context, q, registry, ledger


def owner(context, registry):
    return registry.root / 'post-reboot-dashboards' / digest({'workspace': context['workspaceId'],
        'inode': Path(context['databases']['workspace:' + context['workspaceId']]['path']).stat().st_ino,
        'startup': context['startupHash']})


def catalog(path, context, *, fresh=False):
    value = read(path)
    require(set(value) == {'source', 'observedAt', 'completeResult'} and value['source'] == 'codex_app.list_projects' and
            type(value['observedAt']) in (int, float) and 0 < value['observedAt'] <= time.time() and
            value['completeResult'].get('schemaVersion') == 2 and isinstance(value['completeResult'].get('projects'), list),
            'Actual complete native app catalog observation required')
    if fresh: require(0 <= time.time() - value['observedAt'] <= 120, 'Fresh actual catalog required before dashboard start')
    rows = [p for p in value['completeResult']['projects'] if p.get('path') == context['checkout']]
    require(len(rows) == 1 and rows[0].get('projectId') == context['record']['catalogProjectId'] and
            rows[0].get('hostId') == 'local' and rows[0].get('projectKind') == 'local' and
            rows[0].get('isGitRepository') is True, 'Unique exact app catalog identity/root required')
    return pin(path)


def collect(context):
    """Only explicit inspection/start calls this; the HTTP server never does."""
    record = context['record']; samples = []
    with repair.restart.RestartReadProxy(context['endpoint'], context['brainId'], record['projectId']) as proxy:
        for _ in range(2):
            project = proxy._rpc('project/read', {'projectId': record['projectId']})['project']
            thread = proxy._rpc('thread/read', {'threadId': context['brainId'], 'includeTurns': False})['thread']
            require(project['id'] == record['projectId'] and project['roots'] == [{'path': context['checkout']}] and
                    thread['id'] == context['brainId'] and thread['projectId'] == record['projectId'] and
                    thread['cwd'] == context['checkout'] and thread['status']['type'] in {'notLoaded', 'idle'},
                    'Exact non-active project/brain required; never load')
            turns = proxy._rpc('thread/turns/list', {'threadId': context['brainId'], 'cursor': None, 'limit': 1,
                'sortDirection': 'desc', 'itemsView': 'notLoaded'}).get('data')
            require(isinstance(turns, list) and len(turns) == 1 and turns[0]['id'] == context['latestTurnId'] and
                    turns[0]['status'] == 'completed', 'Original latest completed preparation turn changed')
            require(proxy._rpc('mcpServerStatus/list', {'detail': 'toolsAndAuthOnly'}) == {'data': [], 'nextCursor': None},
                    'Complete empty MCP inventory required')
            reported = policy.reported(proxy._rpc('thread/effectivePolicy/read', {'threadId': context['brainId']}),
                                       context['brainId'], context['checkout'])
            activity = thread['status']['type']
            require(activity != 'notLoaded' or reported is None, 'Unloaded policy remains unknown')
            samples.append({'activity': activity, 'latestTurnId': context['latestTurnId'], 'policy': reported})
            if len(samples) == 1: authentication = auth.inspect(proxy)
        require(samples[0] == samples[1], 'Native metadata changed during inspection')
    return {'observation': samples[0], 'authentication': authentication, 'observedAt': time.time(),
            'modelAccessVerified': False, 'terminalSafety': 'unknown'}


def disjoint(path, context, *, new=True):
    path = Path(path); repair.launch.isolated_directory(path.parent)
    protected = [Path(v['path']).parent for v in context['databases'].values()]
    protected += [Path(context['checkout']), Path(context['nativeHome']), Path(context['endpoint']['executable']).parent.parent,
                  Path(context['launchedSource']['root']), Path(context['repairPin']['path']).parent]
    require(path.is_absolute() and path.resolve() == path and (not new or not os.path.lexists(path)) and
            all(not path.is_relative_to(p) and not p.is_relative_to(path) for p in protected),
            'New disjoint private output required')
    return path


def inspect(repair_file, launched_source, catalog_file, directory):
    c, _, _, _ = foundation(repair_file, launched_source); catalog_pin = catalog(catalog_file, c, fresh=True)
    root = disjoint(directory, c); root.mkdir(mode=0o700)
    exclusive(root / 'intent.json', {'kind': KIND, 'context': c, 'catalogPin': catalog_pin})
    observed = collect(c)
    require(foundation(repair_file, launched_source)[0] == c and pin(catalog_file) == catalog_pin,
            'Scope changed during explicit native inspection')
    candidate = {'endpoint': c['endpoint'], 'brains': {c['brainId']: copy.deepcopy(c['record'])}}
    exclusive(root / 'binding.json', candidate); require(load_binding(root / 'binding.json') == candidate, 'Candidate validation failed')
    exclusive(root / 'result.json', {'kind': KIND, 'contextHash': digest(c), 'observed': observed,
        'bindingHash': digest(candidate), 'boundary': BOUNDARY})
    sync_directory(root)
    return {'status': 'connected_read_only', 'directory': str(root), 'activity': observed['observation']['activity'],
            'loadedPolicyVerified': policy.matches(observed['observation']['policy']), 'boundary': BOUNDARY}


def prepare(repair_file, launched_source, evidence_directory, view_directory, port):
    c, _, registry, _ = foundation(repair_file, launched_source)
    require(type(port) is int and 1024 <= port <= 65535, 'Explicit unprivileged loopback port required')
    root = repair.launch.isolated_directory(evidence_directory)
    require({p.name for p in root.iterdir()} == {'intent.json', 'binding.json', 'result.json'}, 'Closed complete native evidence required')
    intent, result = read(root / 'intent.json'), read(root / 'result.json')
    candidate = load_binding(root / 'binding.json')
    require(intent == {'kind': KIND, 'context': c, 'catalogPin': intent['catalogPin']} and
            pin(intent['catalogPin']['path']) == intent['catalogPin'] and result['kind'] == KIND and
            result['contextHash'] == digest(c) and result['boundary'] == BOUNDARY and
            candidate == {'endpoint': c['endpoint'], 'brains': {c['brainId']: c['record']}} and
            result['bindingHash'] == digest(candidate), 'Exact independently retained candidate/evidence required')
    require(not os.path.lexists(owner(c, registry)), 'Dashboard attempt consumed or partial; never start again')
    view = disjoint(view_directory, c)
    require(not view.is_relative_to(root) and not root.is_relative_to(view), 'Evidence and browser view must be disjoint')
    q = {'version': 1, 'kind': KIND, 'sourceHash': source_hash(), 'repairFile': str(repair_file),
        'launchedSource': str(launched_source), 'evidenceDirectory': str(root),
        'evidencePins': {n: pin(root / n) for n in ('intent.json', 'binding.json', 'result.json')},
        'context': c, 'port': port, 'viewDirectory': str(view),
        'journal': str(owner(c, registry)), 'boundary': BOUNDARY}
    require(len(canonical(q).encode()) <= 64000, 'Bounded exact dashboard review required')
    return {'request': q, 'reviewHash': digest(q), 'validUntil': 'scope_changes',
            'effect': 'Start one loopback read-only recovery dashboard; no operational binding change or native effect'}


def validate(q):
    require(isinstance(q, dict) and set(q) == FIELDS and type(q['version']) is int and q['version'] == 1 and
            q['kind'] == KIND and q['sourceHash'] == source_hash() and q['boundary'] == BOUNDARY,
            'Exact current dashboard review required')
    proposed = prepare(q['repairFile'], q['launchedSource'], q['evidenceDirectory'], q['viewDirectory'], q['port'])
    require(proposed['request'] == q, 'Reviewed dashboard scope changed')
    return q


def backup(q, destination, *, writers_stopped=False):
    require(writers_stopped is True, 'Stop older database writers before backup')
    validate(q); c = q['context']; quiet(c['databases']); root = disjoint(destination, c)
    require(not root.is_relative_to(Path(q['evidenceDirectory'])) and not Path(q['viewDirectory']).is_relative_to(root) and
            not root.is_relative_to(Path(q['viewDirectory'])), 'Backup must be disjoint from evidence/view')
    root.mkdir(mode=0o700); files = {}
    for i, (key, value) in enumerate(sorted(c['databases'].items())):
        dest = root / ('database-' + str(i) + '.sqlite3')
        os.close(os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
        with repair.maintenance.startup.standard.read_db(value['path']) as src, contextlib.closing(sqlite3.connect(dest)) as dst:
            src.backup(dst); require(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Backup integrity failed')
            dst.execute('PRAGMA journal_mode=DELETE')
        require(repair.maintenance.partial.database_proof(dest)['fingerprint'] == value['fingerprint'], 'Database backup differs')
        with dest.open('rb') as f: os.fsync(f.fileno())
        files[dest.name] = {'key': key, 'pin': repair.restart.pin(dest, repair.restart.MAX_FILE), 'fingerprint': value['fingerprint']}
    originals = backup_inputs(q)
    for i, path in enumerate(sorted(originals)):
        expected = originals[path]; require(pin(path) == expected, 'Original private input changed')
        dest = root / ('input-' + str(i) + '.json')
        with os.fdopen(os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as f:
            f.write(Path(path).read_bytes()); f.flush(); os.fsync(f.fileno())
        require(pin(path) == expected and pin(dest)['sha256'] == expected['sha256'], 'Private backup differs')
        files[dest.name] = {'original': expected, 'pin': pin(dest)}
    exclusive(root / 'manifest.json', {'kind': KIND, 'reviewHash': digest(q), 'files': files})
    sync_directory(root); validate(q); verify_backup(q, root)
    return {'backup': str(root), 'verified': True, 'reviewHash': digest(q)}


def backup_inputs(q):
    c = q['context']
    rows = [*c['historicalPins'].values(), *c['certificatePins'].values(),
            *c['launchPins'].values(), *q['evidencePins'].values(),
            c['repairPin'], c['certificatePin'], c['oldBindingPin']]
    values = {r['path']: r for r in rows}
    require(len(values) <= 96 and all(pin(p) == r for p, r in values.items()), 'Complete bounded immutable input inventory required')
    return values


def verify_backup(q, directory):
    root = repair.launch.isolated_directory(directory); m = read(root / 'manifest.json')
    require(set(m) == {'kind', 'reviewHash', 'files'} and m['kind'] == KIND and m['reviewHash'] == digest(q) and
            {p.name for p in root.iterdir()} == set(m['files']) | {'manifest.json'}, 'Complete exact private backup required')
    dbs = q['context']['databases']; found = []; inputs = backup_inputs(q); copied = []
    expected_names = {'database-' + str(i) + '.sqlite3' for i in range(len(dbs))} | {
        'input-' + str(i) + '.json' for i in range(len(inputs))}
    require(set(m['files']) == expected_names, 'No backup input may be omitted or substituted')
    for name, row in m['files'].items():
        if 'key' in row:
            require(set(row) == {'key', 'pin', 'fingerprint'} and
                    repair.restart.pin(root / name, repair.restart.MAX_FILE) == row['pin'], 'Retained database backup changed')
            expected = dbs[row['key']]; found.append(row['key'])
            require(row['fingerprint'] == expected['fingerprint'] ==
                repair.maintenance.partial.database_proof(root / name)['fingerprint'], 'Database backup content differs')
        else:
            path = row['original']['path']; copied.append(path)
            require(set(row) == {'original', 'pin'} and row['original'] == inputs[path] and
                    pin(root / name) == row['pin'] and pin(path) == row['original'] and
                    row['pin']['sha256'] == row['original']['sha256'], 'Original private input differs')
    require(sorted(found) == sorted(dbs) and sorted(copied) == sorted(inputs), 'All databases and private inputs must be backed up')


def serve(q, confirmation, backup_root, catalog_file, *, writers_stopped=False):
    require(writers_stopped is True and confirmation == digest(q), 'Exact new dashboard-only approval and stopped writers required')
    validate(q); quiet(q['context']['databases']); verify_backup(q, backup_root); catalog(catalog_file, q['context'], fresh=True)
    r = repair.restart.fixed(['/usr/sbin/lsof', '-nP', '-iTCP:' + str(q['port']), '-sTCP:LISTEN'])
    require(r.returncode == 1 and not r.stdout, 'Reviewed dashboard port is occupied or unknown; never stop its owner')
    root = Path(q['journal']); root.parent.mkdir(mode=0o700, exist_ok=True); repair.launch.isolated_directory(root.parent)
    root.mkdir(mode=0o700); sync_directory(root.parent)  # Permanent across IDs/source/port/view directories.
    exclusive(root / 'intent.json', {'kind': KIND, 'reviewHash': digest(q), 'request': q})
    exclusive(root / 'serve.claim.json', {'reviewHash': digest(q), 'pid': os.getpid()})
    # No call to validate/prepare after claiming: their unconsumed gate is deliberate.
    require(foundation(q['repairFile'], q['launchedSource'])[0] == q['context'], 'Scope changed after permanent claim')
    verify_backup(q, backup_root); quiet(q['context']['databases']); catalog(catalog_file, q['context'], fresh=True)
    observed = collect(q['context'])  # One explicit startup inspection; never a poll/reconnect owner.
    earlier = read(Path(q['evidenceDirectory']) / 'result.json')['observed']
    require(observed['observation'] == earlier['observation'] and
            observed['authentication']['responseHash'] == earlier['authentication']['responseHash'],
            'Reviewed native activity, policy or account/routing changed')
    require(foundation(q['repairFile'], q['launchedSource'])[0] == q['context'], 'Scope changed during startup inspection')
    quiet(q['context']['databases']); verify_backup(q, backup_root); catalog(catalog_file, q['context'], fresh=True)
    view = disjoint(q['viewDirectory'], q['context']); view.mkdir(mode=0o700)
    from .maintenance_dashboard import RecoveryDashboard
    server = RecoveryDashboard(q, observed, view)
    try:
        exclusive(root / 'serving.json', {'kind': KIND, 'reviewHash': digest(q), 'pid': os.getpid(),
            'processIdentity': repair.restart.process_identity(os.getpid()), 'port': server.server_port,
            'observed': observed, 'boundary': BOUNDARY})
        print(canonical({'status': 'read_only_dashboard_serving', 'privateSessionFile': str(view / 'dashboard-session.json')}), flush=True)
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('inspect')
    for n in ('repair_file', 'launched_source', 'catalog', 'directory'): a.add_argument(n)
    a = sub.add_parser('prepare')
    for n in ('repair_file', 'launched_source', 'evidence', 'view_directory'): a.add_argument(n)
    a.add_argument('--port', type=int, required=True)
    for action in ('backup', 'serve'):
        a = sub.add_parser(action); a.add_argument('review'); a.add_argument('backup'); a.add_argument('--writers-stopped', action='store_true')
        if action == 'serve': a.add_argument('--confirm-hash', required=True); a.add_argument('--catalog', required=True)
    a = p.parse_args()
    if a.action == 'inspect': value = inspect(a.repair_file, a.launched_source, a.catalog, a.directory)
    elif a.action == 'prepare': value = prepare(a.repair_file, a.launched_source, a.evidence, a.view_directory, a.port)
    elif a.action == 'backup': value = backup(read(a.review), a.backup, writers_stopped=a.writers_stopped)
    else: serve(read(a.review), a.confirm_hash, a.backup, a.catalog, writers_stopped=a.writers_stopped); return
    print(canonical(value))


if __name__ == '__main__':
    try: main()
    except (Refusal, OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        print(canonical({'error': 'Read-only dashboard refused; inspect private records, never retry a consumed startup', 'boundary': BOUNDARY}))
        raise SystemExit(2)
