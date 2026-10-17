"""Launch-only repair of an exited, signed-in fresh public pre-Play host.

No transfer, admission, brain load, native turn, binding change or retry. The
older transferred-run and initial empty-home launch contracts stay unchanged.
"""
import argparse
import os
from pathlib import Path
import platform
import sys
import time

from . import missions, partial_admission as partial, public_host_restart as restart, standard
from .app_server_wake import _read_binding, NATIVE_APPROVAL_POLICY
from .core import Refusal, canonical, digest, require
from .host_lifecycle import private_file, sync_directory, write_record
from .public_host_lifecycle import POLICY, directory_identity, environment, isolated_directory
from .native_read_client import decode

KIND = 'public_preplay_home_restart_v1'
SUCCESSOR_KIND = 'public_preplay_successor_restart_v1'
PREFIX = 'public-preplay-host-restart-'
FIELDS = {'version','kind','previousAttempt','previousPins','launchSpec','bindingFile','bindingPin',
          'scope','homeSnapshotPin','backupPath','socketDirectory','socketDirectoryIdentity',
          'reviewDirectory','sourceTree','fencePath'}
BOUNDARY = {'brainLoaded':False,'turnStarted':False,'bindingInstalled':False,'requestReplayed':False,
            'usageReset':False,'credentialBytesRead':False,'credentialsCopied':False,
            'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown','pilotAccepted':False}


def sidecars(ledger):
    """Pin existing private IPC/claims; no transcript/credential projection."""
    found = {}
    for parent, dirs, files in os.walk(ledger.root, followlinks=False):
        require(len(found)+len(dirs)+len(files) <= 512, 'Private sidecar inventory exceeds bound')
        for name in dirs:
            path = Path(parent)/name
            isolated_directory(path)
            require(len(path.relative_to(ledger.root).parts) <= 8, 'Sidecar depth exceeds bound')
        for name in files:
            path = Path(parent)/name
            if path.parent == ledger.root and (name in {'ledger.sqlite3','ledger.sqlite3-wal','ledger.sqlite3-shm','dashboard.lock'} or
                                              name.startswith(PREFIX)):
                continue
            found[str(path.relative_to(ledger.root))] = restart.pin(path,1_000_000)
            require(len(found) <= 512, 'Private sidecar inventory exceeds bound')
    return found


