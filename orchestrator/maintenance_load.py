"""One new post-disposition maintenance load, never old-attempt continuation.

The old load must be positively closed, not failed/partial/unknown. A consumed
preflight-refused planning attempt stays unknown. No model turn or clock grant.
"""
import argparse
import contextlib
import os
from pathlib import Path
import sqlite3
import time

from . import canceled_load as prior, canceled_continuation as planning
from . import same_project_lifecycle as lifecycle, connection_handoff as continuous
from .core import Refusal, canonical, digest, require
from .host_lifecycle import private_file, sync_directory
from .public_host_lifecycle import isolated_directory
from .standard_quarantine import exclusive

KIND='post_disposition_maintenance_load_v1'
BOUNDARY={**prior.BOUNDARY,'oldLoadRearmed':False,'newProjectCreated':False,
    'phaseExpiryChanged':False,'usageCollected':False,'planningAuthorized':False,
    'historicalPredecessorOutcome':'unknown_preserved'}
FIELDS={'version','kind','sourceHash','interpreter','context','scope','journal','boundary'}
OLD_RECORDS={'intent.json','load.claim.json','load-ack.json','observation.json','outcome.json'}
NON_REVIEWS={'auth.json','.credentials.json','.env'}


def location(registry,original):
    key=digest({'ledger':original['databases']['target']['identity'],
        'brain':original['brainId'],'command':original['command']['id']})
    return registry.root/'post-disposition-loads'/key


def context(registry,ledger,planning_file,load_file,legacy_source=None):
    # No budget(), planning.current(), native connection or usage collection.
    # Expiry is preserved, not waived for any model work: this control has none.
    require(all(Path(p).name not in NON_REVIEWS for p in (planning_file,load_file)),
        'Credential files cannot be review inputs')
    lineage,parent,_=lifecycle.predecessor(registry,ledger,planning_file,legacy_source)
    original=parent['original']; old=prior.read_review(load_file); before=old['provenance']['original']
    require(str(prior.location(registry,before))==old['journal'],'Canonical original load required')
    result=prior.status(old); inventory=lifecycle.inventory(old['journal'])
    require(result['status']=='load_observed_idle' and result['connectionClosed'] is True and
        {Path(p).name for p in inventory}==OLD_RECORDS,
        'Require a positively closed original load, never an unknown/partial/stopped attempt')
    require(before['dispositionHash'] is None and original['dispositionHash'] is not None and
        all(before[k]==original[k] for k in ('workspaceId','root','brainId','command','bindingFile',
            'bindingPin','bindingEpoch','scope')) and
        before['databases']['target']['identity']==original['databases']['target']['identity'] and
        before['databases']['registry']==original['databases']['registry'],
        'Same original brain, dual project identities, command, database and binding required')
    # A separately retained usage report may have preceded disposition. Retain
    # both original snapshots; it never grants a refund or a new measurement.
    accounting={'brainObservedTokens','brainUsageCoverage','usageHighWater','usageReport','revision','updatedAt'}
    require({k:v for k,v in before['run'].items() if k not in accounting}==
        {k:v for k,v in original['run'].items() if k not in accounting},'Original phase scope/limits/expiry changed')
    require(old['candidateFile']==parent['candidateFile'] and old['candidatePin']==parent['candidatePin'] and
        old['provenance']['scope']['binding']==parent['candidateBinding'],
        'Same reviewed candidate bytes/epoch required; no host migration or rebind')
    require(planning.pin(parent['candidateFile'])==parent['candidatePin'] and
        prior._read_binding(parent['candidateFile'])==parent['candidateBinding'] and
        planning.package_epochs(parent['package'])==parent['packageEpochs']==old['provenance']['packageEpochs'],
        'Actual candidate binding or native package epoch changed')
    planning.transport.validate_contract(parent['transport'],parent['candidateBinding'],original['brainId'])
    issued=prior.issued_provenance(registry,ledger,old['provenance']['launchFile'],historical=True)
    require(issued==old['provenance'],'Issued host, package, history, credentials metadata or process changed')
    require(not os.path.lexists(continuous.location(registry,parent)) and
        all(not os.path.lexists(p) for p in lifecycle.locations(registry,original)),
        'Existing/partial successor or continuous owner fences maintenance; never adopt it')
    data={'lineage':lineage,'originalHash':digest(original),'loadFile':str(load_file),
        'loadPin':planning.pin(load_file),'loadHash':digest(old),'loadInventory':inventory,
        'loadOutcomeHash':digest(result),'issuedProvenanceHash':digest(issued)}
    return data,parent,old


