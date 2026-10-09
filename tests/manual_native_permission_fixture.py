"""Disposable owner-permission UI fixture; no Codex connection or live state.

Run with PYTHONPATH=tests:. python3 tests/manual_native_permission_fixture.py.
Ctrl-C closes the server and removes its temporary ledgers.
"""
import time

from orchestrator.core import canonical
from test_native_approval_server import NativeApprovalServerTest


if __name__ == "__main__":
    fixture = NativeApprovalServerTest()
    fixture.setUp()
    try:
        fixture.server.bootstrap = "native-permission-disposable-fixture-only"
        fixture.wake.pending["expiresAt"] = time.time() + 6 * 3600
        ledger = fixture.registry.ledger("a")
        with ledger.tx() as db:
            worker = {"id": "fixture-task", "queueId": "fixture-queue",
                      "threadId": "fixture-native-task", "packetId": "fixture-packet",
                      "title": "Synthetic worker — no native task", "status": "running",
                      "repository": "fixture", "createdAt": time.time(),
                      "nativeStatus": "idle", "observedAt": time.time()}
            db.execute("INSERT INTO workers(id,queue_id,data) VALUES(?,?,?)",
                       (worker["id"], worker["queueId"], canonical(worker)))
        print(fixture.server.origin + "/#token=" + fixture.server.bootstrap, flush=True)
        fixture.thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            assert fixture.wake.calls == [], "Rendered inspection must not send a native response"
        finally:
            fixture.tearDown()
