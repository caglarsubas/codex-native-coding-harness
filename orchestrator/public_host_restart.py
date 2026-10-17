"""Reviewed existing-home restart, never a Play/transfer/recovery retry.

The initial empty-home profile is unchanged. This maintenance profile preserves
one completed transfer, an empty paused standard run and all original unknowns.
It backs up opaque native files without opening/editing native databases. No
native RPC occurs before exec; subsequent qualification is metadata-only.
"""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import pwd
import shlex
import stat
import subprocess
import sys
import time
import tomllib

from .core import Refusal, canonical, digest, require
from .host_lifecycle import private_file, sync_directory, write_record
from .host_runtime import safe_path, stamp
from .native_project_assignment import _registered, _read_registry
from .native_read_client import decode, inspect_endpoint, ReadProxy
from .public_host_lifecycle import CONFIG, POLICY, FIELDS as LAUNCH_FIELDS, directory_identity, environment, isolated_directory
from .public_host_runtime import PROFILE as ORIGINAL_PROFILE, validate_pin
from . import public_identity_transfer as transfer
from .turn_host_continuity import process_absent

KIND = 'public_existing_home_restart_v1'
MAX_ENTRIES, MAX_FILE, MAX_HOME = 512, 256_000_000, 512_000_000
DATABASES = {'state_5','thread_history_1','goals_1','logs_2','queue_1','memories_1'}
TOP_FILES = {'config.toml','installation_id','.sqlite-maintenance.lock','.sandbox_migration'} | {
    base+'.sqlite'+suffix for base in DATABASES for suffix in ('','-wal','-shm')}
TOP_DIRS = {'sessions','thread-writer-locks','app-server-control','shell_snapshots','skills','tmp'}
FIELDS = {'version','kind','previousAttempt','previousPins','launchSpec','transferDirectory','transferPins',
          'sourceBinding','scope','homeSnapshotPin','backupPath','socketDirectory','socketDirectoryIdentity',
          'reviewDirectory','sourceTree','fencePath'}


