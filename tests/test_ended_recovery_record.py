import contextlib
import copy
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator import ended_recovery_record as record, phase_closeout, standard
from orchestrator.assistant_actions import catalog
from orchestrator.core import Refusal, digest, require
from orchestrator.notification import NOTIFY_KINDS
import test_pause_receipt_recovery as fixture


class EndedRecoveryRecordTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.PauseReceiptRecoveryTest()
        self.f.setUp()
        self.ledger, self.registry = self.f.ledger, self.f.registry
        p = self.f.preview()
        command = self.f.confirm(p)[0]["result"]
        self.f.notifier.notify(command["id"])
        with self.ledger.tx() as db:
            c = self.ledger.get(db, "commands", command["id"])
            c["notification"].update(hostRunId=self.f.before["id"], hostBindingHash=digest(self.f.host.binding),
                nativeTurnStatus="completed", nativeThreadObservation={"version": 1,
                    "rootThreadId": self.f.brain, "nativeTurnId": "recovery-turn", "streamStatus": "closed",
                    "events": [], "complete": False, "gaps": ["owned_stream_not_exhaustive"],
                    "monitoringEndedAt": time.time()-1},
                nativeResumeProfile={"version": 1, "brainId": self.f.brain, "commandId": c["id"],
                    "nativeTurnId": "recovery-turn", "bindingHash": digest(self.f.host.binding),
                    "requested": self.f.host.binding["brains"][self.f.brain]["nativePolicy"], "resumeAcknowledged": True})
            self.ledger.put(db, "commands", c["id"], c)
        self.recovery = self.f.base.retained(command["id"])
        self.metadata = self.f.metadata
        self.metadata.thread["status"]["type"] = "idle"
        self.metadata.page["data"][0]["id"] = "recovery-turn"
        self.metadata.calls.clear()
        self.f.host.orphan_recovery_idle = lambda: self.f.host.approval is None
        self.controls = SimpleNamespace(prior_binding=None, retired_host=None)
        self.f.base.runtime.turn_recovery_controls = self.controls
        self.patches = [patch.object(record, "MetadataProxy"), patch.object(record, "_scope", side_effect=self.scope),
                        patch.object(record, "membership", side_effect=self.membership),
                        patch.object(record, "validate_endpoint"),
                        patch("orchestrator.pause_host_continuity.check_catalog")]
        self.mocks = [p.start() for p in self.patches]
        self.mocks[0].return_value.__enter__.return_value = self.metadata
        self.before = self.ledger.snapshot()
        self.saved_before = record.saved_state(self.ledger)

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.f.tearDown()

    def scope(self, *_):
        row = self.f.host.binding["brains"][self.f.brain]
        info = self.ledger.db.stat()
        return {"root": self.ledger.root, "brainId": self.f.brain, "projectId": row["projectId"],
            "catalogProjectId": row["catalogProjectId"], "cwd": row["cwd"], "hostId": "local",
            "ledgerIdentity": [info.st_dev, info.st_ino], "ledgerRevision": self.ledger.snapshot()["meta"]["revision"],
            "endpointHash": digest(self.f.host.binding["endpoint"]), "bindingHash": digest(self.f.host.binding),
            "catalogHash": "c"*64, "locationHash": digest(["local", row["cwd"]])}

    def membership(self, registry, ledger, binding, scope):
        require(self.scope() == scope, "Project changed during inspection")

    def preview(self):
        s = self.f.base.state()
        return self.f.proposals.prepare(catalog(s, {})[record.WORKFLOW], s, "session")

    def confirm(self, p, session="session"):
        return self.f.base.confirm(p, session)

    def mutate(self, fn):
        with self.ledger.tx() as db:
            m = self.ledger.get(db, "meta", 1); fn(m); self.ledger.put(db, "meta", 1, m)

    def test_preview_only_reads_exact_metadata_and_never_wakes_or_writes(self):
        with contextlib.closing(self.ledger.connect()) as db: before = list(db.iterdump())
        for _ in range(3): self.assertTrue(record.availability(self.f.base.state())["available"])
        self.assertFalse(self.metadata.calls, "Polling must not collect native evidence")
        p = self.preview()
        self.assertEqual(p["document"]["preview"]["details"]["qualification"], "unqualified")
        methods = [m for m, _ in self.metadata.calls]
        self.assertEqual(methods.count("thread/turns/list"), 2)
        self.assertEqual(methods.count("thread/backgroundTerminals/list"), 2)
        self.assertTrue(set(methods) <= {"project/read", "thread/read", "thread/turns/list", "thread/backgroundTerminals/list"})
        self.assertFalse(set(methods) & {"thread/resume", "turn/start", "turn/interrupt"})
        with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))
        self.assertEqual(len(self.f.host.sent), 1, "Only fixture's already consumed recovery was sent")

    def test_atomic_record_preserves_complete_run_and_original_requests_without_safe_claim(self):
        p = self.preview(); result, notify = self.confirm(p)
        self.assertFalse(notify); self.assertNotIn(record.KIND, NOTIFY_KINDS)
        after = self.ledger.snapshot()
        self.assertEqual(after["meta"]["standardRun"], self.before["meta"]["standardRun"])
        for key in self.before["meta"]:
            if key != "revision": self.assertEqual(after["meta"][key], self.before["meta"][key], key)
        for old in self.before["commands"]: self.assertEqual(self.f.base.retained(old["id"]), old)
        self.assertNotIn("notification", result["result"])
        with contextlib.closing(self.ledger.connect()) as db:
            retained = self.ledger.get(db, "snapshots", result["result"]["payload"]["recordHash"])
        self.assertEqual(digest(retained), result["result"]["payload"]["recordHash"])
        self.assertEqual(retained["preservedRun"], self.before["meta"]["standardRun"])
        self.assertEqual(retained["exhaustedRecovery"], self.recovery)
        self.assertEqual(retained["originalPause"], self.f.original)
        self.assertEqual(retained["outcome"], "blocked")
        self.assertEqual(retained["qualification"], "unqualified")
        self.assertEqual(retained["request"]["evidence"]["observation"]["effectOutcome"], "unknown")
        self.assertFalse(phase_closeout.availability(self.f.base.state())["available"])
        self.assertFalse(standard.read(self.ledger)["available"])
        self.assertFalse(record.availability(self.f.base.state())["available"])
        self.assertFalse(self.f.base.state()["meta"]["pilotPassed"])

    def test_same_confirmation_recovers_receipt_after_expiry_without_host_or_writes(self):
        p = self.preview(); first = self.confirm(p)
        self.f.host.binding = None
        with patch.object(record, "inspect", side_effect=AssertionError("Replay cannot inspect")), \
             patch("orchestrator.assistant_journey.time.time", return_value=p["document"]["expiresAt"]+1):
            self.assertEqual(self.confirm(p), first)
        self.assertEqual(len(self.f.host.sent), 1)

    def test_interrupt_before_receipt_rolls_back_record_and_ownership_unchanged(self):
        p = self.preview()
        original = self.ledger.put
        def fail(db, table, key, value):
            if table == "commands" and value.get("kind") == record.KIND: raise RuntimeError("simulated interruption")
            return original(db, table, key, value)
        with patch.object(self.ledger, "put", side_effect=fail), self.assertRaises(RuntimeError): self.confirm(p)
        self.assertEqual(record.saved_state(self.ledger), self.saved_before)
        with contextlib.closing(self.ledger.connect()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (record.KIND,)).fetchone()[0], 0)
        self.assertFalse(self.confirm(p)[1])

    def test_two_tabs_record_once_never_notify(self):
        p = self.preview()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.confirm(p), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertFalse(any(notify for _, notify in results))
        self.assertEqual(sum(c["kind"] == record.KIND for c in self.ledger.snapshot()["commands"]), 1)

    def test_different_signed_reviews_cannot_record_the_same_recovery_twice(self):
        a, b = self.preview(), self.preview()
        self.confirm(a)
        with self.assertRaises(Refusal): self.confirm(b)
        self.assertEqual(sum(c["kind"] == record.KIND for c in self.ledger.snapshot()["commands"]), 1)

    def test_corrupt_retained_proof_refuses_receipt_replay(self):
        p = self.preview(); command = self.confirm(p)[0]["result"]
        with self.ledger.tx() as db:
            db.execute("UPDATE snapshots SET data=? WHERE id=?", ('{}', command["payload"]["recordHash"]))
        with patch.object(record, "inspect", side_effect=AssertionError("No host I/O on replay")), self.assertRaises(Refusal):
            self.confirm(p)

    def test_authenticated_http_saved_polling_is_inert_and_confirmation_never_notifies(self):
        import http.client
        import threading
        from orchestrator.server import Dashboard
        server = Dashboard(self.ledger, 0, registry=self.registry, runtime_root=self.f.fixture.root,
                           inference_env=self.f.fixture.root/"missing.env")
        runtime = server.runtime_for("alpha")
        runtime.notifier.app_server = self.f.host
        runtime.turn_recovery_controls = self.controls
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        def call(path, body=None, auth=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST" if body is not None else "GET", path, json.dumps(body) if body is not None else None,
                {"Content-Type": "application/json", "Origin": server.origin, **(auth or {})})
            response = conn.getresponse()
            value = response.status, dict(response.getheaders()), json.loads(response.read()); conn.close()
            return value
        try:
            prefix = "/api/workspaces/alpha"
            self.assertEqual(call(prefix+"/assistant/preview", {"key": record.WORKFLOW})[0], 403)
            _, headers, _ = call("/api/login", {"token": server.bootstrap})
            auth = {"Cookie": headers["Set-Cookie"].split(";")[0]}
            session = call(prefix+"/session", auth=auth)[2]; auth["X-CSRF-Token"] = session["csrf"]
            for _ in range(2):
                self.assertEqual(call(prefix+"/state", auth=auth)[0], 200)
                helper = call(prefix+"/assistant/help", auth=auth)[2]
                self.assertEqual(helper["mode"], "blocked")
                self.assertIsNone(helper.get("proposal"))
            self.assertFalse(self.metadata.calls)
            self.assertEqual(record.saved_state(self.ledger), self.saved_before)
            code, _, p = call(prefix+"/assistant/preview", {"key": record.WORKFLOW}, auth)
            self.assertEqual(code, 200)
            wrong = {"Cookie": auth["Cookie"], "X-CSRF-Token": "wrong"}
            body = {"proposal": p, "confirmed": True}
            self.assertEqual(call(prefix+"/assistant/confirm", body, wrong)[0], 403)
            code, _, receipt = call(prefix+"/assistant/confirm", body, auth)
            self.assertEqual(code, 200)
            self.assertEqual(receipt["result"]["kind"], record.KIND)
            calls = len(self.metadata.calls)
            self.assertEqual(call(prefix+"/assistant/confirm", body, auth)[2], receipt)
            self.assertEqual(len(self.metadata.calls), calls)
            self.assertEqual(len(self.f.host.sent), 1)
            self.assertEqual(standard.read(self.ledger)["run"], self.before["meta"]["standardRun"])
        finally:
            server.shutdown(); server.server_close(); worker.join(2)

    def test_signed_preview_session_scope_assent_and_expiry(self):
        p = self.preview()
        bad = copy.deepcopy(p); bad["document"]["request"]["recoveryId"] = "another"
        with self.assertRaises(Refusal): self.confirm(bad)
        with self.assertRaises(Refusal): self.confirm(p, "foreign-session")
        with self.assertRaises(Refusal): self.f.proposals.confirm(self.ledger, {"proposal": p, "confirmed": False}, "session")
        with patch("orchestrator.assistant_journey.time.time", return_value=p["document"]["expiresAt"]+1):
            with self.assertRaises(Refusal): self.confirm(p)
        other, _ = self.f.fixture.workspace("beta")
        with self.assertRaises(Refusal): self.f.proposals.confirm(other, {"proposal": p, "confirmed": True}, "session")
        with self.assertRaises(Refusal): self.ledger.submit({"id": "bypass", "kind": record.KIND, "payload": {}})

    def test_unloaded_active_unknown_and_nonempty_trackers_never_become_safe(self):
        for activity in ("notLoaded", "active", "systemError"):
            self.metadata.thread["status"]["type"] = activity
            with self.subTest(activity=activity), self.assertRaises(Refusal): self.preview()
        self.metadata.thread["status"]["type"] = "idle"
        for value in (None, {}, {"data": [], "nextCursor": "more"}, {"data": [{"id": "terminal"}], "nextCursor": None}):
            self.metadata.terminals = value
            with self.subTest(terminals=value), self.assertRaises(Refusal): self.preview()
        self.assertEqual(record.saved_state(self.ledger), self.saved_before)

    def test_changed_latest_turn_or_completion_fences_confirmation(self):
        p = self.preview()
        for change in ({"id": "later-turn"}, {"status": "inProgress"}, {"status": "failed"}, {"completedAt": None}, {"completedAt": 2}):
            old = copy.deepcopy(self.metadata.page)
            self.metadata.page["data"][0].update(change)
            with self.subTest(change=change), self.assertRaises(Refusal): self.confirm(p)
            self.metadata.page = old
        self.assertEqual(record.saved_state(self.ledger), self.saved_before)

    def test_pause_controller_usage_clock_ownership_and_fence_races(self):
        changes = [lambda m: m.update(controller={"owner": "abandoned"}), lambda m: m.update(runner={"id": "pending"}),
            lambda m: m.update(brainControl={"desired": "stopped"}), lambda m: m.update(admissionBinding={"owner": "managed"}),
            lambda m: m["standardRun"].update(tasks=[{"id": "pending", "status": "creating"}]),
            lambda m: m["standardRun"].update(usageHighWater=999), lambda m: m["standardRun"].update(expiresAt=1),
            lambda m: m["standardRun"].update(status="paused")]
        for change in changes:
            p = self.preview(); before = copy.deepcopy(self.ledger.snapshot()["meta"])
            self.mutate(change)
            with self.subTest(change=change), self.assertRaises(Refusal): self.confirm(p)
            with self.ledger.tx() as db: self.ledger.put(db, "meta", 1, before)
        p = self.preview()
        for name in ("record_in", "fence_exists"):
            with patch.object(record, name, return_value=True), self.assertRaises(Refusal): self.confirm(p)

    def test_native_prompt_or_observer_refuses_and_metadata_drops_content(self):
        self.f.host.approval = {"status": "pending"}
        with self.assertRaises(Refusal): self.preview()
        self.f.host.approval = None
        self.metadata.thread["transcript"] = "PRIVATE"
        self.metadata.page["data"][0]["items"] = [{"text": "PRIVATE"}]
        self.assertNotIn("PRIVATE", json.dumps(self.preview()))
        state = self.f.base.state()
        next(c for c in state["commands"] if c["id"] == self.recovery["id"])["notification"]["nativeApprovals"] = [{"status": "unknown"}]
        self.assertFalse(record.availability(state)["available"])

    def test_pending_decision_without_revision_bump_fences_inspection(self):
        for status in ("open", "answered"):
            p = self.preview()
            with self.ledger.tx() as db:
                self.ledger.put(db, "decisions", "pending", {"id": "pending", "status": status, "createdAt": time.time()})
            with self.subTest(status=status), self.assertRaises(Refusal): self.confirm(p)
            self.assertFalse(record.availability(record.saved_state(self.ledger))["available"])
            with self.ledger.tx() as db: db.execute("DELETE FROM decisions WHERE id='pending'")
        self.assertEqual(record.saved_state(self.ledger), self.saved_before)

    def test_expiry_during_confirmation_reads_refuses_before_local_commit(self):
        p = self.preview()
        original = record.inspect
        clock = patch("orchestrator.assistant_journey.time.time", return_value=p["document"]["expiresAt"]+1)
        def delayed(*args):
            value = original(*args); clock.start(); return value
        try:
            with patch.object(record, "inspect", side_effect=delayed), self.assertRaises(Refusal): self.confirm(p)
        finally: clock.stop()
        self.assertEqual(record.saved_state(self.ledger), self.saved_before)
        self.assertEqual(len(self.f.host.sent), 1)

    def test_replacement_retains_original_binding_and_requires_repeated_pid_absence(self):
        self.controls.prior_binding = copy.deepcopy(self.f.host.binding)
        self.controls.retired_host = {"version": 1, "bindingHash": digest(self.controls.prior_binding),
                                      "processId": 12345, "launchClaimHash": "f"*64}
        self.f.host.binding["endpoint"] = {"replacement": True}
        with patch("orchestrator.turn_host_continuity.process_absent", return_value=True) as absent:
            p = self.preview(); self.assertGreaterEqual(absent.call_count, 2)
            self.assertEqual(p["document"]["request"]["evidence"]["retiredHost"], self.controls.retired_host)
            self.assertFalse(self.confirm(p)[1])
        self.assertEqual(self.f.base.retained(self.recovery["id"]), self.recovery, "No claimed recovery migration")

    def test_changed_replacement_project_or_catalog_or_live_original_pid_refuses(self):
        self.controls.prior_binding = copy.deepcopy(self.f.host.binding)
        self.controls.retired_host = {"version": 1, "bindingHash": digest(self.controls.prior_binding),
                                      "processId": 12345, "launchClaimHash": "f"*64}
        self.f.host.binding["endpoint"] = {"replacement": True}
        for key in ("projectId", "catalogProjectId", "cwd", "nativePolicy", "workspaceId"):
            original = copy.deepcopy(self.f.host.binding["brains"][self.f.brain][key])
            self.f.host.binding["brains"][self.f.brain][key] = "wrong"
            with patch("orchestrator.turn_host_continuity.process_absent", return_value=True), self.subTest(key=key), self.assertRaises(Refusal): self.preview()
            self.f.host.binding["brains"][self.f.brain][key] = original
        with patch("orchestrator.turn_host_continuity.process_absent", return_value=False), self.assertRaises(Refusal): self.preview()


class ExactMetadataTransportTest(unittest.TestCase):
    def test_no_write_or_discovery_permit_exists(self):
        proxy = record.MetadataProxy({}, {"brainId": "brain", "projectId": "project"})
        for method in ("thread/resume", "turn/start", "turn/interrupt", "thread/list", "approval/respond", "thread/items/list"):
            with self.subTest(method=method), self.assertRaises(Refusal): proxy._rpc(method, {})
        with self.assertRaises(Refusal): proxy._rpc("thread/read", {"threadId": "other", "includeTurns": False})
