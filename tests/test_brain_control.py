import time
import unittest

from orchestrator.brain_control import park
from orchestrator.core import Ledger, Refusal
from orchestrator.decisions import workflow
from orchestrator.observations import capture
import test_core


class BrainControlTest(unittest.TestCase):
    command=test_core.LedgerTest.command
    ready=test_core.LedgerTest.ready
    resume=test_core.LedgerTest.resume
    running=test_core.LedgerTest.running
    tearDown=test_core.LedgerTest.tearDown

    def setUp(self):
        test_core.LedgerTest.setUp(self)
        self.ledger.release(self.token,"Fixture controller handoff")
        self.token=self.ledger.acquire("brain-fixture:control-test")

    def stop(self):
        c=self.command("brain_stop")
        action=self.ledger.process(self.token)
        self.assertEqual(action[0]["commandId"],c["id"])
        return c

    def checkpoint(self, command):
        with self.ledger.tx() as db:
            artifact=capture(db,"checkpoint",("Checkpoint for "+command["id"]).encode(),
                {"repository":"a","name":"checkpoint.md","orderAt":time.time(),"references":[]})
        return {"summary":"Bounded step finished. No active external effect; resume from retained state.",
                "artifactIds":[artifact["id"]],"workerObservations":[]}

    def observation(self,w):
        current=next(x for x in self.ledger.snapshot()["workers"] if x["id"]==w["id"])
        return {"workerId":w["id"],"threadId":current["threadId"],"status":"idle", "observedAt":time.time(),"reference":"Native fixture wait observed idle after checkpoint"}

    def test_stop_immediately_fences_dispatch_and_supersedes_pending_resume(self):
        q=self.ready();self.resume()
        w=self.ledger.reserve(self.token,q["id"])
        old=self.command("resume")
        stop=self.command("brain_stop")
        state=self.ledger.snapshot()
        self.assertTrue(state["meta"]["paused"])
        self.assertEqual(state["meta"]["brainControl"]["phase"],"stop_requested")
        self.assertEqual(next(c for c in state["commands"] if c["id"]==old["id"])["status"],"rejected")
        with self.assertRaises(Refusal):self.ledger.begin_creation(self.token,w["id"])
        with self.assertRaises(Refusal):self.ledger.reserve(self.token,q["id"])
        with self.assertRaises(Refusal):self.command("resume")
        with self.assertRaises(Refusal):self.command("brain_stop")
        cp=self.checkpoint(stop)
        with self.assertRaises(Refusal):park(self.ledger,self.token,stop["id"],cp)
        self.ledger.process(self.token)
        park(self.ledger,self.token,stop["id"],cp)
        self.assertEqual(self.ledger.snapshot()["workers"][0]["status"],"reserved")

    def test_checkpoint_lifecycle_resume_is_separate_from_dispatch(self):
        self.resume()
        c=self.stop();cp=self.checkpoint(c)
        with self.assertRaises(Refusal):self.ledger.acknowledge(self.token,c["id"],True,"fake checkpoint")
        saved=park(self.ledger,self.token,c["id"],cp)
        self.assertEqual(park(self.ledger,self.token,c["id"],cp),saved)
        with self.assertRaises(Refusal):park(self.ledger,self.token,c["id"],{**cp,"summary":"Changed retry"})
        document=self.ledger.document(saved["documentHash"])
        self.assertEqual(document["commandId"],c["id"])
        self.assertEqual(document["workerObservations"],[])
        self.assertEqual(self.ledger.process(self.token),[])
        state=self.ledger.snapshot()
        self.assertEqual(workflow(state)["status"],"brain_stopped")
        self.assertFalse(workflow(state)["shouldKeepHeartbeat"])
        self.ledger.release(self.token,"Safe checkpoint saved; ending turn")
        restarted=Ledger(self.ledger.root)
        self.assertEqual(restarted.snapshot()["meta"]["brainControl"]["checkpoint"],saved)
        self.command("reconcile")
        resume=self.command("brain_resume")
        self.token=restarted.acquire("brain-fixture:resumed")
        restarted.process(self.token)
        state=restarted.snapshot()
        self.assertEqual(state["meta"]["brainControl"]["phase"],"ready")
        self.assertEqual(state["meta"]["brainControl"]["checkpoint"],saved)
        self.assertTrue(state["meta"]["paused"])
        self.assertEqual(next(x for x in state["commands"] if x["id"]==resume["id"])["status"],"completed")

    def test_stop_prioritized_and_reconciled_without_draining_saved_requests(self):
        c=self.command("reconcile")
        stop=self.stop()
        self.assertEqual(self.ledger.process(self.token)[0]["commandId"],stop["id"])
        self.assertEqual(next(x for x in self.ledger.snapshot()["commands"] if x["id"]==c["id"])["status"],"queued")

    def test_resume_supersedes_stop_and_late_checkpoint_is_refused(self):
        c=self.stop();cp=self.checkpoint(c)
        self.command("brain_resume")
        with self.assertRaises(Refusal):park(self.ledger,self.token,c["id"],cp)
        with self.assertRaises(Refusal):self.command("brain_resume")
        self.ledger.process(self.token)
        self.assertEqual(self.ledger.snapshot()["meta"]["brainControl"]["phase"],"ready")
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])

    def test_nonbrain_controller_cannot_receive_or_complete_stop_resume(self):
        c=self.command("brain_stop");cp=self.checkpoint(c)
        self.ledger.release(self.token,"Fixture relinquished")
        other=self.ledger.acquire("unrelated")
        with self.assertRaises(Refusal):self.ledger.process(other)
        with self.assertRaises(Refusal):park(self.ledger,other,c["id"],cp)
        self.command("brain_resume")
        with self.assertRaises(Refusal):self.ledger.process(other)

    def test_active_heartbeat_requires_fresh_paused_observation_after_stop(self):
        self.ledger.heartbeat("fixture-heartbeat","PAUSED")
        c=self.stop();cp=self.checkpoint(c)
        with self.assertRaises(Refusal):park(self.ledger,self.token,c["id"],cp)
        self.ledger.heartbeat("fixture-heartbeat","ACTIVE")
        with self.assertRaises(Refusal):park(self.ledger,self.token,c["id"],cp)
        self.ledger.heartbeat("fixture-heartbeat","PAUSED")
        park(self.ledger,self.token,c["id"],cp)

    def test_runner_not_released_by_stop_and_new_acceptance_is_blocked(self):
        w=self.running();self.ledger.transition(self.token,w["id"],"awaiting_acceptance","Ready")
        self.ledger.runner(self.token,w["id"],"acquire","Runner observed idle")
        c=self.stop();cp=self.checkpoint(c)
        with self.assertRaises(Refusal):park(self.ledger,self.token,c["id"],cp)
        self.assertIsNotNone(self.ledger.snapshot()["meta"]["runner"])
        self.ledger.runner(self.token,w["id"],"release","Process exit and cleanup observed")
        cp["workerObservations"]=[self.observation(w)]
        park(self.ledger,self.token,c["id"],cp)

    def test_stop_before_runner_acquire_refuses_acceptance(self):
        w=self.running();self.ledger.transition(self.token,w["id"],"awaiting_acceptance","Ready")
        self.stop()
        with self.assertRaises(Refusal):self.ledger.runner(self.token,w["id"],"acquire","Observed idle")

    def test_uncertain_creation_cannot_be_parked_or_freed(self):
        q=self.ready();self.resume();w=self.ledger.reserve(self.token,q["id"])
        self.ledger.begin_creation(self.token,w["id"])
        c=self.stop();cp=self.checkpoint(c)
        with self.assertRaises(Refusal):park(self.ledger,self.token,c["id"],cp)
        self.assertEqual(self.ledger.snapshot()["workers"][0]["status"],"starting")

    def test_active_workers_require_exact_fresh_native_idle_observation(self):
        w=self.running();c=self.stop();cp=self.checkpoint(c)
        with self.assertRaises(Refusal):park(self.ledger,self.token,c["id"],cp)
        good=self.observation(w)
        for change in ({"status":"running"},{"threadId":"wrong"},{"workerId":"wrong"},
                       {"observedAt":time.time()-121},{"observedAt":time.time()+100},
                       {"observedAt":True},{"reference":""},{"extra":"unsupported"}):
            with self.subTest(change=change),self.assertRaises(Refusal):
                park(self.ledger,self.token,c["id"],{**cp,"workerObservations":[{**good,**change}]})
        with self.assertRaises(Refusal):park(self.ledger,self.token,c["id"],{**cp,"workerObservations":[good,good]})
        cp["workerObservations"]=[good]
        park(self.ledger,self.token,c["id"],cp)
        current=self.ledger.snapshot()["workers"][0]
        self.assertEqual(current["id"],w["id"])
        self.assertEqual(current["status"],"running") # Preserve ledger ownership; observation is separate.
        self.assertFalse(current["archived"])

    def test_inflight_native_worker_control_requires_reconciliation(self):
        w=self.running();pending=self.command("checkpoint",{"workerId":w["id"]})
        self.ledger.process(self.token)
        c=self.stop();cp=self.checkpoint(c);cp["workerObservations"]=[self.observation(w)]
        with self.assertRaises(Refusal):park(self.ledger,self.token,c["id"],cp)
        self.ledger.acknowledge(self.token,pending["id"],True,"Actual native checkpoint observed")
        park(self.ledger,self.token,c["id"],cp)

    def test_checkpoint_requires_retained_new_artifact_and_closed_schema(self):
        before=self.checkpoint({"id":"earlier"})
        c=self.stop();cp=self.checkpoint(c)
        for invalid in (before,{**cp,"artifactIds":[]},{**cp,"artifactIds":["f"*64]},
                        {**cp,"artifactIds":cp["artifactIds"]*2},{**cp,"summary":""},
                        {**cp,"extra":True},{**cp,"workerObservations":{}}):
            with self.subTest(invalid=invalid),self.assertRaises(Refusal):park(self.ledger,self.token,c["id"],invalid)
        self.assertEqual(self.ledger.snapshot()["meta"]["brainControl"]["phase"],"checkpointing")

    def test_control_payloads_are_empty_and_retry_is_idempotent(self):
        for kind in ("brain_stop","brain_resume"):
            with self.assertRaises(Refusal):self.command(kind,{"threadId":"other"})
        c=self.command("brain_stop")
        self.assertEqual(self.ledger.submit({k:c[k] for k in ("id","kind","expectedRevision","payload")}),c)
