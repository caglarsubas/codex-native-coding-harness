import contextlib
import io
import json
import time
import unittest
from unittest.mock import patch

from orchestrator import run_readiness
from orchestrator.core import Ledger, Refusal, PREFLIGHT_CHECKS, canonical, digest
from orchestrator.workspaces import fingerprint
import test_core
import test_missions
import test_reconciliation


class RunReadinessTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_missions.MissionTest(); self.fx.setUp()
        self.ledger, self.registry = self.fx.ledger, self.fx.registry

    def tearDown(self): self.fx.tearDown()

    def review(self, mode="exact_owner"):
        spec = test_missions.specification(mode=mode)
        spec["phase"]["scope"][0]["allowedPaths"] = ["src/**", "tests/test_fixture.py"]
        return self.fx.review(self.fx.save(spec))

    def inspect(self): return run_readiness.inspect(self.registry, self.ledger)

    def checks(self, report): return {c["code"]: c for c in report["checks"]}

    def test_empty_workspace_has_actionable_setup_and_implementation_not_authority(self):
        report = self.inspect(); checks = self.checks(report)
        self.assertEqual(checks["mission_binding"]["status"], "blocked")
        self.assertEqual(checks["owner_review"]["view"], "mission")
        self.assertEqual(checks["run_activation"]["owner"], "platform_development")
        self.assertFalse(report["activationAvailable"]); self.assertFalse(report["executionAuthorized"])
        self.assertIsNone(report["candidateHash"])
        self.assertEqual(report["reportHash"], digest({k: v for k, v in report.items() if k != "reportHash"}))

    def test_reviewed_mission_has_exact_diagnostic_binding_and_limits(self):
        mission = self.review(); report = self.inspect()
        self.assertEqual(report["candidate"]["missionHash"], mission["documentHash"])
        self.assertEqual(report["candidate"]["reviewReceiptHash"], mission["receiptHash"])
        self.assertEqual(report["candidate"]["phaseId"], "phase-one")
        self.assertEqual(report["candidateHash"], digest(report["candidate"]))
        self.assertEqual(report["mission"]["limits"]["tokenBudget"], 100000)
        self.assertEqual(self.checks(report)["owner_review"]["status"], "satisfied")
        self.assertFalse(report["executionAuthorized"])

    def test_inspection_does_not_change_ledger_registry_or_create_admission(self):
        self.review()
        with contextlib.closing(self.ledger.connect()) as db: before = fingerprint(db)
        with self.registry.tx() as db: platform_before = fingerprint(db)
        report = self.inspect(); again = self.inspect()
        self.assertEqual(report["candidateHash"], again["candidateHash"])
        with contextlib.closing(self.ledger.connect()) as db: self.assertEqual(fingerprint(db), before)
        with self.registry.tx() as db: self.assertEqual(fingerprint(db), platform_before)
        self.assertFalse((self.registry.root / "admission.sqlite3").exists())

    def test_draft_revoked_and_changed_review_are_not_valid_candidates(self):
        draft = self.fx.save(); self.assertIsNone(self.inspect()["candidate"])
        reviewed = self.fx.review(draft); self.fx.review(reviewed, "revoke")
        self.assertIsNone(self.inspect()["candidate"])
        self.fx.save(revision=3)
        self.assertIsNone(self.inspect()["candidate"])

    def test_mapping_and_policy_drift_blocks_binding(self):
        self.review()
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "a"); repo["projectId"] = None
            self.ledger.put(db, "repos", "a", repo)
        self.assertIsNone(self.inspect()["candidate"])
        self.assertEqual(self.checks(self.inspect())["mission_binding"]["status"], "blocked")

    def test_corrupted_mission_or_review_hash_never_creates_candidate(self):
        m = self.review()
        for key in (m["documentHash"], m["receiptHash"]):
            with self.ledger.tx() as db:
                original = self.ledger.get(db, "snapshots", key); changed = {**original, "unexpected": True}
                db.execute("UPDATE snapshots SET data=? WHERE id=?", (canonical(changed), key))
            self.assertIsNone(self.inspect()["candidate"])
            with self.ledger.tx() as db: db.execute("UPDATE snapshots SET data=? WHERE id=?", (canonical(original), key))

    def test_prepare_only_and_owned_controller_and_pause_have_distinct_blockers(self):
        self.review("prepare_only")
        self.ledger.acquire("brain-a:fixture")
        self.ledger.submit({"id": "pause-fixture", "kind": "brain_stop", "payload": {}, "expectedRevision": self.ledger.snapshot()["meta"]["revision"]})
        checks = self.checks(self.inspect())
        for code in ("execution_mode", "controller_idle", "pause_checkpoint"): self.assertEqual(checks[code]["status"], "blocked")

    def test_conservative_path_containment(self):
        yes = [("src/a.py", ["src/**"]), ("src/feature/*.py", ["src/**"]),
               ("src/feature/*.py", ["src/feature/*.py"]), ("tests/a.py", ["tests/?.py"])]
        no = [("src-evil/a", ["src/**"]), ("src/**", ["src/feature/**"]),
              ("src/a?.py", ["src/*.py"]), ("src/../escape", ["src/**"]),
              ("src//a.py", ["src/**"]), ("src/./a.py", ["src/**"]),
              ("/absolute", ["**"]), ("src\\a.py", ["src/**"]), ("src", ["src/**"])]
        for path, scopes in yes: self.assertTrue(run_readiness.contained_path(path, scopes), path)
        for path, scopes in no: self.assertFalse(run_readiness.contained_path(path, scopes), path)

    def test_packet_scope_separate_from_legacy_eligibility_and_authority(self):
        self.review(); q = self.ledger.prepare(test_core.seed(profile="standard"))
        result = self.inspect()["packets"][0]
        self.assertEqual(result["pathScope"], "contained"); self.assertEqual(result["legacyEligibility"], "blocked")
        self.ledger.submit({"id": "approve-fixture", "kind": "approve", "payload": {k: q[k] for k in ("seedHash", "packetDigest")} | {"queueId": q["id"]}, "expectedRevision": self.ledger.snapshot()["meta"]["revision"]})
        token = self.ledger.acquire("brain-a:fixture")
        self.ledger.preflight(token, q["id"], {"seedHash": q["seedHash"], "packetDigest": q["packetDigest"], "baseSHA": "c"*40,
            "projectId": "project-a", "checks": {k: True for k in PREFLIGHT_CHECKS}, "evidence": ["fixture"]})
        packet = self.inspect()["packets"][0]
        self.assertEqual(packet["legacyEligibility"], "recorded_checks_satisfied")
        self.assertEqual(packet["issues"][-1]["code"], "operation_contract_missing")
        self.assertFalse(packet["executionAuthorized"])

    def test_out_of_phase_and_ambiguous_packet_paths_are_not_proven(self):
        self.review()
        for i, path in enumerate(("other/a.py", "src//a.py", "**")):
            seed = test_core.seed(profile="standard", packet="TEST-"+str(i)); seed["allowedPaths"] = [path]
            self.ledger.prepare(seed)
        self.assertTrue(all(p["pathScope"] == "not_proven" for p in self.inspect()["packets"]))

    def test_seed_hash_and_packet_binding_are_checked(self):
        self.review(); q = self.ledger.prepare(test_core.seed(profile="standard"))
        with self.ledger.tx() as db:
            seed = self.ledger.get(db, "snapshots", q["seedHash"]); seed["allowedPaths"] = ["src/other"]
            db.execute("UPDATE snapshots SET data=? WHERE id=?", (canonical(seed), q["seedHash"]))
        packet = self.inspect()["packets"][0]
        self.assertEqual(packet["pathScope"], "not_assessed"); self.assertEqual(packet["issues"][0]["code"], "seed_integrity")

    def test_oversized_seed_is_not_read_into_report(self):
        self.review(); q = self.ledger.prepare(test_core.seed(profile="standard"))
        with self.ledger.tx() as db: db.execute("UPDATE snapshots SET data=? WHERE id=?", ('"'+ 'x'*512001+'"', q["seedHash"]))
        self.assertEqual(self.inspect()["packets"][0]["pathScope"], "not_assessed")

    def test_packet_count_and_report_body_are_bounded(self):
        self.review()
        for i in range(101): self.ledger.prepare(test_core.seed(profile="standard", packet="TEST-"+str(i)))
        result = self.inspect()
        self.assertEqual(result["coverage"], {"candidatePackets": 101, "inspectedPackets": 100, "omittedPackets": 1})
        self.assertEqual(self.checks(result)["packet_coverage"]["status"], "blocked")

    def test_platform_errors_are_redacted_and_do_not_erase_implementation_blockers(self):
        self.review()
        with patch.object(run_readiness.reconciliation, "status", side_effect=OSError("private /Users/secret/token")):
            result = self.inspect()
        self.assertNotIn("/Users/", canonical(result))
        self.assertEqual(result["platformEvidence"]["issueCounts"], {"platform_source_unavailable": 1})
        self.assertFalse(result["activationAvailable"])

    def test_consistent_supplied_platform_evidence_still_is_not_execution(self):
        self.review()
        platform = {"sourceMatchesReview": True, "version": 3, "baselineRecordHash": "a"*64,
            "receipt": {"recordHash": "b"*64}, "currentEvaluation": {"status": "consistent", "evidenceConsistent": True, "issues": [], "validUntil": time.time()+60}}
        with patch.object(run_readiness.reconciliation, "status", return_value=platform): result = self.inspect()
        self.assertEqual(self.checks(result)["platform_baseline"]["status"], "satisfied")
        self.assertFalse(result["executionAuthorized"]); self.assertFalse(result["activationAvailable"])
        self.assertEqual(len([c for c in result["checks"] if c["group"] == "implementation"]), 5)

    def test_stale_platform_and_foreign_workspace_details_are_not_exposed(self):
        self.review()
        platform = {"sourceMatchesReview": False, "baselineRecordHash": "a"*64,
            "currentEvaluation": {"status": "needs_evidence", "evidenceConsistent": False,
              "issues": [{"code": "task_stale", "workspaceId": "secret-workspace", "threadId": "secret-task"}]}}
        with patch.object(run_readiness.reconciliation, "status", return_value=platform): result = self.inspect()
        self.assertEqual(self.checks(result)["platform_baseline"]["status"], "blocked")
        self.assertNotIn("secret-", canonical(result))

    def test_state_change_during_inspection_discards_candidate(self):
        self.review()
        def change(registry):
            with self.ledger.tx() as db:
                meta = self.ledger.get(db, "meta", 1); meta["revision"] += 1; self.ledger.put(db, "meta", 1, meta)
            return {}
        with patch.object(run_readiness.reconciliation, "status", side_effect=change): result = self.inspect()
        self.assertIsNone(result["candidate"]); self.assertIn("workspace_changed", self.checks(result))

    def test_other_workspace_does_not_inherit_mission_or_packet(self):
        self.review(); self.ledger.prepare(test_core.seed(profile="standard"))
        other = Ledger(self.fx.root / "other"); other.initialize({"schemaVersion": 1, "brainId": "brain-other", "repositories": []})
        self.registry.register("other", "Other", other.root)
        result = run_readiness.inspect(self.registry, self.registry.ledger("other"))
        self.assertIsNone(result["candidate"]); self.assertEqual(result["packets"], [])
        self.assertNotIn("brain-a", canonical(result))

    def test_report_has_no_paths_transcripts_or_controller_token(self):
        self.review(); token = self.ledger.acquire("brain-a:fixture")
        report = canonical(self.inspect())
        self.assertNotIn(token, report); self.assertNotIn("/fixture/", report); self.assertNotIn(str(self.fx.root), report)

    def test_cli_requires_workspace_before_creating_state(self):
        from orchestrator.cli import main
        missing = self.fx.root / "must-not-be-created"
        with patch("sys.argv", ["orchestrator", "--state", str(missing), "run-readiness"]), self.assertRaises(Refusal): main()
        self.assertFalse(missing.exists())
        out = io.StringIO()
        with patch("sys.argv", ["orchestrator", "--platform", str(self.registry.root), "--workspace", "a", "run-readiness"]), contextlib.redirect_stdout(out): main()
        self.assertEqual(json.loads(out.getvalue())["workspaceId"], "a")

    def test_assistant_summary_is_explicitly_historical_and_bounded(self):
        result = run_readiness.assistant_summary(self.inspect())
        self.assertEqual(result["status"], "historical_inspection"); self.assertFalse(result["executionAuthorized"])
        self.assertLessEqual(len(result["blockers"]), 16)
        self.assertNotIn("candidateHash", result); self.assertNotIn("mission", result)

    def test_corrupt_source_error_is_bounded_and_contains_no_private_payload(self):
        with patch.object(run_readiness, "selected_source", side_effect=KeyError("private /Users/secret")):
            with self.assertRaises(Refusal) as failure: self.inspect()
        self.assertNotIn("/Users/", str(failure.exception))

    def test_expired_platform_validity_cannot_pass_even_if_record_was_consistent(self):
        self.review()
        platform = {"sourceMatchesReview": True, "baselineRecordHash": "a"*64,
            "currentEvaluation": {"status": "consistent", "evidenceConsistent": True, "issues": [], "validUntil": time.time()-1}}
        with patch.object(run_readiness.reconciliation, "status", return_value=platform): result = self.inspect()
        self.assertEqual(self.checks(result)["platform_baseline"]["status"], "blocked")

    def test_foreign_registry_refused_before_platform_inspection(self):
        from orchestrator.workspaces import Registry
        other = Registry(self.fx.root / "other-platform", create=True)
        with patch.object(run_readiness.reconciliation, "status") as status, self.assertRaises(Refusal):
            run_readiness.inspect(other, self.ledger)
        status.assert_not_called()

    def test_real_reconciliation_is_read_without_changing_quarantined_owners(self):
        fixture = test_reconciliation.ReconciliationTest(); fixture.setUp()
        try:
            reviewed = fixture.save(fixture.evidence())
            ledger = fixture.registry.ledger("alpha")
            before = fixture.fx.store().snapshot()
            result = run_readiness.inspect(fixture.registry, ledger)
            self.assertEqual(result["platformEvidence"]["reviewVersion"], reviewed["version"])
            self.assertEqual(fixture.fx.store().snapshot(), before)
            self.assertFalse(result["ownershipReleased"])
        finally: fixture.tearDown()