def protected(registry, ledger, binding_file, launch):
    from .brain_control import stopped
    from .enrollment import fence_exists, record_in
    from .native_project_assignment import _read_registry
    from .public_native_tasks import validate_contract
    from .readiness_disposition import binding_scope, retired_in
    with _read_registry(registry) as db:
        require(record_in(db) is None, 'Strict enrollment cannot use pre-Play restart')
    binding_file = private_file(binding_file)
    binding_pin = restart.pin(binding_file)
    binding = _read_binding(binding_file)
    identity = binding_scope(registry,ledger,binding)
    with standard.read_db(ledger.db) as db:
        meta = ledger.get(db,'meta',1)
        require(meta.get('schemaVersion') == 1 and meta.get('paused') is True and
                meta.get('standardRun') is None and meta.get('controller') is None and meta.get('runner') is None and
                not meta.get('admissionBinding') and not meta.get('brainHandoff') and not stopped(meta) and
                not fence_exists(ledger.root) and not os.path.lexists(standard.controller_file(ledger)),
                'Only an empty unowned paused first-phase standard project qualifies')
        require(not any(meta.get(k) for k in ('standardSuccessor','standardQuarantine','forwardContinuationVersion','successorLedgerVersion')) and
                not any(os.path.lexists(ledger.root/name) for name in ('standard-successor.json','standard-forward-continuation.json',
                        'standard-partial-admission-disposition.json','standard-quarantine.json')),
                'Existing admission, successor or quarantine ownership is outside this repair')
        require(all(not ledger.all(db,t) for t in ('workers','queue','decisions','continuations')),
                'Task, packet or decision ownership fences restart')
        repos = ledger.all(db,'repos')
        require(repos and all(r['policyProfile'] == 'standard' and r['path'] == launch['cwd'] for r in repos),
                'Only this exact all-standard checkout qualifies')
        mission = missions.state_in(ledger,db)
        require(mission['effectiveStatus'] == 'reviewed' and
                mission['document']['spec']['authority']['approvalMode'] == 'phase_delegated',
                'An unchanged reviewed first-phase mission is required')
        commands = ledger.all(db,'commands')
        require(0 < len(commands) <= 16, 'Bounded retained ended readiness requests required')
        turns = []
        for command in commands:
            n = command.get('notification') or {}; observer = n.get('nativeThreadObservation') or {}
            profile = n.get('nativeResumeProfile') or {}
            require(command.get('kind') == standard.CATALOG_REFRESH_KIND and
                    command.get('payload',{}).get('brainId') == meta['brainId'] and
                    command.get('payload',{}).get('missionHash') == mission['documentHash'] and
                    not command.get('notificationHistory') and n.get('status') == 'accepted' and
                    n.get('nativeDelivery') == 'owned_turn_start' and n.get('brainId') == meta['brainId'] and
                    profile.get('bindingHash') == digest(binding) and profile.get('requested') in (POLICY,NATIVE_APPROVAL_POLICY) and
                    profile.get('resumeAcknowledged') is True and profile.get('brainId') == meta['brainId'] and
                    profile.get('commandId') == command['id'] and profile.get('nativeTurnId') == n.get('nativeTurnId') and
                    observer.get('rootThreadId') == meta['brainId'] and
                    observer.get('nativeTurnId') == n.get('nativeTurnId') and observer.get('streamStatus') == 'closed' and
                    n.get('nativeTurnStatus') in {'completed','interrupted','failed'} and
                    all(a.get('status') in {'resolved','resolved_without_response'} for a in n.get('nativeApprovals',[])),
                    'Every original readiness turn must be ended on this unchanged restricted binding')
            require(command.get('status') in {'completed','failed'} or retired_in(ledger,db,command['id']),
                    'Unreceived readiness needs its separate retained disposition, never inferred receipt')
            from .native_project_assignment import UUID
            require(isinstance(n.get('nativeTurnId'),str) and UUID.fullmatch(n['nativeTurnId']), 'Exact ended turn ID required')
            turns.append({'commandId':command['id'],'turnId':n['nativeTurnId'],'status':n['nativeTurnStatus']})
    brain = binding['brains'][meta['brainId']]
    require(brain['nativePolicy'] in (POLICY,NATIVE_APPROVAL_POLICY) and identity['checkout'] == launch['cwd'] and
            binding['endpoint']['executable'] == str(Path(launch['runtimePackage']['root'])/'bin/codex') and
            binding['endpoint']['sha256'] == launch['runtimePackage']['executableHash'],
            'Exact reviewed host executable/checkout/policy required; old endpoint is historical only')
    native = validate_contract(brain.get('nativeTaskBackend'),brain.get('policyEvidence'))
    require(all(native[k] == launch['runtimePackage'][k] for k in ('sourceCommit','sourceTree')),
            'Native task and policy build differ from the original runtime package')
    require(restart.pin(binding_file) == binding_pin, 'Binding changed during local reads')
    return {'workspaceId':ledger.workspace_id,'brainId':meta['brainId'],'identity':identity,
            'bindingHash':digest(binding),'missionHash':mission['documentHash'],'turns':turns,
            'databases':{'registry':partial.database_proof(registry.db),'ledger':partial.database_proof(ledger.db)},
            'sidecars':sidecars(ledger)}


def inputs(registry, ledger, previous, binding_file, *, successor=False):
    if successor:
        from .public_preplay_host_lineage import inputs as successor_inputs
        return successor_inputs(registry,ledger,previous,binding_file)
    # Do not coerce a transferred-run restart into this fresh-home profile.
    require((Path(previous)/'launch.json').is_file(), 'Exact initial fresh public host launch is required')
    launch, old, pins = restart.original_launch(previous,ledger)
    return launch,old,pins,protected(registry,ledger,binding_file,launch)


