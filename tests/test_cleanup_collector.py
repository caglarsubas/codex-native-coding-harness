import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from orchestrator import cleanup_collector as cleanup, historical_effects as history
from orchestrator.core import Refusal, digest
from orchestrator.native_read_client import NativeReadFailure, ReadProxy
import test_historical_effects as fixture
import test_historical_multi_host as multi_fixture


class CleanupCollectorTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.HistoricalEffectsTest(); self.f.setUp()
        self.ledger, self.registry = self.f.ledger, self.f.registry
        self.wake, self.controls = self.f.host, self.f.f.controls
        self.f.turns[-1]["items"][0].update(status="completed", exitCode=0, cwd="PRIVATE CWD", processId="native-handle")
        self.tracker = {"data": [], "nextCursor": None}
        self.on_read = None
        self.reads = []
        self.patches = [patch.object(ReadProxy, "_rpc", lambda proxy,method,params:self.native(method,params)),
                        patch.object(cleanup.CleanupProxy, "__enter__", lambda p:p),
                        patch.object(cleanup.CleanupProxy, "__exit__", lambda *a:None),
                        patch.object(cleanup, "validate_endpoint")]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.f.tearDown()

    def native(self, method, params):
        self.reads.append((method, copy.deepcopy(params)))
        if self.on_read: self.on_read(method, params)
        if method == "thread/backgroundTerminals/list":
            if isinstance(self.tracker, Exception): raise self.tracker
            return copy.deepcopy(self.tracker)
        return self.f.native(method, params)

    def plan(self): return cleanup.plan(self.registry, self.ledger, self.wake, self.controls)

    def collect(self, request=None):
        return cleanup.collect(self.registry, self.ledger, self.wake, self.controls,
                               self.plan() if request is None else request)

    def test_plan_is_inert_and_collection_preserves_originals_usage_and_db(self):
        with contextlib.closing(self.ledger.connect()) as db: before = list(db.iterdump())
        request = self.plan()
        self.assertFalse(self.reads)
        result = self.collect(request)
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertEqual(result["qualification"]["historicalCleanup"], "unqualified")
        self.assertEqual(result["currentObservation"]["tracker"]["rows"], [])
        self.assertTrue(all(value is False for value in result["boundary"].values()))
        self.assertTrue(set(method for method,_ in self.reads) <= {
            "project/read", "thread/read", "thread/turns/list", "thread/items/list", "thread/backgroundTerminals/list"})
        with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(before, list(db.iterdump()))
        self.assertEqual(len(self.wake.sent), 1, "No new send beyond fixture's consumed recovery")

    def test_unloaded_thread_does_not_query_terminals_load_or_claim_empty(self):
        self.f.metadata.thread["status"]["type"] = "notLoaded"
        result = self.collect()
        self.assertEqual(result["currentObservation"]["tracker"]["coverage"], "unknown")
        self.assertIsNone(result["currentObservation"]["tracker"]["rows"])
        self.assertNotIn("thread/backgroundTerminals/list", [m for m,_ in self.reads])
        self.assertEqual(result["qualification"]["historicalCleanup"], "unqualified")

    def test_unavailable_tracker_is_unknown_not_empty_and_error_body_redacted(self):
        self.tracker = NativeReadFailure("rpc_error", "PRIVATE ERROR", -32600)
        result = self.collect()
        tracker = result["currentObservation"]["tracker"]
        self.assertIsNone(tracker["rows"])
        self.assertEqual(tracker["rpcCode"], -32600)
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_native_handle_is_never_interpreted_as_pid(self):
        self.f.turns[-1]["items"][0]["processId"] = "12345"
        row = self.collect()["qualification"]["effects"][0]
        self.assertEqual(row["nativeHandleHash"], digest("12345"))
        self.assertIsNone(row["osPidHash"])
        self.assertIn("effect_process_birth_identity", row["missingCleanupEvidence"])

    def test_pid_birth_descendants_and_supplied_clean_flags_cannot_qualify_source(self):
        item = self.f.turns[-1]["items"][0]
        item.update(osPid=12345, processStartTime=1, completedAt=2, parentProcessId=1,
                    descendants=[], descendantCoverage="complete", cleanupVerified=True)
        row = self.collect()["qualification"]
        self.assertFalse(row["completeProcessLifecycleSource"])
        self.assertFalse(row["completeDescendantCleanupSource"])
        self.assertEqual(row["historicalCleanup"], "unqualified")

    def test_running_current_terminal_is_retained_not_killed_or_settled(self):
        self.tracker = {"data": [{"itemId":"call-1", "processId":"native-handle", "osPid":None,
                                  "command":"PRIVATE COMMAND", "cwd":"PRIVATE CWD"}], "nextCursor":None}
        result = self.collect()
        self.assertEqual(result["qualification"]["effects"][0]["currentTrackedTerminal"], "running")
        self.assertFalse(result["boundary"]["ownershipReleased"])
        self.assertEqual([m for m,_ in self.reads].count("thread/backgroundTerminals/list"), 2)

    def test_changed_native_handle_reuses_item_but_cannot_be_correlated(self):
        self.tracker = {"data":[{"itemId":"call-1", "processId":"reused-handle", "osPid":123}], "nextCursor":None}
        with self.assertRaisesRegex(Refusal, "handle changed"): self.collect()

    def test_unknown_effect_and_missing_saved_result_requirements_are_preserved(self):
        self.f.turns[-1]["items"].append({"id":"compact", "type":"contextCompaction"})
        result = self.collect()
        report = result["historicalEvidence"]
        self.assertIn("unknown_effect:compact", report["gaps"])
        self.assertTrue(report["missingEvidence"])
        self.assertEqual(result["qualification"]["effects"][1]["historicalCleanup"], "unknown")

    def test_declined_native_command_does_not_grant_disposition_or_pilot(self):
        self.f.turns[-1]["items"][0].update(status="declined", exitCode=None)
        result = self.collect()
        self.assertEqual(result["qualification"]["historicalCleanup"], "not_required_non_execution")
        self.assertFalse(result["qualification"]["executedEffectDispositionAvailable"])
        self.assertFalse(result["boundary"]["pilotAccepted"])
        self.assertEqual(history.record.saved_state(self.ledger)["meta"]["standardRun"]["status"], "stopping")

    def test_context_changes_invalidate_plan_before_native_reads(self):
        request = self.plan()
        self.f.f.mutate(lambda meta:meta["standardRun"].update(usageHighWater=100000))
        with self.assertRaises(Refusal): self.collect(request)
        self.assertFalse(self.reads)

    def test_scope_and_extra_authority_fields_cannot_be_injected(self):
        for key,value in (("nativeLoad", True), ("version", True), ("brainId", "foreign")):
            request = self.plan(); request[key] = value
            with self.subTest(key=key), self.assertRaises(Refusal): self.collect(request)
        self.assertFalse(self.reads)

    def test_usage_expiry_controller_pause_and_host_races_refuse_report(self):
        for mutate in (lambda meta:meta["standardRun"].update(usageHighWater=1000),
                       lambda meta:meta["standardRun"].update(expiresAt=1),
                       lambda meta:meta.update(controller={"owner":"foreign"}),
                       lambda meta:meta.update(paused=False)):
            old = history.record.saved_state(self.ledger)["meta"]
            changed = []
            def during(method, params):
                if not changed:
                    changed.append(True); self.f.f.mutate(mutate)
            self.on_read = during
            with self.subTest(mutate=mutate), self.assertRaises(Refusal): self.collect()
            with self.ledger.tx() as db: self.ledger.put(db, "meta", 1, old)
        self.on_read = lambda *_:self.wake.binding["endpoint"].update(changed=True)
        with self.assertRaises(Refusal): self.collect()

    def test_metadata_and_tracker_drift_refuse(self):
        count = []
        def during(method, params):
            if method == "thread/backgroundTerminals/list":
                count.append(1)
                if len(count) == 2:
                    self.tracker = {"data":[{"itemId":"new", "processId":"new"}], "nextCursor":None}
        self.on_read = during
        with self.assertRaisesRegex(Refusal, "changed during collection"): self.collect()

    def test_later_turn_active_thread_and_missing_project_refuse(self):
        self.f.metadata.page["data"][0]["id"] = "later-turn"
        with self.assertRaises(Refusal): self.collect()
        self.f.metadata.page["data"][0]["id"] = "recovery-turn"
        self.f.metadata.thread["status"]["type"] = "active"
        with self.assertRaises(Refusal): self.collect()
        self.f.metadata.thread["status"]["type"] = "idle"
        self.f.metadata.thread["projectId"] = None
        with self.assertRaises(Refusal): self.collect()

    def test_reports_are_bounded_and_never_truncated(self):
        with patch.object(cleanup, "MAX_REPORT_BYTES", 100), self.assertRaisesRegex(Refusal, "report bound"):
            self.collect()

    def test_cli_plan_and_collect_use_same_exact_read_scope_without_controller(self):
        from orchestrator.cli import main
        path = self.ledger.root / "cleanup-plan.json"
        base = ["orchestrator", "--platform", str(self.registry.root), "--workspace", self.ledger.workspace_id]
        with patch("orchestrator.app_server_wake.load_binding", return_value=self.wake.binding):
            output = io.StringIO()
            with patch.object(sys, "argv", base + ["historical-cleanup-plan", "ignored-binding"]), contextlib.redirect_stdout(output):
                main()
            self.assertFalse(self.reads)
            path.write_text(output.getvalue()); path.chmod(0o600)
            output = io.StringIO()
            with patch.object(sys, "argv", base + ["historical-cleanup-collect", "ignored-binding", str(path)]), contextlib.redirect_stdout(output):
                main()
            self.assertEqual(json.loads(output.getvalue())["qualification"]["historicalCleanup"], "unqualified")

    def test_cli_requires_explicit_workspace_before_any_binding_read(self):
        from orchestrator.cli import main
        with patch("orchestrator.app_server_wake.load_binding", side_effect=AssertionError("Do not read binding")), \
             patch.object(sys, "argv", ["orchestrator", "historical-cleanup-plan", "unreviewed"]), self.assertRaises(Refusal):
            main()

    def test_every_native_mutation_and_foreign_read_is_refused_before_transport(self):
        scope = self.f.f.scope()
        proxy = cleanup.CleanupProxy(self.wake.binding["endpoint"], scope)
        for method,params in (("thread/resume", {}), ("turn/start", {}), ("turn/interrupt", {}),
                              ("process/spawn", {}), ("thread/backgroundTerminals/clean", {}),
                              ("thread/backgroundTerminals/terminate", {}), ("thread/list", {}),
                              ("thread/read", {"threadId":"foreign", "includeTurns":False}),
                              ("thread/items/list", {"threadId":self.f.brain, "turnId":"unseen"}),
                              ("thread/backgroundTerminals/list", {"threadId":self.f.brain, "cursor":"unseen", "limit":64})):
            with self.subTest(method=method), self.assertRaises(Refusal): proxy._rpc(method, params)
        self.assertFalse(self.reads)