def prepare(registry,ledger,planning_file,load_file,*,legacy_source=None):
    data,parent,old=context(registry,ledger,planning_file,load_file,legacy_source)
    root=location(registry,parent['original'])
    require(not os.path.lexists(root),'Maintenance attempt already consumed; no recursive/new-ID successor')
    q={'version':1,'kind':KIND,'sourceHash':planning.old.source_hash(),'interpreter':planning.interpreter(),
        'context':data,'scope':old['provenance']['scope'],'journal':str(root),'boundary':dict(BOUNDARY)}
    require(valid(q),'Closed bounded maintenance review required')
    return {'request':q,'reviewHash':digest(q),'validUntil':'scope_changes',
        'effect':'One NEW metadata-only load on the same existing host/brain; no old-claim retry, model turn, clock extension or phase continuation',
        'boundary':dict(BOUNDARY)}


def valid(q):
    return (isinstance(q,dict) and set(q)==FIELDS and type(q['version']) is int and q['version']==1 and
        q['kind']==KIND and q['boundary']==BOUNDARY and isinstance(q['context'],dict) and
        set(q['context'])=={'lineage','originalHash','loadFile','loadPin','loadHash','loadInventory',
            'loadOutcomeHash','issuedProvenanceHash'} and isinstance(q['scope'],dict) and
        len(canonical(q).encode())<=62000)


def read_review(file):
    require(Path(file).name not in NON_REVIEWS,'Credential files cannot be maintenance reviews')
    pin=planning.pin(file); q=planning._read_private(file)
    require(valid(q) and planning.pin(file)==pin,'Exact private maintenance review required')
    return q


def current(registry,ledger,q):
    require(valid(q) and q['sourceHash']==planning.old.source_hash() and q['interpreter']==planning.interpreter(),
        'Maintenance implementation or interpreter changed')
    c=q['context']; line=c['lineage']; proof=line['sourceProof']
    actual,parent,old=context(registry,ledger,line['parentFile'],c['loadFile'],None if proof is None else proof['root'])
    require(actual==c and q['scope']==old['provenance']['scope'] and
        str(location(registry,parent['original']))==q['journal'],'Exact same-project maintenance scope changed')
    require(not os.path.lexists(Path(q['journal'])/'stop.json'),'Owner stop fences maintenance')
    return parent,old


def backup_files(q):
    c=q['context']; parent=planning.read_review(c['lineage']['parentFile']); old=prior.read_review(c['loadFile'])
    files=set(planning.backup_files(parent))|set(c['lineage']['files'])|set(c['loadInventory'])|{c['loadFile']}
    files.update(p['path'] for p in old['provenance']['launchPins'])
    require(len(files)<=256 and all(Path(p).name not in ('auth.json','.credentials.json','.env') for p in files),
        'Bounded non-credential original evidence archive required')
    return sorted(files)


