"""Rendered disposable policy diagnostic; never connects a real native host."""
import json
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator.server import Dashboard
from test_standard_native_policy import NativePolicyTest


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authentication-required',action='store_true')
    args=parser.parse_args()
    fixture = NativePolicyTest(methodName="runTest")
    fixture.setUp()
    fixture.bind()
    fixture.fixture.call("checkpoint", outcome="paused", summary="Synthetic policy gap; terminals unknown",
                         brainObservedTokens=None, reasonCodes=["other_policy"])
    class Host:
        def configured(self, *_): return True
        def connection_status(self, *_): return {"status": "unchecked", "checkedAt": None}
        def policy_status(self, *_):
            if args.authentication_required:
                return {"status":"matching","checkedAt":1,"policyVerified":True,
                        "authentication":{"status":"authentication_required","ready":False},
                        "detail":"Loaded policy matches, but the native host needs sign-in. No login or Resume was sent."}
            return {"status": "unknown", "checkedAt": 1, "policyVerified": False,
                    "detail": "Unloaded native policy remains unknown. No Resume was sent."}
        def check_policy(self, *_): return self.policy_status()
        def pending_approval(self, *_): return None
        def orphan_recovery_idle(self): return False
        def close(self): pass
        def send(self, *_): raise AssertionError("Rendered fixture cannot send a native instruction")
    server = Dashboard(fixture.ledger, 0, registry=fixture.fixture.registry,
                       runtime_root=Path(__file__).resolve().parents[1],
                       inference_env=fixture.fixture.root / "missing.env")
    runtime = server.runtime_for("alpha")
    runtime.notifier.app_server = Host()
    runtime.brain_activity.snapshot = lambda *_: {"status": "unknown", "observedAt": None}
    runtime.task_activity.snapshot = lambda *_: {}
    server.bootstrap = "disposable-policy-adapter-fixture"
    print(json.dumps({"origin": server.origin, "token": server.bootstrap}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        fixture.doCleanups()
