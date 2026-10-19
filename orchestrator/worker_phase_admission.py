"""Exact-reviewed worker-phase lineage to an existing genuinely disjoint target.

Old canceled/preparation records and holds remain immutable. Admission starts
no work: only the existing separate fresh Play and loaded-only worker path apply.
"""
import argparse
import contextlib
import copy
import os
from pathlib import Path
import sqlite3
import time

from . import post_preparation_usage as usage, standard_successor as successor, standard, missions
from . import partial_admission as partial
from .core import Ledger, Refusal, canonical, digest, require
from .host_lifecycle import private_file, sync_directory
from .native_project_assignment import _registered, _read_registry
from .standard_quarantine import exclusive

KIND='post_preparation_worker_admission_v1'
FIELDS=successor.FIELDS|{'postPreparation'}
BOUNDARY={**successor.BOUNDARY,'oldClaimsRearmed':False,'oldRunClosed':False,
    'sourceBrainLoaded':False,'targetCreated':False,'oldUsageChanged':False}


def source_hash(): return usage.completion.planning.old.source_hash()


def target_reader(registry,workspace):
    root,_,_,_=_registered(registry,workspace)
    return partial.reader(root,workspace,registry.root)


def predecessor(registry,source,directory,*,local_only=False):
    result=usage.status(registry,source,directory)
    require(result['status']=='usage_observed','Qualified actual post-preparation usage required; no upload or unknown-as-zero')
    origin=result['context']; proof=origin['completionSource']
    q,_,_,_=usage.context(registry,source,origin['completionDirectory'],None if proof is None else proof['root'])
    original=q['original']; run=original['run']; info=source.db.stat()
    require(source.workspace_id==original['workspaceId'] and str(source.root)==original['root'] and
        time.time()>=run['expiresAt'],'Exact unchanged expired source run required; never extend it')
    with standard.read_db(source.db) as db: repos=successor.repositories(Ledger.all(db,'repos'),local_only=local_only)
    old={'workspaceId':source.workspace_id,'root':str(source.root),'brainId':original['brainId'],
        'ledgerIdentity':[info.st_dev,info.st_ino],'dispositionHash':original['dispositionHash'],
        'runId':run['id'],'runHash':digest(run),'observedTokens':run['brainObservedTokens'],
        'usageHighWater':run['usageHighWater'],'usageCoverage':run['brainUsageCoverage'],
        'usageReportHash':digest(run['usageReport']),'expiresAt':run['expiresAt'],
        'historicalTerminalSafety':'unknown','repositories':repos,
        'postPreparationTokens':result['report']['tokens']['total_tokens'],
        'postPreparationReportHash':digest(result['report']),
        'phaseTokenCeiling':result['remainingConservativePhaseCeiling']}
    return old,result


def context(registry,source,target,binding,directory,db,*,local_only=False):
    old,evidence=predecessor(registry,source,directory,local_only=local_only)
    request=successor.target_context(registry,source,target,binding,db,old,local_only=local_only)
    mission=missions.state_in(target,db)
    require(mission['document']['spec']['authority']['tokenBudget']<=old['phaseTokenCeiling'],
        'Target reviewed phase exceeds conservative carried brain/phase/reserve ceiling')
    request.update(kind=KIND,sourceHash=source_hash(),boundary=copy.deepcopy(BOUNDARY),
        postPreparation={'directory':str(Path(directory)),
            'evidencePin':successor.pin(Path(directory)/'evidence.json'),
            'intentPin':successor.pin(Path(directory)/'intent.json'),'evidenceHash':digest(evidence)})
    return request


def prepare(registry,source,target_id,binding,directory,*,local_only=False):
    target=target_reader(registry,target_id)
    with standard.read_db(target.db) as db:
        request=context(registry,source,target,binding,directory,db,local_only=local_only)
    require(len(canonical(request).encode())<=65536,'Bounded exact worker-admission review required')
    return {'request':request,'reviewHash':digest(request),'validUntil':'scope_changes',
        'effect':'Record disjoint worker-phase lineage only; separate target mission and fresh Play remain required',
        'nativeAction':False,'sourceHoldReleased':False,'playAuthorized':False}


def valid(request):
    return (isinstance(request,dict) and (set(request)==FIELDS or set(request)==FIELDS|{'identityPolicy'} and
        request['identityPolicy']==successor.LOCAL_POLICY) and type(request['version']) is int and request['version']==1 and
        request['kind']==KIND and request['sourceHash']==source_hash() and request['boundary']==BOUNDARY)


