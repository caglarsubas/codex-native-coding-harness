"""Disposable rendered review; native RPCs are the labelled unit fixture only."""
import json
import signal
from pathlib import Path
import sys
import threading

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from orchestrator.server import Dashboard
from test_readiness_owned import ReadinessOwnedTest

if __name__ == '__main__':
    signal.signal(signal.SIGINT,signal.default_int_handler)
    http_thread=threading.Thread
    fixture=ReadinessOwnedTest('runTest'); fixture.setUp()
    # The unit fake suppresses observer threads. HTTP handlers need real
    # threads; this rendered fixture never calls notification/confirmation.
    threading.Thread=http_thread
    server=Dashboard(fixture.ledger,0,registry=fixture.registry,
        runtime_root=Path(__file__).resolve().parents[1],inference_env=fixture.f.root/'absent.env')
    runtime=server.runtime_for('v3'); runtime.notifier.app_server=fixture.wake
    runtime.brain_activity.snapshot=lambda *_:{'status':'unknown','observedAt':None}
    runtime.task_activity.snapshot=lambda *_:{}
    server.bootstrap='disposable-readiness-owned-fixture'
    print(json.dumps({'origin':server.origin,'token':server.bootstrap}),flush=True)
    before=fixture.f.proof()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        assert before==fixture.f.proof(),'Review must not create a command or change old state'
        assert not fixture.calls or all(m not in ('thread/resume','turn/start') for m,_ in fixture.calls)
        server.server_close(); fixture.doCleanups()
