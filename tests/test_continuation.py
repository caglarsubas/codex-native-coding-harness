import copy
from pathlib import Path
import tempfile
import time
import unittest
import uuid

from orchestrator.core import Ledger, Refusal
from orchestrator.continuation import publish as follow_up
from orchestrator.decisions import inbox, publish, resolve, workflow
from orchestrator.observations import capture
from test_decisions import fixture, envelope
from test_core import seed


class ContinuationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.ledger=Ledger(Path(self.tmp.name)/"state")
        self.spec=fixture(self.ledger)
        self.token=self.ledger.acquire("brain-fixture:turn")
        self.d=publish(self.ledger,self.token,self.spec)
        c=self.ledger.submit(envelope(self.ledger,self.d,optionId=None,note="No environment; please propose one."))
        self.ledger.process(self.token)
        self.d=resolve(self.ledger,self.token,self.d["id"],{"commandId":c["id"],"outcome":"blocked","summary":"Capacity not selected; no provisioning authorized.","artifactIds":[self.artifact("outcome")]})
        self.proposal={"expectedVersion":0,"summary":"Choose owned capacity, then separately scope installation.",
                       "artifactIds":[self.artifact("proposal")],"decisionIds":[],"queueIds":[],
                       "externalBlocker":{"reason":"Owner must identify capacity.","resumeWhen":"Owner supplies a non-secret asset label."}}

    def tearDown(self):
        self.tmp.cleanup()

    def artifact(self, name, repo="fixture"):
        with self.ledger.tx() as db:
            return capture(db,name,name.encode(),{"repository":repo,"name":name+".md","orderAt":time.time(),"references":[]})["id"]

    def decision(self):
        return publish(self.ledger,self.token,{**self.spec,"key":"CAPACITY-002","question":"Which owned capacity may be scoped?","artifactIds":self.proposal["artifactIds"]})

    def command(self, kind, payload):
        return self.ledger.submit({"id":str(uuid.uuid4()),"kind":kind,"payload":payload,"expectedRevision":self.ledger.snapshot()["meta"]["revision"]})

    def test_legacy_blocked_outcome_is_readonly_actionable_projection(self):
        before=self.ledger.snapshot()
        for _ in range(3):
            state=Ledger(self.ledger.root).snapshot()
            c=state["continuations"][0]
            self.assertEqual(c["status"],"needs_proposal")
            self.assertEqual(c["response"],self.d["response"])
            self.assertEqual(c["outcome"],self.d["resolution"])
            self.assertEqual(state["meta"]["revision"],before["meta"]["revision"])
            self.assertTrue(state["workflow"]["shouldKeepHeartbeat"])
            self.assertEqual(inbox(state)["continuations"],state["continuations"])

    def test_retained_external_wait_is_not_periodic_model_work(self):
        before=self.ledger.snapshot()
        r=follow_up(self.ledger,self.token,self.d["id"],self.proposal)
        self.assertEqual(follow_up(self.ledger,self.token,self.d["id"],self.proposal),r)
        state=Ledger(self.ledger.root).snapshot()
        self.assertEqual(state["continuations"][0]["status"],"waiting_external")
        self.assertFalse(state["workflow"]["shouldKeepHeartbeat"])
        for k in ("paused","heartbeat","runner","concurrency","pilotPassed"):
            self.assertEqual(state["meta"][k],before["meta"][k])
        self.assertEqual(state["queue"],[])
        self.assertEqual(state["workers"],[])
        self.assertEqual(state["decisions"],before["decisions"])

    def test_new_question_waits_for_owner_then_receives_answer(self):
        d=self.decision()
        p={**self.proposal,"externalBlocker":None,"decisionIds":[d["id"]]}
        follow_up(self.ledger,self.token,self.d["id"],p)
        state=self.ledger.snapshot()
        self.assertEqual(state["continuations"][0]["decisions"][0]["status"],"open")
        self.assertFalse(state["workflow"]["shouldKeepHeartbeat"])
        self.ledger.submit(envelope(self.ledger,d))
        self.assertTrue(self.ledger.snapshot()["workflow"]["shouldKeepHeartbeat"])

    def test_proposed_queue_waits_for_approval_and_paused_dispatch(self):
        q=self.ledger.prepare(seed("fixture",profile="standard"))
        follow_up(self.ledger,self.token,self.d["id"],{**self.proposal,"externalBlocker":None,"queueIds":[q["id"]]})
        self.assertFalse(self.ledger.snapshot()["workflow"]["shouldKeepHeartbeat"])
        self.command("approve",{k:q[k] for k in ("seedHash","packetDigest")}|{"queueId":q["id"]})
        self.assertTrue(self.ledger.snapshot()["workflow"]["shouldKeepHeartbeat"])
        self.ledger.process(self.token)
        self.assertFalse(self.ledger.snapshot()["workflow"]["shouldKeepHeartbeat"])
        self.command("resume",{})
        self.ledger.process(self.token)
        self.assertTrue(self.ledger.snapshot()["workflow"]["shouldKeepHeartbeat"])

    def test_revision_keeps_immutable_history_and_requires_current_version(self):
        first=follow_up(self.ledger,self.token,self.d["id"],self.proposal)
        updated={**self.proposal,"summary":"New bounded proposal"}
        with self.assertRaises(Refusal):follow_up(self.ledger,self.token,self.d["id"],updated)
        second=follow_up(self.ledger,self.token,self.d["id"],{**updated,"expectedVersion":1})
        self.assertEqual(second["version"],2)
        self.assertEqual(self.ledger.document(first["id"])["spec"],self.proposal)
        self.assertEqual(self.ledger.snapshot()["continuations"][0]["proposal"],second)

    def test_superseded_question_and_changed_seed_need_revision(self):
        d=self.decision()
        q=self.ledger.prepare(seed("fixture",profile="standard"))
        follow_up(self.ledger,self.token,self.d["id"],{**self.proposal,"externalBlocker":None,"decisionIds":[d["id"]],"queueIds":[q["id"]]})
        self.ledger.prepare({**seed("fixture",profile="standard"),"objective":"New scope"})
        self.assertEqual(self.ledger.snapshot()["continuations"][0]["status"],"needs_revision")
        publish(self.ledger,self.token,{**d["spec"],"context":"New context"})
        self.assertTrue(self.ledger.snapshot()["workflow"]["shouldKeepHeartbeat"])

    def test_empty_self_links_old_artifacts_extra_fields_and_cross_repo_refused(self):
        other=self.artifact("other",repo="another")
        changes=({"externalBlocker":None},{"externalBlocker":{"reason":"x"}},
                 {"decisionIds":[self.d["id"]],"externalBlocker":None},
                 {"artifactIds":self.d["resolution"]["artifactIds"]},
                 {"artifactIds":[other]}, {"approve":True}, {"decisionIds":[{}]},
                 {"expectedVersion":True})
        for change in changes:
            with self.subTest(change=change),self.assertRaises(Refusal):
                follow_up(self.ledger,self.token,self.d["id"],{**self.proposal,**change})
        self.assertEqual(self.ledger.snapshot()["continuations"][0]["status"],"needs_proposal")

    def test_only_designated_running_brain_can_publish(self):
        self.ledger.release(self.token,"Saved fixture")
        other=self.ledger.acquire("other")
        with self.assertRaises(Refusal):follow_up(self.ledger,other,self.d["id"],self.proposal)
        self.ledger.release(other,"Saved fixture")
        self.token=self.ledger.acquire("brain-fixture:new")
        self.command("brain_stop",{})
        with self.assertRaises(Refusal):follow_up(self.ledger,self.token,self.d["id"],self.proposal)

    def test_policy_receipts_use_latest_state_not_old_toggle(self):
        follow_up(self.ledger,self.token,self.d["id"],self.proposal)
        self.command("listening",{"enabled":True})
        self.command("listening",{"enabled":False})
        self.ledger.process(self.token)
        state=self.ledger.snapshot()
        self.assertFalse(state["meta"]["decisionListener"]["enabled"])
        self.assertFalse(state["workflow"]["shouldKeepHeartbeat"])
        self.assertEqual(inbox(state)["commands"],[])
        self.assertEqual(self.ledger.process(self.token),[])

    def test_active_ownership_and_explicit_idle_preference_keep_supervision(self):
        follow_up(self.ledger,self.token,self.d["id"],self.proposal)
        base=self.ledger.snapshot()
        for key in ("worker","runner","periodic"):
            s=copy.deepcopy(base)
            if key=="worker":s["workers"]=[{"status":"blocked"}]
            elif key=="runner":s["meta"]["runner"]={"id":"owned"}
            else:s["meta"]["decisionListener"]={"enabled":True}
            self.assertTrue(workflow(s)["shouldKeepHeartbeat"])
            s["meta"]["brainControl"]={"desired":"stopped","phase":"parked"}
            self.assertFalse(workflow(s)["shouldKeepHeartbeat"])
