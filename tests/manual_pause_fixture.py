"""Disposable Pause UI fixture; no native tool, inference or real repository calls."""
import json
import os
import sys
import time
from pathlib import Path

from orchestrator.brain_control import park
from orchestrator.core import Ledger
from orchestrator.observations import capture
from orchestrator.server import Dashboard
from orchestrator.workspaces import Registry
from orchestrator.workspace_pause import observe
from test_workspace_pause import WorkspacePauseTest


def advance(root):
    registry = Registry(root / "platform"); ledger = registry.ledger("alpha")
    with ledger.tx() as db:
        meta = ledger.get(db, "meta", 1); token = meta["controller"]["token"]
    ledger.process(token)
    control = ledger.snapshot()["meta"]["brainControl"]; tasks = []
    for worker in ledger.snapshot()["workers"]:
        with ledger.tx() as db:
            artifact = capture(db, "worker-checkpoint", str(time.time()).encode(), {"repository": "a", "name": "worker-checkpoint.md",
                "orderAt": time.time(), "references": [{"session": worker["threadId"], "at": time.time()}]})
        tasks.append({"hostId": worker["hostId"], "threadId": worker["threadId"], "workerId": worker["id"],
            "parent": None, "status": "idle", "observedAt": time.time(), "checkpointArtifactId": artifact["id"]})
    evidence = {"workspaceId": "alpha", "commandId": control["commandId"], "observedAt": time.time(), "evidenceHash": "a"*64,
        "complete": True, "includesDescendants": True, "brain": {"hostId": "local", "threadId": "brain-fixture"}, "tasks": tasks}
    recorded = observe(ledger, token, control["commandId"], evidence)
    with ledger.tx() as db:
        artifact = capture(db, "brain-checkpoint", str(time.time()).encode(), {"repository": "a", "name": "brain-checkpoint.md", "orderAt": time.time(), "references": []})
    park(ledger, token, control["commandId"], {"summary": "Synthetic checkpoint. Native completion is not yet observed.",
        "artifactIds": [artifact["id"]], "pauseEvidenceHash": recorded["documentHash"]})
    ledger.release(token, "Synthetic checkpoint fixture")
    print("Fixture checkpoint retained; no native work performed.")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "checkpoint":
        advance(Path(sys.argv[2])); sys.exit()
    fixture = WorkspacePauseTest(); fixture.setUp(); fixture.fx.running()
    root = fixture.ledger.root.parent
    beta = Ledger(root / "beta")
    beta.initialize({"schemaVersion": 1, "brainId": "brain-beta", "repositories": []})
    fixture.registry.register("beta", "Second product fixture", beta.root)
    server = Dashboard(fixture.ledger, 0, root / "missing.env", registry=fixture.registry)
    with os.fdopen(os.open(root / "session.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as stream:
        json.dump({"url": server.origin + "/#token=" + server.bootstrap}, stream)
    print(json.dumps({"root": str(root), "origin": server.origin}), flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); fixture.tearDown()
