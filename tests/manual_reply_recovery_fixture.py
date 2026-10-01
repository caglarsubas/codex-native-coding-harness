"""Disposable rendered QA. Every native read/send is mocked; no live state."""
import json
import os
import threading
from unittest.mock import patch

from orchestrator import conversation, reply_recovery
from orchestrator.server import Dashboard
from orchestrator.workspaces import Registry
from test_reply_recovery import BRAIN, ReplyRecoveryTest


def main():
    fixture = ReplyRecoveryTest()
    fixture.setUp()
    root = fixture.ledger.root.parent
    registry = Registry(root / "platform", create=True)
    registry.register("fixture", "Disposable receipt recovery UI test · no native calls", fixture.ledger.root)
    ledger = registry.ledger("fixture")

    def retain_reply(command_id):
        token = ledger.acquire(BRAIN + ":rendered-fixture")
        try:
            reply_recovery.receive(ledger, token, command_id)
            conversation.reply(ledger, token, fixture.original["id"], {
                "message": "Fixture recovery retained the missing reply. Original diagnostic outcome remains unknown. "
                           "No original command was rerun; no Play, worker or native approval occurred.",
                "artifactIds": [], "decisionIds": []})
        finally:
            ledger.release(token, "Disposable fixture receipt closed; no native calls")

    def simulated_send(brain, message, command_id):
        assert "PRIVATE original" not in message
        timer = threading.Timer(1, retain_reply, args=(command_id,))
        timer.daemon = True
        timer.start()
        return {"status": "accepted", "nativeTurnId": "fixture-recovery-turn", "nativeDelivery": "owned_turn_start"}

    with patch("orchestrator.app_server_wake.AppServerWake.configured", return_value=True), \
         patch("orchestrator.app_server_wake.AppServerWake.send", side_effect=simulated_send):
        server = Dashboard(ledger, 0, registry=registry, inference_env=root / "missing.env",
                           notification_binding=fixture.binding)
        with os.fdopen(os.open(root / "session.json", os.O_CREAT | os.O_WRONLY, 0o600), "w") as stream:
            json.dump({"url": server.origin + "/#token=" + server.bootstrap,
                       "route": "#/w/fixture/conversation"}, stream)
        print(str(root / "session.json"), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.notifier.close()
            for runtime in server.runtimes.values():
                runtime.notifier.close()
            server.server_close()
            fixture.tearDown()


if __name__ == "__main__":
    main()