def fence_path(ledger, launch, old, *, successor=False):
    if successor:
        require(isinstance(old.get('processIdentity'),str) and old.get('specHash'), 'Issued successor process epoch required')
        key = digest({'kind':SUCCESSOR_KIND,'launchSpec':launch,'homeIdentity':launch['homeIdentity'],
            'previousPid':old['pid'],'previousEpoch':old['processIdentity'],'previousSpecHash':old['specHash']})
        return ledger.root/(PREFIX+key+'.json')
    key = digest({'kind':KIND,'launchSpec':launch,'homeIdentity':launch['homeIdentity'],
                  'previousPid':old['pid'],'previousEpoch':old['observedAt']})
    return ledger.root/(PREFIX+key+'.json')


def paths(spec):
    launch = spec['launchSpec']; directory = Path(spec['reviewDirectory'])
    roots = [Path(launch[k]) for k in ('cwd','codexHome')] + [Path(launch['runtimePackage']['root']),Path(spec['previousAttempt'])]
    sockets = isolated_directory(spec['socketDirectory'])
    require(sockets != Path(launch['socketDirectory']) and len(os.fsencode(str(sockets/'host.sock'))) <= 100 and
            directory.is_absolute() and directory.parent.resolve(strict=True) == directory.parent and
            not directory.is_relative_to(sockets) and not sockets.is_relative_to(directory) and
            all(not p.is_relative_to(q) and not q.is_relative_to(p) for p in (directory,sockets) for q in roots),
            'New socket/review paths must be private, bounded and disjoint from original state')
    require(spec['backupPath'] == str(directory/'native-home-backup') and
            spec['homeSnapshotPin']['path'] == str(directory/'home-snapshot.json'), 'Closed backup locations required')
    if spec['version'] == 2:
        old = [Path(p) for p in spec['scope']['retiredSocketDirectories']+spec['scope']['predecessorReviewDirectories']]
        require(all(not p.is_relative_to(q) and not q.is_relative_to(p) for p in (directory,sockets) for q in old),
                'Successor sockets/review must be disjoint from every predecessor')


def prepare(registry, ledger, previous, binding_file, sockets, directory, *, successor=False):
    launch,old,pins,scope = values = inputs(registry,ledger,previous,binding_file,successor=successor)
    fence = fence_path(ledger,launch,old,successor=successor)
    require(not os.path.lexists(fence), 'This predecessor restart is consumed; never resend')
    sockets = isolated_directory(sockets); directory = Path(directory)
    isolated_directory(directory.parent)
    require(not list(sockets.iterdir()), 'New empty socket directory required')
    tree = restart.source_tree()
    # Check boundaries before creating/copying any source data.
    spec = {'version':2 if successor else 1,'kind':SUCCESSOR_KIND if successor else KIND,'previousAttempt':str(previous),'previousPins':pins,'launchSpec':launch,
            'bindingFile':str(binding_file),'bindingPin':restart.pin(binding_file),'scope':scope,
            'homeSnapshotPin':{'path':str(directory/'home-snapshot.json')},'backupPath':str(directory/'native-home-backup'),
            'socketDirectory':str(sockets),'socketDirectoryIdentity':directory_identity(sockets),
            'reviewDirectory':str(directory),'sourceTree':tree,'fencePath':str(fence)}
    paths(spec)
    for _ in range(2): restart.quiescent(launch,old)
    binary = str(Path(launch['runtimePackage']['root'])/'bin/codex')
    snapshot = restart.signed_in_preplay_snapshot(launch['codexHome'],binary,brain=scope['brainId'])
    directory.mkdir(mode=0o700); sync_directory(directory.parent)
    backup = directory/'native-home-backup'; backup.mkdir(mode=0o700)
    require(snapshot == restart.signed_in_preplay_snapshot(launch['codexHome'],binary,backup,brain=scope['brainId']),
            'Native home changed during opaque backup; retain the partial preparation')
    write_record(directory/'home-snapshot.json',snapshot)
    spec['homeSnapshotPin'] = restart.pin(directory/'home-snapshot.json',1_000_000)
    restart.backup_check(spec,snapshot)
    require(values == inputs(registry,ledger,previous,binding_file,successor=successor), 'Protected scope changed during preparation')
    write_record(directory/'restart.json',spec)
    return preview(registry,ledger,directory/'restart.json')


