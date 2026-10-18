"""Launch-only replacement review after an exact canceled/interrupted Play.

Preserve old ledger/claims/binding and signed-in credential metadata. A new
package is explicitly reviewed; no brain load, endpoint connection or turn.
"""
import argparse
import copy
import os
from pathlib import Path
import platform
import sys
import time

from . import canceled_continuation as control, partial_admission as partial
from . import public_host_restart as shared, public_preplay_host_lineage as lineage
from .core import Refusal, canonical, digest, require
from .host_lifecycle import private_file, sync_directory
from .native_read_client import decode
from .public_host_lifecycle import directory_identity, environment, isolated_directory
from .public_host_runtime import inspect_package, validate_pin
from .standard_quarantine import exclusive

KIND='canceled_play_replacement_host_v1'
BOUNDARY={**control.BOUNDARY,'hostStartsOnlyAfterExactReview':True,'credentialBytesRead':False,
          'credentialsCopied':False,'bindingInstalled':False,'continuationAuthorized':False}
FIELDS={'version','kind','sourceTree','original','previousAttempt','previousPins','previousStatus',
        'originalLaunch','launchSpec','socketDirectory','socketIdentity','reviewDirectory',
        'backupPath','homeSnapshotPin','fencePath','boundary'}


def inputs(registry,ledger,previous,binding_file,command_id):
    original=control.original_context(registry,ledger,binding_file,command_id)
    launch,status,pins,original_file,sockets,reviews,ancestors=lineage.issued(previous,ledger)
    binding=control._read_binding(binding_file)
    require(binding['endpoint']['executable']==str(Path(launch['runtimePackage']['root'])/'bin/codex') and
        binding['endpoint']['sha256']==launch['runtimePackage']['executableHash'] and
        original['scope']['checkout']==launch['cwd'] and
        control._read_binding(original_file)['brains']==binding['brains'],
        'Exact issued original host/package/home/brain provenance required')
    # This distinct post-Cancel scope does not reinterpret any old readiness/load claim.
    known={p['path'] for p in pins}
    from .public_preplay_host_restart import PREFIX, fence_path
    require(not os.path.lexists(fence_path(ledger,launch,status,successor=True)),
        'A prior attempted restart of this process epoch remains consumed')
    found={str(p) for p in ledger.root.iterdir() if p.name.startswith(PREFIX)}
    require(found<=known,'Unknown/partial earlier host claim is not a new-launch permit')
    for _ in range(2): shared.quiescent(launch,status)
    return original,launch,status,pins,sockets,reviews


def fence(registry,original,status):
    key=digest({'ledgerIdentity':original['databases']['target']['identity'],
        'processIdentity':status['processIdentity'],'previousSpecHash':status['specHash']})
    return registry.root/'canceled-host-launches'/key


def paths(old,package,previous,sockets,directory,retired_sockets,retired_reviews,*,prepared=False):
    sockets=isolated_directory(sockets); directory=Path(directory); isolated_directory(directory.parent)
    roots=[Path(old[k]) for k in ('cwd','codexHome')]+[Path(old['runtimePackage']['root']),Path(package['root']),Path(previous)]
    require(not list(sockets.iterdir()) and len(os.fsencode(str(sockets/'host.sock')))<=100 and
        directory.is_absolute() and directory.resolve()==directory and
        (directory.is_dir() if prepared else not os.path.lexists(directory)) and
        all(not a.is_relative_to(b) and not b.is_relative_to(a) for a in (sockets,directory)
            for b in roots+[Path(p) for p in retired_sockets+retired_reviews]) and
        not sockets.is_relative_to(directory) and not directory.is_relative_to(sockets),
        'New canonical private socket/review paths must be disjoint from every prior host and preserved state')
    if prepared: isolated_directory(directory)
    return sockets,directory


