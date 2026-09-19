import contextlib
import copy
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from orchestrator import enrollment
from orchestrator.assistant import context
from orchestrator.assistant_actions import catalog
from orchestrator.core import AXES, Ledger, Refusal, digest
from orchestrator.decisions import inbox
from orchestrator.readiness import diagnose
from orchestrator.workspaces import Registry, fingerprint
from test_core import seed


def crash_after_durable_fence(root, request):
    original = enrollment.durable_fence
    def crash(path, binding):
        original(path, binding)
        os._exit(73)
    with patch.object(enrollment, "durable_fence", side_effect=crash):
        enrollment.apply(Registry(root), request)


class EnrollmentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.registry = Registry(self.root / "platform", create=True)
        self.alpha = self.make("alpha")
        self.beta = self.make("beta")
        self.registry.register("alpha", "Alpha", self.alpha.root)
        self.registry.register("beta", "Beta", self.beta.root)

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, wid):
        ledger = Ledger(self.root / wid)
        ledger.initialize({"schemaVersion": 1, "brainId": "brain-" + wid, "repositories": [
            {"id": "a", "path": "/fixture/" + wid, "projectId": "native-" + wid, "ref": "origin/main",
             "policyProfile": "standard", "mergePolicy": "manual"}]})
        return ledger

    def command(self, ledger, kind, payload=None):
        return ledger.submit({"id": str(uuid.uuid4()), "kind": kind,
                              "expectedRevision": ledger.snapshot()["meta"]["revision"], "payload": payload or {}})

    def prepare(self, ledger, packet="TEST-001"):
        token = ledger.acquire(ledger.snapshot()["meta"]["brainId"] + ":fixture")
        q = ledger.prepare(seed(profile="standard", packet=packet))
        self.command(ledger, "approve", {"queueId": q["id"], "seedHash": q["seedHash"], "packetDigest": q["packetDigest"]})
        ledger.preflight(token, q["id"], {"seedHash": q["seedHash"], "packetDigest": q["packetDigest"], "baseSHA": "c" * 40,
            "projectId": ledger.snapshot()["repositories"][0]["projectId"],
            "checks": {key: True for key in ("packetCurrent", "baseCurrent", "predecessorsVerified", "locksVerified",
                "noActiveDuplicate", "setupSafe", "policyReviewed", "runnerAvailable", "scopeApproved")}, "evidence": ["fixture"]})
        ledger.release(token, "Fixture preparation")
        return q

    def worker(self, ledger, state="running"):
        q = self.prepare(ledger)
        token = ledger.acquire(ledger.snapshot()["meta"]["brainId"] + ":fixture")
        self.command(ledger, "resume"); ledger.process(token)
        worker = ledger.reserve(token, q["id"])
        if state != "reserved":
            ledger.begin_creation(token, worker["id"])
        if state == "starting":
            ledger.bind(token, worker["id"], client_id="fixture-pending")
        elif state != "reserved":
            ledger.bind(token, worker["id"], thread_id="native-" + worker["id"])
            if state in ("awaiting_acceptance", "accepting"):
                ledger.transition(token, worker["id"], "awaiting_acceptance", "Fixture observed ready")
            if state == "accepting":
                ledger.runner(token, worker["id"], "acquire", "Fixture runner idle")
        self.command(ledger, "pause")
        ledger.release(token, "Fixture paused; owners retained")
        return worker

    def request(self):
        return {"id": "fixture-enrollment", "confirmed": True, "preview": enrollment.preview(self.registry)}

    def enroll(self):
        request = self.request()
        return enrollment.apply(self.registry, request)

    def contents(self, ledger):
        with contextlib.closing(ledger.connect()) as db:
            return fingerprint(db)

    def assert_fenced(self, ledger):
        self.assertTrue(ledger.snapshot()["admission"]["dispatchBlocked"])
        with self.assertRaisesRegex(Refusal, "enrollment fences"):
            self.command(ledger, "resume")

    def test_preview_is_read_only_exact_and_does_not_expose_paths_or_tokens(self):
        before = [self.contents(ledger) for ledger in (self.alpha, self.beta)]
        preview = enrollment.preview(self.registry)
        self.assertEqual(preview["documentHash"], digest(preview["document"]))
        self.assertEqual([self.contents(ledger) for ledger in (self.alpha, self.beta)], before)
        self.assertEqual(enrollment.status(self.registry)["state"], "not_enrolled")
        self.assertNotIn(str(self.root), json.dumps(preview))
        self.assertNotIn("/fixture/", json.dumps(preview))
        self.assertFalse((self.alpha.root / enrollment.FENCE_FILE).exists())
        token = self.alpha.acquire("brain-alpha:secret-test")
        self.assertNotIn(token, json.dumps(enrollment.preview(self.registry)))

    def test_explicit_enrollment_preserves_queue_workers_runner_and_limits(self):
        self.worker(self.alpha, "accepting"); self.worker(self.beta, "starting")
        before = {ledger.root.name: ledger.snapshot() for ledger in (self.alpha, self.beta)}
        record = self.enroll()
        self.assertEqual(record["state"], "fenced")
        self.assertFalse(record["activationAvailable"])
        self.assertFalse(record["executionAuthorized"])
        self.assertEqual(len(record["retainedOwnership"]), 3)
        for ledger in (self.alpha, self.beta):
            self.assert_fenced(ledger)
            after = ledger.snapshot()
            for key in ("queue", "workers"):
                self.assertEqual(before[ledger.root.name][key], after[key])
            for key in ("runner", "paused", "concurrency", "maximumConcurrency", "pilotPassed", "brainId", "heartbeat"):
                self.assertEqual(before[ledger.root.name]["meta"][key], after["meta"][key])
            self.assertEqual((ledger.root / enrollment.FENCE_FILE).stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.registry.root / "admission.sqlite3").exists())

    def test_paused_and_controller_release_are_required_not_inferred(self):
        token = self.alpha.acquire("brain-alpha:held")
        with self.assertRaisesRegex(Refusal, "release all controllers"): self.enroll()
        self.command(self.alpha, "resume"); self.alpha.process(token)
        self.alpha.release(token, "Not paused")
        with self.assertRaisesRegex(Refusal, "Pause dispatch"): self.enroll()
        self.assertEqual(enrollment.status(self.registry)["state"], "not_enrolled")

    def test_stale_tampered_future_expired_and_unconfirmed_preview_refused(self):
        original = self.request()
        for edit in (lambda r: r.update(confirmed=False),
                     lambda r: r["preview"].update(documentHash="0" * 64),
                     lambda r: r.update(extra=True)):
            candidate = copy.deepcopy(original); edit(candidate)
            with self.assertRaises(Refusal): enrollment.apply(self.registry, candidate)
        for observed in (time.time() + 1000, time.time() - 1000, True):
            candidate = copy.deepcopy(original)
            doc = candidate["preview"]["document"]; doc.update(observedAt=observed, expiresAt=observed + 300)
            candidate["preview"]["documentHash"] = digest(doc)
            with self.assertRaises(Refusal): enrollment.apply(self.registry, candidate)
        candidate = copy.deepcopy(original); candidate["preview"]["document"]["effect"] = "Activate all work"
        candidate["preview"]["documentHash"] = digest(candidate["preview"]["document"])
        with self.assertRaisesRegex(Refusal, "effect must match"): enrollment.apply(self.registry, candidate)
        self.command(self.beta, "pause")
        with self.assertRaisesRegex(Refusal, "state changed"): enrollment.apply(self.registry, original)
        self.assertEqual(enrollment.status(self.registry)["state"], "not_enrolled")

    def test_membership_change_invalidates_exact_preview(self):
        request = self.request(); gamma = self.make("gamma")
        self.registry.register("gamma", "Gamma", gamma.root)
        with self.assertRaisesRegex(Refusal, "membership changed"): enrollment.apply(self.registry, request)

    def test_duplicate_confirmation_does_not_replay_stages_or_change_policy(self):
        request = self.request()
        first = enrollment.apply(self.registry, request)
        before = enrollment.status(self.registry)
        self.assertEqual(enrollment.apply(self.registry, request), first)
        self.assertEqual(enrollment.status(self.registry), before)
        with self.assertRaises(Refusal): enrollment.apply(self.registry, {**request, "id": "different"})
        with self.assertRaises(Refusal): enrollment.preview(self.registry)

    def test_interruption_between_workspaces_retains_journal_and_first_fence(self):
        request = self.request()
        original = enrollment.stage_workspace
        def stop_after_alpha(record, member, ledger, db):
            if member["id"] == "beta": raise RuntimeError("fixture interrupted")
            return original(record, member, ledger, db)
        with patch.object(enrollment, "stage_workspace", side_effect=stop_after_alpha), self.assertRaises(RuntimeError):
            enrollment.apply(self.registry, request)
        self.assertEqual(enrollment.status(self.registry)["state"], "prepared")
        self.assert_fenced(self.alpha)
        self.assertFalse(self.beta.snapshot()["admission"]["dispatchBlocked"])
        self.assertEqual(enrollment.apply(self.registry, request)["state"], "prepared")
        with self.assertRaisesRegex(Refusal, "confirmation"):
            enrollment.recover(self.registry, request["id"])
        recovered = enrollment.recover(self.registry, request["id"], confirmed=True)
        self.assertEqual(recovered["state"], "fenced")
        self.assert_fenced(self.beta)

    def test_hard_process_crash_after_file_before_sqlite_marker_is_recoverable(self):
        self.worker(self.alpha, "starting")
        request = self.request()
        ctx = multiprocessing.get_context("spawn")
        process = ctx.Process(target=crash_after_durable_fence, args=(str(self.registry.root), request))
        process.start(); process.join(10)
        self.assertEqual(process.exitcode, 73)
        self.assertEqual(self.alpha.snapshot()["admission"]["state"], "fencing")
        self.assert_fenced(self.alpha)
        self.assertEqual(enrollment.status(self.registry)["state"], "prepared")
        recovered = enrollment.recover(Registry(self.registry.root), request["id"], confirmed=True)
        self.assertEqual(recovered["state"], "fenced")
        self.assertEqual(len(recovered["retainedOwnership"]), 1)
        self.assertEqual(self.alpha.snapshot()["admission"]["state"], "fenced")

    def test_recovery_never_clears_an_active_controller_or_owner(self):
        self.worker(self.alpha)
        self.enroll()
        token = self.beta.acquire("brain-beta:active")
        with self.assertRaisesRegex(Refusal, "release all controllers"):
            enrollment.recover(self.registry, "fixture-enrollment", confirmed=True)
        self.assertEqual(self.beta.snapshot()["meta"]["controller"]["owner"], "brain-beta:active")
        self.beta.release(token, "Fixture idle")
        self.assertEqual(enrollment.recover(self.registry, "fixture-enrollment", confirmed=True)["state"], "fenced")
        self.assertEqual(len(self.alpha.snapshot()["workers"]), 1)

    def test_registry_or_workspace_identity_drift_blocks_recovery(self):
        self.enroll()
        with self.alpha.tx() as db:
            meta = self.alpha.get(db, "meta", 1); meta["brainId"] = "different-brain"
            self.alpha.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "identity changed"):
            enrollment.recover(self.registry, "fixture-enrollment", confirmed=True)
        self.assert_fenced(self.alpha)

    def test_private_registry_permissions_are_rechecked_before_enrollment(self):
        request = self.request()
        self.registry.db.chmod(0o644)
        try:
            with self.assertRaisesRegex(Refusal, "private regular"):
                enrollment.apply(self.registry, request)
        finally:
            self.registry.db.chmod(0o600)
        self.assertFalse(enrollment.fence_exists(self.alpha.root))

    def test_current_missing_or_completed_owner_does_not_release_retained_ownership(self):
        worker = self.worker(self.alpha)
        self.enroll()
        token = self.alpha.acquire("brain-alpha:verify")
        self.alpha.transition(token, worker["id"], "verifying", "Independent fixture observation")
        self.alpha.complete(token, worker["id"], {"schemaVersion": 1, "seedHash": worker["seedHash"], "commit": "f" * 40,
            "changedPaths": ["src/example.py"], "pr": "https://github.com/example/repo/pull/1",
            "evidence": {axis: {"status": "verified" if axis in ("source", "ci") else "unverified",
                               "reference": "independent fixture" if axis in ("source", "ci") else None} for axis in AXES},
            "preserved": True, "reviewReference": "independent fixture review"})
        self.alpha.release(token, "Fixture completion recorded")
        record = enrollment.recover(self.registry, "fixture-enrollment", confirmed=True)
        self.assertEqual(record["observedOwners"][0]["owners"], [])
        self.assertEqual(record["retainedOwnership"][0]["workerId"], worker["id"])

    def test_pending_native_binding_and_observed_runner_release_remain_possible(self):
        pending = self.worker(self.alpha, "starting")
        accepting = self.worker(self.beta, "accepting")
        self.enroll()
        a = self.alpha.acquire("brain-alpha:reconcile"); b = self.beta.acquire("brain-beta:reconcile")
        self.alpha.bind(a, pending["id"], thread_id="resolved-existing-task")
        self.beta.runner(b, accepting["id"], "release", "Process exit and cleanup independently observed")
        self.assertEqual(self.alpha.snapshot()["workers"][0]["status"], "running")
        self.assertIsNone(self.beta.snapshot()["meta"]["runner"])
        self.assertEqual(len(enrollment.status(self.registry)["retainedOwnership"]), 3)

    def test_legacy_state_route_blocks_reserve_begin_and_runner_acquire(self):
        reserved = self.worker(self.alpha, "reserved")
        accepting = self.worker(self.beta, "awaiting_acceptance")
        self.enroll()
        for ledger in (Ledger(self.alpha.root), Ledger(self.beta.root)):
            token = ledger.acquire(ledger.snapshot()["meta"]["brainId"] + ":legacy")
            with self.assertRaisesRegex(Refusal, "enrollment fences"): ledger.reserve(token, "a:TEST-001")
            if ledger.root == self.alpha.root:
                with self.assertRaisesRegex(Refusal, "enrollment fences"): ledger.begin_creation(token, reserved["id"])
            else:
                with self.assertRaisesRegex(Refusal, "enrollment fences"):
                    ledger.runner(token, accepting["id"], "acquire", "Idle does not override enrollment")

    def test_either_marker_or_sidecar_blocks_even_if_paused_flag_changes(self):
        self.prepare(self.alpha)
        self.enroll()
        (self.alpha.root / enrollment.FENCE_FILE).unlink()
        with self.beta.tx() as db:
            meta = self.beta.get(db, "meta", 1); del meta["admissionBinding"]
            meta["paused"] = False; self.beta.put(db, "meta", 1, meta)
        self.assert_fenced(Ledger(self.alpha.root))
        self.assert_fenced(Ledger(self.beta.root))
        token = self.beta.acquire("brain-beta:fixture")
        with self.assertRaisesRegex(Refusal, "enrollment fences"): self.beta.reserve(token, "a:TEST-001")

    def test_dangling_or_malformed_fence_never_means_unenrolled(self):
        path = self.alpha.root / enrollment.FENCE_FILE
        path.symlink_to(self.root / "absent")
        self.assert_fenced(self.alpha)
        with self.assertRaises(Refusal): self.enroll()
        path.unlink(); path.write_text("malformed fixture", encoding="utf-8")
        self.assert_fenced(self.alpha)

    def test_foreign_fence_is_not_overwritten_during_recovery(self):
        request = self.request()
        with patch.object(enrollment, "durable_fence", side_effect=RuntimeError("fixture")), self.assertRaises(RuntimeError):
            enrollment.apply(self.registry, request)
        target = self.alpha.root / enrollment.FENCE_FILE
        target.write_text("foreign fixture", encoding="utf-8"); target.chmod(0o600)
        with self.assertRaisesRegex(Refusal, "fence identity changed"):
            enrollment.recover(self.registry, request["id"], confirmed=True)
        self.assertEqual(target.read_text(), "foreign fixture")

    def test_queued_resume_is_rejected_and_cannot_be_reintroduced(self):
        self.command(self.alpha, "resume")
        self.enroll()
        self.assertEqual(self.alpha.snapshot()["commands"][0]["status"], "rejected")
        # Simulate an old queued row restored independently of the fence file.
        with self.alpha.tx() as db:
            cmd = self.alpha.all(db, "commands")[0]; cmd["status"] = "queued"
            self.alpha.put(db, "commands", cmd["id"], cmd)
        token = self.alpha.acquire("brain-alpha:fixture")
        self.alpha.process(token)
        self.assertTrue(self.alpha.snapshot()["meta"]["paused"])
        self.assertEqual(self.alpha.snapshot()["commands"][0]["status"], "rejected")

    def test_membership_and_repository_rebinding_require_explicit_migration(self):
        self.enroll()
        gamma = self.make("gamma")
        with self.assertRaisesRegex(Refusal, "membership"):
            self.registry.register("gamma", "Gamma", gamma.root)
        second = Registry(self.root / "other-platform", create=True)
        with self.assertRaisesRegex(Refusal, "enrollment"):
            second.register("duplicate", "Duplicate", self.alpha.root)
        with self.assertRaisesRegex(Refusal, "enrollment fences"):
            self.alpha.initialize({"schemaVersion": 1, "brainId": "brain-alpha", "repositories": []})

    def test_registration_race_rechecks_journal_inside_commit(self):
        gamma = self.make("gamma")
        original = self.registry.preview
        def preview_then_enroll(*args):
            result = original(*args)
            self.enroll()
            return result
        with patch.object(self.registry, "preview", side_effect=preview_then_enroll), self.assertRaisesRegex(Refusal, "membership"):
            self.registry.register("gamma", "Gamma", gamma.root)
        self.assertEqual(len(self.registry.list()), 2)

    def test_readiness_inbox_and_assistant_explain_fence_without_new_authority(self):
        q = self.prepare(self.alpha)
        self.enroll()
        state = self.alpha.snapshot()
        self.assertTrue(inbox(state)["admission"]["dispatchBlocked"])
        readiness = diagnose(self.alpha, state)
        packet = next(row for row in readiness["packets"] if row["queueId"] == q["id"])
        self.assertIn("platform_enrollment", {row["code"] for row in packet["issues"]})
        self.assertFalse(packet["ledgerEligible"])
        self.assertIn("enrollment", readiness["nextAction"])
        data, links = context(state, "overview")
        self.assertIn("F32", {fact["id"] for fact in data["facts"]})
        self.assertFalse(catalog(state, links)["dispatch_resume"]["available"])
        self.assertNotIn("approved_dispatch", state["workflow"]["supervisionReasons"])

    def test_cli_preview_status_confirm_and_legacy_resume(self):
        base = [sys.executable, "-m", "orchestrator.cli", "--platform", str(self.registry.root)]
        result = subprocess.run([*base, "platform-enrollment-preview"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.root / "private-preview.json"; path.write_text(result.stdout)
        missing = subprocess.run([*base, "platform-enroll", str(path), "--id", "fixture-cli"], capture_output=True, text=True)
        self.assertEqual(missing.returncode, 2)
        applied = subprocess.run([*base, "platform-enroll", str(path), "--id", "fixture-cli", "--confirm"], capture_output=True, text=True)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        self.assertFalse(json.loads(applied.stdout)["activationAvailable"])
        result = subprocess.run([*base, "platform-enrollment-status"], capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout)["state"], "fenced")
        legacy = subprocess.run([sys.executable, "-m", "orchestrator.cli", "--state", str(self.alpha.root), "command", "resume",
                                 "--revision", str(self.alpha.snapshot()["meta"]["revision"])], capture_output=True, text=True)
        self.assertEqual(legacy.returncode, 2)
        self.assertIn("enrollment fences", legacy.stderr)

    def test_concurrent_owner_confirmation_has_one_journal_and_idempotent_result(self):
        request = self.request(); results = []; errors = []
        def confirm():
            try: results.append(enrollment.apply(Registry(self.registry.root), request))
            except Exception as error: errors.append(str(error))
        threads = [threading.Thread(target=confirm) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(12)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual({r["id"] for r in results}, {request["id"]})
        self.assertEqual(enrollment.status(self.registry)["state"], "fenced")


if __name__ == "__main__":
    unittest.main()
