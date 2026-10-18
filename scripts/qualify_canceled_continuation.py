"""Production control + compiled native sandbox, disposable loopback provider only.

The old ledger is a labelled synthetic canceled-Play fixture, not imported live
evidence. Its identity matches a genuinely canceled disposable native turn.
No account, live host, old request, reload, replay or external model is used.
"""
import argparse
import copy
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
from orchestrator import canceled_continuation as api, brain_memory, public_host_runtime
from orchestrator.core import Ledger, canonical, digest, require
from orchestrator.host_lifecycle import write_record
from orchestrator.native_read_client import inspect_endpoint
from orchestrator.public_host_lifecycle import CONFIG, environment
from orchestrator.partial_admission import database_proof
from orchestrator.standard_quarantine import exclusive
from qualify_no_reload_transport import FixtureProxy
import test_canceled_play as fixtures
import test_standard_run_mailbox as mailbox


def qualify_reviewed_load(owner,package,evidence,processes,creators,calls):
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
    summary={'qualifiedProductionMetadataLoad':True,'package':package,'provider':'loopback_fake_only',
        'launchProvenance':'synthetic_fixture_only_unit_qualified_separately','nativeLoads':1,'warmModelRequests':0,
        'fakeProviderRequests':len(calls),'methodCounts':{m:methods.count(m) for m in sorted(set(methods))},
        'originalSyntheticLedgerPreserved':True,'originalBindingPreserved':True,'liveNativeConnections':0,
        'boundary':dict(load.BOUNDARY)}
    exclusive(evidence/'summary.json',summary)
    return summary


def qualify(package,evidence,*,reviewed_load=False,forward_usage_evidence=False):
    require(not (reviewed_load and forward_usage_evidence),'Separate qualification modes required')
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
    base=mailbox.RunMailboxTest.setUp; native_process=[]; creators=[]
    def native_setup(f):
        home=f.root/'native-home'; ipc=f.root/'native-ipc'
        for path in (home,ipc): path.mkdir(mode=0o700)
        (home/'config.toml').write_text('model = "gpt-6-astra"\nmodel_provider = "followup_fixture"\n'+CONFIG+f'''
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
            return qualify_reviewed_load(owner,package,evidence,native_process,creators,calls)
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
            result=api.confirm(registry,ledger,q,review['reviewHash'],writers_stopped=True,backup_root=backup)
        failure=Path(q['journal'])/'failure.json'
        exclusive(evidence/'attempt.json',{'result':result,'methods':methods,
            'failure':json.loads(failure.read_bytes()) if failure.exists() else None})
        exclusive(evidence/'native-events.json',{'events':native})
        if result['status']!='planning_completed':
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
        exclusive(evidence/'summary.json',summary)
        return summary
    finally:
        for creator in creators: creator.__exit__(None,None,None)
        for process in native_process:
            if process.poll() is None: process.terminate(); process.wait(timeout=10)
        owner.doCleanups(); server.shutdown(); server.server_close(); thread.join(5)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--package',required=True); p.add_argument('--evidence',required=True)
    p.add_argument('--reviewed-load',action='store_true',help='Separate cold/warm metadata-only load fixture; no planning turn')
    p.add_argument('--forward-usage-evidence',action='store_true',help='Separate prospective usage with immutable synthetic telemetry')
    args=p.parse_args(); print(canonical(qualify(args.package,args.evidence,reviewed_load=args.reviewed_load,
        forward_usage_evidence=args.forward_usage_evidence)))
