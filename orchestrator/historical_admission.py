"""Append file-only historical admission requalification, never execution.

Original completion/accounting observations keep their bytes and clocks. A new
record binds the completed setup transition and exact historical implementations.
No native transport, collection, load, replay, binding change or admission write.
"""
import argparse
import os
from pathlib import Path
import time

from . import admission_continuity as continuity, post_preparation_usage as usage
from .core import Refusal, canonical, digest, require
from .standard_quarantine import exclusive
from .host_lifecycle import sync_directory

KIND='historical_worker_admission_requalification_v1'
BOUNDARY={'nativeConnection':False,'brainReloaded':False,'requestReplayed':False,
    'usageCollected':False,'usageReset':False,'observationsRenewed':False,'bindingChanged':False,
    'claimsRearmed':False,'admissionAuthorized':False,'playAuthorized':False,
    'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown','pilotAccepted':False}
INPUTS={'targetId','usageDirectory','usageSource','setupSource'}


def context(registry,source,inputs):
    require(isinstance(inputs,dict) and set(inputs)==INPUTS, 'Closed historical admission inputs required')
    transition={'targetId':inputs['targetId'],'setupSource':inputs['setupSource']}
    result=usage.status(registry,source,inputs['usageDirectory'],setup_transition=transition,usage_source=inputs['usageSource'])
    require(result['status']=='usage_observed', 'Unknown/gapped historical accounting cannot be requalified')
    proof=continuity.validate(registry,source,inputs['targetId'],setup_source=inputs['setupSource'])
    original_source=continuity.implementation(result['context']['sourceHash'],inputs['usageSource'],usage.PR183_SOURCE)
    completed=usage.completion.handoff.read(Path(result['context']['completionDirectory'])/'intent.json')
    q=usage.completion.planning.read_review(completed['reviewFile'])
    value={'kind':KIND,'sourceHash':continuity.setup.source_hash(),'inputs':dict(inputs),
        'sourceWorkspace':source.workspace_id,'sourceRoot':str(source.root),
        'usageIntentPin':continuity.setup.pin(Path(inputs['usageDirectory'])/'intent.json'),
        'usageEvidencePin':continuity.setup.pin(Path(inputs['usageDirectory'])/'evidence.json'),
        'usageEvidenceHash':digest(result),'usageSource':original_source,'transition':proof,
        'originalUsageCollectedAt':result['report']['collectedAt'],'originalUsageThrough':result['report']['through'],
        'originalCompletionObservedAt':usage.completion.handoff.read(
            Path(result['context']['completionDirectory'])/'evidence.json')['observedAt'],
        'boundary':dict(BOUNDARY)}
    return value,result,q


def qualify(registry,source,target_id,usage_directory,out,*,setup_source=None,usage_source=None):
    inputs={'targetId':target_id,'usageDirectory':str(Path(usage_directory)),
        'setupSource':None if setup_source is None else str(Path(setup_source)),
        'usageSource':None if usage_source is None else str(Path(usage_source))}
    before,old,q=context(registry,source,inputs)
    receipt=continuity.setup.read(before['transition']['receiptPin']['path'])
    transfer=usage.completion.handoff.transfer_record(q)
    root=Path(out); usage.completion.planning.old.private_path(root.parent,existing=True)
    protected=[registry.root,source.root,Path(inputs['usageDirectory']),Path(q['journal']),Path(q['mailbox']),
        Path(q['transferFile']).parent,Path(q['original']['scope']['checkout']),
        Path(q['package']['root']),Path(transfer['snapshot']['sourceHome']),Path(transfer['destinationHost']['home']),
        Path(receipt['request']['spec']['checkout']),Path(receipt['request']['spec']['configFile']).parent,
        Path(continuity.__file__).resolve().parent.parent,
        *[Path(p) for p in (setup_source,usage_source) if p is not None]]
    require(root.is_absolute() and root.resolve()==root and not os.path.lexists(root) and
        all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in protected),
        'New disjoint private requalification directory required; preserve every original evidence file')
    root.mkdir(mode=0o700); sync_directory(root.parent); exclusive(root/'intent.json',before)
    after,_,_=context(registry,source,inputs)
    require(before==after, 'Historical lineage changed during file-only requalification; no automatic retry')
    value={'kind':KIND,'status':'historical_admission_evidence_requalified','context':before,
        'qualifiedAt':time.time(),'postPreparationTokens':old['report']['tokens']['total_tokens'],
        'remainingConservativePhaseCeiling':old['remainingConservativePhaseCeiling'],'boundary':dict(BOUNDARY)}
    exclusive(root/'evidence.json',value)
    return value


def resolved(registry,source,directory):
    root=Path(directory); value=continuity.setup.read(root/'evidence.json'); before=continuity.setup.read(root/'intent.json')
    require({p.name for p in root.iterdir()}=={'intent.json','evidence.json'} and set(value)=={
        'kind','status','context','qualifiedAt','postPreparationTokens','remainingConservativePhaseCeiling','boundary'} and
        value['kind']==KIND and value['status']=='historical_admission_evidence_requalified' and
        value['context']==before and value['boundary']==BOUNDARY and
        usage.forward_usage.number(value['qualifiedAt']) and value['qualifiedAt']<=time.time(),
        'Complete immutable file-only requalification required; no partial/unknown fallback')
    now,old,q=context(registry,source,before['inputs'])
    require(before==now and value['postPreparationTokens']==old['report']['tokens']['total_tokens'] and
        value['remainingConservativePhaseCeiling']==old['remainingConservativePhaseCeiling'],
        'Requalification scope/source/accounting drifted; never rewrite or renew historical evidence')
    return value,old,q


def status(registry,source,directory): return resolved(registry,source,directory)[0]


def backup_inputs(registry,source,directory):
    value,_,_=resolved(registry,source,directory); proof=value['context']['transition']
    root=Path(directory); backup=Path(proof['backupDirectory'])
    receipt=continuity.setup.read(Path(proof['receiptPin']['path']))
    files={str(root/'intent.json'),str(root/'evidence.json'),proof['receiptPin']['path'],proof['claimPin']['path'],
        str(backup/'manifest.json'),str(backup/'request.json')}
    snapshots={v['path'] for v in proof['snapshots'].values()}; files.update(snapshots)
    manifest=continuity.setup.read(backup/'manifest.json')
    files.update(str(backup/e['copy']) for e in manifest['files'])
    # Public non-writable original source inputs may be 644. Their immutable
    # private copies are backed up here; never broaden ordinary sidecar reads.
    files.update(e['original'] for e in manifest['files'] if not Path(e['original']).stat().st_mode & 0o077)
    require(receipt['reviewHash']==proof['reviewHash'] and len(files)<=192, 'Bounded exact historical backup inventory required')
    return files,snapshots


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('qualify'); c.add_argument('target'); c.add_argument('usage'); c.add_argument('directory')
    c.add_argument('--setup-source'); c.add_argument('--usage-source')
    s=sub.add_parser('status'); s.add_argument('directory')
    args=p.parse_args(); registry,source=usage.completion.planning.partial.routes(args.platform,args.workspace)
    result=(qualify(registry,source,args.target,args.usage,args.directory,setup_source=args.setup_source,usage_source=args.usage_source)
        if args.action=='qualify' else status(registry,source,args.directory))
    print(canonical(result))


if __name__=='__main__':
    try: main()
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
