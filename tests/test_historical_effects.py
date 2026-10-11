import contextlib
import copy
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from orchestrator import historical_effects as history, ended_recovery_record as record, standard, development_help
from orchestrator.assistant_actions import catalog
from orchestrator.core import Refusal, digest
from orchestrator.notification import NOTIFY_KINDS
import test_ended_recovery_record as fixture


class HistoricalEffectsTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.EndedRecoveryRecordTest()
        self.f.setUp()
        self.ledger, self.registry = self.f.ledger, self.f.registry
        self.host, self.brain = self.f.f.host, self.f.f.brain
        with self.ledger.tx() as db:
            play = next(c for c in self.ledger.all(db, "commands") if c["kind"] == "standard_play")
            play["notification"] = {"status": "accepted", "nativeDelivery": "owned_turn_start",
                "brainId": self.brain, "hostRunId": self.f.before["meta"]["standardRun"]["id"],
                "hostBindingHash": digest(self.host.binding), "nativeTurnId": "play-turn",
                "nativeTurnStatus": "unconfirmed", "nativeThreadObservation": {"streamStatus": "closed", "events": []}}
            self.ledger.put(db, "commands", play["id"], play)
        self.turns = [
            {"id": "recovery-turn", "status": "completed", "completedAt": 3, "items": []},
            {"id": "pause-turn", "status": "completed", "completedAt": 2, "items": []},
            {"id": "play-turn", "status": "completed", "completedAt": 1, "items": [
                {"id": "call-1", "type": "commandExecution", "command": "PRIVATE COMMAND",
                 "status": "declined", "exitCode": None, "aggregatedOutput": "PRIVATE OUTPUT"}]}]
        for turn in self.turns: turn["itemsView"] = "full"
        self.metadata = self.f.metadata
        self.metadata.item_cursors = {}
        self.metadata.page["data"][0]["completedAt"] = 3
        self.rpc = self.metadata._rpc
        self.metadata._rpc = self.native
        self.raw = self.f.f.fixture.root / "logs" / "sessions" / ("rollout-"+self.brain+".jsonl")
        self.raw.parent.mkdir(parents=True)
        self.write_log()
        (self.ledger.root/"observations.json").write_text(json.dumps({"codexHome": str(self.raw.parent.parent)}))
        self.real_proxy = history.HistoryProxy
        self.proxy_patch = patch.object(history, "HistoryProxy")
        self.proxy_mock = self.proxy_patch.start()
        self.proxy_mock.return_value.__enter__.return_value = self.metadata
        # Endpoint and catalog are already mocked by the shared disposable fixture.
        self.endpoint = patch.object(history, "validate_endpoint")
        self.endpoint.start()
        self.member = patch.object(history, "membership", side_effect=self.f.membership)
        self.member.start()
        self.before = record.saved_state(self.ledger)

    def tearDown(self):
        self.member.stop()
        self.endpoint.stop()
        self.proxy_patch.stop()
        self.f.tearDown()

    def write_log(self, extra=None):
        rows = [{"type": "session_meta", "payload": {"id": self.brain, "cwd": self.metadata.thread["cwd"]}}]
        for turn in reversed(self.turns):
            rows.append({"type": "turn_context", "payload": {"turn_id": turn["id"], "cwd": self.metadata.thread["cwd"]}})
            if turn["id"] == "play-turn":
                rows.append({"type": "response_item", "payload": {"type": "function_call", "call_id": "call-1",
                    "name": "exec_command", "arguments": json.dumps({"cmd": "PRIVATE COMMAND"})}})
                if extra: rows.append(extra)
        self.raw.write_text("\n".join(json.dumps(r) for r in rows)+"\n")

    def native(self, method, params):
        if method == "thread/items/list":
            self.metadata.calls.append((method, copy.deepcopy(params)))
            raise Refusal("Fixture store does not support item pagination")
        if method == "thread/turns/list" and params.get("itemsView") == "full":
            self.metadata.calls.append((method, copy.deepcopy(params)))
            idx = 0 if params["cursor"] is None else int(params["cursor"])
            return {"data": [copy.deepcopy(self.turns[idx])],
                    "nextCursor": str(idx+1) if idx+1 < len(self.turns) else None}
        return self.rpc(method, params)

    def state(self):
        s = self.f.f.base.state()
        s["historicalEffects"] = history.saved_view(self.ledger, s)
        s["terminalCloseout"] = history.close_available(self.ledger, s)
        with contextlib.closing(self.ledger.connect()) as db:
            s["historicalCommandIds"] = sorted(history.historical_ids(self.ledger, db))
        return s

    def preview(self, closing=False):
        s = self.state()
        key = history.CLOSE_WORKFLOW if closing else history.WORKFLOW
        return self.f.f.proposals.prepare(catalog(s, {})[key], s, "session")

    def confirm(self, p, session="session"): return self.f.f.base.confirm(p, session)

    def test_non_waking_reconciliation_and_separate_closeout_preserve_all_originals(self):
        p = self.preview()
        self.assertNotIn("PRIVATE", json.dumps(p))
        self.assertEqual(p["document"]["request"]["evidence"]["report"]["effectOutcome"], "not_executed")
        result, notify = self.confirm(p)
        self.assertFalse(notify)
        self.assertEqual(record.saved_state(self.ledger)["meta"]["standardRun"], self.before["meta"]["standardRun"])
        self.assertEqual(development_help.plan(self.state())["key"], history.CLOSE_WORKFLOW)
        close = self.preview(True)
        closed, notify = self.confirm(close)
        self.assertFalse(notify)
        after = record.saved_state(self.ledger)
        old, run = self.before["meta"]["standardRun"], after["meta"]["standardRun"]
        for key in old:
            if key not in ("status", "revision", "updatedAt"): self.assertEqual(old[key], run[key], key)
        self.assertEqual(run["checkpoint"], old["checkpoint"], "No fabricated checkpoint")
        self.assertEqual(run["status"], "blocked")
        self.assertFalse(after["meta"]["pilotPassed"])
        self.assertIsNone(after["meta"]["controller"])
        for c in self.before["commands"]: self.assertEqual(self.f.f.base.retained(c["id"]), c)
        self.assertEqual(set(self.state()["historicalCommandIds"]), {self.f.recovery["id"], self.f.f.original["id"]})
        self.assertTrue(catalog(self.state(), {})["phase_help"]["available"])
        with self.ledger.tx() as db:
            development_help.validate_in(self.ledger, db, self.ledger.get(db, "meta", 1))
        self.assertEqual(len(self.host.sent), 1)
        self.assertNotIn(history.KIND, NOTIFY_KINDS); self.assertNotIn(history.CLOSE_KIND, NOTIFY_KINDS)
        with patch.object(history, "inspect", side_effect=AssertionError("No reread on replay")):
            self.assertEqual(self.confirm(close), (closed, False))
            self.assertEqual(self.confirm(p), (result, False))

    def test_missing_native_result_retains_unknown_without_closeout(self):
        self.turns[-1]["items"] = []
        p = self.preview()
        self.assertEqual(p["document"]["request"]["evidence"]["report"]["effectOutcome"], "unknown")
        self.assertIn("unmatched_effect:call-1", p["document"]["request"]["evidence"]["report"]["gaps"])
        self.confirm(p)
        self.assertFalse(history.close_available(self.ledger, self.state())["available"])
        self.metadata.calls.clear()
        self.assertEqual(development_help.plan(self.state())["mode"], "blocked", "Do not demand endless confirmations for missing evidence")
        self.assertFalse(self.metadata.calls, "Saved historical guidance never collects evidence")
        self.assertEqual(record.saved_state(self.ledger)["meta"]["standardRun"], self.before["meta"]["standardRun"])

    def test_interrupted_history_without_completion_time_is_recorded_unknown_not_safe(self):
        self.turns[-1].update(status="interrupted", completedAt=None)
        p = self.preview()
        report = p["document"]["request"]["evidence"]["report"]
        self.assertIn("historical_turn_completion_unknown:play-turn", report["gaps"])
        self.assertEqual(report["effectOutcome"], "unknown")
        self.confirm(p)
        self.assertFalse(history.close_available(self.ledger, self.state())["available"])
        self.turns[-1]["itemsView"] = "notLoaded"
        with self.assertRaises(Refusal): self.preview()

    def test_repeated_or_unlisted_turn_context_remains_a_coverage_gap(self):
        self.write_log({"type":"turn_context", "payload":{"turn_id":"play-turn", "cwd":self.metadata.thread["cwd"]}})
        p = self.preview(); self.confirm(p)
        self.assertIn("repeated_historical_turn_context", p["document"]["request"]["evidence"]["report"]["gaps"])
        self.assertFalse(history.close_available(self.ledger, self.state())["available"])
        self.write_log({"type":"turn_context", "payload":{"turn_id":"unlisted-turn", "cwd":self.metadata.thread["cwd"]}})
        self.assertIn("unlisted_historical_turn_context", self.preview()["document"]["request"]["evidence"]["report"]["gaps"])

    def test_executed_failed_or_unknown_effects_never_imply_cleanup(self):
        for status, code in (("completed", 0), ("failed", 1), ("inProgress", None), ("declined", 0)):
            self.turns[-1]["items"][0].update(status=status, exitCode=code)
            p = self.preview()
            r = p["document"]["request"]["evidence"]["report"]
            self.assertEqual(r["historicalTerminalCoverage"], "unknown")
            self.assertNotEqual(r["effectOutcome"], "not_executed")
            self.confirm(p)
            self.assertFalse(history.close_available(self.ledger, self.state())["available"])

    def test_unloaded_reconciliation_does_not_load_and_cannot_close(self):
        self.metadata.thread["status"]["type"] = "notLoaded"
        p = self.preview(); self.confirm(p)
        o = p["document"]["request"]["evidence"]["observation"]
        self.assertIsNone(o["trackedTerminals"]); self.assertEqual(o["terminalCoverage"], "unknown")
        with self.assertRaises(Refusal): self.preview(True)
        self.assertNotIn("thread/resume", [m for m,_ in self.metadata.calls])
        self.assertEqual(len(self.host.sent), 1)

    def test_nonempty_unknown_or_truncated_current_terminals_refuse_closeout(self):
        self.confirm(self.preview())
        for tracker in (None, {}, {"data": [], "nextCursor": "more"}, {"data": [{"id": "busy"}], "nextCursor": None}):
            self.metadata.terminals = tracker
            with self.subTest(tracker=tracker), self.assertRaises(Refusal): self.preview(True)

    def test_raw_command_mismatch_unmatched_call_or_native_effect_blocks_closeout(self):
        self.turns[-1]["items"][0]["command"] = "DIFFERENT"
        self.assertIn("unmatched_effect:call-1", self.preview()["document"]["request"]["evidence"]["report"]["gaps"])
        self.turns[-1]["items"][0]["command"] = "PRIVATE COMMAND"
        self.write_log({"type":"response_item","payload":{"type":"custom_tool_call","call_id":"other","name":"apply_patch","input":"PRIVATE"}})
        self.assertIn("unmatched_effect:other", self.preview()["document"]["request"]["evidence"]["report"]["gaps"])

    def test_unknown_native_item_types_remain_unresolved(self):
        for kind in ("fileChange", "dynamicToolCall", "mcpToolCall", "collabAgentToolCall", "futureType"):
            self.turns[-1]["items"][0]["type"] = kind
            report = self.preview()["document"]["request"]["evidence"]["report"]
            self.assertEqual(report["effectOutcome"], "unknown")
            self.assertIn("unknown_effect:call-1", report["gaps"])

    def test_missing_or_compacted_rollout_does_not_prove_no_effect(self):
        self.write_log({"type":"compacted","payload":{}})
        self.assertIn("compacted_effect_inventory", self.preview()["document"]["request"]["evidence"]["report"]["gaps"])
        self.raw.unlink()
        with self.assertRaises(Refusal): self.preview()

    def test_malformed_active_duplicate_and_missing_play_history_refuse(self):
        old = copy.deepcopy(self.turns)
        for modify in (lambda: self.turns[-1].update(id="missing"),
                       lambda: self.turns[0].update(status="inProgress"),
                       lambda: self.turns[1].update(id="recovery-turn"),
                       lambda: self.turns[-1].update(items=None),
                       lambda: self.turns[-1]["items"].append(copy.deepcopy(self.turns[-1]["items"][0]))):
            modify()
            with self.assertRaises(Refusal): self.preview()
            self.turns = copy.deepcopy(old)

    def test_latest_turn_and_usage_expiry_ownership_races_refuse(self):
        p = self.preview()
        for fn in (lambda m:m["standardRun"].update(usageHighWater=10000),
                   lambda m:m["standardRun"].update(expiresAt=1),
                   lambda m:m.update(controller={"owner":"unknown"}),
                   lambda m:m["standardRun"].update(tasks=[{"id":"pending"}]),
                   lambda m:m.update(brainControl={"desired":"stopped"})):
            old = copy.deepcopy(self.ledger.snapshot()["meta"])
            self.f.mutate(fn)
            with self.assertRaises(Refusal): self.confirm(p)
            with self.ledger.tx() as db:self.ledger.put(db,"meta",1,old)
        self.metadata.page["data"][0]["id"] = "later"
        with self.assertRaises(Refusal): self.confirm(p)
        self.assertEqual(record.saved_state(self.ledger), self.before)

    def test_changed_historical_result_requires_fresh_owner_review(self):
        p = self.preview()
        self.turns[-1]["items"][0]["status"] = "completed"
        self.turns[-1]["items"][0]["exitCode"] = 0
        with self.assertRaises(Refusal): self.confirm(p)

    def test_concurrent_confirmation_records_once_without_notify(self):
        p = self.preview()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:self.confirm(p),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(sum(c["kind"]==history.KIND for c in self.ledger.snapshot()["commands"]),1)

    def test_atomic_interruption_rolls_back_closeout_and_sidecar(self):
        self.confirm(self.preview())
        p = self.preview(True); before = record.saved_state(self.ledger)
        original = self.ledger.event
        def interrupt(db, kind, payload):
            if kind == history.CLOSE_KIND: raise RuntimeError("interrupted")
            return original(db,kind,payload)
        with patch.object(self.ledger,"event",side_effect=interrupt), self.assertRaises(RuntimeError):self.confirm(p)
        self.assertEqual(record.saved_state(self.ledger),before)
        self.assertFalse(self.confirm(p)[1])

    def test_signature_session_expiry_and_raw_submit_cannot_bypass_review(self):
        p = self.preview()
        with self.assertRaises(Refusal):self.confirm(p,"foreign")
        changed = copy.deepcopy(p);changed["document"]["request"]["closing"]=True
        with self.assertRaises(Refusal):self.confirm(changed)
        with patch("orchestrator.assistant_journey.time.time",return_value=p["document"]["expiresAt"]+1):
            with self.assertRaises(Refusal):self.confirm(p)
        with self.assertRaises(Refusal):self.ledger.submit({"id":"bypass","kind":history.CLOSE_KIND,"payload":{}})

    def test_corrupt_record_or_original_request_fences_retirement(self):
        self.confirm(self.preview()); command = self.confirm(self.preview(True))[0]["result"]
        with self.ledger.tx() as db:
            old = self.ledger.get(db,"commands",self.f.f.original["id"])
            old["result"]="changed"; self.ledger.put(db,"commands",old["id"],old)
        with contextlib.closing(self.ledger.connect()) as db, self.assertRaises(Refusal): history.historical_ids(self.ledger,db)
        with self.ledger.tx() as db:db.execute("UPDATE snapshots SET data='{}' WHERE id=?",(command["payload"]["recordHash"],))
        with contextlib.closing(self.ledger.connect()) as db, self.assertRaises(Refusal):
            history.retained(self.ledger, db, command, {"closing": True})

    def test_polling_and_help_are_inert(self):
        for _ in range(3):history.availability(self.state());development_help.plan(self.state())
        self.assertFalse(self.metadata.calls)
        self.assertEqual(record.saved_state(self.ledger),self.before)

    def test_custom_exec_call_is_correlated_but_code_mode_is_unknown(self):
        self.write_log()
        rows = [json.loads(line) for line in self.raw.read_text().splitlines()]
        call = next(r["payload"] for r in rows if r["type"] == "response_item")
        call.update(type="custom_tool_call", input=call.pop("arguments"))
        self.raw.write_text("\n".join(json.dumps(r) for r in rows)+"\n")
        self.assertEqual(self.preview()["document"]["request"]["evidence"]["report"]["effectOutcome"], "not_executed")
        call["name"] = "exec"
        self.raw.write_text("\n".join(json.dumps(r) for r in rows)+"\n")
        self.assertIn("unmatched_effect:call-1", self.preview()["document"]["request"]["evidence"]["report"]["gaps"])

    def test_validated_closeout_allows_only_future_catalog_preparation_not_old_recovery(self):
        self.confirm(self.preview()); self.confirm(self.preview(True))
        token = self.ledger.acquire(self.brain)
        before = record.saved_state(self.ledger)
        # Existing mission gates still apply; the closure does not review a plan.
        from orchestrator import missions
        from test_missions import specification, request
        spec = specification(mode="phase_delegated"); spec["phase"]["id"] = "successor"
        current = missions.change(self.ledger, request(spec=spec, revision=missions.read(self.ledger)["revision"]))["current"]
        missions.change(self.ledger, request("review", current["revision"], documentHash=current["documentHash"], confirmed=True))
        standard.brain(self.registry, self.ledger, token, {"operation":"catalog",
            "models":[{"model":"fixture-model", "efforts":["high"]}], "source":"disposable test metadata"})
        self.assertEqual(record.saved_state(self.ledger)["meta"]["standardRun"], before["meta"]["standardRun"])
        for operation in ("receive", "pause_receipt_recovery_receive", "claim"):
            with self.assertRaises(Refusal):
                standard.brain(self.registry, self.ledger, token, {"operation":operation, "runId":self.before["meta"]["standardRun"]["id"]})
        for c in self.before["commands"]: self.assertEqual(self.f.f.base.retained(c["id"]), c)

    def test_nested_effect_compaction_and_unknown_records_cannot_be_ignored(self):
        for extra, gap in (
            ({"type":"event_msg", "payload":{"type":"item_completed", "thread_id":self.brain,
                "turn_id":"play-turn", "item":{"id":"nested", "type":"CommandExecution"}}}, "additional_native_effect:nested"),
            ({"type":"event_msg", "payload":{"type":"item_completed", "item":{"type":"ContextCompaction"}}}, "compacted_effect_inventory"),
            ({"type":"event_msg", "payload":{"type":"future_native_event"}}, "unsupported_native_event"),
            ({"type":"future_record", "payload":{}}, "unsupported_rollout_record")):
            self.write_log(extra)
            self.assertIn(gap, self.preview()["document"]["request"]["evidence"]["report"]["gaps"])
        self.write_log({"type":"event_msg", "payload":{"type":"item_completed", "thread_id":self.brain,
            "turn_id":"play-turn", "item":{"id":"call-1", "type":"CommandExecution", "command":"PRIVATE COMMAND",
            "status":"Declined", "exit_code":None}}})
        self.assertEqual(self.preview()["document"]["request"]["evidence"]["report"]["effectOutcome"], "not_executed")

    def test_absent_pause_and_foreign_or_malformed_log_identity_refuse(self):
        self.turns[1]["id"] = "unrelated-turn"; self.write_log()
        with self.assertRaises(Refusal): self.preview()
        self.turns[1]["id"] = "pause-turn"; self.write_log()
        original = self.raw.read_text()
        for header in ([], {"type":"session_meta", "payload":[]},
                       {"type":"session_meta", "payload":{"id":"other", "cwd":self.metadata.thread["cwd"]}}):
            self.raw.write_text(json.dumps(header)+"\n"+"\n".join(original.splitlines()[1:])+"\n")
            with self.assertRaises(Refusal): self.preview()
        self.raw.write_text(original)

    def test_review_expiring_during_native_inspection_is_refused_at_commit(self):
        p = self.preview()
        old = history.inspect
        def expire(*args, **kwargs):
            value = old(*args, **kwargs)
            self.expiry = patch("orchestrator.historical_effects.time.time", return_value=p["document"]["expiresAt"]+1)
            self.expiry.start()
            return value
        try:
            with patch.object(history, "inspect", side_effect=expire), self.assertRaises(Refusal): self.confirm(p)
        finally: self.expiry.stop()
        self.assertEqual(record.saved_state(self.ledger), self.before)

    def test_authenticated_http_controls_are_separate_and_non_waking(self):
        import http.client
        import threading
        from orchestrator.server import Dashboard
        server = Dashboard(self.ledger, 0, registry=self.registry, runtime_root=self.f.f.fixture.root,
                           inference_env=self.f.f.fixture.root/"missing.env")
        runtime = server.runtime_for("alpha")
        runtime.notifier.app_server, runtime.turn_recovery_controls = self.host, self.f.controls
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        def request(path, body=None, auth=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST" if body is not None else "GET", path,
                json.dumps(body) if body is not None else None,
                {"Content-Type":"application/json", "Origin":server.origin, **(auth or {})})
            response = conn.getresponse(); result = response.status, dict(response.getheaders()), json.loads(response.read())
            conn.close(); return result
        try:
            path = "/api/workspaces/alpha"
            self.assertEqual(request(path+"/assistant/help")[0], 401)
            _, headers, _ = request("/api/login", {"token":server.bootstrap})
            auth = {"Cookie":headers["Set-Cookie"].split(";")[0]}
            _, _, session = request(path+"/session", auth=auth); auth["X-CSRF-Token"] = session["csrf"]
            self.assertEqual(request(path+"/assistant/help", auth=auth)[2]["key"], history.WORKFLOW)
            self.assertFalse(self.metadata.calls)
            for key in (history.WORKFLOW, history.CLOSE_WORKFLOW):
                status, _, proposal = request(path+"/assistant/preview", {"key":key}, auth)
                self.assertEqual(status, 200, proposal)
                body = {"proposal":proposal, "confirmed":True}
                self.assertLess(len(json.dumps(body).encode()), 32768)
                self.assertEqual(request(path+"/assistant/confirm", body, {**auth,"X-CSRF-Token":"wrong"})[0], 403)
                status, _, receipt = request(path+"/assistant/confirm", body, auth)
                self.assertEqual(status, 200, receipt)
                self.assertEqual(receipt["result"]["kind"], history.KIND if key == history.WORKFLOW else history.CLOSE_KIND)
                self.assertEqual(request(path+"/assistant/confirm", body, auth)[2], receipt)
            for old in self.before["commands"]: self.assertEqual(self.f.f.base.retained(old["id"]), old)
            self.assertEqual(len(self.host.sent), 1)
        finally: server.shutdown(); server.server_close(); worker.join()

    def test_transport_refuses_every_write_and_foreign_cursor(self):
        scope={"brainId":"brain","projectId":"project"}
        proxy=self.real_proxy({},scope)
        for method,params in (("thread/resume",{}),("turn/start",{}),("turn/interrupt",{}),
                              ("command/exec",{}),("item/commandExecution/requestApproval",{}),
                              ("thread/turns/list",{"threadId":"other","cursor":None,"limit":1,"sortDirection":"desc","itemsView":"full"}),
                              ("thread/turns/list",{"threadId":"brain","cursor":"not-returned","limit":1,"sortDirection":"desc","itemsView":"full"})):
            with self.subTest(method=method),self.assertRaises(Refusal):proxy._rpc(method,params)
