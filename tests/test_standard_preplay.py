"""Disposable pre-Play IPC qualification; no native connections or live state."""
import copy
import contextlib
import json
import os
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
import uuid
from unittest.mock import patch

from orchestrator import standard_preplay as preplay
from orchestrator.core import Ledger, Refusal, canonical, digest
from orchestrator.missions import change
from orchestrator.notification import BrainNotifier
from orchestrator.standard import read, request_catalog_refresh
from orchestrator.workspaces import Registry, fingerprint
from test_missions import specification, request


class PreplayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "checkout"; self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.registry = Registry(self.root / "outside-registry", create=True)
        self.brain = str(uuid.uuid4())
        ledger = Ledger(self.repo / ".state")
        ledger.initialize({"schemaVersion": 1, "brainId": self.brain, "repositories": [{
            "id": "a", "path": str(self.repo), "projectId": "projectless", "ref": "HEAD",
            "policyProfile": "standard", "mergePolicy": "manual"}]})
        self.registry.register("v3", "Disposable V3", ledger.root)
        self.ledger = self.registry.ledger("v3")
        saved = change(self.ledger, request(spec=specification(mode="phase_delegated")))["current"]
        change(self.ledger, request("review", saved["revision"], documentHash=saved["documentHash"], confirmed=True))
        self.command = request_catalog_refresh(self.ledger, {"id": str(uuid.uuid4()), "contextHash": read(self.ledger)["contextHash"]})
        self.cid = self.command["id"]
        self.binding = {"endpoint": {"private": "not-for-the-sandbox"}, "brains": {self.brain: {
            "workspaceId": "v3", "cwd": str(self.repo), "projectId": str(uuid.uuid4())}}}
        self.handoff = preplay.path(ledger.root, self.cid, "handoff")
        self.sent = []
        self.notifier = BrainNotifier(self.ledger)
        self.notifier.app_server = SimpleNamespace(binding=self.binding, send=self.send)
        self.status_patch = patch.object(self.notifier, "status", return_value={"status": "configured", "transport": "owned_app_server"})
        self.status_patch.start(); self.addCleanup(self.status_patch.stop)
        self.result = {"operation": "catalog", "requestId": self.cid, "models": [
            {"model": "fixture-native", "efforts": ["low", "high"]}], "source": "Actual disposable native schema"}

    def send(self, brain, message, command_id):
        # The handoff and notification claim must precede the only native boundary.
        self.assertEqual(brain, self.brain); self.assertEqual(command_id, self.cid)
        value = preplay.handoff(self.handoff)
        self.assertEqual(value["bindingHash"], digest(self.binding))
        self.sent.append(message)
        with self.ledger.tx() as db:
            command = self.ledger.get(db, "commands", self.cid)
            command["notification"]["nativeThreadObservation"] = {"rootThreadId": self.brain, "streamStatus": "open"}
            self.ledger.put(db, "commands", self.cid, command)
        return {"status": "accepted", "nativeDelivery": "owned_turn_start", "nativeTurnId": "original-turn"}

    def deliver(self):
        return self.notifier.notify(self.cid)

    def publish(self, result=None):
        preplay._write_once(preplay.path(self.ledger.root, self.cid, "request"), {
            "version": 1, "handoffHash": digest(preplay.handoff(self.handoff)), "result": result or self.result})

    def service(self, **kwargs):
        return preplay.service(self.ledger, kwargs.get("binding", self.binding), self.cid,
                               kwargs.get("brain", self.brain), kwargs.get("turn", "original-turn"))

    def mutate(self, table, key, mutate):
        with self.ledger.tx() as db:
            value = self.ledger.get(db, table, key); mutate(value); self.ledger.put(db, table, key, value)

    def proof(self):
        with contextlib.closing(sqlite3.connect(self.ledger.db)) as db:
            return fingerprint(db)

    def test_original_notification_is_prospective_closed_and_one_shot(self):
        self.deliver(); self.deliver()
        self.assertEqual(len(self.sent), 1)
        self.assertIn("--preplay-handoff", self.sent[0])
        self.assertIn("standard-preplay-receipt", self.sent[0])
        value = preplay.handoff(self.handoff)
        self.assertNotIn("endpoint", value); self.assertNotIn("token", canonical(value))
        self.assertNotIn(str(self.registry.root), canonical(value))
        self.assertFalse(preplay.state(self.handoff)["liveStateObserved"])
        with self.assertRaisesRegex(Refusal, "cannot be added"):
            with self.ledger.tx() as db:
                preplay.prepare(self.ledger, db, self.command, self.binding)

    def test_explicit_brain_receipt_uses_existing_validation_without_controller_or_play(self):
        self.deliver(); before = self.ledger.snapshot()["meta"]
        self.publish(); self.service()
        state = read(self.ledger)
        self.assertEqual(state["catalogRefresh"]["status"], "completed")
        self.assertEqual(state["catalog"]["models"], self.result["models"])
        self.assertEqual(preplay.status(self.handoff)["status"], "completed")
        after = self.ledger.snapshot()["meta"]
        self.assertIsNone(after["controller"]); self.assertTrue(after["paused"])
        self.assertNotIn("standardRun", after)
        self.assertEqual(before["checkpoint"], after["checkpoint"])
        self.assertFalse((self.ledger.root / "standard-controller.json").exists())
        self.assertEqual(self.ledger.snapshot()["workers"], [])
        proof = self.proof(); self.service(); self.deliver()
        self.assertEqual(self.proof(), proof); self.assertEqual(len(self.sent), 1)

    def test_catalog_error_is_receipted_not_guessed_capabilities(self):
        self.deliver(); self.publish({"operation": "catalog_error", "requestId": self.cid,
            "code": "schema_unavailable", "detail": "The native schema was not exposed", "retryable": False})
        self.service()
        state = read(self.ledger)
        self.assertEqual(state["catalogRefresh"]["status"], "failed")
        self.assertIsNone(state["catalog"]); self.assertFalse(state["available"])
        self.assertEqual(preplay.status(self.handoff)["status"], "completed")

    def test_no_explicit_request_means_no_collection_or_write(self):
        self.deliver(); proof = self.proof()
        with patch("orchestrator.workspaces.Registry", side_effect=AssertionError("No implicit registry access")):
            self.service()
        self.assertEqual(proof, self.proof())
        self.assertEqual(preplay.status(self.handoff)["status"], "not_submitted")

    def test_sandbox_helpers_never_open_sqlite_registry_ledger_or_native_socket(self):
        self.deliver()
        result = self.ledger.root / "result.json"; preplay._write_once(result, self.result)
        with patch("orchestrator.workspaces.Registry", side_effect=AssertionError("Registry forbidden")), \
             patch("orchestrator.core.Ledger", side_effect=AssertionError("Ledger forbidden")), \
             patch("sqlite3.connect", side_effect=AssertionError("SQLite forbidden")), \
             patch("socket.socket", side_effect=AssertionError("Socket forbidden")), \
             patch.object(preplay.time, "monotonic", side_effect=[0, 31]):
            self.assertEqual(preplay.state(self.handoff)["brainId"], self.brain)
            self.assertEqual(preplay.submit(self.handoff, result)["status"], "waiting_for_original_observer")
        self.service()
        with patch("sqlite3.connect", side_effect=AssertionError("No DB fallback")):
            self.assertEqual(preplay.submit(self.handoff, result)["status"], "completed")
        altered = self.ledger.root / "altered.json"
        preplay._write_once(altered, {**self.result, "source": "changed"})
        with self.assertRaisesRegex(Refusal, "never replace"):
            preplay.submit(self.handoff, altered)

    def test_cli_dispatch_precedes_all_database_initialization_even_on_cold_readonly_wal(self):
        self.deliver()
        # Close fixture connections and leave WAL-mode database without sidecars.
        # The sandbox command must not open either database, even read-only.
        protected = [self.registry.root, self.ledger.root]
        before = {p: (p / ("platform.sqlite3" if p == self.registry.root else "ledger.sqlite3")).read_bytes() for p in protected}
        self.assertTrue(all(raw[18:20] == b"\x02\x02" for raw in before.values()), "Cold WAL fixture required")
        try:
            for directory in protected:
                for file in directory.glob("*.sqlite3*"): os.chmod(file, 0o400)
                os.chmod(directory, 0o500)
            output = subprocess.run([sys.executable, "-m", "orchestrator.cli", "--preplay-handoff", str(self.handoff),
                                     "standard-preplay-state"], capture_output=True, text=True, cwd=preplay.SOURCE, timeout=15)
            self.assertEqual(output.returncode, 0, output.stderr)
            self.assertEqual(json.loads(output.stdout)["brainId"], self.brain)
            for directory in protected:
                file = directory / ("platform.sqlite3" if directory == self.registry.root else "ledger.sqlite3")
                self.assertEqual(file.read_bytes(), before[directory])
                self.assertFalse(file.with_name(file.name + "-shm").exists())
        finally:
            for directory in protected:
                os.chmod(directory, 0o700)
                for file in directory.glob("*.sqlite3*"): os.chmod(file, 0o600)

    def test_cli_rejects_mixed_or_unrestricted_routes(self):
        self.deliver()
        for tail in (["--platform", str(self.registry.root), "standard-preplay-state"], ["standard-state"], ["standard-acquire", self.brain + ":bad"]):
            run = subprocess.run([sys.executable, "-m", "orchestrator.cli", "--preplay-handoff", str(self.handoff), *tail],
                                 cwd=preplay.SOURCE, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(run.returncode, 0)

    def test_interrupted_claim_cannot_reapply_and_status_cannot_collect(self):
        self.deliver(); self.publish()
        preplay._write_once(preplay.path(self.ledger.root, self.cid, "claim"), {"interrupted": True})
        proof = self.proof(); self.service()
        self.assertEqual(preplay.status(self.handoff)["status"], "claimed_outcome_unknown")
        self.assertEqual(proof, self.proof())

    def test_receipt_commit_without_reply_is_not_reapplied(self):
        self.deliver(); self.publish()
        original = preplay._write_once
        def lost_reply(file, value):
            if "-reply.json" in file.name: raise OSError("lost reply")
            original(file, value)
        with patch.object(preplay, "_write_once", side_effect=lost_reply), self.assertRaises(OSError):
            self.service()
        proof = self.proof(); self.service()
        self.assertEqual(proof, self.proof())
        self.assertEqual(read(self.ledger)["catalogRefresh"]["status"], "completed")
        self.assertEqual(preplay.status(self.handoff)["status"], "claimed_outcome_unknown")

    def test_wrong_turn_brain_or_binding_cannot_apply(self):
        self.deliver(); self.publish(); proof = self.proof()
        self.service(turn="other-turn")
        self.assertEqual(preplay.status(self.handoff)["status"], "unavailable")
        self.service(); self.assertEqual(self.proof(), proof)

    def test_wrong_brain_or_binding_cannot_apply(self):
        self.deliver(); self.publish(); proof = self.proof()
        self.service(brain=str(uuid.uuid4()), binding={**self.binding, "endpoint": {"other": True}})
        self.assertEqual(preplay.status(self.handoff)["status"], "unavailable")
        self.assertEqual(proof, self.proof())

    def test_native_approval_stop_and_new_owner_each_fence_before_receipt(self):
        self.deliver(); self.publish()
        self.mutate("commands", self.cid, lambda c: c["notification"].update(nativeApprovals=[{"status": "pending"}]))
        proof = self.proof(); self.service()
        self.assertEqual(proof, self.proof())
        self.assertEqual(preplay.status(self.handoff)["status"], "unavailable")

    def test_newer_owned_turn_fences_original_receipt(self):
        self.deliver(); self.publish()
        with self.ledger.tx() as db:
            c = copy.deepcopy(self.command); c.update(id=str(uuid.uuid4()), status="completed")
            c["notification"] = {"brainId": self.brain, "attemptedAt": time.time() + 1}
            self.ledger.put(db, "commands", c["id"], c)
        proof = self.proof(); self.service(); self.assertEqual(proof, self.proof())

    def test_closed_or_legacy_observer_cannot_backfill_handoff(self):
        self.deliver(); self.publish()
        self.mutate("commands", self.cid, lambda c: c["notification"].pop("preplayCatalog"))
        proof = self.proof(); self.service(); self.assertEqual(proof, self.proof())
        self.assertEqual(preplay.status(self.handoff)["status"], "unavailable")

    def test_source_file_epoch_and_handoff_tampering_refuse_without_mutation(self):
        self.deliver(); self.publish(); proof = self.proof()
        with patch.object(preplay, "source_hash", return_value="different"):
            self.service()
        self.assertEqual(proof, self.proof())
        with self.assertRaises(Refusal):
            os.chmod(self.handoff, 0o644); preplay.state(self.handoff)
        os.chmod(self.handoff, 0o600)

    def test_malformed_catalog_cannot_create_authority_or_partial_receipt(self):
        self.deliver(); self.publish({**self.result, "operation": "play"})
        proof = self.proof(); self.service(); self.assertEqual(proof, self.proof())
        self.assertEqual(preplay.status(self.handoff)["status"], "unavailable")

    def test_notification_waits_for_committed_acceptance_before_claiming(self):
        self.deliver(); self.publish()
        self.mutate("commands", self.cid, lambda c: c["notification"].update(status="sending"))
        self.assertFalse(preplay.pending(self.ledger, self.cid))
        self.assertFalse(preplay.path(self.ledger.root, self.cid, "claim").exists())
        self.mutate("commands", self.cid, lambda c: c["notification"].update(status="accepted"))
        self.assertTrue(preplay.pending(self.ledger, self.cid)); self.service()
        self.assertEqual(preplay.status(self.handoff)["status"], "completed")

    def test_stop_and_controller_races_cannot_apply(self):
        self.deliver(); self.publish()
        self.mutate("meta", 1, lambda m: m.update(brainControl={"desired": "stopped", "phase": "checkpointing"},
                                               controller={"owner": "someone-else", "token": "private"}))
        proof = self.proof(); self.service()
        self.assertEqual(proof, self.proof())
        self.assertEqual(preplay.status(self.handoff)["status"], "unavailable")

    def test_ended_observer_cannot_apply_late_result(self):
        self.deliver(); self.publish()
        self.mutate("commands", self.cid, lambda c: c["notification"].update(nativeTurnStatus="completed"))
        proof = self.proof(); self.service()
        self.assertEqual(proof, self.proof())

    def test_unknown_turn_status_remains_unknown_without_receipt(self):
        self.deliver(); self.publish()
        self.mutate("commands", self.cid, lambda c: c["notification"].update(nativeTurnStatus="unknown"))
        proof = self.proof(); self.service(); self.assertEqual(proof, self.proof())

    def test_preserves_other_runs_usage_claims_and_bindings_byte_for_byte(self):
        old = self.root / "old-private"; old.mkdir(mode=0o700)
        files = {"old-run.json": {"status": "paused", "expired": True, "observedTokens": 1049625,
                                 "gaps": ["historical_unknown"], "terminalSafety": "unknown"},
                 "admission.claim": {"consumed": True}, "host-binding.json": {"pin": "old-binding"}}
        for name, value in files.items(): preplay._write_once(old / name, value)
        before = {file: (file.read_bytes(), file.stat().st_ino, file.stat().st_mtime_ns) for file in old.iterdir()}
        self.deliver(); self.publish(); self.service()
        self.assertEqual(before, {file: (file.read_bytes(), file.stat().st_ino, file.stat().st_mtime_ns) for file in old.iterdir()})

    def test_insecure_or_hardlinked_request_cannot_apply(self):
        self.deliver(); self.publish()
        file = preplay.path(self.ledger.root, self.cid, "request")
        os.link(file, self.ledger.root / "alias.json")
        proof = self.proof()
        with self.assertRaises(Refusal): self.service()
        self.assertEqual(proof, self.proof())

    def test_extra_fields_or_missing_model_evidence_roll_back_entire_receipt(self):
        self.deliver(); self.publish({**self.result, "models": [], "permit": "Play"})
        proof = self.proof(); self.service(); self.assertEqual(proof, self.proof())

    def test_explicit_receipt_does_not_need_a_timer_renewal(self):
        self.deliver(); self.publish()
        with patch.object(preplay.time, "time", return_value=time.time() + 3600):
            self.service()
        self.assertEqual(preplay.status(self.handoff)["status"], "completed")

    def test_strict_platform_enrollment_fences_receipt(self):
        self.deliver(); self.publish()
        with self.registry.tx() as db:
            db.execute("CREATE TABLE admission_enrollment(id INTEGER PRIMARY KEY,data TEXT NOT NULL)")
            db.execute("INSERT INTO admission_enrollment VALUES(1,?)", (canonical({"id": "fixture-fence"}),))
        proof = self.proof(); self.service(); self.assertEqual(proof, self.proof())
        self.assertEqual(preplay.status(self.handoff)["status"], "unavailable")

    def test_competing_observer_service_calls_apply_only_one_receipt(self):
        self.deliver(); self.publish()
        barrier = threading.Barrier(3); failures = []
        def worker():
            try:
                barrier.wait(3); self.service()
            except Exception as error:
                failures.append(type(error).__name__)
        workers = [threading.Thread(target=worker) for _ in range(2)]
        for thread in workers: thread.start()
        barrier.wait(3)
        for thread in workers: thread.join(5)
        self.assertFalse(failures)
        self.assertTrue(all(not thread.is_alive() for thread in workers))
        with contextlib.closing(sqlite3.connect(self.ledger.db)) as db:
            count = db.execute("SELECT COUNT(*) FROM events WHERE kind='standard_preplay_receipt'").fetchone()[0]
        self.assertEqual(count, 1)
        self.assertEqual(preplay.status(self.handoff)["status"], "completed")

    def test_late_failure_rolls_back_catalog_receipt_and_event_together(self):
        self.deliver(); self.publish(); proof = self.proof()
        original = self.ledger.event
        def fail(db, kind, value):
            if kind == "standard_preplay_receipt": raise Refusal("fixture interrupted commit")
            original(db, kind, value)
        with patch.object(self.ledger, "event", side_effect=fail): self.service()
        self.assertEqual(proof, self.proof())
        self.assertEqual(preplay.status(self.handoff)["status"], "unavailable")

    def test_mission_change_blocks_old_result_without_recording_capabilities(self):
        self.deliver(); self.publish()
        self.mutate("meta", 1, lambda m: m.update(missionConfiguration=None))
        proof = self.proof(); self.service()
        self.assertEqual(proof, self.proof())

    def test_cannot_forge_an_old_handoff_when_the_original_has_none(self):
        with self.ledger.tx() as db:
            c = self.ledger.get(db, "commands", self.cid)
            c["notification"] = {"status": "accepted", "nativeTurnId": "old-turn"}
            self.ledger.put(db, "commands", self.cid, c)
        with self.assertRaisesRegex(Refusal, "cannot be added"):
            with self.ledger.tx() as db:
                preplay.prepare(self.ledger, db, self.command, self.binding)
        self.assertFalse(self.handoff.exists())

    @unittest.skipUnless(sys.platform == "darwin" and shutil.which("sandbox-exec"), "Requires macOS sandbox-exec")
    def test_real_macos_sandbox_catalog_receipt_without_registry_database_or_socket_access(self):
        self.deliver()
        result = self.ledger.root / "result.json"; preplay._write_once(result, self.result)
        profile = ("(version 1)(allow default)"
                   f"(deny file-read* file-write* (subpath {json.dumps(str(self.registry.root))}))"
                   f"(deny file-read* file-write* (literal {json.dumps(str(self.ledger.db))}))"
                   "(deny network*)")
        failure = []
        def original_observer():
            try:
                end = time.monotonic() + 10
                while time.monotonic() < end:
                    if preplay.pending(self.ledger, self.cid):
                        self.service(); return
                    time.sleep(0.02)
                failure.append("No explicit request appeared")
            except Exception as error:
                failure.append(type(error).__name__)
        worker = threading.Thread(target=original_observer); worker.start()
        try:
            run = subprocess.run([shutil.which("sandbox-exec"), "-p", profile, sys.executable,
                "-m", "orchestrator.cli", "--preplay-handoff", str(self.handoff),
                "standard-preplay-receipt", str(result)], cwd=preplay.SOURCE, capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout)["status"], "completed")
        finally:
            worker.join(11)
        self.assertFalse(failure)
        self.assertEqual(read(self.ledger)["catalogRefresh"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
