"""Exact one-shot loading of an empty pre-Play public brain, never a turn.

Preparation is read-only apart from its private review. An application claims
permanent ledger/brain ownership before its one fixed metadata-only resume.
Old readiness outcomes and all database rows remain untouched.
"""
import argparse
import contextlib
import hashlib
import os
from pathlib import Path
import sqlite3
import time
import uuid

from . import partial_admission as partial, public_host_restart as restart
from . import public_preplay_host_restart as fresh, public_pilot_inspection as inspection
from .app_server_wake import load_binding
from .core import Refusal, canonical, digest, require
from .host_lifecycle import sync_directory
from .native_read_client import inspect_endpoint
from .native_subscription import SubscriptionOwner, duration
from .public_host_lifecycle import directory_identity, isolated_directory

KIND = 'public_preplay_inspection_load_v1'
PREFIX = 'public-preplay-load-'
FIELDS = {'version','kind','reviewDirectory','sourceTree','restartPath','bindingPath',
          'provenance','before','fencePath','subscription'}
BOUNDARY = {'nativeTurns':0,'readinessRequested':False,'readinessPlayRecoveryReplayed':False,
            'bindingChanged':False,'usageReset':False,'requestsChanged':False,
            'controllerAcquired':False,'ownershipReleased':False,'policyBackfilled':False,
            'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown','pilotAccepted':False}
record = inspection.record
exclusive = inspection.exclusive


def fence_path(ledger, brain):
    # Not keyed by endpoint, source, review directory, mission, request or clock.
    # A replacement host or a second preview cannot mint a second allowance.
    identity = partial.database_proof(ledger.db)['identity']
    return ledger.root/(PREFIX+digest({'workspaceId':ledger.workspace_id,'brainId':brain,
                                     'ledgerIdentity':identity})+'.claim')


def review_hash(spec):
    return digest({'kind':KIND,'action':'one_metadata_only_load','specHash':digest(spec)})


def fence_record(spec):
    return {'kind':KIND,'specHash':digest(spec),'reviewHash':review_hash(spec),
            'reviewDirectory':spec['reviewDirectory']}


