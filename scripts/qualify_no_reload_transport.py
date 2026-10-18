"""Real two-connection Unix fixture; never connects to a live host or account.

The provider is a labelled loopback fake. Its sole escalated command is canceled
inside this disposable fixture to verify permission delivery, never auto-accepted.
No shared home, credentials, ledger, old request, reload, or recovery is used.
"""
import argparse
import contextlib
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
from orchestrator import no_reload_transport as transport
from orchestrator.app_server_wake import WakeProxy
from orchestrator.core import Refusal, digest, require
from orchestrator.native_read_client import inspect_endpoint, secure_path
from orchestrator.public_host_lifecycle import CONFIG, environment
from orchestrator.standard_quarantine import exclusive


class FixtureProxy(WakeProxy):
    """Fixed disposable-only methods, including creation and fixture turn input."""
    def __init__(self,endpoint,bootstrap=False):
        super().__init__(endpoint); self.bootstrap = bootstrap; self.methods = []; self.events = []
        self._on_effect_event = lambda row:self.events.append(row)

    def _rpc(self,method,params):
        require(method in {'initialize','project/create','project/read','thread/start','thread/read',
            'thread/subscribe','thread/unsubscribe','thread/effectivePolicy/read',
            'thread/backgroundTerminals/list','turn/start'},'Fixture forbids native reload/recovery/authentication')
        self.methods.append(method)
        value = super()._rpc(method,params)
        if method == 'initialize' and self.bootstrap:
            # Only initial fixture discovery; production never adopts an identity.
            self.endpoint['serverIdentityHash'] = digest({k:value[k] for k in
                ('userAgent','platformFamily','platformOs','codexHome')})
        return value

    def completion(self,brain,turn, *, permission=False):
        self.deadline = time.monotonic()+30
        self.watch_connection()
        early = list(getattr(self,'_early_requests',[])); self._early_requests = []
        seen = False
        for _ in range(256):
            ended = getattr(self,'_early_completion',None)
            if ended and ended[:2] == (brain,turn) and not early:
                require(seen == permission,'Unexpected or missing disposable permission')
                return ended[2]
            row = early.pop(0) if early else self._line()
            if 'id' in row and 'method' in row:
                require(permission and not seen and row['method'] == 'item/commandExecution/requestApproval',
                        'Unexpected native server request; never automatically accept')
                params = row['params']
                require(params['threadId'] == brain and params['turnId'] == turn and
                        '/usr/bin/true' in params.get('command',''), 'Foreign or changed fixture permission')
                self.on_fixture_permission()
                # Fixed explicit fixture resolution only; no production relay response.
                self._write({'id':row['id'],'result':{'decision':'cancel'}}); seen = True
            if row.get('method') == 'turn/completed':
                params = row['params']; observed = params['turn']
                require(params['threadId'] == brain and observed['id'] == turn and seen == permission,
                        'Completion does not match this disposable original turn')
                return observed['status']
        raise Refusal('Disposable lifecycle bound exceeded')


