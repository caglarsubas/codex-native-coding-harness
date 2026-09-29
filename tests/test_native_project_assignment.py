import contextlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from orchestrator.core import Ledger, Refusal, digest
from orchestrator import native_project_assignment as assignment, projects
from orchestrator.workspaces import Registry


BRAIN = "11111111-1111-4111-8111-111111111111"
PROJECT = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"


class NativeProxy:
    project_id = None
    native_project_id = PROJECT
    cwd = None
    project_roots = None
    status = "notLoaded"
    writes = 0
    fail_update = False
    calls = []
    project_reads = 0
    on_project_read = None

    def __init__(self, endpoint, **_):
        self.endpoint = endpoint

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def _rpc(self, method, params):
        self.calls.append((method, params))
        if method == "project/read":
            type(self).project_reads += 1
            if type(self).project_reads == 3 and type(self).on_project_read:
                type(self).on_project_read()
            return {"project": {"id": self.native_project_id,
                                "roots": [{"path": path} for path in self.project_roots]}}
        if method == "thread/read":
            return {"thread": {"id": BRAIN, "cwd": self.cwd, "projectId": self.project_id,
                               "status": {"type": self.status}}}
        if method == "thread/metadata/update":
            type(self).writes += 1
            if self.fail_update:
                raise Refusal("Lost native response")
            type(self).project_id = params["projectId"]
            return {"thread": {"id": BRAIN, "cwd": self.cwd, "projectId": self.project_id}}
        raise AssertionError("Unexpected native method " + method)


class NativeProjectAssignmentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "source"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.ledger = Ledger(self.root / "state")
        self.ledger.initialize({"schemaVersion": 1, "brainId": BRAIN, "repositories": [{
            "id": "source", "path": str(self.repo), "projectId": PROJECT, "ref": "HEAD",
            "mergePolicy": "manual", "policyProfile": "standard"}]})
        self.registry = Registry(self.root / "platform", create=True)
        self.registry.register("pilot", "Pilot", self.ledger.root)
        projects.record(self.registry, {"schemaVersion": 2, "projects": [{
            "projectId": PROJECT, "projectKind": "local", "label": "Pilot",
            "hostId": "local", "path": str(self.repo), "isGitRepository": True}]}, time.time())
        projects.bind(self.registry, "pilot", "local", PROJECT, projects.catalog(self.registry)["hash"])
        self.binding = {"endpoint": {"fixture": "pinned"}, "brains": {BRAIN: {
            "workspaceId": "pilot", "projectId": PROJECT, "cwd": str(self.repo)}}}
        NativeProxy.project_id = None
        NativeProxy.native_project_id = PROJECT
        NativeProxy.cwd = str(self.repo)
        NativeProxy.project_roots = [str(self.repo)]
        NativeProxy.status = "notLoaded"
        NativeProxy.writes = 0
        NativeProxy.fail_update = False
        NativeProxy.calls = []
        NativeProxy.project_reads = 0
        NativeProxy.on_project_read = None
        self.patches = [patch.object(assignment, "ReadProxy", NativeProxy),
                        patch.object(assignment, "WakeProxy", NativeProxy),
                        patch.object(assignment, "validate_endpoint")]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def preview(self):
        return assignment.preview(self.registry, "pilot", self.binding)

    def confirm(self, review):
        return assignment.confirm(self.registry, "pilot", self.binding, review, review["previewHash"])

    def replacement_binding(self):
        return {"endpoint": {"fixture": "replacement"}, "brains": {
            BRAIN: dict(self.binding["brains"][BRAIN])}}

    def test_preview_is_read_only_and_exact_confirmation_is_one_shot(self):
        before = self.ledger.snapshot()["meta"]["revision"]
        review = self.preview()
        self.assertEqual(assignment.status(self.registry, "pilot")["status"], "not_started")
        self.assertEqual(before, self.ledger.snapshot()["meta"]["revision"])
        with contextlib.closing(sqlite3.connect(self.ledger.db)) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name=?", (assignment.TABLE,)).fetchone())
        self.assertEqual(review["preview"]["projectLocationHash"], digest(["local", str(self.repo)]))
        result = self.confirm(review)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["nativeOutcome"], "project_id_observed")
        self.assertEqual(NativeProxy.writes, 1)
        self.assertIn(("thread/metadata/update", {"threadId": BRAIN, "projectId": PROJECT}), NativeProxy.calls)
        with self.assertRaises(Refusal):
            self.confirm(review)
        self.assertEqual(NativeProxy.writes, 1)

    def test_distinct_catalog_and_app_server_project_ids_are_explicit_and_bound(self):
        # The desktop's list_projects identity need not be the same as this
        # installed app-server's project/read identity for the same Git root.
        self.binding["brains"][BRAIN]["catalogProjectId"] = PROJECT
        self.binding["brains"][BRAIN]["projectId"] = OTHER
        NativeProxy.native_project_id = OTHER
        review = self.preview()
        self.assertEqual(review["preview"]["catalogProjectId"], PROJECT)
        self.assertEqual(review["preview"]["projectId"], OTHER)
        self.assertEqual(self.confirm(review)["status"], "verified")
        self.assertEqual(NativeProxy.project_id, OTHER)
        self.assertIn(("thread/metadata/update", {"threadId": BRAIN, "projectId": OTHER}),
                      NativeProxy.calls)
        self.assertEqual(assignment.status(self.registry, "pilot")["catalogProjectId"], PROJECT)

    def test_unmapped_or_changed_dual_identity_fails_before_native_write(self):
        self.binding["brains"][BRAIN]["projectId"] = OTHER
        NativeProxy.native_project_id = OTHER
        with self.assertRaises(Refusal):
            self.preview()  # No implied mapping from the matching project root.
        self.assertEqual(NativeProxy.calls, [])
        self.binding["brains"][BRAIN]["catalogProjectId"] = PROJECT
        review = self.preview()
        self.binding["brains"][BRAIN]["catalogProjectId"] = OTHER
        with self.assertRaises(Refusal):
            self.confirm(review)
        self.assertEqual(NativeProxy.writes, 0)

    def test_lost_response_is_retained_and_reconcile_never_resends(self):
        review = self.preview()
        NativeProxy.fail_update = True
        result = self.confirm(review)
        self.assertEqual(result["status"], "uncertain")
        self.assertTrue(result["nativeAttempted"])
        self.assertEqual(NativeProxy.writes, 1)
        self.assertEqual(assignment.reconcile(self.registry, "pilot", self.binding)["status"], "uncertain")
        NativeProxy.project_id = PROJECT
        self.assertEqual(assignment.reconcile(self.registry, "pilot", self.binding)["status"], "verified")
        self.assertEqual(NativeProxy.writes, 1)
        with self.assertRaises(Refusal):
            self.preview()

    def test_pre_dual_identity_intent_reconciles_without_a_second_native_write(self):
        review = self.preview()
        NativeProxy.fail_update = True
        self.assertEqual(self.confirm(review)["status"], "uncertain")
        self.assertEqual(NativeProxy.writes, 1)
        # PR #100 intents carried one project ID for both native namespaces.
        # Preserve an otherwise exact historical intent during reconciliation.
        with self.ledger.tx() as db:
            prior = assignment._row(db, BRAIN)
            prior.pop("catalogProjectId")
            self.ledger.put(db, assignment.TABLE, BRAIN, prior)
        NativeProxy.project_id = PROJECT
        self.assertEqual(assignment.reconcile(self.registry, "pilot", self.binding)["status"], "verified")
        self.assertEqual(NativeProxy.writes, 1)

    def test_claim_survives_pre_send_host_failure_without_retry(self):
        review = self.preview()
        class FailedWake(NativeProxy):
            def __enter__(self):
                raise OSError("Pinned host unavailable")
        with patch.object(assignment, "WakeProxy", FailedWake):
            result = self.confirm(review)
        self.assertEqual(result["status"], "uncertain")
        self.assertFalse(result["nativeAttempted"])
        self.assertEqual(NativeProxy.writes, 0)
        with self.assertRaises(Refusal):
            self.confirm(review)
        self.assertEqual(NativeProxy.writes, 0)

    def test_concurrent_local_pause_change_fences_native_write_after_claim(self):
        review = self.preview()
        def mutate():
            def writer():
                with self.ledger.tx() as db:
                    meta = self.ledger.get(db, "meta", 1)
                    meta["paused"] = False
                    self.ledger.put(db, "meta", 1, meta)
                    self.ledger.event(db, "fixture_resume", {})
            thread = threading.Thread(target=writer)
            thread.start(); thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        NativeProxy.on_project_read = mutate
        result = self.confirm(review)
        self.assertEqual(result["status"], "uncertain")
        self.assertFalse(result["nativeAttempted"])
        self.assertEqual(NativeProxy.writes, 0)
        with self.assertRaises(Refusal):
            self.confirm(review)

    def test_conflicting_native_project_and_wrong_roots_refuse_before_claim(self):
        NativeProxy.native_project_id = OTHER
        with self.assertRaises(Refusal):
            self.preview()
        NativeProxy.native_project_id = PROJECT
        NativeProxy.project_id = OTHER
        with self.assertRaises(Refusal):
            self.preview()
        NativeProxy.project_id = None
        other_repo = self.root / "other"
        other_repo.mkdir()
        subprocess.run(["git", "init", "-q", str(other_repo)], check=True)
        NativeProxy.project_roots = [str(other_repo)]
        with self.assertRaises(Refusal):
            self.preview()
        NativeProxy.project_roots = [str(self.repo), str(other_repo)]
        with self.assertRaises(Refusal):
            self.preview()
        self.assertEqual(NativeProxy.writes, 0)
        self.assertEqual(assignment.status(self.registry, "pilot")["status"], "not_started")

    def test_stale_preview_and_wrong_confirmation_hash_refuse(self):
        review = self.preview()
        with self.assertRaises(Refusal):
            assignment.confirm(self.registry, "pilot", self.binding, review, "a" * 64)
        with self.ledger.tx() as db:
            self.ledger.event(db, "fixture_change", {})
        with self.assertRaises(Refusal):
            self.confirm(review)
        self.assertEqual(NativeProxy.writes, 0)
        self.assertEqual(assignment.status(self.registry, "pilot")["status"], "not_started")

    def test_active_turn_and_unresolved_native_delivery_refuse(self):
        NativeProxy.status = "active"
        with self.assertRaises(Refusal):
            self.preview()

    def test_unsettled_brain_stop_or_resume_refuses(self):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["brainControl"] = {"desired": "running", "phase": "resume_requested"}
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal):
            self.preview()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["brainControl"] = {"desired": "running", "phase": "ready"}
            self.ledger.put(db, "meta", 1, meta)
            self.ledger.put(db, "commands", "resume", {"id": "resume", "kind": "brain_resume",
                "status": "queued"})
        with self.assertRaises(Refusal):
            self.preview()
        NativeProxy.status = "idle"
        with self.ledger.tx() as db:
            self.ledger.put(db, "commands", "pending", {"id": "pending", "kind": "reconcile",
                "status": "queued", "notification": {"status": "accepted"}})
        with self.assertRaises(Refusal):
            self.preview()

    def test_strict_repository_refuses_before_native_read(self):
        with self.ledger.tx() as db:
            repo = self.ledger.get(db, "repos", "source")
            repo["policyProfile"] = "harness"
            self.ledger.put(db, "repos", "source", repo)
        with self.assertRaises(Refusal):
            self.preview()
        self.assertEqual(NativeProxy.calls, [])

    def test_reconcile_accepts_active_turn_but_no_second_write(self):
        review = self.preview()
        NativeProxy.fail_update = True
        self.confirm(review)
        NativeProxy.project_id = PROJECT
        NativeProxy.status = "active"
        self.assertEqual(assignment.reconcile(self.registry, "pilot", self.binding)["status"], "verified")
        self.assertEqual(NativeProxy.writes, 1)

    def test_reconcile_records_conflicting_project_without_overwrite(self):
        review = self.preview()
        NativeProxy.fail_update = True
        self.confirm(review)
        NativeProxy.project_id = OTHER
        result = assignment.reconcile(self.registry, "pilot", self.binding)
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["projectId"], PROJECT)
        self.assertEqual(NativeProxy.writes, 1)

    def test_verified_project_drift_is_visible_without_erasing_historical_proof(self):
        result = self.confirm(self.preview())
        verified_at = result["verifiedAt"]
        NativeProxy.project_id = OTHER
        changed = assignment.reconcile(self.registry, "pilot", self.binding)
        self.assertEqual(changed["status"], "conflict")
        self.assertEqual(changed["verifiedAt"], verified_at)
        self.assertEqual(changed["observedProjectId"], OTHER)
        self.assertEqual(NativeProxy.writes, 1)

    def test_replacement_host_preview_is_read_only_and_preserves_one_shot_assignment(self):
        saved = self.confirm(self.preview())
        revision = self.ledger.snapshot()["meta"]["revision"]
        replacement = self.replacement_binding()
        NativeProxy.calls = []
        report = assignment.host_preview(self.registry, "pilot", replacement)
        doc = report["preview"]
        self.assertEqual(doc["assignmentPreviewHash"], saved["previewHash"])
        self.assertEqual(doc["nativeProjectId"], PROJECT)
        self.assertEqual(doc["nativeStatus"], "notLoaded")
        self.assertEqual(doc["candidateEndpointHash"], digest(replacement["endpoint"]))
        self.assertNotEqual(doc["originalEndpointHash"], doc["candidateEndpointHash"])
        self.assertEqual(report["previewHash"], digest(doc))
        self.assertEqual({name for name, _ in NativeProxy.calls}, {"project/read", "thread/read"})
        self.assertEqual(assignment.status(self.registry, "pilot"), saved)
        self.assertEqual(self.ledger.snapshot()["meta"]["revision"], revision)
        self.assertEqual(NativeProxy.writes, 1)
        with self.assertRaises(Refusal):
            self.preview()

    def test_replacement_host_preview_refuses_unverified_or_same_host(self):
        replacement = self.replacement_binding()
        with self.assertRaises(Refusal):
            assignment.host_preview(self.registry, "pilot", replacement)
        self.confirm(self.preview())
        with self.assertRaises(Refusal):
            assignment.host_preview(self.registry, "pilot", self.binding)
        with self.ledger.tx() as db:
            prior = assignment._row(db, BRAIN)
            prior["status"] = "uncertain"
            self.ledger.put(db, assignment.TABLE, BRAIN, prior)
        with self.assertRaises(Refusal):
            assignment.host_preview(self.registry, "pilot", replacement)
        self.assertEqual(NativeProxy.writes, 1)

    def test_replacement_host_preview_refuses_wrong_identity_or_unsettled_state(self):
        self.confirm(self.preview())
        replacement = self.replacement_binding()
        replacement["brains"][BRAIN]["projectId"] = OTHER
        with self.assertRaises(Refusal):
            assignment.host_preview(self.registry, "pilot", replacement)
        replacement = self.replacement_binding()
        NativeProxy.project_id = OTHER
        with self.assertRaises(Refusal):
            assignment.host_preview(self.registry, "pilot", replacement)
        NativeProxy.project_id = PROJECT
        NativeProxy.native_project_id = OTHER
        with self.assertRaises(Refusal):
            assignment.host_preview(self.registry, "pilot", replacement)
        NativeProxy.native_project_id = PROJECT
        NativeProxy.status = "active"
        with self.assertRaises(Refusal):
            assignment.host_preview(self.registry, "pilot", replacement)
        NativeProxy.status = "idle"
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta["paused"] = False
            self.ledger.put(db, "meta", 1, meta)
        with self.assertRaises(Refusal):
            assignment.host_preview(self.registry, "pilot", replacement)
        self.assertEqual(NativeProxy.writes, 1)


if __name__ == "__main__":
    unittest.main()
