import json
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import checkpoint_views as views, phase_checkpoints as phases
from orchestrator.core import Refusal
import test_phase_checkpoints
import test_server


class CheckpointViewsTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_phase_checkpoints.PhaseCheckpointTest(); self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.ledger = self.fx.ledger

    def inspect(self, receipt):
        return views.inspect(self.ledger, {k: receipt[k] for k in ("reportHash", "artifactId")})

    def test_empty_history_and_reads_never_initialize_shared_state(self):
        before = self.fx.fx.fx.logical()
        with patch("subprocess.run", side_effect=AssertionError("No native or Git calls")), patch.object(Path, "read_bytes", side_effect=AssertionError("No source reads")):
            result = views.history(self.ledger)
        self.assertEqual(result["status"], "empty")
        self.assertFalse(result["executionAuthorized"])
        self.assertEqual(before, self.fx.fx.fx.logical())
        self.assertFalse((self.fx.fx.fx.registry.root / "admission.sqlite3").exists())

    def test_history_is_creation_ordered_with_per_run_versions_and_no_bodies(self):
        with patch.object(phases.time, "time", return_value=time.time()):
            one = self.fx.prepare()
            request = self.fx.report_request(); request["note"] = "Second retained report at the same clock tick."
            two = self.fx.prepare(request)
        before = self.fx.fx.fx.logical()
        with patch.object(phases, "read_in", side_effect=AssertionError("No proof reads for metadata")):
            result = views.history(self.ledger)
        self.assertEqual([r["artifactId"] for r in result["reports"]], [one["artifactId"], two["artifactId"]])
        self.assertEqual([r["version"] for r in result["reports"]], [1, 2])
        self.assertTrue(result["latestAvailable"])
        self.assertNotIn("note", json.dumps(result)); self.assertNotIn("tasks", json.dumps(result))
        self.assertEqual(before, self.fx.fx.fx.logical())

    def test_intact_report_matches_local_context_but_not_acceptance_or_measured_usage(self):
        receipt = self.fx.prepare(); before = self.fx.fx.fx.logical()
        result = self.inspect(receipt)
        self.assertEqual(result["status"], "intact")
        self.assertEqual(result["contextStatus"], "matches_recorded_checkpoint")
        self.assertEqual(result["report"]["checkpointAt"], self.fx.checkpoint["at"])
        self.assertFalse(result["nativeCallMade"])
        summary = views.summary(result)
        self.assertIsNone(summary["measuredPhaseTokens"])
        self.assertEqual(summary["phaseAcceptance"], "not_established")
        self.assertEqual(summary["counts"]["unfinishedDeclaredTasks"], 1)
        self.assertEqual(before, self.fx.fx.fx.logical())

    def test_metadata_does_not_claim_proof_integrity_until_explicit_read(self):
        receipt = self.fx.prepare()
        with self.ledger.tx() as db:
            db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"changed", receipt["artifactId"]))
        self.assertEqual(views.history(self.ledger)["reports"][0]["status"], "not_inspected")
        result = self.inspect(receipt)
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("report", result)

    def test_missing_source_evidence_or_report_receipt_does_not_display_old_results(self):
        receipt = self.fx.prepare()
        with self.ledger.tx() as db:
            db.execute("DELETE FROM artifact_versions WHERE id=?", (self.fx.checkpoint["artifactIds"][0],))
        self.assertEqual(self.inspect(receipt)["status"], "unavailable")
        with self.ledger.tx() as db:
            db.execute("DELETE FROM snapshots WHERE id=?", (self.ledger.document(receipt["reportHash"])["requestKey"],))
        history = views.history(self.ledger)
        self.assertEqual(history["unavailable"], 1)
        self.assertFalse(history["latestAvailable"])
        self.assertEqual(history["reports"], [])

    def test_changed_superseded_and_unavailable_context_are_separate(self):
        first = self.fx.prepare()
        self.fx.fx.fx.command("hold", {"queueId": self.fx.fx.fx.q["id"], "held": True})
        self.assertEqual(self.inspect(first)["contextStatus"], "workspace_changed")
        second = self.fx.prepare()
        self.assertEqual(self.inspect(first)["contextStatus"], "superseded")
        self.assertEqual(self.inspect(second)["contextStatus"], "matches_recorded_checkpoint")
        self.fx.fx.fx.command("brain_resume"); self.ledger.process(self.fx.token)
        self.assertEqual(self.inspect(second)["contextStatus"], "checkpoint_unavailable")
        self.assertEqual(self.inspect(second)["status"], "intact")

    def test_swapped_artifact_or_foreign_report_cannot_return_content(self):
        one = self.fx.prepare(); two = self.fx.prepare()
        self.assertEqual(self.inspect({**one, "artifactId": two["artifactId"]})["status"], "unavailable")
        self.ledger.workspace_id = "foreign"
        self.assertEqual(self.inspect(one)["status"], "unavailable")
        self.assertEqual(views.history(self.ledger)["unavailable"], 2)

    def test_invalid_and_oversized_report_metadata_are_counted_not_rendered(self):
        receipt = self.fx.prepare()
        for value in ('{}', 'x'*256001):
            with self.ledger.tx() as db:
                db.execute("UPDATE snapshots SET data=? WHERE id=?", (value, receipt["reportHash"]))
            history = views.history(self.ledger)
            self.assertEqual(history["unavailable"], 1)
            self.assertEqual(history["reports"], [])
            self.assertEqual(self.inspect(receipt)["status"], "unavailable")

    def test_history_bound_refuses_partial_success(self):
        with self.ledger.tx() as db:
            for n in range(views.MAX_REPORTS+1):
                db.execute("INSERT INTO snapshots VALUES(?,?,?)", (f"{n:064x}", phases.REPORT, '{}'))
        result = views.history(self.ledger)
        self.assertEqual(result["status"], "history_limit")
        self.assertEqual(result["reports"], [])
        self.assertEqual(result["total"], views.MAX_REPORTS+1)

    def test_cached_summary_is_bounded_historical_and_excludes_sensitive_text(self):
        request = self.fx.report_request(); request["note"] = "PRIVATE-NOTE /private/path body"
        result = self.inspect(self.fx.prepare(request)); cached = views.summary(result)
        encoded = json.dumps(cached)
        for secret in ("PRIVATE-NOTE", "/private/path", result["reportHash"], result["artifactId"], "references", "source", "tasks"):
            self.assertNotIn(secret, encoded)
        with patch.object(views.time, "time", return_value=result["inspectedAt"]+61):
            summary = views.cached_summary(cached, result["workspaceRevision"]+1)
        self.assertTrue(summary["historical"]); self.assertTrue(summary["expired"]); self.assertTrue(summary["workspaceChanged"])
        self.assertEqual(views.cached_summary(None, 1)["status"], "not_inspected")
        with patch.object(views.time, "time", return_value=result["inspectedAt"]-1):
            self.assertTrue(views.cached_summary(cached, result["workspaceRevision"])["expired"])

    def test_closed_request_schema_and_digest_validation(self):
        for request in ({}, {"reportHash": "x", "artifactId": "y"}, {"reportHash": "a"*64, "artifactId": "b"*64, "confirmed": True}):
            with self.assertRaises(Refusal): views.inspect(self.ledger, request)

    def test_missing_latest_pointer_never_promotes_an_earlier_report(self):
        receipt = self.fx.prepare()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta.pop("phaseCheckpointReport")
            self.ledger.put(db, "meta", 1, meta)
        self.assertFalse(views.history(self.ledger)["latestAvailable"])
        self.assertEqual(self.inspect(receipt)["contextStatus"], "superseded")