class TerminalPaginationTest(unittest.TestCase):
    def proxy(self, pages):
        class Proxy:
            terminal_cursor = None
            def _rpc(self, method, params):
                value = pages.pop(0)
                if isinstance(value, Exception): raise value
                return value
        return Proxy()

    def row(self, ident): return {"itemId":ident, "processId":ident, "osPid":None}

    def test_complete_pages_keep_every_identity(self):
        rows = cleanup.terminals(self.proxy([{"data":[self.row("a")],"nextCursor":"b"},
                                             {"data":[self.row("b")],"nextCursor":None}]), "brain")
        self.assertEqual([row["itemId"] for row in rows], ["a", "b"])

    def test_truncated_repeated_empty_and_duplicate_pages_refuse(self):
        bad = ([{"data":[]}], [{"data":[],"nextCursor":"next"}],
               [{"data":[self.row("a"),self.row("a")],"nextCursor":None}],
               [{"data":[self.row("a")],"nextCursor":"same"},
                {"data":[self.row("b")],"nextCursor":"same"}])
        for pages in bad:
            with self.subTest(pages=pages), self.assertRaises(Refusal): cleanup.terminals(self.proxy(pages), "brain")

    def test_interrupted_partial_inventory_is_not_discarded(self):
        pages = [{"data":[self.row("a")],"nextCursor":"next"}, NativeReadFailure("rpc_error", "PRIVATE", -32600)]
        with self.assertRaisesRegex(Refusal, "cannot be discarded"): cleanup.terminals(self.proxy(pages), "brain")

    def test_bool_pid_and_native_numeric_handle_are_not_os_identity(self):
        for fields in ({"osPid":True}, {"osPid":0}, {"processId":123}):
            row = self.row("a"); row.update(fields)
            with self.subTest(fields=fields), self.assertRaises(Refusal):
                cleanup.terminals(self.proxy([{"data":[row],"nextCursor":None}]), "brain")

    def test_page_bound_remains_unknown_without_truncation(self):
        pages = [{"data":[self.row(str(i))], "nextCursor":str(i)} for i in range(9)]
        with self.assertRaisesRegex(Refusal, "page bound"): cleanup.terminals(self.proxy(pages), "brain")