def provenance(registry, ledger, restart_path, binding_path, *, claimed=None):
    """Independently validate the issued fresh-host journal, never old code/RPC."""
    spec = record(restart_path)
    require(isinstance(spec,dict) and set(spec) == fresh.FIELDS and type(spec['version']) is int and
            spec['version'] == 1 and spec['kind'] == fresh.KIND and
            Path(restart_path) == Path(spec['reviewDirectory'])/'restart.json' and
            isinstance(spec['sourceTree'],str) and len(spec['sourceTree']) == 40 and
            all(c in '0123456789abcdef' for c in spec['sourceTree']), 'Exact issued pre-Play restart required')
    directory = isolated_directory(spec['reviewDirectory'])
    launch, previous, earlier, scope = fresh.inputs(registry,ledger,spec['previousAttempt'],spec['bindingFile'])
    brain = scope['brainId']; fence = fence_path(ledger,brain)
    claims = [p for p in ledger.root.iterdir() if p.name.startswith(PREFIX)]
    if claimed is None:
        require(not claims,'Pre-Play load already claimed or ambiguous; never load again')
    else:
        require(claims == [fence] and str(fence) == claimed['fencePath'] and
                record(fence) == fence_record(claimed), 'Exact original load claim required')
        sidecars = scope['sidecars']
        require(sidecars.pop(fence.name,None) == restart.pin(fence), 'Original load fence changed')
    require((launch,earlier,scope,restart.pin(spec['bindingFile'])) ==
            (spec['launchSpec'],spec['previousPins'],spec['scope'],spec['bindingPin']),
            'Original requests, disposition, mission, usage, identities or claims changed')
    attempt = directory/'attempt'
    intent, state = record(attempt/'intent.json'), record(attempt/'status.json')
    require(intent.get('kind') == state.get('kind') == fresh.KIND and
            intent.get('specHash') == state.get('specHash') == digest(spec) and
            intent.get('reviewHash') == fresh.review_hash(spec) and state.get('status') == 'exec_boundary_issued' and
            restart.pin(attempt/'exec.claim')['bytes'] == 0, 'Issued same-attempt launch provenance required')
    launch_fence = fresh.fence_path(ledger,launch,previous)
    require(str(launch_fence) == spec['fencePath'] and record(launch_fence) ==
            {'kind':fresh.KIND,'specHash':digest(spec),'reviewDirectory':str(directory)}, 'Original launch fence differs')
    for _ in range(2):
        require(restart.process_absent(previous['pid']), 'Original PID absence is unverified')
        restart.live_process(spec,state)
    require(spec['backupPath'] == str(directory/'native-home-backup') and
            spec['homeSnapshotPin']['path'] == str(directory/'home-snapshot.json') and
            restart.pin(spec['homeSnapshotPin']['path'],1_000_000) == spec['homeSnapshotPin'], 'Original archive changed')
    snapshot = record(spec['homeSnapshotPin']['path'],1_000_000)
    restart.backup_check(spec,snapshot)
    config = restart.restricted_config(launch['codexHome'],launch['cwd'])
    # Do not enumerate the native home or open credentials/native SQL. Preserve
    # only the already pinned initial history/installation prefixes and config.
    for relative,pin in snapshot['files'].items():
        if relative.startswith('sessions/') or relative == 'installation_id':
            raw,_ = restart.read_file(Path(launch['codexHome'])/relative)
            require(len(raw) >= pin['bytes'] and hashlib.sha256(raw[:pin['bytes']]).hexdigest() == pin['sha256'],
                    'Original history prefix or installation identity changed')
    binding = load_binding(binding_path); original = record(spec['bindingFile'])
    require(binding['brains'] == original['brains'] and set(binding['brains']) == {brain},
            'The exact reviewed brain, dual project IDs, backend and policy must remain unchanged')
    sockets = isolated_directory(spec['socketDirectory'])
    require(directory_identity(sockets) == spec['socketDirectoryIdentity'], 'Reviewed socket directory changed')
    alias = sockets/'host.sock'
    require(alias.lstat().st_uid == os.getuid(), 'Socket rendezvous owner changed')
    actual = inspect_endpoint(str(Path(launch['runtimePackage']['root'])/'bin/codex'),
                             str(alias.resolve(strict=True)),original['endpoint']['serverIdentityHash'])
    require(binding['endpoint'] == actual and actual['socket'] != original['endpoint']['socket'] and
            actual['socketIdentity'] != original['endpoint']['socketIdentity'], 'Exact reviewed new host socket required')
    # Verify actual socket ownership, not just a same-binary process elsewhere.
    owners = restart.fixed(['/usr/sbin/lsof','-nP','-a','-p',str(state['pid']),'-U','-Fn'])
    require(owners.returncode == 0 and 'n'+actual['socket'] in owners.stdout.decode().splitlines(),
            'Exact native process must own the reviewed socket')
    commands = _commands(ledger)
    ended_receipts(ledger,commands,scope)
    times = {c['id']:c['createdAt'] for c in commands}
    require(all(type(t) in (int,float) and 0 < t < float('inf') for t in times.values()) and
            len(set(times.values())) == len(times),'Unambiguous original request ordering required')
    latest = max(scope['turns'],key=lambda t:times[t['commandId']])
    pins = [restart.pin(p) for p in (Path(restart_path),attempt/'intent.json',attempt/'status.json',
            attempt/'exec.claim',launch_fence,Path(binding_path))]
    return {'restartHash':digest(spec),'pins':pins,'scope':scope,'config':config,'host':state,
            'binding':binding,'home':launch['codexHome'],'cwd':launch['cwd'],'brainId':brain,
            'projectId':binding['brains'][brain]['projectId'],
            'catalogProjectId':binding['brains'][brain].get('catalogProjectId',binding['brains'][brain]['projectId']),
            'latestTurnId':latest['turnId'],'latestTurnStatus':latest['status']}


def _commands(ledger):
    from .standard import read_db
    with read_db(ledger.db) as db: return ledger.all(db,'commands')


