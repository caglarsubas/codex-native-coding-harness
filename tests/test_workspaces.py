import contextlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

from orchestrator.core import Ledger, Refusal
from orchestrator.workspaces import Registry, fingerprint


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.registry = Registry(self.root / "platform", create=True)
        self.a = self.make("a")
        self.b = self.make("b")

    def tearDown(self):
        self.temp.cleanup()

    def make(self, name, brain=None):
        ledger = Ledger(self.root / name)
        ledger.initialize({"schemaVersion": 1, "brainId": brain or "brain-" + name, "repositories": []})
        return ledger

    def contents(self, ledger):
        with contextlib.closing(ledger.connect()) as db:
            return fingerprint(db)

    def test_registration_and_backup_preserve_existing_ledger(self):
        from orchestrator.observations import capture
        with self.a.tx() as db:
            capture(db, "binary-fixture", b"\x00\xffretained artifact", {
                "orderAt": 0, "name": "fixture.bin", "repository": "@portfolio", "references": []})
        before = self.contents(self.a)
        preview = self.registry.preview("a", "First workspace", self.a.root)
        self.assertFalse(preview["changesLedger"])
        self.assertEqual(self.registry.list(), [])
        self.registry.register("a", "First workspace", self.a.root)
        self.assertEqual(before, self.contents(self.a))
        self.assertTrue(self.registry.verify_backup("a")["verified"])
        self.a.acquire("brain-a:test")
        self.assertTrue(self.registry.verify_backup("a")["verified"])
        self.assertEqual(self.registry.ledger("a").snapshot()["meta"]["brainId"], "brain-a")
        self.assertNotIn(str(self.a.root), json.dumps(self.registry.list()))

    def test_independent_commands_and_profiles(self):
        for name, ledger in (("a", self.a), ("b", self.b)):
            self.registry.register(name, name.upper(), ledger.root)
        a = self.registry.ledger("a")
        a.submit({"id": "same-command-id", "kind": "pause", "payload": {}, "expectedRevision": 1})
        self.assertEqual(self.registry.ledger("b").snapshot()["commands"], [])
        profile = {"goal": "Alpha", "architecture": "Local", "roadmap": "Phase one",
                   "successCriteria": ["Test passes"], "techStack": ["Python"], "references": ["charter.md@exact-ref"]}
        one = self.registry.save_profile("a", profile, 0)
        self.assertEqual(self.registry.profile("b")["version"], 0)
        two = self.registry.save_profile("a", {**profile, "goal": "New alpha"}, 1)
        self.assertEqual(two["version"], 2)
        with self.registry.tx() as db:
            prior = json.loads(db.execute("SELECT data FROM profiles WHERE workspace='a' AND version=1").fetchone()[0])
        self.assertEqual(prior, one)
        with self.assertRaises(Refusal): self.registry.save_profile("a", profile, 0)
        with self.assertRaises(Refusal): self.registry.save_profile("a", {**profile, "extra": "no"}, 2)
        with self.assertRaises(Refusal): self.registry.save_profile("a", profile, True)

    def test_duplicate_brain_root_id_and_overlap_refused(self):
        self.registry.register("a", "A", self.a.root)
        clone = self.make("clone", "brain-a")
        nested = Ledger(self.a.root / "nested")
        nested.initialize({"schemaVersion": 1, "brainId": "brain-nested", "repositories": []})
        for wid, ledger in (("b", self.a), ("a", self.b), ("clone", clone), ("nested", nested)):
            with self.assertRaises(Refusal): self.registry.register(wid, "test", ledger.root)
        self.assertEqual(len(self.registry.list()), 1)

    def test_unknown_or_traversal_ids_do_not_create_ledgers(self):
        for wid in ("missing", "../a", "a/b", "a%2Fb", "A", "", None):
            with self.assertRaises(Refusal): self.registry.ledger(wid)
        self.assertEqual(self.registry.list(), [])

    def test_symlinks_and_unprivate_roots_refused(self):
        alias = self.root / "alias"
        alias.symlink_to(self.a.root, target_is_directory=True)
        with self.assertRaises(Refusal): self.registry.register("a", "A", alias)
        os.chmod(self.b.root, 0o755)
        with self.assertRaises(Refusal): self.registry.register("b", "B", self.b.root)
        os.chmod(self.b.root, 0o700)
        os.chmod(self.b.db, 0o644)
        with self.assertRaises(Refusal): self.registry.register("b", "B", self.b.root)

    def test_identity_change_requires_recovery(self):
        self.registry.register("a", "A", self.a.root)
        with self.a.tx() as db:
            meta = self.a.get(db, "meta", 1)
            meta["brainId"] = "different"
            self.a.put(db, "meta", 1, meta)
        with self.assertRaisesRegex(Refusal, "identity changed"): self.registry.ledger("a")

    def test_restart_keeps_registry_profile_and_backup(self):
        self.registry.register("a", "A", self.a.root)
        other = Registry(self.registry.root)
        self.assertEqual(other.list(), self.registry.list())
        self.assertTrue(other.verify_backup("a")["verified"])
        self.assertEqual(other.db.stat().st_mode & 0o777, 0o600)
        self.assertEqual(other.root.stat().st_mode & 0o777, 0o700)

    def test_backup_corruption_detected_without_restoring(self):
        self.registry.register("a", "A", self.a.root)
        path = next((self.registry.root / "backups").glob("*.sqlite3"))
        with sqlite3.connect(path) as db:
            db.execute("UPDATE meta SET data='{}'")
        self.assertFalse(self.registry.verify_backup("a")["verified"])
        self.assertEqual(self.a.snapshot()["meta"]["brainId"], "brain-a")

    def test_concurrent_duplicate_registration_has_one_winner(self):
        outcomes = []
        def register():
            try:
                Registry(self.registry.root).register("a", "A", self.a.root)
                outcomes.append("ok")
            except Refusal:
                outcomes.append("refused")
        threads = [threading.Thread(target=register) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(sorted(outcomes), ["ok", "refused"])

    def test_cli_workspace_never_falls_back_to_default(self):
        self.registry.register("a", "A", self.a.root)
        base = [sys.executable, "-m", "orchestrator.cli", "--platform", str(self.registry.root)]
        result = subprocess.run([*base, "status"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        result = subprocess.run([*base, "--workspace", "a", "status"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["meta"]["brainId"], "brain-a")
        result = subprocess.run([*base, "--workspace", "a", "--state", str(self.b.root), "status"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)

    def test_summary_deduplicates_shared_sessions_and_excludes_conflicts(self):
        from orchestrator.observations import save
        vector = {"id": "shared-task", "input_tokens": 90, "cached_input_tokens": 80,
                  "output_tokens": 10, "reasoning_output_tokens": 5, "total_tokens": 100,
                  "userMessages": 1, "assistantMessages": 1, "samples": 1}
        for wid, ledger in (("a", self.a), ("b", self.b)):
            self.registry.register(wid, wid.upper(), ledger.root)
            with ledger.tx() as db:
                save(db, "usage", {"status": "measured", "aggregate": {"total_tokens": 100}, "sessions": [vector]})
        summary = self.registry.summary()
        self.assertEqual(summary["aggregate"]["tokens"], 100)
        self.assertEqual(summary["aggregate"]["cachedInput"], 80)
        self.assertEqual(summary["aggregate"]["distinctObservedSessions"], 1)
        self.assertIsNone(summary["aggregate"]["lines"])
        with self.b.tx() as db:
            save(db, "usage", {"status": "measured", "aggregate": {"total_tokens": 110},
                "sessions": [{**vector, "input_tokens": 100, "total_tokens": 110}]})
        summary = self.registry.summary()
        self.assertEqual(summary["aggregate"]["conflictingSessionsExcluded"], 1)
        self.assertIsNone(summary["aggregate"]["tokens"])
        self.assertEqual(self.registry.summary({"a"})["aggregate"]["tokens"], 100)

    def test_shared_artifact_identity_preserves_reverted_byte_versions(self):
        from orchestrator.observations import capture
        for wid, ledger in (("a", self.a), ("b", self.b)):
            self.registry.register(wid, wid.upper(), ledger.root)
            with ledger.tx() as db:
                for index, raw in enumerate((b"first", b"second", b"first")):
                    capture(db, "shared-source", raw, {"name": "design.md", "repository": "@portfolio", "references": [], "orderAt": index})
        summary = self.registry.summary()
        self.assertEqual(summary["aggregate"]["uniqueArtifactVersions"], 3)
        self.assertEqual([a["version"] for a in summary["artifacts"]], [1, 2, 3])
