"""Temporary observer UI only: fake endpoint, synthetic report, no native calls."""
import json
from unittest.mock import patch
from orchestrator.core import Ledger
from orchestrator import native_evidence
from orchestrator.server import Dashboard
from test_observer_controls import ObserverControlsTest
from test_native_evidence import FakeProxy


if __name__ == "__main__":
    fixture=ObserverControlsTest(); fixture.setUp()
    fixture.confirm(fixture.preview())
    api=native_evidence.NativeEvidence(fixture.fx.bridge)
    plan=api.plan(fixture.fx.token,fixture.aid)
    with patch.object(native_evidence,"ReadProxy",return_value=FakeProxy(fixture.endpoint)):
        api.collect(fixture.fx.token,fixture.aid,{"id":"fixture-report",**{k:plan[k] for k in ("expectedRevision","expectedHash","contextHash","endpointHash")}})
    other=Ledger(fixture.registry.root.parent / "observer-empty-workspace")
    other.initialize({"schemaVersion":1,"brainId":"empty-fixture","repositories":[]})
    fixture.registry.register("empty","Second product · no allocation",other.root)
    server=Dashboard(fixture.ledger,0,fixture.root / "missing.env",registry=fixture.registry,
                     notification_cli="/nonexistent-fixture-notifier")
    server.bootstrap="observer-owner-fixture-only"
    print(server.origin+"/#token="+server.bootstrap,flush=True)
    print(json.dumps({k:fixture.endpoint[k] for k in ("executable","socket","serverIdentityHash")}),flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close(); fixture.doCleanups()
