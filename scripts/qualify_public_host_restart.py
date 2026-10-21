"""Disposable real-native existing-home/Unix-read fixture; no live pilot.

One cold receipt uses a loopback-only provider override. The warm process reads
the same project/brain/history without loading it or making another model call.
The override is fixture-only, never accepted by the live restart launcher.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orchestrator.core import canonical, digest, require
from orchestrator.native_read_client import secure_path, inspect_endpoint
from orchestrator.public_host_lifecycle import CONFIG, environment
from orchestrator.public_host_restart import home_snapshot, signed_in_preplay_snapshot, backup_check, restricted_config, RestartReadProxy
from orchestrator.host_runtime import stamp
from orchestrator.native_auth_readiness import inspect as authentication
from qualify_public_native_tasks import StdioFixture


def qualify(binary, expected_hash, *, inspection=False, subscription_seconds=None, signed_in_preplay=False, preplay_load=False, readiness_owned=False, successor_preplay=False, prestart_startup=False):
    require(not prestart_startup or not any((inspection,signed_in_preplay,preplay_load,readiness_owned,successor_preplay,subscription_seconds)),
            'New startup qualification is a separate disposable fixture')
    require(not successor_preplay or signed_in_preplay,'Successor reopen fixture requires synthetic signed-in pre-Play metadata')
    require(not readiness_owned or not inspection and not signed_in_preplay and subscription_seconds is None,
            'Readiness-owned qualification is a separate disposable fixture')
    require(not preplay_load or inspection, 'Pre-Play load qualification requires the explicit disposable inspection fixture')
    require(not signed_in_preplay or not inspection and subscription_seconds is None,
            'The signed-in pre-Play backup fixture grants no inspection load')
    if subscription_seconds is not None:
        from orchestrator.native_subscription import duration
        duration(subscription_seconds)
        require(inspection and subscription_seconds >= 75,
                'Subscription fixture requires inspection and at least 75 seconds past the pinned 60-second grace')
    path, _ = secure_path(binary)
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash, 'Exact reviewed native fixture binary required')
    requests, processes = [], []
    readiness_hook = []
    class Provider(http.server.BaseHTTPRequestHandler):
        def do_GET(self): self.send_error(404)
        def do_POST(self):
            require(self.path == '/v1/responses', 'Only the loopback fixture response route is permitted')
            size = int(self.headers.get('Content-Length','0')); require(0 < size < 1_000_000, 'Bounded fixture request required')
            self.rfile.read(size); requests.append(self.path)
            if readiness_hook: readiness_hook[0]()
            events = [{'type':'response.created','response':{'id':'restart-fixture'}},
                {'type':'response.output_item.done','item':{'type':'message','role':'assistant','id':'receipt',
                    'content':[{'type':'output_text','text':'Retained disposable fixture receipt.'}]}},
                {'type':'response.completed','response':{'id':'restart-fixture',
                    'usage':{'input_tokens':5,'output_tokens':5,'total_tokens':10}}}]
            data = ''.join('data: '+json.dumps(row)+'\n\n' for row in events).encode()
            self.send_response(200); self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
        def log_message(self,*_): pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0),Provider)
    runner = threading.Thread(target=server.serve_forever,daemon=True); runner.start()
    def stop(process):
        if process.stdin: process.stdin.close()
        if process.stdout: process.stdout.close()
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    try:
        with tempfile.TemporaryDirectory(prefix='cpr.',dir='/private/tmp' if Path('/private/tmp').exists() else None) as temporary:
            root = Path(temporary).resolve(); root.chmod(0o700)
            home, cwd, sockets, backup = [root/name for name in ('home','repo','ipc','backup')]
            for directory in (home,cwd,sockets,backup): directory.mkdir(mode=0o700)
            subprocess.run(['/usr/bin/git','init','-q',str(cwd)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            (home/'config.toml').write_text(CONFIG); (home/'config.toml').chmod(0o600)
            override = ['-c','model="gpt-6-astra"','-c','model_provider="restart_fixture"',
                '-c','model_providers.restart_fixture.name="Loopback restart fixture"',
                '-c',f'model_providers.restart_fixture.base_url="http://127.0.0.1:{server.server_port}/v1"',
                '-c','model_providers.restart_fixture.wire_api="responses"',
                '-c','model_providers.restart_fixture.requires_openai_auth=false',
                '-c','model_providers.restart_fixture.request_max_retries=0',
                '-c','model_providers.restart_fixture.stream_max_retries=0']
            cold = subprocess.Popen([binary,*override,'app-server','--stdio'],cwd=cwd,env=environment({'codexHome':str(home)}),
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
            processes.append(cold); io = StdioFixture(cold)
            identity = io._rpc('initialize',{'clientInfo':{'name':'codex_orchestrator_observer','version':'1'},
                                            'capabilities':{'experimentalApi':True}})
            cold.stdin.write(b'{"method":"initialized","params":{}}\n'); cold.stdin.flush()
            project = io._rpc('project/create',{'name':'Disposable restart fixture','roots':[{'path':str(cwd)}],
                                               'metadata':{'fixture':'restart'},'idempotencyKey':str(uuid.uuid4())})['project']
            thread = io._rpc('thread/start',{'cwd':str(cwd),'projectId':project['id'],'model':'gpt-6-astra',
                'approvalPolicy':'on-request','approvalsReviewer':'user','sandbox':'workspace-write',
                'config':{'features':{'code_mode':{'enabled':False},'goals':False}},'historyMode':'paginated','ephemeral':False})['thread']
            brain = thread['id']
            turn = io._rpc('turn/start',{'threadId':brain,'input':[{'type':'text','text':'Return only a receipt. No tools, files, tasks or commands.','text_elements':[]}],
                'approvalPolicy':'on-request','approvalsReviewer':'user'})['turn']
            if not io._early_completion:
                for _ in range(1000):
                    row = io._line()
                    if row.get('method') == 'turn/completed':
                        value = row['params']; io._early_completion = (value['threadId'],value['turn']['id'],value['turn']['status']); break
            require(io._early_completion == (brain,turn['id'],'completed') and len(requests) == 1, 'Exactly one cold fixture receipt required')
            history = Path(io._rpc('thread/read',{'threadId':brain,'includeTurns':False})['thread']['path'])
            before = history.read_bytes(); stop(cold)
            require(cold.poll() is not None, 'Owned cold fixture process has not exited')
            config_before = restricted_config(home,cwd)
            if signed_in_preplay:
                # Empty synthetic auth container, not an account, key or token.
                # Exercise preservation only, never claim sign-in qualification.
                auth_file = home/'auth.json'
                require(not auth_file.exists(), 'Fixture unexpectedly acquired credentials')
                auth_file.write_bytes(b'{}\n'); auth_file.chmod(0o600)
                auth_epoch = stamp(auth_file.lstat())
            snapshotter = signed_in_preplay_snapshot if signed_in_preplay else home_snapshot
            snapshot = snapshotter(home,binary,brain=brain)
            require(snapshotter(home,binary,backup,brain=brain) == snapshot, 'Cold native home changed during fixture backup')
            backup_check({'backupPath':str(backup)},snapshot)
            if signed_in_preplay:
                require(not (backup/'auth.json').exists() and stamp(auth_file.lstat()) == auth_epoch and
                        snapshot['credentialMetadata']['bytesRead'] is False and snapshot['credentialMetadata']['copied'] is False,
                        'Synthetic auth must remain in place and outside the opaque backup')
            warm = subprocess.Popen([binary,*override,'app-server','--listen','unix://'+str(sockets/'host.sock')],cwd=cwd,
                env=environment({'codexHome':str(home)}),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,start_new_session=True)
            processes.append(warm)
            deadline = time.monotonic()+15
            while not (sockets/'host.sock').exists():
                require(warm.poll() is None and time.monotonic() < deadline, 'Warm fixture host did not create its socket')
                time.sleep(.05)
            identity_hash = digest({key:identity[key] for key in ('userAgent','platformFamily','platformOs','codexHome')})
            endpoint = inspect_endpoint(binary,str((sockets/'host.sock').resolve(strict=True)),identity_hash)
            samples = []
            with RestartReadProxy(endpoint,brain,project['id']) as proxy:
                for _ in range(2):
                    saved_project = proxy._rpc('project/read',{'projectId':project['id']})['project']
                    saved_thread = proxy._rpc('thread/read',{'threadId':brain,'includeTurns':False})['thread']
                    latest = proxy._rpc('thread/turns/list',{'threadId':brain,'cursor':None,'limit':1,'sortDirection':'desc','itemsView':'notLoaded'})['data']
                    policy = proxy._rpc('thread/effectivePolicy/read',{'threadId':brain})
                    require(saved_project['id'] == project['id'] and saved_project['roots'] == [{'path':str(cwd)}] and
                        saved_thread['id'] == brain and saved_thread['projectId'] == project['id'] and saved_thread['cwd'] == str(cwd) and
                        saved_thread['status']['type'] == 'notLoaded' and latest[0]['id'] == turn['id'] and latest[0]['status'] == 'completed' and
                        policy == {'version':1,'threadId':brain,'policy':None}, 'Warm native identity/history/unloaded policy differs')
                    require(proxy._rpc('mcpServerStatus/list',{'detail':'toolsAndAuthOnly'}) == {'data':[],'nextCursor':None}, 'Unexpected fixture MCP inventory')
                    samples.append((saved_project['id'],saved_thread['id'],latest[0]['id']))
                auth = authentication(proxy)
            require(samples[0] == samples[1] and history.read_bytes().startswith(before) and len(requests) == 1,
                    'Warm native read caused history drift or another model request')
            require(restricted_config(home,cwd) == config_before, 'Warm fixture modified reviewed restricted config')
            if signed_in_preplay:
                require(stamp(auth_file.lstat()) == auth_epoch and not (backup/'auth.json').exists(),
                        'Warm native fixture changed or copied the synthetic auth file')
            if successor_preplay:
                stop(warm)
                require(warm.poll() is not None,'Exact owned warm predecessor must actually exit')
                next_backup=root/'successor-backup'; next_backup.mkdir(mode=0o700)
                next_snapshot=signed_in_preplay_snapshot(home,binary,brain=brain)
                require(signed_in_preplay_snapshot(home,binary,next_backup,brain=brain)==next_snapshot,
                        'Successor non-credential snapshot changed')
                backup_check({'backupPath':str(next_backup)},next_snapshot)
                next_socket=root/'successor-ipc'; next_socket.mkdir(mode=0o700)
                successor=subprocess.Popen([binary,*override,'app-server','--listen','unix://'+str(next_socket/'host.sock')],
                    cwd=cwd,env=environment({'codexHome':str(home)}),stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                processes.append(successor); deadline=time.monotonic()+15
                while not (next_socket/'host.sock').exists():
                    require(successor.poll() is None and time.monotonic()<deadline,'Successor fixture socket unavailable')
                    time.sleep(.05)
                next_endpoint=inspect_endpoint(binary,str((next_socket/'host.sock').resolve(strict=True)),identity_hash)
                with RestartReadProxy(next_endpoint,brain,project['id']) as proxy:
                    for _ in range(2):
                        p=proxy._rpc('project/read',{'projectId':project['id']})['project']
                        t=proxy._rpc('thread/read',{'threadId':brain,'includeTurns':False})['thread']
                        latest=proxy._rpc('thread/turns/list',{'threadId':brain,'cursor':None,'limit':1,
                            'sortDirection':'desc','itemsView':'notLoaded'})['data']
                        require(p['id']==project['id'] and p['roots']==[{'path':str(cwd)}] and
                            t['id']==brain and t['projectId']==project['id'] and t['cwd']==str(cwd) and
                            t['status']['type']=='notLoaded' and latest[0]['id']==turn['id'] and
                            latest[0]['status']=='completed' and proxy._rpc('thread/effectivePolicy/read',{'threadId':brain})==
                            {'version':1,'threadId':brain,'policy':None},'Successor metadata/policy differs')
                require(len(requests)==1 and history.read_bytes().startswith(before) and
                    restricted_config(home,cwd)==config_before and stamp(auth_file.lstat())==auth_epoch and
                    not (next_backup/'auth.json').exists(),'Successor changed history/config/auth or requested a model')
                return {'status':'successor_preplay_runtime_fixture_passed','sameHomeReopenedTwice':True,
                    'exactOwnedPredecessorExited':True,'projectBrainAndEndedTurnPreserved':True,
                    'syntheticAuthOnly':True,'credentialBytesReadByBackup':False,'credentialsCopied':False,
                    'coldReceiptModelRequests':1,'warmModelRequests':0,'warmLoads':0,'warmTurns':0,
                    'externalProviderRequests':0,'liveHostConnections':0,'lineageJournals':'separate_unit_fixtures',
                    'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown','livePilotQualified':False}
            if readiness_owned or prestart_startup:
                if prestart_startup: from qualify_prestart_startup import Fixture
                else: from qualify_readiness_owned import Fixture
                fixture = Fixture(endpoint,brain,project['id'],cwd)
                readiness_hook.append(fixture.provider_ack)
                result = fixture.run()
                require(len(requests) == 2 and history.read_bytes().startswith(before) and
                        restricted_config(home,cwd) == config_before,'Readiness fixture changed old history/config or made extra requests')
                result.update(status='new_startup_fixture_passed' if prestart_startup else 'readiness_owned_fixture_passed',
                    coldReceiptModelRequests=1,externalProviderRequests=0,liveHostConnections=0,
                    liveNativeWrites=0,oldHistoryAndConfigPreserved=True)
                result['loopbackPreparationModelRequests' if prestart_startup else 'loopbackReadinessModelRequests']=1
                return result
            if inspection:
                from orchestrator.public_pilot_inspection import InspectionProxy, load_params, repeated
                scope = {'brainId': brain, 'projectId': project['id'], 'cwd': str(cwd),
                    'latestTurnId': turn['id'], 'latestTurnStatus': 'completed', 'binding': {'endpoint': endpoint}}
                with InspectionProxy(scope) as proxy:
                    unloaded = repeated(proxy,scope)
                    require(unloaded['activity'] == 'notLoaded' and unloaded['policy'] is None and
                            unloaded['trackedTerminals'] is None, 'Unloaded state must stay unknown before inspection')
                    owner = None
                    if subscription_seconds is not None:
                        from orchestrator.native_subscription import SubscriptionOwner
                        owner = SubscriptionOwner(proxy, subscription_seconds, digest(scope))
                        proxy.subscription_owner = owner; proxy.query_limit = 2048
                    proxy.load_permitted = True
                    if preplay_load:
                        from orchestrator.public_preplay_load import load_once
                        load_once(proxy,scope)
                    else:
                        reply = proxy._rpc('thread/resume',load_params(scope))
                        require(reply['thread']['id'] == brain and reply['thread']['cwd'] == str(cwd) and
                                reply['thread'].get('turns',[]) == [], 'Exact metadata-only load acknowledgment required')
                    loaded = repeated(proxy,scope)
                    if owner is not None:
                        checks = []
                        def check():
                            require(repeated(proxy,scope) == loaded and warm.poll() is None,
                                    'Held original subscription lost loaded identity/policy/terminals')
                            checks.append(time.monotonic()-owner.started)
                        owner.hold(check)
                        require(checks and checks[-1] > 60 and time.monotonic()-owner.started >= subscription_seconds,
                                'Subscription must remain loaded beyond the actual pinned default grace')
                require(loaded['activity'] == 'idle' and loaded['trackedTerminals'] == [] and
                        len(requests) == 1 and history.read_bytes().startswith(before),
                        'Inspection must not start a turn, request a model or change original history')
                # A new connection can inspect the same loaded brain, but never
                # receives another load permit. This is current evidence only.
                with InspectionProxy(scope) as proxy:
                    require(repeated(proxy,scope) == loaded, 'Read-only reconciliation changed native evidence')
                if subscription_seconds is not None:
                    # Read-only connections do not inherit ownership. Wait for
                    # native unload, proving that neither reads nor release
                    # secretly reloaded or retained an indefinite subscription.
                    deadline = time.monotonic()+80
                    while True:
                        with InspectionProxy(scope) as reader: ended = repeated(reader,scope)
                        if ended['activity'] == 'notLoaded': break
                        require(warm.poll() is None and time.monotonic() < deadline,
                                'Pinned fixture did not unload after owner release')
                        time.sleep(2)
                    require(ended['policy'] is None and ended['trackedTerminals'] is None and
                            warm.poll() is None and len(requests) == 1 and history.read_bytes().startswith(before) and
                            restricted_config(home,cwd) == config_before,
                            'Release must preserve unknown evidence, same host, history/config and zero model requests')
                    return {'status':'subscription_ownership_fixture_passed', 'sameHome':True,'preplayLoadBoundaryQualified':preplay_load,
                        'reviewedObservationSeconds':subscription_seconds,'verifiedLoadedBeyondSeconds':60,
                        'heldOriginalSubscription':True,'metadataCheckCount':len(checks),
                        'releasedConnectionAllowsUnload':True,'readOnlyConnectionsDoNotAdoptOwnership':True,
                        'hostStayedRunning':True,'coldReceiptModelRequests':1,'inspectionLoads':1,
                        'inspectionTurns':0,'inspectionModelRequests':0,'reconciliationLoads':0,
                        'currentActivity':'notLoaded','currentPolicy':None,'currentTrackedTerminals':None,
                        'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown',
                        'configAndHistoryPreserved':True,'liveNativeWrites':0,'livePilotQualified':False}
                require(restricted_config(home,cwd) == config_before and len(requests) == 1,
                        'Inspection/reconciliation changed configuration or requested a model')
                return {'status':'inspection_fixture_passed','sameHome':True,'preplayLoadBoundaryQualified':preplay_load,
                    'projectBrainAndEndedTurnPreserved':True,'actualRestrictedLoadedPolicy':True,
                    'unixTransport':'actual_inspection_proxy','coldReceiptModelRequests':1,
                    'inspectionLoads':1,'inspectionTurns':0,'inspectionModelRequests':0,
                    'reconciliationLoads':0,'reconciliationTurns':0,'reconciliationModelRequests':0,
                    'currentTrackedTerminals':'known_empty','currentTerminalSafety':'unknown',
                    'historicalTerminalSafety':'unknown','livePilotQualified':False}
            return {'status':'fixture_passed','sameHome':True,'projectBrainAndEndedTurnPreserved':True,
                'signedInPreplayBackupProfile':signed_in_preplay,'syntheticAuthOnly':signed_in_preplay,
                'credentialBytesReadByBackup':False,'credentialsCopied':False,'liveSignInQualified':False,
                'backupVerified':True,'preservedNativeProjectTrust':config_before['nativeProjectTrust'],
                'unixTransport':'actual_read_proxy','coldReceiptModelRequests':1,
                'warmModelRequests':0,'warmLoads':0,'warmTurns':0,'warmNativeWrites':0,
                'unloadedPolicyRemainsUnknown':True,'fixtureAuthentication':auth['status'],
                'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown','livePilotQualified':False}
    finally:
        for process in reversed(processes): stop(process)
        server.shutdown(); server.server_close(); runner.join(timeout=2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',required=True); parser.add_argument('--sha256',required=True)
    parser.add_argument('--inspection',action='store_true',help='Also qualify one metadata-only warm load and read-only reconciliation')
    parser.add_argument('--preplay-load',action='store_true',help='Use the separate pre-Play load boundary in the disposable inspection fixture')
    parser.add_argument('--readiness-owned',action='store_true',help='Qualify a distinct readiness-owned load, capture, turn and synthetic fixture receipt')
    parser.add_argument('--prestart-startup',action='store_true',help='Qualify a new preparation purpose after an injected old pre-load failure; never replay readiness')
    parser.add_argument('--signed-in-preplay',action='store_true',help='Test the separate auth-metadata-only backup using a synthetic empty auth container; no load')
    parser.add_argument('--successor-preplay',action='store_true',help='With signed-in-preplay, qualify a second disposable same-home reopen after actual warm exit')
    parser.add_argument('--subscription-seconds',type=int,
                        help='Disposable only: hold the original subscription for 75–300 seconds, then verify unload')
    args = parser.parse_args()
    print(canonical(qualify(args.executable,args.sha256,inspection=args.inspection,
                          subscription_seconds=args.subscription_seconds,signed_in_preplay=args.signed_in_preplay,
                          preplay_load=args.preplay_load,readiness_owned=args.readiness_owned,
                          successor_preplay=args.successor_preplay,prestart_startup=args.prestart_startup)))
