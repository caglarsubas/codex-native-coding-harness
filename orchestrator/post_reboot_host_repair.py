"""Separate exact launch-only repair after a completed maintenance certificate.

No ordinary identity override, native client, load, binding installation or turn.
Historical device translation is closed to the original launch/package proof;
all proposed execution pins use their real current epochs.
"""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import pwd
import sqlite3
import sys
import time

from . import post_reboot_maintenance as maintenance, public_host_restart as restart
from . import public_host_lifecycle as launch, public_host_runtime as runtime
from . import public_preplay_host_restart as preplay
from .core import Refusal, canonical, digest, require
from .app_server_wake import NATIVE_APPROVAL_POLICY
from .host_lifecycle import sync_directory, write_record
from .host_runtime import file_record, safe_path, stamp
from .standard_quarantine import exclusive

KIND = 'post_reboot_host_repair_v1'
PR192 = 'ebb448e5f0523f03e361a85477c651fe21836b37bba9257add3cb07bf050e0a7'
PROTECTED_SOCKET_BUILD = ('cd935163b03fbbe3d26a464be5c199a31011b120', '26323f8f8aea3827361be30d75826551c61277e8')
FIELDS = {'version', 'kind', 'sourceHash', 'certificateFile', 'certificatePin', 'scope',
          'previousAttempt', 'launchSpec', 'previousStatus', 'previousPins', 'runtimePin',
          'homeSnapshotPin', 'backupPath', 'socketDirectory', 'socketDirectoryIdentity',
          'reviewDirectory', 'journal', 'boundary'}
BOUNDARY = {**preplay.BOUNDARY, 'ledgerWritten': False, 'registryWritten': False,
            'ordinaryRoutesUnfenced': False, 'subscriptionMade': False,
            'playAuthorized': False, 'recoveryAuthorized': False}


def certificate(path):
    """Revalidate only the completed allowlisted certificate, never old code.

    The original maintenance.current() remains strict and unchanged. This is a
    separately named consumer, not permission for normal reads/writes to adopt
    a historical database or binding identity.
    """
    q = maintenance.read(path)
    require(set(q) == maintenance.FIELDS and type(q['version']) is int and q['version'] == 2 and
            q['kind'] == maintenance.KIND and q['boundary'] == maintenance.BOUNDARY and
            q['sourceHash'] in (PR192, maintenance.startup.owned.preplay.source_hash()),
            'Exact qualified version-2 maintenance certificate required')
    c = q['context']
    require(c == maintenance.context(q['platform'], q['workspaceId'], q['witness'], reviewed_boot={
                k: c[k] for k in ('bootSessionUuid', 'bootedAt')}), 'Maintenance context changed')
    registry, ledger, _ = maintenance.route(q['platform'], q['workspaceId'])
    root = maintenance.location(registry, ledger, c['startupReviewHash'])
    require(q['journal'] == str(root) and {p.name for p in root.iterdir()} == {'intent.json', 'result.json'} and
            maintenance.read(root / 'intent.json') == {'kind': maintenance.KIND, 'reviewHash': digest(q), 'request': q} and
            maintenance.read(ledger.root / maintenance.FENCE) == {
                'kind': maintenance.KIND, 'reviewHash': digest(q), 'journal': str(root)},
            'Complete canonical maintenance intent and fence required; no partial successor')
    result = maintenance.read(root / 'result.json')
    require(set(result) == {'kind', 'reviewHash', 'status', 'backup', 'boundary'} and
            result == {'kind': maintenance.KIND, 'reviewHash': digest(q), 'status': 'maintenance_epoch_retained',
                       'backup': result['backup'], 'boundary': maintenance.BOUNDARY},
            'Exact completed maintenance result required')
    maintenance.verify_backup(q, result['backup'])
    pins = {str(p): maintenance.pin(p) for p in (Path(path), root / 'intent.json', root / 'result.json',
                                               ledger.root / maintenance.FENCE, Path(result['backup']) / 'manifest.json')}
    return q, registry, ledger, pins


