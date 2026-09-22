"""Disposable loopback UI fixture; never point this at real workspace state."""
import argparse
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestrator.core import Ledger
from orchestrator.server import Dashboard

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=8793)
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='browser-auth-ui-') as directory:
    root = Path(directory)
    ledger = Ledger(root / 'state')
    ledger.initialize({'schemaVersion': 1, 'brainId': 'browser-auth-fixture', 'repositories': []})
    server = Dashboard(ledger, args.port, root / '.env', runtime_root=root)
    # Deliberately public fixture-only credential; no real projects or services.
    server.bootstrap = 'disposable-browser-auth-fixture'
    print(server.origin + '/#token=' + server.bootstrap, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
