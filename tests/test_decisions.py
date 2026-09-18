import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid

from orchestrator.core import Ledger, Refusal
from orchestrator.decisions import inbox, publish, resolve, workflow
from orchestrator.observations import capture


def fixture(ledger):
    ledger.initialize({"schemaVersion":1, "brainId":"brain-fixture", "repositories":[
        {"id":"fixture", "path":"/fixture", "projectId":None, "ref":"main", "mergePolicy":"manual", "policyProfile":"standard"}]})
    with ledger.tx() as db:
        a = capture(db, "design", b"Private design fixture", {"repository":"fixture", "name":"design.md", "orderAt":time.time(), "references":[]})
    return {"key":"DESIGN-001", "repository":"fixture", "title":"Choose a design direction",
            "question":"Which direction should the private design use?", "context":"No implementation is prepared.",
            "scope":"Private design only", "nextStep":"Record the selected direction in an artifact.",
            "options":[{"id":"bounded", "label":"Bounded option", "implications":"Keep existing constraints.", "requiresNote":False},
                       {"id":"details", "label":"Provide information", "implications":"Review the supplied input; no execution.", "requiresNote":True}],
            "recommendedOptionId":"bounded", "artifactIds":[a["id"]]}


def envelope(ledger, d, **overrides):
    payload={"decisionId":d["id"], "decisionHash":d["decisionHash"], "optionId":"bounded", "note":"", "confirmed":True, **overrides}
    return {"id":str(uuid.uuid4()), "kind":"decision_response", "expectedRevision":ledger.snapshot()["meta"]["revision"], "payload":payload}


class DecisionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ledger=Ledger(Path(self.tmp.name)/"state")
        self.spec=fixture(self.ledger)
        self.token=self.ledger.acquire("brain-fixture:turn")
        self.d=publish(self.ledger,self.token,self.spec)

    def tearDown(self):
        self.tmp.cleanup()

    def result(self, command, outcome="applied"):
        with self.ledger.tx() as db:
            a=capture(db,"outcome",b"Direction applied to private design only",{"repository":"fixture","name":"result.md","orderAt":time.time(),"references":[]})
        return {"commandId":command["id"],"outcome":outcome,"summary":"Applied only to the private design.","artifactIds":[a["id"]]}

    def test_complete_decision_cycle_preserves_dispatch_authority(self):
        before=self.ledger.snapshot()
        cmd=self.ledger.submit(envelope(self.ledger,self.d))
        self.assertEqual(cmd["status"],"queued")
        self.assertEqual(self.ledger.snapshot()["decisions"][0]["status"],"answered")
        actions=self.ledger.process(self.token)
        self.assertEqual(actions[0]["kind"],"decision_response")
        self.assertEqual(self.ledger.snapshot()["decisions"][0]["status"],"received")
        result=self.result(cmd)
        d=resolve(self.ledger,self.token,self.d["id"],result)
        self.assertEqual(d["status"],"applied")
        self.assertEqual(resolve(self.ledger,self.token,d["id"],result),d)
        self.assertEqual(publish(self.ledger,self.token,self.spec),d)
        after=Ledger(self.ledger.root).snapshot()
        for key in ("paused","concurrency","pilotPassed","heartbeat","runner"):
            self.assertEqual(after["meta"][key],before["meta"][key])
        for key in ("queue","workers"):
            self.assertEqual(after[key],before[key])
        self.assertEqual(after["commands"][0]["status"],"completed")
        self.assertNotIn(self.token,json.dumps(after))

    def test_replay_idempotency_and_conflicting_duplicate(self):
        request=envelope(self.ledger,self.d)
        a=self.ledger.submit(request)
        self.assertEqual(a,self.ledger.submit(request))
        conflict=copy.deepcopy(request);conflict["payload"]["note"]="Changed"
        with self.assertRaises(Refusal): self.ledger.submit(conflict)
        with self.assertRaises(Refusal): self.ledger.submit(envelope(self.ledger,self.d))

    def test_concurrent_answers_only_one_commits(self):
        requests=[envelope(self.ledger,self.d),envelope(self.ledger,self.d,optionId="details",note="input")]
        results=[]
        def submit(request):
            try: self.ledger.submit(request);results.append("ok")
            except Refusal: results.append("refused")
        threads=[threading.Thread(target=submit,args=(r,)) for r in requests]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertCountEqual(results,["ok","refused"])

    def test_stale_revision_and_hash_require_review(self):
        old=envelope(self.ledger,self.d)
        self.ledger.heartbeat("fixture-heartbeat","PAUSED")
        with self.assertRaises(Refusal):self.ledger.submit(old)
        with self.assertRaises(Refusal):self.ledger.submit(envelope(self.ledger,self.d,decisionHash="a"*64))

    def test_bad_responses_are_atomic(self):
        for change in ({"confirmed":False},{"confirmed":1},{"optionId":"unknown"},{"optionId":"details"},{"note":"x"*4001},{"note":{}},{"extra":"execute"},{"decisionId":[]}):
            with self.subTest(change=str(change)[:60]),self.assertRaises(Refusal):self.ledger.submit(envelope(self.ledger,self.d,**change))
        state=self.ledger.snapshot()
        self.assertEqual(state["decisions"][0]["status"],"open")
        self.assertEqual(state["commands"],[])

    def test_superseded_answer_never_reaches_brain(self):
        self.ledger.submit(envelope(self.ledger,self.d))
        revised=copy.deepcopy(self.spec);revised["context"]="New constraints"
        new=publish(self.ledger,self.token,revised)
        self.assertEqual(new["version"],2)
        self.assertNotEqual(new["decisionHash"],self.d["decisionHash"])
        self.assertEqual(self.ledger.process(self.token),[])
        with self.assertRaises(Refusal):self.ledger.submit(envelope(self.ledger,self.d))
        self.assertEqual(self.ledger.document(self.d["decisionHash"])["spec"],self.spec)
        self.assertEqual(self.ledger.snapshot()["commands"][0]["status"],"rejected")

    def test_inflight_is_not_replayed_or_revised_after_restart(self):
        cmd=self.ledger.submit(envelope(self.ledger,self.d))
        self.ledger.process(self.token)
        restarted=Ledger(self.ledger.root)
        self.assertEqual(restarted.process(self.token),[])
        revised=copy.deepcopy(self.spec);revised["context"]="New context"
        with self.assertRaises(Refusal):publish(restarted,self.token,revised)
        with self.assertRaises(Refusal):restarted.acknowledge(self.token,cmd["id"],True,"not enough evidence")
        self.assertEqual(restarted.snapshot()["decisions"][0]["status"],"received")

    def test_resolution_needs_exact_response_and_retained_artifact(self):
        cmd=self.ledger.submit(envelope(self.ledger,self.d));result=self.result(cmd)
        with self.assertRaises(Refusal):resolve(self.ledger,self.token,self.d["id"],result)
        self.ledger.process(self.token)
        for change in ({"commandId":"other"},{"outcome":"approved"},{"artifactIds":[]},{"artifactIds":["b"*64]}):
            with self.assertRaises(Refusal):resolve(self.ledger,self.token,self.d["id"],{**result,**change})
        d=resolve(self.ledger,self.token,self.d["id"],{**result,"outcome":"blocked"})
        self.assertEqual(d["status"],"blocked")
        with self.assertRaises(Refusal):resolve(self.ledger,self.token,self.d["id"],result)

    def test_only_designated_brain_can_publish_receive_resolve(self):
        cmd=self.ledger.submit(envelope(self.ledger,self.d))
        self.ledger.release(self.token,"Fixture checkpoint")
        other=self.ledger.acquire("other-brain:turn")
        with self.assertRaises(Refusal):publish(self.ledger,other,self.spec)
        with self.assertRaises(Refusal):self.ledger.process(other)
        with self.assertRaises(Refusal):resolve(self.ledger,other,self.d["id"],self.result(cmd))
        self.assertEqual(self.ledger.snapshot()["commands"][0]["status"],"queued")

    def test_bad_specs_and_unretained_references_rejected(self):
        for change in ({"artifactIds":[]},{"artifactIds":["f"*64]},{"repository":"missing"},{"recommendedOptionId":"missing"},{"options":[]},{"key":"../escape"},{"title":"x"*201},{"execute":True}):
            with self.subTest(change=change),self.assertRaises(Refusal):publish(self.ledger,self.token,{**self.spec,**change})

    def test_listener_is_independent_and_honest_about_native_activation(self):
        def listening(enabled):
            self.ledger.submit({"id":str(uuid.uuid4()),"kind":"listening","expectedRevision":self.ledger.snapshot()["meta"]["revision"],"payload":{"enabled":enabled}})
        self.assertEqual(self.ledger.snapshot()["workflow"]["status"],"off")
        listening(True)
        self.assertEqual(self.ledger.snapshot()["workflow"]["status"],"needs_activation")
        self.ledger.heartbeat("fixture-heartbeat","ACTIVE")
        self.assertEqual(self.ledger.snapshot()["workflow"]["status"],"unconfirmed")
        self.ledger.process(self.token)
        state=self.ledger.snapshot()
        self.assertEqual(state["workflow"]["status"],"listening")
        self.assertTrue(state["workflow"]["shouldKeepHeartbeat"])
        self.assertTrue(state["meta"]["paused"])
        state["serverTime"]+=36*60
        self.assertEqual(workflow(state)["status"],"unconfirmed")
        listening(False)
        state=self.ledger.snapshot()
        self.assertEqual(state["workflow"]["status"],"off")
        self.assertEqual(state["meta"]["heartbeat"]["status"],"ACTIVE")
        self.assertFalse(state["workflow"]["shouldKeepHeartbeat"])

    def test_legacy_ledger_defaults_and_additive_migration(self):
        with self.ledger.tx() as db:db.execute("DROP TABLE decisions")
        upgraded=Ledger(self.ledger.root).snapshot()
        self.assertEqual(upgraded["decisions"],[])
        self.assertFalse(upgraded["workflow"]["listenerEnabled"])
        self.assertTrue(upgraded["meta"]["paused"])

    def test_cross_repository_artifacts_are_refused(self):
        with self.ledger.tx() as db:
            other=capture(db,"other",b"Other repository",{"repository":"another","name":"other.md","orderAt":time.time(),"references":[]})
        with self.assertRaises(Refusal):publish(self.ledger,self.token,{**self.spec,"artifactIds":[other["id"]]})

    def test_compact_inbox_and_missing_native_observation_are_explicit(self):
        self.ledger.heartbeat("fixture-heartbeat","ACTIVE")
        self.ledger.process(self.token)
        state=self.ledger.snapshot()
        small=inbox(state)
        self.assertNotIn("observations",small)
        self.assertNotIn("events",small)
        self.assertEqual(len(small["decisions"]),1)
        state["meta"]["decisionListener"]={"enabled":True}
        state["meta"]["heartbeat"].pop("observedAt")
        self.assertEqual(workflow(state)["status"],"unconfirmed")

    def test_other_controller_does_not_claim_a_brain_checkin(self):
        self.ledger.release(self.token,"Fixture checkpoint")
        other=self.ledger.acquire("non-brain")
        self.ledger.process(other)
        self.assertIsNone(self.ledger.snapshot()["workflow"]["lastCheckedAt"])
