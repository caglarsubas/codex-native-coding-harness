"""Real compiled public-protocol task fixture, isolated home and loopback model.

No real credentials, desktop pipe, live project, ledger, host or cloud provider.
Creates one disposable native project/thread and starts one receipt-only turn;
the optional tools fixture instead exercises apply_patch and fixed pwd there.
This qualifies protocol translation, not an installed host or pilot acceptance.
"""
import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator.core import digest, require
from orchestrator.native_read_client import decode, secure_path
from orchestrator.native_policy_evidence import matches, reported
from orchestrator.native_auth_readiness import require_ready as require_authentication
from orchestrator.public_native_tasks import PublicTaskProxy, arguments, PROTOCOL


class StdioFixture:
    """Private fixture transport. Production continues to use pinned proxy IPC."""
    request_limit = 65536
    def __init__(self, process):
        self.process, self.sequence, self.buffer = process, 0, b""
        self.methods = []
        self._early_requests = []
        self._early_completion = None
        self._awaiting_start = False
        self.deadline = time.monotonic()+30
        os.set_blocking(process.stdout.fileno(), False)

    def _line(self):
        with selectors.DefaultSelector() as selector:
            selector.register(self.process.stdout, selectors.EVENT_READ)
            while b"\n" not in self.buffer:
                remaining = min(30, self.deadline-time.monotonic())
                require(remaining > 0 and selector.select(remaining), "Disposable native fixture timed out")
                chunk = os.read(self.process.stdout.fileno(),65536)
                require(chunk,"Disposable native fixture exited")
                self.buffer += chunk
                require(len(self.buffer)<=1_000_000,"Disposable native response exceeds bound")
        line,self.buffer=self.buffer.split(b"\n",1)
        row = decode(line)
        if getattr(self, 'on_native_event', None) is not None:
            self.on_native_event(row)
        return row

    def _rpc(self,method,params):
        allowed={"initialize","project/create","project/read","thread/start","turn/start","thread/read",
                 "thread/effectivePolicy/read","thread/backgroundTerminals/list","mcpServerStatus/list",
                 "project/restoreMetadata","thread/resume","thread/metadata/update","project/list","thread/list","account/read"}
        require(method in allowed,"Fixture RPC is not allowlisted")
        self.methods.append(method);self.sequence+=1
        self.deadline=time.monotonic()+30
        data=json.dumps({"id":self.sequence,"method":method,"params":params})+"\n"
        require(len(data.encode())<=self.request_limit,"Disposable native request exceeds bound")
        self.process.stdin.write(data.encode());self.process.stdin.flush()
        for _ in range(1000):
            row=self._line()
            if "id" not in row:
                if row.get("method")=="turn/completed":
                    params=row.get("params") or {};turn=params.get("turn") or {}
                    self._early_completion=(params.get("threadId"),turn.get("id"),turn.get("status"))
                continue
            require(row["id"]==self.sequence and "error" not in row,"Disposable native RPC refused")
            return row["result"]
        raise ValueError("Disposable notification bound exceeded")

    def call(self,method,params): return self._rpc(method,params)


