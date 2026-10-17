"""Opt-in compiled-runtime readiness fixture: isolated home, zero model turns.

Uses a pinned binary's real schemas/model/policy/identity reads over fixture
stdio. It does not qualify a live socket/binding, entitlement or terminal safety.
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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import public_readiness as readiness
from orchestrator.core import digest, require
from orchestrator.native_read_client import secure_path
from orchestrator.public_host_lifecycle import CONFIG
from qualify_public_native_tasks import StdioFixture


def qualify(binary, expected_hash):
    binary, _ = secure_path(binary)
    require(hashlib.sha256(binary.read_bytes()).hexdigest() == expected_hash, 'Exact reviewed fixture binary required')
    schemas = readiness.export_schemas(str(binary), expected_hash)
    calls = []
    class NoInference(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append('POST'); self.send_error(403)
        def do_GET(self):
            calls.append('GET'); self.send_error(404)
        def log_message(self, *_): pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), NoInference)
    waiter = threading.Thread(target=server.serve_forever, daemon=True); waiter.start()
    try:
        with tempfile.TemporaryDirectory(prefix='public-readiness-native.') as directory:
            root = Path(directory).resolve(); home = root/'home'; cwd = root/'checkout'
            home.mkdir(mode=0o700); cwd.mkdir(mode=0o700)
            (home/'config.toml').write_text('model = "gpt-6-astra"\nmodel_provider = "fixture"\n'+CONFIG+f'''
[model_providers.fixture]
name = "Disposable no-inference fixture"
base_url = "http://127.0.0.1:{server.server_port}/v1"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
''')
            env = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'CODEX_HOME': str(home), 'TMPDIR': str(root)}
            process = subprocess.Popen([str(binary), 'app-server', '--stdio'], cwd=cwd, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                io = StdioFixture(process)
                io._rpc('initialize', {'clientInfo': {'name': 'public_readiness_fixture', 'version': '1'},
                    'capabilities': {'experimentalApi': True}})
                process.stdin.write(b'{"method":"initialized","params":{}}\n'); process.stdin.flush()
                project = io._rpc('project/create', {'name': 'Disposable readiness fixture',
                    'roots': [{'path': str(cwd)}], 'idempotencyKey': str(uuid.uuid4())})['project']
                thread = io._rpc('thread/start', {'cwd': str(cwd), 'projectId': project['id'],
                    'approvalPolicy': 'on-request', 'approvalsReviewer': 'user', 'sandbox': 'workspace-write',
                    'config': {'features': {'code_mode': {'enabled': False}}}, 'ephemeral': False})['thread']
                brain = thread['id']; command = str(uuid.uuid4())
                backend = {'protocol': readiness.PROTOCOL, 'sourceCommit': 'a'*40, 'sourceTree': 'b'*40,
                    'trust': 'operator_reviewed_build_v1', 'desktopBridge': 'absent', 'repositoryMode': 'repo_exclusive'}
                binding = {'endpoint': {'executable': str(binary), 'sha256': expected_hash}, 'brains': {brain: {
                    'cwd': str(cwd), 'projectId': project['id'], 'catalogProjectId': str(uuid.uuid4()),
                    'nativeTaskBackend': backend, 'policyEvidence': {'protocol': 'loaded_thread_policy_v1',
                        'sourceCommit': 'a'*40, 'sourceTree': 'b'*40}}}}
                # Fixture stdio has no socket epoch. The production endpoint
                # validator is separately covered in unit tests; never label
                # this fixture as reviewed live-binding/source-build evidence.
                def pin_fixture(endpoint):
                    require(endpoint == binding['endpoint'] and
                        hashlib.sha256(binary.read_bytes()).hexdigest() == expected_hash, 'Fixture binary changed')
                with patch.object(readiness, 'validate_endpoint', side_effect=pin_fixture):
                    evidence = readiness.collect(io, binding, brain, command, 'd'*64)
                readiness.validate(evidence, digest(binding), brain, command, 'd'*64)
                require(evidence['schema'] == schemas and not calls and not (home/'auth.json').exists(),
                        'Readiness fixture made an unexpected provider/authentication request')
                require(not any(m in io.methods for m in ('thread/resume', 'turn/start')),
                        'Readiness must not reload or start a model turn')
                return {'binarySha256': expected_hash, 'compiledSchemasVerified': True,
                    'advertisedModels': len(evidence['models']), 'repeatedModelReads': io.methods.count('model/list'),
                    'effectivePolicyVerified': True, 'disposableProjects': 1, 'disposableThreads': 1,
                    'nativeLoads': 0, 'turnStarts': 0, 'providerRequests': len(calls), 'liveHostConnections': 0,
                    'liveWrites': 0, 'modelEntitlementVerified': False, 'terminalSafety': 'unknown', 'pilotAccepted': False,
                    'fixtureSourcePinsAreSynthetic': True, 'liveBindingQualified': False}
            finally:
                process.stdin.close()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate(); process.wait(timeout=5)
                process.stdout.close()
    finally:
        server.shutdown(); waiter.join(timeout=2); server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True); parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(qualify(args.executable, args.sha256), sort_keys=True))