def ended_receipts(ledger, commands, scope):
    """A failed command alone is not an original designated-brain receipt."""
    from .readiness_disposition import retired_in
    from .standard import read_db
    from .standard_preplay import path, BOUNDARY as RECEIPT_BOUNDARY, TRANSPORT
    with read_db(ledger.db) as db:
        for command in commands:
            if retired_in(ledger,db,command['id']): continue
            cid = command['id']; note = command['notification']; saved = command.get('preplayReceipt')
            require(command['status'] == 'failed' and command.get('catalogError') ==
                    {'code':'native_schema_unavailable','retryable':False} and
                    isinstance(saved,dict) and set(saved) == {'requestHash','handoffHash','brainId','nativeTurnId','bindingHash'},
                    'Exact original failed public schema receipt or real canceled disposition required')
            handoff = record(path(ledger.root,cid,'handoff')); request = record(path(ledger.root,cid,'request'))
            claim = record(path(ledger.root,cid,'claim')); reply = record(path(ledger.root,cid,'reply'))
            require(handoff['version'] == 1 and handoff['transport'] == TRANSPORT and
                    handoff['brainId'] == scope['brainId'] and handoff['workspaceId'] == ledger.workspace_id and
                    handoff['commandId'] == cid and handoff['bindingHash'] == scope['bindingHash'] and
                    handoff['missionHash'] == command['payload']['missionHash'] and
                    handoff['contextHash'] == command['payload']['contextHash'] and
                    handoff['ledgerIdentity'] == dict(zip(('device','inode'),scope['identity']['ledgerIdentity'])) and
                    handoff['boundary'] == RECEIPT_BOUNDARY and
                    note['preplayCatalog'] == {'version':1,'transport':TRANSPORT,'handoffHash':digest(handoff)} and
                    saved == {'requestHash':digest(request),'handoffHash':digest(handoff),'brainId':scope['brainId'],
                              'nativeTurnId':note['nativeTurnId'],'bindingHash':scope['bindingHash']} and
                    set(request) == {'version','handoffHash','result'} and request['version'] == 1 and
                    request['handoffHash'] == digest(handoff) and
                    request['result'] == {'operation':'catalog_error','requestId':cid,'code':'native_schema_unavailable',
                                         'detail':command['result'],'retryable':False} and
                    claim == {'requestHash':digest(request)} and
                    reply == {'requestHash':digest(request),'status':'completed','boundary':RECEIPT_BOUNDARY},
                    'Original receipt/observer mailbox correlation changed; never manufacture or backfill it')


def prepare(registry, ledger, restart_path, binding_path, directory, *, subscription_seconds=300):
    duration(subscription_seconds)
    tree = restart.source_tree()
    scope = provenance(registry,ledger,restart_path,binding_path)
    directory = Path(directory); isolated_directory(directory.parent)
    original = record(restart_path)
    roots = [ledger.root,Path(scope['cwd']),Path(scope['home']),Path(original['reviewDirectory']),
             Path(original['previousAttempt']),Path(original['socketDirectory']),
             Path(original['launchSpec']['runtimePackage']['root']),registry.root]
    # A preparation folder may live below the registry's sibling preparation
    # root, but never inside any operational/native root or its ancestor.
    require(directory.is_absolute() and directory.parent.resolve(strict=True) == directory.parent and
            not os.path.lexists(directory) and all(not directory.is_relative_to(p) and
            not p.is_relative_to(directory) for p in roots), 'New private disjoint load review directory required')
    with inspection.InspectionProxy(scope) as proxy: before = inspection.repeated(proxy,scope)
    require(before['activity'] == 'notLoaded' and before['policy'] is None and before['trackedTerminals'] is None,
            'This profile is only for an unloaded pre-Play brain; never adopt or reload an idle/active brain')
    require(provenance(registry,ledger,restart_path,binding_path) == scope and restart.source_tree() == tree,
            'Scope changed during preparation')
    spec = {'version':1,'kind':KIND,'reviewDirectory':str(directory),'sourceTree':tree,
            'restartPath':str(restart_path),'bindingPath':str(binding_path),'provenance':scope,'before':before,
            'fencePath':str(fence_path(ledger,scope['brainId'])),
            'subscription':{'protocol':'foreground_connection_v1','maximumSeconds':subscription_seconds}}
    require(len(canonical(spec).encode()) <= 60000,'Exact review exceeds bounded private record')
    directory.mkdir(mode=0o700); sync_directory(directory.parent)
    exclusive(directory/'load.json',spec)
    return preview(registry,ledger,directory/'load.json')


