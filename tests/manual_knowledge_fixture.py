"""Isolated rendered Knowledge QA. No native task, model or live project."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

from orchestrator.core import Ledger
from orchestrator.project_knowledge import refresh
from orchestrator.server import Dashboard
from orchestrator.workspaces import Registry


if __name__ == '__main__':
    root = Path(tempfile.mkdtemp(prefix='orchestrator-knowledge-ui-')).resolve()
    repo = root / 'project'
    (repo / 'src').mkdir(parents=True)
    (repo / 'src' / 'service.py').write_text('from src.helper import helper\n\ndef verified_source():\n    return helper()\n')
    (repo / 'src' / 'helper.py').write_text('def helper():\n    return "fixture"\n')
    subprocess.run(['git', '-C', str(repo), 'init', '-q'], check=True)
    subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.email=fixture@example.invalid',
                    '-c', 'user.name=Fixture', 'commit', '-qm', 'Fixture source'], check=True)
    ledger = Ledger(root / 'private')
    ledger.initialize({'schemaVersion': 1, 'brainId': str(uuid.uuid4()), 'repositories': [
        {'id': 'sample', 'path': str(repo), 'projectId': 'fixture', 'ref': 'HEAD',
         'policyProfile': 'standard', 'mergePolicy': 'manual'}]})
    executable = os.environ.get('GRAPHIFY_TEST_EXECUTABLE')
    provider = None
    if executable:
        path = Path(executable).resolve()
        provider = {'executable': str(path), 'version': '0.9.66',
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (ledger.root / 'knowledge.json').write_text(json.dumps({
        'schemaVersion': 1, 'repositories': {'sample': ['src/']}, 'graphify': provider}))
    refresh(ledger, 'sample')
    registry = Registry(root / 'platform', create=True)
    registry.register('fixture', 'Knowledge fixture', ledger.root)
    server = Dashboard(registry.ledger('fixture'), 8771, root / '.env', runtime_root=root, registry=registry)
    fd = os.open(root / 'session.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'url': server.origin + '/#token=' + server.bootstrap}, stream)
    print(root, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
