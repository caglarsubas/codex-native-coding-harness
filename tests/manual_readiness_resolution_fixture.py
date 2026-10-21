"""Disposable browser projection after a local-only pre-start resolution."""
import json
from pathlib import Path
import signal
import sys
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orchestrator.server import Dashboard
from test_readiness_deadline_resolution import PrestartResolutionTest

if __name__=='__main__':
    real_thread=threading.Thread
    f=PrestartResolutionTest('test_exact_disposition_preserves_request_claims_and_does_not_enable_play')
    f.setUp(); f.apply(); f.conserved()
    threading.Thread=real_thread
    server=Dashboard(f.ledger,0,registry=f.registry,runtime_root=Path(__file__).resolve().parents[1],
                     inference_env=f.r.f.root/'absent.env')
    server.daemon_threads=False
    runtime=server.runtime_for(f.ledger.workspace_id)
    runtime.brain_activity.snapshot=lambda *_:{'status':'unknown','observedAt':None}
    runtime.task_activity.snapshot=lambda *_:{}
    server.bootstrap='disposable-prestart-resolution'
    print(json.dumps({'origin':server.origin,'token':server.bootstrap,'workspace':f.ledger.workspace_id}),flush=True)
    signal.signal(signal.SIGINT,signal.default_int_handler)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close(); f.conserved(); f.doCleanups()
