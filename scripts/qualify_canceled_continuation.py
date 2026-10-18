"""Production control + compiled native sandbox, disposable loopback provider only.

The old ledger is a labelled synthetic canceled-Play fixture, not imported live
evidence. Its identity matches a genuinely canceled disposable native turn.
No account, live host, old request, reload, replay or external model is used.
"""
import argparse
import copy
import contextlib
import http.server
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import uuid

SOURCE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(SOURCE),str(SOURCE/'tests')]
from orchestrator import canceled_continuation as api, brain_memory, public_host_runtime, connection_handoff, same_project_lifecycle
from orchestrator.core import Ledger, canonical, digest, require
from orchestrator.host_lifecycle import write_record
from orchestrator.native_read_client import inspect_endpoint
from orchestrator.public_host_lifecycle import CONFIG, environment
from orchestrator.partial_admission import database_proof
from orchestrator.standard_quarantine import exclusive
from qualify_no_reload_transport import FixtureProxy
import test_canceled_play as fixtures
import test_standard_run_mailbox as mailbox


def qualify_reviewed_load(owner,package,evidence,processes,creators,calls,*,maintenance_load=False):
    """Real cold/warm native load; synthetic launch provenance is labelled.

    The separate unit fixtures validate full issued-launch provenance. Here only
    that local provenance is supplied by the fixture; the production claim,
    backup, closed proxy, native resume and policy/tracker checks run unchanged.
    """
    from orchestrator import canceled_load as load
    f=owner.f; registry,ledger=owner.registry,owner.ledger
    before=[database_proof(p) for p in (registry.db,ledger.db)]
    sidecars=api.old.sidecars(ledger); original_pin=api.pin(owner.binding_file)
    for creator in creators: creator.__exit__(None,None,None)
    creators.clear()
    cold=processes[-1]; cold.terminate(); cold.wait(timeout=10)
    home=f.root/'native-home'; ipc=f.root/'warm-ipc'; ipc.mkdir(mode=0o700)
    binary=str(Path(package['root'])/'bin/codex')
    warm=subprocess.Popen([binary,'app-server','--listen','unix://'+str(ipc/'host.sock')],
        cwd=f.repo,env=environment({'codexHome':str(home)}),stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    processes.append(warm); until=time.monotonic()+15
    while not (ipc/'host.sock').exists():
        require(warm.poll() is None and time.monotonic()<until,'Disposable warm host did not listen'); time.sleep(.02)
    endpoint=inspect_endpoint(binary,str((ipc/'host.sock').resolve()),'0'*64)
    with FixtureProxy(endpoint,bootstrap=True): pass
    candidate=copy.deepcopy(owner.binding); candidate['endpoint']=endpoint
    candidate_file=f.root/'load-candidate.json'; write_record(candidate_file,candidate)
    original=api.original_context(registry,ledger,owner.binding_file,owner.cid)
    launch_dir=f.root/'synthetic-launch'; launch_dir.mkdir(mode=0o700)
    launch_file=launch_dir/'synthetic-issued-launch.json'
    write_record(launch_file,{'fixture':'synthetic launch provenance, not live authority'})
    scope={'binding':candidate,'brainId':f.brain,'projectId':f.project,'cwd':str(f.repo),
        'latestTurnId':f.turn,'latestTurnStatus':'interrupted'}
    provenance={'original':original,'launchFile':str(launch_file),'launchPins':[{'path':str(launch_file)}],
        'home':str(home),'scope':scope,'host':{'pid':warm.pid},'config':{'fixture':'loopback only'},
        'packageEpochs':api.package_epochs(package)}
    methods=[]; production=load.inspection.InspectionProxy
    class Observed(production):
        def _rpc(self,method,params):
            methods.append(method); return super()._rpc(method,params)
    with patch.object(load,'provenance',return_value=provenance):
        q=load.prepare(registry,ledger,launch_file,candidate_file)['request']
        archive=f.root/'load-backup'; load.backup(registry,ledger,q,archive,writers_stopped=True)
        with patch.object(load.inspection,'InspectionProxy',Observed):
            result=load.confirm(registry,ledger,q,digest(q),writers_stopped=True,backup_root=archive)
        require(load.status(q)==result,'Saved production load result changed')
    exclusive(evidence/'load-attempt.json',{'result':result,'methods':methods})
    require(result['status']=='load_observed_idle','Compiled native metadata-only load failed')
    require(methods.count('thread/resume')==1 and 'turn/start' not in methods and
        'turn/interrupt' not in methods and len(calls)==1,'Warm load started model work or replayed an effect')
    require(before==[database_proof(p) for p in (registry.db,ledger.db)] and sidecars==api.old.sidecars(ledger)
        and original_pin==api.pin(owner.binding_file),'Original synthetic requests/usage/claims/binding changed')
    if maintenance_load:
        return qualify_maintenance_load(owner,package,evidence,calls,q,provenance,candidate_file)
    summary={'qualifiedProductionMetadataLoad':True,'package':package,'provider':'loopback_fake_only',
        'launchProvenance':'synthetic_fixture_only_unit_qualified_separately','nativeLoads':1,'warmModelRequests':0,
        'fakeProviderRequests':len(calls),'methodCounts':{m:methods.count(m) for m in sorted(set(methods))},
        'originalSyntheticLedgerPreserved':True,'originalBindingPreserved':True,'liveNativeConnections':0,
        'boundary':dict(load.BOUNDARY)}
    exclusive(evidence/'summary.json',summary)
    return summary


def qualify_maintenance_load(owner,package,evidence,calls,old_load,provenance,candidate_file):
    """Real additional maintenance load; synthetic lineage is explicitly labelled.

    Full issued-host provenance is unit-qualified. Old load is real; parent
    preflight refusal and expired wall clock are injected fixture conditions.
    """
    from orchestrator import canceled_load as prior, maintenance_load as maintenance
    f=owner.f; registry,ledger=owner.registry,owner.ledger
    old_file=f.root/'original-load.json'; write_record(old_file,old_load)
    old_pins=same_project_lifecycle.inventory(old_load['journal'])
    for file in f.home.rglob('*.jsonl'): file.chmod(0o600)
    with ledger.tx() as db:
        meta=ledger.get(db,'meta',1); run=meta['standardRun']; report=brain_memory.collect(ledger,run)
        run.update(brainObservedTokens=report['tokens']['total_tokens'],brainUsageCoverage='observed_partial',
            usageHighWater=report['tokens']['total_tokens'],usageReport=report)
        ledger.put(db,'meta',1,meta)
        db.execute('INSERT INTO snapshots VALUES(?,?,?)',(digest(report),'standard_usage',canonical(report)))
    owner.apply()  # Separately labelled synthetic canceled-Play disposition.
    contract={'protocol':api.transport.PROTOCOL,'method':api.transport.METHOD,
        'sourceCommit':package['sourceCommit'],'sourceTree':package['sourceTree'],
        'executableSha256':package['executableHash']}
    parent=api.prepare(registry,ledger,owner.binding_file,owner.cid,candidate_file,contract,100,forward_usage_evidence=True)['request']
    parent_backup=f.root/'original-planning-backup'; api.backup(registry,ledger,parent,parent_backup,writers_stopped=True)
    with patch.object(api.transport.Subscription,'_sample',side_effect=api.Refusal(same_project_lifecycle.REFUSAL)):
        refused=api.confirm(registry,ledger,parent,digest(parent),writers_stopped=True,backup_root=parent_backup)
    require(refused['status']=='incomplete_unknown' and refused['nativeOutcome']=='unknown','Parent fixture must remain unknown')
    parent_file=f.root/'original-planning.json'; write_record(parent_file,parent)
    parent_pins=same_project_lifecycle.inventory(parent['journal'])
    before=[database_proof(p) for p in (registry.db,ledger.db)]; sidecars=api.old.sidecars(ledger)
    binding_pin=api.pin(owner.binding_file); calls_before=len(calls)
    time.sleep(1.5)  # Explicit disposable one-second unload fixture, not live waiting.
    with FixtureProxy(provenance['scope']['binding']['endpoint']) as observer:
        actual=observer._rpc('thread/read',{'threadId':f.brain,'includeTurns':False})
    require(actual['thread']['status']=={'type':'notLoaded'},'Require real unloaded native runtime before the new load')
    methods=[]; production=prior.inspection.InspectionProxy
    class Observed(production):
        def _rpc(self,method,params): methods.append(method); return super()._rpc(method,params)
    with patch.object(prior,'issued_provenance',return_value=provenance),\
         patch('time.time',return_value=parent['original']['run']['expiresAt']+1):
        reviewed=maintenance.prepare(registry,ledger,parent_file,old_file); q=reviewed['request']
        archive=f.root/'new-maintenance-backup'; maintenance.backup(registry,ledger,q,archive,writers_stopped=True)
        try: api.current(registry,ledger,parent)
        except api.Refusal as error: require('clock expired' in str(error),'Unrelated planning refusal is not expiry qualification')
        else: raise api.Refusal('Expired phase continuation unexpectedly authorized')
        with patch.object(prior.inspection,'InspectionProxy',Observed):
            result=maintenance.confirm(registry,ledger,q,digest(q),writers_stopped=True,backup_root=archive)
        require(result['status']=='maintenance_load_observed_idle' and maintenance.status(q)==result,'Compiled maintenance load failed')
        try: api.current(registry,ledger,parent)
        except api.Refusal as error: require('Maintenance load claim' in str(error),'Competing planning was not maintenance-fenced')
        else: raise api.Refusal('Maintenance silently enabled planning')
        try: maintenance.confirm(registry,ledger,q,digest(q),writers_stopped=True,backup_root=archive)
        except (OSError,api.Refusal): pass
        else: raise api.Refusal('Maintenance attempt was replayed')
    require(methods.count('thread/resume')==1 and not set(methods)&{'turn/start','turn/interrupt','thread/subscribe'} and
        len(calls)==calls_before==1,'Maintenance emitted a turn, replay, subscription or provider request')
    require(before==[database_proof(p) for p in (registry.db,ledger.db)] and sidecars==api.old.sidecars(ledger) and
        api.pin(owner.binding_file)==binding_pin and old_pins==same_project_lifecycle.inventory(old_load['journal']) and
        parent_pins==same_project_lifecycle.inventory(parent['journal']),'Original fixture history changed')
    exclusive(evidence/'maintenance-attempt.json',{'review':reviewed,'outcome':result,'methods':methods})
    summary={'qualifiedProductionMaintenanceLoad':True,'qualifiedSourceHash':api.old.source_hash(),'package':package,
        'provider':'loopback_fake_only','launchProvenance':'synthetic_fixture_only_unit_qualified_separately',
        'predecessorPreflightRefusal':'injected_fixture_only','expiredWallClock':'simulated_fixture_only',
        'actualNativeUnloadObserved':True,'nativeMaintenanceLoads':1,'maintenanceModelRequests':0,
        'fakeProviderRequests':len(calls),'newProjectsCreated':0,'liveNativeConnections':0,
        'originalSyntheticLedgerPreserved':True,'originalBindingPreserved':True,'originalLoadClaimPreserved':True,
        'originalPlanningUnknownPreserved':True,'expiredPhaseContinuationRefused':True,'maintenanceReplayRefused':True,
        'methodCounts':{m:methods.count(m) for m in sorted(set(methods))},'boundary':dict(maintenance.BOUNDARY)}
    exclusive(evidence/'summary.json',summary); return summary


def qualify(package,evidence,*,reviewed_load=False,maintenance_load=False,forward_usage_evidence=False,continuous_handoff=False,same_project_successor=False,same_project_unloaded=False):
    reviewed_load=reviewed_load or maintenance_load
    same_project_successor=same_project_successor or same_project_unloaded
    require(not (reviewed_load and (forward_usage_evidence or continuous_handoff or same_project_successor)) and
        not (continuous_handoff and same_project_successor),'Separate qualification modes required')
    forward_usage_evidence=forward_usage_evidence or continuous_handoff or same_project_successor
    evidence=Path(evidence).resolve(strict=True)
    require(not list(evidence.iterdir()) and not evidence.stat().st_mode & 0o077 and
        not evidence.is_relative_to(SOURCE),'New empty private evidence directory outside source required')
    package=public_host_runtime.inspect_package(package); binary=str(Path(package['root'])/'bin/codex')
    calls=[]; command=[]; methods=[]; native=[]
    class Provider(http.server.BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def do_POST(self):
            require(self.path=='/v1/responses','Loopback fake only')
            size=int(self.headers.get('Content-Length','0')); require(0<size<=1_000_000,'Bounded fake request')
            self.rfile.read(size); calls.append('loopback_fake')
            if len(calls)==1:
                item={'type':'function_call','name':'exec_command','call_id':'fixture-cancel',
                    'arguments':json.dumps({'cmd':'/usr/bin/true','workdir':str(owner.f.repo),
                        'sandbox_permissions':'require_escalated','justification':'Disposable Cancel fixture','max_output_tokens':100})}
            elif len(calls)==2:
                item={'type':'function_call','name':'exec_command','call_id':'fixture-new-planning-receipt',
                    'arguments':json.dumps({'cmd':command[0],'workdir':str(owner.f.repo),'max_output_tokens':1000})}
            else:
                item={'type':'message','role':'assistant','id':'fixture-proposal-message',
                    'content':[{'type':'output_text','text':'New inert proposal retained.'}]}
            events=[{'type':'response.created','response':{'id':'fixture-response'}},
                {'type':'response.output_item.done','item':item},
                {'type':'response.completed','response':{'id':'fixture-response',
                    'usage':{'input_tokens':5,'output_tokens':5,'total_tokens':10}}}]
            payload=''.join('data: '+json.dumps(row)+'\n\n' for row in events).encode()
            self.send_response(200); self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(payload))); self.end_headers(); self.wfile.write(payload)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Provider)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    owner=fixtures.CanceledPlayTest('runTest')
    base=mailbox.RunMailboxTest.setUp; native_process=[]; creators=[]; owner_thread=None; continuous=None
    def native_setup(f):
        home=f.root/'native-home'; ipc=f.root/'native-ipc'
        for path in (home,ipc): path.mkdir(mode=0o700)
        (home/'config.toml').write_text('model = "gpt-6-astra"\nmodel_provider = "followup_fixture"\n'+
            ('thread_unload_delay_secs = 1\n' if continuous_handoff or same_project_unloaded or maintenance_load else '')+CONFIG+f'''
[model_providers.followup_fixture]
name = "Disposable continuation loopback provider"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
'''); (home/'config.toml').chmod(0o600)
        process=subprocess.Popen([binary,'app-server','--listen','unix://'+str(ipc/'host.sock')],
            cwd=f.repo,env=environment({'codexHome':str(home)}),stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        native_process.append(process); deadline=time.monotonic()+15
        while not (ipc/'host.sock').exists():
            require(process.poll() is None and time.monotonic()<deadline,'Disposable host did not listen'); time.sleep(.02)
        endpoint=inspect_endpoint(binary,str((ipc/'host.sock').resolve()),'0'*64)
        creator=FixtureProxy(endpoint,bootstrap=True).__enter__(); creators.append(creator)
        project=creator._rpc('project/create',{'name':'Disposable followup fixture','roots':[{'path':str(f.repo)}],
            'idempotencyKey':str(uuid.uuid4())})['project']
        brain=creator._rpc('thread/start',{'cwd':str(f.repo),'projectId':project['id'],'ephemeral':False,
            'sandbox':'workspace-write','approvalPolicy':'on-request','approvalsReviewer':'user',
            'config':{'features':{'code_mode':{'enabled':False}}}})['thread']['id']
        turn=creator._rpc('turn/start',{'threadId':brain,'input':[{'type':'text',
            'text':'Disposable original permission fixture.','text_elements':[]}],
            'approvalPolicy':'on-request','approvalsReviewer':'user'})['turn']['id']
        creator.on_fixture_permission=lambda:None
        require(creator.completion(brain,turn,permission=True)=='interrupted','Original fixture Cancel did not end')
        return brain,project['id'],turn,endpoint
    original_initialize=Ledger.initialize
    def setup(f):
        owner.f=f; created=[]
        def initialize(ledger,spec):
            brain,project,turn,endpoint=native_setup(f); created.append((brain,project,turn,endpoint))
            spec={**spec,'brainId':brain}; f.brain,f.project=brain,project
            return original_initialize(ledger,spec)
        with patch.object(Ledger,'initialize',initialize): base(f)
        brain,project,turn,endpoint=created[0]
        row=copy.deepcopy(f.binding['brains'][f.brain]); f.brain,f.project,f.turn=brain,project,turn
        for key in ('policyEvidence','nativeTaskBackend'):
            row[key].update(sourceCommit=package['sourceCommit'],sourceTree=package['sourceTree'])
        row['projectId']=f.project; f.binding={'endpoint':endpoint,'brains':{brain:row}}
        with f.ledger.tx() as db:
            c=f.ledger.get(db,'commands',f.cid); n=c['notification']; n['nativeTurnId']=turn
            n['nativeResumeProfile'].update(brainId=brain,nativeTurnId=turn)
            n['nativeTaskContract']=row['nativeTaskBackend']; f.ledger.put(db,'commands',f.cid,c)
    try:
        temp=tempfile.TemporaryDirectory
        with patch.object(mailbox.RunMailboxTest,'setUp',setup),patch('tempfile.TemporaryDirectory',
            side_effect=lambda *a,**kw:temp(prefix='fc.',dir='/private/tmp')):
            owner.setUp()
        f=owner.f; ledger,registry=owner.ledger,owner.registry
        if reviewed_load:
            return qualify_reviewed_load(owner,package,evidence,native_process,creators,calls,maintenance_load=maintenance_load)
        with ledger.tx() as db:
            meta=ledger.get(db,'meta',1); run=meta['standardRun']
            if forward_usage_evidence:
                # Deliberately synthetic numeric logs; the native lifecycle below
                # is real, but neither side attests live/provider consumption.
                for file in f.home.rglob('*.jsonl'): file.chmod(0o600)
                report=brain_memory.collect(ledger,run)
            else:
                report={'runId':run['id'],'scopeHash':brain_memory.scope(run),'coverage':'observed_local','gaps':[],
                    'tokens':{'total_tokens':10},'collectedAt':time.time(),'through':time.time(),'records':[]}
            run.update(brainObservedTokens=report['tokens']['total_tokens'],brainUsageCoverage='observed_partial',
                usageHighWater=report['tokens']['total_tokens'])
            run['usageReport']=report; ledger.put(db,'meta',1,meta)
            db.execute('INSERT INTO snapshots VALUES(?,?,?)',(digest(report),'standard_usage',canonical(report)))
        owner.apply()  # Synthetic fixture owner disposition; no live control.
        candidate=f.root/'candidate.json'; write_record(candidate,owner.binding)
        contract={'protocol':api.transport.PROTOCOL,'method':api.transport.METHOD,
            'sourceCommit':package['sourceCommit'],'sourceTree':package['sourceTree'],
            'executableSha256':package['executableHash']}
        review=api.prepare(registry,ledger,owner.binding_file,owner.cid,candidate,contract,100,
            forward_usage_evidence=forward_usage_evidence)
        q=review['request']; backup=f.root/'prospective-backup'; api.backup(registry,ledger,q,backup,writers_stopped=True)
        before=[database_proof(p) for p in (registry.db,ledger.db)]; pins=api.old.sidecars(ledger)
        script='import sys;sys.path.insert(0,'+repr(str(SOURCE))+');from orchestrator.canceled_continuation import submit;'+\
            'p='+repr(str(Path(q['mailbox'])/'handoff.json'))+';'+\
            'assert submit(p,"receive")["status"]=="received";'+\
            'assert submit(p,"proposal",{"summary":"Disposable inert proposal","nextSteps":["Owner review only; no dispatch"]})["status"]=="proposal_retained"'
        command.append(shlex.join([sys.executable,'-B','-c',script]))
        production=api.Proxy
        class Observed(production):
            def _rpc(self,method,params):
                methods.append(method); return super()._rpc(method,params)
            def _line(self):
                row=super()._line(); native.append(row); return row
        with patch.object(api,'Proxy',Observed):
            if same_project_successor:
                # Label the historical failure as injected, not an actual native
                # unload. The current successor uses the real compiled host and
                # real restricted sandbox/connection without a fixture reload.
                parent_file=f.root/'predecessor-review.json'; write_record(parent_file,q)
                if same_project_unloaded:
                    for creator in creators: creator.__exit__(None,None,None)
                    creators.clear(); time.sleep(1.5)
                failure_fixture=(contextlib.nullcontext() if same_project_unloaded else
                    patch.object(api.transport.Subscription,'_sample',side_effect=api.Refusal(same_project_lifecycle.REFUSAL)))
                with failure_fixture:
                    parent_result=api.confirm(registry,ledger,q,review['reviewHash'],writers_stopped=True,backup_root=backup)
                require(parent_result['status']=='incomplete_unknown' and 'turn/start' not in methods and
                    'thread/subscribe' not in methods and len(calls)==1,'Injected predecessor refusal performed an effect')
                parent_pins={**same_project_lifecycle.inventory(q['journal']),**same_project_lifecycle.inventory(q['mailbox'])}
                exclusive(evidence/'predecessor-fixture.json',{'injectedPreflightRefusal':not same_project_unloaded,'nativeUnloadClaimed':same_project_unloaded,
                    'result':parent_result,'pins':parent_pins,'methods':list(methods)})
                review=same_project_lifecycle.prepare(registry,ledger,parent_file); q=review['request']
                backup=f.root/'same-project-backup'; api.backup(registry,ledger,q,backup,writers_stopped=True)
                exclusive(evidence/'successor-review.json',q)
                if same_project_unloaded:
                    methods.clear(); native.clear()
                    original_inspector=same_project_lifecycle.InspectionProxy
                    class Inspector(original_inspector):
                        def _rpc(self,method,params):
                            methods.append(method); return super()._rpc(method,params)
                    with patch.object(same_project_lifecycle,'InspectionProxy',Inspector):
                        diagnostic=same_project_lifecycle.inspect(registry,ledger,q)
                    require(diagnostic['nativeStatus']=={'type':'notLoaded'} and
                        diagnostic['blockers']==['brain_not_loaded_no_reload_authorized'] and
                        diagnostic['policy']==diagnostic['trackedTerminals']=='unknown' and
                        not diagnostic['executionAuthorized'] and not Path(q['journal']).exists() and
                        not connection_handoff.location(registry,q).exists(),'Unloaded diagnostic created authority or assumed safety')
                    require(not any(m in methods for m in ('thread/resume','thread/subscribe','turn/start','turn/interrupt')) and
                        len(calls)==1 and before==[database_proof(p) for p in (registry.db,ledger.db)] and
                        parent_pins=={**same_project_lifecycle.inventory(api.read_review(parent_file)['journal']),
                            **same_project_lifecycle.inventory(api.read_review(parent_file)['mailbox'])},'Unloaded case changed native work, claims or original rows')
                    exclusive(evidence/'diagnostic.json',diagnostic)
                    summary={'qualifiedSameProjectUnloadedDiagnostic':True,'actualNativeUnloadObserved':True,
                        'injectedPredecessorRefusal':False,'fixtureUnloadDelaySeconds':1,'fixtureWaitSeconds':1.5,
                        'provider':'loopback_fake_only','setupFakeProviderRequests':1,'diagnosticModelRequests':0,
                        'diagnosticNativeWrites':0,'usageCollections':0,'executionClaimsCreated':0,
                        'liveNativeConnections':0,'productionReloads':0,'newProjectsCreated':0,
                        'originalSyntheticLedgerPreserved':True,'predecessorUnknownPreserved':True,
                        'originalBindingPreserved':True,'methodCounts':{m:methods.count(m) for m in sorted(set(methods))},
                        'qualifiedSourceHash':api.old.source_hash(),'boundary':dict(same_project_lifecycle.BOUNDARY)}
                    exclusive(evidence/'summary.json',summary); return summary
                script='import sys;sys.path.insert(0,'+repr(str(SOURCE))+');from orchestrator.canceled_continuation import submit;'+\
                    'p='+repr(str(Path(q['mailbox'])/'handoff.json'))+';'+\
                    'assert submit(p,"receive")["status"]=="received";'+\
                    'assert submit(p,"proposal",{"summary":"Disposable same-project proposal","nextSteps":["Owner review only; no dispatch"]})["status"]=="proposal_retained"'
                command[0]=shlex.join([sys.executable,'-B','-c',script]); methods.clear(); native.clear()
                result_owner=same_project_lifecycle.confirm(registry,ledger,q,review['reviewHash'],writers_stopped=True,backup_root=backup)
                require(result_owner['status']=='planning_completed' and result_owner['connectionClosed'] and
                    same_project_lifecycle.status(registry,q)==result_owner,'Same-project owner failed: '+canonical(result_owner))
                exclusive(evidence/'successor-owner.json',result_owner)
                parent=api.read_review(parent_file)
                require(parent_pins=={**same_project_lifecycle.inventory(parent['journal']),**same_project_lifecycle.inventory(parent['mailbox'])},
                    'Predecessor bytes/epochs changed')
                result=api.status(q)
            elif continuous_handoff:
                planning_file=f.root/'planning-review.json'; write_record(planning_file,q)
                continuous=connection_handoff.prepare(registry,ledger,planning_file,60)['request']
                exclusive(evidence/'continuous-review.json',continuous)
                continuous_backup=f.root/'continuous-backup'
                connection_handoff.backup(registry,ledger,continuous,continuous_backup,writers_stopped=True)
                outcomes=[]; failures=[]
                def own():
                    try: outcomes.append(connection_handoff.serve(registry,ledger,continuous,digest(continuous),
                        writers_stopped=True,backup_root=continuous_backup))
                    except BaseException as error: failures.append(str(error))
                owner_thread=threading.Thread(target=own,daemon=True); owner_thread.start()
                until=time.monotonic()+15
                while not (Path(continuous['journal'])/'ready.json').exists():
                    require(owner_thread.is_alive() and time.monotonic()<until,
                        'Continuous fixture did not establish ownership: '+canonical(failures or outcomes))
                    time.sleep(.02)
                for creator in creators: creator.__exit__(None,None,None)
                creators.clear()
                # Real native 1-second idle-unload policy; no model keepalive,
                # resubscription or creator connection remains during this wait.
                time.sleep(1.5)
                require(len(calls)==1 and methods.count('thread/subscribe')==1 and
                    'turn/start' not in methods,'Review wait performed work or reattached')
                approval=connection_handoff.planning_review(registry,ledger,continuous)
                connection_handoff.authorize(registry,ledger,continuous,approval['request'],approval['reviewHash'])
                owner_thread.join(45)
                require(not owner_thread.is_alive() and not failures and len(outcomes)==1,
                    'Original continuous owner did not finish: '+canonical(failures))
                require(outcomes[0]['status']=='planning_completed' and outcomes[0]['connectionClosed'] is True,
                    'Continuous planning did not complete: '+canonical(outcomes))
                require(connection_handoff.status(continuous)==outcomes[0],'Continuous retained result changed')
                exclusive(evidence/'continuous-owner.json',outcomes[0])
                result=api.status(q)
                time.sleep(1.5)
                # A new read-only fixture observer is NOT an owning handoff,
                # reconnect or retry of the consumed production connection.
                with FixtureProxy(q['candidateBinding']['endpoint']) as observer:
                    metadata=observer.call('thread/read',{'threadId':f.brain,'includeTurns':False})['thread']
                require(metadata['id']==f.brain and metadata['status']=={'type':'notLoaded'},
                    'Closed fixture owner did not permit normal idle unloading')
                exclusive(evidence/'post-close-metadata.json',{'threadId':metadata['id'],'status':metadata['status'],
                    'terminalSafety':'unknown','observer':'separate disposable read-only fixture observer'})
            else:
                result=api.confirm(registry,ledger,q,review['reviewHash'],writers_stopped=True,backup_root=backup)
        failure=Path(q['journal'])/'failure.json'
        exclusive(evidence/'attempt.json',{'result':result,'methods':methods,
            'failure':json.loads(failure.read_bytes()) if failure.exists() else None})
        exclusive(evidence/'native-events.json',{'events':native})
        if result['status']!='planning_completed' and creators:
            exclusive(evidence/'fixture-only-diagnostic.json',creators[0]._rpc('thread/read',
                {'threadId':f.brain,'includeTurns':True}))
        require(result['status']=='planning_completed','Production receipt/proposal lifecycle not complete: '+canonical(result))
        require(api.status(q)==result and before==[database_proof(p) for p in (registry.db,ledger.db)] and
            pins==api.old.sidecars(ledger),'Original fixture rows/claims changed')
        require(methods.count('thread/subscribe')==methods.count('turn/start')==1 and
            not any(m in methods for m in ('thread/resume','turn/interrupt')) and len(calls)==3,
            'Not exactly one prospective subscribe/start and sandboxed receipt/proposal')
        summary={'qualifiedProductionPlanningControl':True,'provider':'loopback_fake_only','package':package,
            'methodCounts':{m:methods.count(m) for m in sorted(set(methods))},'fakeProviderRequests':len(calls),
            'nativeOutcome':result['nativeOutcome'],'receiptRetained':True,'proposalRetained':True,
            'originalSyntheticLedgerPreserved':True,'originalBindingPreserved':True,
            'nativeReloads':0,'liveNativeConnections':0,'boundary':dict(api.BOUNDARY)}
        if forward_usage_evidence:
            usage=json.loads((Path(q['journal'])/'usage.json').read_bytes())
            require(usage['baselineHash']==digest(report) and usage['report']['collectedAt']>=report['collectedAt'],
                'New usage did not preserve and advance its immutable fixture baseline')
            summary.update(qualifiedProspectiveUsage=True,telemetry='synthetic_local_numeric_fixture_only',
                oldUsageHash=digest(report),newUsageHash=digest(usage['report']))
        if continuous_handoff:
            summary.update(qualifiedContinuousHandoff=True,fixtureUnloadDelaySeconds=1,
                reviewDelaySeconds=1.5,otherSubscribersClosedBeforeReview=True,
                oneOwningConnection=methods.count('initialize')==1,
                reconnected=False,resubscribed=False,postCloseUnloadedObserved=True,
                qualifiedSourceHash=api.old.source_hash(),continuousSourceHash=connection_handoff.source_hash())
            require(summary['oneOwningConnection'],'More than one original connection')
        if same_project_successor:
            summary.update(qualifiedSameProjectSuccessor=True,predecessorFixture='injected_preflight_refusal_not_native_unload',
                predecessorUnknownPreserved=True,oneOwningConnection=methods.count('initialize')==1,
                sameBrainProjectAndBinding=True,newProjectsCreated=0,productionReloads=0,
                qualifiedSourceHash=api.old.source_hash())
            require(summary['oneOwningConnection'],'Successor changed connection')
        exclusive(evidence/'summary.json',summary)
        return summary
    finally:
        if owner_thread is not None and owner_thread.is_alive() and continuous is not None:
            try: connection_handoff.stop(continuous,digest(continuous))
            except (OSError,ValueError): pass
            owner_thread.join(5)
        for creator in creators: creator.__exit__(None,None,None)
        for process in native_process:
            if process.poll() is None: process.terminate(); process.wait(timeout=10)
        owner.doCleanups(); server.shutdown(); server.server_close(); thread.join(5)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--package',required=True); p.add_argument('--evidence',required=True)
    p.add_argument('--reviewed-load',action='store_true',help='Separate cold/warm metadata-only load fixture; no planning turn')
    p.add_argument('--maintenance-load',action='store_true',help='Separate real post-disposition maintenance load; simulated expired clock and injected historical preflight refusal')
    p.add_argument('--forward-usage-evidence',action='store_true',help='Separate prospective usage with immutable synthetic telemetry')
    p.add_argument('--continuous-handoff',action='store_true',help='Same owning connection beyond actual fixture idle-unload timeout; separate exact planning approval')
    p.add_argument('--same-project-successor',action='store_true',help='Injected historical preflight refusal, then one actual same-project compiled receipt/proposal lifecycle')
    p.add_argument('--same-project-unloaded',action='store_true',help='Actual native unload and original preflight refusal, then non-authorizing same-project diagnostic')
    args=p.parse_args(); print(canonical(qualify(args.package,args.evidence,reviewed_load=args.reviewed_load,
        maintenance_load=args.maintenance_load,
        forward_usage_evidence=args.forward_usage_evidence,continuous_handoff=args.continuous_handoff,
        same_project_successor=args.same_project_successor,same_project_unloaded=args.same_project_unloaded)))
