"""Temporary UI fixture. No native tool, model service or live ledger access."""
from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from test_rereview_controls import RereviewControlsTest


if __name__ == "__main__":
    fixture = RereviewControlsTest(); fixture.setUp()
    root = fixture.registry.root.parent
    other = Ledger(root / "empty-workspace")
    other.initialize({"schemaVersion": 1, "brainId": "empty-fixture", "repositories": []})
    fixture.registry.register("empty", "Second product · no settled results", other.root)
    server = Dashboard(fixture.ledger, 0, root / "missing.env", registry=fixture.registry,
                       notification_cli="/nonexistent-fixture-notifier")
    server.bootstrap = "rereview-owner-fixture-only"
    print(server.origin + "/#token=" + server.bootstrap, flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); fixture.doCleanups()