def qualify(executable,sha256,source_commit,source_tree):
    binary,_ = secure_path(executable)
    with binary.open('rb') as stream: require(hashlib.file_digest(stream,'sha256').hexdigest() == sha256,'Pinned binary changed')
    calls = []
    class Provider(http.server.BaseHTTPRequestHandler):
        def do_GET(self): self.send_error(404)
        def do_POST(self):
            size = int(self.headers.get('Content-Length','0'))
            require(0 < size <= 1_000_000,'Bounded loopback request required')
            body = json.loads(self.rfile.read(size)); calls.append(body.get('model'))
            if len(calls) == 2:
                item = {'type':'function_call','name':'exec_command','call_id':'fixture-permission',
                    'arguments':json.dumps({'cmd':'/usr/bin/true','workdir':str(cwd),
                        'sandbox_permissions':'require_escalated','justification':'Disposable subscription permission fixture',
                        'max_output_tokens':100})}
            else:
                item = {'type':'message','role':'assistant','id':'fixture-message',
                        'content':[{'type':'output_text','text':'Disposable receipt only.'}]}
            events = [{'type':'response.created','response':{'id':'fixture-response'}},
                      {'type':'response.output_item.done','item':item},
                      {'type':'response.completed','response':{'id':'fixture-response',
                       'usage':{'input_tokens':5,'output_tokens':5,'total_tokens':10}}}]
            payload = ''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode()
            self.send_response(200); self.send_header('Content-Type','text/event-stream')
            self.send_header('Content-Length',str(len(payload))); self.end_headers(); self.wfile.write(payload)
        def log_message(self,*_): pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0),Provider)
    worker = threading.Thread(target=server.serve_forever,daemon=True); worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix='no-reload-fixture-') as temporary:
            root = Path(temporary).resolve(); home = root/'home'; cwd = root/'checkout'; ipc = root/'ipc'
            for path in (home,cwd,ipc): path.mkdir(mode=0o700)
            (home/'config.toml').write_text('model = "gpt-6-astra"\nmodel_provider = "subscription_fixture"\n'
                'thread_unload_delay_secs = 2\n'+CONFIG+f'''
[model_providers.subscription_fixture]
name = "Disposable loopback provider"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
''')
            process = subprocess.Popen([str(binary),'app-server','--listen','unix://'+str(ipc/'host.sock')],
                cwd=cwd,env=environment({'codexHome':str(home)}),stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                deadline = time.monotonic()+15
                while not (ipc/'host.sock').exists():
                    require(process.poll() is None and time.monotonic()<deadline,'Disposable host did not listen')
                    time.sleep(.02)
                endpoint = inspect_endpoint(str(binary),str((ipc/'host.sock').resolve()),'0'*64)
                methods = []
                with contextlib.ExitStack() as stack:
                    creator = stack.enter_context(FixtureProxy(endpoint,bootstrap=True))
                    project = creator._rpc('project/create',{'name':'Subscribe-only fixture',
                        'roots':[{'path':str(cwd)}],'idempotencyKey':str(uuid.uuid4())})['project']
                    thread = creator._rpc('thread/start',{'cwd':str(cwd),'projectId':project['id'],'ephemeral':False,
                        'sandbox':'workspace-write','approvalPolicy':'on-request','approvalsReviewer':'user',
                        'config':{'features':{'code_mode':{'enabled':False}}}})['thread']
                    brain = thread['id']
                    binding = {'endpoint':endpoint,'brains':{brain:{'cwd':str(cwd),'projectId':project['id'],
                        'policyEvidence':{'protocol':'loaded_thread_policy_v1',
                                          'sourceCommit':source_commit,'sourceTree':source_tree}}}}
                    contract = {'protocol':transport.PROTOCOL,'method':transport.METHOD,
                        'sourceCommit':source_commit,'sourceTree':source_tree,'executableSha256':sha256}
                    subscriber = stack.enter_context(FixtureProxy(endpoint))
                    snapshots = {str(p):p.read_bytes() for p in (home/'sessions').rglob('*.jsonl')}
                    def claim(context):
                        exclusive(root/'subscribe.claim.json',{'contextHash':context,'subscriptionClaimed':True})
                        return json.loads((root/'subscribe.claim.json').read_text())
                    observed = transport.Subscription(subscriber,binding,brain,contract).attach(claim)
                    require(observed['subscriptionAttached'] and not calls,'Subscription loaded or invoked a model')
                    require(snapshots == {str(p):p.read_bytes() for p in (home/'sessions').rglob('*.jsonl')},
                            'Subscribe-only changed durable thread history')
                    require(not any(r.get('method') == 'thread/started' for r in subscriber.events),
                            'Subscribe-only emitted a runtime start')
                    creator._rpc('thread/unsubscribe',{'threadId':brain})
                    active_refused = []
                    def active_probe():
                        with FixtureProxy(endpoint) as probe:
                            try: probe._rpc('thread/subscribe',{'threadId':brain})
                            except Refusal: active_refused.append(True)
                            else: raise Refusal('An active permission wait accepted subscribe-only')
                            methods.extend(probe.methods)
                    subscriber.on_fixture_permission = active_probe
                    # A second original fixture turn is not a replay of any live control.
                    for permission in (False,True):
                        subscriber._early_completion = None
                        result = subscriber._rpc('turn/start',{'threadId':brain,
                            'input':[{'type':'text','text':'Disposable receipt fixture only.','text_elements':[]}],
                            'approvalPolicy':'on-request','approvalsReviewer':'user'})
                        status = subscriber.completion(brain,result['turn']['id'],permission=permission)
                        require(status == ('interrupted' if permission else 'completed'), 'Exact native fixture lifecycle missing')
                    require(any(r.get('method') == 'item/commandExecution/requestApproval' for r in subscriber.events),
                            'New subscription did not own the native permission stream')
                    require(active_refused == [True], 'Active native subscription was not fenced')
                    methods += creator.methods+subscriber.methods
                    subscriber._rpc('thread/unsubscribe',{'threadId':brain})
                    # Explicitly wait for the actual native unload notification, not
                    # elapsed time as a safety inference. No new native effects follow.
                    subscriber.deadline = time.monotonic()+15
                    while True:
                        row = subscriber._line()
                        if row.get('method') == 'thread/closed' and row.get('params',{}).get('threadId') == brain: break
                    reader = stack.enter_context(FixtureProxy(endpoint))
                    before = reader.call('thread/read',{'threadId':brain,'includeTurns':False})
                    require(before['thread']['status'] == {'type':'notLoaded'},'Fixture did not unload')
                    try: reader._rpc('thread/subscribe',{'threadId':brain})
                    except Refusal: pass
                    else: raise Refusal('Unloaded native subscription unexpectedly succeeded')
                    after = reader.call('thread/read',{'threadId':brain,'includeTurns':False})
                    require(after['thread']['status'] == {'type':'notLoaded'},'Subscribe refusal reloaded history')
                    # Deterministically unload another disposable brain AFTER
                    # the client's successful preflight and BEFORE its subscribe.
                    race_brain = creator._rpc('thread/start',{'cwd':str(cwd),'projectId':project['id'],
                        'ephemeral':False,'sandbox':'workspace-write','approvalPolicy':'on-request',
                        'approvalsReviewer':'user','config':{'features':{'code_mode':{'enabled':False}}}})['thread']['id']
                    race_binding = {'endpoint':endpoint,'brains':{race_brain:binding['brains'][brain]}}
                    race = transport.Subscription(reader,race_binding,race_brain,contract)
                    race_unload_observed = []
                    subscribe_attempts_before_race = reader.methods.count('thread/subscribe')
                    def unload_between_preflight_and_subscribe(context):
                        exclusive(root/'race.claim.json',{'contextHash':context,'subscriptionClaimed':True})
                        creator._rpc('thread/unsubscribe',{'threadId':race_brain})
                        creator.deadline = time.monotonic()+15
                        for _ in range(256):
                            row = creator._line()
                            if row.get('method') == 'thread/closed' and row.get('params',{}).get('threadId') == race_brain:
                                race_unload_observed.append(True)
                                return json.loads((root/'race.claim.json').read_text())
                        raise Refusal('Exact native race unload not observed')
                    try: race.attach(unload_between_preflight_and_subscribe)
                    except Refusal: pass
                    else: raise Refusal('Preflight-to-unload race unexpectedly subscribed')
                    require(race_unload_observed == [True] and
                        reader.methods.count('thread/subscribe') == subscribe_attempts_before_race+1 and
                        not race.ready and (root/'race.claim.json').exists() and
                        reader.call('thread/read',{'threadId':race_brain,'includeTurns':False})['thread']['status'] ==
                        {'type':'notLoaded'},'Unload race reloaded a brain or lost its consumed claim')
                    methods += reader.methods
                    require('thread/resume' not in methods and not (home/'auth.json').exists(),
                            'Fixture loaded or authenticated a native brain')
                    return {'transportQualified':True,'binarySha256':sha256,'sourceCommit':source_commit,
                        'sourceTree':source_tree,'newConnectionOwnedLifecycleAndPermission':True,
                        'disposableTurnStarts':2,'fixturePermissionCanceled':True,'nativeReloads':0,
                        'activePermissionWaitRefusedSubscription':True,
                        'preflightUnloadRaceRefusedWithoutReload':True,
                        'unloadedThreadStillUnloaded':True,'subscriptionDidNotChangeHistory':True,
                        'loopbackProviderRequests':len(calls),'cloudRequests':0,'liveHostConnections':0,
                        'liveBindingChanged':False,'liveDispositionApplied':False,'liveContinuationAuthorized':False,
                        'currentTerminalSafety':'unknown','historicalTerminalSafety':'unknown','pilotAccepted':False}
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('executable','sha256','source_commit','source_tree'): parser.add_argument('--'+arg.replace('_','-'),required=True)
    print(json.dumps(qualify(**vars(parser.parse_args())),indent=2))
