"""Disposable session-map preview. Synthetic metadata only; no native effects.

Run: python3 tests/manual_session_map_fixture.py
"""
from pathlib import Path
import argparse
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
        {'id': 'task-ui', 'packetId': 'WSP-UI-01', 'title': 'Build the session map', 'repository': 'dashboard',
         'status': 'running', 'threadId': 'fixture-ui', 'nativeStatus': 'active', 'observedAt': now - 20,
         'createdAt': now - 900, 'note': 'Make the brain, its tasks and responsibilities visible in one place.',
         'commit': 'a'*40, 'branch': 'codex/map', 'pr': 'https://github.com/example/dashboard/pull/17',
         'evidence': {'ci': {'status': 'verified', 'reference': 'Synthetic CI proof'}}, 'paths': ['web/session-map.js', 'web/session-map.css']},
        {'id': 'task-review', 'packetId': 'WSP-UI-02', 'title': 'Review keyboard navigation', 'repository': 'accessibility',
         'status': 'blocked', 'threadId': 'fixture-review', 'createdAt': now - 800,
         'nativeStatus': 'idle', 'observedAt': now - 30,
         'note': 'Review required: preserve focus when a status update arrives.', 'evidence': {'ci': {'status': 'failed', 'reference': 'Synthetic failed CI proof'}}},
        {'id': 'task-tests', 'packetId': 'WSP-UI-03', 'title': 'Verify the task lifecycle', 'repository': 'verification',
         'status': 'complete', 'threadId': 'fixture-tests', 'createdAt': now - 1200, 'completedAt': now - 100,
         'note': 'Synthetic completed-task example. Archival has not been observed.',
         'commit': 'b'*40,
         'evidence': {'ci': {'status': 'not_applicable'}, 'tests': {'status': 'verified', 'reference': 'Synthetic fixture result'},
                      'runtime': {'status': 'unverified'}}},
        {'id': 'task-pending', 'title': 'Check responsive layouts', 'repository': 'dashboard-mobile',
         'status': 'starting', 'threadId': None, 'clientThreadId': 'fixture-pending',
         'createdAt': now - 60, 'note': 'Waiting for a confirmed native task identity.', 'evidence': {}},
        {'id': 'task-stale', 'packetId': 'WSP-UI-04', 'title': 'Inspect a quiet task', 'repository': 'dashboard',
         'status': 'running', 'threadId': 'fixture-stale', 'nativeStatus': 'active', 'observedAt': now - 600,
         'createdAt': now - 1800, 'note': 'Old activity cannot prove this task is still working.', 'evidence': {}},
        {'id': 'task-archived', 'packetId': 'WSP-UI-00', 'title': 'Preserve the previous layout', 'repository': 'history',
         'status': 'complete', 'threadId': 'fixture-history', 'archived': True,
         'createdAt': now - 50*86400, 'completedAt': now - 40*86400, 'evidence': {}}
    ]
    state['observations']['git'] = [
        {'repository': 'dashboard', 'status': 'measured', 'at': now-120, 'remoteStatus': 'observed', 'remoteAt': now-120,
         'worktrees': [], 'branches': [{'branch': 'codex/map', 'commit': 'a'*40, 'remoteCommit': 'a'*40}],
         'pullRequests': [{'number': 17, 'url': 'https://github.com/example/dashboard/pull/17', 'title': 'Build the map',
                           'state': 'open', 'draft': False, 'head': 'a'*40, 'branch': 'codex/map'}]},
        {'repository': 'verification', 'status': 'measured', 'at': now-200, 'remoteStatus': 'observed', 'remoteAt': now-200,
         'worktrees': [], 'branches': [], 'pullRequests': [{'number': 9, 'url': 'https://github.com/example/verification/pull/9',
          'title': 'Task lifecycle', 'state': 'merged', 'draft': False, 'head': 'b'*40, 'mergeCommit': 'c'*40}]}]
    return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8794)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='session-map-preview-') as directory:
        root = Path(directory).resolve()
        registry = Registry(root / 'registry', create=True)
        for identity, name in [('map-preview', 'Session map · synthetic preview'), ('empty-preview', 'Empty project · synthetic preview')]:
            ledger = Ledger(root / identity)
            ledger.initialize({'schemaVersion': 1, 'brainId': 'fixture-brain-' + identity, 'repositories': []})
            registry.register(identity, name, ledger.root)
        server = Dashboard(registry.ledger('map-preview'), args.port, inference_env=root / '.env', runtime_root=root, registry=registry)
        server.bootstrap = 'disposable-session-map-preview'
        print(server.origin + '/#token=' + server.bootstrap, flush=True)
        with patch.object(WorkspaceRuntime, 'snapshot', snapshot):
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
