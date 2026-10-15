"""Explicit rendered fixture: two disposable ledgers, no native endpoint."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator.server import Dashboard
from orchestrator import standard
from orchestrator.workspaces import fingerprint
from test_standard_successor import SuccessorTest


if __name__ == '__main__':
    fixture = SuccessorTest(methodName='runTest'); fixture.setUp()
    fixture.confirm()  # Synthetic owner control in this disposable fixture only.
    with standard.read_db(fixture.target.db) as db: before = fingerprint(db)
    server = Dashboard(fixture.source, 0, registry=fixture.registry,
                       runtime_root=Path(__file__).resolve().parents[1],
                       inference_env=fixture.target.root/'missing.env')
    for workspace in ('alpha', 'beta'):
        runtime = server.runtime_for(workspace)
        runtime.brain_activity.snapshot = lambda *_: {'status': 'unknown', 'observedAt': None}
        runtime.task_activity.snapshot = lambda *_: {}
    server.bootstrap = 'disposable-successor-render-fixture'
    print(json.dumps({'origin': server.origin, 'token': server.bootstrap}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        fixture.assert_source_unchanged()
        with standard.read_db(fixture.target.db) as db:
            assert fingerprint(db) == before, 'Rendered reads changed successor ledger'
        fixture.doCleanups()
