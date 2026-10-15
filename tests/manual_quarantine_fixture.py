"""Disposable rendered quarantine. No native connection, model or live ledger."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import standard_quarantine as quarantine
from orchestrator.server import Dashboard
from test_standard_quarantine import QuarantineTest


if __name__ == '__main__':
    fixture = QuarantineTest(methodName='runTest'); fixture.setUp()
    proposal = quarantine.prepare(fixture.registry, fixture.ledger)
    quarantine.confirm(fixture.registry, fixture.ledger, proposal['request'], proposal['reviewHash'])
    server = Dashboard(fixture.ledger, 0, registry=fixture.registry,
                       runtime_root=Path(__file__).resolve().parents[1],
                       inference_env=fixture.ledger.root/'absent.env')
    server.bootstrap = 'disposable-quarantine-fixture'
    print(json.dumps({'origin': server.origin, 'token': server.bootstrap}), flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close(); fixture.doCleanups()
