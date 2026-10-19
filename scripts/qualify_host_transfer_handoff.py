"""Called by the finite canceled-continuation loopback fixture, never live.

Actual native two-home transfer/load/subscription/receipt is tested. The original
ledger, usage, launch journals, expired clock and preflight lineage are labelled
synthetic. No credential or external provider is accessed.
"""
import copy
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from unittest.mock import patch

from orchestrator import host_transfer_handoff as api, canceled_continuation as planning, canceled_load
from orchestrator.core import Refusal,canonical,digest,require
from orchestrator.host_lifecycle import write_record
from orchestrator.native_read_client import inspect_endpoint
from orchestrator.partial_admission import database_proof
from orchestrator.public_host_lifecycle import environment
from orchestrator.standard_quarantine import exclusive
from qualify_no_reload_transport import FixtureProxy


def qualify_transfer(owner,package,evidence,calls,maintenance_q,source_provenance,before,sidecars,
        binding_pin,old_pins,parent_pins,commands,processes,*,lost_ack=False):
    f=owner.f; registry,ledger=owner.registry,owner.ledger
    file=f.root/'completed-maintenance-transfer.json'; write_record(file,maintenance_q)
    maintenance_pins=api.phase.lifecycle.inventory(maintenance_q['journal'])
    parent=planning.read_review(maintenance_q['context']['lineage']['parentFile'])
    home=f.root/'destination-home'; ipc=f.root/'destination-ipc'
    home.mkdir(mode=0o700); ipc.mkdir(mode=0o700)
    source_home=Path(source_provenance['home']); config=(source_home/'config.toml').read_text()
    (home/'config.toml').write_text(config); (home/'config.toml').chmod(0o600)
    manifest=f.root/'destination-launch.json'; attempt=f.root/'destination-launch'; attempt.mkdir(mode=0o700)
    binary=str(Path(package['root'])/'bin/codex'); methods=[]; pipes=[]
    # Only this temporary fixture substitutes the explicit no-auth loopback
    # provider overlay for the fixed production config. Never patch live config.
    with patch.object(api.launch,'CONFIG',config):
        spec=api.launch.setup_scope(package['root'],f.repo,home,ipc); write_record(manifest,spec)
        write_record(attempt/'launch.json',{'spec':spec,'manifestHash':digest(spec),
            'reviewHash':api.launch.review_hash(spec),'mode':'exec','createdAt':time.time()})
        fd=os.open(attempt/'exec.claim',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600); os.fsync(fd); os.close(fd)
        process=subprocess.Popen([binary,'app-server','--listen','unix://'+str(ipc/'host.sock')],
            cwd=f.repo,env=environment(spec),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,start_new_session=True)
        processes.append(process); until=time.monotonic()+15
        while not (ipc/'host.sock').exists():
            require(process.poll() is None and time.monotonic()<until,'Disposable destination failed to listen'); time.sleep(.02)
        write_record(attempt/'status.json',{'status':'exec_boundary_issued','mode':'exec','profile':api.PROFILE,
            'pid':process.pid,'parentPid':os.getpid(),'observedAt':time.time(),
            'hostReady':False,'nativeToolsQualified':False,'bindingInstalled':False,'terminalSafety':'unknown','restarted':False})
        process_record=f.root/'destination-issued-process.json'
        write_record(process_record,{'pid':process.pid,'parentPid':os.getpid(),
            'processIdentity':api.fixed(['/bin/ps','-p',str(process.pid),'-o','pid=,lstart=']),
            'manifestPin':planning.pin(manifest),'fixture':'synthetic exec records bound to actual disposable PID'})
        endpoint=inspect_endpoint(binary,str((ipc/'host.sock').resolve()),'0'*64)
        with FixtureProxy(endpoint,bootstrap=True): pass
        destination=copy.deepcopy(parent['candidateBinding']); destination['endpoint']=endpoint
        destination['brains'][f.brain]['identityTransferEvidence']={'protocol':api.transfer.KIND,
            **{k:package[k] for k in ('sourceCommit','sourceTree')}}
        candidate=f.root/'destination-candidate.json'; write_record(candidate,destination)
        directory=f.root/'transfer-review'; archive=f.root/'transfer-backup'
        real=api.DestinationProxy
        class Observed(real):
            def _rpc(self,method,params):
                methods.append(method)
                if self.process is not None: pipes.append(self.process.pid)
                result=super()._rpc(method,params)
                if lost_ack and method=='thread/resume': raise OSError('Injected lost acknowledgement AFTER actual native load')
                return result
        attach=planning.transport.Subscription.attach
        def delayed(sub,claim):
            result=attach(sub,claim)
            # Every other destination client is already closed. This delay
            # exceeds its actual one-second idle-unload setting; the original
            # production load/subscription connection must retain ownership.
            time.sleep(1.5)
            require(sub._sample()['identity']['status']=={'type':'idle'},'Continuous destination owner was lost')
            return result
        with patch.object(canceled_load,'issued_provenance',return_value=source_provenance),\
             patch('time.time',return_value=parent['original']['run']['expiresAt']+1):
            review=api.prepare(registry,ledger,file,candidate,manifest,attempt,process_record,directory,
                duration_hours=1,max_tokens=100); q=review['request']
            planning.backup(registry,ledger,q,archive,writers_stopped=True)
            script='import sys;sys.path.insert(0,'+repr(str(Path(__file__).resolve().parents[1]))+');'+\
                'from orchestrator.canceled_continuation import submit;p='+repr(str(Path(q['mailbox'])/'handoff.json'))+';'+\
                'assert submit(p,"receive")["status"]=="received";'+\
                'assert submit(p,"proposal",{"summary":"Continuous new-host preparation","nextSteps":["Review the next bounded mission; no old Play"]})["status"]=="proposal_retained"'
            commands.append(shlex.join([sys.executable,'-B','-c',script]))
            with patch.object(api,'DestinationProxy',Observed),patch.object(planning.transport.Subscription,'attach',delayed):
                result=api.confirm(registry,ledger,q,digest(q),writers_stopped=True,backup_root=archive)
            exclusive(evidence/'transfer-attempt.json',{'review':review,'result':result,'methods':methods,
                'owner':{p.name:planning._read_private(p) for p in api.phase.owner_root(q).iterdir() if p.name=='failure.json'}})
            require(result['status']==('blocked_or_unknown' if lost_ack else 'planning_completed') and api.status(q)==result,
                'Compiled production transfer/handoff failed: '+canonical(result))
            require(methods.count('initialize')==methods.count('thread/resume')==methods.count('project/restoreMetadata')==1 and
                methods.count('thread/subscribe')==methods.count('turn/start')==methods.count('thread/metadata/update')==(0 if lost_ack else 1) and
                len(set(pipes))==1 and len(calls)==(1 if lost_ack else 3),'Transfer/reload/reconnect/replay or model request count differs')
            require(not set(methods)&{'thread/start','project/create','project/import','turn/interrupt','account/login/start'} and
                api.binding_review(q)['prerequisiteSatisfied'] is (not lost_ack),'Transfer introduced work, login or lost the exact result')
            try: api.confirm(registry,ledger,q,digest(q),writers_stopped=True,backup_root=archive)
            except (Refusal,OSError): pass
            else: raise Refusal('Compiled transfer/handoff was retried')
        require(before==[database_proof(p) for p in (registry.db,ledger.db)] and sidecars==planning.old.sidecars(ledger) and
            binding_pin==planning.pin(owner.binding_file) and maintenance_pins==api.phase.lifecycle.inventory(maintenance_q['journal']) and
            old_pins==api.phase.lifecycle.inventory(canceled_load.read_review(maintenance_q['context']['loadFile'])['journal']) and
            parent_pins==api.phase.lifecycle.inventory(parent['journal']),'Old fixture state was changed')
        summary={'qualifiedHostTransferContinuousHandoff':not lost_ack,'qualifiedLostLoadAcknowledgement':lost_ack,
            'qualifiedSourceHash':planning.old.source_hash(),
            'package':package,'provider':'loopback_fake_only','telemetry':'synthetic_local_numeric_fixture_only',
            'launchProvenance':'synthetic_journals_bound_to_actual_disposable_OS_process',
            'predecessorPreflightRefusal':'injected_fixture_only','expiredWallClock':'simulated_fixture_only',
            'oldMaintenanceAndLoad':'actual_disposable_compiled_metadata_reads',
            'sameBrainId':True,'sameDualProjectIds':True,'newPilotProjectCreated':False,
            'oneOriginalDestinationConnection':True,'otherDestinationSubscribersClosed':True,
            'fixtureUnloadDelaySeconds':1,'handoffDelaySeconds':0 if lost_ack else 1.5,'fixtureKeeperUsed':False,
            'destinationLoads':1,'destinationProjectRestores':1,'destinationAssignments':0 if lost_ack else 1,
            'destinationSubscriptions':0 if lost_ack else 1,'newPreparationTurns':0 if lost_ack else 1,'fakeProviderRequests':len(calls),
            'originalSyntheticLedgerPreserved':True,'originalBindingPreserved':True,'originalClaimsPreserved':True,
            'liveNativeConnections':0,'cloudRequests':0,'credentialStoresReadOrCopied':False,
            'methodCounts':{m:methods.count(m) for m in sorted(set(methods))},'boundary':dict(api.BOUNDARY)}
        exclusive(evidence/'summary.json',summary); return summary
