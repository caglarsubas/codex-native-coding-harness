import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from orchestrator.provenance import Provenance, git, inspect, remote_revision


class ProvenanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / "orchestrator").mkdir()
        self.source = self.root / "orchestrator" / "app.py"
        self.source.write_text("print('fixture')\n")
        (self.root / ".gitignore").write_text(".env\n__pycache__/\n")
        self.git("add", "."); self.git("commit", "-m", "Fixture")
        self.git("remote", "add", "origin", "git@github.com:example/fixture.git")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.DEVNULL).decode().strip()

    def remote(self, revision=None):
        return {"at": time.time(), "status": "observed", "repository": "example/fixture",
            "branch": "main", "commit": revision or self.git("rev-parse", "HEAD")}

    def test_clean_start_and_snapshots_do_not_scan_or_query(self):
        p = Provenance(self.root)
        with patch("orchestrator.provenance.inspect") as scan, patch("orchestrator.provenance.remote_revision") as remote:
            result = p.snapshot()
            self.assertEqual(result["status"], "matching_snapshot")
            self.assertFalse(result["restartRecommended"])
            self.assertEqual(result["remote"]["status"], "not_requested")
            scan.assert_not_called(); remote.assert_not_called()
        result["startup"]["commit"] = "modified-return-value"
        self.assertNotEqual(p.snapshot()["startup"]["commit"], "modified-return-value")

    def test_dirty_start_is_not_a_clean_commit_claim(self):
        self.source.write_text("uncommitted code\n")
        p = Provenance(self.root)
        with patch("orchestrator.provenance.remote_revision", return_value=self.remote()):
            p.refresh(True)
        result = p.snapshot()
        self.assertEqual(result["status"], "unverified_workspace")
        self.assertIsNone(result["startupMatchesRemote"])
        self.assertIsNone(result["checkoutMatchesRemote"])

    def test_edit_at_same_head_requires_restart_and_startup_is_immutable(self):
        p = Provenance(self.root); before = p.snapshot()["startup"]
        self.source.write_text("changed code\n"); p.refresh()
        result = p.snapshot()
        self.assertEqual(result["startup"], before)
        self.assertEqual(result["current"]["commit"], before["commit"])
        self.assertEqual(result["status"], "source_changed")
        self.assertTrue(result["restartRecommended"])

    def test_untracked_runtime_file_and_deleted_source_are_detected(self):
        for mode in ("added", "deleted"):
            with self.subTest(mode=mode):
                p = Provenance(self.root)
                if mode == "added": (self.root / "orchestrator" / "new.py").write_text("fixture\n")
                else: self.source.unlink()
                p.refresh()
                self.assertEqual(p.snapshot()["status"], "source_changed")

    def test_docs_only_commit_changes_revision_not_runtime_hash(self):
        p = Provenance(self.root)
        (self.root / "README.md").write_text("Documentation\n")
        self.git("add", "README.md"); self.git("commit", "-m", "Docs")
        p.refresh()
        result = p.snapshot()
        self.assertEqual(result["status"], "revision_changed")
        self.assertEqual(result["startup"]["fingerprint"], result["current"]["fingerprint"])
        self.assertNotEqual(result["startup"]["commit"], result["current"]["commit"])

    def test_ignored_credentials_never_enter_snapshot_or_source_hash(self):
        p = Provenance(self.root)
        (self.root / ".env").write_text("PRIVATE_FIXTURE_SECRET=private-value\n")
        with patch("orchestrator.provenance.remote_revision") as remote:
            p.refresh()
            remote.assert_not_called()
        result = p.snapshot()
        self.assertEqual(result["status"], "matching_snapshot")
        self.assertNotIn("private-value", json.dumps(result))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_symlink_source_is_not_followed(self):
        self.source.unlink()
        secret = self.root / ".env"; secret.write_text("sensitive fixture")
        self.source.symlink_to(secret)
        result = inspect(self.root)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["commit"])
        self.assertNotIn("sensitive fixture", json.dumps(result))

    def test_non_repository_nested_root_and_unborn_commit_are_unknown(self):
        nested = self.root / "nested"; nested.mkdir()
        self.assertEqual(inspect(nested)["status"], "unavailable")
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(inspect(folder)["status"], "unavailable")
            subprocess.run(["git", "init", "-b", "main", folder], check=True, capture_output=True)
            self.assertEqual(inspect(folder)["status"], "unavailable")

    def test_changed_during_inspection_is_unknown(self):
        with patch("orchestrator.provenance.fingerprint", side_effect=["a", "b"]):
            self.assertEqual(inspect(self.root)["status"], "unavailable")

    def test_oversized_runtime_source_is_unavailable(self):
        self.source.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
        self.assertEqual(inspect(self.root)["status"], "unavailable")

    def test_local_git_disables_optional_writes_and_fsmonitor(self):
        with patch("orchestrator.provenance.subprocess.run", return_value=subprocess.CompletedProcess([], 0, b"")) as run:
            git(self.root, "status", "--porcelain=v1")
        self.assertEqual(run.call_args.args[0][:5], ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C"])
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_stale_or_future_observations_never_claim_alignment(self):
        p = Provenance(self.root)
        with patch("orchestrator.provenance.remote_revision", return_value=self.remote()): p.refresh(True)
        self.assertTrue(p.snapshot()["checkoutMatchesRemote"])
        for offset in (901, -60):
            with patch("orchestrator.provenance.time.time", return_value=p.current["at"] + offset):
                result = p.snapshot()
                self.assertEqual(result["status"], "unknown")
                self.assertIsNone(result["restartRecommended"])
                self.assertIsNone(result["checkoutMatchesRemote"])

    def test_remote_origin_change_invalidates_prior_comparison(self):
        p = Provenance(self.root)
        with patch("orchestrator.provenance.remote_revision", return_value=self.remote()): p.refresh(True)
        self.git("remote", "set-url", "origin", "https://github.com/another/repo.git")
        p.refresh()
        self.assertFalse(p.snapshot()["remoteComparable"])
        self.assertIsNone(p.snapshot()["checkoutMatchesRemote"])
        other = {**self.remote(), "repository": "another/repo"}
        with patch("orchestrator.provenance.remote_revision", return_value=other): p.refresh(True)
        self.assertTrue(p.snapshot()["checkoutMatchesRemote"])
        self.assertIsNone(p.snapshot()["startupMatchesRemote"])

    def test_failed_remote_refresh_does_not_reuse_success(self):
        p = Provenance(self.root)
        with patch("orchestrator.provenance.remote_revision", return_value=self.remote()): p.refresh(True)
        with patch("orchestrator.provenance.remote_revision", return_value={**self.remote(), "status": "unavailable", "commit": None}): p.refresh(True)
        self.assertFalse(p.snapshot()["remoteFresh"])
        self.assertIsNone(p.snapshot()["checkoutMatchesRemote"])


class RemoteProvenanceTest(unittest.TestCase):
    def test_fixed_read_only_endpoints_and_default_branch(self):
        responses = [{"default_branch": "release/next"}, {"ref": "refs/heads/release/next", "object": {"type": "commit", "sha": "a" * 40}}]
        with patch("orchestrator.provenance.subprocess.run", side_effect=[subprocess.CompletedProcess([], 0, json.dumps(r).encode()) for r in responses]) as run:
            result = remote_revision("example/fixture")
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["branch"], "release/next")
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            ["gh", "api", "--method", "GET", "repos/example/fixture"],
            ["gh", "api", "--method", "GET", "repos/example/fixture/git/ref/heads/release%2Fnext"]])

    def test_bad_origin_malformed_response_and_errors_are_sanitized(self):
        with patch("orchestrator.provenance.subprocess.run") as run:
            for repository in (None, "https://untrusted/", "example/fixture?query=1"):
                self.assertEqual(remote_revision(repository)["status"], "unavailable")
            run.assert_not_called()
        for error in (subprocess.CalledProcessError(1, "gh", stderr=b"PRIVATE_SECRET"), ValueError("PRIVATE_SECRET")):
            with patch("orchestrator.provenance.subprocess.run", side_effect=error):
                result = remote_revision("example/fixture")
                self.assertEqual(result["status"], "unavailable")
                self.assertNotIn("PRIVATE_SECRET", json.dumps(result))
        with patch("orchestrator.provenance.subprocess.run", return_value=subprocess.CompletedProcess([], 0, b'[]')):
            self.assertEqual(remote_revision("example/fixture")["status"], "unavailable")
