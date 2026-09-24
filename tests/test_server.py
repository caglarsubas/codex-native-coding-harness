import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid
import subprocess
import sys

from orchestrator.core import Ledger
from orchestrator.server import Dashboard
from orchestrator.observations import capture
from unittest.mock import patch


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "state")
        self.server = Dashboard(self.ledger, 0, Path(self.tmp.name) / ".env", runtime_root=self.tmp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        merged = {"Content-Type": "application/json", "Origin": self.server.origin, **(headers or {})}
        conn.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None, merged)
        res = conn.getresponse(); result = res.status, dict(res.getheaders()), res.read(); conn.close(); return result

    def login(self):
        status, headers, body = self.request("/api/login", {"token": self.server.bootstrap})
        self.assertEqual(status, 200)
        return {"Cookie": headers["Set-Cookie"].split(";")[0], "X-CSRF-Token": json.loads(body)["csrf"]}

    def test_private_reads_need_auth_and_never_expose_controller_token(self):
        self.assertEqual(self.request("/api/state")[0], 401)
        auth = self.login(); token = self.ledger.acquire("fixture")
        status, headers, body = self.request("/api/state", headers=auth)
        self.assertEqual(status, 200); self.assertNotIn(token.encode(), body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_cross_origin_csrf_and_host_refused(self):
        auth = self.login()
        command = {"id": str(uuid.uuid4()), "kind": "pause", "expectedRevision": 0, "payload": {}}
        for change in ({"Origin": "https://malicious.example"}, {"X-CSRF-Token": "wrong"}, {"Host": "malicious.example"}):
            self.assertEqual(self.request("/api/commands", command, {**auth, **change})[0], 403)
        self.assertEqual(self.request("/api/commands", command, auth)[0], 200)

    def test_static_has_no_private_data_and_traversal_not_served(self):
        status, _, body = self.request("/"); self.assertEqual(status, 200)
        self.assertNotIn(self.server.bootstrap.encode(), body)
        self.assertNotEqual(self.request("/../.state/ledger.sqlite3", headers=self.login())[0], 200)

    def test_assistant_auth_csrf_strict_input_and_read_only_context(self):
        from test_assistant import response, CONFIG
        from test_decisions import fixture
        from orchestrator.decisions import publish
        spec=fixture(self.ledger)
        token=self.ledger.acquire("brain-fixture:assistant-http")
        publish(self.ledger,token,spec)
        body={"view":"overview","messages":[{"role":"user","content":"What needs review?"}]}
        self.assertEqual(self.request("/api/assistant",body)[0],403)
        self.assertEqual(self.request("/api/assistant/context")[0],401)
        auth=self.login()
        for change in ({"Origin":"https://other.example"},{"X-CSRF-Token":"wrong"},{"Host":"other.example"}):
            self.assertEqual(self.request("/api/assistant",body,{**auth,**change})[0],403)
        before=self.ledger.snapshot()
        with patch("orchestrator.assistant.settings",return_value=CONFIG), patch("orchestrator.assistant.Client.request",return_value=response()) as call:
            for path in ("/api/assistant/context?view=decisions","/api/state"):
                self.assertEqual(self.request(path,headers=auth)[0],200)
            call.assert_not_called()
            self.assertEqual(self.request("/api/assistant",{**body,"model":"external"},auth)[0],409)
            self.assertEqual(self.request("/api/assistant/context?view=unknown",headers=auth)[0],400)
            self.assertEqual(self.request("/api/assistant/context?view=operations",headers=auth)[0],200)
            self.assertEqual(self.request("/api/assistant/context?view=usage&view=queue",headers=auth)[0],400)
            status,_,raw=self.request("/api/assistant",body,auth)
            self.assertEqual(status,200)
            self.assertNotIn(CONFIG.api_key.encode(),raw)
            self.assertTrue(json.loads(raw)["advisoryOnly"])
            self.assertEqual(call.call_count,1)
        after=self.ledger.snapshot()
        before.pop("serverTime"); after.pop("serverTime")
        self.assertEqual(before,after)
        for path in ("/assistant.js","/panes.js","/routing.js","/panes.css","/session-map.js","/session-map.css","/journey.js","/journey.css","/summaries.js"):
            self.assertEqual(self.request(path)[0],200)

    def test_unknown_command_and_bad_revision_rejected(self):
        auth = self.login()
        for kind, rev in (("shell",0), ("continuation-publish",0), ("pause",999)):
            status, _, _ = self.request("/api/commands", {"id":str(uuid.uuid4()),"kind":kind,"expectedRevision":rev,"payload":{}}, auth)
            self.assertEqual(status, 409)

    def test_assistant_confirmation_auth_exact_intent_and_single_notification(self):
        from test_decisions import fixture
        from orchestrator.assistant import context
        from orchestrator.assistant_actions import catalog
        fixture(self.ledger)
        auth = self.login()
        state = self.ledger.snapshot()
        _, links = context(state, "overview")
        proposal = self.server.assistant_proposals.prepare(catalog(state, links)["brain_stop"], state, auth["X-CSRF-Token"])
        body = {"proposal": proposal, "confirmed": True}
        self.assertEqual(self.request("/api/assistant/confirm", body)[0], 403)
        for change in ({"Origin":"https://other.example"}, {"X-CSRF-Token":"wrong"}, {"Host":"other.example"}):
            self.assertEqual(self.request("/api/assistant/confirm", body, {**auth, **change})[0], 403)
        self.assertEqual(self.request("/api/assistant/confirm", {**body,"confirmed":False}, auth)[0], 409)
        self.assertEqual(self.request("/api/assistant/confirm", body, self.login())[0], 409)
        self.assertEqual(self.ledger.snapshot()["commands"], [])
        with patch.object(self.server.notifier, "notify", wraps=self.server.notifier.notify) as notify:
            status, _, raw = self.request("/api/assistant/confirm", body, auth)
            self.assertEqual(status, 200)
            command = json.loads(raw)
            self.assertEqual(command["kind"], "brain_stop")
            self.assertEqual(command["actor"], "assistant_owner_confirmed")
            self.assertEqual(command["notification"]["status"], "unavailable")
            status, _, raw = self.request("/api/assistant/confirm", body, auth)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)["id"], command["id"])
            self.assertEqual(notify.call_count, 1)

    def test_paused_dashboard_resume_is_queued_not_executed(self):
        status, _, raw = self.request("/api/commands", {"id":str(uuid.uuid4()),"kind":"resume","expectedRevision":0,"payload":{}}, self.login())
        self.assertEqual(status,200); self.assertEqual(json.loads(raw)["status"],"queued")
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])

    def test_decision_http_receipt_and_brain_resolution(self):
        from test_decisions import fixture, envelope
        from orchestrator.decisions import publish, resolve
        spec=fixture(self.ledger)
        token=self.ledger.acquire("brain-fixture:http-test")
        d=publish(self.ledger,token,spec)
        request=envelope(self.ledger,d)
        self.assertEqual(self.request("/api/commands",request)[0],403)
        auth=self.login()
        status,_,raw=self.request("/api/commands",request,auth)
        self.assertEqual(status,200)
        cmd=json.loads(raw);self.assertEqual(cmd["status"],"queued")
        self.assertEqual(self.request("/api/commands",request,auth)[0],200)
        self.ledger.process(token)
        resolve(self.ledger,token,d["id"],{"commandId":cmd["id"],"outcome":"blocked","summary":"Fixture needs additional input; no execution.","artifactIds":spec["artifactIds"]})
        status,_,raw=self.request("/api/state",headers=auth)
        state=json.loads(raw)
        self.assertEqual(state["decisions"][0]["status"],"blocked")
        self.assertTrue(state["meta"]["paused"])
        self.assertEqual(state["workers"],[])
        self.assertNotIn(token.encode(),raw)
        self.assertEqual(self.request("/api/decision-publish",spec,auth)[0],404)
        self.assertEqual(self.request("/api/continuation-publish",spec,auth)[0],404)
        self.assertEqual(state["continuations"][0]["status"],"needs_proposal")
        for path in ("/decisions.js","/decisions.css"):
            self.assertEqual(self.request(path)[0],200)

    def test_brain_controls_are_authenticated_not_native_completion(self):
        from test_decisions import fixture
        from test_notification import BRAIN, MESSAGE
        from orchestrator.notification import BrainNotifier
        fixture(self.ledger,BRAIN)
        self.server.notifier=BrainNotifier(self.ledger,sys.executable)
        auth=self.login()
        ack=subprocess.CompletedProcess([],0,f"Queued message {MESSAGE} for thread {BRAIN}.\n","")
        with patch("orchestrator.notification.subprocess.run",return_value=ack) as native:
            for kind in ("resume","reconcile","brain_stop","brain_resume"):
                request={"id":str(uuid.uuid4()),"kind":kind,"expectedRevision":self.ledger.snapshot()["meta"]["revision"],"payload":{}}
                self.assertEqual(self.request("/api/commands",request)[0],403)
                self.assertEqual(self.request("/api/commands",{**request,"payload":{"threadId":"other"}},auth)[0],409)
                status,_,raw=self.request("/api/commands",request,auth)
                self.assertEqual(status,200)
                result=json.loads(raw)
                self.assertEqual(result["status"],"queued")
                self.assertEqual(result["notification"]["status"],"accepted")
                self.assertEqual(self.request("/api/commands",request,auth)[0],200)
            self.assertEqual(native.call_count,4)
            self.assertEqual(self.ledger.snapshot()["meta"]["brainControl"]["phase"],"resume_requested")
            self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
            self.assertEqual(self.request("/api/brain-park",{},auth)[0],404)
            self.request("/api/state",headers=auth)
            self.assertEqual(native.call_count,4)

    def test_artifact_preview_is_authenticated_json_and_download_is_inert(self):
        with self.ledger.tx() as db:
            document = capture(db,"fixture",b"<script>alert('x')</script>",{"name":"page.html","references":[],"orderAt":1,"repository":"fixture"})
        path = "/api/artifacts/" + document["id"]
        self.assertEqual(self.request(path)[0],401)
        auth = self.login()
        status, headers, raw = self.request(path,headers=auth)
        self.assertEqual(status,200)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertEqual(json.loads(raw)["text"],"<script>alert('x')</script>")
        status, headers, raw = self.request(path + "/download",headers=auth)
        self.assertEqual(status,200)
        self.assertEqual(headers["Content-Type"],"application/octet-stream")
        self.assertTrue(headers["Content-Disposition"].startswith("attachment;"))
        self.assertNotEqual(self.request("/api/artifacts/../../ledger.sqlite3",headers=auth)[0],200)

    def test_free_text_http_response_without_selecting_option(self):
        from test_decisions import fixture, envelope
        from orchestrator.decisions import publish
        spec=fixture(self.ledger)
        token=self.ledger.acquire("brain-fixture:free-text-test")
        d=publish(self.ledger,token,spec)
        auth=self.login()
        blank=envelope(self.ledger,d,optionId=None,note=" \n ")
        self.assertEqual(self.request("/api/commands",blank,auth)[0],409)
        note="Neither option: <script>alert('fixture')</script>\nExact free-text input."
        request=envelope(self.ledger,d,optionId=None,note=note)
        self.assertEqual(self.request("/api/commands",request)[0],403)
        self.assertEqual(self.request("/api/commands",request,{**auth,"X-CSRF-Token":"wrong"})[0],403)
        status,_,raw=self.request("/api/commands",request,auth)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)["payload"]["note"],note)
        self.assertEqual(self.request("/api/commands",request,auth)[0],200)
        self.ledger.process(token)
        status,_,raw=self.request("/api/state",headers=auth)
        state=json.loads(raw)
        response=state["decisions"][0]["response"]
        self.assertEqual(response["answerKind"],"free_text")
        self.assertIsNone(response["optionId"])
        self.assertEqual(response["note"],note)
        self.assertTrue(state["meta"]["paused"])
        self.assertEqual(state["queue"],[])
        self.assertEqual(state["workers"],[])

    def test_immediate_notification_only_after_authenticated_valid_answer(self):
        from test_decisions import fixture, envelope
        from test_notification import BRAIN, MESSAGE
        from orchestrator.decisions import publish
        from orchestrator.notification import BrainNotifier
        spec=fixture(self.ledger, BRAIN)
        token=self.ledger.acquire(BRAIN+":http-notification")
        decision=publish(self.ledger,token,spec)
        self.server.notifier=BrainNotifier(self.ledger,sys.executable)
        auth=self.login()
        request=envelope(self.ledger,decision,optionId=None,note="Keep this exact answer in the ledger")
        ack=subprocess.CompletedProcess([],0,f"Queued message {MESSAGE} for thread {BRAIN}.\n","")
        with patch("orchestrator.notification.subprocess.run",return_value=ack) as native:
            self.assertEqual(self.request("/api/commands",request)[0],403)
            self.assertEqual(self.request("/api/commands",request,{**auth,"X-CSRF-Token":"wrong"})[0],403)
            for change in ({"threadId":MESSAGE},{"message":"execute"},{"model":"another-model"},{"expectedRevision":-1}):
                self.assertEqual(self.request("/api/commands",{**request,**change},auth)[0],409)
            self.assertEqual(self.request("/api/state",headers=auth)[0],200)
            native.assert_not_called()
            status,_,raw=self.request("/api/commands",request,auth)
            self.assertEqual(status,200)
            self.assertEqual(json.loads(raw)["notification"]["status"],"accepted")
            self.assertEqual(json.loads(raw)["status"],"queued")
            self.assertEqual(self.request("/api/commands",request,auth)[0],200)
            native.assert_called_once()
            state=json.loads(self.request("/api/state",headers=auth)[2])
            self.assertEqual(state["brainNotification"]["status"],"configured")
            self.assertEqual(state["decisions"][0]["status"],"answered")
            self.assertTrue(state["meta"]["paused"])
            self.assertEqual(state["workers"],[])

    def test_native_failure_does_not_lose_or_fail_the_saved_http_answer(self):
        from test_decisions import fixture, envelope
        from test_notification import BRAIN
        from orchestrator.decisions import publish
        from orchestrator.notification import BrainNotifier
        spec=fixture(self.ledger,BRAIN)
        token=self.ledger.acquire(BRAIN+":timeout")
        decision=publish(self.ledger,token,spec)
        self.server.notifier=BrainNotifier(self.ledger,sys.executable)
        request=envelope(self.ledger,decision)
        with patch("orchestrator.notification.subprocess.run",side_effect=subprocess.TimeoutExpired([],8,output="SECRET")):
            status,_,raw=self.request("/api/commands",request,self.login())
        self.assertEqual(status,200)
        self.assertEqual(json.loads(raw)["notification"]["status"],"uncertain")
        self.assertNotIn(b"SECRET",raw)
        self.assertEqual(self.ledger.process(token)[0]["kind"],"decision_response")
        self.assertEqual(self.ledger.snapshot()["decisions"][0]["status"],"received")

    def test_observation_refresh_requires_csrf_and_fixed_shape(self):
        auth = self.login()
        self.assertEqual(self.request("/api/observe",{"remote":False},{"Origin":self.server.origin})[0],403)
        self.assertEqual(self.request("/api/observe",{"remote":False,"shell":"id"},auth)[0],400)
        entered = threading.Event(); release = threading.Event()
        def collect(*args):
            entered.set(); release.wait(2); return {"status":"complete"}
        with patch("orchestrator.observations.refresh_observations",side_effect=collect):
            self.assertEqual(self.request("/api/observe",{"remote":False},auth)[0],202)
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.request("/api/observe",{"remote":False},auth)[0],409)
            release.set()
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertEqual(self.ledger.snapshot()["workers"],[])

    def test_inference_requires_csrf_fixed_shape_and_serializes(self):
        auth = self.login()
        self.assertEqual(self.request("/api/executive-summary", {"force": False})[0], 403)
        for body in ({"prompt": "arbitrary"}, {"force": 1}, {"force": False, "model": "external"}, {"force": False, "url": "https://elsewhere"}):
            self.assertEqual(self.request("/api/executive-summary", body, auth)[0], 400)
        entered = threading.Event(); release = threading.Event()
        def generate(*args):
            entered.set(); release.wait(2); return {"status": "generated"}
        with patch("orchestrator.inference.generate", side_effect=generate):
            self.assertEqual(self.request("/api/executive-summary", {"force": False}, auth)[0], 202)
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.request("/api/executive-summary", {"force": False}, auth)[0], 409)
            release.set()
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertEqual(self.ledger.snapshot()["commands"], [])

    def test_state_is_network_free_and_has_no_inference_credentials(self):
        env = self.server.inference_env
        env.write_text("CODEX_LLM_BASE_URL=https://private.example/v1\nCODEX_LLM_API_KEY=private-fixture-key\n")
        env.chmod(0o600)
        with patch("orchestrator.inference.Client.request") as network:
            status, _, raw = self.request("/api/state", headers=self.login())
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(raw)["inference"]["configured"])
            self.assertNotIn(b"private-fixture-key", raw)
            self.assertNotIn(b"private.example", raw)
            network.assert_not_called()

    def test_readiness_operations_are_authenticated_fixed_and_serialized(self):
        auth = self.login()
        self.assertEqual(self.request("/api/readiness", {"operation": "inspect"})[0], 403)
        for body in ({"operation": "dispatch"}, {"operation": "inspect", "path": "/private"}, {"operation": "native-observe"}, {"operation": []}):
            self.assertEqual(self.request("/api/readiness", body, auth)[0], 400)
        entered = threading.Event(); release = threading.Event()
        def inspect(*args):
            entered.set(); release.wait(2); return {"status": "complete"}
        before = self.ledger.snapshot()["meta"]
        with patch("orchestrator.readiness.collect", side_effect=inspect):
            self.assertEqual(self.request("/api/readiness", {"operation": "inspect"}, auth)[0], 202)
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.request("/api/readiness", {"operation": "rehearse"}, auth)[0], 409)
            release.set()
        self.assertEqual(before, self.ledger.snapshot()["meta"])

    def test_state_readiness_does_not_inspect_repositories_or_run_rehearsal(self):
        with patch("orchestrator.readiness.collect") as collect, patch("orchestrator.rehearsal.run") as run:
            status, _, raw = self.request("/api/state", headers=self.login())
            self.assertEqual(status, 200)
            self.assertFalse(json.loads(raw)["readiness"]["launchAuthorized"])
            collect.assert_not_called(); run.assert_not_called()

    def test_runtime_inspection_requires_auth_fixed_shape_and_single_operation(self):
        auth = self.login()
        self.assertEqual(self.request("/api/provenance", {"remote": False})[0], 403)
        for body in ({"remote": 1}, {"remote": False, "path": "/private"}, {"operation": "restart"}):
            self.assertEqual(self.request("/api/provenance", body, auth)[0], 400)
        entered = threading.Event(); release = threading.Event()
        def inspect(remote):
            self.assertFalse(remote); entered.set(); release.wait(2)
        before = self.ledger.snapshot()["meta"]
        with patch.object(self.server.provenance, "refresh", side_effect=inspect):
            self.assertEqual(self.request("/api/provenance", {"remote": False}, auth)[0], 202)
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.request("/api/provenance", {"remote": True}, auth)[0], 409)
            release.set()
        self.assertEqual(before, self.ledger.snapshot()["meta"])

    def test_runtime_state_polling_never_scans_or_calls_remote(self):
        with patch("orchestrator.provenance.inspect") as local, patch("orchestrator.provenance.remote_revision") as remote:
            status, _, raw = self.request("/api/state", headers=self.login())
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)["provenance"]["status"], "unknown")
            local.assert_not_called(); remote.assert_not_called()

    def test_brain_activity_is_authenticated_read_only_and_static_is_public(self):
        with patch.object(self.server.brain_activity, "snapshot", return_value={"status":"unknown", "readOnly":True}) as reader:
            self.assertEqual(self.request("/api/state")[0], 401)
            reader.assert_not_called()
            before = self.ledger.snapshot()["meta"]
            status, _, raw = self.request("/api/state", headers=self.login())
            self.assertEqual(status, 200)
            self.assertTrue(json.loads(raw)["brainActivity"]["readOnly"])
            self.assertEqual(self.ledger.snapshot()["meta"], before)
        status, _, raw = self.request("/activity.js")
        self.assertEqual(status, 200)
        self.assertNotIn(self.server.bootstrap.encode(), raw)


if __name__ == "__main__": unittest.main()
