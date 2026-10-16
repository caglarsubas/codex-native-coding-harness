"""Disposable rendered backend-specific readiness; no native host is available."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator.server import Dashboard
from test_standard_preplay import PreplayTest
from test_public_native_tasks import CONTRACT


if __name__ == '__main__':
    fixture = PreplayTest('runTest'); fixture.setUp()
    fixture.deliver()
    fixture.mutate('commands', fixture.cid, lambda c: c['notification'].update(nativeTaskContract=CONTRACT))
    fixture.publish({'operation': 'catalog_error', 'requestId': fixture.cid,
        'code': 'native_schema_unavailable', 'detail': 'The public host has no desktop tools bridge. The old request is preserved.',
        'retryable': False})
    fixture.service()
    fixture.status_patch.stop()

    class Host:
        binding = {'brains': {fixture.brain: {'nativeTaskBackend': CONTRACT}}}
        def configured(self, *_): return True
        def connection_status(self, *_): return {'status': 'unchecked', 'checkedAt': None}
        def pending_approval(self, *_): return None
        def orphan_recovery_idle(self): return False
        def close(self): pass
        def send(self, *_): raise AssertionError('Rendered fixture cannot send native work')

    server = Dashboard(fixture.ledger, 0, registry=fixture.registry,
        runtime_root=Path(__file__).resolve().parents[1], inference_env=fixture.root/'absent.env')
    runtime = server.runtime_for('v3')
    runtime.notifier.app_server = Host()
    runtime.brain_activity.snapshot = lambda *_: {'status': 'unknown', 'observedAt': None}
    runtime.task_activity.snapshot = lambda *_: {}
    server.bootstrap = 'disposable-public-readiness-fixture'
    print(json.dumps({'origin': server.origin, 'token': server.bootstrap}), flush=True)
    before = fixture.proof()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        assert before == fixture.proof(), 'Rendered inspection must not create a request or change preserved state'
        server.server_close(); fixture.doCleanups()
