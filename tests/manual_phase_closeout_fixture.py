"""Disposable closeout browser rehearsal. Every native response is synthetic.

No live state, Codex host, inference service or native task is used.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestrator.server import Dashboard
from test_phase_closeout import PhaseCloseoutTest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8803)
    args = parser.parse_args()
    f = PhaseCloseoutTest()
    f.setUp()
    # No native permission request exists in this synthetic host. Do not make
    # the unrelated permission inspector try to contact a real connection.
    f.f.native.pending_approval = lambda brain_id: None
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
