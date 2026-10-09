"""Disposable closeout browser rehearsal. Every native response is synthetic.

No live state, Codex host, inference service or native task is used.
"""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestrator.server import Dashboard
from test_phase_closeout import PhaseCloseoutTest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8803)
    parser.add_argument("--duration-stopped", action="store_true",
                        help="Rehearse a retained duration stop before the legacy Play clock expires")
    parser.add_argument("--review-seconds", type=int, default=300, choices=range(1, 301),
                        help="Disposable-only review clock for rendered expiry testing")
    args = parser.parse_args()
    import orchestrator.assistant_journey as journey
    journey.TTL = args.review_seconds
    f = PhaseCloseoutTest()
    f.setUp()
    if args.duration_stopped:
        def duration_stop(meta):
            run = meta["standardRun"]
            run["expiresAt"] = run["startedAt"] + 24 * 3600
            run["checkpoint"]["reasonCodes"] = ["duration", "external_dependency"]
            run["checkpoint"]["summary"] = "The mission's four-hour duration stopped before the legacy 24-hour Play window."
        f.mutate(duration_stop)
    # No native permission request exists in this synthetic host. Do not make
    # the unrelated permission inspector try to contact a real connection.
    f.f.native.pending_approval = lambda brain_id: None
    connection = {"status": "unchecked", "checkedAt": None, "detail": "Synthetic host, not checked."}
    f.f.native.connection_status = lambda brain_id: dict(connection)
    def check_connection(brain_id):
        connection.update(status="disconnected", checkedAt=time.time(),
                          detail="Synthetic offline host. No native request was sent.")
        return dict(connection)
    f.f.native.check_connection = check_connection
    server = Dashboard(f.ledger, args.port, registry=f.registry, runtime_root=f.f.fixture.root,
                       inference_env=f.f.fixture.root / "absent.env")
    server.runtime_for("alpha").notifier.app_server = f.f.native
    server.bootstrap = "disposable-closeout-preview-only"
    print(server.origin + "/#token=" + server.bootstrap, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        f.tearDown()
