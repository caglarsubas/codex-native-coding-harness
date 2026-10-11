"""Disposable rendered inspection-record QA; every native observation is synthetic.

Run: python3 tests/manual_ended_recovery_fixture.py --port 0
Reuses the authenticated source adapter and disposable test ledger. Fixed
metadata, identity, endpoint and catalog seams are mocked. No live data, real
host, inference service, native turn or runtime installation is contacted.
"""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestrator.server import Dashboard, WorkspaceRuntime
from test_ended_recovery_record import EndedRecoveryRecordTest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    fixture = EndedRecoveryRecordTest()
    fixture.setUp()
    try:
        server = Dashboard(fixture.ledger, args.port, registry=fixture.registry,
                           runtime_root=fixture.f.fixture.root,
                           inference_env=fixture.f.fixture.root / "missing.env")
        runtime = server.runtime_for("alpha")
        runtime.notifier.app_server = fixture.f.host
        runtime.turn_recovery_controls = fixture.controls
        def refuse_send(*_):
            raise AssertionError("Rendered inspection QA cannot send a native instruction")
        fixture.f.host.send = refuse_send
        server.bootstrap = "disposable-ended-recovery-record-preview"
        original = WorkspaceRuntime.snapshot
        def snapshot(runtime):
            state = original(runtime)
            state["workspace"]["name"] = "Disposable recovery inspection · synthetic metadata"
            return state
        print(server.origin + "/#token=" + server.bootstrap, flush=True)
        with patch.object(WorkspaceRuntime, "snapshot", snapshot):
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
    finally:
        fixture.tearDown()