def prepare(registry,ledger,previous,binding_file,command_id,package,sockets,directory):
    values=inputs(registry,ledger,previous,binding_file,command_id)
    original,old,status,pins,retired_sockets,retired_reviews=values
    package=inspect_package(package); launch=copy.deepcopy(old); launch['runtimePackage']=package
    require(package['executableHash']!=old['runtimePackage']['executableHash'],
        'Distinct reviewed subscribe-only replacement package required, not original launch replay')
    sockets,directory=paths(old,package,previous,sockets,directory,retired_sockets,retired_reviews)
    claim=fence(registry,original,status); require(not os.path.lexists(claim),'This last process epoch already has a launch claim')
    binary=str(Path(old['runtimePackage']['root'])/'bin/codex')
    shared.restricted_config(old['codexHome'],old['cwd'])
    for _ in range(2): shared.quiescent(launch,status)
    snapshot=shared.signed_in_preplay_snapshot(old['codexHome'],binary,brain=original['brainId'])
    directory.mkdir(mode=0o700); backup=directory/'native-home-backup'; backup.mkdir(mode=0o700)
    require(shared.signed_in_preplay_snapshot(old['codexHome'],binary,backup,brain=original['brainId'])==snapshot,
        'Native home changed during opaque non-credential backup; preserve this partial preparation')
    exclusive(directory/'home-snapshot.json',snapshot)
    q={'version':1,'kind':KIND,'sourceTree':shared.source_tree(),'original':original,
        'previousAttempt':str(previous),'previousPins':pins,'previousStatus':status,'originalLaunch':old,'launchSpec':launch,
        'socketDirectory':str(sockets),'socketIdentity':directory_identity(sockets),'reviewDirectory':str(directory),
        'backupPath':str(backup),'homeSnapshotPin':shared.pin(directory/'home-snapshot.json',1_000_000),
        'fencePath':str(claim),'boundary':dict(BOUNDARY)}
    shared.backup_check(q,snapshot)
    require(inputs(registry,ledger,previous,binding_file,command_id)==values,'Original scope changed during preparation')
    exclusive(directory/'replacement.json',q)
    return preview(registry,ledger,directory/'replacement.json')


def load(file):
    q=decode(shared.read_file(private_file(file),65536)[0])
    require(isinstance(q,dict) and set(q)==FIELDS and type(q['version']) is int and q['version']==1 and
        q['kind']==KIND and q['boundary']==BOUNDARY and Path(file)==Path(q['reviewDirectory'])/'replacement.json' and
        q['sourceTree']==shared.source_tree(),'Exact clean-source closed replacement-host review required')
    return q


def review_hash(q): return digest({'kind':KIND,'mode':'launch_only_exec','requestHash':digest(q)})


def validate(registry,ledger,file,*,claimed=False):
    q=load(file); o=q['original']
    actual=inputs(registry,ledger,q['previousAttempt'],o['bindingFile'],o['command']['id'])
    require(actual[:4]==(o,q['originalLaunch'],q['previousStatus'],q['previousPins']), 'Original host/run/claims/binding changed')
    require(str(fence(registry,o,q['previousStatus']))==q['fencePath'],'Canonical predecessor fence differs')
    claim=Path(q['fencePath'])
    if claimed: require(control._read_private(claim/'intent.json')=={'kind':KIND,'reviewHash':review_hash(q)},'Exact claimed launch required')
    else: require(not os.path.lexists(claim),'Launch consumed; never retry')
    require(q['launchSpec']=={**q['originalLaunch'],'runtimePackage':q['launchSpec']['runtimePackage']},'Only reviewed native package may differ')
    require(q['launchSpec']['runtimePackage']['executableHash']!=q['originalLaunch']['runtimePackage']['executableHash'],
        'Replacement cannot reinterpret the original launch as retry')
    validate_pin(q['launchSpec']['runtimePackage'])
    sockets,directory=paths(q['originalLaunch'],q['launchSpec']['runtimePackage'],q['previousAttempt'],
        q['socketDirectory'],q['reviewDirectory'],actual[4],actual[5],prepared=True)
    require(q['backupPath']==str(directory/'native-home-backup') and
        q['homeSnapshotPin']['path']==str(directory/'home-snapshot.json'),'Exact review-local archive required')
    require(directory_identity(sockets)==q['socketIdentity'] and not list(sockets.iterdir()),'New socket directory changed')
    require(shared.pin(q['homeSnapshotPin']['path'],1_000_000)==q['homeSnapshotPin'],'Native archive changed')
    snapshot=decode(shared.read_file(q['homeSnapshotPin']['path'],1_000_000)[0]); shared.backup_check(q,snapshot)
    old=q['originalLaunch']; shared.restricted_config(old['codexHome'],old['cwd'])
    for _ in range(2): shared.quiescent(q['launchSpec'],q['previousStatus'])
    require(shared.signed_in_preplay_snapshot(old['codexHome'],str(Path(old['runtimePackage']['root'])/'bin/codex'),
        brain=o['brainId'])==snapshot,'Home/config/credential metadata changed')
    return q


