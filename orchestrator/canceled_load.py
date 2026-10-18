"""Separately reviewed replacement-host load after a canceled, unreceived Play.

One metadata-only load, never a turn, replay, phase Resume or old receipt.
Original ledgers, claims, usage and historical bindings remain immutable.
"""
import argparse
import contextlib
import copy
import hashlib
import os
from pathlib import Path
import sqlite3
import time

from . import canceled_continuation as control, canceled_host_review as host
from . import partial_admission as partial, public_host_restart as shared
from . import public_pilot_inspection as inspection
from .app_server_wake import _read_binding
from .core import Refusal, canonical, digest, require
from .host_lifecycle import private_file, sync_directory
from .host_runtime import stamp
from .native_read_client import decode, inspect_endpoint
from .public_host_lifecycle import directory_identity, isolated_directory
from .public_host_runtime import validate_pin
from .standard_quarantine import exclusive

KIND = 'canceled_play_replacement_load_v1'
BOUNDARY = {'maximumLoads': 1, 'turnStarts': 0, 'playOrRecoveryReplayed': False,
            'bindingInstalled': False, 'usageReset': False, 'oldRunChanged': False,
            'receiptReconstructed': False, 'dispositionApplied': False,
            'dispatchAuthorized': False, 'resumeAuthorized': False,
            'currentTerminalSafety': 'unknown', 'historicalTerminalSafety': 'unknown',
            'pilotAccepted': False}
FIELDS = {'version', 'kind', 'sourceHash', 'provenance', 'candidateFile', 'candidatePin',
          'journal', 'boundary'}


