"""Disposable budget dashboard; synthetic samples, no inference or native calls.

Run with PYTHONPATH=tests:. python3 tests/manual_budget_fixture.py.
The printed link is a fixture-only credential; Ctrl-C removes temporary ledgers.
"""
from unittest.mock import patch

from orchestrator.server import Dashboard
from test_phase_usage import PhaseUsageTest
import test_dispatch_admission


if __name__ == "__main__":
    # Longer valid evidence age for visual inspection, in this temporary fixture only.
    with patch.object(test_dispatch_admission, "POLICY", {**test_dispatch_admission.POLICY, "maxObservationAgeSeconds": 300}):
        fixture = PhaseUsageTest(); fixture.setUp()
    try:
        fixture.start(); fixture.save(); fixture.second_workspace()
        registry = fixture.fx.registry
        server = Dashboard(fixture.ledger, 0, registry.root.parent / "missing.env", registry=registry,
                           notification_cli="/nonexistent-fixture-notifier")
        server.bootstrap = "budget-visibility-fixture-only"
        print(server.origin + "/#token=" + server.bootstrap, flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()
    finally: fixture.doCleanups()