def load_spec(path):
    spec = record(path)
    require(isinstance(spec,dict) and set(spec) == FIELDS and type(spec['version']) is int and
            spec['version'] == 1 and spec['kind'] == KIND and
            Path(path) == Path(spec['reviewDirectory'])/'load.json' and
            isinstance(spec['subscription'],dict) and set(spec['subscription']) == {'protocol','maximumSeconds'} and
            spec['subscription']['protocol'] == 'foreground_connection_v1' and spec['before']['activity'] == 'notLoaded',
            'Closed exact pre-Play load review required')
    duration(spec['subscription']['maximumSeconds']); isolated_directory(spec['reviewDirectory'])
    return spec


def validate(registry, ledger, path, *, claimed=False):
    spec = load_spec(path)
    require(restart.source_tree() == spec['sourceTree'],'Load implementation changed')
    scope = provenance(registry,ledger,spec['restartPath'],spec['bindingPath'],claimed=spec if claimed else None)
    require(scope == spec['provenance'] and str(fence_path(ledger,scope['brainId'])) == spec['fencePath'],
            'Reviewed source, registry, request, binding or native process changed')
    attempt = Path(spec['reviewDirectory'])/'attempt'
    if claimed:
        require(record(attempt/'intent.json') == fence_record(spec) and
                record(attempt/'load.claim') == {'specHash':digest(spec)}, 'Original permanent load claim required')
    else:
        require(not os.path.lexists(attempt),'Attempt already exists; never load again')
    return spec


def preview(registry, ledger, path):
    spec = validate(registry,ledger,path)
    with inspection.InspectionProxy(spec['provenance']) as proxy:
        require(inspection.repeated(proxy,spec['provenance']) == spec['before'],'Native state changed during review')
    require(validate(registry,ledger,path) == spec,'Review scope changed')
    return {'kind':KIND,'reviewHash':review_hash(spec),'validity':'until_scope_changes',
            'workspaceId':ledger.workspace_id,'brainId':spec['provenance']['brainId'],
            'maximumLoads':1,'loadsMade':0,'fixedParameters':inspection.load_params(spec['provenance']),
            'subscription':dict(spec['subscription'],automaticReconnect=False,deadlineRenewable=False),
            'boundary':dict(BOUNDARY)}