class CheckpointHTTPTest(unittest.TestCase):
    request = test_server.ServerTest.request
    login = test_server.ServerTest.login

    def setUp(self):
        from orchestrator.core import Ledger
        from orchestrator.server import Dashboard
        self.fx = test_phase_checkpoints.PhaseCheckpointTest(); self.fx.setUp()
        self.receipt = self.fx.prepare(); self.registry = self.fx.fx.fx.registry
        other = Ledger(self.registry.root.parent / "second-ledger")
        other.initialize({"schemaVersion": 1, "brainId": "second-brain", "repositories": []})
        self.registry.register("second", "Second", other.root)
        self.server = Dashboard(self.fx.ledger, 0, self.registry.root / "missing.env", registry=self.registry)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.fx.tearDown()

    def test_real_http_detail_and_assistant_cache_are_workspace_isolated(self):
        auth = self.login()
        query = "?reportHash="+self.receipt["reportHash"]+"&artifactId="+self.receipt["artifactId"]
        before = self.fx.fx.fx.logical()
        status, _, raw = self.request("/api/workspaces/a/phase-checkpoints"+query, headers=auth)
        self.assertEqual(status, 200); result = json.loads(raw)
        self.assertEqual(result["contextStatus"], "matches_recorded_checkpoint")
        _, _, raw = self.request("/api/workspaces/second/phase-checkpoints"+query, headers=auth)
        self.assertEqual(json.loads(raw)["status"], "unavailable")
        self.assertNotIn(b"Fixture phase", raw)
        _, _, raw = self.request("/api/workspaces/a/assistant/context?view=phaseCheckpoints", headers=auth)
        context = json.loads(raw); summary = next(f["data"] for f in context["facts"] if f["id"] == "F33")
        self.assertEqual(summary["status"], "intact")
        self.assertNotIn(result["report"]["note"].encode(), raw)
        self.assertNotIn(self.receipt["reportHash"].encode(), raw)
        self.assertEqual(before, self.fx.fx.fx.logical())


if __name__ == "__main__": unittest.main()
