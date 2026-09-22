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
parser.add_argument('--public-port', type=int, help='Optional disposable Compose gateway browser port')
parser.add_argument('--account', action='store_true', help='Enable a disposable local account instead of token pairing')
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='browser-auth-ui-') as directory:
    root = Path(directory).resolve()
    ledger = Ledger(root / 'state')
    ledger.initialize({'schemaVersion': 1, 'brainId': 'browser-auth-fixture', 'repositories': []})
    account_file = None
    if args.account:
        from orchestrator.account import configure
        account_file = root / 'account.json'
        configure(account_file, 'owner@example.test', 'fixture-only-password')
    server = Dashboard(ledger, args.port, root / '.env', runtime_root=root, public_port=args.public_port, account_file=account_file)
    # Deliberately public fixture-only credential; no real projects or services.
    if not args.account:
        server.bootstrap = 'disposable-browser-auth-fixture'
    print(server.origin + ('/' if args.account else '/#token=' + server.bootstrap), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
