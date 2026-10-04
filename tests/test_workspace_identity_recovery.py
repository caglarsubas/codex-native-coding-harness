import contextlib
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from orchestrator.core import Ledger, Refusal, canonical
from orchestrator.projects import bind, catalog, record
from orchestrator.workspaces import Registry, fingerprint
from orchestrator import workspace_identity_recovery as recovery


class DeviceRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.registry = Registry(self.root / "platform", create=True)
        self.ledger = Ledger(self.root / "ledger")
        self.ledger.initialize({"schemaVersion": 1, "brainId": "brain-a", "repositories": [
            {"id": "source", "path": str(self.root / "source"), "projectId": "native-a", "ref": "main",
             "mergePolicy": "manual", "policyProfile": "standard"}]})
        self.registry.register("a", "A", self.ledger.root)
        native = record(self.registry, {"schemaVersion": 2, "projects": [
            {"projectKind": "local", "projectId": "native-a", "hostId": "local", "label": "A",
             "path": str(self.root / "source"), "isGitRepository": True}]}, 1)
        bind(self.registry, "a", "local", "native-a", native["hash"])
        self.reference = self.root / "reference.sqlite3"
        self.save_reference()
        self.drift()

    def tearDown(self):
        self.temp.cleanup()

    def save_reference(self):
        if not self.reference.exists():
            os.close(os.open(self.reference, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        with contextlib.closing(sqlite3.connect(self.ledger.db)) as source, \
                contextlib.closing(sqlite3.connect(self.reference)) as target:
            source.backup(target)

    def drift(self):
        """Fixture-only simulation of a reboot's old device pin, not live repair."""
        old = [self.ledger.db.stat().st_dev - 1, self.ledger.db.stat().st_ino]
        with self.registry.tx() as db:
            row = json.loads(db.execute("SELECT data FROM workspaces WHERE id='a'").fetchone()[0])
            row["databaseIdentity"] = old
            db.execute("UPDATE workspaces SET data=? WHERE id='a'", (canonical(row),))
            binding = json.loads(db.execute("SELECT data FROM project_bindings").fetchone()[0])
            binding["databaseIdentity"] = old
            db.execute("UPDATE project_bindings SET data=?", (canonical(binding),))

    def preview(self):
        return recovery.preview(self.registry, "a", self.reference)

    def apply(self, proposal=None):
        proposal = proposal or self.preview()
        return recovery.confirm(self.registry, "a", proposal, proposal["documentHash"],
                                confirmed=True, writers_stopped=True)

    def contents(self, path):
        with recovery.read_database(path) as db:
            return fingerprint(db)

    def change_meta(self, **fields):
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            meta.update(fields)
            self.ledger.put(db, "meta", 1, meta)

    def test_preview_read_only_and_confirmation_preserves_ledger_and_mapping(self):
        ledger_before, platform_before = self.contents(self.ledger.db), self.contents(self.registry.db)
        with self.assertRaisesRegex(Refusal, "identity changed"):
            self.registry.root_for("a")
        proposal = self.preview()
        self.assertEqual(self.contents(self.ledger.db), ledger_before)
        self.assertEqual(self.contents(self.registry.db), platform_before)
        receipt = self.apply(proposal)
        self.assertEqual(self.registry.root_for("a"), self.ledger.root)
        self.assertTrue(catalog(self.registry)["projects"][0]["managed"])
        self.assertEqual(self.contents(self.ledger.db), ledger_before)
        self.assertFalse(any(receipt["boundary"].values()))
        retained = self.registry.root / "backups" / receipt["backupId"]
        self.assertEqual(self.contents(retained / "platform.sqlite3"), platform_before)
        self.assertEqual(self.contents(retained / "ledger.sqlite3"), ledger_before)
        self.assertEqual((retained / "ledger.sqlite3").stat().st_mode & 0o777, 0o600)
        self.assertEqual(retained.stat().st_mode & 0o777, 0o700)

    def test_exact_confirmation_and_stopped_writers_required(self):
        proposal = self.preview()
        for confirmed, stopped, hash_value in ((False, True, proposal["documentHash"]),
                                              (True, False, proposal["documentHash"]),
                                              (True, True, "0" * 64)):
            with self.assertRaises(Refusal):
                recovery.confirm(self.registry, "a", proposal, hash_value,
                                 confirmed=confirmed, writers_stopped=stopped)
        with self.assertRaises(Refusal):
            recovery.confirm(self.registry, "b", proposal, proposal["documentHash"],
                             confirmed=True, writers_stopped=True)

    def test_identical_replay_does_not_reapply_or_make_more_backups(self):
        proposal = self.preview()
        receipt = self.apply(proposal)
        before = self.contents(self.registry.db)
        self.assertEqual(self.apply(proposal), receipt)
        self.assertEqual(self.contents(self.registry.db), before)
        self.drift()  # A later change must not be repaired by the old confirmation.
        self.assertEqual(self.apply(proposal), receipt)
        with self.assertRaises(Refusal): self.registry.root_for("a")
        self.assertEqual(len(list((self.registry.root / "backups").glob("device-recovery-*"))), 1)

    def test_reference_data_or_schema_change_refused(self):
        with sqlite3.connect(self.reference) as db:
            db.execute("CREATE TRIGGER changed AFTER UPDATE ON meta BEGIN SELECT 1; END")
        with self.assertRaisesRegex(Refusal, "contents do not match"): self.preview()

    def test_reference_cannot_be_current_ledger_alias_or_public(self):
        with self.assertRaises(Refusal): recovery.preview(self.registry, "a", self.ledger.db)
        alias = self.root / "alias.sqlite3"
        alias.symlink_to(self.reference)
        with self.assertRaises(Refusal): recovery.preview(self.registry, "a", alias)
        os.chmod(self.reference, 0o644)
        with self.assertRaises(Refusal): self.preview()

    def test_inode_or_brain_change_cannot_be_adopted(self):
        with self.registry.tx() as db:
            data = json.loads(db.execute("SELECT data FROM workspaces WHERE id='a'").fetchone()[0])
            data["databaseIdentity"][1] += 1
            db.execute("UPDATE workspaces SET data=? WHERE id='a'", (canonical(data),))
        with self.assertRaisesRegex(Refusal, "unchanged ledger inode"): self.preview()
        self.drift()
        self.change_meta(brainId="replacement")
        self.save_reference()
        with self.assertRaisesRegex(Refusal, "replace a brain"): self.preview()

    def test_pending_controller_runner_worker_and_controls_refused(self):
        for field, value in (("paused", False), ("controller", {"owner": "brain-a:test"}),
                             ("runner", {"workerId": "x"})):
            with self.subTest(field=field):
                before = self.ledger.snapshot()["meta"]
                self.change_meta(**{field: value})
                self.save_reference()
                with self.assertRaises(Refusal): self.preview()
                self.change_meta(**before)
        with self.ledger.tx() as db:
            self.ledger.put(db, "commands", "pending", {"status": "queued"})
        self.save_reference()
        with self.assertRaisesRegex(Refusal, "Pending commands"): self.preview()
        with self.ledger.tx() as db:
            db.execute("DELETE FROM commands WHERE id='pending'")
            db.execute("INSERT INTO workers(id,queue_id,data) VALUES('owned','fixture',?)",
                       (canonical({"status": "creation_pending"}),))
        self.save_reference()
        with self.assertRaisesRegex(Refusal, "Unsettled legacy"): self.preview()

    def test_paused_expired_run_accounting_and_receipts_are_preserved(self):
        self.change_meta(schemaVersion=4, standardRun={"protocol": "standard_cooperative_v1",
            "brainId": "brain-a", "status": "paused", "tasks": [], "merges": [],
            "expiresAt": 1, "usage": {"tokens": 1_225_378, "gaps": ["retained"]}})
        self.save_reference()
        before = self.contents(self.ledger.db)
        self.apply()
        self.assertEqual(self.contents(self.ledger.db), before)
        run = self.ledger.snapshot()["meta"]["standardRun"]
        self.assertEqual(run["expiresAt"], 1)
        self.assertEqual(run["usage"]["gaps"], ["retained"])

    def test_unresolved_standard_tasks_and_merge_intents_refused(self):
        for tasks, merges in (([{"status": "creation_pending"}], []),
                              ([], [{"status": "uncertain"}])):
            self.change_meta(standardRun={"protocol": "standard_cooperative_v1", "brainId": "brain-a",
                                         "status": "paused", "tasks": tasks, "merges": merges})
            self.save_reference()
            with self.assertRaisesRegex(Refusal, "unresolved standard"): self.preview()

    def test_strict_and_managed_fences_refused(self):
        self.change_meta(admissionBinding={})
        self.save_reference()
        with self.assertRaisesRegex(Refusal, "Managed ownership"): self.preview()
        with self.ledger.tx() as db:
            meta = self.ledger.get(db, "meta", 1)
            del meta["admissionBinding"]
            self.ledger.put(db, "meta", 1, meta)
            repo = self.ledger.get(db, "repos", "source")
            repo["policyProfile"] = "harness"
            self.ledger.put(db, "repos", "source", repo)
        self.save_reference()
        with self.assertRaisesRegex(Refusal, "Strict Harness"): self.preview()

    def test_dashboard_lock_refuses_recovery(self):
        proposal = self.preview()
        with open(self.ledger.root / "dashboard.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(Refusal, "Stop the dashboard"): self.apply(proposal)

    def test_revision_and_foreign_registry_changes_invalidate_preview(self):
        proposal = self.preview()
        self.change_meta(checkpoint="later")
        with self.assertRaises(Refusal): self.apply(proposal)
        self.save_reference()
        proposal = self.preview()
        with self.registry.tx() as db:
            db.execute("UPDATE workspaces SET name='Changed' WHERE id='a'")
        with self.assertRaisesRegex(Refusal, "evidence changed"): self.apply(proposal)

    def test_changed_binding_is_not_reassigned(self):
        with self.registry.tx() as db:
            value = json.loads(db.execute("SELECT data FROM project_bindings").fetchone()[0])
            value["brainId"] = "different"
            db.execute("UPDATE project_bindings SET data=?", (canonical(value),))
        with self.assertRaisesRegex(Refusal, "Changed project mapping"): self.preview()

    def test_no_drift_missing_reference_and_corrupt_reference_refused(self):
        self.apply()
        with self.assertRaisesRegex(Refusal, "Only device-number drift"): self.preview()
        self.drift()
        with self.assertRaises(OSError): recovery.preview(self.registry, "a", self.root / "missing.sqlite3")
        self.reference.write_bytes(b"not a database")
        with self.assertRaises((Refusal, sqlite3.DatabaseError)): self.preview()

    def test_enrollment_fence_and_private_controller_sidecar_remain_fenced(self):
        for name in ("admission-fence.json", "standard-controller.json"):
            path = self.ledger.root / name
            path.touch(mode=0o600)
            with self.assertRaises(Refusal): self.preview()
            path.unlink()  # Fixture-only cleanup; never remove a live fence.

    def test_hard_link_reference_refused(self):
        alias = self.root / "hard-linked.sqlite3"
        os.link(self.reference, alias)
        with self.assertRaises(Refusal): self.preview()

    def test_other_workspace_record_and_ledger_are_not_modified(self):
        other = Ledger(self.root / "other")
        other.initialize({"schemaVersion": 1, "brainId": "brain-b", "repositories": []})
        self.registry.register("b", "B", other.root)
        with self.registry.tx() as db:
            before_row = tuple(db.execute("SELECT * FROM workspaces WHERE id='b'").fetchone())
        before_ledger = self.contents(other.db)
        self.apply()
        with self.registry.tx() as db:
            self.assertEqual(tuple(db.execute("SELECT * FROM workspaces WHERE id='b'").fetchone()), before_row)
        self.assertEqual(self.contents(other.db), before_ledger)

    def test_preview_files_stay_private_and_duplicate_keys_refused(self):
        path = self.root / "proposal.json"
        path.write_text('{"document":{},"document":{}}')
        with self.assertRaises(Refusal): recovery.read_preview(path)
        path.chmod(0o600)
        with self.assertRaises(Refusal): recovery.read_preview(path)

    def test_post_backup_drift_rolls_back_registry_and_preserves_backups(self):
        before = self.contents(self.registry.db)
        original = recovery.backup_database
        calls = 0
        def save(*args):
            nonlocal calls
            original(*args)
            calls += 1
            if calls == 2:
                with sqlite3.connect(self.reference) as db:
                    db.execute("CREATE TABLE drift(id TEXT)")
        with patch.object(recovery, "backup_database", side_effect=save):
            with self.assertRaises(Refusal): self.apply()
        self.assertEqual(self.contents(self.registry.db), before)
        with self.assertRaises(Refusal): self.registry.root_for("a")
        retained = next((self.registry.root / "backups").glob("device-recovery-*"))
        self.assertEqual(self.contents(retained / "platform.sqlite3"), before)

    def test_corrupt_history_is_not_a_replay_permission(self):
        self.apply()
        self.drift()
        with self.registry.tx() as db:
            data = json.loads(db.execute("SELECT data FROM workspaces WHERE id='a'").fetchone()[0])
            data["identityRecoveries"][0]["document"]["workspaceId"] = "different"
            db.execute("UPDATE workspaces SET data=? WHERE id='a'", (canonical(data),))
        with self.assertRaisesRegex(Refusal, "history is invalid"): self.preview()

    def test_backup_failure_leaves_original_identity_and_partial_backup(self):
        before = self.contents(self.registry.db)
        with patch.object(recovery, "backup_database", side_effect=Refusal("backup failed")):
            with self.assertRaisesRegex(Refusal, "backup failed"): self.apply()
        self.assertEqual(self.contents(self.registry.db), before)
        with self.assertRaises(Refusal): self.registry.root_for("a")
        self.assertEqual(len(list((self.registry.root / "backups").glob("device-recovery-*"))), 1)

    def test_concurrent_exact_confirmations_make_one_durable_receipt(self):
        proposal = self.preview()
        results, errors = [], []
        def apply():
            try: results.append(self.apply(proposal))
            except Exception as error: errors.append(error)
        threads = [threading.Thread(target=apply) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertFalse(errors, errors)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], results[1])

    def test_ledger_lock_remains_held_at_registry_commit_boundary(self):
        original_tx = self.registry.tx
        checked = []
        @contextlib.contextmanager
        def transaction():
            with original_tx() as db:
                yield db
                with contextlib.closing(sqlite3.connect(self.ledger.db, timeout=0)) as competing:
                    with self.assertRaises(sqlite3.OperationalError):
                        competing.execute("BEGIN IMMEDIATE")
                checked.append(True)
        proposal = self.preview()
        with patch.object(self.registry, "tx", transaction):
            self.apply(proposal)
        self.assertEqual(checked, [True])

    def test_cli_requires_exact_workspace_and_explicit_confirmation(self):
        base = [sys.executable, "-m", "orchestrator.cli", "--platform", str(self.registry.root)]
        result = subprocess.run([*base, "workspace-identity-preview", str(self.reference)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        result = subprocess.run([*base, "--workspace", "a", "workspace-identity-preview", str(self.reference)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        proposal = json.loads(result.stdout)
        path = self.root / "preview.json"
        path.write_text(canonical(proposal))
        path.chmod(0o600)
        command = [*base, "--workspace", "a", "workspace-identity-recover", str(path),
                   "--confirm-hash", proposal["documentHash"]]
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)
        result = subprocess.run([*command, "--confirm", "--writers-stopped"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.registry.root_for("a"), self.ledger.root)