def fixed(argv):
    try:
        result = subprocess.run(argv,capture_output=True,timeout=10,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    except (OSError,subprocess.TimeoutExpired):
        raise Refusal('Restart metadata unavailable; no execution or fallback') from None
    require(len(result.stdout) <= 1_000_000 and not result.stderr, 'Incomplete restart metadata')
    return result


def source_tree():
    root = Path(__file__).resolve().parent.parent
    head = fixed(['/usr/bin/git','-C',str(root),'rev-parse','HEAD^{tree}'])
    dirty = fixed(['/usr/bin/git','-C',str(root),'status','--porcelain=v1'])
    require(head.returncode == dirty.returncode == 0 and not dirty.stdout, 'Clean exact implementation source required')
    value = head.stdout.decode().strip()
    require(len(value) == 40 and all(c in '0123456789abcdef' for c in value), 'Exact implementation tree required')
    return value


def read_file(path, maximum=MAX_FILE):
    path = Path(path); before = safe_path(path)
    require(before.st_uid == os.getuid() and before.st_nlink == 1 and before.st_size <= maximum,
            'Bounded owner-controlled unaliased restart file required')
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),'rb') as stream:
        require(stamp(os.fstat(stream.fileno())) == stamp(before), 'Restart file changed before reading')
        raw = stream.read(maximum+1)
        require(len(raw) == before.st_size and stamp(os.fstat(stream.fileno())) == stamp(before), 'Restart file changed during reading')
    require(stamp(path.lstat()) == stamp(before), 'Restart file changed after reading')
    return raw, {'identity':list(stamp(before)), 'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def pin(path, maximum=65536):
    require(not safe_path(Path(path)).st_mode & 0o077, 'Owner-private restart record required')
    return {'path':str(path), **read_file(path,maximum)[1]}


def restricted_config(home, cwd):
    path = Path(home)/'config.toml'
    require(not safe_path(path).st_mode & 0o077, 'Native restart config must remain owner-private')
    raw, record = read_file(path,65536)
    try: value = tomllib.loads(raw.decode('utf-8'))
    except (ValueError,UnicodeError): raise Refusal('Malformed native restart configuration') from None
    projects = value.pop('projects',{})
    require(canonical(value) == canonical(tomllib.loads(CONFIG)) and
            (projects == {} or canonical(projects) == canonical({str(cwd):{'trust_level':'trusted'}})),
            'Only fixed restricted policy and an already saved exact-checkout native trust entry are supported')
    return {**record,'nativeProjectTrust':'trusted' if projects else 'absent'}


def original_launch(attempt, ledger, seen=()):
    attempt = isolated_directory(attempt)
    require(str(attempt) not in seen and len(seen) < 8, 'Restart provenance cycle or depth bound exceeded')
    if not (attempt/'launch.json').exists():
        return historical_restart(attempt,ledger,(*seen,str(attempt)))
    paths = [attempt/name for name in ('launch.json','status.json','exec.claim')]
    pins = [pin(p) for p in paths]
    launch, status = [decode(read_file(p,65536)[0]) for p in paths[:2]]
    require(set(launch) == {'spec','manifestHash','reviewHash','mode','createdAt'} and launch['mode'] == 'exec',
            'Exact original public exec journal required')
    spec = launch['spec']
    require(isinstance(spec,dict) and set(spec) == LAUNCH_FIELDS and type(spec['schemaVersion']) is int and
            spec['schemaVersion'] == 1 and spec['profile'] == ORIGINAL_PROFILE and spec['nativePolicy'] == POLICY and
            type(spec['nativePolicy'].get('codeMode')) is bool and spec['credentialMode'] == 'unconfigured',
            'Only the unchanged initial public launch is supported')
    from .public_host_lifecycle import review_hash, status as historical_status
    require(launch['manifestHash'] == digest(spec) and launch['reviewHash'] == review_hash(spec) and
            historical_status(attempt)['status'] == 'exec_boundary_issued' and pins[2]['bytes'] == 0,
            'Original public exec claim/provenance is incomplete')
    validate_pin(spec['runtimePackage'])
    require(directory_identity(Path(spec['cwd'])) == spec['cwdIdentity'] and
            directory_identity(Path(spec['codexHome'])) == spec['homeIdentity'], 'Original home/checkout identity changed')
    home, cwd, runtime = isolated_directory(spec['codexHome']), Path(spec['cwd']), Path(spec['runtimePackage']['root'])
    require(home != (Path(pwd.getpwuid(os.getuid()).pw_dir)/'.codex').resolve() and
            not home.is_relative_to(Path('/private/var/tmp')) and (cwd/'.git').is_dir() and not (cwd/'.git').is_symlink() and
            all(not a.is_relative_to(b) for a in (home,cwd,runtime) for b in (home,cwd,runtime) if a != b) and
            len({home,cwd,runtime}) == 3, 'Original isolated home/checkout/package boundaries are required')
    for extra in (cwd/'config.toml',cwd/'.codex/config.toml',Path('/etc/codex/config.toml'),Path('/etc/codex/requirements.toml'),
                  Path('/etc/codex/managed_config.toml'),Path('/Library/Preferences/com.openai.codex.plist')):
        require(not extra.exists() and not extra.is_symlink(), 'Additional configuration requires a separately qualified profile')
    require(spec['configPin']['sha256'] == hashlib.sha256(CONFIG.encode()).hexdigest() and
            spec['configPin']['bytes'] == len(CONFIG.encode()) and spec['configPin']['mode'] == 0o600,
            'Original empty-home restricted configuration pin differs')
    restricted_config(spec['codexHome'],spec['cwd'])
    # Old socket bytes remain historical. Never validate or connect that endpoint.
    return spec, status, pins


def historical_restart(attempt, ledger, seen):
    """Preserved predecessor only. No source-tree upgrade, socket or native read."""
    path = attempt.parent/'restart.json'
    spec = decode(read_file(private_file(path),65536)[0])
    require(set(spec) == FIELDS and type(spec['version']) is int and spec['version'] == 1 and spec['kind'] == KIND and
            spec['reviewDirectory'] == str(attempt.parent), 'Exact historical restart scope required')
    launch, predecessor, earlier_pins = original_launch(spec['previousAttempt'],ledger,seen)
    require(launch == spec['launchSpec'] and earlier_pins == spec['previousPins'], 'Restart chain predecessor changed')
    transferred_spec, source, transfer_pins = transferred(spec['transferDirectory'],launch)
    require(source == spec['sourceBinding'] and transfer_pins == spec['transferPins'], 'Historical transfer changed')
    require(spec['scope']['workspaceId'] == ledger.workspace_id and spec['scope']['brainId'] == transferred_spec['brainId'] and
            transfer.context(ledger,source) == spec['scope']['context'] == transferred_spec['context'], 'Historical run scope changed')
    intent = decode(read_file(private_file(attempt/'intent.json'),65536)[0])
    state = decode(read_file(private_file(attempt/'status.json'),65536)[0])
    validate_status(state,spec,execution_boundary=True)
    require(intent.get('kind') == KIND and intent.get('specHash') == digest(spec) and
            intent.get('reviewHash') == review_hash(spec) and pin(attempt/'exec.claim')['bytes'] == 0,
            'Historical restart intent/claim differs')
    fence = restart_fence(ledger,launch,transferred_spec,predecessor)
    require(spec['fencePath'] == str(fence) and decode(read_file(private_file(fence),65536)[0]) ==
            {'kind':KIND,'specHash':digest(spec),'reviewDirectory':spec['reviewDirectory']}, 'Historical restart fence differs')
    require(pin(spec['homeSnapshotPin']['path'],1_000_000) == spec['homeSnapshotPin'], 'Historical home archive changed')
    snapshot = decode(read_file(spec['homeSnapshotPin']['path'],1_000_000)[0]); backup_check(spec,snapshot)
    for previous in (predecessor, state):
        require(process_absent(previous['pid']), 'A predecessor PID is live, reused or unknown')
    pins = [pin(path),pin(attempt/'intent.json'),pin(attempt/'status.json'),pin(attempt/'exec.claim'),pin(fence),
            pin(spec['homeSnapshotPin']['path'],1_000_000)]
    return launch,state,earlier_pins+pins


def transferred(directory, launch):
    directory = isolated_directory(directory)
    spec = transfer.load_spec(directory/'transfer.json')
    result = decode(read_file(private_file(directory/'attempt/result.json'),65536)[0])
    review = transfer.preview(spec)['reviewHash']
    require(result == {'version':1,'specHash':digest(spec),'reviewHash':review,'status':'metadata_transferred',
        'brainId':spec['brainId'],'projectId':spec['snapshot']['project']['id'],
        'historySha256':spec['archivePin']['sha256'],'historicalTerminalSafety':'unknown',
        'sourceCurrentTerminalSafety':'unknown','migrationQualified':False,'bindingInstalled':False,
        'resumeAuthorized':False,'pilotAccepted':False}, 'A completed exact one-brain transfer is required')
    require(spec['destinationHome'] == launch['codexHome'] and spec['cwd'] == launch['cwd'], 'Transfer home or checkout differs')
    source = decode(read_file(private_file(spec['sourceBindingPath']),65536)[0])
    destination = decode(read_file(private_file(spec['destinationBindingPath']),65536)[0])
    require(digest(source) == spec['sourceBindingHash'] and digest(destination) == spec['destinationBindingHash'] and
            set(source['brains']) == set(destination['brains']) == {spec['brainId']}, 'Preserved transfer binding changed')
    row = destination['brains'][spec['brainId']]
    require(all(row.get(k) == source['brains'][spec['brainId']].get(k) for k in transfer.IDENTITY_FIELDS), 'Transferred identities changed')
    native = row.get('nativeTaskBackend') or {}
    require(all(native.get(k) == launch['runtimePackage'][k] for k in ('sourceCommit','sourceTree')),
            'Transferred native build differs from restart runtime')
    require(row['projectId'] == result['projectId'] and row.get('catalogProjectId',row['projectId']) == spec['catalogProjectId'],
            'Both transferred project identities are required')
    intent = decode(read_file(private_file(directory/'attempt/intent.json'),65536)[0])
    require(intent.get('specHash') == digest(spec) and intent.get('reviewHash') == review, 'Transfer intent differs')
    fence = decode(read_file(private_file(spec['fencePath']),65536)[0])
    require(fence == {'kind':transfer.KIND,'specHash':digest(spec),'reviewHash':review,
        'runId':spec['context']['runId'],'originalPlayId':spec['context']['originalPlayId'],
        'originalPlayHash':spec['context']['originalPlayHash'],'attemptDirectory':str(directory/'attempt')}, 'Original transfer fence differs')
    paths = [directory/'transfer.json', directory/'attempt/intent.json',directory/'attempt/result.json',Path(spec['fencePath']),
             Path(spec['sourceBindingPath']),Path(spec['destinationBindingPath']),Path(spec['archivePath'])]
    for name in ('project_restore','inspection_load','project_assignment'):
        path = directory/'attempt'/(name+'.claim')
        require(pin(path)['bytes'] == 0, 'Transfer claim differs')
        paths.append(path)
    require(transfer.archive_pin(spec['archivePath']) == spec['archivePin'], 'Transferred archive changed')
    return spec, source, [pin(path,transfer.MAX_ROLLOUT if path == Path(spec['archivePath']) else 65536) for path in paths]


def scope(registry, ledger, transferred_spec, source):
    from .enrollment import record_in
    with _read_registry(registry) as db: require(record_in(db) is None, 'Strict enrollment refuses restart')
    root, inspected, catalog, mappings = _registered(registry,ledger.workspace_id)
    require(root == ledger.root and inspected['brainId'] == transferred_spec['brainId'], 'Registered brain changed')
    require(transfer.context(ledger,source) == transferred_spec['context'], 'Original paused run, usage, receipts or expiry changed')
    row = source['brains'][inspected['brainId']]
    require(row['workspaceId'] == ledger.workspace_id, 'Workspace differs')
    linked = [p for p in (catalog or {}).get('projects',[]) if p['projectId'] == transferred_spec['catalogProjectId'] and
        (mappings.get(p['key']) or {}).get('workspaceId') == ledger.workspace_id and
        (mappings.get(p['key']) or {}).get('brainId') == inspected['brainId'] and
        (mappings.get(p['key']) or {}).get('databaseIdentity') == inspected['databaseIdentity'] and
        (mappings.get(p['key']) or {}).get('locationHash') == p['locationHash']]
    require(len(linked) == 1, 'Exact retained native catalog mapping required')
    return {'workspaceId':ledger.workspace_id,'brainId':inspected['brainId'],'ledgerIdentity':inspected['databaseIdentity'],
            'catalogHash':catalog['hash'],'mappingHash':digest(mappings),'context':transferred_spec['context']}


def quiescent(launch, status):
    require(process_absent(status['pid']), 'Previous PID is live, reused or unknown; never kill it')
    binary = str(Path(launch['runtimePackage']['root'])/'bin/codex')
    processes = fixed(['/bin/ps','-axo','pid=,comm='])
    require(processes.returncode == 0, 'Complete process metadata required')
    for line in processes.stdout.decode().splitlines():
        values = line.strip().split(None,1)
        require(len(values) == 2 and values[0].isdigit(), 'Incomplete process metadata')
        require(values[1] != binary and not (Path(values[1]).name == 'codex' and not Path(values[1]).is_absolute()),
                'A matching or ambiguous native binary is running')
    handles = fixed(['/usr/sbin/lsof','-nP','-t','+D',launch['codexHome']])
    require(handles.returncode == 1 and not handles.stdout, 'Native home has open handles or unknown writer status')


def home_snapshot(home, binary, backup=None, *, brain=None):
    """Opaque bounded file inventory; no SQL, configuration evaluation or restore."""
    return _home_snapshot(home, binary, backup, brain=brain, signed_in_preplay=False)


def signed_in_preplay_snapshot(home, binary, backup=None, *, brain):
    """Separate pre-Play maintenance profile; credential bytes are never opened.

    This is not permission to copy credentials or to use this home in the older
    transferred-run restart profile. The caller pins the existing credential
    epoch and preserves the file in place, outside the opaque state backup.
    """
    return _home_snapshot(home, binary, backup, brain=brain, signed_in_preplay=True)


def _home_snapshot(home, binary, backup, *, brain, signed_in_preplay):
    home = isolated_directory(home)
    top_files = TOP_FILES | ({'auth.json', 'models_cache.json'} if signed_in_preplay else set())
    with os.scandir(home) as entries:
        top = []
        for entry in entries:
            top.append(entry)
            require(len(top) <= MAX_ENTRIES, 'Native home inventory exceeds bound')
    require(len(top) <= MAX_ENTRIES and all(p.name in top_files|TOP_DIRS for p in top),
            'Unsupported native home entry; credentials/plugins are not imported or read')
    rows, directories, count, total, credential = {}, {}, 0, 0, None
    pending = [home]
    while pending:
        current = pending.pop(); relative = current.relative_to(home)
        info = safe_path(current,directory=True)
        require(info.st_uid == os.getuid(), 'Native directory owner differs')
        directories[str(relative)] = list(stamp(info))
        if backup is not None and current != home: (backup/relative).mkdir(mode=0o700)
        with os.scandir(current) as scan:
            entries = []
            for entry in scan:
                entries.append(entry)
                require(len(entries)+count <= MAX_ENTRIES, 'Native home inventory exceeds bound')
        entries.sort(key=lambda p:p.name)
        count += len(entries)
        require(count <= MAX_ENTRIES, 'Native home inventory exceeds bound')
        for entry in entries:
            path = Path(entry.path); rel = str(path.relative_to(home)); before = path.lstat()
            parts = path.relative_to(home).parts
            require(len(path.relative_to(home).parts) <= 16 and len(rel) <= 1024, 'Native path bound exceeded')
            if signed_in_preplay and rel == 'auth.json':
                # Deliberately no open(), hash, JSON decode, backup or auth RPC.
                safe_path(path)
                require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid() and
                        before.st_nlink == 1 and not before.st_mode & 0o077 and 0 < before.st_size <= 65536,
                        'Existing private unaliased credential metadata required')
                credential = {'identity':list(stamp(before)), 'bytesRead':False, 'copied':False}
                continue
            require(entry.name not in {'auth.json','.credentials.json','.env','plugins','hooks','managed-config.toml'},
                    'Credential/plugin/config content is outside native-home backup scope')
            require(parts[0] != 'skills' or len(parts) == 1 or parts[1] == '.system', 'Only embedded system skills may be retained')
            require(parts[0] != 'shell_snapshots' or stat.S_ISDIR(before.st_mode) and len(parts) == 1,
                    'Shell snapshots need a separate qualified profile')
            if stat.S_ISDIR(before.st_mode):
                require(entry.name in TOP_DIRS if current == home else True, 'Unexpected native directory')
                pending.append(path); continue
            if stat.S_ISLNK(before.st_mode):
                require(path.relative_to(home).parts[:2] == ('tmp','arg0') and entry.name in
                        {'apply_patch','applypatch','codex-execve-wrapper'} and os.readlink(path) == binary and
                        before.st_uid == os.getuid() and before.st_nlink == 1, 'Only pinned native arg0 links are supported')
                rows[rel] = {'link':binary,'identity':list(stamp(before))}
                if backup is not None: os.symlink(binary,backup/rel)
                require(stamp(path.lstat()) == stamp(before) and os.readlink(path) == binary, 'Native link changed')
                continue
            require(entry.name in top_files if current == home else True, 'Unexpected native file')
            if parts[0] == 'sessions' and brain is not None:
                require(entry.name.endswith('-'+brain+'.jsonl'), 'Foreign or unsupported native session history')
            raw, record = read_file(path,min(MAX_FILE,MAX_HOME-total))
            total += len(raw); rows[rel] = record
            if backup is not None:
                with os.fdopen(os.open(backup/rel,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as stream:
                    stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        require(list(stamp(current.lstat())) == directories[str(relative)], 'Native directory changed')
    require('config.toml' in rows and 'state_5.sqlite' in rows and any(p.startswith('sessions/') for p in rows),
            'An existing native state/history home is required')
    for rel, record in rows.items():
        require(list(stamp((home/rel).lstat())) == record['identity'], 'Native file epoch changed')
    for rel, record in directories.items():
        require(list(stamp((home/rel).lstat())) == record, 'Native directory epoch changed')
    if signed_in_preplay:
        require(credential is not None and list(stamp((home/'auth.json').lstat())) == credential['identity'],
                'Existing credential metadata is missing or changed')
    if backup is not None:
        for rel in sorted(directories,key=lambda p:len(Path(p).parts),reverse=True): sync_directory(backup/rel)
    result = {'files':rows,'directories':directories,'bytes':total}
    if signed_in_preplay: result['credentialMetadata'] = credential
    return result


def backup_check(spec, snapshot):
    root = isolated_directory(spec['backupPath'])
    found_files, found_dirs = set(), {'.'}
    for parent, dirs, files in os.walk(root,followlinks=False):
        for name in dirs:
            path = Path(parent)/name
            require(not path.is_symlink(), 'Backup directory alias')
            found_dirs.add(str(path.relative_to(root)))
        for name in files:
            path = Path(parent)/name; rel = str(path.relative_to(root)); found_files.add(rel)
            require(rel in snapshot['files'], 'Unexpected backup file')
            record = snapshot['files'][rel]
            if 'link' in record:
                require(path.is_symlink() and os.readlink(path) == record['link'], 'Backup link differs')
            else:
                private_file_limit = safe_path(path)
                require(not private_file_limit.st_mode & 0o077, 'Backup must remain private')
                raw, value = read_file(path)
                require(value['bytes'] == record['bytes'] and value['sha256'] == record['sha256'], 'Backup bytes differ')
    require(found_files == set(snapshot['files']) and found_dirs == set(snapshot['directories']), 'Incomplete native backup')


def inputs(registry, ledger, previous, transfer_directory):
    launch, old_status, old_pins = original_launch(previous,ledger)
    spec, source, transfer_pins = transferred(transfer_directory,launch)
    require(Path(spec['fencePath']) == transfer.fence_path(ledger,spec['context']), 'Original canonical transfer fence differs')
    return launch, old_status, old_pins, spec, source, transfer_pins, scope(registry,ledger,spec,source)


def restart_fence(ledger, launch, transfer_spec, predecessor):
    # Independent of review directories, file epochs, touched journals, current
    # usage and proposed socket paths. Another preview cannot reset an attempt.
    key = digest({'launchSpec':launch,'homeIdentity':launch['homeIdentity'],
                  'runId':transfer_spec['context']['runId'],'originalPlayId':transfer_spec['context']['originalPlayId'],
                  'brainId':transfer_spec['brainId'],'previousPid':predecessor['pid'],
                  'previousEpoch':predecessor.get('processIdentity',predecessor.get('observedAt')),
                  'previousSpecHash':predecessor.get('specHash')})
    return ledger.root/('public-existing-home-restart-'+key+'.json')


def prepare(registry, ledger, previous, transfer_directory, sockets, directory):
    values = inputs(registry,ledger,previous,transfer_directory)
    launch, old_status, old_pins, transfer_spec, source, transfer_pins, protected = values
    sockets = isolated_directory(sockets)
    require(not list(sockets.iterdir()) and len(os.fsencode(str(sockets/'host.sock'))) <= 100, 'New empty bounded private socket directory required')
    directory = Path(directory); isolated_directory(directory.parent)
    roots = [Path(launch[k]) for k in ('cwd','codexHome')] + [Path(launch['runtimePackage']['root']),Path(previous),Path(transfer_directory),sockets]
    require(sockets != Path(launch['socketDirectory']), 'A separate new socket directory is required')
    require(directory.is_absolute() and directory.parent.resolve(strict=True) == directory.parent and
            all(not directory.is_relative_to(p) and not p.is_relative_to(directory) for p in roots) and
            all(not sockets.is_relative_to(p) and not p.is_relative_to(sockets) for p in roots[:-1]), 'Restart paths must be disjoint')
    tree = source_tree()
    for _ in range(2): quiescent(launch,old_status)
    binary = str(Path(launch['runtimePackage']['root'])/'bin/codex')
    before = home_snapshot(launch['codexHome'],binary,brain=transfer_spec['brainId'])
    directory.mkdir(mode=0o700); sync_directory(directory.parent)
    backup = directory/'native-home-backup'; backup.mkdir(mode=0o700)
    copied = home_snapshot(launch['codexHome'],binary,backup,brain=transfer_spec['brainId'])
    require(copied == before, 'Native home changed while backing up; retain partial review')
    write_record(directory/'home-snapshot.json',before)
    fence = restart_fence(ledger,launch,transfer_spec,old_status)
    require(not fence.exists() and not fence.is_symlink(), 'A restart of this original host is already consumed')
    spec = {'version':1,'kind':KIND,'previousAttempt':str(previous),'previousPins':old_pins,'launchSpec':launch,
        'transferDirectory':str(transfer_directory),'transferPins':transfer_pins,'sourceBinding':source,'scope':protected,
        'homeSnapshotPin':pin(directory/'home-snapshot.json',1_000_000),'backupPath':str(backup),
        'socketDirectory':str(sockets),'socketDirectoryIdentity':directory_identity(sockets),
        'reviewDirectory':str(directory),'sourceTree':tree,'fencePath':str(fence)}
    backup_check(spec,before)
    require(values == inputs(registry,ledger,previous,transfer_directory), 'Protected scope changed while preparing')
    for _ in range(2): quiescent(launch,old_status)
    require(before == home_snapshot(launch['codexHome'],binary,brain=transfer_spec['brainId']), 'Native home changed during review preparation')
    write_record(directory/'restart.json',spec)
    return preview(registry,ledger,directory/'restart.json')


def load_spec(path):
    spec = decode(read_file(private_file(path),65536)[0])
    require(isinstance(spec,dict) and set(spec) == FIELDS and type(spec['version']) is int and spec['version'] == 1 and spec['kind'] == KIND,
            'Closed existing-home restart manifest required')
    require(Path(path) == Path(spec['reviewDirectory'])/'restart.json' and
            spec['sourceTree'] == source_tree(), 'Restart implementation or review location changed')
    directory = isolated_directory(spec['reviewDirectory'])
    require(spec['backupPath'] == str(directory/'native-home-backup') and
            spec['homeSnapshotPin']['path'] == str(directory/'home-snapshot.json'), 'Closed restart archive locations required')
    launch = spec['launchSpec']; sockets = isolated_directory(spec['socketDirectory'])
    roots = [Path(launch[k]) for k in ('cwd','codexHome')] + [Path(launch['runtimePackage']['root']),
             Path(spec['previousAttempt']),Path(spec['transferDirectory'])]
    require(sockets != Path(launch['socketDirectory']) and
            all(not directory.is_relative_to(p) and not p.is_relative_to(directory) and
                not sockets.is_relative_to(p) and not p.is_relative_to(sockets) for p in roots) and
            not sockets.is_relative_to(directory) and not directory.is_relative_to(sockets), 'Restart path boundary changed')
    return spec


def validate(registry, ledger, path, *, claimed=False):
    spec = load_spec(path)
    values = inputs(registry,ledger,spec['previousAttempt'],spec['transferDirectory'])
    launch, old_status, old_pins, transfer_spec, source, transfer_pins, protected = values
    require((launch,old_pins,source,transfer_pins,protected) ==
            (spec['launchSpec'],spec['previousPins'],spec['sourceBinding'],spec['transferPins'],spec['scope']), 'Reviewed restart scope drifted')
    expected_fence = restart_fence(ledger,launch,transfer_spec,old_status)
    require(spec['fencePath'] == str(expected_fence), 'Canonical restart fence differs')
    require(pin(spec['homeSnapshotPin']['path'],1_000_000) == spec['homeSnapshotPin'], 'Native snapshot archive changed')
    snapshot = decode(read_file(spec['homeSnapshotPin']['path'],1_000_000)[0])
    sockets = isolated_directory(spec['socketDirectory'])
    require(directory_identity(sockets) == spec['socketDirectoryIdentity'] and not list(sockets.iterdir()), 'New socket directory changed')
    for _ in range(2): quiescent(launch,old_status)
    binary = str(Path(launch['runtimePackage']['root'])/'bin/codex')
    require(home_snapshot(launch['codexHome'],binary,brain=transfer_spec['brainId']) == snapshot, 'Reviewed existing home changed')
    backup_check(spec,snapshot)
    fence = Path(spec['fencePath'])
    if claimed:
        require(decode(read_file(private_file(fence),65536)[0]) ==
                {'kind':KIND,'specHash':digest(spec),'reviewDirectory':spec['reviewDirectory']}, 'Claimed restart fence differs')
    else: require(not fence.exists() and not fence.is_symlink(), 'Restart already consumed; never relaunch')
    return spec


def review_hash(spec): return digest({'kind':KIND,'mode':'exec','specHash':digest(spec)})


def process_identity(pid):
    value = fixed(['/bin/ps','-p',str(pid),'-o','pid=,lstart='])
    require(value.returncode == 0, 'Exact process birth metadata unavailable')
    text = value.stdout.decode().strip()
    require(20 <= len(text) <= 128 and text.split(None,1)[0] == str(pid), 'Process identity metadata is malformed')
    return text


def preview(registry, ledger, path):
    spec = validate(registry,ledger,path)
    return {'kind':KIND,'reviewHash':review_hash(spec),'validity':'until_scope_changes','brainId':spec['scope']['brainId'],
            'preservedNativeProjectTrust':restricted_config(spec['launchSpec']['codexHome'],spec['launchSpec']['cwd'])['nativeProjectTrust'],
            'startsHost':False,'loadsBrain':False,'turnStarted':False,'bindingInstalled':False,'terminalSafety':'unknown','pilotAccepted':False}


def exec_host(registry, ledger, path, confirm_hash):
    spec = validate(registry,ledger,path)
    require(sys.platform == 'darwin' and platform.machine() == 'arm64', 'This restart profile requires macOS ARM64')
    require(confirm_hash == review_hash(spec), 'Exact new existing-home launch review required; old approvals cannot be reused')
    attempt = Path(spec['reviewDirectory'])/'attempt'
    attempt.mkdir(mode=0o700); sync_directory(attempt.parent)
    write_record(attempt/'intent.json',{'kind':KIND,'specHash':digest(spec),'reviewHash':confirm_hash,'at':time.time()})
    with os.fdopen(os.open(spec['fencePath'],os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'w') as stream:
        stream.write(canonical({'kind':KIND,'specHash':digest(spec),'reviewDirectory':spec['reviewDirectory']}))
        stream.flush(); os.fsync(stream.fileno())
    sync_directory(Path(spec['fencePath']).parent)
    with os.fdopen(os.open(attempt/'exec.claim',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'w') as stream:
        stream.flush(); os.fsync(stream.fileno())
    sync_directory(attempt)
    require(validate(registry,ledger,path,claimed=True) == spec, 'Restart drift before exec')
    state = {'kind':KIND,'status':'exec_boundary_issued','pid':os.getpid(),'parentPid':os.getppid(),'at':time.time(),
             'processIdentity':process_identity(os.getpid()),
             'specHash':digest(spec),'hostReady':False,'terminalSafety':'unknown','pilotAccepted':False}
    write_record(attempt/'status.json',state)
    binary = str(Path(spec['launchSpec']['runtimePackage']['root'])/'bin/codex')
    argv = [binary,'app-server','--listen','unix://'+str(Path(spec['socketDirectory'])/'host.sock')]
    try:
        os.chdir(spec['launchSpec']['cwd'])
        with open(os.devnull,'rb') as source, open(os.devnull,'wb') as sink:
            os.dup2(source.fileno(),0); os.dup2(sink.fileno(),1); os.dup2(sink.fileno(),2)
        os.execve(binary,argv,environment(spec['launchSpec']))
        raise OSError('Exec unexpectedly returned')
    except (OSError,KeyboardInterrupt) as error:
        write_record(attempt/'status.json',{**state,'status':'exec_outcome_unknown' if isinstance(error,KeyboardInterrupt) else 'exec_failed'})
        if isinstance(error,KeyboardInterrupt): raise
        raise Refusal('Restart exec failed; claim remains consumed, with no fallback') from None


def live_process(spec, state):
    require(type(state.get('pid')) is int and state['pid'] > 1, 'Exact restart PID required')
    require(process_identity(state['pid']) == state['processIdentity'], 'Restart PID birth epoch differs')
    binary = str(Path(spec['launchSpec']['runtimePackage']['root'])/'bin/codex')
    expected = [binary,'app-server','--listen','unix://'+str(Path(spec['socketDirectory'])/'host.sock')]
    command = fixed(['/bin/ps','-p',str(state['pid']),'-o','command='])
    require(command.returncode == 0 and shlex.split(command.stdout.decode()) == expected, 'Restart process is absent, reused or different')
    cwd = fixed(['/usr/sbin/lsof','-a','-p',str(state['pid']),'-d','cwd','-Fn'])
    require(cwd.returncode == 0 and 'n'+spec['launchSpec']['cwd'] in cwd.stdout.decode().splitlines(), 'Restart process checkout differs')


def validate_status(state, spec, *, execution_boundary=False):
    require(isinstance(state,dict) and set(state) == {'kind','status','pid','parentPid','at','specHash','processIdentity','hostReady','terminalSafety','pilotAccepted'} and
            state['kind'] == KIND and state['status'] in {'exec_boundary_issued','exec_failed','exec_outcome_unknown'} and
            (not execution_boundary or state['status'] == 'exec_boundary_issued') and state['specHash'] == digest(spec) and
            all(type(state[k]) is int and state[k] > 1 for k in ('pid','parentPid')) and
            isinstance(state['processIdentity'],str) and 20 <= len(state['processIdentity']) <= 128 and
            state['processIdentity'].split(None,1)[0] == str(state['pid']) and
            state['hostReady'] is False and state['pilotAccepted'] is False and state['terminalSafety'] == 'unknown',
            'Issued restart is required; failed/unknown exec is not connectivity authority')


class RestartReadProxy(ReadProxy):
    """Closed project/brain metadata only; no load, turn, login or response."""
    def __init__(self, endpoint, brain, project):
        self.brain, self.project = brain, project
        super().__init__(endpoint)

    def _rpc(self, method, params):
        allowed = {'project/read':{'projectId':self.project},
            'thread/read':{'threadId':self.brain,'includeTurns':False},
            'thread/turns/list':{'threadId':self.brain,'cursor':None,'limit':1,'sortDirection':'desc','itemsView':'notLoaded'},
            'thread/effectivePolicy/read':{'threadId':self.brain},
            'mcpServerStatus/list':{'detail':'toolsAndAuthOnly'},'account/read':{'refreshToken':False},
            'initialize':{'clientInfo':{'name':'codex_orchestrator_observer','version':'1'},'capabilities':{'experimentalApi':True}}}
        require(method in allowed and params == allowed[method], 'Restart inspection accepts only exact non-waking metadata')
        return super()._rpc(method,params)


def inspect(registry, ledger, path, directory):
    """Explicit post-exec connectivity evidence; no dashboard binding applied."""
    from .native_auth_readiness import inspect as authentication
    from .native_policy_evidence import reported, matches
    spec = load_spec(path)
    directory = Path(directory); isolated_directory(directory.parent)
    roots = [Path(spec['launchSpec'][k]) for k in ('cwd','codexHome')] + [Path(spec['launchSpec']['runtimePackage']['root']),
        Path(spec['socketDirectory']),Path(spec['reviewDirectory']),Path(spec['previousAttempt']),Path(spec['transferDirectory'])]
    require(directory.is_absolute() and directory.parent.resolve(strict=True) == directory.parent and
            not directory.exists() and not directory.is_symlink() and
            all(not directory.is_relative_to(p) and not p.is_relative_to(directory) for p in roots),
            'New private disjoint evidence directory required before native inspection')
    launch, old_status, old_pins, transferred_spec, source, transfer_pins, protected = inputs(
        registry,ledger,spec['previousAttempt'],spec['transferDirectory'])
    require((launch,old_pins,source,transfer_pins,protected) ==
            (spec['launchSpec'],spec['previousPins'],spec['sourceBinding'],spec['transferPins'],spec['scope']), 'Protected restart scope changed')
    attempt = Path(spec['reviewDirectory'])/'attempt'
    require(pin(attempt/'exec.claim')['bytes'] == 0, 'Restart exec claim missing')
    intent = decode(read_file(private_file(attempt/'intent.json'),65536)[0])
    require(intent.get('kind') == KIND and intent.get('specHash') == digest(spec) and intent.get('reviewHash') == review_hash(spec), 'Restart intent changed')
    expected_fence = restart_fence(ledger,launch,transferred_spec,old_status)
    require(str(expected_fence) == spec['fencePath'] and decode(read_file(private_file(expected_fence),65536)[0]) ==
            {'kind':KIND,'specHash':digest(spec),'reviewDirectory':spec['reviewDirectory']}, 'Restart claim changed')
    state = decode(read_file(private_file(attempt/'status.json'),65536)[0])
    validate_status(state,spec,execution_boundary=True)
    require(process_absent(old_status['pid']), 'Old host PID is live, reused or unknown')
    live_process(spec,state)
    require(directory_identity(Path(spec['socketDirectory'])) == spec['socketDirectoryIdentity'], 'Reviewed socket directory changed')
    alias = Path(spec['socketDirectory'])/'host.sock'
    require(alias.lstat().st_uid == os.getuid(), 'New rendezvous owner differs')
    physical = alias.resolve(strict=True)
    previous = decode(read_file(private_file(transferred_spec['destinationBindingPath']),65536)[0])
    endpoint = inspect_endpoint(str(Path(launch['runtimePackage']['root'])/'bin/codex'),str(physical),previous['endpoint']['serverIdentityHash'])
    require(endpoint['socket'] != previous['endpoint']['socket'] and endpoint['socketIdentity'] != previous['endpoint']['socketIdentity'],
            'A new actual socket epoch is required; no old endpoint reconnect')
    candidate = {'endpoint':endpoint,'brains':previous['brains']}
    snapshot = decode(read_file(spec['homeSnapshotPin']['path'],1_000_000)[0])
    require(pin(spec['homeSnapshotPin']['path'],1_000_000) == spec['homeSnapshotPin'], 'Snapshot changed')
    backup_check(spec,snapshot)
    def preserved_history():
        for relative, record in snapshot['files'].items():
            if relative == 'config.toml':
                _, current = read_file(Path(launch['codexHome'])/relative,65536)
                require(current == record, 'Reviewed configuration bytes or epoch changed after restart')
            elif relative.startswith('sessions/') or relative == 'installation_id':
                raw, _ = read_file(Path(launch['codexHome'])/relative)
                require(len(raw) >= record['bytes'] and hashlib.sha256(raw[:record['bytes']]).hexdigest() == record['sha256'],
                        'Retained native history prefix or installation identity changed')
    preserved_history()
    observations = []
    with RestartReadProxy(endpoint,transferred_spec['brainId'],transferred_spec['snapshot']['project']['id']) as proxy:
        for _ in range(2):
            project = proxy._rpc('project/read',{'projectId':transferred_spec['snapshot']['project']['id']})['project']
            require(project['id'] == transferred_spec['snapshot']['project']['id'] and project['roots'] == [{'path':launch['cwd']}], 'Native project identity/root differs')
            thread = proxy._rpc('thread/read',{'threadId':transferred_spec['brainId'],'includeTurns':False})['thread']
            require(thread['id'] == transferred_spec['brainId'] and thread['projectId'] == project['id'] and
                    thread['cwd'] == launch['cwd'] and thread['status']['type'] in {'notLoaded','idle'}, 'Native brain identity or activity differs')
            latest = proxy._rpc('thread/turns/list',{'threadId':transferred_spec['brainId'],'cursor':None,'limit':1,'sortDirection':'desc','itemsView':'notLoaded'})
            turns = latest.get('data')
            require(isinstance(turns,list) and len(turns) == 1 and turns[0]['id'] == transferred_spec['snapshot']['latestTurnId'] and
                    turns[0]['status'] == transferred_spec['snapshot']['latestTurnStatus'], 'Original latest ended turn differs')
            require(proxy._rpc('mcpServerStatus/list',{'detail':'toolsAndAuthOnly'}) == {'data':[],'nextCursor':None}, 'MCP inventory is not complete/empty')
            policy = reported(proxy._rpc('thread/effectivePolicy/read',{'threadId':transferred_spec['brainId']}),transferred_spec['brainId'],launch['cwd'])
            observations.append({'brainActivity':thread['status']['type'],'policy':policy,'latestTurnId':turns[0]['id'],'latestTurnStatus':turns[0]['status']})
        require(observations[0] == observations[1], 'Native metadata changed during inspection')
        auth = authentication(proxy)
    live_process(spec,state); preserved_history()
    require(inputs(registry,ledger,spec['previousAttempt'],spec['transferDirectory']) ==
            (launch,old_status,old_pins,transferred_spec,source,transfer_pins,protected), 'Protected state changed during native reads')
    require(all(not directory.is_relative_to(p) and not p.is_relative_to(directory) for p in roots),
            'Private disjoint evidence directory changed')
    directory.mkdir(mode=0o700); sync_directory(directory.parent)
    report = {'kind':KIND,'status':'connected_read_only','checkedAt':time.time(),'specHash':digest(spec),'pid':state['pid'],
        'bindingHash':digest(candidate),'workspaceId':ledger.workspace_id,'brainId':transferred_spec['brainId'],
        'projectId':project['id'],'catalogProjectId':transferred_spec['catalogProjectId'],'observation':observations[-1],
        'policyVerified':matches(observations[-1]['policy']),'authentication':auth,
        'nativeWrites':0,'loads':0,'turns':0,'bindingInstalled':False,'originalStateUnchanged':True,
        'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown','migrationQualified':False,'pilotAccepted':False}
    write_record(directory/'binding-candidate.json',candidate); write_record(directory/'connectivity.json',report)
    return report


def status(path):
    """Historical private files only, even after scope/source/host drift."""
    spec = decode(read_file(private_file(path),65536)[0])
    require(isinstance(spec,dict) and set(spec) == FIELDS and spec['kind'] == KIND and
            type(spec['version']) is int and spec['version'] == 1 and
            Path(path) == Path(spec['reviewDirectory'])/'restart.json', 'Closed historical restart record required')
    attempt = Path(spec['reviewDirectory'])/'attempt'
    base = {'kind':KIND,'specHash':digest(spec),'historical':True,'hostReady':False,
            'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown','pilotAccepted':False}
    if not attempt.exists(): return {**base,'status':'prepared_not_submitted','claimRetained':False}
    isolated_directory(attempt)
    if not (attempt/'status.json').exists():
        return {**base,'status':'outcome_unknown','claimRetained':(attempt/'exec.claim').exists()}
    row = decode(read_file(private_file(attempt/'status.json'),65536)[0])
    require(row.get('status') in {'exec_boundary_issued','exec_failed','exec_outcome_unknown'}, 'Unknown historical restart status')
    validate_status(row,spec)  # Preserve the actual original status verbatim.
    return {**base,'status':row['status'],'claimRetained':(attempt/'exec.claim').exists(),
            'pid':row['pid'],'processIdentity':row['processIdentity']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform',type=Path,required=True); parser.add_argument('--workspace',required=True)
    sub = parser.add_subparsers(dest='operation',required=True)
    setup = sub.add_parser('prepare')
    for name in ('previous_attempt','transfer_directory','socket_directory','review_directory'): setup.add_argument(name,type=Path)
    show = sub.add_parser('preview'); show.add_argument('manifest',type=Path)
    execute = sub.add_parser('exec'); execute.add_argument('manifest',type=Path); execute.add_argument('--confirm-hash',required=True)
    check = sub.add_parser('inspect'); check.add_argument('manifest',type=Path); check.add_argument('evidence_directory',type=Path)
    saved = sub.add_parser('status'); saved.add_argument('manifest',type=Path)
    args = parser.parse_args()
    from .workspaces import Registry
    try:
        if args.operation == 'status':
            print(canonical(status(args.manifest))); return
        registry = Registry(args.platform); ledger = registry.ledger(args.workspace)
        if args.operation == 'prepare':
            value = prepare(registry,ledger,args.previous_attempt,args.transfer_directory,args.socket_directory,args.review_directory)
        elif args.operation == 'preview': value = preview(registry,ledger,args.manifest)
        elif args.operation == 'inspect': value = inspect(registry,ledger,args.manifest,args.evidence_directory)
        else: exec_host(registry,ledger,args.manifest,args.confirm_hash); return
        print(canonical(value))
    except (Refusal,OSError,KeyError,ValueError,TypeError) as error:
        parser.exit(1,'Existing-home restart refused: '+(str(error) if isinstance(error,Refusal) else 'private state unavailable')+'\n')


if __name__ == '__main__': main()
