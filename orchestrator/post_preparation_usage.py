"""Explicit append-only usage of one exactly transferred completed preparation.

No old usage claim is consumed again. Only its original native-returned rollout
is read; copied prefixes are measured once, against both immutable baselines.
No native write, load, subscription, turn, binding or ledger mutation exists.
"""
import argparse
import io
import os
from pathlib import Path
import time

from . import brain_memory, forward_usage, handoff_reconciliation as completion
from .core import Refusal, canonical, digest, require
from .native_read_client import file_identity
from .standard_quarantine import exclusive

KIND='transferred_preparation_usage_v1'
PR183_SOURCE='a12d24ecc2eaceb2bff8f5e59a435e8084c8ff9d30bf4ad7dd812e89313a38fa'
BOUNDARY={k:v for k,v in completion.BOUNDARY.items() if k not in {'usageCollected','postTurnUsage'}}
BOUNDARY.update(executionAuthorized=False,providerBillingVerified=False,originalUsageChanged=False,
    originalCompletionUsageChanged=False,usageEvidenceOnly=True)


def context(registry,ledger,directory,completion_source=None,*,live=False,setup_transition=None):
    require(setup_transition is None or live is False, 'Registration requalification is file-only, not a usage collection permit')
    evidence=completion.status(registry,ledger,directory,completion_source=completion_source,setup_transition=setup_transition)
    require(evidence['status']=='preparation_completion_observed','Independent completed preparation evidence required')
    old=evidence['context']; original_source=old['originalSource']
    q,now=completion.context(registry,ledger,old['reviewFile'],
        None if original_source is None else original_source['root'],live=live,setup_transition=setup_transition)
    source_proof=None if completion_source is None else completion.handoff.phase.lifecycle.source_proof(completion_source)
    usage_file=Path(q['journal'])/'usage.json'; usage_pin=completion.planning.pin(usage_file)
    completion.handoff.check_usage(q,usage_pin,fresh=False,active=False)
    baseline=completion.handoff.read(usage_file)['report']
    return q,evidence,{'completionDirectory':str(Path(directory)),'completionPin':completion.planning.pin(Path(directory)/'evidence.json'),
        'completionIntentPin':completion.planning.pin(Path(directory)/'intent.json'),'completionSource':source_proof,
        'context':now,'preTurnUsagePin':usage_pin,'preTurnReportHash':digest(baseline),
        'sourceHash':completion.planning.old.source_hash()},baseline


def observation(raw,q,baseline,now):
    run=q['original']['run']; brain=run['brainId']
    rows=[completion.planning.decode(line) for line in raw.splitlines()]
    turn=completion.handoff.read(Path(q['journal'])/'native-ack.json')['turnId']
    starts=[]; ends=[]
    for row in rows:
        p=row.get('payload') or {}
        if row.get('type')=='event_msg' and p.get('turn_id')==turn:
            if p.get('type')=='task_started': starts.append(brain_memory.stamp(row.get('timestamp')))
            if p.get('type')=='task_complete': ends.append(brain_memory.stamp(row.get('timestamp')))
    require(len(starts)==len(ends)==1 and all(forward_usage.number(v) for v in starts+ends) and
        run['startedAt']<=starts[0]<=ends[0]<=now,'Exact dated new-turn interval required')
    record=brain_memory.session_usage([Path('exact-registered-rollout')],brain,run['startedAt'],ends[0],True,
        open_log=lambda _:io.BytesIO(raw))
    record['role']='brain'
    report={'scopeHash':brain_memory.scope(run),'runId':run['id'],'collectedAt':now,'through':ends[0],
        'records':[record],'tokens':record['tokens'],'gaps':record['gaps'],
        'coverage':'gapped' if record['gaps'] else 'observed_local',
        'boundary':'Single exact transferred session; inherited prefix counted once, not billing or descendants'}
    issues=[]
    try:
        forward_usage.baseline(q['original'])
        prior=forward_usage.validate(baseline,run); after=forward_usage.validate(report,run)
        require(set(prior)==set(after)=={brain},'Only the unchanged single registered brain is supported')
        a,b=after[brain],prior[brain]
        require(starts[0]<=a['sampleAt']<=ends[0] and a['sampleAt']>=b['sampleAt'] and
            report['collectedAt']>=baseline['collectedAt'] and
            a['calls']>=b['calls'] and all(a['tokens'][k]>=b['tokens'][k] for k in forward_usage.TOKENS) and
            report['through']>=baseline['through'] and
            report['tokens']['total_tokens']>=max(run['usageHighWater'],run['brainObservedTokens']),
            'Post-turn counters must cover both immutable baselines without refunds or resets')
    except Refusal:
        issues.append('incomplete_or_regressed_post_turn_usage')
    amount=report['tokens']['total_tokens']
    ceiling=min(run['brainAllowance']-amount,
        run['limits']['tokenBudget']-amount-run['limits']['checkpointReserveTokens'])
    if ceiling<=0: issues.append('unchanged_budget_or_reserve_exhausted')
    return {'report':report,'newTurnInterval':{'startedAt':starts[0],'completedAt':ends[0]},
        'remainingConservativePhaseCeiling':max(0,ceiling),'issues':issues}


