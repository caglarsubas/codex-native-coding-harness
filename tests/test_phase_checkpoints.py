import contextlib
import copy
import io
import json
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from orchestrator import cli, missions, phase_checkpoints as phases, run_authority as runs
from orchestrator.core import Ledger, Refusal, canonical, digest
import test_missions
import test_run_authority
import test_result_review


class PhaseCheckpointTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_run_authority.RunAuthorityTest(); self.fx.setUp()
        self.ledger, self.token = self.fx.ledger, self.fx.token
        self.run = self.fx.authorize()
        self.checkpoint = self.fx.park({"commandId": self.fx.fx.command("brain_stop")["id"]})

    def tearDown(self): self.fx.tearDown()

    def request(self, **fields): return self.fx.request(**fields)

    def report_request(self):
        return self.request(runHash=self.run["runHash"], checkpointHash=self.checkpoint["documentHash"],
                            note="Recorded fixture only; not a phase-completion claim.")

    def prepare(self, request=None): return phases.prepare(self.ledger, self.token, request or self.report_request())

    def read(self, receipt):
        return phases.read(self.ledger, self.token, {k: receipt[k] for k in ("reportHash", "artifactId")})

    def review_request(self, report):
        auth = self.fx.auth_request(self.checkpoint["documentHash"])
        return self.request(reportHash=report["reportHash"], artifactId=report["artifactId"],
            **{k: auth[k] for k in ("missionHash", "reviewReceiptHash", "settingsPolicy", "expiresAt", "confirmed")})

    def reviewed(self):
        report = self.prepare(); request = self.review_request(report)
        receipt = phases.review(self.ledger, request, actor="dashboard_owner")
        return report, request, receipt

    def authorize_request(self, reviewed, receipt):
        return self.request(**{k: reviewed[k] for k in ("missionHash", "reviewReceiptHash", "settingsPolicy", "expiresAt", "confirmed")},
            checkpointHash=self.checkpoint["documentHash"], checkpointReviewHash=receipt["checkpointReviewHash"])

    def test_report_retains_goal_limits_unknown_usage_and_unfinished_tasks(self):
        before = self.ledger.snapshot(); receipt = self.prepare(); report = self.read(receipt)["report"]
        self.assertEqual(report["summary"]["declaredTasks"], 1)
        self.assertEqual(report["summary"]["unfinishedDeclaredTasks"], 1)
        self.assertEqual(report["summary"]["phaseAcceptance"], "not_established")
        self.assertIsNone(report["summary"]["measuredPhaseTokens"])
        self.assertEqual(report["limits"]["tokenBudget"], 100000)
        self.assertEqual(report["phase"], self.ledger.document(self.ledger.document(self.run["runHash"])["missionHash"])["spec"]["phase"])
        self.assertEqual(report["checkpointAt"], self.checkpoint["at"])
        self.assertFalse(receipt["executionAuthorized"])
        after = self.ledger.snapshot()
        for k in ("workers", "queue", "commands"): self.assertEqual(before[k], after[k])
        for k in ("paused", "brainControl", "runAuthority", "runner", "heartbeat"):
            self.assertEqual(before["meta"][k], after["meta"][k])
        self.assertFalse((self.fx.fx.registry.root / "admission.sqlite3").exists())

    def test_versioned_artifacts_and_read_only_historical_reads(self):
        first = self.prepare(); one = self.read(first); second = self.prepare()
        with contextlib.closing(self.ledger.connect()) as db:
            a, raw = phases.artifact_bytes(db, first["artifactId"])
            b, _ = phases.artifact_bytes(db, second["artifactId"])
        self.assertEqual(b["version"], a["version"]+1)
        self.assertEqual(a["key"], b["key"])
        self.assertIn(b"# Phase checkpoint report", raw)
        before = self.fx.fx.logical()
        self.assertEqual(self.read(first), one)
        self.assertEqual(before, self.fx.fx.logical())

    def test_report_prepare_replay_is_historical_after_resume(self):
        request = self.report_request(); receipt = self.prepare(request)
        self.fx.fx.command("brain_resume"); self.ledger.process(self.token)
        before = self.fx.fx.logical()
        self.assertEqual(self.prepare(request), receipt)
        self.assertEqual(before, self.fx.fx.logical())
        with self.assertRaisesRegex(Refusal, "parked"): self.prepare()

    def test_review_and_new_generation_do_not_resume_or_release_resources(self):
        before = self.ledger.snapshot(); report, request, receipt = self.reviewed()
        next_run = self.fx.authorize(self.authorize_request(request, receipt))
        self.assertEqual(next_run["generation"], 2)
        self.assertEqual(self.ledger.document(next_run["runHash"])["checkpointReviewHash"], receipt["checkpointReviewHash"])
        after = self.ledger.snapshot()
        self.assertEqual(before["meta"]["brainControl"], after["meta"]["brainControl"])
        self.assertTrue(after["meta"]["paused"])
        self.assertEqual(before["workers"], after["workers"])
        self.assertTrue(self.read(report)["historical"])

    def test_direct_release_without_review_refuses(self):
        with self.assertRaisesRegex(Refusal, "Phase checkpoint record"):
            self.fx.authorize(self.fx.auth_request(self.checkpoint["documentHash"]))

    def test_initial_grant_cannot_consume_checkpoint_review(self):
        fixture = test_run_authority.RunAuthorityTest(); fixture.setUp()
        try:
            with self.assertRaisesRegex(Refusal, "Initial run"):
                fixture.authorize({**fixture.auth_request(), "checkpointReviewHash": "a"*64})
        finally: fixture.tearDown()

    def test_owner_only_and_explicit_confirmation(self):
        request = self.review_request(self.prepare())
        with self.assertRaisesRegex(Refusal, "owner"):
            phases.review(self.ledger, request, actor="designated_brain")
        with self.assertRaisesRegex(Refusal, "confirmation"):
            phases.review(self.ledger, {**request, "confirmed": False}, actor="dashboard_owner")

    def test_brain_token_and_workspace_are_required(self):
        request = self.report_request()
        with self.assertRaises(Refusal): phases.prepare(self.ledger, "bad-token", request)
        report = self.prepare(request)
        with self.assertRaises(Refusal): phases.read(self.ledger, "bad-token", {k: report[k] for k in ("reportHash", "artifactId")})
        foreign = Ledger(self.ledger.root); foreign.workspace_id = "foreign"
        with self.assertRaises(Refusal): phases.prepare(foreign, self.token, self.report_request())

    def test_report_request_changed_id_content_refuses(self):
        request = self.report_request(); self.prepare(request)
        with self.assertRaisesRegex(Refusal, "reused"):
            self.prepare({**request, "note": "different"})

    def test_stale_revision_refuses_and_empty_note_is_invalid(self):
        request = self.report_request(); self.prepare()
        with self.assertRaisesRegex(Refusal, "Workspace changed"): self.prepare(request)
        with self.assertRaises(Refusal): self.prepare({**self.report_request(), "note": " "})

    def test_queue_drift_invalidates_report_and_review(self):
        report, request, receipt = self.reviewed()
        self.fx.fx.command("hold", {"queueId": self.fx.fx.q["id"], "held": True})
        with self.assertRaisesRegex(Refusal, "stale"):
            phases.review(self.ledger, self.review_request(report), actor="dashboard_owner")
        with self.assertRaisesRegex(Refusal, "stale"):
            self.fx.authorize(self.authorize_request(request, receipt))

    def test_new_report_supersedes_old_review_even_without_task_changes(self):
        _, request, receipt = self.reviewed(); self.prepare()
        with self.assertRaisesRegex(Refusal, "superseded"):
            self.fx.authorize(self.authorize_request(request, receipt))

    def test_missing_report_pointer_is_not_a_legacy_release(self):
        _, request, receipt = self.reviewed()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1); meta.pop("phaseCheckpointReport"); self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal): self.fx.authorize(self.authorize_request(request, receipt))

    def test_exact_settings_expiry_and_mission_must_match_review(self):
        _, request, receipt = self.reviewed()
        for key, value in (("expiresAt", request["expiresAt"]+1), ("missionHash", "a"*64),
                           ("reviewReceiptHash", "b"*64), ("settingsPolicy", "adaptive")):
            with self.assertRaises(Refusal): self.fx.authorize({**self.authorize_request(request, receipt), key: value})

    def test_expired_review_cannot_grant_run(self):
        _, request, receipt = self.reviewed()
        with patch("orchestrator.run_authority.time.time", return_value=request["expiresAt"]+1):
            with self.assertRaises(Refusal): self.fx.authorize(self.authorize_request(request, receipt))

    def test_review_replay_is_historical_and_cannot_restore_old_generation(self):
        report, request, receipt = self.reviewed(); auth = self.authorize_request(request, receipt)
        grant = self.fx.authorize(auth)
        self.fx.fx.command("brain_resume"); self.ledger.process(self.token)
        self.fx.stop(grant)
        before = self.fx.fx.logical()
        self.assertEqual(phases.review(self.ledger, request, actor="dashboard_owner"), receipt)
        self.assertEqual(self.fx.authorize(auth), grant)
        self.assertEqual(before, self.fx.fx.logical())
        self.assertEqual(self.fx.state()["status"], "fenced")
        self.assertEqual(self.read(report)["report"]["generation"], 1)

    def test_mission_change_needs_new_exact_owner_review(self):
        _, request, receipt = self.reviewed()
        current = missions.read(self.ledger); spec = copy.deepcopy(current["document"]["spec"])
        spec["phase"]["id"] = "phase-two"
        saved = missions.change(self.ledger, test_missions.request(revision=current["revision"], spec=spec))["current"]
        missions.change(self.ledger, test_missions.request("review", saved["revision"], documentHash=saved["documentHash"], confirmed=True))
        with self.assertRaises(Refusal): self.fx.authorize(self.authorize_request(request, receipt))

    def test_report_artifact_and_source_artifact_corruption_block(self):
        report, request, receipt = self.reviewed()
        for key in (report["artifactId"], self.checkpoint["artifactIds"][0]):
            with self.ledger.tx() as db:
                raw = db.execute("SELECT content FROM artifact_versions WHERE id=?", (key,)).fetchone()[0]
                db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"changed", key))
            with self.assertRaisesRegex(Refusal, "integrity"): self.read(report)
            with self.assertRaises(Refusal): self.fx.authorize(self.authorize_request(request, receipt))
            with self.ledger.tx() as db: db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (raw, key))

    def test_snapshot_and_receipt_tampering_block(self):
        report, request, receipt = self.reviewed()
        review = self.ledger.document(receipt["checkpointReviewHash"])
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (review["requestKey"],))
        with self.assertRaisesRegex(Refusal, "receipt missing"):
            self.fx.authorize(self.authorize_request(request, receipt))
        with self.ledger.tx() as db: db.execute("UPDATE snapshots SET data=? WHERE id=?", ('{}', report["reportHash"]))
        with self.assertRaises(Refusal): self.read(report)

    def test_report_receipt_is_required_even_for_historical_read(self):
        report = self.prepare(); data = self.read(report)["report"]
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (data["requestKey"],))
        with self.assertRaisesRegex(Refusal, "receipt missing"): self.read(report)

    def test_report_and_review_failures_roll_back_atomically(self):
        before = self.fx.fx.logical()
        with patch.object(self.ledger, "event", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): self.prepare()
        self.assertEqual(before, self.fx.fx.logical())
        report = self.prepare(); before = self.fx.fx.logical()
        with patch.object(self.ledger, "event", side_effect=RuntimeError("fixture crash")):
            with self.assertRaises(RuntimeError): phases.review(self.ledger, self.review_request(report), actor="dashboard_owner")
        self.assertEqual(before, self.fx.fx.logical())

    def test_concurrent_report_replay_has_one_artifact(self):
        request = self.report_request()
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(self.prepare, (request, request)))
        self.assertEqual(results[0], results[1])
        with contextlib.closing(self.ledger.connect()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (phases.REPORT,)).fetchone()[0], 1)

    def test_concurrent_distinct_reviews_have_one_winner(self):
        report = self.prepare(); one, two = self.review_request(report), self.review_request(report)
        def call(request):
            try: return phases.review(self.ledger, request, actor="dashboard_owner")
            except Refusal: return None
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(call, (one, two)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_prepare_never_observes_native_git_or_files(self):
        with patch("subprocess.run", side_effect=AssertionError("No subprocess")), patch.object(Path, "read_bytes", side_effect=AssertionError("No source reads")):
            self.read(self.prepare())

    def test_large_source_refuses_without_partial_report(self):
        with self.ledger.tx() as db:
            original = self.ledger.get(db, "queue", self.fx.fx.q["id"])
            for i in range(1000):
                q = {**original, "id": "overflow-"+str(i)}
                db.execute("INSERT INTO queue VALUES(?,?,?,?)", (q["id"], q["repository"], "overflow-"+str(i), canonical(q)))
        before = self.fx.fx.logical()
        with self.assertRaisesRegex(Refusal, "bound"): self.prepare()
        self.assertEqual(before, self.fx.fx.logical())

    def test_fresh_report_does_not_refresh_checkpoint_observation_time(self):
        with patch("orchestrator.phase_checkpoints.time.time", return_value=time.time()+600): report = self.prepare()
        data = self.read(report)["report"]
        self.assertEqual(data["checkpointAt"], self.checkpoint["at"])
        self.assertGreater(data["retainedAt"]-data["checkpointAt"], 599)

    def test_cli_prepare_read_scope_and_no_owner_release_route(self):
        registry = self.fx.fx.registry
        base = ["cli", "--platform", str(registry.root), "--workspace", "a"]
        path = registry.root / "phase-request.json"; path.write_text(canonical(self.report_request()))
        def call(operation):
            with patch.dict(os.environ, {"ORCHESTRATOR_CONTROLLER_TOKEN": self.token}), patch("sys.argv", base+[operation, str(path)]), contextlib.redirect_stdout(io.StringIO()) as out:
                cli.main()
            return json.loads(out.getvalue())
        report = call("phase-checkpoint-prepare")
        path.write_text(canonical({k: report[k] for k in ("reportHash", "artifactId")}))
        self.assertEqual(call("phase-checkpoint-read")["reportHash"], report["reportHash"])
        missing = registry.root / "must-not-exist"
        with patch("sys.argv", ["cli", "--state", str(missing), "phase-checkpoint-read", str(path)]):
            with self.assertRaises(Refusal): cli.main()
        self.assertFalse(missing.exists())
        for file in ("orchestrator/cli.py", "orchestrator/server.py", "orchestrator/assistant_actions.py"):
            source = Path(file).read_text()
            self.assertNotIn("phase-checkpoint-review", source)
            self.assertNotIn("phase-checkpoint-release", source)


class PhaseResultProjectionTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_result_review.ResultReviewTest(); self.fx.setUp()
        self.addCleanup(self.fx.tearDown)
        self.ledger = self.fx.ledger
        self.grant = self.ledger.document(self.fx.intent["runHash"])

    def rows(self):
        with contextlib.closing(self.ledger.connect()) as db:
            db.execute("BEGIN")
            return phases.task_rows(db, self.grant, phases.rows_in(self.ledger, db, "queue"), phases.rows_in(self.ledger, db, "workers"))[0]

    def test_accepted_result_keeps_axes_distinct_without_shared_accounting_write(self):
        self.fx.review(); shared = self.fx.store.snapshot(); before = self.fx.logical()
        row = self.rows()[0]["workers"][0]["review"]
        self.assertEqual(row["outcome"], "accepted")
        self.assertEqual(row["axes"]["source"], "verified")
        self.assertEqual(row["axes"]["runtime"], "unverified")
        self.assertEqual(shared, self.fx.store.snapshot()); self.assertEqual(before, self.fx.logical())

    def test_changes_required_not_promoted_and_tampered_proof_refuses(self):
        request = self.fx.evidence("changes_required"); self.fx.review(request)
        self.assertEqual(self.rows()[0]["workers"][0]["review"]["outcome"], "changes_required")
        with self.ledger.tx() as db:
            db.execute("UPDATE artifact_versions SET content=? WHERE id=?", (b"changed", request["reviewArtifactId"]))
        with self.assertRaises(Refusal): self.rows()

    def test_recorded_complete_without_review_stays_unreviewed(self):
        with self.ledger.tx() as db:
            worker = self.ledger.get(db, "workers", self.fx.wid); worker["status"] = "complete"
            self.ledger.put(db, "workers", self.fx.wid, worker)
        self.assertIsNone(self.rows()[0]["workers"][0]["review"])


if __name__ == "__main__": unittest.main()
