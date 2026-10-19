"""Compiled transferred usage, loopback only; never reads a live home.

Native lifecycle and numeric response journal are real. Original admission,
permission disposition, provenance, short expiry and baselines are labelled
disposable fixture setup, not imported live authority or provider billing.
"""
import argparse
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SOURCE),str(SOURCE/'tests')]
import qualify_canceled_continuation as fixture
import qualify_host_transfer_handoff as transfer_fixture
from orchestrator import post_preparation_usage as usage, handoff_reconciliation as completion
from orchestrator import brain_memory, standard
from orchestrator.core import canonical,require
from orchestrator.partial_admission import database_proof
from orchestrator.standard_quarantine import exclusive


def qualify(package,evidence):
    real_time=time.time; original_usage=fixture.mailbox.RunMailboxTest.write_usage
    original_transfer=transfer_fixture.qualify_transfer; result={}
    def setup_numeric(f,*args,**kwargs):
        original_usage(f,*args,**kwargs)
        home=f.root/'native-home'
        paths=list((home/'sessions').rglob('*'+f.brain+'*.jsonl'))
        require(len(paths)==1,'One exact disposable native session required')
        header=json.loads(paths[0].read_bytes().splitlines()[0])
        at=brain_memory.stamp(header['timestamp']); require(at is not None,'Dated native header required')
        # Before any fixture disposition/usage/continuation capture, align its
        # synthetic run interval with the genuinely created native session.
        with f.ledger.tx() as db:
            meta=f.ledger.get(db,'meta',1); run=meta['standardRun']
            require(run.get('usageHighWater') is None,'Never reset previously retained consumption')
            run.update(startedAt=at-.001,expiresAt=real_time()+5)
            f.ledger.put(db,'meta',1,meta); f.run=run
        f.home=home
        (f.ledger.root/'observations.json').write_text(canonical({'codexHome':str(home),'artifactRoots':[],'roadmaps':[]}))
        for path in paths: path.chmod(0o600)
    def after_transfer(owner,package,evidence,calls,maintenance_q,*args,**kwargs):
        # Expire only this synthetic short clock before the existing fixture's
        # fixed wall-clock injection. New native samples must actually be later.
        with standard.read_db(owner.ledger.db) as db:
            expires=owner.ledger.get(db,'meta',1)['standardRun']['expiresAt']
        wait=expires+1-real_time()
        require(wait<=10,'Finite disposable clock only')
        if wait>0: time.sleep(wait)
        prior=original_transfer(owner,package,evidence,calls,maintenance_q,*args,**kwargs)
        registry,ledger=owner.registry,owner.ledger
        before=[database_proof(p) for p in (registry.db,ledger.db)]
        q=json.loads((Path(evidence)/'transfer-attempt.json').read_bytes())['review']['request']
        pins=completion.handoff.phase.consumer_inventory(q)
        old=completion.handoff.status(q); native_methods=[]; proxy=completion.Probe
        class ReadOnly(proxy):
            def _rpc(self,method,params):
                native_methods.append(method); return super()._rpc(method,params)
        directory=owner.f.root/'post-preparation-usage'
        home=Path(completion.handoff.transfer_record(q)['destinationHost']['home'])
        # Same explicit loopback overlay as the original fixture's launch;
        # production's fixed restricted configuration is not changed.
        with patch('time.time',side_effect=real_time),patch.object(completion,'Probe',ReadOnly),\
             patch.object(completion.handoff.launch,'CONFIG',(home/'config.toml').read_text()):
            observed=usage.collect(registry,ledger,owner.f.root/'independent-completion',directory)
            require(observed['status']=='usage_observed','Compiled numeric evidence failed: '+canonical(observed))
            require(usage.status(registry,ledger,directory)==observed,'Saved numeric evidence changed')
        require(set(native_methods)=={'initialize','account/read','project/read','thread/read','thread/turns/list'} and
            native_methods.count('initialize')==1 and len(calls)==3 and
            observed['report']['records'][0]['counterSource']=='native_response_usage_v1' and
            observed['report']['tokens']['total_tokens']>q['original']['run']['usageHighWater'] and
            before==[database_proof(p) for p in (registry.db,ledger.db)] and
            pins==completion.handoff.phase.consumer_inventory(q) and old==completion.handoff.status(q),
            'Usage read changed authority/claims, reloaded/replayed, refunded counters or used legacy fallback')
        result.update(qualifiedCompiledPostPreparationUsage=True,qualifiedSourceHash=usage.completion.planning.old.source_hash(),
            completedNativeStatus=observed['native']['nativeStatus'],tokens=observed['report']['tokens'],
            counterSource=observed['report']['records'][0]['counterSource'],nativeMethods=native_methods,
            liveNativeConnections=0,nativeLoadsDuringEvidence=0,newTurnsDuringEvidence=0,provider='loopback_fake_only',
            originalLedgerAndExpiry='synthetic_fixture_aligned_before_capture',
            numericTelemetry='real_compiled_response_journal_from_fake_provider_not_billing',
            claimsAndUsagePreserved=True,terminalSafety='unknown',bindingInstalled=False)
        exclusive(Path(evidence)/'post-preparation-usage.json',observed)
        exclusive(Path(evidence)/'worker-usage-summary.json',result)
        return {**prior,**result}
    with patch.object(fixture.mailbox.RunMailboxTest,'write_usage',setup_numeric),\
         patch.object(transfer_fixture,'qualify_transfer',after_transfer):
        fixture.qualify(package,evidence,transfer_reconciliation=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--package',required=True); p.add_argument('--evidence',required=True)
    args=p.parse_args(); print(canonical(qualify(args.package,args.evidence)))
