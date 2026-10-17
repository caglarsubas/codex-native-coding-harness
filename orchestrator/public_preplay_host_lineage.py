"""File-only lineage of genuine issued pre-Play host exits, never native replay.

The original v1 repair stays original-launch-only. A distinct v2 review pins
every issued ancestor and immutable archive without requiring historical code
to run. Failed, partial or unknown execs cannot become successor authority.
"""
import os
from pathlib import Path
import re

from . import public_host_restart as shared, public_preplay_host_restart as fresh
from .app_server_wake import _read_binding
from .core import digest, require
from .host_lifecycle import private_file
from .native_read_client import decode
from .public_host_lifecycle import isolated_directory


def read(path,limit=65536): return decode(shared.read_file(private_file(path),limit)[0])


def issued(attempt,ledger,seen=()):
    """Validate closed original journals; never read native stores/endpoints."""
    attempt=isolated_directory(attempt)
    require(str(attempt) not in seen and len(seen)<7,'Pre-Play successor cycle/depth bound exceeded')
    require(not (attempt/'launch.json').exists(),'Successor mode requires an issued restart, never its ancestor')
    spec_path=attempt.parent/'restart.json'; spec=read(spec_path)
    require(set(spec)==fresh.FIELDS and type(spec.get('version')) is int and
            ((spec['version']==1 and spec['kind']==fresh.KIND) or
             (spec['version']==2 and spec['kind']==fresh.SUCCESSOR_KIND)) and
            spec['reviewDirectory']==str(attempt.parent) and isinstance(spec['sourceTree'],str) and
            re.fullmatch('[0-9a-f]{40}',spec['sourceTree']), 'Exact historical pre-Play restart required')
    if spec['version']==1:
        require((Path(spec['previousAttempt'])/'launch.json').is_file(),'Initial repair must pin the original launch')
        launch,predecessor,earlier=shared.original_launch(spec['previousAttempt'],ledger)
        original_binding=spec['bindingFile']; sockets=[launch['socketDirectory']]; reviews=[]; ancestors=[]
    else:
        launch,predecessor,earlier,original_binding,sockets,reviews,ancestors=issued(
            spec['previousAttempt'],ledger,(*seen,str(attempt)))
    require(spec['launchSpec']==launch and spec['previousPins']==earlier,'Historical predecessor changed')
    state=read(attempt/'status.json'); intent=read(attempt/'intent.json')
    require(set(state)=={'kind','status','pid','parentPid','processIdentity','at','specHash','boundary'} and
            state['kind']==spec['kind'] and state['status']=='exec_boundary_issued' and
            type(state['pid']) is int and state['pid']>0 and
            isinstance(state['processIdentity'],str) and state['processIdentity'].startswith(str(state['pid'])+' ') and
            len(state['processIdentity'])<=200 and state['specHash']==digest(spec) and state['boundary']==fresh.BOUNDARY and
            set(intent)=={'kind','specHash','reviewHash','at'} and intent['kind']==spec['kind'] and
            intent['specHash']==digest(spec) and intent['reviewHash']==fresh.review_hash(spec) and
            shared.pin(attempt/'exec.claim')['bytes']==0, 'Only a complete issued process epoch may have a successor')
    fence=fresh.fence_path(ledger,launch,predecessor,successor=spec['version']==2)
    require(spec['fencePath']==str(fence) and read(fence)==
            {'kind':spec['kind'],'specHash':digest(spec),'reviewDirectory':spec['reviewDirectory']},
            'Historical permanent predecessor fence changed')
    require(shared.pin(spec['homeSnapshotPin']['path'],1_000_000)==spec['homeSnapshotPin'] and
            spec['homeSnapshotPin']['path']==str(attempt.parent/'home-snapshot.json') and
            spec['backupPath']==str(attempt.parent/'native-home-backup'), 'Exact original archive location required')
    shared.backup_check(spec,read(spec['homeSnapshotPin']['path'],1_000_000))
    require(shared.pin(spec['bindingFile'])==spec['bindingPin'],'Historical reviewed binding changed')
    # Absence is quiescence, never terminal cleanup or proof of why it exited.
    for _ in range(2):
        require(shared.process_absent(predecessor['pid']) and shared.process_absent(state['pid']),
                'A predecessor PID is live, reused or unknown')
    pins=earlier+[shared.pin(p) for p in (spec_path,attempt/'intent.json',attempt/'status.json',attempt/'exec.claim',fence,
                                         spec['bindingFile'])]+[shared.pin(spec['homeSnapshotPin']['path'],1_000_000)]
    return launch,state,pins,original_binding,[*sockets,spec['socketDirectory']],[*reviews,str(attempt.parent)],[*ancestors,spec]


def inputs(registry,ledger,previous,binding_file):
    from .readiness_owned import claims
    require(not claims(ledger),'A readiness-owned attempt is outside this unchanged pre-Play maintenance scope')
    launch,old,pins,original_file,sockets,reviews,ancestors=issued(previous,ledger)
    original=_read_binding(original_file); current=_read_binding(binding_file)
    require(set(original['brains'])==set(current['brains']) and current['brains']==original['brains'] and
            current['endpoint']['executable']==original['endpoint']['executable'] and
            current['endpoint']['sha256']==original['endpoint']['sha256'],
            'Only unchanged brain/checkout/dual IDs/package/policy may continue maintenance')
    scope=fresh.protected(registry,ledger,original_file,launch)
    for spec in ancestors:
        prior=spec['scope']
        require(all(prior[k]==scope[k] for k in ('workspaceId','brainId','identity','missionHash','turns','databases')) and
                all(scope['sidecars'].get(k)==v for k,v in prior['sidecars'].items()),
                'Original first-phase requests, database scope or captured claims changed')
    known={p['path'] for p in pins if Path(p['path']).parent==ledger.root and Path(p['path']).name.startswith(fresh.PREFIX)}
    own=fresh.fence_path(ledger,launch,old,successor=True)
    found={str(p) for p in ledger.root.iterdir() if p.name.startswith(fresh.PREFIX)}
    require(found<=known|{str(own)},'An unrelated or partial restart claim must be preserved, not bypassed')
    require(not os.path.lexists(ledger.root/'standard-forward-continuation.json'),'Forward admission cannot use pre-Play maintenance')
    scope.update(originalBindingFile=str(original_file),originalBindingPin=shared.pin(original_file),
        currentBindingHash=digest(current),currentBindingPin=shared.pin(binding_file),
        retiredSocketDirectories=sockets,predecessorReviewDirectories=reviews,
        predecessorProcess={'pid':old['pid'],'processIdentity':old['processIdentity'],'specHash':old['specHash']})
    return launch,old,pins,scope
