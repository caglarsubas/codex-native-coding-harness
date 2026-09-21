"""Disposable owner-control fixture; never supplies native or inference credentials."""
from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from test_checkpoint_controls import CheckpointControlsTest


if __name__ == "__main__":
    fixture = CheckpointControlsTest(); fixture.setUp()
    root = fixture.registry.root.parent
    other = Ledger(root / "empty-workspace")
    other.initialize({"schemaVersion": 1, "brainId": "empty-fixture", "repositories": []})
    fixture.registry.register("empty", "Second product · no checkpoint", other.root)
    server = Dashboard(fixture.ledger, 0, root / "missing.env", registry=fixture.registry,
                       notification_cli="/nonexistent-fixture-notifier")
    # Public constant is confined to this temporary test server, not the live dashboard.
    server.bootstrap = "checkpoint-owner-fixture-only"
    print(server.origin + "/#token=" + server.bootstrap, flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); fixture.doCleanups()