def backup(registry, ledger, spec):
    """Verified private logical snapshots; not global atomic writer exclusion."""
    from .standard import read_db
    root = Path(spec['reviewDirectory'])/'backup'; root.mkdir(mode=0o700)
    rows = {}
    for name,source in (('registry',registry.db),('ledger',ledger.db)):
        target = root/(name+'.sqlite3')
        os.close(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        with read_db(source) as src, contextlib.closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            require(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok','Private backup integrity failed')
        require(partial.database_proof(target)['fingerprint'] == spec['provenance']['scope']['databases'][name]['fingerprint'],
                'Backup differs from reviewed database')
        with target.open('rb') as stream: os.fsync(stream.fileno())
        rows[name] = restart.pin(target,partial.MAX_DATABASE)
    paths = {p['path'] for p in spec['provenance']['pins']}
    paths.update(p['path'] for p in spec['provenance']['scope']['sidecars'].values())
    paths.add(str(Path(spec['reviewDirectory'])/'load.json'))
    for number,path in enumerate(sorted(paths)):
        raw,pin = restart.read_file(path,1_000_000)
        target = root/('private-'+str(number)+'.record')
        fd = os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        require(restart.read_file(path,1_000_000)[1] == pin,'Private input changed during backup')
        rows[str(number)] = restart.pin(target,1_000_000)
    exclusive(root/'manifest.json',{'specHash':digest(spec),'files':rows})
    for pin in rows.values(): require(restart.pin(pin['path'],partial.MAX_DATABASE) == pin,'Private backup changed')
    return digest(rows)


def observation(registry, ledger, path, spec, proxy, *, reconciled):
    current = inspection.repeated(proxy,spec['provenance'])
    require(current['activity'] == 'idle' and current['trackedTerminals'] == [],
            'Loaded-idle, actual restricted policy and complete current empty tracker required')
    require(validate(registry,ledger,path,claimed=True) == spec,'Scope changed after load; no readiness or retry')
    attempt = Path(spec['reviewDirectory'])/'attempt'; ack = attempt/'load-ack.json'
    acknowledged = ack.exists()
    if acknowledged: require(record(ack) == {'specHash':digest(spec),'acknowledged':True},'Load acknowledgment changed')
    result = {'kind':KIND,'specHash':digest(spec),'observedAt':time.time(),'status':'current_policy_observed',
              'loadDelivery':'acknowledged' if acknowledged else 'unknown','reconciledReadOnly':reconciled,
              'observation':current,'boundary':dict(BOUNDARY)}
    exclusive(attempt/('observation-'+str(uuid.uuid4())+'.json'),result)
    return result


def apply(registry, ledger, path, confirm_hash):
    spec = validate(registry,ledger,path)
    require(confirm_hash == review_hash(spec),'Exact new pre-Play load approval required')
    require(not os.path.lexists(Path(spec['reviewDirectory'])/'backup'),'Partial backup exists; retain it, never reapply')
    backup_hash = backup(registry,ledger,spec)
    require(validate(registry,ledger,path) == spec,'Scope changed during backup')
    owner = None; completed = False
    try:
        with inspection.InspectionProxy(spec['provenance']) as proxy:
            require(inspection.repeated(proxy,spec['provenance']) == spec['before'],'Native state changed before claim')
            require(validate(registry,ledger,path) == spec,'Scope changed before permanent claim')
            # Canonical claim first: even partial intent persistence must fence
            # another review directory before there can be any native effect.
            exclusive(Path(spec['fencePath']),fence_record(spec))
            attempt = Path(spec['reviewDirectory'])/'attempt'; attempt.mkdir(mode=0o700); sync_directory(attempt.parent)
            exclusive(attempt/'intent.json',fence_record(spec))
            exclusive(attempt/'load.claim',{'specHash':digest(spec)})
            require(validate(registry,ledger,path,claimed=True) == spec,'Claimed scope changed; no retry')
            require(inspection.repeated(proxy,spec['provenance']) == spec['before'],'Native state changed after claim')
            owner = SubscriptionOwner(proxy,spec['subscription']['maximumSeconds'],digest(spec))
            proxy.subscription_owner = owner; proxy.query_limit = 2048
            exclusive(attempt/'subscription-open.json',owner.record())
            require(validate(registry,ledger,path,claimed=True) == spec,'Scope changed at load boundary; no retry')
            proxy.load_permitted = True
            load_once(proxy,spec['provenance'])
            exclusive(attempt/'load-ack.json',{'specHash':digest(spec),'acknowledged':True})
            result = observation(registry,ledger,path,spec,proxy,reconciled=False)
            # Explicit foreground ownership only. No timer/config change,
            # keepalive turn, new readiness, reconnect or detached worker.
            def check():
                nonlocal result
                result = observation(registry,ledger,path,spec,proxy,reconciled=False)
            owner.hold(check)
            require(validate(registry,ledger,path,claimed=True) == spec,'Scope changed at release')
        completed = True
    finally:
        if owner is not None:
            exclusive(Path(spec['reviewDirectory'])/'attempt/subscription-close.json',
                {'specHash':digest(spec),'connectionId':owner.connection_id,'closedAt':time.time(),
                 'status':'window_completed' if completed else 'interrupted_or_failed',
                 'connectionClosed':owner.proxy.process is None,'currentEvidence':'unknown_after_release',
                 'reconnectAllowed':False,'terminalSafety':'unknown'})
    return dict(result,backupHash=backup_hash,subscription={'status':'window_completed',
        'connectionClosed':True,'currentEvidence':'unknown_after_release','reconnectAllowed':False})


def load_once(proxy, scope):
    """Fixed native boundary, also exercised against the disposable compiled CLI."""
    reply = proxy._rpc('thread/resume',inspection.load_params(scope))
    thread = reply.get('thread') if isinstance(reply,dict) else None
    require(isinstance(thread,dict) and thread.get('id') == scope['brainId'] and
            thread.get('projectId') == scope['projectId'] and thread.get('cwd') == scope['cwd'] and
            thread.get('turns',[]) == [],'Exact metadata-only load acknowledgment required; never retry')


def reconcile(registry, ledger, path):
    spec = validate(registry,ledger,path,claimed=True)
    with inspection.InspectionProxy(spec['provenance']) as proxy:
        return observation(registry,ledger,path,spec,proxy,reconciled=True)


def status(path):
    """Historical files only; never treat a PID/time as an active subscription."""
    spec = load_spec(path); attempt = Path(spec['reviewDirectory'])/'attempt'
    claimed = os.path.lexists(attempt) or os.path.lexists(spec['fencePath'])
    if os.path.lexists(spec['fencePath']):
        require(record(spec['fencePath']) == fence_record(spec),'Saved canonical claim differs')
    if (attempt/'intent.json').exists():
        require(record(attempt/'intent.json') == fence_record(spec),'Saved intent differs')
    closed = attempt/'subscription-close.json'
    subscription = 'unknown_not_reconnectable' if (attempt/'subscription-open.json').exists() else 'not_started'
    if closed.exists():
        row = record(closed); opened = record(attempt/'subscription-open.json')
        require(set(row) == {'specHash','connectionId','closedAt','status','connectionClosed','currentEvidence',
                            'reconnectAllowed','terminalSafety'} and
                row['specHash'] == opened['specHash'] == digest(spec) and row['connectionId'] == opened['connectionId'] and
                row['status'] in {'window_completed','interrupted_or_failed'} and row['reconnectAllowed'] is False and
                type(row['connectionClosed']) is bool and
                (row['status'] != 'window_completed' or row['connectionClosed'] is True) and
                row['currentEvidence'] == 'unknown_after_release' and row['terminalSafety'] == 'unknown',
                'Original subscription close record changed')
        subscription = row['status']
    acknowledged = (attempt/'load-ack.json').exists()
    if acknowledged:
        require(record(attempt/'load-ack.json') == {'specHash':digest(spec),'acknowledged':True},'Saved load acknowledgment differs')
    return {'kind':KIND,'reviewHash':review_hash(spec),'historical':True,'claimRetained':claimed,
            'status':'consumed_outcome_not_inferred' if claimed else 'prepared_not_submitted',
            'subscription':subscription,'loadAcknowledged':acknowledged,
            'boundary':dict(BOUNDARY)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform',type=Path,required=True); parser.add_argument('--workspace',required=True)
    sub = parser.add_subparsers(dest='operation',required=True)
    setup = sub.add_parser('prepare')
    for name in ('restart_manifest','binding','review_directory'): setup.add_argument(name,type=Path)
    setup.add_argument('--subscription-seconds',type=int,default=300)
    for name in ('preview','apply','reconcile','status'):
        item = sub.add_parser(name); item.add_argument('manifest',type=Path)
        if name == 'apply': item.add_argument('--confirm-hash',required=True)
    args = parser.parse_args()
    try:
        if args.operation == 'status': value = status(args.manifest)
        else:
            registry,ledger = partial.routes(args.platform,args.workspace)
            if args.operation == 'prepare': value = prepare(registry,ledger,args.restart_manifest,args.binding,args.review_directory,
                                                          subscription_seconds=args.subscription_seconds)
            elif args.operation == 'preview': value = preview(registry,ledger,args.manifest)
            elif args.operation == 'apply': value = apply(registry,ledger,args.manifest,args.confirm_hash)
            else: value = reconcile(registry,ledger,args.manifest)
        print(canonical(value))
    except (Refusal,OSError,KeyError,ValueError,TypeError,sqlite3.Error) as error:
        parser.exit(1,'Pre-Play load refused: '+(str(error) if isinstance(error,Refusal) else 'private state unavailable')+'\n')


if __name__ == '__main__': main()
