import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from orchestrator import portfolio_metrics as pm
from orchestrator.core import Refusal, digest
from orchestrator.repository import aggregate, measure, report
import test_workspaces


def metric(rid="repo", *, local="local", remote="origin", commit="a"*40, lines=3, at=10):
    repo = {"id": rid, "path": "/fixture/"+rid, "ref": "main"}
    vector = {"files": 1, "lines": lines, "characters": lines*5, "bytes": lines*5}
    return {"schemaVersion": 1, "repository": rid, "commit": commit, "at": at,
            "status": "measured", "measurementPolicy": pm.POLICY,
            "configurationHash": pm.configuration(repo), "workspaceId": "one",
            "identity": {"version": 1, "configurationHash": pm.configuration(repo),
                "checkoutHash": digest(repo["path"]), "localKey": "repo-local:"+digest(local),
                "remoteKey": "repo-remote:"+digest(remote) if remote else None,
                "status": "observed" if remote else "local_only"},
            "groups": {"source": dict(vector)}, **vector}


class CountingTest(unittest.TestCase):
    def summarize(self, *rows): return pm.summarize(list(rows))

    def test_same_origin_and_commit_clones_count_once(self):
        value = self.summarize(metric(), metric("clone", local="clone"))
        self.assertEqual(value["aggregate"]["lines"], 3)
        self.assertEqual(value["coverage"]["duplicateAliases"], 1)
        self.assertEqual(len(value["snapshots"][0]["aliases"]), 2)

    def test_worktrees_without_origin_share_local_identity(self):
        value = self.summarize(metric(remote=None), metric("linked", remote=None))
        self.assertEqual(value["aggregate"]["lines"], 3)
        self.assertEqual(value["coverage"]["localOnlySnapshots"], 1)

    def test_different_commits_are_distinct_snapshots(self):
        value = self.summarize(metric(), metric("branch", commit="b"*40))
        self.assertEqual(value["aggregate"]["lines"], 6)
        self.assertEqual(value["aggregate"]["measuredRepositories"], 2)

    def test_fork_equal_commit_does_not_collapse(self):
        value = self.summarize(metric(), metric("fork", local="fork", remote="fork"))
        self.assertEqual(value["aggregate"]["lines"], 6)

    def test_shared_local_conflicting_remote_is_excluded(self):
        value = self.summarize(metric(), metric("linked", remote="changed"))
        self.assertIsNone(value["aggregate"]["lines"])
        self.assertEqual(value["coverage"]["excludedRows"], 2)
        self.assertEqual(value["coverage"]["issues"][0]["codes"], ["shared_local_origin_conflict"])

    def test_same_snapshot_conflicting_counts_excludes_both_even_if_newer(self):
        value = self.summarize(metric(), metric("clone", local="clone", lines=9, at=20))
        self.assertIsNone(value["aggregate"]["lines"])
        self.assertEqual(value["coverage"]["conflictingSnapshots"], 1)
        self.assertEqual(value["snapshots"][0]["status"], "conflict")

    def test_different_group_counts_are_a_conflict(self):
        other = metric("clone", local="clone")
        other["groups"]["tests"] = other["groups"].pop("source")
        self.assertEqual(self.summarize(metric(), other)["coverage"]["conflictingSnapshots"], 1)

    def test_legacy_metrics_remain_readable_but_excluded(self):
        row = metric(); row.pop("identity"); row.pop("measurementPolicy")
        value = self.summarize(row)
        self.assertEqual(value["repositories"][0]["lines"], 3)
        self.assertIsNone(value["aggregate"]["lines"])
        self.assertIn("identity_refresh_required", value["coverage"]["issues"][0]["codes"])

    def test_changed_path_or_ref_needs_refresh(self):
        row = metric()
        for field, changed in (("path", "/new/checkout"), ("ref", "other")):
            repo = {"id": "repo", "path": "/fixture/repo", "ref": "main", field: changed}
            state = {"repositories": [repo], "metrics": [row], "workers": []}
            value = aggregate(state)
            self.assertIsNone(value["aggregate"]["lines"])
            self.assertIn("repository_configuration_changed", value["coverage"]["issues"][0]["codes"])

    def test_removed_repository_does_not_survive_in_totals(self):
        value = aggregate({"repositories": [], "metrics": [metric()], "workers": []})
        self.assertIsNone(value["aggregate"]["lines"])
        self.assertEqual(value["repositories"], [])

    def test_newest_failure_does_not_fall_back(self):
        good = metric(); bad = {**good, "at": 20, "status": "unavailable"}
        rows = pm.candidates({"repositories": [{"id": "repo", "path": "/fixture/repo", "ref": "main"}], "metrics": [bad, good]})
        self.assertIsNone(self.summarize(*rows)["aggregate"]["lines"])
        self.assertEqual(rows[0]["at"], 20)

    def test_invalid_observation_time_cannot_hide_behind_old_success(self):
        good = metric(); bad = {**good, "at": None}
        rows = pm.candidates({"repositories": [{"id": "repo", "path": "/fixture/repo", "ref": "main"}], "metrics": [good, bad]})
        value = self.summarize(*rows)
        self.assertIsNone(value["aggregate"]["lines"])
        self.assertIn("observation_time_invalid", value["coverage"]["issues"][0]["codes"])

    def test_equal_time_observation_conflict_is_deterministic(self):
        a, b = metric(), metric(lines=9)
        state = {"repositories": [{"id": "repo", "path": "/fixture/repo", "ref": "main"}], "metrics": [a, b]}
        one = self.summarize(*pm.candidates(state))
        two = self.summarize(*pm.candidates({**state, "metrics": [b, a]}))
        self.assertEqual(one, two)
        self.assertIsNone(one["aggregate"]["lines"])

    def test_unknown_policy_invalid_identity_and_counts_are_excluded(self):
        for change in ({"measurementPolicy": "future-v99"}, {"commit": None}, {"files": True},
                       {"lines": -1}, {"bytes": 2**54}, {"groups": {}}, {"identity": {}},
                       {"identity": {**metric()["identity"], "localKey": "raw-secret"}},
                       {"identity": {**metric()["identity"], "version": True}}):
            with self.subTest(change=change):
                value = self.summarize(metric() | change)
                self.assertIsNone(value["aggregate"]["lines"])
                self.assertTrue(value["coverage"]["refreshRequired"])

    def test_empty_measured_snapshot_is_zero_unmeasured_is_null(self):
        row = metric(); row.update({k: 0 for k in pm.FIELDS}); row["groups"] = {}
        self.assertEqual(self.summarize(row)["aggregate"]["lines"], 0)
        self.assertIsNone(self.summarize()["aggregate"]["lines"])

    def test_read_path_is_pure_and_does_not_modify_inputs(self):
        rows = [metric(), metric("clone", local="clone")]; before = copy.deepcopy(rows)
        with patch.object(pm, "repository_identity", side_effect=AssertionError("No Git")), \
             patch.object(Path, "resolve", side_effect=AssertionError("No filesystem resolution")):
            value = pm.summarize(rows)
        self.assertEqual(rows, before)
        self.assertEqual(value, pm.summarize(list(reversed(rows))))

    def test_bound_refuses_instead_of_silently_truncating(self):
        with self.assertRaises(Refusal): pm.summarize([metric()]*10001)

    def test_large_portfolio_groups_in_linear_space(self):
        # 32 workspace scopes, 100 repositories each. Same origin/commit snapshots
        # must not be multiplied by 32; deterministic output is part of the test.
        rows = [{**metric(str(r), local=f"{w}-{r}", remote=str(r)), "workspaceId": str(w)}
                for w in range(32) for r in range(100)]
        start = time.perf_counter(); value = pm.summarize(rows)
        self.assertLess(time.perf_counter()-start, 5)
        self.assertEqual(value["aggregate"]["lines"], 300)
        self.assertEqual(value["coverage"]["duplicateAliases"], 3100)
        self.assertEqual(len(value["snapshots"]), 100)
        self.assertEqual(pm.summarize(list(reversed(rows))), value)


class GitIdentityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.repo = self.root / "main"
        self.git(self.root, "init", "-q", str(self.repo))
        (self.repo / "app.py").write_text("# café\nprint('hello')\n")
        self.git(self.repo, "add", "."); self.git(self.repo, "commit", "-qm", "fixture")
        self.git(self.repo, "remote", "add", "origin", "git@github.com:Fixture/Portfolio.git")

    def git(self, path, *args):
        return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.invalid", "-C", str(path), *args],
            capture_output=True, check=True, text=True).stdout.strip()

    def measure(self, path, name="repo"):
        return measure({"id": name, "path": str(path), "ref": "HEAD"})

    def test_real_clone_worktree_fork_and_https_normalization(self):
        clone, linked = self.root / "clone", self.root / "linked"
        self.git(self.root, "clone", "-q", "--no-hardlinks", str(self.repo), str(clone))
        self.git(clone, "remote", "set-url", "origin", "https://github.com/fixture/portfolio.git")
        self.git(self.repo, "worktree", "add", "-q", "--detach", str(linked))
        a, b, c = self.measure(self.repo), self.measure(clone, "clone"), self.measure(linked, "linked")
        self.assertEqual(a["identity"]["localKey"], c["identity"]["localKey"])
        self.assertNotEqual(a["identity"]["localKey"], b["identity"]["localKey"])
        self.assertEqual(a["identity"]["remoteKey"], b["identity"]["remoteKey"])
        def row(m): return {**m, "workspaceId": "one", "configurationHash": m["identity"]["configurationHash"]}
        self.assertEqual(pm.summarize([row(m) for m in (a, b, c)])["aggregate"]["lines"], 2)
        self.git(clone, "remote", "set-url", "origin", "https://github.com/fixture/fork.git")
        self.assertEqual(pm.summarize([row(a), row(self.measure(clone))])["aggregate"]["lines"], 4)

    def test_credential_remote_is_not_retained_or_used_for_clone_identity(self):
        self.git(self.repo, "remote", "set-url", "origin", "https://user:SECRET@github.com/fixture/portfolio.git")
        value = self.measure(self.repo)
        self.assertEqual(value["identity"]["status"], "local_only")
        self.assertIsNone(value["identity"]["remoteKey"])
        self.assertNotIn("SECRET", json.dumps(value))
        self.assertNotIn(str(self.repo), json.dumps(value["identity"]))

    def test_symlink_alias_resolves_only_at_collection(self):
        alias = self.root / "alias"; alias.symlink_to(self.repo, target_is_directory=True)
        a, b = self.measure(self.repo), self.measure(alias)
        self.assertEqual(a["identity"]["localKey"], b["identity"]["localKey"])
        self.assertEqual(a["identity"]["checkoutHash"], b["identity"]["checkoutHash"])
        self.assertNotEqual(a["identity"]["configurationHash"], b["identity"]["configurationHash"])

    def test_unavailable_path_and_identity_drift_do_not_invent_identity(self):
        self.assertEqual(self.measure(self.root / "absent")["status"], "unavailable")
        before = pm.observe_identity({"id": "repo", "path": str(self.repo), "ref": "HEAD"})
        with patch.object(pm, "observe_identity", side_effect=[before, {**before, "remoteKey": "repo-remote:"+"b"*64}]):
            value = self.measure(self.repo)
        self.assertEqual(value["status"], "measured")
        self.assertEqual(value["identity"]["status"], "unavailable")

    def test_inherited_git_targeting_does_not_mislabel_another_repository(self):
        other = self.root / "other"; self.git(self.root, "init", "-q", str(other))
        (other / "b.py").write_text("other\n"*50)
        self.git(other, "add", "."); self.git(other, "commit", "-qm", "other")
        with patch.dict(os.environ, {"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other)}):
            value = self.measure(self.repo)
        self.assertEqual(value["lines"], 2)
        self.assertEqual(value["commit"], self.git(self.repo, "rev-parse", "HEAD"))


class PortfolioIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.fx = test_workspaces.WorkspaceTest(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.registry = self.fx.registry
        for wid, ledger in (("a", self.fx.a), ("b", self.fx.b)):
            self.registry.register(wid, wid.upper(), ledger.root)
            with ledger.tx() as db:
                ledger.put(db, "repos", wid, {"id": wid, "path": "/fixture/"+wid, "ref": "main"})
            ledger.metric(metric(wid, local=wid))

    def test_registry_and_workspace_and_report_use_same_counting_contract(self):
        before = [self.fx.contents(x) for x in (self.fx.a, self.fx.b)]
        data = self.registry.summary()
        self.assertEqual(data["aggregate"]["lines"], 3)
        self.assertEqual(data["codeCoverage"]["duplicateAliases"], 1)
        self.assertEqual([w["metrics"]["lines"] for w in data["workspaces"]], [3, 3])
        self.assertEqual(self.registry.summary({"a"})["codeCoverage"]["duplicateAliases"], 0)
        self.assertEqual(self.registry.summary({"b"})["codeSnapshots"][0]["aliases"][0]["workspaceId"], "b")
        self.assertEqual(before, [self.fx.contents(x) for x in (self.fx.a, self.fx.b)])
        text = report(self.registry.ledger("a").snapshot())
        self.assertIn("## Counting coverage", text)
        self.assertIn("included", text)

    def test_new_failure_and_foreign_workspace_dont_leak_into_selected_total(self):
        self.fx.b.metric({**metric("b", local="b", at=20), "status": "unavailable"})
        self.assertEqual(self.registry.summary({"a"})["aggregate"]["lines"], 3)
        self.assertEqual(self.registry.summary({"a"})["codeCoverage"]["excludedRows"], 0)
        self.assertIsNone(self.registry.summary({"b"})["aggregate"]["lines"])


if __name__ == "__main__": unittest.main()
