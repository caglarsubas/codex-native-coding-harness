import copy
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from orchestrator.core import Ledger, Refusal
from orchestrator.observations import artifact
from orchestrator.readiness import collect, diagnose, inspect_repository, native_observation
from orchestrator.rehearsal import run
import test_core


class ReadinessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "repo"; self.repo.mkdir()
        def git(*args):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)
        git("init", "-b", "main")
        git("config", "user.name", "Fixture"); git("config", "user.email", "fixture@example.invalid")
        (self.repo / "AGENTS.md").write_text("Fixture only")
        git("add", "AGENTS.md"); git("commit", "-m", "Fixture")
        self.ledger = Ledger(self.root / "state")
        self.mapping = {"id": "a", "path": str(self.repo), "projectId": "native-a", "ref": "HEAD", "policyProfile": "standard", "mergePolicy": "manual"}
        self.ledger.initialize({"schemaVersion": 1, "brainId": "brain", "repositories": [self.mapping]})

    def tearDown(self):
        self.tmp.cleanup()

    def native(self):
        return {"schemaVersion": 1, "observedAt": time.time(), "brain": {"id": "brain", "status": "idle"}, "projects": [
            {"projectId": "native-a", "path": str(self.repo), "hostId": "local", "isGitRepository": True},
            {"projectId": "unrelated-private", "path": str(self.root / "unrelated"), "hostId": "local", "isGitRepository": True}]}

    def test_local_metadata_and_native_inventory_are_separate_not_authorization(self):
        before = self.ledger.snapshot()
        collect(self.ledger)
        missing = diagnose(self.ledger)
        self.assertFalse(missing["repositories"][0]["mappingObserved"])
        native_observation(self.ledger, self.native())
        result = diagnose(self.ledger)
        self.assertEqual(result["status"], "parked")
        self.assertTrue(result["repositories"][0]["registrationReady"])
        self.assertFalse(result["launchAuthorized"])
        self.assertIn("No repository workflow", result["repositories"][0]["ciNote"])
        self.assertIn("before each new worktree", result["repositories"][0]["setupReview"])
        after = self.ledger.snapshot()
        self.assertNotIn("unrelated-private", json.dumps(after))
        for key in ("meta", "queue", "workers", "commands", "events"):
            self.assertEqual(before[key], after[key])

    def test_missing_nested_and_bad_ref_checkouts_never_ready(self):
        for changes in ({"path": None}, {"path": str(self.root / "missing")}, {"ref": "missing-ref"}):
            self.assertEqual(inspect_repository({**self.mapping, **changes})["status"], "unavailable")
        nested = self.repo / "nested"; nested.mkdir()
        self.assertEqual(inspect_repository({**self.mapping, "path": str(nested)})["status"], "unavailable")

    def test_native_import_requires_exact_identity_current_time_and_unique_ids(self):
        variants = []
        for at in (time.time() + 60, time.time() - 301, float("nan")):
            record = self.native(); record["observedAt"] = at; variants.append(record)
        record = self.native(); record["brain"]["id"] = "wrong-brain"; variants.append(record)
        record = self.native(); record["projects"].append(record["projects"][0]); variants.append(record)
        record = self.native(); record["projects"][0]["shell"] = "id"; variants.append(record)
        for record in variants: self.assertRaises(Refusal, native_observation, self.ledger, record)

    def test_stale_and_mismatched_native_projects_fail_closed(self):
        collect(self.ledger); record = self.native()
        native_observation(self.ledger, record)
        with patch("orchestrator.readiness.time.time", return_value=record["observedAt"] + 901):
            result = diagnose(self.ledger)
            self.assertFalse(result["nativeFresh"])
            self.assertFalse(result["repositories"][0]["mappingObserved"])
            self.assertEqual(result["brainObservedStatus"], "unknown")
        for changes in ({"hostId": "other-host"}, {"isGitRepository": False}, {"projectId": "different-project"}):
            record = self.native(); record["projects"][0].update(changes)
            native_observation(self.ledger, record)
            self.assertFalse(diagnose(self.ledger)["repositories"][0]["mappingObserved"])

    def test_candidate_does_not_silently_change_configuration(self):
        self.mapping["projectId"] = None
        self.ledger.initialize({"schemaVersion": 1, "brainId": "brain", "repositories": [self.mapping]})
        collect(self.ledger); native_observation(self.ledger, self.native())
        row = diagnose(self.ledger)["repositories"][0]
        self.assertEqual(row["candidateProjectId"], "native-a")
        self.assertFalse(row["registrationReady"])
        self.assertIsNone(self.ledger.snapshot()["repositories"][0]["projectId"])

    def test_config_change_invalidates_recorded_local_metadata(self):
        collect(self.ledger); native_observation(self.ledger, self.native())
        self.mapping["ref"] = "main"
        self.ledger.initialize({"schemaVersion": 1, "brainId": "brain", "repositories": [self.mapping]})
        row = diagnose(self.ledger)["repositories"][0]
        self.assertIsNone(row["commit"])
        self.assertFalse(row["registrationReady"])

    def test_setup_files_are_never_executed_or_approved(self):
        environment = self.repo / ".codex" / "environments"; environment.mkdir(parents=True)
        (environment / "environment.toml").write_text('setup = "touch SHOULD_NOT_EXIST"')
        (self.repo / ".worktreeinclude").write_text(".env\n")
        row = inspect_repository(self.mapping)
        self.assertTrue(row["worktreeIncludePresent"])
        self.assertTrue(row["localEnvironmentPresent"])
        self.assertEqual(row["setupReview"], "not_verified")
        self.assertFalse((self.repo / "SHOULD_NOT_EXIST").exists())

    def test_rehearsal_is_isolated_and_cannot_certify_live_pilot(self):
        before = self.ledger.snapshot()
        result = run(self.ledger)
        self.assertTrue(result["synthetic"])
        self.assertEqual(result["nativeCalls"], 0)
        self.assertFalse(result["realPilotAccepted"])
        self.assertEqual(len(result["steps"]), 7)
        after = self.ledger.snapshot()
        for key in ("meta", "queue", "workers", "commands", "events"):
            self.assertEqual(before[key], after[key])
        saved = json.loads(artifact(self.ledger, result["artifactId"])[1])
        self.assertTrue(saved["synthetic"])
        self.assertFalse(after["meta"]["pilotPassed"])