def read_request(file):
    file=private_file(file); before=successor.pin(file); value=usage.completion.handoff.read(file)
    require(valid(value) and successor.pin(file)==before,'Exact closed current-source admission review required')
    return value


def source_current(registry,source,request):
    p=request['postPreparation']
    require(set(p)=={'directory','evidencePin','intentPin','evidenceHash'} and
        successor.pin(Path(p['directory'])/'evidence.json')==p['evidencePin'] and
        successor.pin(Path(p['directory'])/'intent.json')==p['intentPin'],'Exact post-preparation evidence changed')
    old,evidence=predecessor(registry,source,p['directory'],local_only=request.get('identityPolicy')==successor.LOCAL_POLICY)
    require(old==request['source'] and digest(evidence)==p['evidenceHash'],'Preserve source rows, holds and carried numeric usage')


def backup_inputs(registry,source,request):
    # All registered databases are preserved, not just the new target. No auth,
    # native databases or arbitrary evidence paths are discovered/copied.
    with _read_registry(registry) as db: rows=list(db.execute('SELECT id,root FROM workspaces'))
    require(len(rows)<=32,'Bounded complete registry required')
    databases=[registry.db,*[partial.reader(Path(r['root']),r['id'],registry.root).db for r in rows]]
    require(len(set(databases))==len(databases),'Database aliases refuse admission backup')
    p=request['postPreparation']; evidence=usage.status(registry,source,p['directory'])
    old=evidence['context']; proof=old['completionSource']
    q,_,_,_=usage.context(registry,source,old['completionDirectory'],None if proof is None else proof['root'])
    files=set(usage.completion.handoff.backup_files(q))|{request['bindingFile'],
        str(Path(p['directory'])/'intent.json'),str(Path(p['directory'])/'evidence.json'),
        str(Path(old['completionDirectory'])/'intent.json'),str(Path(old['completionDirectory'])/'evidence.json')}
    files.update(str(path) for path in Path(q['journal']).iterdir())
    files.update(str(path) for path in usage.completion.handoff.phase.owner_root(q).iterdir())
    require(len(files)<=256,'Bounded exact non-credential sidecars required')
    return databases,sorted(files)


