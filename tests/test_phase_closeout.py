import copy
import contextlib
import http.client as http_client
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import conversation, missions, phase_closeout, standard
from orchestrator.app_server_wake import NATIVE_APPROVAL_POLICY
from orchestrator.assistant_actions import catalog
from orchestrator.core import Refusal, digest
from orchestrator.development_help import plan
import test_checkpoint_recovery as recovery_fixture
from test_missions import request as mission_request, specification


class Metadata:
    def __init__(self, brain, cwd):
        self.calls = []
        self.thread = {"id": brain, "projectId": "owned-project", "cwd": str(cwd), "status": {"type": "notLoaded"}}
        self.page = {"data": [{"id": "fixture-native-turn", "status": "completed", "completedAt": 1}], "nextCursor": None}

    def call(self, method, params):
        self.calls.append((method, copy.deepcopy(params)))
        return copy.deepcopy({"thread": self.thread} if method == "thread/read" else self.page)


class PhaseCloseoutTest(unittest.TestCase):
    def setUp(self):
        self.f = recovery_fixture.CheckpointRecoveryTest()
        self.f.setUp()
        self.ledger, self.registry = self.f.ledger, self.f.registry
        self.brain = self.ledger.snapshot()["meta"]["brainId"]
        recovered, _ = self.f.confirm(self.f.preview())
        self.recovery = recovered["result"]
        self.f.notifier.notify(self.recovery["id"])
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", self.recovery["id"])
            command["notification"]["nativeTurnId"] = "fixture-native-turn"
            self.ledger.put(db, "commands", command["id"], command)
        token = self.ledger.acquire(self.brain + ":recovery")
        self.f.fixture.call("recovery_receive", token=token, requestId=self.recovery["id"])
        conversation.reply(self.ledger, token, self.recovery["payload"]["messageId"], {
            "message": "Expired, unqualified. No workers; owner closeout required. Keep the diagnostic uncertainty.",
            "artifactIds": [], "decisionIds": []})
        self.ledger.release(token, "Recovery reply saved; no further effects")
        self.f.native.binding = {"endpoint": {}, "brains": {self.brain: {
            "workspaceId": "alpha", "cwd": str(self.f.fixture.repo), "projectId": "owned-project",
            "catalogProjectId": "projectless", "nativePolicy": NATIVE_APPROVAL_POLICY.copy()}}}
        self.f.runtime.snapshot = self.f.snapshot
        self.metadata = Metadata(self.brain, self.f.fixture.repo)
        self.proxy = patch("orchestrator.native_read_client.ReadProxy")
        self.factory = self.proxy.start()
        self.factory.return_value.__enter__.return_value = self.metadata

    def tearDown(self):
        self.proxy.stop()
        self.f.tearDown()

    def preview(self):
        s = self.f.snapshot()
        return self.f.proposals.prepare(catalog(s, {})["phase_close"], s, "session")

    def confirm(self, p):
        return self.f.confirm(p)

    def mutate(self, fn):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            fn(meta)
            self.ledger.put(db, "meta", 1, meta)

    def test_read_only_next_step_and_preview_never_close_or_notify(self):
        with contextlib.closing(self.ledger.connect()) as db: before = list(db.iterdump())
        for _ in range(2):
            result = plan(self.f.snapshot())
            self.assertEqual((result["mode"], result["key"]), ("decision", "phase_close"))
        self.assertEqual(self.metadata.calls, [], "Help reads must not connect to the host")
        p = self.preview()
        self.assertEqual(p["document"]["preview"]["closeout"]["qualification"], "unqualified")
        self.assertEqual([m for m, _ in self.metadata.calls],
                         ["thread/read", "thread/turns/list", "thread/turns/list", "thread/read"])
        self.assertTrue(all(params.get("includeTurns") is False if m == "thread/read" else
                            params["itemsView"] == "notLoaded" and params["limit"] == 64
                            for m, params in self.metadata.calls))
        with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))
        self.assertEqual(len(self.f.native.sent), 1, "Only fixture's original recovery wake exists")

    def test_review_window_starts_after_slow_native_inspection(self):
        from orchestrator.assistant_actions import TTL
        now = time.time()
        original = phase_closeout.observe
        def slow(*args):
            result = original(*args)
            clock.return_value = now + 240
            return result
        with patch("orchestrator.assistant_journey.time.time", return_value=now) as clock, patch.object(phase_closeout, "observe", side_effect=slow):
            p = self.preview()
        self.assertEqual(p["document"]["createdAt"], now + 240)
        self.assertEqual(p["document"]["expiresAt"], now + 240 + TTL)
        self.assertEqual(self.f.snapshot()["standard"]["run"]["status"], "paused")

    def test_nonexpired_duration_stop_closes_without_rewriting_the_play_clock(self):
        def duration_stop(meta):
            run = meta["standardRun"]
            run["expiresAt"] = run["startedAt"] + 24 * 3600
            run["checkpoint"]["reasonCodes"] = ["duration", "external_dependency"]
        self.mutate(duration_stop)
        before = copy.deepcopy(standard.read(self.ledger)["run"])
        self.assertIn("Recorded duration stop", " ".join(standard.read(self.ledger)["blockers"]))
        self.assertFalse(catalog(self.f.snapshot(), {})["phase_resume"]["available"])
        self.assertEqual(plan(self.f.snapshot())["key"], "phase_close")
        p = self.preview()
        self.assertEqual(p["document"]["preview"]["closeout"]["stopBasis"], "duration_checkpoint")
        self.assertIn("duration-stopped", p["document"]["preview"]["summary"][0])
        result, notify = self.confirm(p)
        after = standard.read(self.ledger)["run"]
        self.assertFalse(notify)
        self.assertEqual(after["ownerCloseout"]["stopBasis"], "duration_checkpoint")
        self.assertEqual(after["ownerCloseout"]["originalExpiresAt"], before["expiresAt"])
        self.assertEqual(after["ownerCloseout"]["previousCheckpoint"], before["checkpoint"])
        for key in before:
            if key not in ("revision", "status", "checkpoint", "updatedAt"):
                self.assertEqual(after[key], before[key], key)
        self.assertEqual(after["status"], "blocked")
        self.assertEqual(after["ownerCloseout"]["qualification"], "unqualified")
        self.assertEqual(self.confirm(p)[0], result)
        self.assertEqual(len(self.f.native.sent), 1)
        self.assertEqual(plan(self.f.snapshot())["key"], "phase_help")

    def test_nonexpired_other_stop_or_malformed_duration_checkpoint_cannot_close(self):
        self.mutate(lambda m: m["standardRun"].update(expiresAt=time.time() + 86400))
        before = self.f.snapshot()
        self.assertFalse(phase_closeout.availability(before)["available"])
        for checkpoint in (None, {"reasonCodes": ["duration"]},
                           {"reasonCodes": "duration", "summary": "Stop", "at": time.time()},
                           {"reasonCodes": ["duration"], "summary": "", "at": time.time()},
                           {"reasonCodes": ["duration"], "summary": "Stop", "at": True},
                           {"reasonCodes": ["duration"], "summary": "Stop", "at": time.time()+300},
                           {"reasonCodes": ["duration"], "summary": "Stop", "at": 1}):
            bad = copy.deepcopy(before)
            bad["meta"]["standardRun"]["checkpoint"] = checkpoint
            self.assertFalse(phase_closeout.availability(bad)["available"])

    def test_closeout_preserves_usage_gap_and_old_checkpoint_without_wake(self):
        self.mutate(lambda m: m["standardRun"].update(usageReport={"gaps": ["invalid_token_record"],
            "coverage": "gapped", "collectedAt": 1, "through": 1, "tokens": {"total_tokens": 90000}},
            usageHighWater=95000, brainObservedTokens=85000, brainUsageCoverage="observed_partial"))
        before = copy.deepcopy(standard.read(self.ledger)["run"])
        p = self.preview()
        result, notify = self.confirm(p)
        self.assertFalse(notify)
        self.assertEqual(result["result"]["kind"], phase_closeout.KIND)
        after = standard.read(self.ledger)["run"]
        self.assertEqual(after["status"], "blocked")
        self.assertEqual(after["ownerCloseout"]["qualification"], "unqualified")
        self.assertEqual(after["ownerCloseout"]["previousCheckpoint"], before["checkpoint"])
        for key in before:
            if key not in ("revision", "status", "checkpoint", "updatedAt"):
                self.assertEqual(after[key], before[key], key)
        self.assertTrue(self.ledger.snapshot()["meta"]["paused"])
        self.assertEqual(len(self.f.native.sent), 1)
        self.assertNotIn("notification", result["result"])
        self.assertEqual(plan(self.f.snapshot())["key"], "phase_help")
        with contextlib.closing(self.ledger.connect()) as db:
            history = [json.loads(r[0]) for r in db.execute("SELECT data FROM snapshots WHERE kind='standard_run'")]
        self.assertTrue(any(r["run"] == before for r in history) or
                        any(r["run"]["status"] == "paused" for r in history))

    def test_exact_replay_after_expiry_or_successor_returns_receipt_only(self):
        p = self.preview(); first, _ = self.confirm(p)
        calls = len(self.metadata.calls)
        self.mutate(lambda m: m.update(brainControl={"desired": "stopped"}))
        with patch("orchestrator.assistant_journey.time.time", return_value=p["document"]["expiresAt"] + 1000):
            same, notify = self.confirm(p)
        self.assertEqual(same, first); self.assertFalse(notify)
        self.assertEqual(len(self.metadata.calls), calls)
        self.assertEqual(len(self.f.native.sent), 1)

    def test_successor_help_review_and_play_are_separate(self):
        self.confirm(self.preview())
        s = self.f.snapshot(); helper = self.f.proposals.prepare(catalog(s, {})["phase_help"], s, "session")
        run = copy.deepcopy(standard.read(self.ledger)["run"])
        result, notify = self.confirm(helper)
        self.assertTrue(notify)
        self.assertEqual(standard.read(self.ledger)["run"], run)
        token = self.ledger.acquire(self.brain + ":successor-preparation")
        conversation.receive(self.ledger, token, result["id"])
        spec = specification(mode="phase_delegated"); spec["phase"]["id"] = "genuinely-new-phase"
        missions.change(self.ledger, mission_request(spec=spec, expectedRevision=missions.read(self.ledger)["revision"]))
        conversation.reply(self.ledger, token, result["id"], {"message": "New draft ready; no Play.", "artifactIds": [], "decisionIds": []})
        self.ledger.release(token, "Draft only")
        self.assertEqual(plan(self.f.snapshot())["key"], "phase_review")
        self.assertEqual(missions.read(self.ledger)["effectiveStatus"], "draft")
        s = self.f.snapshot(); self.confirm(self.f.proposals.prepare(catalog(s, {})["phase_review"], s, "session"))
        self.assertEqual(plan(self.f.snapshot())["key"], "phase_play")
        self.assertEqual(standard.read(self.ledger)["run"], run, "Review cannot start or replace a run")
        token = self.ledger.acquire(self.brain + ":late-checkpoint")
        with self.assertRaisesRegex(Refusal, "cannot be reopened"):
            self.f.fixture.call("checkpoint", token=token, outcome="paused", summary="No reopen", brainObservedTokens=None)
        self.ledger.release(token, "Closed run unchanged")

    def test_signature_session_workspace_expiry_and_direct_submit_refuse(self):
        p = self.preview()
        bad = copy.deepcopy(p); bad["document"]["request"]["runHash"] = "bad"
        with self.assertRaises(Refusal): self.confirm(bad)
        with self.assertRaises(Refusal): self.f.confirm(p, "foreign-session")
        other, _ = self.f.fixture.workspace("beta")
        with self.assertRaises(Refusal): self.f.proposals.confirm(other, {"proposal": p, "confirmed": True}, "session")
        with patch("orchestrator.assistant_journey.time.time", return_value=p["document"]["expiresAt"] + 1):
            with self.assertRaises(Refusal): self.confirm(p)
        with self.assertRaises(Refusal): self.ledger.submit({"id": "unsafe", "kind": phase_closeout.KIND, "payload": {}})
        self.assertEqual(standard.read(self.ledger)["run"]["status"], "paused")

    def test_local_fences_and_ownership_races_preserve_the_run(self):
        changes = [lambda m: m.update(controller={"owner": "another"}), lambda m: m.update(runner={"id": "runner"}),
            lambda m: m.update(brainControl={"desired": "stopped"}), lambda m: m.update(brainHandoff={"status": "candidate"}),
            lambda m: m.update(admissionBinding={"owner": "managed"}), lambda m: m.update(schemaVersion=3),
            lambda m: m["standardRun"].update(tasks=[{"id": "pending", "status": "creating"}]),
            lambda m: m["standardRun"].update(merges=[{"status": "uncertain"}]),
            lambda m: m["standardRun"].update(expiresAt=time.time() + 300),
            lambda m: m["standardRun"]["recovery"].update(status="processing")]
        for change in changes:
            with self.subTest(change=change):
                p = self.preview(); old = copy.deepcopy(self.ledger.snapshot()["meta"])
                self.mutate(change)
                with self.assertRaises((Refusal, KeyError)): self.confirm(p)
                with self.ledger.tx() as db: self.ledger.put(db, "meta", 1, old)
        self.assertEqual(standard.read(self.ledger)["run"]["status"], "paused")

    def test_run_change_without_revision_and_enrollment_refuse(self):
        p = self.preview()
        self.mutate(lambda m: m["standardRun"].update(usageHighWater=100000))
        with self.assertRaisesRegex(Refusal, "Run changed"): self.confirm(p)
        p = self.preview()
        with patch("orchestrator.phase_closeout.record_in", return_value={"fenced": True}):
            with self.assertRaisesRegex(Refusal, "Maintenance"): self.confirm(p)
        with patch("orchestrator.phase_closeout.fence_exists", return_value=True):
            with self.assertRaisesRegex(Refusal, "Maintenance"): self.confirm(p)

    def test_pending_messages_even_held_or_missing_reply_block_closeout(self):
        meta = self.ledger.snapshot()["meta"]
        self.ledger.submit({"id": "held-message", "kind": "reconcile", "expectedRevision": meta["revision"],
            "payload": {"brainId": self.brain, "message": "Held instruction", "confirmed": True}})
        self.assertFalse(catalog(self.f.snapshot(), {})["phase_close"]["available"])
        with self.assertRaises(Refusal): self.preview()
        self.assertEqual(standard.read(self.ledger)["run"]["status"], "paused")

    def test_missing_accepted_delivery_or_corrupt_reply_is_not_closeout_evidence(self):
        for damage in ("notification", "reply"):
            with self.subTest(damage=damage), self.ledger.tx() as db:
                ident = self.recovery["id"] if damage == "notification" else self.recovery["payload"]["messageId"]
                old = self.ledger.get(db, "commands", ident); new = copy.deepcopy(old)
                if damage == "notification": new["notification"]["status"] = "uncertain"
                else: new["conversationReply"]["hash"] = "corrupt"
                self.ledger.put(db, "commands", ident, new)
            self.assertFalse(catalog(self.f.snapshot(), {})["phase_close"]["available"])
            with self.ledger.tx() as db: self.ledger.put(db, "commands", ident, old)

    def test_strict_project_and_legacy_worker_never_use_empty_run_closeout(self):
        state = self.f.snapshot()
        for key, value in (("workers", [{"status": "complete"}]), ("queue", [{"status": "proposed"}])):
            bad = copy.deepcopy(state); bad[key] = value
            self.assertFalse(phase_closeout.availability(bad)["available"])
        bad = copy.deepcopy(state); bad["repositories"][0]["policyProfile"] = "harness"
        self.assertNotIn("phase_close", catalog(bad, {}))

    def test_native_activity_latest_turn_identity_and_binding_changes_refuse(self):
        for changed in ("active", "turn", "project", "binding", "catalog", "time"):
            with self.subTest(changed=changed):
                p = self.preview(); thread, page, binding = copy.deepcopy(self.metadata.thread), copy.deepcopy(self.metadata.page), copy.deepcopy(self.f.native.binding)
                if changed == "active": self.metadata.thread["status"] = {"type": "active"}
                elif changed == "turn": self.metadata.page["data"][0]["id"] = "later-turn"
                elif changed == "project": self.metadata.thread["projectId"] = "catalog-not-native"
                elif changed == "time": self.metadata.page["data"][0]["completedAt"] = time.time() + 300
                elif changed == "binding": self.f.native.binding["endpoint"]["changed"] = True
                else: self.f.native.binding["brains"][self.brain]["catalogProjectId"] = "foreign"
                with self.assertRaises(Refusal): self.confirm(p)
                self.metadata.thread, self.metadata.page = thread, page; self.f.native.binding = binding
        self.assertEqual(standard.read(self.ledger)["run"]["status"], "paused")

    def test_native_unknown_incomplete_and_changing_reads_refuse(self):
        for page in ({"data": [], "nextCursor": None}, {"data": [{"id": "fixture-native-turn", "status": "completed"}]},
                     {"data": [{"id": "fixture-native-turn", "status": "inProgress", "completedAt": 1}], "nextCursor": None}):
            self.metadata.page = page
            with self.assertRaises(Refusal): self.preview()
        self.metadata.page = {"data": [{"id": "fixture-native-turn", "status": "completed", "completedAt": 1}], "nextCursor": None}
        call = self.metadata.call
        def racing(method, params):
            result = call(method, params)
            if method == "thread/turns/list": self.metadata.page["data"][0]["completedAt"] += 1
            return result
        with patch.object(self.metadata, "call", side_effect=racing):
            with self.assertRaisesRegex(Refusal, "changed during"): self.preview()

    def test_concurrent_tabs_close_once_and_lost_response_replays(self):
        previews = [self.preview(), self.preview()]
        def apply(p):
            try: return self.confirm(p)
            except Refusal: return None
        with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(apply, previews))
        self.assertEqual(sum(r is not None for r in results), 1)
        commands = [c for c in self.ledger.snapshot()["commands"] if c["kind"] == phase_closeout.KIND]
        self.assertEqual(len(commands), 1)
        self.assertEqual(len(self.f.native.sent), 1)

    def test_authenticated_http_journey_never_collects_on_poll_or_notifies_closeout(self):
        from orchestrator.server import Dashboard
        server = Dashboard(self.ledger, 0, registry=self.registry, runtime_root=self.f.fixture.root,
                           inference_env=self.f.fixture.root / "absent.env")
        server.runtime_for("alpha").notifier.app_server = self.f.native
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        def http(path, body=None, auth=None):
            conn = http_client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None,
                {"Content-Type": "application/json", "Origin": server.origin, **(auth or {})})
            r = conn.getresponse(); result = r.status, dict(r.getheaders()), json.loads(r.read()); conn.close(); return result
        path = "/api/workspaces/alpha/assistant"
        try:
            self.assertEqual(http(path + "/help")[0], 401)
            _, headers, _ = http("/api/login", {"token": server.bootstrap})
            auth = {"Cookie": headers["Set-Cookie"].split(";")[0]}
            _, _, session = http("/api/workspaces/alpha/session", auth=auth); auth["X-CSRF-Token"] = session["csrf"]
            for _ in range(2):
                status, _, help_step = http(path + "/help", auth=auth)
                self.assertEqual(status, 200); self.assertEqual(help_step["key"], "phase_close")
                self.assertNotIn("proposal", help_step)
            self.assertEqual(self.metadata.calls, [])
            status, _, p = http(path + "/preview", {"key": "phase_close"}, auth); self.assertEqual(status, 200, p)
            body = {"proposal": p, "confirmed": True}
            self.assertEqual(http(path + "/confirm", body, {**auth, "X-CSRF-Token": "wrong"})[0], 403)
            status, _, receipt = http(path + "/confirm", body, auth); self.assertEqual(status, 200, receipt)
            self.assertEqual(receipt["result"]["kind"], phase_closeout.KIND)
            self.assertEqual(len(self.f.native.sent), 1)
            calls = len(self.metadata.calls)
            self.assertEqual(http(path + "/confirm", body, auth)[0], 200)
            self.assertEqual(len(self.metadata.calls), calls)
            status, _, next_step = http(path + "/help", auth=auth)
            self.assertEqual(status, 200); self.assertEqual(next_step["key"], "phase_help")
            self.assertEqual(next_step["proposal"]["document"]["workflow"], "phase_help")
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=5)
