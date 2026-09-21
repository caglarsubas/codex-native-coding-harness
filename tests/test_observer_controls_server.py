import contextlib
import http.client
import json
import threading
import unittest
from unittest.mock import patch

from orchestrator import observer_controls as controls
from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from orchestrator.workspaces import fingerprint
import test_observer_controls
import test_server


class ObserverControlsServerTest(unittest.TestCase):
    request = test_server.ServerTest.request
    login = test_server.ServerTest.login

    def setUp(self):
        self.fx=test_observer_controls.ObserverControlsTest(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.ledger,self.registry=self.fx.ledger,self.fx.registry
        other=Ledger(self.registry.root.parent / "observer-empty-fixture")
        other.initialize({"schemaVersion":1,"brainId":"empty-fixture","repositories":[]})
        self.registry.register("other","Other product",other.root)
        self.server=Dashboard(self.ledger,0,self.registry.root / "missing.env",registry=self.registry,
                              notification_cli="/nonexistent-fixture-notifier")
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start(); self.addCleanup(self.stop)

    def stop(self): self.server.shutdown(); self.server.server_close(); self.thread.join()
    def auth(self,wid="a",session=None):
        auth=session or self.login(); status,_,raw=self.request(f"/api/workspaces/{wid}/session",headers=auth)
        self.assertEqual(status,200); return auth | {"X-CSRF-Token":json.loads(raw)["csrf"]}
    def path(self,suffix="",wid="a"): return f"/api/workspaces/{wid}/native-observer-controls"+suffix
    def preview(self,auth,op="review"):
        status,_,raw=self.request(self.path("/preview"),self.fx.request(op),auth)
        self.assertEqual(status,200,raw); return json.loads(raw)

    def test_explicit_inspection_is_authenticated_and_not_polled(self):
        self.assertEqual(self.request(self.path())[0],401); auth=self.auth(); before=self.fx.logical()
        with patch.object(controls,"inspect",side_effect=AssertionError("No automatic inspection")):
            self.assertEqual(self.request("/api/workspaces/a/state",headers=auth)[0],200)
            self.assertEqual(self.request("/api/workspaces/a/assistant/context?view=runReadiness",headers=auth)[0],200)
        status,_,raw=self.request(self.path(),headers=auth); self.assertEqual(status,200,raw)
        self.assertTrue(json.loads(raw)["canReview"]); self.assertEqual(before,self.fx.logical())
        self.assertEqual(self.request(self.path()+"?connect=true",headers=auth)[0],400)
        self.assertEqual(self.request("/api/native-observer-controls",headers=auth)[0],400)

    def test_review_revoke_and_replay_do_not_notify_or_connect(self):
        auth=self.auth(); body={"proposal":self.preview(auth),"confirmed":True}; before=self.ledger.snapshot()
        with patch.object(self.server.runtime_for("a").notifier,"notify",side_effect=AssertionError("No notification")), patch.object(controls.evidence,"ReadProxy",side_effect=AssertionError("No native connection")):
            self.assertEqual(self.request(self.path("/confirm"),body,auth)[0],200)
            revoke=self.preview(auth,"revoke")
            self.assertEqual(self.request(self.path("/confirm"),{"proposal":revoke,"confirmed":True},auth)[0],200)
            status,_,raw=self.request(self.path("/confirm"),body,auth); self.assertEqual(status,200); self.assertTrue(json.loads(raw)["replayed"])
        self.assertTrue(self.fx.state()["endpoint"]["revoked"])
        for key in ("workers","commands","queue"): self.assertEqual(before[key],self.ledger.snapshot()[key])

    def test_session_workspace_origin_csrf_and_confirmation_are_bound(self):
        auth=self.auth(); body={"proposal":self.preview(auth),"confirmed":True}
        for headers in ({},auth|{"X-CSRF-Token":"wrong"},auth|{"Origin":"https://evil.invalid"},self.auth("other",auth)):
            self.assertEqual(self.request(self.path("/confirm"),body,headers)[0],403)
        self.assertEqual(self.request(self.path("/confirm"),body,self.auth())[0],409)
        self.assertEqual(self.request(self.path("/confirm","other"),body,self.auth("other",auth))[0],409)
        self.assertEqual(self.request(self.path("/confirm"),body|{"confirmed":1},auth)[0],409)

    def test_no_collect_discovery_server_start_or_direct_owner_routes(self):
        auth=self.auth(); before=self.fx.logical()
        for suffix in ("","/review","/revoke","/collect","/discover","/start","/connect","/play"):
            self.assertEqual(self.request(self.path(suffix),{},auth)[0],404)
        self.assertEqual(self.request(self.path("/preview")+"?override=true",self.fx.request(),auth)[0],400)
        self.assertEqual(before,self.fx.logical())

    def test_strict_json_bounds_busy_and_sanitized_io_errors(self):
        auth=self.auth()
        for raw,expected in (('{"confirmed":false,"confirmed":true}',409),('{"value":NaN}',409),('x'*32769,413)):
            conn=http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=3)
            conn.request("POST",self.path("/confirm"),raw,{"Content-Type":"application/json","Origin":self.server.origin,**auth})
            res=conn.getresponse(); self.assertEqual(res.status,expected); res.read(); conn.close()
        with self.server.runtime_for("a").observer_lock:
            self.assertEqual(self.request(self.path(),headers=auth)[0],409)
            self.assertEqual(self.request(self.path("/preview"),self.fx.request(),auth)[0],409)
        status,_,raw=self.request(self.path("/preview"),self.fx.request(executable=str(self.fx.root/"PRIVATE-MISSING")),auth)
        self.assertEqual(status,409); self.assertNotIn(b"PRIVATE-MISSING",raw)

    def test_empty_workspace_has_no_foreign_endpoint_or_allocation(self):
        auth=self.auth(); self.request(self.path("/confirm"),{"proposal":self.preview(auth),"confirmed":True},auth)
        other=self.registry.ledger("other")
        with contextlib.closing(other.connect()) as db: before=fingerprint(db)
        status,_,raw=self.request(self.path(wid="other"),headers=self.auth("other",auth))
        self.assertEqual(status,200); r=json.loads(raw); self.assertFalse(r["canReview"]); self.assertIsNone(r["endpoint"])
        self.assertEqual(r["allocations"],[]); self.assertNotIn(str(self.fx.binary).encode(),raw)
        with contextlib.closing(other.connect()) as db: self.assertEqual(before,fingerprint(db))

    def test_assistant_gets_only_cached_status_and_counts(self):
        auth=self.auth(); self.request(self.path(),headers=auth)
        status,_,raw=self.request("/api/workspaces/a/assistant/context?view=runReadiness",headers=auth)
        self.assertEqual(status,200,raw); result=json.loads(raw); fact=next(f["data"] for f in result["facts"] if f["id"]=="F39")
        self.assertTrue(fact["historical"]); self.assertFalse(fact["completeEvidence"])
        for private in (str(self.fx.root),self.fx.aid,"socket","executable","serverIdentityHash"):
            self.assertNotIn(private,json.dumps(fact))
        self.assertFalse(any("observer" in a["key"] for a in result["actions"]))
        self.assertEqual(self.request("/observer-controls.js")[0],200)


if __name__ == "__main__": unittest.main()
