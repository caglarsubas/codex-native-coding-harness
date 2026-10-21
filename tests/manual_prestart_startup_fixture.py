"""Disposable read-only browser state for the new preparation-only result."""
import json
from pathlib import Path
import signal
import sys
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orchestrator.server import Dashboard
from test_prestart_startup import StartupTest

if __name__=='__main__':
    real_thread=threading.Thread
    f=StartupTest('test_one_new_load_turn_receipt_and_usage_without_catalog_or_old_receipt')
    f.setUp(); f.apply(); f.conserved()
    threading.Thread=real_thread
    server=Dashboard(f.ledger,0,registry=f.registry,runtime_root=Path(__file__).resolve().parents[1],
                     inference_env=f.r.f.root/'absent.env')
    server.daemon_threads=False
    runtime=server.runtime_for(f.ledger.workspace_id)
    runtime.brain_activity.snapshot=lambda *_:{'status':'unknown','observedAt':None}
    runtime.task_activity.snapshot=lambda *_:{}
    server.bootstrap='disposable-new-startup'
    print(json.dumps({'origin':server.origin,'token':server.bootstrap,'workspace':f.ledger.workspace_id}),flush=True)
    signal.signal(signal.SIGINT,signal.default_int_handler)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close(); f.conserved(); f.doCleanups()
