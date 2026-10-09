"""Synthetic owner controls only; no native process or live state."""
import copy
import http.client
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator import standard, standard_budget as budget
from orchestrator.core import Refusal, canonical
from orchestrator.workspaces import fingerprint
import test_standard as fixtures


class BrainBudgetTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.StandardTest(methodName="runTest"); self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.ledger, self.registry = self.fixture.ledger, self.fixture.registry
        self.fixture.control(); self.fixture.call("receive")
        self.fixture.call("checkpoint", outcome="paused", summary="Budget checkpoint", brainObservedTokens=9500,
                          reasonCodes=["token_budget", "external_dependency"])
        self.ledger.release(self.fixture.token, "Fixture controller released")
        self.controls = budget.Controls()
        self.run_id = standard.read(self.ledger)["run"]["id"]
        with self.ledger.tx() as db:
            command = self.ledger.all(db, "commands")[0]
            command["notification"] = {"brainId": self.ledger.get(db, "meta", 1)["brainId"],
                "attemptedAt": time.time(), "hostRunId": self.run_id, "status": "accepted",
                "nativeDelivery": "owned_turn_start", "nativeTurnStatus": "completed", "nativeTurnId": "fixture-turn",
                "nativeThreadObservation": {"streamStatus": "closed"}}
            self.ledger.put(db, "commands", command["id"], command)
        self.request = {"runId": self.run_id, "contextHash": self.summary()["contextHash"], "brainAllowance": 30000}

    def summary(self):
        with standard.read_db(self.ledger.db) as db: return budget.summary_in(self.ledger, db)

    def preview(self, **changes):
        return self.controls.preview(self.registry, self.ledger, {**self.request, **changes}, "session")

    def confirm(self, p, **changes):
        return self.controls.confirm(self.registry, self.ledger, {**p, "confirmed": True, **changes}, "session")

    def mutate(self, edit):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); edit(meta)
            self.ledger.put(db, "meta", 1, meta)

    def test_preview_and_projection_do_not_mutate_collect_or_notify(self):
        with standard.read_db(self.ledger.db) as db: before = fingerprint(db)
        with patch("orchestrator.notification.BrainNotifier.notify") as notify:
            p = self.preview(); self.summary(); standard.read(self.ledger)
            notify.assert_not_called()
        self.assertEqual(p["preview"]["recordedBrainTokens"], 9500)
        self.assertEqual(p["preview"]["previousAllowance"], 10000)
        with standard.read_db(self.ledger.db) as db: self.assertEqual(fingerprint(db), before)

    def test_exact_reallocation_preserves_every_other_run_fact_and_replay(self):
        before = standard.read(self.ledger)["run"]; p = self.preview(); result = self.confirm(p)
        after = standard.read(self.ledger)["run"]
        self.assertEqual(result["kind"], budget.KIND)
        self.assertEqual(after["status"], "paused"); self.assertEqual(after["brainAllowance"], 30000)
        for field in before:
            if field not in ("revision", "updatedAt", "brainAllowance"):
                self.assertEqual(after[field], before[field], field)
        with patch("orchestrator.standard_budget.time.time", return_value=p["preview"]["expiresAt"] + 1):
            self.assertEqual(self.confirm(p), result)
        self.assertEqual(standard.read(self.ledger)["run"], after)
        from orchestrator.notification import NOTIFY_KINDS
        self.assertNotIn(result["kind"], NOTIFY_KINDS)

    def test_unknown_and_gapped_usage_never_becomes_zero_or_complete(self):
        self.mutate(lambda m: m["standardRun"].update(brainUsageCoverage="not_observed", usageHighWater=47000,
            usageReport={"tokens":{"total_tokens":47000}, "gaps":["missing-prefix"], "coverage":"gapped", "collectedAt":1, "through":1}))
        self.request["contextHash"] = self.summary()["contextHash"]
        p = self.preview(); self.assertIsNone(p["preview"]["recordedBrainTokens"])
        before = standard.read(self.ledger)["run"]; self.confirm(p); after = standard.read(self.ledger)["run"]
        self.assertEqual(after["usageReport"], before["usageReport"])
        self.assertEqual(after["usageHighWater"], 47000)
        self.assertEqual(after["brainUsageCoverage"], "not_observed")

    def test_closed_inputs_limits_signatures_sessions_and_expiry(self):
        for changes in ({"brainAllowance":True}, {"brainAllowance":10000}, {"brainAllowance":90000},
                        {"brainAllowance":30000.5}, {"durationHours":24}, {"tokenBudget":1000000}, {"runId":"foreign"}):
            with self.assertRaises((Refusal, ValueError)): self.preview(**changes)
        p = self.preview(); bad = copy.deepcopy(p); bad["preview"]["brainAllowance"] += 1
        with self.assertRaises(Refusal): self.confirm(bad)
        with self.assertRaises(Refusal): self.confirm(p, confirmed=False)
        with self.assertRaises(Refusal): self.controls.confirm(self.registry, self.ledger, {**p,"confirmed":True}, "other")
        with patch("orchestrator.standard_budget.time.time", return_value=p["preview"]["expiresAt"]+1):
            with self.assertRaises(Refusal): self.confirm(p)
        self.assertEqual(standard.read(self.ledger)["run"]["brainAllowance"], 10000)

    def test_new_usage_and_pause_changes_invalidate_the_exact_preview(self):
        p = self.preview(); self.mutate(lambda m: m["standardRun"].update(brainObservedTokens=9600))
        with self.assertRaisesRegex(Refusal, "changed"): self.confirm(p)
        self.request["contextHash"] = self.summary()["contextHash"]; p = self.preview()
        self.mutate(lambda m: m["standardRun"].update(status="stopping"))
        with self.assertRaises(Refusal): self.confirm(p)

    def test_unsafe_ownership_strict_expired_or_pending_states_refuse(self):
        original = self.ledger.snapshot()["meta"]
        for edit in (lambda m: m.update(controller={"token":"owned"}),
                     lambda m: m.update(brainControl={"desired":"stopped"}),
                     lambda m: m.update(brainHandoff={"status":"candidate"}),
                     lambda m: m.update(admissionBinding={"fixture":True}),
                     lambda m: m["standardRun"].update(expiresAt=time.time()-1),
                     lambda m: m["standardRun"].update(tasks=[{"status":"completed"}]),
                     lambda m: m["standardRun"].update(merges=[{"status":"uncertain"}]),
                     lambda m: m["standardRun"].update(recovery={"status":"processing"})):
            self.mutate(edit); self.assertFalse(self.summary()["available"])
            with self.assertRaises(Refusal): self.preview()
            with self.ledger.tx() as db: self.ledger.put(db,"meta",1,copy.deepcopy(original))
        with self.ledger.tx() as db:
            c = self.ledger.all(db,"commands")[0]; c["status"]="queued"; self.ledger.put(db,"commands",c["id"],c)
        with self.assertRaises(Refusal): self.preview()

    def test_unknown_delivery_and_native_approval_never_use_budget_as_reconciliation(self):
        with self.ledger.tx() as db:
            c = self.ledger.all(db,"commands")[0]
            original = copy.deepcopy(c)
            c["notification"]["nativeTurnStatus"]="connection_lost"; self.ledger.put(db,"commands",c["id"],c)
        with self.assertRaises(Refusal): self.preview()
        with self.ledger.tx() as db:
            c = original; c["notification"]["nativeApprovals"]=[{"status":"pending"}]; self.ledger.put(db,"commands",c["id"],c)
        with self.assertRaises(Refusal): self.preview()

    def test_chat_adapter_uses_same_signed_control_without_notification(self):
        from orchestrator.assistant_journey import JourneyProposals, catalog
        from orchestrator import missions
        runtime = SimpleNamespace(ledger=self.ledger, registry=self.registry, brain_budget_controls=self.controls)
        chat = JourneyProposals(runtime)
        s = self.ledger.snapshot(); s.update(workspace={"id":"alpha","name":"Alpha"}, standard=standard.read(self.ledger),mission=missions.read(self.ledger))
        p = chat.prepare(catalog(s)["brain_budget"], s, "session")
        self.assertIn("Brain allowance: 10000", p["document"]["preview"]["summary"][0])
        result, notify = chat.confirm(self.ledger, {"proposal":p,"confirmed":True}, "session")
        self.assertFalse(notify); self.assertEqual(result["result"]["kind"], budget.KIND)
        self.assertEqual(standard.read(self.ledger)["run"]["status"], "paused")

    def test_http_auth_csrf_workspace_and_no_notification(self):
        from orchestrator.server import Dashboard
        server = Dashboard(self.ledger, 0, registry=self.registry, runtime_root=self.fixture.root, inference_env=self.fixture.root/".env")
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        def send(path, body, auth=None):
            conn=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=5)
            conn.request("POST",path,json.dumps(body),{"Content-Type":"application/json","Origin":server.origin,**(auth or {})})
            res=conn.getresponse(); out=(res.status,dict(res.getheaders()),json.loads(res.read())); conn.close(); return out
        base="/api/workspaces/alpha/standard/budget"
        try:
            self.assertEqual(send(base+"/preview", self.request)[0],403)
            _,headers,_=send("/api/login",{"token":server.bootstrap})
            from orchestrator.server import scoped_csrf
            cookie=headers["Set-Cookie"].split(";")[0]; session=server.browser_auth.session(cookie.split("=",1)[1])
            auth={"Cookie":cookie,"X-CSRF-Token":scoped_csrf(session,"alpha")}
            self.assertEqual(send(base+"/preview",self.request,{**auth,"X-CSRF-Token":"wrong"})[0],403)
            self.assertEqual(send(base+"/preview?runId=foreign",self.request,auth)[0],409)
            status,_,p=send(base+"/preview",self.request,auth); self.assertEqual(status,200,p)
            with patch("orchestrator.notification.BrainNotifier.notify") as notify:
                status,_,result=send(base+"/confirm",{**p,"confirmed":True},auth)
                self.assertEqual(status,200,result); notify.assert_not_called()
                self.assertEqual(send(base+"/confirm",{**p,"confirmed":True},auth)[2],result)
        finally:
            server.shutdown(); server.server_close(); worker.join(5)