def provenance(registry, ledger, launch_file):
    """File/process validation of an actually issued replacement, no native RPC.

    This path deliberately precedes local disposition: the launch's complete
    original scope must still match. Later disposition cannot rearm this load.
    """
    require(Path(launch_file).name == 'replacement.json', 'Exact replacement review filename required')
    q = host.load(launch_file)
    review = isolated_directory(q['reviewDirectory'])
    require(q['backupPath'] == str(review/'native-home-backup')
            and q['homeSnapshotPin']['path'] == str(review/'home-snapshot.json'), 'Closed reviewed native archive paths required')
    o = q['original']
    require(control.original_context(registry, ledger, o['bindingFile'], o['command']['id']) == o
            and o['dispositionHash'] is None, 'Unchanged undisposed canceled attempt required')
    earlier = host.lineage.issued(q['previousAttempt'], ledger)
    require(earlier[:3] == (q['originalLaunch'], q['previousStatus'], q['previousPins']),
            'Issued original host lineage changed')
    require(q['launchSpec'] == {**q['originalLaunch'], 'runtimePackage': q['launchSpec']['runtimePackage']}
            and q['launchSpec']['runtimePackage']['executableHash'] != q['originalLaunch']['runtimePackage']['executableHash'],
            'Distinct reviewed replacement package required')
    validate_pin(q['launchSpec']['runtimePackage'])
    claim = isolated_directory(q['fencePath'])
    require(str(host.fence(registry, o, q['previousStatus'])) == str(claim)
            and control._read_private(claim/'intent.json') == {'kind': host.KIND, 'reviewHash': host.review_hash(q)}
            and not os.path.lexists(claim/'failed-or-unknown.json'), 'Issued exact replacement launch required')
    issued = control._read_private(claim/'issued.json')
    execution = control._read_private(claim/'exec.claim.json')
    binary = str(Path(q['launchSpec']['runtimePackage']['root'])/'bin/codex')
    argv = [binary, 'app-server', '--listen', 'unix://'+str(Path(q['socketDirectory'])/'host.sock')]
    require(set(issued) == {'kind','status','argv','reviewHash','pid','processIdentity','cwd','boundary'}
            and issued['kind'] == host.KIND and issued['status'] == 'exec_boundary_issued'
            and issued['reviewHash'] == host.review_hash(q) and issued['argv'] == argv
            and issued['cwd'] == q['launchSpec']['cwd'] and issued['boundary'] == host.BOUNDARY
            and set(execution) == {'kind','reviewHash','pid','processIdentity','at'}
            and execution['kind'] == host.KIND and execution['reviewHash'] == issued['reviewHash']
            and all(execution[k] == issued[k] for k in ('pid','processIdentity')),
            'A launch intent or failed exec is not a running replacement')
    for _ in range(2):
        require(shared.process_absent(q['previousStatus']['pid']), 'Original process absence is unknown')
        shared.live_process(q, issued)
    sockets = isolated_directory(q['socketDirectory'])
    require(directory_identity(sockets) == q['socketIdentity'], 'Replacement rendezvous directory changed')
    alias = sockets/'host.sock'
    require(alias.lstat().st_uid == os.getuid(), 'Replacement rendezvous owner changed')
    old_binding = _read_binding(o['bindingFile'])
    endpoint = inspect_endpoint(binary, str(alias.resolve(strict=True)), old_binding['endpoint']['serverIdentityHash'])
    require(endpoint['sha256'] == q['launchSpec']['runtimePackage']['executableHash']
            and endpoint['socket'] != old_binding['endpoint']['socket']
            and endpoint['socketIdentity'] != old_binding['endpoint']['socketIdentity'],
            'New actual socket epoch required; never connect the historical endpoint')
    require(shared.pin(q['homeSnapshotPin']['path'], 1_000_000) == q['homeSnapshotPin'], 'Original native archive changed')
    snapshot = decode(shared.read_file(q['homeSnapshotPin']['path'], 1_000_000)[0])
    require(isinstance(snapshot,dict) and isinstance(snapshot.get('files'),dict)
            and 'auth.json' not in snapshot['files']
            and set(snapshot.get('credentialMetadata',{})) == {'identity','bytesRead','copied'}
            and snapshot['credentialMetadata']['bytesRead'] is False
            and snapshot['credentialMetadata']['copied'] is False, 'Credential metadata-only archive required')
    shared.backup_check(q, snapshot)
    home = Path(q['launchSpec']['codexHome'])
    config = shared.restricted_config(home, q['launchSpec']['cwd'])
    require(list(stamp(private_file(home/'auth.json').lstat())) == snapshot['credentialMetadata']['identity'],
            'Native credential metadata changed; no authentication repair is permitted')
    for relative, record in snapshot['files'].items():
        if relative == 'installation_id' or relative.startswith('sessions/'):
            raw, _ = shared.read_file(home/relative)
            require(len(raw) >= record['bytes'] and hashlib.sha256(raw[:record['bytes']]).hexdigest() == record['sha256'],
                    'Original native history prefix changed')
    candidate = copy.deepcopy(old_binding)
    candidate['endpoint'] = endpoint
    for field in ('policyEvidence', 'nativeTaskBackend'):
        candidate['brains'][o['brainId']][field].update({k: q['launchSpec']['runtimePackage'][k]
                                                       for k in ('sourceCommit','sourceTree')})
    paths = [Path(launch_file), claim/'intent.json', claim/'exec.claim.json', claim/'issued.json',
             Path(q['homeSnapshotPin']['path'])] + [Path(p['path']) for p in q['previousPins']]
    scope = {'binding': candidate, 'brainId': o['brainId'], 'cwd': o['scope']['checkout'],
             'projectId': candidate['brains'][o['brainId']]['projectId'],
             'latestTurnId': o['command']['notification']['nativeTurnId'], 'latestTurnStatus': 'interrupted'}
    return {'original': o, 'launchFile': str(launch_file), 'launchPins': [shared.pin(p) for p in paths], 'home':str(home),
            'scope': scope, 'host': issued, 'config': config,
            'packageEpochs': control.package_epochs(q['launchSpec']['runtimePackage'])}


def location(registry, o):
    key = digest({'ledger': o['databases']['target']['identity'], 'brain': o['brainId'], 'command': o['command']['id']})
    return registry.root/'canceled-brain-loads'/key