def package_continuity(original, c):
    """Reconstruct only this three-file historical inventory; never live pins."""
    actual = runtime.inspect_package(original['root'])
    root = Path(original['root']); rows = []
    for name in runtime.FILES:
        row = file_record(root, name, runtime.MAX_BYTES)
        require(row['device'] == c['currentDevice'] and row['changedNs'] / 1e9 <= c['bootedAt'],
                'Original native package must predate the reviewed reboot')
        rows.append({**row, 'device': c['oldDevice']})
    directories = []
    for path in (root, root / 'bin'):
        s = stamp(safe_path(path, directory=True))
        require(s[0] == c['currentDevice'] and s[8] / 1e9 <= c['bootedAt'],
                'Original package directory epoch changed beyond device')
        directories.append((c['oldDevice'], *s[1:]))
    historical = {**actual, 'inventoryHash': digest({'files': rows, 'root': directories[0], 'bin': directories[1]})}
    require(historical == original and runtime.inspect_package(original['root']) == actual,
            'Original package differs beyond the reviewed device component')
    return actual


def original_attempt(path, q, ledger):
    """Read the initial issued epoch only. No restart chain or old RPC target."""
    path = launch.isolated_directory(path); c = q['context']
    pins = [maintenance.pin(path / name) for name in ('launch.json', 'status.json', 'exec.claim')]
    require(all(p['epoch'][7] / 1e9 <= c['bootedAt'] for p in pins), 'Original launch records must predate reboot')
    record = maintenance.read(path / 'launch.json'); spec = record['spec']
    require(set(record) == {'spec', 'manifestHash', 'reviewHash', 'mode', 'createdAt'} and
            record['mode'] == 'exec' and record['manifestHash'] == digest(spec) and
            record['reviewHash'] == launch.review_hash(spec) and set(spec) == launch.FIELDS and
            type(spec['schemaVersion']) is int and spec['schemaVersion'] == 1 and
            spec['profile'] == runtime.PROFILE and spec['nativePolicy'] == launch.POLICY and
            type(spec['nativePolicy'].get('codeMode')) is bool and spec['credentialMode'] == 'unconfigured' and
            pins[2]['epoch'][5] == 0, 'Exact originally issued public launch and empty exec claim required')
    state = launch.status(path)
    require(state['status'] == 'exec_boundary_issued' and state['observedAt'] <= c['bootedAt'],
            'Only the issued original process epoch qualifies; failed/unknown attempts stay consumed')
    require(spec['cwd'] == c['checkout'] and spec['codexHome'] != str(Path(pwd.getpwuid(os.getuid()).pw_dir) / '.codex') and
            not Path(spec['codexHome']).is_relative_to(Path('/private/var/tmp')),
            'Exact original checkout and isolated native home required')
    for key, identity_key in (('cwd', 'cwdIdentity'), ('codexHome', 'homeIdentity')):
        actual = launch.directory_identity(spec[key]); expected = spec[identity_key]
        require(actual['device'] == c['currentDevice'] and expected['device'] == c['oldDevice'] and
                {**actual, 'device': c['oldDevice']} == expected, 'Original home/checkout inode or permissions changed')
    roots = [Path(spec[k]) for k in ('cwd', 'codexHome')] + [Path(spec['runtimePackage']['root'])]
    require(len(set(roots)) == 3 and all(not a.is_relative_to(b) for a in roots for b in roots if a != b) and
            (roots[0] / '.git').is_dir() and not (roots[0] / '.git').is_symlink(), 'Original isolated boundaries required')
    for extra in (roots[0] / 'config.toml', roots[0] / '.codex/config.toml', Path('/etc/codex/config.toml'),
                  Path('/etc/codex/requirements.toml'), Path('/etc/codex/managed_config.toml'),
                  Path('/Library/Preferences/com.openai.codex.plist')):
        require(not os.path.lexists(extra), 'Additional configuration requires a separate qualified profile')
    config = restart.restricted_config(spec['codexHome'], spec['cwd'])
    require(config['identity'][8] / 1e9 <= c['bootedAt'], 'Native configuration must predate reboot')
    witness = maintenance.read(Path(q['witness']) / 'report.json')['context']
    binding = maintenance.read(witness['bindingFile']); endpoint = binding['endpoint']; brain = binding['brains'][c['brainId']]
    require(digest(binding) == c['bindingHash'] and brain['cwd'] == spec['cwd'] and
            brain['workspaceId'] == ledger.workspace_id and brain['nativePolicy'] in (launch.POLICY, NATIVE_APPROVAL_POLICY) and
            endpoint['socket'] == str(socket_path(spec, spec['socketDirectory'])) and
            endpoint['executable'] == str(Path(spec['runtimePackage']['root']) / 'bin/codex') and
            endpoint['sha256'] == spec['runtimePackage']['executableHash'], 'Exact original binding/launch relationship required')
    from .public_native_tasks import validate_contract
    native = validate_contract(brain['nativeTaskBackend'], brain['policyEvidence'])
    require(all(native[k] == spec['runtimePackage'][k] for k in ('sourceCommit', 'sourceTree')),
            'Native task/policy build differs from the original launch')
    actual = package_continuity(spec['runtimePackage'], c)
    require(maintenance.pin(path / 'launch.json') == pins[0] and maintenance.pin(path / 'status.json') == pins[1],
            'Original launch records changed during inspection')
    return spec, state, pins, actual