def load_spec(path):
    spec = decode(restart.read_file(private_file(path),65536)[0])
    require(isinstance(spec,dict) and set(spec) == FIELDS and type(spec['version']) is int and
            ((spec['version'] == 1 and spec['kind'] == KIND) or
             (spec['version'] == 2 and spec['kind'] == SUCCESSOR_KIND)) and
            Path(path) == Path(spec['reviewDirectory'])/'restart.json' and spec['sourceTree'] == restart.source_tree(),
            'Exact closed clean-source pre-Play restart manifest required')
    isolated_directory(spec['reviewDirectory']); paths(spec)
    return spec


def review_hash(spec): return digest({'kind':spec['kind'],'mode':'exec','specHash':digest(spec)})


def validate(registry, ledger, path, *, claimed=False):
    spec = load_spec(path)
    successor = spec['version'] == 2
    launch,old,pins,scope = inputs(registry,ledger,spec['previousAttempt'],spec['bindingFile'],successor=successor)
    require((launch,pins,scope,restart.pin(spec['bindingFile'])) ==
            (spec['launchSpec'],spec['previousPins'],spec['scope'],spec['bindingPin']), 'Reviewed scope changed')
    fence = fence_path(ledger,launch,old,successor=successor)
    require(str(fence) == spec['fencePath'], 'Canonical predecessor restart fence differs')
    expected = {'kind':spec['kind'],'specHash':digest(spec),'reviewDirectory':spec['reviewDirectory']}
    if claimed: require(decode(restart.read_file(private_file(fence),65536)[0]) == expected, 'Claimed restart fence differs')
    else: require(not os.path.lexists(fence), 'Restart is consumed; inspection only, never relaunch')
    sockets = isolated_directory(spec['socketDirectory'])
    require(directory_identity(sockets) == spec['socketDirectoryIdentity'] and not list(sockets.iterdir()), 'New socket directory changed')
    require(restart.pin(spec['homeSnapshotPin']['path'],1_000_000) == spec['homeSnapshotPin'], 'Snapshot changed')
    snapshot = decode(restart.read_file(spec['homeSnapshotPin']['path'],1_000_000)[0])
    for _ in range(2): restart.quiescent(launch,old)
    require(restart.signed_in_preplay_snapshot(launch['codexHome'],str(Path(launch['runtimePackage']['root'])/'bin/codex'),
                brain=scope['brainId']) == snapshot, 'Reviewed home or credential metadata changed')
    restart.backup_check(spec,snapshot)
    return spec


def preview(registry, ledger, path):
    spec = validate(registry,ledger,path)
    return {'kind':spec['kind'],'reviewHash':review_hash(spec),'validity':'until_scope_changes',
            'workspaceId':ledger.workspace_id,'brainId':spec['scope']['brainId'],
            'startsHost':False,'boundary':dict(BOUNDARY)}


