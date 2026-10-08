"""Disposable rendered Pause recovery QA; every native read/send is mocked."""
import json
import argparse
import os
import threading
from unittest.mock import patch

from orchestrator.server import Dashboard
from test_pause_recovery import PauseRecoveryTest
from test_pause_host_continuity import HostContinuityTest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replacement', action='store_true', help='Render a proved failed first recovery; all native operations remain mocked')
    parser.add_argument('--host-continuity', action='store_true', help='Render exact old/new host continuity; no real connection or effect')
    args = parser.parse_args()
    continuity_fixture = HostContinuityTest() if args.host_continuity else None
    if continuity_fixture:
        continuity_fixture.setUp(); fixture = continuity_fixture.f
    else:
        fixture = PauseRecoveryTest(); fixture.setUp()
    if args.replacement and not continuity_fixture:
        fixture.failed_first()
    ledger, registry = fixture.ledger, fixture.registry
    root = fixture.fixture.root

    def checkpoint(command_id):
        token = ledger.acquire(fixture.brain+":rendered-fixture")
        try:
            fixture.fixture.call("pause_recovery_receive", token=token, requestId=command_id)
            fixture.fixture.call("checkpoint", token=token, outcome="paused", brainObservedTokens=None,
                summary="Disposable fixture: saved Pause received and paused checkpoint retained. Usage remains unknown. No native call, worker or pilot qualification.",
                reasonCodes=["usage_evidence"])
        finally:
            ledger.release(token, "Disposable fixture checkpoint retained; no native calls")

    def simulated_send(brain, message, command_id):
        assert "pause_recovery_receive" in message
        timer = threading.Timer(2, checkpoint, args=(command_id,)); timer.daemon = True; timer.start()
        return {"status": "accepted", "nativeTurnId": "fixture-recovery-turn", "nativeDelivery": "owned_turn_start"}

    with patch("orchestrator.app_server_wake.AppServerWake.configured", return_value=True), \
         patch("orchestrator.app_server_wake.AppServerWake.send", side_effect=simulated_send):
        server = Dashboard(ledger, 0, registry=registry, inference_env=root/"missing.env",
                           notification_binding=fixture.host.binding,
                           pause_recovery_prior_binding=getattr(fixture.host, 'pause_recovery_prior_binding', None))
        with os.fdopen(os.open(root/"session.json", os.O_CREAT|os.O_WRONLY, 0o600), "w") as stream:
            json.dump({"url": server.origin+"/#token="+server.bootstrap,
                       "route": "#/w/alpha/overview"}, stream)
        print(str(root/"session.json"), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.notifier.close()
            for runtime in server.runtimes.values(): runtime.notifier.close()
            server.server_close()
            (continuity_fixture or fixture).tearDown()


if __name__ == "__main__": main()