def collect(registry,ledger,directory,out,*,completion_source=None):
    q,evidence,before,baseline=context(registry,ledger,directory,completion_source,live=True)
    root=Path(out); completion.planning.old.private_path(root.parent,existing=True)
    transfer=completion.handoff.transfer_record(q)
    protected=[registry.root,ledger.root,Path(q['journal']).parent,Path(q['mailbox']),Path(directory),
        Path(q['transferFile']).parent,Path(transfer['snapshot']['sourceHome']),Path(transfer['destinationHost']['home']),
        Path(q['original']['scope']['checkout']),Path(q['package']['root']),Path(__file__).resolve().parent.parent]
    if completion_source is not None: protected.append(Path(completion_source))
    require(root.is_absolute() and root.resolve()==root and not os.path.lexists(root) and
        all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in protected),
        'New disjoint private evidence directory required; never write an old journal or native home')
    root.mkdir(mode=0o700); completion.handoff.sync_directory(root.parent)
    exclusive(root/'intent.json',before)
    try:
        with completion.Probe(q) as proxy:
            first=completion.sample(proxy,q,before['context']['nativeTurnId'])
            second=completion.sample(proxy,q,before['context']['nativeTurnId'])
        require(first==second==evidence['native'],'Exact unchanged native completion/account/history required')
        path=first['history']['path']
        raw,history=completion.handoff.transfer.rollout(path,transfer['destinationHost']['home'],
            q['original']['brainId'],q['original']['scope']['checkout'])
        require(history==first['history'],'Native-returned file changed before numeric observation')
        value=observation(raw,q,baseline,time.time())
        _,_,after,_=context(registry,ledger,directory,completion_source,live=True)
        require(before==after and list(file_identity(Path(path).stat()))==history['identity'],
            'Original scope or exact telemetry file changed during collection; no fallback')
        result={'kind':KIND,'status':'usage_observed' if not value['issues'] else 'usage_gapped',
            'context':before,'observedAt':time.time(),'history':history,'native':first,
            **value,'boundary':dict(BOUNDARY)}
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        result={'kind':KIND,'status':'unknown','context':before,'observedAt':time.time(),
            'errorType':type(error).__name__,'boundary':dict(BOUNDARY)}
    exclusive(root/'evidence.json',result)
    return result


def status(registry,ledger,directory,*,fresh=False,setup_transition=None,usage_source=None):
    root=Path(directory); result=completion.handoff.read(root/'evidence.json'); before=completion.handoff.read(root/'intent.json')
    require({p.name for p in root.iterdir()}=={'intent.json','evidence.json'} and result.get('kind')==KIND and
        result.get('context')==before and result.get('boundary')==BOUNDARY and
        result.get('status') in {'usage_observed','usage_gapped','unknown'},'Complete closed usage evidence required')
    source=before['completionSource']
    q,original,now,baseline=context(registry,ledger,before['completionDirectory'],None if source is None else source['root'],
        setup_transition=setup_transition)
    if usage_source is not None:
        from .admission_continuity import implementation
        require(setup_transition is not None and before['sourceHash']==before['context']['currentSourceHash']==PR183_SOURCE,
            'Only exact original PR-183 accounting may use registration requalification')
        implementation(before['sourceHash'],usage_source,PR183_SOURCE)
        left,right=dict(before),dict(now)
        left_context,right_context=dict(left.pop('context')),dict(right.pop('context'))
        left.pop('sourceHash'); right.pop('sourceHash')
        left_context.pop('currentSourceHash'); right_context.pop('currentSourceHash')
        require(left==right and left_context==right_context, 'Unrelated accounting provenance changed')
    else: require(before==now, 'Original usage evidence, source or observation changed')
    require(forward_usage.number(result.get('observedAt')) and
        result['observedAt']<=time.time(),'Original usage evidence, source or observation changed')
    common={'kind','status','context','observedAt','boundary'}
    if result['status']=='unknown':
        require(set(result)==common|{'errorType'},'Closed unknown usage evidence required')
    else:
        require(set(result)==common|{'history','native','report','newTurnInterval','remainingConservativePhaseCeiling','issues'} and
            result['native']==original['native'] and result['history']==result['native']['history'] and
            list(file_identity(Path(result['history']['path']).stat()))==result['history']['identity'],
            'Exact observed usage source epoch changed; status never rereads or refreshes telemetry')
        # Recompute consistency from retained numeric records, not from a fresh
        # file read or a caller-authored usable flag.
        report=result['report']; run=q['original']['run']
        if result['status']=='usage_observed':
            require(result['issues']==[],'Gapped usage cannot become usable')
            forward_usage.validate(report,run); forward_usage.baseline(q['original'])
            a,b=report['records'][0],baseline['records'][0]
            interval=result['newTurnInterval']
            require(run['startedAt']<=interval['startedAt']<=a['sampleAt']<=interval['completedAt']==report['through']<=report['collectedAt'] and
                a['sampleAt']>=b['sampleAt'] and a['calls']>=b['calls'] and
                all(a['tokens'][k]>=b['tokens'][k] for k in forward_usage.TOKENS) and
                report['through']>=baseline['through'] and baseline['collectedAt']<=report['collectedAt']<=result['observedAt'] and
                report['tokens']['total_tokens']>=max(run['usageHighWater'],run['brainObservedTokens']) and
                result['remainingConservativePhaseCeiling']==min(run['brainAllowance']-report['tokens']['total_tokens'],
                    run['limits']['tokenBudget']-report['tokens']['total_tokens']-run['limits']['checkpointReserveTokens'])>0,
                'Retained numeric accounting or unchanged caps differ')
    if fresh:
        require(result['status']=='usage_observed' and
            0<=time.time()-result['report']['collectedAt']<brain_memory.FRESH_SECONDS,
            'Fresh actual post-preparation usage required; never retimestamp or use unknown as zero')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('collect'); c.add_argument('completion'); c.add_argument('directory'); c.add_argument('--completion-source')
    s=sub.add_parser('status'); s.add_argument('directory')
    args=p.parse_args(); registry,ledger=completion.planning.partial.routes(args.platform,args.workspace)
    result=(collect(registry,ledger,args.completion,args.directory,completion_source=args.completion_source)
        if args.action=='collect' else status(registry,ledger,args.directory))
    print(canonical(result))


if __name__=='__main__':
    try: main()
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
