"""Disposable task-declaration browser fixture. Never uses live ledgers or tools."""
import json
import os

from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from test_task_contracts import TaskContractTest


if __name__ == "__main__":
    fixture = TaskContractTest(); fixture.setUp(); fixture.propose()
    fixture.ledger.release(fixture.token, "Fixture declaration prepared; no task execution")
    root = fixture.fx.fx.root
    other = Ledger(root / "other")
    other.initialize({"schemaVersion": 1, "brainId": "brain-other", "repositories": []})
    fixture.registry.register("other", "Second product fixture", other.root)
    server = Dashboard(fixture.ledger, 0, root / "missing.env", registry=fixture.registry)
    with os.fdopen(os.open(root / "session.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as stream:
        json.dump({"url": server.origin + "/#token=" + server.bootstrap}, stream)
    print(json.dumps({"root": str(root), "origin": server.origin}), flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); fixture.tearDown()