def backup(registry,ledger,q,destination,*,writers_stopped=False):
    require(writers_stopped is True,'Quiesce all ledger writers before backup')
    parent,old=current(registry,ledger,q); original=parent['original']
    root=Path(destination); planning.old.private_path(root.parent,existing=True)
    protected=[Path(original['root']),registry.root,Path(old['provenance']['home']),Path(q['scope']['cwd']),
        Path(old['provenance']['launchFile']).parent,Path(q['scope']['binding']['endpoint']['executable']).parent.parent]
    require(root.is_absolute() and root.resolve()==root and not os.path.lexists(root) and
        all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in protected),
        'New private disjoint backup outside protected state required')
    root.mkdir(mode=0o700); records={}
    for key,file in (('target',ledger.db),('registry',registry.db)):
        target=root/(key+'.sqlite3'); os.close(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        with planning.standard.read_db(file) as source,contextlib.closing(sqlite3.connect(target)) as copy:
            source.backup(copy); require(copy.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Backup integrity failed')
        require(planning.partial.database_proof(target)['fingerprint']==original['databases'][key]['fingerprint'],'Backup differs')
        with target.open('rb') as stream: os.fsync(stream.fileno())
        records[target.name]=planning.old.prior.database_epoch(target)
    for i,file in enumerate(backup_files(q)):
        before=planning.archive_pin(file); target=root/('private-'+str(i)+'.bin')
        with os.fdopen(os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as stream:
            stream.write(Path(file).read_bytes()); stream.flush(); os.fsync(stream.fileno())
        require(planning.archive_pin(file)==before and planning.archive_pin(target)['sha256']==before['sha256'],
            'Original archive changed')
        records[target.name]=planning.archive_pin(target)
    current(registry,ledger,q)
    exclusive(root/'manifest.json',{'kind':KIND,'reviewHash':digest(q),'files':records})
    return {'backup':str(root),'verified':True,'reviewHash':digest(q)}


def verify_backup(q,root):
    root=planning.old.private_path(root,existing=True); m=planning._read_private(root/'manifest.json')
    files=backup_files(q); original=planning.read_review(q['context']['lineage']['parentFile'])['original']
    require(set(m)=={'kind','reviewHash','files'} and m['kind']==KIND and m['reviewHash']==digest(q) and
        set(m['files'])=={'target.sqlite3','registry.sqlite3'}|{'private-'+str(i)+'.bin' for i in range(len(files))},
        'Complete exact verified backup required')
    for name,pin in m['files'].items():
        actual=planning.old.prior.database_epoch(root/name) if name.endswith('.sqlite3') else planning.archive_pin(root/name)
        require(actual==pin,'Backup bytes or epoch changed')
    for key in ('target','registry'):
        proof=planning.partial.database_proof(root/(key+'.sqlite3'))
        require(proof['fingerprint']==original['databases'][key]['fingerprint'] and
            proof['identity']!=original['databases'][key]['identity'],'Aliased/changed backup database')
    for i,file in enumerate(files):
        require(planning.archive_pin(root/('private-'+str(i)+'.bin'))['sha256']==planning.archive_pin(file)['sha256'],
            'Every original record must be preserved')


def confirm(registry,ledger,q,confirmation_hash,*,writers_stopped=False,backup_root=None):
    require(valid(q) and confirmation_hash==digest(q) and writers_stopped is True and backup_root is not None,
        'Exact new maintenance review, stopped writers and verified backup required')
    current(registry,ledger,q); verify_backup(q,backup_root); root=Path(q['journal'])
    with planning.partial.lock(registry.db),planning.partial.lock(ledger.db):
        current(registry,ledger,q)
        root.parent.mkdir(mode=0o700,exist_ok=True); isolated_directory(root.parent); sync_directory(root.parent.parent)
        root.mkdir(mode=0o700); sync_directory(root.parent)
        exclusive(root/'intent.json',{'kind':KIND,'reviewHash':digest(q)})
    proxy=None; observed=False
    def guard():
        current(registry,ledger,q); isolated_directory(root)
        require(planning._read_private(root/'intent.json')=={'kind':KIND,'reviewHash':digest(q)} and
            {Path(p).name for p in lifecycle.inventory(root)}<={'intent.json','load.claim.json','load-ack.json'},
            'Original maintenance ownership changed or ended; no adoption or load')
        if (root/'load.claim.json').exists():
            require(planning._read_private(root/'load.claim.json')=={'reviewHash':digest(q),
                'paramsHash':digest(prior.inspection.load_params(q['scope']))},'Exact original load claim changed')
        if (root/'load-ack.json').exists():
            require((root/'load.claim.json').exists() and planning._read_private(root/'load-ack.json')=={
                'reviewHash':digest(q),'acknowledged':True},'Exact load acknowledgement changed; retain unknown')
    try:
        guard()
        with prior.inspection.InspectionProxy(q['scope']) as proxy:
            before=prior.inspection.repeated(proxy,q['scope'])
            require(before['activity']=='notLoaded' and before['policy'] is None and before['trackedTerminals'] is None,
                'Exact unloaded brain required; never adopt or reload an active/loaded brain')
            guard()
            require(prior.inspection.repeated(proxy,q['scope'])==before,'Native drift before maintenance load')
            exclusive(root/'load.claim.json',{'reviewHash':digest(q),'paramsHash':digest(prior.inspection.load_params(q['scope']))})
            guard(); proxy.load_permitted=True
            reply=proxy._rpc('thread/resume',prior.inspection.load_params(q['scope']))
            thread=reply.get('thread') if isinstance(reply,dict) else None
            require(isinstance(thread,dict) and thread.get('id')==q['scope']['brainId'] and
                thread.get('cwd')==q['scope']['cwd'] and thread.get('turns',[])==[],'Load acknowledgement unknown; no retry')
            exclusive(root/'load-ack.json',{'reviewHash':digest(q),'acknowledged':True})
            after=prior.inspection.repeated(proxy,q['scope'])
            require(after['activity']=='idle' and after['trackedTerminals']==[],'Loaded policy/tracker unknown')
            guard()
            exclusive(root/'observation.json',{'reviewHash':digest(q),'observedAt':time.time(),
                'observation':after,'boundary':dict(BOUNDARY)})
            observed=True
    except (OSError,Refusal,ValueError,KeyError,TypeError,KeyboardInterrupt) as error:
        exclusive(root/'failure.json',{'reviewHash':digest(q),'errorType':type(error).__name__,'retryPermitted':False})
    closed=proxy is not None and proxy.process is None
    result={'status':'maintenance_load_observed_idle' if observed and closed else 'consumed_outcome_unknown',
        'reviewHash':digest(q),'records':{name:planning.pin(root/name) for name in
            ('load.claim.json','load-ack.json','observation.json') if (root/name).exists()},
        'connectionClosed':closed,'currentEvidence':'historical_after_attempt','boundary':dict(BOUNDARY)}
    exclusive(root/'outcome.json',result); return result


def status(q):
    """File-only history, never another connection, load, claim or observation."""
    require(valid(q),'Closed maintenance review required'); root=Path(q['journal'])
    if not os.path.lexists(root): return {'status':'not_submitted','boundary':dict(BOUNDARY)}
    require(planning._read_private(root/'intent.json')=={'kind':KIND,'reviewHash':digest(q)},'Partial maintenance claim; no retry')
    names={Path(p).name for p in lifecycle.inventory(root)}
    require(names<=OLD_RECORDS|{'failure.json','stop.json'},'Unlisted maintenance effects remain unknown')
    if not (root/'outcome.json').exists(): return {'status':'consumed_outcome_unknown','boundary':dict(BOUNDARY)}
    r=planning._read_private(root/'outcome.json')
    require(set(r)=={'status','reviewHash','records','connectionClosed','currentEvidence','boundary'} and
        r['reviewHash']==digest(q) and r['boundary']==BOUNDARY and r['currentEvidence']=='historical_after_attempt' and
        r['status'] in ('maintenance_load_observed_idle','consumed_outcome_unknown') and type(r['connectionClosed']) is bool and
        set(r['records'])<={'load.claim.json','load-ack.json','observation.json'} and
        all(planning.pin(root/name)==pin for name,pin in r['records'].items()),'Changed maintenance outcome remains unknown')
    if 'load.claim.json' in r['records']:
        require(planning._read_private(root/'load.claim.json')=={'reviewHash':digest(q),
            'paramsHash':digest(prior.inspection.load_params(q['scope']))},'Original load claim changed')
    require('load-ack.json' not in r['records'] or 'load.claim.json' in r['records'],'Uncorrelated load acknowledgement')
    if r['status']=='maintenance_load_observed_idle':
        observation=planning._read_private(root/'observation.json')
        require(r['connectionClosed'] is True and set(r['records'])=={'load.claim.json','load-ack.json','observation.json'} and
            'failure.json' not in names and
            planning._read_private(root/'load-ack.json')=={'reviewHash':digest(q),'acknowledged':True} and
            observation['reviewHash']==digest(q) and observation['boundary']==BOUNDARY and
            observation['observation']['activity']=='idle' and observation['observation']['trackedTerminals']==[] and
            prior.inspection.matches(observation['observation']['policy']),
            'Actual closed metadata observation required; never infer safety')
    return r


def stop(q,confirmation_hash):
    require(valid(q) and confirmation_hash==digest(q),'Exact maintenance review required')
    root=Path(q['journal'])
    require(planning._read_private(root/'intent.json')=={'kind':KIND,'reviewHash':digest(q)},'Exact maintenance claim required')
    exclusive(root/'stop.json',{'kind':KIND,'reviewHash':digest(q),'nativeCancelSent':False})
    return {'status':'stop_requested','nativeCancelSent':False,'boundary':dict(BOUNDARY)}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare'); a.add_argument('planning_review'); a.add_argument('prior_load_review'); a.add_argument('--legacy-source')
    for action in ('backup','confirm','status','stop'):
        a=sub.add_parser(action); a.add_argument('review')
        if action=='backup': a.add_argument('destination')
        if action in ('backup','confirm'): a.add_argument('--writers-stopped',action='store_true')
        if action=='confirm': a.add_argument('--confirm-hash',required=True); a.add_argument('--backup',required=True)
        if action=='stop': a.add_argument('--confirm-hash',required=True)
    args=p.parse_args()
    if args.action=='status': out=status(read_review(args.review))
    elif args.action=='stop': out=stop(read_review(args.review),args.confirm_hash)
    else:
        registry,ledger=planning.partial.routes(args.platform,args.workspace)
        if args.action=='prepare': out=prepare(registry,ledger,args.planning_review,args.prior_load_review,legacy_source=args.legacy_source)
        else:
            q=read_review(args.review)
            if args.action=='backup': out=backup(registry,ledger,q,args.destination,writers_stopped=args.writers_stopped)
            else: out=confirm(registry,ledger,q,args.confirm_hash,writers_stopped=args.writers_stopped,backup_root=args.backup)
    print(canonical(out))


if __name__=='__main__':
    try: main()
    except (OSError,Refusal,ValueError,KeyError,TypeError,sqlite3.Error) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