def status(file):
    q=load(file); root=Path(q['fencePath'])
    if not os.path.lexists(root): return {'status':'prepared_not_submitted','boundary':dict(BOUNDARY)}
    isolated_directory(root)
    require(control._read_private(root/'intent.json')=={'kind':KIND,'reviewHash':review_hash(q)},'Partial launch claim; never retry')
    return {'status':'launch_claimed_outcome_unknown','boundary':dict(BOUNDARY)}


def preview(registry,ledger,file):
    q=validate(registry,ledger,file)
    return {'reviewHash':review_hash(q),'validUntil':'scope_changes','requestFile':str(file),
        'effect':'One foreground launch of the reviewed replacement binary on the unchanged isolated home; no load, turn or rebind',
        'nativeSource':q['launchSpec']['runtimePackage']['sourceCommit'],
        'nativeExecutableSha256':q['launchSpec']['runtimePackage']['executableHash'],
        'originalHostPid':q['previousStatus']['pid'],'startsHost':False,'boundary':dict(BOUNDARY)}


def execute(registry,ledger,file,confirmation_hash):
    q=validate(registry,ledger,file)
    require(confirmation_hash==review_hash(q) and sys.platform=='darwin' and platform.machine()=='arm64',
        'Exact new replacement-host launch confirmation on macOS ARM64 required')
    claim=Path(q['fencePath']); claim.parent.mkdir(mode=0o700,exist_ok=True)
    isolated_directory(claim.parent); claim.mkdir(mode=0o700)
    exclusive(claim/'intent.json',{'kind':KIND,'reviewHash':confirmation_hash})
    exclusive(claim/'exec.claim.json',{'kind':KIND,'reviewHash':confirmation_hash,'pid':os.getpid(),
        'processIdentity':shared.process_identity(os.getpid()),'at':time.time()})
    validate(registry,ledger,file,claimed=True)
    binary=str(Path(q['launchSpec']['runtimePackage']['root'])/'bin/codex')
    argv=[binary,'app-server','--listen','unix://'+str(Path(q['socketDirectory'])/'host.sock')]
    exclusive(claim/'issued.json',{'kind':KIND,'status':'exec_boundary_issued','argv':argv,
        'reviewHash':confirmation_hash,'pid':os.getpid(),'processIdentity':shared.process_identity(os.getpid()),
        'cwd':q['launchSpec']['cwd'],'boundary':dict(BOUNDARY)})
    try:
        os.chdir(q['launchSpec']['cwd'])
        with open(os.devnull,'rb') as source,open(os.devnull,'wb') as sink:
            os.dup2(source.fileno(),0); os.dup2(sink.fileno(),1); os.dup2(sink.fileno(),2)
        os.execve(binary,argv,environment(q['launchSpec']))
        raise OSError('Exec unexpectedly returned')
    except (OSError,KeyboardInterrupt):
        exclusive(claim/'failed-or-unknown.json',{'reviewHash':confirmation_hash,'status':'unknown_no_retry'})
        raise Refusal('Launch failed or was interrupted; claims remain consumed, no automatic retry') from None


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare')
    for name in ('previous','binding','command','package','sockets','directory'): a.add_argument(name)
    for name in ('preview','exec','status'):
        a=s.add_parser(name); a.add_argument('review')
        if name=='exec': a.add_argument('--confirm-hash',required=True)
    args=p.parse_args(); registry,ledger=partial.routes(args.platform,args.workspace)
    if args.action=='prepare': out=prepare(registry,ledger,args.previous,args.binding,args.command,args.package,args.sockets,args.directory)
    elif args.action=='preview': out=preview(registry,ledger,args.review)
    elif args.action=='status': out=status(args.review)
    else: out=execute(registry,ledger,args.review,args.confirm_hash)
    print(canonical(out))


if __name__=='__main__':
    try: main()
    except (OSError,Refusal,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