class PrivateRequestTest(unittest.TestCase):
    def test_private_finite_unique_json_no_symlinks_hardlinks_or_oversize(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root).resolve() / "plan.json"
            path.write_text('{"version":1}'); path.chmod(0o600)
            self.assertEqual(cleanup.read_request(path), {"version":1})
            for text in ('{"version":1,"version":2}', '{"v":NaN}', ' ' * 16001):
                path.write_text(text)
                with self.subTest(text=text[:40]), self.assertRaises(Refusal): cleanup.read_request(path)
            path.write_text('{}'); path.chmod(0o644)
            with self.assertRaises(Refusal): cleanup.read_request(path)
            path.chmod(0o600)
            link = Path(root) / "link.json"; link.symlink_to(path)
            with self.assertRaises(Refusal): cleanup.read_request(link)
            hard = Path(root) / "hard.json"; hard.hardlink_to(path)
            with self.assertRaises(Refusal): cleanup.read_request(path)


class MultiHostCleanupTest(unittest.TestCase):
    def setUp(self):
        self.m = multi_fixture.MultiHostHistoryTest(); self.m.setUp()
        self.f = self.m.f
        self.f.turns[-1]["items"][0].update(status="completed", exitCode=0, processId="original-handle")
        self.patches = [patch.object(ReadProxy, "_rpc", lambda proxy,method,params:self.f.native(method,params)),
                        patch.object(cleanup.CleanupProxy, "__enter__", lambda p:p),
                        patch.object(cleanup.CleanupProxy, "__exit__", lambda *a:None),
                        patch.object(cleanup, "validate_endpoint")]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.m.tearDown()

    def collect(self):
        args = (self.f.registry, self.f.ledger, self.f.host, self.m.controls)
        return cleanup.collect(*args, cleanup.plan(*args))

    def test_replacement_empty_tracker_never_proves_original_cleanup_or_backfills_observer(self):
        before = history.record.saved_state(self.f.ledger)
        result = self.collect()
        self.assertEqual(result["currentObservation"]["tracker"]["rows"], [])
        self.assertEqual(result["qualification"]["historicalCleanup"], "unqualified")
        self.assertIn("original_host_cleanup_provenance", result["qualification"]["effects"][0]["missingCleanupEvidence"])
        self.assertEqual(history.record.saved_state(self.f.ledger), before)
        play = next(c for c in before["commands"] if c["kind"] == "standard_play")
        self.assertEqual(play["notification"]["nativeThreadObservation"]["streamStatus"], "unconfirmed")

    def test_retired_pid_reuse_or_missing_chain_refuses_before_native_connection(self):
        self.m.absent_mock.return_value = False
        self.f.metadata.calls.clear()
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse(self.f.metadata.calls)
        self.m.absent_mock.return_value = True
        self.m.controls.host_chain = None
        with self.assertRaises(Refusal): self.collect()
        self.assertFalse(self.f.metadata.calls)

    def test_changed_historical_launch_provenance_refuses_after_io(self):
        old = self.f.native
        def during(method, params):
            result = old(method, params)
            Path(self.m.chain["hosts"][0]["launch"]["process"]["path"]).write_text('{}')
            return result
        self.f.native = during
        with self.assertRaises(Refusal): self.collect()
