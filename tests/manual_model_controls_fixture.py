"""Temporary model policy UI fixture; fictitious catalog, no native/model calls."""
from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from test_model_controls import ModelControlsTest


if __name__ == "__main__":
    fixture = ModelControlsTest(); fixture.setUp()
    root = fixture.registry.root.parent
    other = Ledger(root / "empty-model-workspace")
    other.initialize({"schemaVersion": 1, "brainId": "empty-fixture", "repositories": []})
    fixture.registry.register("empty", "Second product · no catalog", other.root)
    server = Dashboard(fixture.ledger, 0, root / "missing.env", registry=fixture.registry,
                       notification_cli="/nonexistent-fixture-notifier")
    server.bootstrap = "model-policy-owner-fixture-only"
    print(server.origin + "/#token=" + server.bootstrap, flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); fixture.doCleanups()