def socket_path(spec, directory):
    """Derive a pathname only, never a future socket epoch or native identity.

    This exact reviewed build hashes the advertised canonical pathname into the
    sandbox-protected rendezvous root. Do not accept an alias as an endpoint or
    silently change the mapping for another native source/build.
    """
    advertised = Path(directory) / 'host.sock'
    native = spec['runtimePackage']
    if (native['sourceCommit'], native['sourceTree']) == PROTECTED_SOCKET_BUILD:
        require(advertised.parent.resolve() == advertised.parent, 'Canonical advertised socket parent required')
        return Path('/private/tmp' if sys.platform == 'darwin' else '/tmp') / ('codex-daemon-' + str(os.getuid())) / \
               hashlib.sha256(os.fsencode(str(advertised))).hexdigest()
    return advertised


def owner(q, registry, ledger):
    # Permanent across source versions, devices, new endpoints and review IDs.
    return registry.root / 'post-reboot-host-repairs' / digest({
        'workspace': q['workspaceId'], 'inode': ledger.db.stat().st_ino,
        'startup': q['context']['startupReviewHash']})


def inputs(certificate_file, previous):
    q, registry, ledger, pins = certificate(certificate_file)
    spec, state, originals, package = original_attempt(previous, q, ledger)
    scope = {'maintenanceHash': digest(q), 'certificatePins': pins, 'contextHash': digest(q['context']),
             'sidecars': preplay.sidecars(ledger),
             'databases': {k: restart.pin(v['path'], restart.MAX_FILE) for k, v in q['context']['databases'].items()}}
    return q, registry, ledger, spec, state, originals, package, scope


def quiet(q, spec, state):
    for _ in range(2): restart.quiescent(spec, state)
    for value in q['context']['databases'].values():
        r = restart.fixed(['/usr/sbin/lsof', '-nP', '-t', value['path']])
        require(r.returncode == 1 and not r.stdout, 'All operational database writers must be stopped')


def paths(s, q):
    directory = Path(s['reviewDirectory']); sockets = launch.isolated_directory(s['socketDirectory'])
    launch.isolated_directory(directory.parent)
    protected = [Path(q['platform']), Path(q['context']['root']), Path(q['witness']), Path(s['previousAttempt']),
                 *[Path(s['launchSpec'][k]) for k in ('cwd', 'codexHome', 'socketDirectory')],
                 Path(s['runtimePin']['root']), *[Path(v['root']) for v in q['context']['sourceEpochs']]]
    require(directory.is_absolute() and directory.resolve() == directory and
            len(os.fsencode(str(sockets / 'host.sock'))) <= 100 and
            all(not a.is_relative_to(b) and not b.is_relative_to(a) for a in (directory, sockets) for b in protected) and
            not directory.is_relative_to(sockets) and not sockets.is_relative_to(directory) and
            s['backupPath'] == str(directory / 'native-home-backup') and
            s['homeSnapshotPin']['path'] == str(directory / 'home-snapshot.json'), 'Private disjoint closed repair paths required')
    old = socket_path(s['launchSpec'], s['launchSpec']['socketDirectory'])
    new = socket_path(s['launchSpec'], sockets)
    require(new != old and not os.path.lexists(new) and not os.path.lexists(new.with_suffix('.lock')) and
            not os.path.lexists(Path(s['launchSpec']['socketDirectory']) / 'host.sock'),
            'New physical socket/lock and retired alias must be absent; never unlink or adopt')
    if new.parent != sockets and os.path.lexists(new.parent): launch.isolated_directory(new.parent)


