"""Disposable rendered disposition; no native connection, live data or models."""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orchestrator.server import Dashboard
from test_canceled_play import CanceledPlayTest

if __name__ == '__main__':
    fixture = CanceledPlayTest('runTest'); fixture.setUp(); fixture.apply()
    server = Dashboard(fixture.ledger,0,registry=fixture.registry,
        runtime_root=Path(__file__).resolve().parents[1],inference_env=fixture.f.root/'absent.env')
    server.bootstrap = 'disposable-canceled-play-fixture'
    print(json.dumps({'origin':server.origin,'token':server.bootstrap}),flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close(); fixture.conserved(); fixture.doCleanups()