def prepare(registry, ledger, launch_file, candidate_file):
    p = provenance(registry, ledger, launch_file)
    candidate_file = Path(candidate_file)
    require(candidate_file.name not in {'auth.json','.credentials.json','.env'}
            and not candidate_file.is_relative_to(Path(p['home'])), 'Candidate is a separate non-credential review file')
    candidate_file = private_file(candidate_file)
    require(_read_binding(candidate_file) == p['scope']['binding'], 'Exact separately pinned candidate required')
    root = location(registry, p['original'])
    require(not os.path.lexists(root) and not os.path.lexists(control.locations(registry,p['original'])[0]),
            'A load or forward control already claimed this original attempt')
    q = {'version': 1, 'kind': KIND, 'sourceHash': control.old.source_hash(), 'provenance': p,
         'candidateFile': str(candidate_file), 'candidatePin': control.pin(candidate_file),
         'journal': str(root), 'boundary': dict(BOUNDARY)}
    require(valid(q), 'Closed replacement-load review exceeds its bound')
    return {'request': q, 'reviewHash': digest(q), 'validUntil': 'scope_changes',
            'effect': 'One metadata-only load of the exact v3 brain; no turn, disposition, Resume or dispatch',
            'boundary': dict(BOUNDARY)}


def valid(q):
    return (isinstance(q,dict) and set(q) == FIELDS and type(q['version']) is int and q['version'] == 1
            and q['kind'] == KIND and q['boundary'] == BOUNDARY and isinstance(q['provenance'],dict)
            and len(canonical(q).encode()) <= 62000)


def read_review(file):
    before = control.pin(file)
    q = decode(private_file(file).read_bytes())
    require(control.pin(file) == before and valid(q), 'Exact private replacement-load review required')
    return q


def current(registry, ledger, q):
    require(valid(q) and q['sourceHash'] == control.old.source_hash(), 'Reviewed load implementation changed')
    p = q['provenance']
    require(provenance(registry,ledger,p['launchFile']) == p, 'Original scope or reviewed runtime changed')
    require(str(location(registry,p['original'])) == q['journal'], 'Canonical load location changed')
    require(control.pin(q['candidateFile']) == q['candidatePin']
            and _read_binding(q['candidateFile']) == p['scope']['binding'], 'Candidate binding bytes/epoch changed')
    require(not os.path.lexists(control.locations(registry,p['original'])[0]), 'A forward control owns this original attempt')
    require(not os.path.lexists(Path(q['journal'])/'stop.json'), 'Owner stop fences the load')


def backup_files(q):
    o = q['provenance']['original']
    return sorted({o['bindingFile'],q['candidateFile']} | {p['path'] for p in q['provenance']['launchPins']}
                  | {str(Path(o['root'])/p) for p in o['sidecars']})


