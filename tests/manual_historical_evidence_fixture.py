"""Disposable rendered multi-host/missing-effect QA; no real native I/O.

python3 tests/manual_historical_evidence_fixture.py --port 0 [--known]
All identity, native metadata and PID seams use temporary synthetic fixtures.
The default scenario has a missing call result. --known tests non-execution
and its separately reviewed blocked/unqualified closeout, never pilot success.
"""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from orchestrator.server import Dashboard, WorkspaceRuntime
from test_historical_multi_host import MultiHostHistoryTest


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=0)
    parser.add_argument("--known",action="store_true")
    args=parser.parse_args()
    fixture=MultiHostHistoryTest(); fixture.setUp()
    try:
        if not args.known:fixture.f.turns[-1]["items"]=[]
        server=Dashboard(fixture.ledger,args.port,registry=fixture.f.registry,
            runtime_root=fixture.f.f.f.fixture.root,inference_env=fixture.f.f.f.fixture.root/"missing.env")
        runtime=server.runtime_for("alpha")
        runtime.notifier.app_server=fixture.f.host
        runtime.historical_controls=fixture.controls
        def refuse_send(*_):raise AssertionError("Rendered QA has no native send permit")
        fixture.f.host.send=refuse_send
        server.bootstrap="disposable-multi-host-historical-evidence"
        original=WorkspaceRuntime.snapshot
        def snapshot(runtime):
            state=original(runtime)
            state["workspace"]["name"]="Disposable multi-host history · synthetic evidence"
            return state
        print(server.origin+"/#token="+server.bootstrap,flush=True)
        with patch.object(WorkspaceRuntime,"snapshot",snapshot):
            try:server.serve_forever()
            except KeyboardInterrupt:pass
            finally:server.server_close()
    finally:fixture.tearDown()