def exec_host(registry, ledger, path, confirm_hash):
    spec = validate(registry,ledger,path)
    require(sys.platform == 'darwin' and platform.machine() == 'arm64', 'macOS ARM64 is required')
    require(confirm_hash == review_hash(spec), 'Exact new pre-Play launch review required; consumed approvals cannot be reused')
    attempt = Path(spec['reviewDirectory'])/'attempt'; attempt.mkdir(mode=0o700); sync_directory(attempt.parent)
    write_record(attempt/'intent.json',{'kind':spec['kind'],'specHash':digest(spec),'reviewHash':confirm_hash,'at':time.time()})
    from .standard_quarantine import exclusive
    exclusive(Path(spec['fencePath']),{'kind':spec['kind'],'specHash':digest(spec),'reviewDirectory':spec['reviewDirectory']})
    with os.fdopen(os.open(attempt/'exec.claim',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as stream:
        stream.flush(); os.fsync(stream.fileno())
    sync_directory(attempt)
    require(validate(registry,ledger,path,claimed=True) == spec, 'Scope changed after permanent claim; no retry')
    state = {'kind':spec['kind'],'status':'exec_boundary_issued','pid':os.getpid(),'parentPid':os.getppid(),
             'processIdentity':restart.process_identity(os.getpid()),'at':time.time(),'specHash':digest(spec),
             'boundary':dict(BOUNDARY)}
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
        raise Refusal('Host exec failed; permanent claims remain consumed without fallback') from None


def status(path):
    """Historical file-only read, even after source, scope or host drift."""
    spec = decode(restart.read_file(private_file(path),65536)[0])
    require(isinstance(spec,dict) and set(spec) == FIELDS and type(spec['version']) is int and
            ((spec['version'] == 1 and spec['kind'] == KIND) or
             (spec['version'] == 2 and spec['kind'] == SUCCESSOR_KIND)) and
            Path(path) == Path(spec['reviewDirectory'])/'restart.json', 'Closed restart record required')
    attempt = Path(spec['reviewDirectory'])/'attempt'
    base = {'kind':spec['kind'],'historical':True,'hostReady':False,'boundary':dict(BOUNDARY)}
    if not os.path.lexists(attempt): return {**base,'status':'prepared_not_submitted','claimRetained':False}
    isolated_directory(attempt)
    if not (attempt/'status.json').exists(): return {**base,'status':'outcome_unknown','claimRetained':(attempt/'exec.claim').exists()}
    row = decode(restart.read_file(private_file(attempt/'status.json'),65536)[0])
    require(row.get('kind') == spec['kind'] and row.get('specHash') == digest(spec) and row.get('boundary') == BOUNDARY and
            row.get('status') in {'exec_boundary_issued','exec_failed','exec_outcome_unknown'}, 'Invalid historical restart status')
    return {**base,'status':row['status'],'pid':row['pid'],'processIdentity':row['processIdentity'],
            'claimRetained':(attempt/'exec.claim').exists()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform',type=Path,required=True); parser.add_argument('--workspace',required=True)
    sub = parser.add_subparsers(dest='operation',required=True)
    setup = sub.add_parser('prepare')
    setup.add_argument('--successor',action='store_true',help='Separate exact review of a genuinely exited issued pre-Play restart')
    for name in ('previous_attempt','binding_file','socket_directory','review_directory'): setup.add_argument(name,type=Path)
    for name in ('preview','status','exec'):
        operation = sub.add_parser(name); operation.add_argument('manifest',type=Path)
        if name == 'exec': operation.add_argument('--confirm-hash',required=True)
    args = parser.parse_args()
    try:
        if args.operation == 'status': value = status(args.manifest)
        else:
            registry,ledger = partial.routes(args.platform,args.workspace)
            if args.operation == 'prepare': value = prepare(registry,ledger,args.previous_attempt,args.binding_file,args.socket_directory,args.review_directory,successor=args.successor)
            elif args.operation == 'preview': value = preview(registry,ledger,args.manifest)
            else: exec_host(registry,ledger,args.manifest,args.confirm_hash); return
        print(canonical(value))
    except (Refusal,OSError,KeyError,ValueError,TypeError) as error:
        parser.exit(1,'Pre-Play host repair refused: '+(str(error) if isinstance(error,Refusal) else 'private state unavailable')+'\n')


if __name__ == '__main__': main()