def qualify(binary, expected_hash, exercise_tools=False, public_host_config=False, missing_auth=False, capture_lifecycles=False):
    require(not missing_auth or not exercise_tools, "Missing-auth fixture cannot execute tools")
    require(not capture_lifecycles or exercise_tools, 'Lifecycle fixture requires the bounded disposable tool exercise')
    path,_=secure_path(binary)
    with path.open("rb") as stream: actual_hash=hashlib.file_digest(stream,"sha256").hexdigest()
    require(actual_hash==expected_hash,"Reviewed compiled runtime changed")
    model_calls=[]
    command_outputs=[]
    class Provider(http.server.BaseHTTPRequestHandler):
        def do_GET(self): self.send_error(404)
        def do_POST(self):
            length=int(self.headers.get("Content-Length","0"))
            if not 0 < length <= 1_000_000: self.send_error(400);return
            body=decode(self.rfile.read(length))
            model_calls.append(body.get("model"))
            if exercise_tools and len(model_calls)==3:
                command_outputs.extend(item.get("output") for item in body.get("input",[]) if
                    isinstance(item,dict) and item.get("type")=="function_call_output" and
                    item.get("call_id")=="fixture-readonly-command")
            item={"type":"message","role":"assistant","id":"fixture-message",
                  "content":[{"type":"output_text","text":"Disposable receipt retained."}]}
            if exercise_tools and len(model_calls)==1:
                item={"type":"custom_tool_call","name":"apply_patch","call_id":"fixture-patch",
                      "input":"*** Begin Patch\n*** Add File: RESULT.md\n+Public native task fixture.\n*** End Patch"}
            elif exercise_tools and len(model_calls)==2:
                item={"type":"function_call","name":"exec_command","call_id":"fixture-readonly-command",
                      "arguments":json.dumps({"cmd":"pwd","workdir":str(cwd),"max_output_tokens":200})}
            events=[{"type":"response.created","response":{"id":"fixture-response"}},
                    {"type":"response.output_item.done","item":item},
                    {"type":"response.completed","response":{"id":"fixture-response",
                     "usage":{"input_tokens":5,"output_tokens":5,"total_tokens":10}}}]
            payload="".join("data: "+json.dumps(e)+"\n\n" for e in events).encode()
            self.send_response(200);self.send_header("Content-Type","text/event-stream")
            self.send_header("Content-Length",str(len(payload)));self.end_headers();self.wfile.write(payload)
        def log_message(self,*_):pass
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),Provider)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix="codex-public-task-fixture.") as directory:
            root=Path(directory).resolve();home=root/"home";cwd=root/"checkout"
            home.mkdir(mode=0o700);cwd.mkdir(mode=0o700)
            (home/"config.toml").write_text(f'''model = "gpt-6-astra"
model_provider = "public_task_fixture"
[model_providers.public_task_fixture]
name = "Loopback fixture"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
[features]
code_mode = false
code_mode_only = true
skip_host_skill_discovery = true
plugins = false
apps = false
hooks = false
[analytics]
enabled = false
''')
            env={k:os.environ[k] for k in ("HOME","USER","LOGNAME","TMPDIR","PATH") if k in os.environ}
            env["CODEX_HOME"]=str(home)
            if public_host_config:
                from orchestrator.public_host_lifecycle import CONFIG, environment
                # Fixture-only provider overlay. The live launch profile still
                # requires byte-exact CONFIG and an unconfigured credential home.
                (home/"config.toml").write_text('model = "gpt-6-astra"\nmodel_provider = "public_task_fixture"\n'+CONFIG+
                    f'''\n[model_providers.public_task_fixture]
name = "Loopback fixture"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
''')
                env=environment({"codexHome":str(home)})
            if missing_auth:
                from orchestrator.public_host_lifecycle import CONFIG, environment
                (home/"config.toml").write_text('model = "gpt-6-astra"\ncli_auth_credentials_store = "file"\n'+CONFIG)
                env=environment({"codexHome":str(home)})
            process=subprocess.Popen([binary,"app-server","--stdio"],cwd=cwd,env=env,
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                io=StdioFixture(process)
                result=io._rpc("initialize",{"clientInfo":{"name":"public_task_qualifier","version":"1"},
                            "capabilities":{"experimentalApi":True}})
                require(Path(result["codexHome"]).resolve()==home,"Disposable runtime isolation changed")
                process.stdin.write(b'{"method":"initialized","params":{}}\n');process.stdin.flush()
                if missing_auth:
                    from orchestrator.core import Refusal
                    from orchestrator.native_auth_readiness import inspect
                    report=inspect(io)
                    require(report["status"]=="authentication_required" and not report["ready"],
                            "Disposable unauthenticated host did not report missing sign-in")
                    try: require_authentication(io)
                    except Refusal: pass
                    else: raise ValueError("Unauthenticated native work was not fenced")
                    require(io.methods==["initialize"]+["account/read"]*4 and not model_calls and
                            not list(cwd.iterdir()) and not (home/"auth.json").exists(),
                            "Missing-auth fixture unexpectedly performed work or authentication")
                    return {"binarySha256":actual_hash,"nativeAuthentication":"authentication_required",
                            "guardRefused":True,"disposableProjects":0,"disposableThreads":0,
                            "disposableTurnStarts":0,"loopbackModelRequests":0,"cloudModelRequests":0,
                            "liveHostConnections":0,"liveNativeWrites":0,"loginStarted":False,
                            "modelAccessVerified":False,"terminalSafetyVerified":False,"pilotAccepted":False}
                project=io._rpc("project/create",{"name":"Disposable public task fixture","roots":[{"path":str(cwd)}],
                                    "idempotencyKey":str(uuid.uuid4())})["project"]
                contract={"protocol":PROTOCOL,"sourceCommit":"a"*40,"sourceTree":"b"*40,
                          "trust":"operator_reviewed_build_v1","desktopBridge":"absent","repositoryMode":"repo_exclusive"}
                # Synthetic seed/source pins are explicit fixture data, not build attestation.
                seed={"task":{"model":"gpt-6-astra","effort":"low","paths":["RESULT.md"]},
                      "repository":{"path":str(cwd)},"mission":{"fixture":True},
                      "instructions":("Apply the exact fixture patch to RESULT.md, execute pwd in this disposable checkout, "
                                      "then return a receipt. No other edits, commands or tasks." if exercise_tools else
                                      "Return a receipt only. Do not execute commands, edit files or create tasks."),
                      "acceptance":["One native receipt-only turn ends"]}
                record={"cwd":str(cwd),"projectId":project["id"],"nativeTaskBackend":contract,
                        "policyEvidence":{"protocol":"loaded_thread_policy_v1","sourceCommit":"a"*40,"sourceTree":"b"*40}}
                start,turn=arguments(seed,record)
                adapter=PublicTaskProxy({},start,turn)
                adapter.proxy=io
                adapter.public_environment()
                require_authentication(adapter)
                thread_id,_=adapter.create()
                adapter.public_environment()
                samples=[adapter._rpc("thread/effectivePolicy/read",{"threadId":thread_id}) for _ in range(2)]
                require(samples[0]==samples[1] and all(matches(reported(s,thread_id,str(cwd))) for s in samples),
                        "Compiled worker effective policy differs from review")
                require_authentication(adapter)
                if capture_lifecycles:
                    from orchestrator import effect_capture as capture, prospective_lifecycle as lifecycle
                    ledger = SimpleNamespace(root=root, workspace_id='disposable-lifecycle')
                    fixture_binding = {'endpoint': {}, 'brains': {thread_id: {'workspaceId': ledger.workspace_id}}}
                    fixture_run = {'id': str(uuid.uuid4()), 'brainId': thread_id, 'protocol': 'standard_cooperative_v1'}
                    command = {'id': str(uuid.uuid4()), 'kind': 'standard_play', 'notification': {
                        'status': 'sending', 'brainId': thread_id, 'hostRunId': fixture_run['id'],
                        'hostInspectionTransport': 'owned_observer_v1', 'hostBindingHash': digest(fixture_binding)}}
                    meta = {'brainId': thread_id, 'standardRun': fixture_run}
                    command['notification'][capture.FIELD] = capture.begin(ledger, fixture_binding, command, meta)
                    command['notification'][lifecycle.FIELD] = lifecycle.bind(command, meta)
                    io.on_native_event = lambda row: capture.append(ledger, command['id'], thread_id, row)
                turn_id,_=adapter.begin()
                require(adapter.ended(turn_id)=="ended","Disposable native task did not end")
                lifecycle_result = None
                if capture_lifecycles:
                    io.on_native_event = None
                    command['notification']['nativeTurnId'] = turn_id
                    capture.seal(ledger, command, turn_id, 'completed')
                    lifecycle_result = lifecycle.retained(ledger, command)
                    require(lifecycle_result['status'] == 'recorded_item_lifecycles_observed' and
                            {row['itemType'] for row in lifecycle_result['items']} >= {'fileChange', 'commandExecution'} and
                            not any(lifecycle_result['boundary'].values()) and
                            lifecycle_result['terminalSafety'] == 'unknown', 'Disposable lifecycle capture did not qualify its bounded item evidence')
                thread=adapter.call("thread/read",{"threadId":thread_id,"includeTurns":False})["thread"]
                terminals=adapter.call("thread/backgroundTerminals/list",{"threadId":thread_id,"cursor":None,"limit":64})
                require(thread["id"]==thread_id and thread["projectId"]==project["id"] and
                        thread["status"]["type"]=="idle" and terminals["data"]==[] and terminals["nextCursor"] is None,
                        "Disposable current task evidence is incomplete")
                expected_calls=3 if exercise_tools else 1
                require(model_calls==["gpt-6-astra"]*expected_calls,"Unexpected fixture provider/model request")
                require(io.methods.count("thread/start")==1 and io.methods.count("turn/start")==1,
                        "Disposable task effects were repeated")
                if exercise_tools:
                    require([p.name for p in cwd.iterdir()]==["RESULT.md"] and
                            (cwd/"RESULT.md").read_text()=="Public native task fixture.\n",
                            "Native apply_patch did not preserve the exact disposable artifact")
                    require(len(command_outputs)==1 and isinstance(command_outputs[0],str) and
                            str(cwd) in command_outputs[0] and "Process exited with code 0" in command_outputs[0],
                            "Native readonly command did not report its exact checkout and successful exit")
                else:
                    require(not list(cwd.iterdir()),"Receipt-only fixture unexpectedly edited its checkout")
                return {"binarySha256":actual_hash,"protocol":PROTOCOL,"compiledProtocolQualified":True,
                        "disposableProjects":1,"disposableThreads":1,"disposableTurnStarts":1,
                        "loopbackModelRequests":expected_calls,"cloudModelRequests":0,"desktopPipeConfigured":False,
                        "desktopToolsAdvertised":False,
                        "workerPolicyVerified":True,"fixtureCurrentTerminals":"none",
                        "disposableFileEditVerified":exercise_tools,"readonlyCommandVerified":exercise_tools,
                        "publicHostConfigFixture":public_host_config,"launchLifecycleQualified":False,
                        "prospectiveNativeItemLifecycleQualified":lifecycle_result is not None,
                        "capturedItemLifecycles":len(lifecycle_result['items']) if lifecycle_result else None,
                        "processLifecycleCleanupQualified":False,
                        "liveHostConnections":0,"liveNativeWrites":0,"migrationQualified":False,"pilotAccepted":False}
            finally:
                process.stdin.close()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
                process.stdout.close()
    finally:
        server.shutdown();server.server_close();worker.join(timeout=5)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable",required=True);parser.add_argument("--sha256",required=True)
    parser.add_argument("--exercise-tools",action="store_true",help="Additionally exercise native apply_patch and fixed pwd only inside the disposable checkout")
    parser.add_argument("--public-host-config",action="store_true",help="Exercise restricted public-host config/environment with fixture-only loopback provider; not a live launch review")
    parser.add_argument("--missing-auth",action="store_true",help="Verify the unauthenticated default-provider guard with zero project/thread/turn creation or login")
    parser.add_argument("--capture-lifecycles",action="store_true",help="Qualify original-bound native item lifecycle only, never OS descendant cleanup")
    args=parser.parse_args()
    print(json.dumps(qualify(args.executable,args.sha256,args.exercise_tools,args.public_host_config,args.missing_auth,args.capture_lifecycles),indent=2))
