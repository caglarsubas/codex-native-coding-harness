"""Disposable rendered recovery UI; no certificate/native/operational authority."""
import contextlib
import hashlib
import json
from pathlib import Path
import signal
import sqlite3
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator import post_reboot_dashboard as api, maintenance_dashboard as web


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary).resolve(); root.chmod(0o700)
        ledger = root / 'original.sqlite3'
        with contextlib.closing(sqlite3.connect(ledger)) as db, db:
            db.execute('CREATE TABLE old(value TEXT)'); db.execute("INSERT INTO old VALUES ('original request, usage and claims')")
        before = hashlib.sha256(ledger.read_bytes()).hexdigest()
        view = root / 'view'; view.mkdir(mode=0o700)
        context = {'workspaceId': 'disposable-recovery', 'brainId': 'fixture-brain', 'latestTurnId': 'fixture-ended-turn',
            'pid': 12345, 'originalReadinessId': 'fixture-original-readiness', 'historicalObservedAt': time.time() - 86400,
            'originalUsage': {'observedLastTurnTokens': None, 'chargedReservationFloor': 15823,
                'carriedPhaseCeiling': 5736373, 'futurePhaseCeiling': 5720550, 'coverage': 'per_turn_not_lifetime',
                'gaps': ['lifetime_coverage_not_asserted', 'fixture_unknown_usage']}}
        review = {'port': 0, 'repairFile': 'fixture-only', 'launchedSource': 'fixture-only',
                  'sourceHash': api.source_hash(), 'context': context, 'evidencePins': {}}
        observation = {'observedAt': time.time() - 600, 'observation': {'activity': 'notLoaded', 'policy': None},
                       'authentication': {'accountPresent': True, 'ready': True}}
        def foundation(*_):
            assert hashlib.sha256(ledger.read_bytes()).hexdigest() == before
            return context, None, None, None
        with patch.object(api, 'foundation', side_effect=foundation), patch.object(api, 'collect', side_effect=AssertionError('No native polling')):
            server = web.RecoveryDashboard(review, observation, view)
            print(json.dumps({'origin': server.origin, 'token': server.bootstrap}), flush=True)
            signal.signal(signal.SIGINT, signal.default_int_handler)
            try: server.serve_forever()
            except KeyboardInterrupt: pass
            finally:
                server.server_close()
                assert hashlib.sha256(ledger.read_bytes()).hexdigest() == before