class GateReadinessTest(unittest.TestCase):
    setUp = test_core.LedgerTest.setUp
    tearDown = test_core.LedgerTest.tearDown
    command = test_core.LedgerTest.command
    ready = test_core.LedgerTest.ready
    resume = test_core.LedgerTest.resume
    running = test_core.LedgerTest.running
    finish = test_core.LedgerTest.finish
    completion = test_core.LedgerTest.completion
    def test_preview_matches_enforced_gate_and_is_read_only(self):
        q = self.ready(); self.resume()
        before = self.ledger.snapshot()
        packet = diagnose(self.ledger)["packets"][0]
        self.assertTrue(packet["ledgerEligible"])
        self.assertFalse(diagnose(self.ledger)["launchAuthorized"])
        self.assertEqual(before["meta"], self.ledger.snapshot()["meta"])
        self.command("hold", {"queueId": q["id"], "held": True})
        self.assertFalse(diagnose(self.ledger)["packets"][0]["ledgerEligible"])
        self.assertRaises(Refusal, self.ledger.reserve, self.token, q["id"])

    def test_mapping_change_invalidates_approval_and_preflight(self):
        for key, value in (("projectId", "project-new"), ("path", "/fixture/new"), ("ref", "main")):
            self.ledger.initialize(self.config)
            self.ready()
            updated = copy.deepcopy(self.config); updated["repositories"][0][key] = value
            self.ledger.initialize(updated)
            q = self.ledger.snapshot()["queue"][0]
            self.assertEqual(q["status"], "proposed")
            self.assertIsNone(q["approval"]); self.assertIsNone(q["preflight"])

    def test_active_mapping_cannot_be_replaced(self):
        self.running()
        updated = copy.deepcopy(self.config); updated["repositories"][0]["path"] = "/different"
        with self.assertRaisesRegex(Refusal, "owned by active"):
            self.ledger.initialize(updated)
        self.assertEqual(self.ledger.snapshot()["repositories"], self.config["repositories"])

    def test_unchanged_mapping_preserves_reviewed_approval(self):
        self.ready()
        before = self.ledger.snapshot()["queue"]
        self.ledger.initialize(self.config)
        self.assertEqual(self.ledger.snapshot()["queue"], before)

    def test_owned_and_complete_packets_are_not_new_launch_candidates(self):
        worker = self.running()
        preview = diagnose(self.ledger)["packets"][0]
        self.assertEqual(preview["status"], "dispatched")
        self.assertEqual([i["code"] for i in preview["issues"]], ["owned"])
        self.finish(worker)
        preview = diagnose(self.ledger)["packets"][0]
        self.assertEqual(preview["status"], "complete")
        self.assertFalse(preview["ledgerEligible"])
        self.assertEqual([i["code"] for i in preview["issues"]], ["complete"])

    def test_preview_accounts_for_capacity_and_repository_ownership(self):
        self.running()
        q = self.ready(packet="TEST-002")
        preview = next(p for p in diagnose(self.ledger)["packets"] if p["queueId"] == q["id"])
        self.assertFalse(preview["ledgerEligible"])
        self.assertTrue({"capacity", "repository_owned"} <= {i["code"] for i in preview["issues"]})
        self.assertRaises(Refusal, self.ledger.reserve, self.token, q["id"])

    def test_approval_packet_digest_and_future_preflight_are_checked(self):
        q = self.ready(); self.resume()
        with self.ledger.tx() as db:
            row = self.ledger.get(db, "queue", q["id"])
            row["approval"]["packetDigest"] = "f" * 64
            self.ledger.put(db, "queue", q["id"], row)
        self.assertRaises(Refusal, self.ledger.reserve, self.token, q["id"])
        self.assertIn("approval_binding", [i["code"] for i in diagnose(self.ledger)["packets"][0]["issues"]])
        with self.ledger.tx() as db:
            row = self.ledger.get(db, "queue", q["id"])
            row["approval"]["packetDigest"] = q["packetDigest"]
            row["preflight"]["at"] = time.time() + 100
            self.ledger.put(db, "queue", q["id"], row)
        self.assertRaises(Refusal, self.ledger.reserve, self.token, q["id"])
