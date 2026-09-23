"""Disposable session-map preview. Synthetic metadata only; no native effects.

Run: python3 tests/manual_session_map_fixture.py
"""
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestrator.core import Ledger
from orchestrator.server import Dashboard, WorkspaceRuntime
from orchestrator.workspaces import Registry

original_snapshot = WorkspaceRuntime.snapshot


def snapshot(runtime):
    state = original_snapshot(runtime)
    if runtime.workspace_id != 'map-preview':
        return state
    now = time.time()
    state['brainActivity'] = {
        'title': 'Coordinate the dashboard redesign', 'fresh': True,
        'status': 'running', 'observedAt': now - 12, 'checkedAt': now,
        'phase': 'Reviewing task results and preparing the next checkpoint.',
        'source': 'Synthetic preview fixture', 'reason': 'Fixture data, not live Codex activity.',
        'events': [{'at': now - 42, 'label': 'Result retained for interface review'},
                   {'at': now - 96, 'label': 'Implementation task registered'},
                   {'at': now - 300, 'label': 'Phase scope reviewed'}]}
    state['workers'] = [
        {'id': 'task-ui', 'packetId': 'Build the session map', 'repository': 'dashboard',
         'status': 'running', 'threadId': 'fixture-ui', 'nativeStatus': 'active', 'observedAt': now - 20,
         'createdAt': now - 900, 'note': 'Make the brain, its tasks and responsibilities visible in one place.',
         'evidence': {}, 'paths': ['web/session-map.js', 'web/session-map.css']},
        {'id': 'task-review', 'packetId': 'Review keyboard navigation', 'repository': 'accessibility',
         'status': 'blocked', 'threadId': 'fixture-review', 'createdAt': now - 800,
         'note': 'Review required: preserve focus when a status update arrives.', 'evidence': {}},
        {'id': 'task-tests', 'packetId': 'Verify the task lifecycle', 'repository': 'verification',
         'status': 'complete', 'threadId': 'fixture-tests', 'createdAt': now - 1200, 'completedAt': now - 100,
         'note': 'Synthetic completed-task example. Archival has not been observed.',
         'evidence': {'tests': {'status': 'verified', 'reference': 'Synthetic fixture result'},
                      'runtime': {'status': 'unverified'}}},
        {'id': 'task-pending', 'packetId': 'Check responsive layouts', 'repository': 'dashboard-mobile',
         'status': 'starting', 'threadId': None, 'clientThreadId': 'fixture-pending',
         'createdAt': now - 60, 'note': 'Waiting for a confirmed native task identity.', 'evidence': {}},
        {'id': 'task-archived', 'packetId': 'Preserve the previous layout', 'repository': 'history',
         'status': 'complete', 'threadId': 'fixture-history', 'archived': True,
         'createdAt': now - 3600, 'completedAt': now - 1800, 'evidence': {}}
    ]
    return state


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='session-map-preview-') as directory:
        root = Path(directory).resolve()
        registry = Registry(root / 'registry', create=True)
        for identity, name in [('map-preview', 'Session map · synthetic preview'), ('empty-preview', 'Empty project · synthetic preview')]:
            ledger = Ledger(root / identity)
            ledger.initialize({'schemaVersion': 1, 'brainId': 'fixture-brain-' + identity, 'repositories': []})
            registry.register(identity, name, ledger.root)
        server = Dashboard(registry.ledger('map-preview'), 8794, inference_env=root / '.env', runtime_root=root, registry=registry)
        server.bootstrap = 'disposable-session-map-preview'
        print(server.origin + '/#token=' + server.bootstrap, flush=True)
        with patch.object(WorkspaceRuntime, 'snapshot', snapshot):
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