def prepare(certificate_file, previous, sockets, directory):
    values = inputs(certificate_file, previous)
    q, registry, ledger, spec, state, pins, package, scope = values
    journal = owner(q, registry, ledger)
    require(not os.path.lexists(journal), 'Host repair already consumed or partial; never retry')
    sockets = launch.isolated_directory(sockets); directory = Path(directory)
    require(not list(sockets.iterdir()) and not os.path.lexists(directory), 'New empty socket/review directories required')
    s = {'version': 1, 'kind': KIND, 'sourceHash': maintenance.startup.owned.preplay.source_hash(),
         'certificateFile': str(certificate_file), 'certificatePin': maintenance.pin(certificate_file),
         'scope': scope, 'previousAttempt': str(previous), 'launchSpec': spec, 'previousStatus': state,
         'previousPins': pins, 'runtimePin': package, 'homeSnapshotPin': {'path': str(directory / 'home-snapshot.json')},
         'backupPath': str(directory / 'native-home-backup'), 'socketDirectory': str(sockets),
         'socketDirectoryIdentity': launch.directory_identity(sockets), 'reviewDirectory': str(directory),
         'journal': str(journal), 'boundary': dict(BOUNDARY)}
    paths(s, q); quiet(q, spec, state)
    binary = str(Path(package['root']) / 'bin/codex')
    snapshot = restart.signed_in_preplay_snapshot(spec['codexHome'], binary, brain=q['context']['brainId'])
    directory.mkdir(mode=0o700); sync_directory(directory.parent)
    backup = directory / 'native-home-backup'; backup.mkdir(mode=0o700)
    require(snapshot == restart.signed_in_preplay_snapshot(spec['codexHome'], binary, backup, brain=q['context']['brainId']),
            'Native home changed while backing up; preserve partial preparation')
    write_record(directory / 'home-snapshot.json', snapshot)
    s['homeSnapshotPin'] = restart.pin(directory / 'home-snapshot.json', 1_000_000)
    restart.backup_check(s, snapshot)
    require(values == inputs(certificate_file, previous), 'Scope changed while preparing the new host review')
    require(len(canonical(s).encode()) <= 64000, 'Bounded complete host repair review required')
    write_record(directory / 'repair.json', s)
    return preview(directory / 'repair.json')


def load(path):
    s = maintenance.read(path)
    require(set(s) == FIELDS and type(s['version']) is int and s['version'] == 1 and s['kind'] == KIND and
            s['boundary'] == BOUNDARY and Path(path) == Path(s['reviewDirectory']) / 'repair.json', 'Closed repair review required')
    return s


def review_hash(s):
    return digest({'kind': KIND, 'mode': 'launch_only_exec', 'specHash': digest(s)})


def validate(path, *, claimed=False):
    s = load(path)
    require(s['sourceHash'] == maintenance.startup.owned.preplay.source_hash() and
            maintenance.pin(s['certificateFile']) == s['certificatePin'], 'Repair source or certificate changed')
    q, registry, ledger, spec, state, pins, package, scope = inputs(s['certificateFile'], s['previousAttempt'])
    require((s['launchSpec'], s['previousStatus'], s['previousPins'], s['runtimePin'], s['scope']) ==
            (spec, state, pins, package, scope) and s['journal'] == str(owner(q, registry, ledger)), 'Reviewed repair context changed')
    paths(s, q); journal = Path(s['journal'])
    if claimed:
        require(maintenance.read(journal / 'intent.json') == {'kind': KIND, 'specHash': digest(s), 'reviewHash': review_hash(s)} and
                maintenance.pin(journal / 'exec.claim')['epoch'][5] == 0 and
                {p.name for p in journal.iterdir()} == {'intent.json', 'exec.claim'}, 'Canonical claimed repair differs')
    else: require(not os.path.lexists(journal), 'Host repair consumed or partial; inspection only')
    sockets = launch.isolated_directory(s['socketDirectory'])
    require(launch.directory_identity(sockets) == s['socketDirectoryIdentity'] and not list(sockets.iterdir()),
            'New socket directory changed; never use the old endpoint')
    require(restart.pin(s['homeSnapshotPin']['path'], 1_000_000) == s['homeSnapshotPin'], 'Native snapshot changed')
    snapshot = maintenance.decode(restart.read_file(s['homeSnapshotPin']['path'], 1_000_000)[0])
    quiet(q, spec, state)
    require(restart.signed_in_preplay_snapshot(spec['codexHome'], str(Path(package['root']) / 'bin/codex'),
                brain=q['context']['brainId']) == snapshot, 'Native home or credential metadata changed')
    restart.backup_check(s, snapshot)
    return s


