import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from orchestrator.core import Ledger, Refusal
from orchestrator.resources import audit, remote_key, repository_identity
from orchestrator.workspaces import Registry, fingerprint


class ResourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.repo = self.root / "repo"
        self.git("init", "-q", str(self.repo))
        self.git("-C", str(self.repo), "config", "remote.origin.url", "git@github.com:Acme/Product.git")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        return subprocess.run(["git", *args], check=True, capture_output=True, env=env).stdout.decode().strip()

    def registry(self):
        registry = Registry(self.root / "platform", create=True)
        for wid in ("alpha", "beta"):
            ledger = Ledger(self.root / wid)
            ledger.initialize({"schemaVersion": 1, "brainId": "brain-" + wid, "repositories": [
                {"id": "repo", "path": str(self.repo), "projectId": "native-" + wid,
                 "ref": "origin/main", "policyProfile": "standard", "mergePolicy": "manual"}]})
            registry.register(wid, wid.title(), ledger.root)
        return registry

    def owner(self, registry, wid, status="starting"):
        ledger = registry.ledger(wid)
        with ledger.tx() as db:
            worker = {"id": "worker-" + wid, "repository": "repo", "queueId": "repo:fixture",
                      "status": status, "createdAt": 1000, "updatedAt": 1000, "hostId": "local", "threadId": None}
            db.execute("INSERT INTO workers VALUES(?,?,?)", (worker["id"], worker["queueId"], json.dumps(worker)))

    def test_conventional_ssh_https_and_case_are_one_identity(self):
        expected = remote_key("git@github.com:Acme/Product.git")
        for value in ("https://github.com/acme/product", "ssh://git@github.com/ACME/PRODUCT.git",
                      "https://github.com:443/acme/product.git/", "ssh://git@github.com:22/acme/product",
                      "https://github.com/ACME/PRODUCT.GIT"):
            self.assertEqual(remote_key(value), expected)
        self.assertNotEqual(remote_key("https://git.example.com/Acme/Repo"), remote_key("https://git.example.com/acme/repo"))
        self.assertNotEqual(remote_key("ssh://git@example.com:443/a/b"), remote_key("https://example.com:443/a/b"))

    def test_credentials_aliases_traversal_and_unsupported_remotes_refused(self):
        values = ("https://secret@github.com/acme/repo", "https://user:password@github.com/acme/repo",
                  "git@personal:acme/repo", "file:///private/repo", "/private/repo", "ext::bad",
                  "https://github.com/acme/../repo", "https://github.com/acme/repo?token=secret",
                  "ssh://root@github.com/acme/repo", "https://github.com/acme/%72epo",
                  "https://github.com/acme/repo\nsecret", "https://github.com:bad/acme/repo",
                  "https://github.com//acme/repo")
        for value in values:
            with self.subTest(value=value), self.assertRaises(Refusal): remote_key(value)

    def test_repository_worktree_and_symlink_share_local_resource(self):
        self.git("-C", str(self.repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", "fixture")
        worktree = self.root / "worktree"
        self.git("-C", str(self.repo), "worktree", "add", "--detach", str(worktree))
        alias = self.root / "alias"; alias.symlink_to(self.repo)
        primary = repository_identity(self.repo)
        self.assertEqual(primary["status"], "observed")
        self.assertEqual(primary, repository_identity(worktree))
        self.assertEqual(primary, repository_identity(alias))

    def test_separate_checkouts_share_remote_but_not_local_identity(self):
        other = self.root / "other"
        self.git("init", "-q", str(other))
        self.git("-C", str(other), "config", "remote.origin.url", "https://github.com/acme/product")
        first, second = repository_identity(self.repo), repository_identity(other)
        self.assertEqual(len(set(first["keys"]) & set(second["keys"])), 1)
        self.assertEqual(len(set(first["keys"]) | set(second["keys"])), 3)

    def test_missing_and_multiple_origins_keep_partial_identity_not_safe_admission(self):
        self.git("-C", str(self.repo), "config", "--unset-all", "remote.origin.url")
        observed = repository_identity(self.repo)
        self.assertEqual(observed["status"], "unknown")
        self.assertEqual(len(observed["keys"]), 1)
        self.git("-C", str(self.repo), "config", "--add", "remote.origin.url", "https://github.com/a/b")
        self.git("-C", str(self.repo), "config", "--add", "remote.origin.url", "https://github.com/a/c")
        self.assertEqual(repository_identity(self.repo)["status"], "unknown")
        self.assertEqual(repository_identity(self.root / "missing")["keys"], [])

    def test_remote_credentials_are_not_returned_or_in_errors(self):
        secret = "fixture-secret-do-not-output"
        self.git("-C", str(self.repo), "config", "remote.origin.url", "https://user:" + secret + "@github.com/a/b")
        result = repository_identity(self.repo)
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(str(self.repo), json.dumps(result))

    def test_unconfigured_checkout_is_unknown_not_an_audit_failure(self):
        for value in (None, "", ".", "repo"):
            self.assertEqual(repository_identity(value)["status"], "unknown")
        registry = self.registry()
        ledger = registry.ledger("alpha")
        with ledger.tx() as db:
            repo = ledger.get(db, "repos", "repo"); repo["path"] = None
            ledger.put(db, "repos", "repo", repo)
        result = audit(registry)
        self.assertEqual(result["repositories"][0]["status"], "unknown")
        self.assertEqual(result["issues"][0]["code"], "identity_unknown")

    def test_inherited_git_targeting_and_includes_are_ignored(self):
        expected = repository_identity(self.repo)
        self.git("-C", str(self.repo), "config", "include.path", str(self.root / "not-present"))
        with patch.dict(os.environ, {"GIT_DIR": "/nonexistent", "GIT_CONFIG_COUNT": "1",
                                     "GIT_CONFIG_KEY_0": "remote.origin.url", "GIT_CONFIG_VALUE_0": "bad"}):
            self.assertEqual(repository_identity(self.repo), expected)

    def test_audit_detects_cross_workspace_ownership_without_mutation(self):
        registry = self.registry()
        self.owner(registry, "alpha"); self.owner(registry, "beta", "blocked")
        before = {}
        for row in registry.list():
            with registry.ledger(row["id"]).tx() as db:
                before[row["id"]] = fingerprint(db)
        result = audit(registry)
        self.assertFalse(result["executionAuthorized"])
        self.assertFalse(result["atomicSnapshot"])
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(len(result["aliases"]), 2)
        self.assertEqual(len(result["owners"]), 2)
        for row in registry.list():
            with registry.ledger(row["id"]).tx() as db:
                self.assertEqual(fingerprint(db), before[row["id"]])
        self.assertFalse((registry.root / "admission.sqlite3").exists())

    def test_unavailable_ledger_and_unknown_runner_are_visible(self):
        registry = self.registry(); self.owner(registry, "alpha")
        ledger = registry.ledger("alpha")
        with ledger.tx() as db:
            meta = ledger.get(db, "meta", 1); meta["runner"] = {"workerId": "worker-alpha"}
            ledger.put(db, "meta", 1, meta)
        os.chmod(self.root / "beta" / "ledger.sqlite3", 0o644)
        try:
            result = audit(registry)
        finally:
            os.chmod(self.root / "beta" / "ledger.sqlite3", 0o600)
        self.assertEqual({row["code"] for row in result["issues"]}, {"runner_global_identity_unknown", "ledger_unavailable"})

    def test_cli_is_explicit_read_only_and_platform_wide(self):
        registry = self.registry()
        result = subprocess.run([sys.executable, "-m", "orchestrator.cli", "--platform", str(registry.root), "platform-resources"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["repositories"]), 2)
        bad = subprocess.run([sys.executable, "-m", "orchestrator.cli", "--platform", str(registry.root),
                              "--workspace", "alpha", "platform-resources"], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("omit --workspace", bad.stderr)
        self.assertFalse((registry.root / "admission.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