def backup(registry,source,request,root,*,writers_stopped=False):
    require(valid(request) and writers_stopped is True,'Exact review and explicitly quiesced writers required')
    target=target_reader(registry,request['target']['workspaceId'])
    with standard.read_db(target.db) as db:
        require(context(registry,source,target,request['bindingFile'],request['postPreparation']['directory'],db,
            local_only=request.get('identityPolicy')==successor.LOCAL_POLICY)==request,'Admission scope changed')
    root=Path(root); usage.completion.planning.old.private_path(root.parent,existing=True)
    databases,files=backup_inputs(registry,source,request)
    protected=[registry.root,source.root,target.root,Path(request['bindingFile']),Path(__file__).resolve().parent.parent,
        *[p.parent for p in databases],*[Path(p) for p in files]]
    require(root.is_absolute() and root.resolve()==root and not os.path.lexists(root) and
        all(not root.is_relative_to(p) and not p.is_relative_to(root) for p in protected),
        'New disjoint private backup directory required')
    root.mkdir(mode=0o700); entries=[]
    for i,path in enumerate(databases):
        before=partial.database_proof(path); name='db-'+str(i)+'.sqlite3'; copied=root/name
        os.close(os.open(copied,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600))
        with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as src,contextlib.closing(sqlite3.connect(copied)) as dst:
            src.backup(dst)
            dst.execute('PRAGMA journal_mode=DELETE')  # Normalize the COPY only; no original pragma/write.
        require(partial.database_proof(copied)['fingerprint']==before['fingerprint'] and
            partial.database_proof(path)==before,'Exact fresh database backup required')
        entries.append({'type':'database','original':str(path),'before':before,'copy':name})
    for i,path in enumerate(files):
        before=successor.pin(path); name='file-'+str(i)+'.bin'; copied=root/name
        raw=private_file(path).read_bytes()
        with os.fdopen(os.open(copied,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        require(successor.pin(path)==before and successor.pin(copied)['sha256']==before['sha256'],'Sidecar backup changed')
        entries.append({'type':'file','original':path,'before':before,'copy':name})
    parts=[]
    for i in range(0,len(entries),8):
        file=root/('part-'+str(i//8)+'.json'); exclusive(file,{'entries':entries[i:i+8]}); parts.append(successor.pin(file))
    exclusive(root/'manifest.json',{'kind':KIND,'reviewHash':digest(request),'parts':parts})
    sync_directory(root); verify_backup(registry,source,request,root)
    with standard.read_db(target.db) as db:
        require(context(registry,source,target,request['bindingFile'],request['postPreparation']['directory'],db,
            local_only=request.get('identityPolicy')==successor.LOCAL_POLICY)==request,'Admission changed during backup')
    return {'backup':str(root),'databases':len(databases),'files':len(files),'nativeAction':False}


def verify_backup(registry,source,request,root):
    root=Path(root); usage.completion.planning.old.private_path(root,existing=True)
    manifest=usage.completion.handoff.read(root/'manifest.json')
    require(isinstance(manifest,dict) and set(manifest)=={'kind','reviewHash','parts'} and manifest['kind']==KIND and
        manifest['reviewHash']==digest(request),'Exact private admission backup required')
    databases,files=backup_inputs(registry,source,request); seen_db=[]; seen_files=[]; names={'manifest.json'}
    require(isinstance(manifest['parts'],list) and len(manifest['parts'])==(len(databases)+len(files)+7)//8,
        'Bounded complete backup parts required')
    for i,pin in enumerate(manifest['parts']):
        file=root/('part-'+str(i)+'.json'); require(successor.pin(file)==pin,'Backup part changed')
        names.add(file.name); part=usage.completion.handoff.read(file)
        require(isinstance(part,dict) and set(part)=={'entries'} and isinstance(part['entries'],list) and
            1<=len(part['entries'])<=8,'Closed bounded backup part required')
        for row in part['entries']:
            require(isinstance(row,dict) and set(row)=={'type','original','before','copy'},'Closed backup entry required')
            expected=('db-'+str(len(seen_db))+'.sqlite3' if row['type']=='database' else 'file-'+str(len(seen_files))+'.bin')
            require(row['copy']==expected and expected not in names,'Exact unique backup copy required')
            names.add(expected)
            copied=root/row['copy']; require(copied.parent==root and copied.resolve(strict=True)==copied,'No backup aliases')
            if row['type']=='database':
                original=Path(row['original']); seen_db.append(original)
                require(partial.database_proof(original)==row['before'] and
                    partial.database_proof(copied)['fingerprint']==row['before']['fingerprint'],'Database backup drifted')
            else:
                require(row['type']=='file','Unsupported backup entry'); seen_files.append(row['original'])
                require(successor.pin(row['original'])==row['before'] and
                    successor.pin(copied)['sha256']==row['before']['sha256'],'Sidecar backup drifted')
    require(seen_db==databases and seen_files==files,'Complete exact backup inventory required')
    require({p.name for p in root.iterdir()}==names,'Unlisted backup contents refused')


def confirm(registry,source,request,confirmed_hash,*,writers_stopped=False,backup_root=None):
    require(valid(request) and digest(request)==confirmed_hash and writers_stopped is True and backup_root is not None,
        'Exact owner review, stopped writers and verified private backups required')
    require(source.workspace_id==request['source']['workspaceId'] and str(source.root)==request['source']['root'],
        'Exact registered source required')
    target=target_reader(registry,request['target']['workspaceId'])
    with standard.read_db(target.db) as db:
        if os.path.lexists(target.root/successor.FENCE):
            previous=retained_in(target,db)
            require(previous['request']==request,'Another or partial admission remains fenced')
            return successor.public(previous)
    verify_backup(registry,source,request,backup_root)
    with partial.lock(registry.db),partial.lock(target.db) as db:
        require(context(registry,source,target,request['bindingFile'],request['postPreparation']['directory'],db,
            local_only=request.get('identityPolicy')==successor.LOCAL_POLICY)==request,'Admission changed at commit boundary')
        record={'kind':KIND,'request':copy.deepcopy(request),'reviewHash':confirmed_hash,
            'recordedAt':time.time(),'outcome':'lineage_recorded_play_not_started'}
        key=digest(record)
        # Fence the source FIRST: even failure before the target marker cannot
        # turn another target/review into a retry of this admission.
        exclusive(successor.source_claim(registry.root,source.workspace_id),
            {'kind':KIND,'target':target.workspace_id,'recordHash':key})
        exclusive(target.root/successor.FENCE,{'kind':KIND,'recordHash':key,'reviewHash':confirmed_hash})
        db.execute('INSERT INTO snapshots(id,kind,data) VALUES(?,?,?)',(key,KIND,canonical(record)))
        meta=Ledger.get(db,'meta',1)
        meta.update(schemaVersion=7,successorLedgerVersion=1,standardSuccessor=key,revision=meta['revision']+1)
        Ledger.put(db,'meta',1,meta); db.commit()
    return successor.public(record)


def retained_in(ledger,db,meta=None):
    meta=meta or Ledger.get(db,'meta',1); marker=usage.completion.handoff.read(ledger.root/successor.FENCE)
    require(set(marker)=={'kind','recordHash','reviewHash'} and marker['kind']==KIND and
        meta.get('schemaVersion')==7 and meta.get('successorLedgerVersion')==1 and
        meta.get('standardSuccessor')==marker['recordHash'],'Partial worker admission stays fenced')
    record=Ledger.get(db,'snapshots',marker['recordHash']); req=record['request']; target=req['target']
    require(valid(req) and record['kind']==KIND and record['outcome']=='lineage_recorded_play_not_started' and
        digest(record)==marker['recordHash'] and digest(req)==marker['reviewHash']==record['reviewHash'],
        'Exact current-source worker admission receipt required')
    registry,source=partial.routes(ledger.platform_root,req['source']['workspaceId'])
    source_current(registry,source,req)
    info=ledger.db.stat(); ri=registry.db.stat()
    require(ledger.workspace_id==target['workspaceId'] and str(ledger.root)==target['root'] and
        meta['brainId']==target['brainId'] and [info.st_dev,info.st_ino]==target['ledgerIdentity'] and
        [ri.st_dev,ri.st_ino]==target['registryIdentity'],'Exact registered target/registry/database identities required')
    registered,inspected,_,_=_registered(registry,ledger.workspace_id)
    require(registered==ledger.root and inspected['brainId']==target['brainId'],'Registered target mapping changed')
    partial.private_database(ledger.db)
    require(successor.repositories(Ledger.all(db,'repos'),local_only=req.get('identityPolicy')==successor.LOCAL_POLICY)==
        target['repositories'],'Target repository identity changed')
    successor.disjoint(req['source']['repositories'],target['repositories'])
    # Cross-workspace exclusion is rechecked by the existing effect/loaded-only
    # send gates. A late foreign owner must not prevent recording local Pause.
    require(successor.pin(req['bindingFile'])==req['bindingPin'] and
        digest(successor._read_binding(req['bindingFile']))==target['bindingHash'],'Target binding changed; no fallback')
    outgoing=usage.completion.handoff.read(successor.source_claim(registry.root,source.workspace_id))
    require(outgoing=={'kind':KIND,'target':target['workspaceId'],'recordHash':marker['recordHash']},
        'Missing, foreign or partial source admission claim stays fenced')
    mission=missions.state_in(ledger,db)
    require(mission['effectiveStatus']=='reviewed' and mission['documentHash']==target['missionHash'] and
        mission['receiptHash']==target['missionReviewHash'] and
        mission['document']['spec']['authority']['tokenBudget']<=req['source']['phaseTokenCeiling'],
        'Exact target mission and carried accounting ceiling required')
    run=meta.get('standardRun')
    if run:
        require(run.get('successorHash')==marker['recordHash']==run.get('ownerReceipt',{}).get('successorHash'),
            'Only its separately confirmed fresh target Play is supported')
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='action',required=True)
    c=sub.add_parser('prepare'); c.add_argument('target'); c.add_argument('binding'); c.add_argument('usage'); c.add_argument('--local-only',action='store_true')
    b=sub.add_parser('backup'); b.add_argument('review'); b.add_argument('directory'); b.add_argument('--writers-stopped',action='store_true')
    c=sub.add_parser('confirm'); c.add_argument('review'); c.add_argument('--confirm-hash',required=True); c.add_argument('--backup',required=True); c.add_argument('--writers-stopped',action='store_true')
    sub.add_parser('status')
    args=p.parse_args(); registry,source=partial.routes(args.platform,args.workspace)
    if args.action=='prepare': result=prepare(registry,source,args.target,args.binding,args.usage,local_only=args.local_only)
    elif args.action=='backup': result=backup(registry,source,read_request(args.review),args.directory,writers_stopped=args.writers_stopped)
    elif args.action=='confirm': result=confirm(registry,source,read_request(args.review),args.confirm_hash,writers_stopped=args.writers_stopped,backup_root=args.backup)
    else:
        with standard.read_db(source.db) as db: result=successor.public(retained_in(source,db))
    print(canonical(result))


if __name__=='__main__':
    try: main()
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