def preview(path):
    s = validate(path)
    return {'kind': KIND, 'reviewHash': review_hash(s), 'validUntil': 'scope_changes',
            'workspaceId': maintenance.read(s['certificateFile'])['workspaceId'], 'startsHost': False,
            'effect': 'One launch-only foreground exec on a new socket; no load, binding change or turn',
            'boundary': dict(BOUNDARY)}


def exec_host(path, confirmation, *, writers_stopped=False):
    require(writers_stopped is True, 'Stop older writers before launch')
    s = validate(path)
    require(sys.platform == 'darwin' and platform.machine() == 'arm64' and confirmation == review_hash(s),
            'Exact new macOS ARM64 launch-only review required; old approvals grant no launch')
    root = Path(s['journal']); root.parent.mkdir(mode=0o700, exist_ok=True); launch.isolated_directory(root.parent)
    root.mkdir(mode=0o700); sync_directory(root.parent)  # Canonical permanent owner, including partial writes.
    exclusive(root / 'intent.json', {'kind': KIND, 'specHash': digest(s), 'reviewHash': confirmation})
    with os.fdopen(os.open(root / 'exec.claim', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
        stream.flush(); os.fsync(stream.fileno())
    sync_directory(root)
    require(validate(path, claimed=True) == s, 'Changed after permanent claim; no fallback')
    state = {'kind': KIND, 'specHash': digest(s), 'status': 'exec_boundary_issued', 'pid': os.getpid(),
             'parentPid': os.getppid(), 'processIdentity': restart.process_identity(os.getpid()),
             'at': time.time(), 'boundary': dict(BOUNDARY)}
    write_record(root / 'status.json', state)
    binary = str(Path(s['runtimePin']['root']) / 'bin/codex')
    argv = [binary, 'app-server', '--listen', 'unix://' + str(Path(s['socketDirectory']) / 'host.sock')]
    try:
        os.chdir(s['launchSpec']['cwd'])
        with open(os.devnull, 'rb') as source, open(os.devnull, 'wb') as sink:
            os.dup2(source.fileno(), 0); os.dup2(sink.fileno(), 1); os.dup2(sink.fileno(), 2)
        os.execve(binary, argv, launch.environment(s['launchSpec']))
        raise OSError('Exec unexpectedly returned')
    except (OSError, KeyboardInterrupt) as error:
        write_record(root / 'status.json', {**state, 'status': 'exec_outcome_unknown' if isinstance(error, KeyboardInterrupt) else 'exec_failed'})
        if isinstance(error, KeyboardInterrupt): raise
        raise Refusal('Host exec failed; canonical claim remains consumed, no fallback') from None


def status(path):
    """Historical file-only status, not liveness, native connectivity or safety."""
    s = load(path); root = Path(s['journal'])
    base = {'kind': KIND, 'historical': True, 'hostReady': False, 'boundary': dict(BOUNDARY)}
    if not os.path.lexists(root): return {**base, 'status': 'prepared_not_submitted'}
    if not (root / 'status.json').exists(): return {**base, 'status': 'outcome_unknown'}
    row = maintenance.read(root / 'status.json')
    require(row.get('kind') == KIND and row.get('specHash') == digest(s) and row.get('boundary') == BOUNDARY and
            row.get('status') in {'exec_boundary_issued', 'exec_failed', 'exec_outcome_unknown'}, 'Invalid historical repair result')
    return {**base, 'status': row['status'], 'pid': row['pid'], 'processIdentity': row['processIdentity']}


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('prepare')
    for key in ('certificate', 'previous_attempt', 'socket_directory', 'review_directory'): a.add_argument(key)
    for action in ('preview', 'status', 'exec'):
        a = sub.add_parser(action); a.add_argument('review')
        if action == 'exec': a.add_argument('--confirm-hash', required=True); a.add_argument('--writers-stopped', action='store_true')
    a = p.parse_args()
    if a.action == 'prepare': value = prepare(a.certificate, a.previous_attempt, a.socket_directory, a.review_directory)
    elif a.action == 'preview': value = preview(a.review)
    elif a.action == 'status': value = status(a.review)
    else: exec_host(a.review, a.confirm_hash, writers_stopped=a.writers_stopped); return
    print(canonical(value))


if __name__ == '__main__':
    try: main()
    except (Refusal, OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        print(canonical({'error': 'Post-reboot host repair refused; inspect private records, never retry a claim', 'boundary': BOUNDARY}))
        raise SystemExit(2)
