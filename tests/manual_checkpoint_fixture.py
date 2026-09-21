"""Disposable saved-report dashboard; no native calls, notifications or inference."""
import json
import os

from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from test_phase_checkpoints import PhaseCheckpointTest


if __name__ == "__main__":
    fixture = PhaseCheckpointTest(); fixture.setUp()
    fixture.prepare(); fixture.prepare()
    registry = fixture.fx.fx.registry
    root = registry.root.parent
    other = Ledger(root / "empty-workspace")
    other.initialize({"schemaVersion": 1, "brainId": "empty-brain", "repositories": []})
    registry.register("empty", "Second product · no reports", other.root)
    server = Dashboard(fixture.ledger, 0, root / "missing.env", registry=registry)
    with os.fdopen(os.open(root / "checkpoint-session.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as stream:
        json.dump({"url": server.origin + "/#token=" + server.bootstrap}, stream)
    print(json.dumps({"root": str(root), "origin": server.origin}), flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); fixture.tearDown()
