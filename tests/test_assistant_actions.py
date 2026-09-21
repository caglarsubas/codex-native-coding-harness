import copy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from orchestrator.assistant import chat, context
from orchestrator.assistant_actions import ActionProposals, catalog, resolve_action
from orchestrator.core import Ledger, Refusal, canonical
from orchestrator.decisions import publish
from test_assistant import CONFIG, response
from test_decisions import fixture


class AssistantActionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name)/"state")
        self.spec = fixture(self.ledger)
        self.token = self.ledger.acquire("brain-fixture:action-test")
        self.decision = publish(self.ledger, self.token, self.spec)
        self.proposals = ActionProposals()
        self.session = "fixture-session"

    def tearDown(self):
        self.tmp.cleanup()

    def actions(self):
        s = self.ledger.snapshot()
        _, links = context(s, "overview")
        return s, catalog(s, links)

    def proposal(self, key="brain_stop", text=None):
        s, actions = self.actions()
        intent = {"key": key, **({"text": text} if text is not None else {})}
        action = resolve_action(intent, actions, text or "Stop the brain")
        return self.proposals.prepare(action, s, self.session)

    def confirm(self, proposal, session=None):
        return self.proposals.confirm(self.ledger, {"proposal": proposal, "confirmed": True}, session or self.session)

    def test_proposal_is_inert_and_confirmation_is_exact_typed_control(self):
        before = self.ledger.snapshot()
        p = self.proposal()
        self.assertEqual(self.ledger.snapshot()["meta"], before["meta"])
        self.assertEqual(self.ledger.snapshot()["commands"], [])
        c, first = self.confirm(p)
        self.assertTrue(first)
        self.assertEqual(c["kind"], "brain_stop")
        self.assertEqual(c["status"], "queued")
        self.assertEqual(c["actor"], "assistant_owner_confirmed")
        after = self.ledger.snapshot()
        self.assertTrue(after["meta"]["paused"])
        self.assertEqual(after["meta"]["brainControl"]["phase"], "stop_requested")
        self.assertEqual(after["workers"], before["workers"])
        self.assertEqual(after["meta"]["heartbeat"], before["meta"]["heartbeat"])

    def test_explicit_confirm_session_signature_and_restart_required(self):
        p = self.proposal()
        for confirmed in (False, None, "true", 1):
            with self.assertRaises(Refusal):
                self.proposals.confirm(self.ledger, {"proposal": p, "confirmed": confirmed}, self.session)
        with self.assertRaises(Refusal): self.confirm(p, "other-session")
        for path in ("title", "impact", "target"):
            changed = copy.deepcopy(p); changed["document"]["preview"][path] = "harmless"
            with self.assertRaises(Refusal): self.confirm(changed)
        changed = copy.deepcopy(p); changed["document"]["command"]["kind"] = "resume"
        with self.assertRaises(Refusal): self.confirm(changed)
        with self.assertRaises(Refusal):
            ActionProposals().confirm(self.ledger, {"proposal": p, "confirmed": True}, self.session)
        self.assertEqual(self.ledger.snapshot()["commands"], [])

    def test_expiry_revision_and_replay_no_automatic_rebase(self):
        p = self.proposal()
        with patch("orchestrator.assistant_actions.time.time", return_value=p["document"]["expiresAt"]+1), self.assertRaises(Refusal):
            self.confirm(p)
        self.ledger.submit({"id":"external-change", "kind":"pause", "payload":{}, "expectedRevision":self.ledger.snapshot()["meta"]["revision"]})
        with self.assertRaisesRegex(Refusal, "State changed"): self.confirm(p)
        p = self.proposal(); c, first = self.confirm(p)
        with patch("orchestrator.assistant_actions.time.time", return_value=p["document"]["expiresAt"]+1):
            same, first = self.confirm(p)
        self.assertFalse(first)
        self.assertEqual(same, c)
        self.assertEqual(len(self.ledger.snapshot()["commands"]), 2)

    def test_concurrent_confirmation_has_one_durable_command(self):
        p = self.proposal(); results = []
        threads = [threading.Thread(target=lambda: results.append(self.confirm(p))) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(results), 4)
        self.assertEqual(len({c["id"] for c, _ in results}), 1)
        self.assertEqual(len(self.ledger.snapshot()["commands"]), 1)

    def test_no_arbitrary_payload_or_unsupported_actions(self):
        _, actions = self.actions()
        for intent in ({"key":"shell"}, {"key":"approve"}, {"key":"resume"}, {"key":"brain_stop","payload":{"target":"other"}},
                       {"key":"brain_stop","confirmed":True}, {"key":"answer_D1","text":"invented answer"}):
            with self.subTest(intent=intent), self.assertRaises(Refusal): resolve_action(intent, actions, "The actual message")

    def test_exact_free_text_answer_version_and_receipt(self):
        note = "I choose a third approach; retain existing constraints."
        p = self.proposal("answer_D1", note)
        c, _ = self.confirm(p)
        self.assertEqual(c["payload"]["note"], note)
        self.assertIsNone(c["payload"]["optionId"])
        self.assertEqual(c["payload"]["decisionHash"], self.decision["decisionHash"])
        self.assertEqual(self.ledger.snapshot()["decisions"][0]["response"]["note"], note)
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertNotIn("answer_D1", self.actions()[1])

    def test_stopped_brain_and_dispatch_remain_separate(self):
        self.confirm(self.proposal())
        _, actions = self.actions()
        self.assertFalse(actions["dispatch_resume"]["available"])
        self.assertTrue(actions["brain_resume"]["available"])
        self.confirm(self.proposal("brain_resume"))
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertFalse(self.actions()[1]["brain_resume"]["available"])

    def test_inference_only_returns_proposal_never_submits(self):
        r = response("Review the safe checkpoint stop below; it has not been executed.")
        msg = json.loads(r["choices"][0]["message"]["content"]); msg["action"] = {"key":"brain_stop"}
        r["choices"][0]["message"]["content"] = json.dumps(msg)
        with patch("orchestrator.assistant.settings", return_value=CONFIG), patch("orchestrator.assistant.Client.request", return_value=r):
            result = chat(self.ledger, {"view":"overview", "messages":[{"role":"user","content":"Stop the brain at a safe checkpoint"}]},
                          proposals=self.proposals, session=self.session)
        self.assertIsNotNone(result["proposal"])
        self.assertEqual(self.ledger.snapshot()["commands"], [])

    def test_platform_domain_context_freshness_capabilities_and_redaction(self):
        state = self.ledger.snapshot()
        state["brainActivity"] = {"status":"unknown", "lastKnownStatus":"idle", "fresh":False, "observedAt":123,
                                  "checkedAt":time.time(), "source":"local_task_events", "events":[{"text":"secret event body"}]}
        state["brainNotification"] = {"status":"configured", "secret":"private bridge"}
        state["meta"]["controller"]["owner"] = "private-owner"
        data, _ = context(state, "overview")
        self.assertEqual(data["facts"][11]["data"]["activity"]["status"], "unknown")
        self.assertFalse(data["facts"][11]["data"]["activity"]["fresh"])
        self.assertIsNone(data["facts"][8]["data"]["brainDesired"])
        self.assertEqual(len(data["capabilities"]), 13)
        self.assertIn("phaseCheckpoints", {c["view"] for c in data["capabilities"]})
        self.assertIn("runReadiness", {c["view"] for c in data["capabilities"]})
        for value in ("secret event body", "private-owner", "private bridge", self.decision["id"], self.token, "/fixture"):
            self.assertNotIn(value, canonical(data))
        self.assertTrue(any(a["key"] == "brain_stop" for a in data["actions"]))

    def test_large_portfolio_has_explicit_omission_counts(self):
        state = self.ledger.snapshot()
        state["repositories"] = [{**state["repositories"][0], "id":"r"+str(i)} for i in range(200)]
        data, _ = context(state, "metrics")
        repos = data["facts"][12]["data"]
        self.assertEqual(repos["total"], 200)
        self.assertGreaterEqual(repos["omitted"], 170)
        self.assertLessEqual(len(canonical(data).encode()), 48000)
