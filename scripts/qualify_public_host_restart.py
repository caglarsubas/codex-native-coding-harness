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
from orchestrator.public_host_restart import home_snapshot, backup_check, restricted_config, RestartReadProxy
from orchestrator.native_auth_readiness import inspect as authentication
from qualify_public_native_tasks import StdioFixture


def qualify(binary, expected_hash):
    path, _ = secure_path(binary)
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash, 'Exact reviewed native fixture binary required')
    requests, processes = [], []
    class Provider(http.server.BaseHTTPRequestHandler):
        def do_GET(self): self.send_error(404)
        def do_POST(self):
            require(self.path == '/v1/responses', 'Only the loopback fixture response route is permitted')
            size = int(self.headers.get('Content-Length','0')); require(0 < size < 1_000_000, 'Bounded fixture request required')
            self.rfile.read(size); requests.append(self.path)
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
            snapshot = home_snapshot(home,binary,brain=brain)
            require(home_snapshot(home,binary,backup,brain=brain) == snapshot, 'Cold native home changed during fixture backup')
            backup_check({'backupPath':str(backup)},snapshot)
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
            return {'status':'fixture_passed','sameHome':True,'projectBrainAndEndedTurnPreserved':True,
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
    args = parser.parse_args()
    print(canonical(qualify(args.executable,args.sha256)))
