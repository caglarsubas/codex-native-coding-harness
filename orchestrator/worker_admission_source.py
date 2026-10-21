"""Explicit file-only continuity for a completed qualified PR185 admission.

No pending request compatibility, old-source execution, native transport or
admission retry. Every original record/hash/claim/usage observation is retained.
"""
import argparse
from pathlib import Path
import os
import time

from .core import Ledger, Refusal, SHA, canonical, digest, require
from . import historical_admission as history, worker_phase_admission as admission, standard
from .same_project_lifecycle import source_proof
from .standard_quarantine import exclusive

KIND='completed_worker_admission_source_v1'
FILE='standard-worker-admission-source.json'
BOUNDARY={'nativeAction':False,'oldRequestChanged':False,'admissionRetried':False,
          'usageReset':False,'observationRenewed':False,'bindingChanged':False,
          'playAuthorized':False,'terminalSafety':'unknown'}


def context(ledger,record,marker,root):
    q=record['request']; target=q['target']
    require(admission.shape(q) and q['sourceHash']==history.PR185_SOURCE and
            set(record)=={'kind','request','reviewHash','recordedAt','outcome'} and
            record['kind']==admission.KIND and record['outcome']=='lineage_recorded_play_not_started' and
            set(marker)=={'kind','recordHash','reviewHash'} and marker['kind']==admission.KIND and
            marker['recordHash']==digest(record) and marker['reviewHash']==record['reviewHash']==digest(q),
            'Only an exact complete PR185 worker-admission receipt qualifies; no pending or partial allowance')
    proof=source_proof(root)
    require(proof['sourceHash']==history.PR185_SOURCE,'Exact immutable qualified PR185 source bytes required')
    require(ledger.workspace_id==target['workspaceId'] and str(ledger.root)==target['root'] and
            [ledger.db.stat().st_dev,ledger.db.stat().st_ino]==target['ledgerIdentity'],
            'Original target/database identity required')
    registry,source=admission.partial.routes(ledger.platform_root,q['source']['workspaceId'])
    admission.source_current(registry,source,q,implementation_source=str(Path(root)))
    outgoing=admission.usage.completion.handoff.read(admission.successor.source_claim(registry.root,source.workspace_id))
    require(outgoing=={'kind':admission.KIND,'target':ledger.workspace_id,'recordHash':digest(record)},
            'Both complete original admission claims required')
    return {'kind':KIND,'workspaceId':ledger.workspace_id,'brainId':target['brainId'],
            'ledgerIdentity':target['ledgerIdentity'],'recordHash':digest(record),'requestHash':digest(q),
            'source':proof,'bindingPin':admission.successor.pin(q['bindingFile']),
            'markerPin':admission.successor.pin(ledger.root/admission.successor.FENCE),
            'sourceClaimPin':admission.successor.pin(admission.successor.source_claim(registry.root,source.workspace_id)),
            'boundary':dict(BOUNDARY)}


def retained_source(ledger,record,marker):
    saved=admission.usage.completion.handoff.read(ledger.root/FILE)
    require(isinstance(saved,dict) and set(saved)=={'context','qualifiedAt','qualifiedBy'} and
            isinstance(saved['qualifiedBy'],str) and SHA.fullmatch(saved['qualifiedBy']) and
            admission.usage.forward_usage.number(saved['qualifiedAt']) and saved['qualifiedAt']<=time.time(),
            'Explicit complete source-continuity qualification required; no implicit historical fallback')
    require(saved['context']==context(ledger,record,marker,saved['context']['source']['root']),
            'Completed-admission source, original records or preservation pins changed')
    return saved['context']['source']['root']


def qualify(registry,ledger,root,*,writers_stopped=False):
    require(writers_stopped is True,'Explicitly quiesced writers required for source qualification')
    require(not os.path.lexists(ledger.root/FILE),'Preserve the original source qualification; never overwrite a partial record')
    marker=admission.usage.completion.handoff.read(ledger.root/admission.successor.FENCE)
    with standard.read_db(ledger.db) as db:
        meta=Ledger.get(db,'meta',1); record=Ledger.get(db,'snapshots',marker['recordHash'])
        require(meta.get('schemaVersion')==7 and meta.get('successorLedgerVersion')==1 and
                meta.get('standardSuccessor')==marker['recordHash'] and meta.get('paused') is True and
                not any(meta.get(k) for k in ('standardRun','controller','runner','brainHandoff','admissionBinding')) and
                not any(Ledger.all(db,t) for t in ('commands','workers','queue','decisions','continuations')),
                'Only a completed empty paused admission may qualify its historical implementation')
    before=context(ledger,record,marker,root)
    proof=admission.partial.database_proof(ledger.db)
    require(context(ledger,record,marker,root)==before and admission.partial.database_proof(ledger.db)==proof,
            'Source qualification changed while read; no native action or retry')
    value={'context':before,'qualifiedAt':time.time(),'qualifiedBy':admission.source_hash()}
    exclusive(ledger.root/FILE,value)
    # Validate all normal current mapping/mission/repository/evidence gates too.
    with standard.read_db(ledger.db) as db: admission.retained_in(ledger,db)
    return {'status':'completed_admission_source_qualified','recordHash':digest(record),
            'oldRowsChanged':False,'nativeAction':False,'playAuthorized':False,'terminalSafety':'unknown'}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--platform',required=True); p.add_argument('--workspace',required=True)
    p.add_argument('action',choices=['qualify','status']); p.add_argument('source',nargs='?')
    p.add_argument('--writers-stopped',action='store_true')
    args=p.parse_args(); registry,ledger=admission.partial.routes(args.platform,args.workspace)
    if args.action=='qualify':
        require(args.source is not None,'Supply the exact immutable PR185 source explicitly')
        result=qualify(registry,ledger,args.source,writers_stopped=args.writers_stopped)
    else:
        with standard.read_db(ledger.db) as db: result=admission.successor.public(admission.retained_in(ledger,db))
    print(canonical(result))


if __name__=='__main__':
    try: main()
    except (Refusal,OSError,ValueError,KeyError,TypeError) as error:
        print(canonical({'error':str(error)})); raise SystemExit(2)
