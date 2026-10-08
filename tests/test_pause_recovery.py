import contextlib
import copy
import json
import http.client
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orchestrator import missions, pause_recovery as recovery, standard
from orchestrator.app_server_wake import NATIVE_APPROVAL_POLICY
from orchestrator.assistant_actions import catalog
from orchestrator.assistant_journey import JourneyProposals
from orchestrator.core import Refusal, digest
from orchestrator.development_help import plan
from orchestrator.notification import BrainNotifier
from orchestrator.native_read_client import ReadProxy as RealReadProxy
import test_standard


class Metadata:
    def __init__(self, brain, cwd):
        self.calls = []
        self.thread = {"id": brain, "projectId": "native-project", "cwd": cwd, "status": {"type": "notLoaded"}}
        self.page = {"data": [{"id": "last-turn", "status": "completed", "completedAt": 1}], "nextCursor": None}

    def call(self, method, params):
        self.calls.append((method, copy.deepcopy(params)))
        return copy.deepcopy({"thread": self.thread} if method == "thread/read" else self.page)


class OwnedHost:
    def __init__(self, binding):
        self.binding, self.sent, self.approval = binding, [], None

    def configured(self, brain): return True
    def connection_status(self, brain): return {"status": "unchecked"}
    def pending_approval(self, brain): return self.approval
    def send(self, brain, message, command_id):
        self.sent.append((brain, message, command_id))
        return {"status": "accepted", "nativeDelivery": "owned_turn_start", "nativeTurnId": "recovery-turn"}
    def close(self): pass


class PauseRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_standard.StandardTest()
        self.fixture.setUp()
        self.ledger, self.registry = self.fixture.ledger, self.fixture.registry
        self.fixture.control()
        self.fixture.call("receive")
        self.pause = self.fixture.control("pause")
        self.ledger.release(self.fixture.token, "No tasks; failed Pause retained")
        self.brain = self.ledger.snapshot()["meta"]["brainId"]
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "a")
            repo["projectId"] = "catalog-project"
            self.ledger.put(db, "repos", "a", repo)
            self.pause["notification"] = {"status": "unavailable", "brainId": self.brain,
                "wakeId": digest({"commandId": self.pause["id"]}), "attemptedAt": 1, "finishedAt": 2,
                "detail": "Bound Codex app-server inspection failed before a turn was sent."}
            self.ledger.put(db, "commands", self.pause["id"], self.pause)
        self.before = standard.read(self.ledger)["run"]
        binding = {"endpoint": {}, "brains": {self.brain: {"workspaceId": "alpha", "cwd": str(self.fixture.repo),
            "projectId": "native-project", "catalogProjectId": "catalog-project", "nativePolicy": NATIVE_APPROVAL_POLICY.copy()}}}
        self.host = OwnedHost(binding)
        self.notifier = BrainNotifier(self.ledger)
        self.notifier.app_server = self.host
        self.runtime = SimpleNamespace(ledger=self.ledger, registry=self.registry, notifier=self.notifier,
                                       snapshot=self.state)
        self.proposals = JourneyProposals(self.runtime)
        self.metadata = Metadata(self.brain, str(self.fixture.repo))
        self.proxy = patch("orchestrator.native_read_client.ReadProxy")
        self.factory = self.proxy.start()
        self.factory.return_value.__enter__.return_value = self.metadata

    def tearDown(self):
        self.proxy.stop()
        self.fixture.tearDown()

    def state(self):
        state = self.ledger.snapshot()
        state.update(workspace={"id": "alpha", "name": "Alpha"}, standard=standard.read(self.ledger),
                     mission=missions.read(self.ledger), brainNotification=self.notifier.status(self.brain))
        return state

    def preview(self):
        state = self.state()
        return self.proposals.prepare(catalog(state, {})["phase_pause_recovery"], state, "session")

    def confirm(self, p, session="session"):
        return self.proposals.confirm(self.ledger, {"proposal": p, "confirmed": True}, session)

    def retained(self, ident):
        return next(c for c in self.ledger.snapshot()["commands"] if c["id"] == ident)

    def failed_first(self):
        proposal = self.preview()
        c = self.confirm(proposal)[0]["result"]
        self.host.send = lambda *args: {"status": "unavailable", "detail": "Closed pre-turn failure",
            "nativeFailure": {"version": 1, "stage": "thread_resume", "reason": "rpc_error", "rpcCode": -32600,
                              "resumeAttempted": True, "turnStartAttempted": False}}
        self.notifier.notify(c["id"])
        return proposal, self.retained(c["id"]), copy.deepcopy(standard.read(self.ledger)["run"]["pauseRecovery"])

    def test_replacement_is_a_separately_signed_read_only_preview(self):
        old_preview, old, old_permit = self.failed_first()
        state = self.state()
        self.assertEqual(state["standard"]["pauseRecovery"]["replacementOf"], old["id"])
        self.assertEqual(plan(state)["mode"], "decision")
        self.assertIn("replacement", plan(state)["title"])
        with contextlib.closing(self.ledger.connect()) as db: before = list(db.iterdump())
        p = self.preview()
        self.assertEqual(p["document"]["request"]["payload"]["replacement"], {
            "id": old["id"], "commandHash": digest(old), "notificationHash": digest(old["notification"]),
            "permitHash": digest(old_permit)})
        self.assertIn("No third", json.dumps(p))
        with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))
        self.assertFalse(self.host.sent)
        with patch("orchestrator.assistant_journey.time.time", return_value=time.time()+10000):
            self.assertFalse(self.confirm(old_preview)[1], "Old confirmation only reads its original receipt")
        self.assertEqual(self.retained(old["id"]), old)

    def test_replacement_preserves_failed_snapshot_and_only_receives_latest(self):
        _, old, old_permit = self.failed_first()
        self.host.send = OwnedHost.send.__get__(self.host)
        p = self.preview(); c = self.confirm(p)[0]["result"]
        permit = standard.read(self.ledger)["run"]["pauseRecovery"]
        self.assertEqual(permit["priorAttempt"], {"command": old, "permit": old_permit})
        retired = self.retained(old["id"])
        self.assertEqual(retired, recovery.retired_attempt(old, c["id"], c["createdAt"]))
        self.assertNotIn("receivedAt", retired); self.assertNotIn("completedAt", retired)
        self.assertEqual(retired["notification"], old["notification"])
        self.assertEqual(self.retained(self.pause["id"]), self.pause)
        self.notifier.notify(old["id"])
        self.notifier.notify(c["id"]); self.notifier.notify(c["id"])
        self.assertEqual(len(self.host.sent), 1)
        self.assertFalse(self.confirm(p)[1]); self.assertFalse(self.state()["standard"]["pauseRecovery"]["available"])
        token = self.ledger.acquire(self.brain+":replacement")
        with self.assertRaises(Refusal): self.fixture.call("pause_recovery_receive", token=token, requestId=old["id"])
        with self.assertRaises(Refusal): self.fixture.call("receive", token=token)
        self.fixture.call("pause_recovery_receive", token=token, requestId=c["id"])
        self.fixture.call("checkpoint", token=token, outcome="paused", summary="Replacement checkpoint; usage unknown",
                          brainObservedTokens=None, reasonCodes=["usage_evidence"])
        run = standard.read(self.ledger)["run"]
        self.assertEqual(run["status"], "paused")
        self.assertEqual(run["pauseRecovery"]["priorAttempt"], {"command": old, "permit": old_permit})
        self.assertEqual(self.retained(old["id"]), retired)
        for key in ("limits", "expiresAt", "brainAllowance", "brainObservedTokens", "brainUsageCoverage", "tasks"):
            self.assertEqual(run[key], self.before[key])
        self.ledger.release(token, "Replacement paused checkpoint")
        self.assertFalse(any(x["status"] in ("queued", "processing") for x in self.ledger.snapshot()["commands"]))

    def test_replacement_requires_closed_failure_and_excludes_every_unknown_effect(self):
        _, old, _ = self.failed_first()
        baseline = self.state()
        variants = [{"status": "uncertain"}, {"status": "sending"}, {"status": "accepted"},
            {"nativeTurnId": "x"}, {"nativeThreadObservation": {}}, {"nativeDelivery": "owned_turn_start"},
            {"nativeTurnStatus": "failed"}, {"finishedAt": 0}, {"attemptedAt": 1}, {"nativeFailure": None}]
        for changes in variants:
            state = copy.deepcopy(baseline)
            next(c for c in state["commands"] if c["id"] == old["id"])["notification"].update(changes)
            with self.subTest(changes=changes): self.assertFalse(recovery.availability(state)["available"])
        for changes in ({"turnStartAttempted": True}, {"stage": "turn_start"}, {"stage": "observation_record"}):
            state = copy.deepcopy(baseline)
            next(c for c in state["commands"] if c["id"] == old["id"])["notification"]["nativeFailure"].update(changes)
            with self.subTest(changes=changes): self.assertFalse(recovery.availability(state)["available"])

    def test_replacement_host_turn_scope_and_prior_record_drift_refuse(self):
        _, old, _ = self.failed_first()
        p = self.preview()
        self.metadata.page["data"][0]["id"] = "another"
        with self.assertRaises(Refusal): self.preview()
        with self.assertRaises(Refusal): self.confirm(p)
        self.metadata.page["data"][0]["id"] = "last-turn"
        self.host.binding["endpoint"]["changed"] = True
        with self.assertRaises(Refusal): self.preview()
        self.host.binding["endpoint"].clear()
        for field in ("notification", "payload"):
            changed = copy.deepcopy(old)
            if field == "notification": changed[field]["finishedAt"] += 0.01
            else: changed[field]["scopeHash"] = "different"
            with self.ledger.tx() as db: self.ledger.put(db, "commands", old["id"], changed)
            with self.subTest(field=field), self.assertRaises(Refusal): self.confirm(p)
            with self.ledger.tx() as db: self.ledger.put(db, "commands", old["id"], old)
        baseline = self.ledger.snapshot()["meta"]
        for field in ("expiresAt", "brainObservedTokens", "brainUsageCoverage", "limits"):
            meta = copy.deepcopy(baseline)
            if field == "limits": meta["standardRun"][field]["tokenBudget"] += 1
            elif field == "brainUsageCoverage": meta["standardRun"][field] = "observed_partial"
            else: meta["standardRun"][field] += 1
            with self.ledger.tx() as db: self.ledger.put(db, "meta", 1, meta)
            with self.subTest(field=field), self.assertRaises(Refusal): self.preview()
        with self.ledger.tx() as db: self.ledger.put(db, "meta", 1, baseline)

    def test_no_third_attempt_even_when_replacement_provably_failed_or_expired(self):
        self.failed_first()
        p = self.preview(); c = self.confirm(p)[0]["result"]
        self.notifier.notify(c["id"])
        self.assertFalse(self.state()["standard"]["pauseRecovery"]["available"])
        self.assertIn("third", self.state()["standard"]["pauseRecovery"]["reason"])
        with self.assertRaises(Refusal): self.preview()
        with patch("orchestrator.assistant_journey.time.time", return_value=time.time()+10000):
            self.assertFalse(self.confirm(p)[1])
            with self.assertRaises(Refusal): self.preview()

    def test_replacement_confirmation_failure_rolls_back_failed_disposition(self):
        _, old, old_permit = self.failed_first()
        p = self.preview(); original_put = self.ledger.put
        def fail_new(db, table, ident, value):
            if table == "commands" and ident == p["document"]["id"]: raise RuntimeError("fixture interruption")
            return original_put(db, table, ident, value)
        with patch.object(self.ledger, "put", side_effect=fail_new), self.assertRaises(RuntimeError): self.confirm(p)
        self.assertEqual(self.retained(old["id"]), old)
        self.assertEqual(standard.read(self.ledger)["run"]["pauseRecovery"], old_permit)
        self.assertEqual(self.retained(self.pause["id"]), self.pause)

    def test_expired_proved_failed_first_permit_is_not_renewed(self):
        _, old, old_permit = self.failed_first()
        with patch("time.time", return_value=old_permit["receiveBy"]+1):
            c = self.confirm(self.preview())[0]["result"]
        permit = standard.read(self.ledger)["run"]["pauseRecovery"]
        self.assertEqual(permit["priorAttempt"]["permit"], old_permit)
        self.assertEqual(permit["receiveBy"], c["createdAt"]+3600)
        self.assertEqual(standard.read(self.ledger)["run"]["expiresAt"], self.before["expiresAt"])
        self.assertEqual(permit["priorAttempt"]["command"], old)
        self.assertFalse(self.host.sent)

    def test_replacement_retained_snapshot_tamper_blocks_send_and_receipt(self):
        self.failed_first(); c = self.confirm(self.preview())[0]["result"]
        baseline = self.ledger.snapshot()["meta"]
        with self.ledger.tx() as db:
            value = self.ledger.get(db, "commands", c["id"])
            value["notification"] = {"status": "sending", "brainId": self.brain, "wakeId": digest({"commandId": c["id"]})}
            self.ledger.put(db, "commands", c["id"], value)
            meta = copy.deepcopy(baseline)
            meta["standardRun"]["pauseRecovery"]["priorAttempt"]["command"]["notification"]["finishedAt"] += 1
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal): recovery.send_check(self.ledger, self.host.binding, c["id"], self.metadata)
        token = self.ledger.acquire(self.brain+":tampered")
        with self.assertRaises(Refusal): self.fixture.call("pause_recovery_receive", token=token, requestId=c["id"])

    def test_read_only_catalog_help_and_preview_are_not_wakes(self):
        with contextlib.closing(self.ledger.connect()) as db: before = list(db.iterdump())
        state = self.state()
        self.assertTrue(state["standard"]["pauseRecovery"]["available"])
        self.assertEqual(plan(state)["key"], "phase_pause_recovery")
        self.assertEqual(plan(state)["mode"], "decision")
        self.assertFalse(self.metadata.calls)
        p = self.preview()
        self.assertEqual(p["document"]["expiresAt"]-p["document"]["createdAt"], 300)
        with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))
        self.assertFalse(self.host.sent)
        self.assertEqual({m for m, _ in self.metadata.calls}, {"thread/read", "thread/turns/list"})
        self.assertTrue(all(not params.get("includeTurns", False) for _, params in self.metadata.calls))
        self.assertIn("not a phase-budget", json.dumps(p))

    def test_real_read_proxy_closed_page_sizes_and_mutations(self):
        client = RealReadProxy({})
        params = {"threadId": self.brain, "cursor": None, "limit": 1,
                  "sortDirection": "desc", "itemsView": "notLoaded"}
        with patch.object(client, "_rpc", return_value={}) as rpc:
            client.call("thread/turns/list", params)
            client.call("thread/turns/list", {**params, "limit": 64})
            self.assertEqual(rpc.call_count, 2)
            for changed in ({"limit": 2}, {"limit": True}, {"itemsView": "full"}, {"sortDirection": "asc"}):
                with self.assertRaises(Refusal): client.call("thread/turns/list", {**params, **changed})
            with self.assertRaises(Refusal): client.call("turn/start", params)

    def test_exact_one_shot_receipt_and_paused_checkpoint(self):
        p = self.preview()
        result, first = self.confirm(p)
        c = result["result"]
        self.assertTrue(first)
        self.assertEqual(self.retained(self.pause["id"]), self.pause)
        help_progress = plan(self.state())
        self.assertEqual(help_progress["mode"], "follow")
        self.assertEqual(help_progress["requestId"], c["id"])
        self.assertEqual(standard.read(self.ledger)["run"]["status"], "stopping")
        self.notifier.notify(c["id"]); self.notifier.notify(c["id"])
        self.assertEqual(len(self.host.sent), 1)
        self.assertIn("pause_recovery_receive", self.host.sent[0][1])
        self.assertNotIn("Keep supervising", self.host.sent[0][1])
        self.assertFalse(self.confirm(p)[1])
        token = self.ledger.acquire(self.brain+":recovery")
        with self.assertRaises(Refusal): self.fixture.call("receive", token=token)
        with self.assertRaises(Refusal): self.ledger.process(token)
        self.fixture.call("pause_recovery_receive", token=token, requestId=c["id"])
        self.fixture.call("pause_recovery_receive", token=token, requestId=c["id"])
        self.assertEqual(self.retained(c["id"])["status"], "processing")
        self.assertEqual(self.retained(self.pause["id"])["notification"], self.pause["notification"])
        for outcome in ("completed", "blocked"):
            with self.assertRaises(Refusal):
                self.fixture.call("checkpoint", token=token, outcome=outcome, summary="Not allowed", brainObservedTokens=None)
        self.fixture.call("checkpoint", token=token, outcome="paused", summary="Saved Pause received; usage remains unknown. Review recovery next.",
                          brainObservedTokens=None, reasonCodes=["usage_evidence"])
        run = standard.read(self.ledger)["run"]
        self.assertEqual(run["status"], "paused")
        self.assertEqual(self.retained(c["id"])["status"], "completed")
        for key in ("limits", "expiresAt", "brainAllowance", "brainObservedTokens", "brainUsageCoverage", "tasks"):
            self.assertEqual(run[key], self.before[key])
        self.assertEqual(run["brainUsageCoverage"], "not_observed")
        self.ledger.release(token, "Pause checkpoint retained")

    def test_signature_scope_expiry_and_no_direct_submission(self):
        p = self.preview()
        for value in ("signature", "session", "workspaceId", "ledger"):
            bad = copy.deepcopy(p)
            if value == "signature": bad[value] = "bad"
            else:
                bad["document"][value] = "foreign"
                bad["signature"] = self.proposals.sign(bad["document"])
            with self.subTest(value=value), self.assertRaises(Refusal): self.confirm(bad)
        with patch("orchestrator.assistant_journey.time.time", return_value=time.time()+301):
            with self.assertRaises(Refusal): self.confirm(p)
        with self.assertRaises(Refusal):
            self.ledger.submit({"id": "bypass", "kind": recovery.KIND, "expectedRevision": self.state()["meta"]["revision"],
                                "payload": p["document"]["request"]["payload"]})
        self.assertEqual(self.retained(self.pause["id"]), self.pause)

    def test_legacy_and_closed_diagnostic_failure_not_ambiguous_delivery(self):
        self.assertTrue(recovery.pre_turn_failure(self.pause))
        for changes in ({"status": "uncertain"}, {"status": "accepted"}, {"detail": "Unavailable"},
                        {"nativeTurnId": "x"}, {"nativeThreadObservation": "x"}, {"finishedAt": float("nan")},
                        {"wakeId": "other"}, {"nativeDelivery": "owned_turn_start"}):
            c = copy.deepcopy(self.pause); c["notification"].update(changes)
            with self.subTest(changes=changes): self.assertFalse(recovery.pre_turn_failure(c))
        c = copy.deepcopy(self.pause)
        c["notification"]["nativeFailure"] = {"version": 1, "stage": "thread_read", "reason": "rpc_error",
            "resumeAttempted": False, "turnStartAttempted": False, "rpcCode": -32601}
        self.assertTrue(recovery.pre_turn_failure(c))
        for changes in ({"turnStartAttempted": True}, {"stage": "turn_start"}, {"stage": "observation_record"},
                        {"reason": "PRIVATE error"}, {"rpcCode": True}, {"version": True}, {"resumeAttempted": 0}):
            bad = copy.deepcopy(c); bad["notification"]["nativeFailure"].update(changes)
            with self.subTest(changes=changes): self.assertFalse(recovery.pre_turn_failure(bad))

    def test_pending_uncertain_recovery_permanently_prevents_second_attempt(self):
        p = self.preview(); c = self.confirm(p)[0]["result"]
        self.host.send = lambda *a: {"status": "uncertain", "detail": "Outcome unknown"}
        self.notifier.notify(c["id"])
        self.assertFalse(self.state()["standard"]["pauseRecovery"]["available"])
        with self.assertRaises(Refusal): self.preview()
        with patch("orchestrator.assistant_journey.time.time", return_value=time.time()+1000):
            self.assertFalse(self.confirm(p)[1])
        token = self.ledger.acquire(self.brain+":recovery")
        with self.assertRaises(Refusal): self.fixture.call("pause_recovery_receive", token=token, requestId=c["id"])
        self.assertEqual(self.retained(self.pause["id"]), self.pause)

    def test_latest_turn_unknown_active_absent_changed_and_private_data(self):
        old = copy.deepcopy(self.metadata.page)
        for page in ({"data": [], "nextCursor": None}, {"data": [{}], "nextCursor": None},
                     {"data": [{"id": "x", "status": "interrupted", "completedAt": 1}], "nextCursor": None},
                     {"data": [{"id": "x", "status": "completed", "completedAt": True}], "nextCursor": None}):
            self.metadata.page = page
            with self.subTest(page=page), self.assertRaises(Refusal): self.preview()
        self.metadata.page = old
        self.metadata.thread["status"] = {"type": "active"}
        with self.assertRaises(Refusal): self.preview()
        self.metadata.thread["status"] = {"type": "notLoaded"}
        self.metadata.page["data"][0].update(items=["PRIVATE"], error={"message": "PRIVATE"})
        self.assertNotIn("PRIVATE", json.dumps(self.preview()))
        count = 0
        def changed(method, params):
            nonlocal count
            result = self.metadata.call(method, params)
            if method == "thread/turns/list":
                count += 1
                if count == 4: result["data"][0]["id"] = "newer"
            return result
        self.factory.return_value.__enter__.return_value = SimpleNamespace(call=changed)
        with self.assertRaisesRegex(Refusal, "changed"): self.preview()

    def test_racing_scope_host_policy_stop_and_pending_requests_refuse(self):
        p = self.preview()
        original = self.ledger.snapshot()["meta"]
        for change in ("task", "merge", "stop", "controller", "admission", "limits", "expiry", "run", "brain", "handoff"):
            meta = copy.deepcopy(original)
            if change == "task": meta["standardRun"]["tasks"] = [{"id": "unknown", "status": "not_created", "observedTokens": 0, "allowance": 1}]
            elif change == "merge": meta["standardRun"]["merges"] = [{"status": "uncertain"}]
            elif change == "stop": meta["brainControl"] = {"desired": "stopped"}
            elif change == "controller": meta["controller"] = {"owner": "other"}
            elif change == "admission": meta["admissionBinding"] = {"id": "managed"}
            elif change == "limits": meta["standardRun"]["limits"]["tokenBudget"] += 1
            elif change == "expiry": meta["standardRun"]["expiresAt"] += 1
            elif change == "run": meta["standardRun"]["id"] = "another"
            elif change == "brain": meta["brainId"] = "another"
            else: meta["brainHandoff"] = {"status": "candidate"}
            with self.ledger.tx() as db: self.ledger.put(db, "meta", 1, meta)
            with self.subTest(change=change), self.assertRaises(Refusal): self.confirm(p)
        with self.ledger.tx() as db: self.ledger.put(db, "meta", 1, original)
        for key, value in (("projectId", "catalog-project"), ("catalogProjectId", "wrong"),
                           ("nativePolicy", {"sandbox": "danger-full-access"})):
            row = self.host.binding["brains"][self.brain]; old = row[key]; row[key] = value
            with self.subTest(key=key), self.assertRaises(Refusal): self.confirm(p)
            row[key] = old
        self.host.approval = {"id": "pending"}
        with self.assertRaises(Refusal): self.confirm(p)
        self.assertFalse(self.host.sent)

    def test_send_boundary_rechecks_exact_native_turn_and_racing_stop(self):
        c = self.confirm(self.preview())[0]["result"]
        with self.ledger.tx() as db:
            value = self.ledger.get(db, "commands", c["id"])
            value["notification"] = {"status": "sending", "brainId": self.brain,
                                      "wakeId": digest({"commandId": c["id"]})}
            self.ledger.put(db, "commands", c["id"], value)
        recovery.send_check(self.ledger, self.host.binding, c["id"], self.metadata)
        self.metadata.page["data"][0]["id"] = "different"
        with self.assertRaises(Refusal): recovery.send_check(self.ledger, self.host.binding, c["id"], self.metadata)
        self.metadata.page["data"][0]["id"] = "last-turn"
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["brainControl"] = {"desired": "stopped"}
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal): recovery.send_check(self.ledger, self.host.binding, c["id"], self.metadata)
        self.assertEqual(self.retained(self.pause["id"]), self.pause)

    def test_bridge_same_connection_rechecks_after_resume_and_stop_wins(self):
        from orchestrator.app_server_wake import AppServerWake
        from test_app_server_wake import FakeThread
        c = self.confirm(self.preview())[0]["result"]
        with self.ledger.tx() as db:
            value = self.ledger.get(db, "commands", c["id"])
            value["notification"] = {"status": "sending", "brainId": self.brain,
                                      "wakeId": digest({"commandId": c["id"]})}
            self.ledger.put(db, "commands", c["id"], value)
        fixture = self
        class Proxy(Metadata):
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def _rpc(self, method, params):
                if method == "thread/read": return self.call(method, params)
                self.calls.append((method, params))
                if method == "thread/resume":
                    fixture.assertIs(params.get("excludeTurns"), True)
                    self.thread["historyMode"] = "paginated"
                    self.thread["status"] = {"type": "idle"}
                    if self.stop:
                        with fixture.ledger.tx() as db:
                            meta = fixture.ledger.get(db, "meta", 1)
                            meta["brainControl"] = {"desired": "stopped"}
                            fixture.ledger.put(db, "meta", 1, meta)
                    return {"thread": copy.deepcopy(self.thread)}
                if method == "turn/start": return {"turn": {"id": "recovery-turn"}}
                raise AssertionError(method)
        baseline = self.ledger.snapshot()["meta"]
        for stop in (False, True):
            with self.ledger.tx() as db: self.ledger.put(db, "meta", 1, baseline)
            proxy = Proxy(self.brain, str(self.fixture.repo)); proxy.stop = stop
            wake = AppServerWake(self.host.binding, self.ledger)
            with patch.object(wake, "configured", return_value=True), \
                 patch("orchestrator.app_server_wake.WakeProxy", return_value=proxy), \
                 patch("orchestrator.app_server_wake.threading.Thread", FakeThread):
                result = wake.send(self.brain, "fixed checkpoint pointer", c["id"])
            wake.close()
            methods = [m for m, _ in proxy.calls]
            self.assertEqual(result["status"], "unavailable" if stop else "accepted")
            self.assertEqual(methods.count("turn/start"), 0 if stop else 1)
            self.assertEqual(methods.count("thread/turns/list"), 4 if stop else 8)
            self.assertIn("thread/resume", methods)
            resume = methods.index("thread/resume")
            self.assertIn("thread/turns/list", methods[:resume])
            if not stop: self.assertIn("thread/turns/list", methods[resume+1:])

    def test_worker_queue_strict_enrollment_decision_and_other_message_are_fenced(self):
        baseline = self.state()
        for change in ("worker", "queue", "strict", "enrollment", "decision", "message", "schema"):
            state = copy.deepcopy(baseline)
            if change in ("worker", "queue"): state["workers" if change == "worker" else "queue"] = [{}]
            elif change == "strict": state["repositories"][0]["policyProfile"] = "harness"
            elif change == "enrollment": state["admission"]["dispatchBlocked"] = True
            elif change == "decision": state["decisions"] = [{"status": "open"}]
            elif change == "schema": state["meta"]["schemaVersion"] = 3
            else: state["commands"].append({"id": "other", "kind": "reconcile", "status": "processing"})
            with self.subTest(change=change): self.assertFalse(recovery.availability(state)["available"])
        c = self.confirm(self.preview())[0]["result"]
        with self.registry.tx() as db:
            db.execute("CREATE TABLE admission_enrollment(id INTEGER PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("INSERT INTO admission_enrollment VALUES(1,?)", (json.dumps({"state": "prepared"}),))
        self.notifier.notify(c["id"])
        self.assertFalse(self.host.sent)
        self.assertNotIn("notification", self.retained(c["id"]))

    def test_no_desktop_fallback_early_checkpoint_or_new_effect(self):
        c = self.confirm(self.preview())[0]["result"]
        self.notifier.app_server = None
        self.notifier.notify(c["id"])
        self.assertNotIn("notification", self.retained(c["id"]))
        self.notifier.app_server = self.host
        self.notifier.notify(c["id"])
        token = self.ledger.acquire(self.brain+":recovery")
        with self.assertRaises(Refusal): self.fixture.call("checkpoint", token=token, outcome="paused", summary="No receipt", brainObservedTokens=None)
        for operation in ("receive", "claim", "issue", "bind", "finish", "merge_prepare", "catalog", "cancel_unissued"):
            with self.subTest(operation=operation), self.assertRaises(Refusal): self.fixture.call(operation, token=token)
        with self.assertRaises(Refusal): self.fixture.call("pause_recovery_receive", token="foreign", requestId=c["id"])
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta["standardRun"]["pauseRecovery"]["receiveBy"] = 1
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal): self.fixture.call("pause_recovery_receive", token=token, requestId=c["id"])

    def test_authenticated_http_help_is_read_only_preview_and_one_confirmation(self):
        from orchestrator.server import Dashboard
        server = Dashboard(self.ledger, 0, registry=self.registry, runtime_root=self.fixture.root,
                           inference_env=self.fixture.root/"missing.env")
        server.runtime_for("alpha").notifier.app_server = self.host
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        def request(path, body=None, auth=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST" if body is not None else "GET", path,
                         json.dumps(body) if body is not None else None,
                         {"Content-Type": "application/json", "Origin": server.origin, **(auth or {})})
            response = conn.getresponse()
            value = response.status, dict(response.getheaders()), json.loads(response.read()); conn.close()
            return value
        try:
            path = "/api/workspaces/alpha"
            self.assertEqual(request(path+"/assistant/help")[0], 401)
            _, headers, _ = request("/api/login", {"token": server.bootstrap})
            auth = {"Cookie": headers["Set-Cookie"].split(";")[0]}
            _, _, session = request(path+"/session", auth=auth); auth["X-CSRF-Token"] = session["csrf"]
            with contextlib.closing(self.ledger.connect()) as db: before = list(db.iterdump())
            help_view = request(path+"/assistant/help", auth=auth)[2]
            self.assertEqual(help_view["mode"], "decision")
            self.assertEqual(help_view["key"], "phase_pause_recovery")
            self.assertFalse(self.metadata.calls, "Polling cannot collect native metadata")
            with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))
            status, _, p = request(path+"/assistant/preview", {"key": "phase_pause_recovery"}, auth)
            self.assertEqual(status, 200, p)
            body = {"proposal": p, "confirmed": True}
            self.assertEqual(request(path+"/assistant/confirm", body, {**auth, "X-CSRF-Token": "wrong"})[0], 403)
            status, _, result = request(path+"/assistant/confirm", body, auth)
            self.assertEqual(status, 200, result)
            self.assertEqual(result["result"]["kind"], recovery.KIND)
            self.assertEqual(len(self.host.sent), 1)
            self.assertEqual(request(path+"/assistant/confirm", body, auth)[0], 200)
            self.assertEqual(len(self.host.sent), 1)
            self.assertEqual(self.retained(self.pause["id"]), self.pause)
        finally:
            server.shutdown(); server.server_close(); worker.join()


if __name__ == "__main__": unittest.main()