def backup(registry, ledger, q, destination, *, writers_stopped=False):
    require(writers_stopped is True, 'Quiesce older writers before backup')
    current(registry,ledger,q)
    root = Path(destination); control.old.private_path(root.parent,existing=True)
    p = q['provenance']; o = p['original']
    protected = [Path(o['root']),registry.root,Path(p['home']),Path(p['scope']['cwd']),
                 Path(p['launchFile']).parent,Path(p['scope']['binding']['endpoint']['executable']).parent.parent]
    require(root.is_absolute() and root.resolve() == root and not os.path.lexists(root)
            and all(not root.is_relative_to(path) and not path.is_relative_to(root) for path in protected),
            'New disjoint private backup outside protected state required')
    root.mkdir(mode=0o700); records = {}
    for key,file in (('target',ledger.db),('registry',registry.db)):
        target = root/(key+'.sqlite3')
        os.close(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        with control.standard.read_db(file) as original, contextlib.closing(sqlite3.connect(target)) as copy_db:
            original.backup(copy_db)
            require(copy_db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Backup integrity failed')
        require(partial.database_proof(target)['fingerprint'] == q['provenance']['original']['databases'][key]['fingerprint'],
                'Database changed while backing up')
        with target.open('rb') as stream: os.fsync(stream.fileno())
        records[key+'.sqlite3'] = control.old.prior.database_epoch(target)
    for index,file in enumerate(backup_files(q)):
        before = control.archive_pin(file); target = root/('private-'+str(index)+'.bin')
        fd = os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(private_file(file).read_bytes()); stream.flush(); os.fsync(stream.fileno())
        require(control.archive_pin(file) == before and control.archive_pin(target)['sha256'] == before['sha256'],
                'Private record changed during backup')
        records[target.name] = control.archive_pin(target)
    current(registry,ledger,q)
    exclusive(root/'manifest.json', {'kind':KIND,'reviewHash':digest(q),'files':records})
    return {'backup': str(root), 'verified': True, 'reviewHash': digest(q)}


def verify_backup(q, root):
    root = control.old.private_path(root,existing=True)
    manifest = control._read_private(root/'manifest.json')
    names = {'target.sqlite3','registry.sqlite3'} | {'private-'+str(i)+'.bin' for i in range(len(backup_files(q)))}
    require(set(manifest) == {'kind','reviewHash','files'} and manifest['kind'] == KIND
            and manifest['reviewHash'] == digest(q) and set(manifest['files']) == names, 'Complete exact backup required')
    for name, expected in manifest['files'].items():
        actual = control.old.prior.database_epoch(root/name) if name.endswith('.sqlite3') else control.archive_pin(root/name)
        require(actual == expected, 'Backup bytes or epoch changed')
    for key in ('target','registry'):
        proof = partial.database_proof(root/(key+'.sqlite3'))
        require(proof['fingerprint'] == q['provenance']['original']['databases'][key]['fingerprint']
                and proof['identity'] != q['provenance']['original']['databases'][key]['identity'], 'Aliased/changed backup')
    for i,file in enumerate(backup_files(q)):
        require(control.archive_pin(root/('private-'+str(i)+'.bin'))['sha256'] == control.archive_pin(file)['sha256'],
                'Backup must preserve every original byte')


def confirm(registry, ledger, q, confirmation_hash, *, writers_stopped=False, backup_root=None):
    require(valid(q) and confirmation_hash == digest(q) and writers_stopped is True and backup_root is not None,
            'Exact new load confirmation, quiesced writers and verified backup required')
    current(registry,ledger,q); verify_backup(q,backup_root)
    root = Path(q['journal'])
    with partial.lock(registry.db), partial.lock(ledger.db):
        current(registry,ledger,q)
        root.parent.mkdir(mode=0o700,exist_ok=True); isolated_directory(root.parent)
        sync_directory(root.parent.parent)
        root.mkdir(mode=0o700); sync_directory(root.parent)
        exclusive(root/'intent.json', {'kind':KIND,'reviewHash':digest(q)})
    # The intent is canonical before any connection. Interrupted attempts cannot migrate.
    result = None; proxy = None
    try:
        scope = q['provenance']['scope']
        with inspection.InspectionProxy(scope) as proxy:
            before = inspection.repeated(proxy,scope)
            require(before['activity'] == 'notLoaded' and before['policy'] is None
                    and before['trackedTerminals'] is None, 'Require the exact unloaded brain; do not adopt another load')
            current(registry,ledger,q)
            require(inspection.repeated(proxy,scope) == before, 'Native drift before the one load')
            exclusive(root/'load.claim.json', {'reviewHash':digest(q),'paramsHash':digest(inspection.load_params(scope))})
            current(registry,ledger,q)
            proxy.load_permitted = True
            reply = proxy._rpc('thread/resume',inspection.load_params(scope))
            thread = reply.get('thread') if isinstance(reply,dict) else None
            require(isinstance(thread,dict) and thread.get('id') == scope['brainId']
                    and thread.get('cwd') == scope['cwd'] and thread.get('turns',[]) == [], 'Load acknowledgement unknown; never retry')
            exclusive(root/'load-ack.json', {'reviewHash':digest(q),'acknowledged':True})
            after = inspection.repeated(proxy,scope)
            require(after['activity'] == 'idle' and after['trackedTerminals'] == [], 'Loaded policy/tracker remains unqualified')
            current(registry,ledger,q)
            exclusive(root/'observation.json', {'reviewHash':digest(q),'observedAt':time.time(),'observation':after,
                                               'boundary':dict(BOUNDARY)})
            result = 'load_observed_idle'
    except (OSError,Refusal,ValueError,KeyError,TypeError,KeyboardInterrupt) as error:
        exclusive(root/'failure.json', {'reviewHash':digest(q),'errorType':type(error).__name__,
                                       'retryPermitted':False})
    closed = proxy is not None and proxy.process is None
    outcome = {'status':result if result and closed else 'consumed_outcome_unknown','reviewHash':digest(q),
               'records':{name:control.pin(root/name) for name in ('load.claim.json','load-ack.json','observation.json') if (root/name).exists()},
               'connectionClosed':closed,'currentEvidence':'historical_after_attempt','boundary':dict(BOUNDARY)}
    exclusive(root/'outcome.json',outcome)
    return outcome


def status(q):
    """File-only historical outcome. No reconnect, collection, load or renewal."""
    require(valid(q), 'Closed replacement-load review required')
    root = Path(q['journal'])
    if not os.path.lexists(root): return {'status':'not_submitted','boundary':dict(BOUNDARY)}
    require(control._read_private(root/'intent.json') == {'kind':KIND,'reviewHash':digest(q)}, 'Partial load intent; never retry')
    if not (root/'outcome.json').exists(): return {'status':'consumed_outcome_unknown','boundary':dict(BOUNDARY)}
    outcome = control._read_private(root/'outcome.json')
    require(set(outcome) == {'status','reviewHash','records','connectionClosed','currentEvidence','boundary'}
            and outcome['reviewHash'] == digest(q) and outcome['boundary'] == BOUNDARY
            and outcome['status'] in ('load_observed_idle','consumed_outcome_unknown')
            and type(outcome['connectionClosed']) is bool and outcome['currentEvidence'] == 'historical_after_attempt'
            and set(outcome['records']) <= {'load.claim.json','load-ack.json','observation.json'}
            and all(control.pin(root/name) == pin for name,pin in outcome['records'].items()), 'Changed load outcome; retain unknown')
    if 'load.claim.json' in outcome['records']:
        require(control._read_private(root/'load.claim.json') == {'reviewHash':digest(q),
            'paramsHash':digest(inspection.load_params(q['provenance']['scope']))}, 'Original load claim changed')
    require('load-ack.json' not in outcome['records'] or 'load.claim.json' in outcome['records'],
            'Acknowledgement without its original load claim remains unqualified')
    if outcome['status'] == 'load_observed_idle':
        require(outcome['connectionClosed'] is True and set(outcome['records']) == {'load.claim.json','load-ack.json','observation.json'}
                and control._read_private(root/'load-ack.json') == {'reviewHash':digest(q),'acknowledged':True},
                'An outcome label is not a load acknowledgement')
        observed = control._read_private(root/'observation.json')
        require(observed.get('reviewHash') == digest(q) and observed.get('boundary') == BOUNDARY
                and observed['observation']['activity'] == 'idle' and observed['observation']['trackedTerminals'] == [],
                'Actual retained loaded-idle observation required')
    return outcome


def stop(q, confirmation_hash):
    require(valid(q) and confirmation_hash == digest(q), 'Exact new load review required to stop')
    root = Path(q['journal'])
    require(control._read_private(root/'intent.json') == {'kind':KIND,'reviewHash':digest(q)}, 'Exact claimed load required')
    exclusive(root/'stop.json',{'kind':KIND,'reviewHash':digest(q),'nativeCancelSent':False})
    return {'status':'stop_requested','nativeCancelSent':False,'boundary':dict(BOUNDARY)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub = p.add_subparsers(dest='action',required=True)
    a = sub.add_parser('candidate'); a.add_argument('launch_review')
    a = sub.add_parser('prepare'); a.add_argument('launch_review'); a.add_argument('candidate_binding')
    for action in ('backup','confirm','status','stop'):
        a = sub.add_parser(action); a.add_argument('review')
        if action == 'backup': a.add_argument('destination')
        if action in ('backup','confirm'): a.add_argument('--writers-stopped',action='store_true')
        if action == 'confirm': a.add_argument('--confirm-hash',required=True); a.add_argument('--backup',required=True)
        if action == 'stop': a.add_argument('--confirm-hash',required=True)
    args = p.parse_args()
    if args.action == 'status': out = status(read_review(args.review))
    elif args.action == 'stop': out = stop(read_review(args.review),args.confirm_hash)
    else:
        registry,ledger = partial.routes(args.platform,args.workspace)
        if args.action == 'candidate': out = {'binding':provenance(registry,ledger,args.launch_review)['scope']['binding'],
                                             'nativeRpcCalls':0,'bindingInstalled':False}
        elif args.action == 'prepare': out = prepare(registry,ledger,args.launch_review,args.candidate_binding)
        else:
            q = read_review(args.review)
            if args.action == 'backup': out = backup(registry,ledger,q,args.destination,writers_stopped=args.writers_stopped)
            else: out = confirm(registry,ledger,q,args.confirm_hash,writers_stopped=args.writers_stopped,backup_root=args.backup)
    print(canonical(out))


if __name__ == '__main__':
    try: main()
    except (OSError,Refusal,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
