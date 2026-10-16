"""Compiled, disposable zero-turn persistence qualification. Never a live repair.

Uses an isolated home, an explicitly fake loopback provider and two native process
epochs. No credentials, shared Codex home, live socket, load, turn or recovery.
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
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator.core import require
from orchestrator.native_read_client import secure_path
from orchestrator.native_policy_evidence import matches, reported
from orchestrator.public_host_lifecycle import CONFIG, environment
from qualify_public_native_tasks import StdioFixture


class EmptyBrainFixture(StdioFixture):
    def _rpc(self, method, params):
        require(method in {'initialize', 'project/create', 'project/read', 'thread/start', 'thread/read',
                           'thread/effectivePolicy/read', 'thread/backgroundTerminals/list'},
                'Zero-turn fixture cannot load, turn, interrupt, update metadata or authenticate')
        return super()._rpc(method, params)


def qualify(executable, sha256):
    binary, _ = secure_path(executable)
    require(hashlib.sha256(binary.read_bytes()).hexdigest() == sha256, 'Exact reviewed fixture binary required')
    calls = []
    class Provider(http.server.BaseHTTPRequestHandler):
        def do_GET(self): self.send_error(404)
        def do_POST(self):
            calls.append(self.path); self.send_error(500)
        def log_message(self, *_): pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Provider)
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    methods, ids, snapshots = [], [], []
    try:
        with tempfile.TemporaryDirectory(prefix='empty-brain-fixture-') as temporary:
            root = Path(temporary).resolve(); home = root/'home'; home.mkdir(mode=0o700)
            cwd = root/'checkout'; cwd.mkdir(mode=0o700)
            (home/'config.toml').write_text('model = "gpt-6-astra"\nmodel_provider = "empty_brain_fixture"\n'+CONFIG+
                f'''\n[model_providers.empty_brain_fixture]
name = "No-turn loopback fixture"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
''')
            for epoch in range(2):
                process = subprocess.Popen([str(binary), 'app-server', '--stdio'], cwd=cwd,
                    env=environment({'codexHome': str(home)}), stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
                try:
                    io = EmptyBrainFixture(process)
                    initial = io._rpc('initialize', {'clientInfo': {'name': 'empty_brain_fixture', 'version': '1'},
                        'capabilities': {'experimentalApi': True}})
                    require(initial['codexHome'] == str(home), 'Fixture home differs')
                    process.stdin.write(b'{"method":"initialized","params":{}}\n'); process.stdin.flush()
                    if epoch == 0:
                        project = io._rpc('project/create', {'name': 'Empty brain fixture',
                            'roots': [{'path': str(cwd)}], 'idempotencyKey': str(uuid.uuid4())})['project']
                        for history in ('paginated', 'legacy'):
                            result = io._rpc('thread/start', {'projectId': project['id'], 'cwd': str(cwd),
                                'ephemeral': False, 'historyMode': history, 'sandbox': 'workspace-write',
                                'approvalPolicy': 'on-request', 'approvalsReviewer': 'user',
                                'config': {'features': {'code_mode': {'enabled': False}}}})
                            ids.append(result['thread']['id'])
                    for brain in ids:
                        for _ in range(2):
                            observed_project = io._rpc('project/read', {'projectId': project['id']})['project']
                            thread = io._rpc('thread/read', {'threadId': brain, 'includeTurns': False})['thread']
                            require(observed_project['roots'] == [{'path': str(cwd)}] and
                                    thread['id'] == brain and thread['projectId'] == project['id'] and
                                    thread['cwd'] == str(cwd) and not thread.get('turns'),
                                    'Empty brain project metadata was not durably materialized')
                            expected = 'idle' if epoch == 0 else 'notLoaded'
                            require(thread['status'] == {'type': expected}, 'Fixture loading state differs')
                            if epoch == 0:
                                policy = io._rpc('thread/effectivePolicy/read', {'threadId': brain})
                                terminals = io._rpc('thread/backgroundTerminals/list',
                                    {'threadId': brain, 'cursor': None, 'limit': 64})
                                require(matches(reported(policy, brain, str(cwd))) and terminals ==
                                        {'data': [], 'nextCursor': None}, 'Fixture current policy/terminals differ')
                            snapshots.append({'epoch': epoch, 'threadId': brain, 'status': expected})
                    methods.extend(io.methods)
                finally:
                    process.stdin.close()
                    try: process.wait(timeout=10)
                    except subprocess.TimeoutExpired: process.terminate(); process.wait(timeout=5)
                    process.stdout.close()
            require(not calls and not (home/'auth.json').exists(), 'Zero-turn fixture invoked a model or authentication')
            require(methods.count('thread/start') == 2 and not any(method in methods for method in
                    ('thread/resume', 'turn/start', 'thread/metadata/update')), 'Fixture changed its fixed effects')
            return {'emptyBrainReadbackQualified': True, 'binarySha256': sha256, 'nativeProcessEpochs': 2,
                'disposableProjects': 1, 'disposableEmptyBrains': 2, 'historyModes': ['paginated', 'legacy'],
                'metadataSamples': len(snapshots), 'projectMembershipSurvivesRestart': True,
                'nativeTurnStarts': 0, 'nativeLoads': 0, 'modelRequests': 0, 'cloudRequests': 0,
                'liveHostConnections': 0, 'terminalSafety': 'unknown', 'liveRepairApplied': False,
                'pilotAccepted': False}
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.executable, args.sha256), indent=2))
