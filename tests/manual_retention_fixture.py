"""Disposable two-workspace browser fixture; no native/archive/inference calls."""
from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from test_retention_controls import RetentionControlsTest


if __name__ == "__main__":
    fixture = RetentionControlsTest(); fixture.setUp()
    try:
        registry = fixture.fx.api.bridge.registry
        if "b" not in {w["id"] for w in registry.list()}:
            other = Ledger(registry.root.parent / "other-fixture")
            other.initialize({"schemaVersion": 1, "brainId": "brain-other-fixture", "repositories": []})
            registry.register("b", "Other fixture", other.root)
        server = Dashboard(fixture.ledger, 0, registry.root.parent / "missing.env", registry=registry,
                           runtime_root=registry.root, notification_cli="/nonexistent-fixture-notifier")
        server.bootstrap = "retention-controls-fixture-only"
        print(server.origin + "/#token=" + server.bootstrap, flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
        finally: server.server_close()
    finally: fixture.doCleanups()
