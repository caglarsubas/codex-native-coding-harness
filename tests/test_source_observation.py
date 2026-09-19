"""Real Git fixtures only; never inspect product repositories or live state."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from orchestrator import run_authority as runs, source_observation as source
from orchestrator.core import Ledger, PREFLIGHT_CHECKS, Refusal, canonical, digest
from orchestrator.observations import capture
import test_core
import test_dispatch_admission
import test_ownership_settlement
import test_result_review


class GitFixture:
    def make_git(self):
        temporary = tempfile.TemporaryDirectory(prefix="source-fixture-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repo = self.root / "repo"; self.repo.mkdir()
        self.git("init", "--template=", "-b", "main")
        self.git("config", "user.name", "Source fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repo / "src").mkdir()
        (self.repo / "src/example.py").write_text("original\n")
        self.git("add", "--", "src/example.py"); self.git("commit", "-m", "base", "--no-gpg-sign")
        self.base = self.git("rev-parse", "HEAD")
        self.git("switch", "-c", "codex/test-001")
        self.result = self.change("src/example.py", "result\n")
        info = (self.repo / ".git").stat()
        self.key = "repo-local:"+digest({"device": info.st_dev, "inode": info.st_ino})

    def git(self, *args):
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
               "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": ""}
        return subprocess.check_output(["/usr/bin/git", "-c", "core.hooksPath="+os.devnull,
            "-c", "core.fsmonitor=false", *args], cwd=self.repo, env=env, stderr=subprocess.DEVNULL).decode().strip()

    def change(self, path, content):
        target = self.repo / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(content)
        self.git("add", "--", path); self.git("commit", "-m", "change", "--no-gpg-sign")
        return self.git("rev-parse", "HEAD")

    def inspect(self, **fields):
        return source.inspect_source(**({"path": str(self.repo), "key": self.key, "base": self.base,
            "result": self.result, "branch": "codex/test-001", "allowed": ["src/example.py"]} | fields))

    def disk(self):
        return {str(p.relative_to(self.repo)): (p.stat().st_ino, p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in self.repo.rglob("*") if p.is_file()}


class GitObservationTest(GitFixture, unittest.TestCase):
    def setUp(self): self.make_git()

    def test_exact_structure_without_worktree_reads_or_git_writes(self):
        (self.repo / "src/example.py").write_text("uncommitted and deliberately different\n")
        before = self.disk(); observed = self.inspect()
        self.assertEqual(before, self.disk())
        self.assertEqual(observed["baseSHA"], self.base); self.assertEqual(observed["commit"], self.result)
        self.assertEqual(observed["changedPaths"], ["src/example.py"])
        self.assertEqual(observed["outOfScope"], [])
        self.assertTrue(observed["baseAncestor"]); self.assertTrue(observed["diffComplete"])
        self.assertFalse(observed["remoteObserved"]); self.assertFalse(observed["worktreeInspected"])
        self.assertFalse(observed["semanticReviewPerformed"])
        self.assertEqual(observed["resultTree"], self.git("rev-parse", self.result+"^{tree}"))
        self.assertEqual(observed["changes"][0]["newObject"], self.git("rev-parse", self.result+":src/example.py"))

    def test_rename_keeps_both_paths_and_reports_outside_scope(self):
        self.git("mv", "src/example.py", "outside.py"); self.git("commit", "-m", "move", "--no-gpg-sign")
        observed = self.inspect(result=self.git("rev-parse", "HEAD"))
        self.assertEqual(observed["changedPaths"], ["outside.py", "src/example.py"])
        self.assertEqual(observed["outOfScope"], ["outside.py"])
        self.assertEqual([p["change"] for p in observed["changes"]], ["A", "D"])

    def test_linked_worktree_and_packed_refs(self):
        linked = self.root / "linked"
        self.git("switch", "main")
        self.git("worktree", "add", str(linked), "codex/test-001")
        self.git("pack-refs", "--all", "--prune")
        self.assertEqual(self.inspect(path=str(linked))["commit"], self.result)

    def test_packed_objects_are_supported(self):
        self.git("repack", "-ad")
        self.assertEqual(self.inspect()["changedPaths"], ["src/example.py"])

    def test_original_config_replacements_and_inherited_git_env_are_ignored(self):
        marker = self.root / "MUST-NOT-EXIST"
        config = self.repo / ".git/config"
        config.write_text(config.read_text()+f'\n[core]\n fsmonitor = touch {marker}\n'
            f'[diff]\n external = touch {marker}\n[extensions]\n worktreeConfig = true\n'
            f'[include]\n path = {self.root}/nonexistent-config\n'
            '[remote "trap"]\n url = ext::invalid\n promisor = true\n')
        replacements = self.repo / ".git/refs/replace"; replacements.mkdir()
        (replacements / self.result).write_text(self.base+"\n")
        with patch.dict(os.environ, {"GIT_DIR": "/missing", "GIT_WORK_TREE": "/missing",
                "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "include.path", "GIT_CONFIG_VALUE_0": "/missing",
                "GIT_OBJECT_DIRECTORY": "/missing", "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/missing"}):
            self.assertEqual(self.inspect()["commit"], self.result)
        self.assertFalse(marker.exists())

    def test_missing_local_object_never_fetches(self):
        self.git("config", "remote.origin.url", "ext::unavailable")
        self.git("config", "remote.origin.promisor", "true")
        obj = self.repo / ".git/objects" / self.result[:2] / self.result[2:]
        obj.rename(self.root / "saved-fixture-object")
        with self.assertRaises(Refusal): self.inspect()

    def test_unrelated_base_and_wrong_tip_refuse(self):
        with self.assertRaisesRegex(Refusal, "tip"): self.inspect(result=self.base, base=self.result)
        self.git("switch", "--orphan", "other"); other = self.change("unrelated.py", "other\n")
        with self.assertRaisesRegex(Refusal, "Git evidence"): self.inspect(base=other)

    def test_shallow_grafts_and_alternates_refuse(self):
        for name in ("shallow", "info/grafts", "objects/info/alternates", "objects/info/http-alternates"):
            with self.subTest(name=name):
                item = self.repo / ".git" / name; item.parent.mkdir(parents=True, exist_ok=True); item.write_text("fixture\n")
                try:
                    with self.assertRaisesRegex(Refusal, "separate adapter"): self.inspect()
                finally: item.unlink()  # Only the exact synthetic file created above.

    def test_object_and_ref_symlinks_refuse(self):
        trap = self.repo / ".git/objects/trap"; trap.symlink_to(self.root)
        with self.assertRaisesRegex(Refusal, "indirection"): self.inspect()
        trap.unlink()
        ref = self.repo / ".git/refs/heads/codex/test-001"; saved = self.root / "saved-ref"; ref.rename(saved); ref.symlink_to(saved)
        with self.assertRaises(Refusal): self.inspect()

    def test_changed_symlink_and_gitlink_refuse(self):
        (self.repo / "link").symlink_to("src/example.py")
        self.git("add", "link"); self.git("commit", "-m", "link", "--no-gpg-sign")
        with self.assertRaisesRegex(Refusal, "symlinks or submodules"): self.inspect(result=self.git("rev-parse", "HEAD"))
        self.git("update-index", "--add", "--cacheinfo", "160000", self.base, "module")
        self.git("commit", "-m", "gitlink", "--no-gpg-sign")
        with self.assertRaisesRegex(Refusal, "symlinks or submodules"):
            self.inspect(base=self.git("rev-parse", "HEAD^"), result=self.git("rev-parse", "HEAD"))

    def test_wrong_identity_and_branch_injection_refuse_before_git(self):
        for fields in ({"key": "repo-local:"+"f"*64}, {"branch": "codex/../HEAD"}, {"branch": "codex/x\n"},
                       {"result": "f"*64}, {"base": self.result}, {"path": str(self.root / "missing")}):
            with self.subTest(fields=fields), patch.object(source, "git_read", side_effect=AssertionError("no Git")):
                with self.assertRaises(Refusal): self.inspect(**fields)

    def test_branch_moved_during_read_refuses(self):
        original = source.git_read
        def moved(*args, **kwargs):
            output = original(*args, **kwargs)
            if "diff-tree" in args[1]: self.git("update-ref", "refs/heads/codex/test-001", self.base)
            return output
        with patch.object(source, "git_read", side_effect=moved):
            with self.assertRaisesRegex(Refusal, "changed during"): self.inspect()

    def test_output_and_time_are_bounded(self):
        with self.assertRaisesRegex(Refusal, "bound"): source.git_read(self.repo / ".git", ["cat-file", "commit", self.result], bound=1)
        with self.assertRaisesRegex(Refusal, "timed out"): source.git_read(self.repo / ".git", ["cat-file", "commit", self.result], timeout=0)

    def test_diff_parser_rejects_truncation_ambiguous_paths_and_size(self):
        header = f":100644 100644 {self.base} {self.result} M\0".encode()
        for raw in (b"", header+b"path", header+b"../bad\0", header+b"src/*\0", header+b"\xff\0",
                    (header+b"same\0")*2, b"".join(header+f"src/{i}\0".encode() for i in range(201))):
            with self.subTest(raw=raw[:100]), self.assertRaises((Refusal, UnicodeError)): source.changes(raw)

    def test_no_change_commit_and_large_diff_refuse(self):
        self.git("commit", "--allow-empty", "-m", "empty", "--no-gpg-sign")
        with self.assertRaisesRegex(Refusal, "nonempty"):
            self.inspect(base=self.result, result=self.git("rev-parse", "HEAD"))
        for i in range(201): (self.repo / "src" / f"p{i}").write_text("fixture\n")
        self.git("add", "src"); self.git("commit", "-m", "too broad", "--no-gpg-sign")
        with self.assertRaisesRegex(Refusal, "200 changed paths"):
            self.inspect(result=self.git("rev-parse", "HEAD"))

    def test_commit_rehash_catches_wrong_bytes(self):
        with patch.object(source, "git_read", return_value=b"tree "+b"a"*40+b"\n\nwrong content"):
            with self.assertRaisesRegex(Refusal, "object does not match"): source.commit_tree(self.repo, self.base)


class SourceRetentionTest(GitFixture, unittest.TestCase):
    def setUp(self):
        self.make_git()
        initialize, seed = Ledger.initialize, test_core.seed
        def initialize_fixture(ledger, config):
            config = copy.deepcopy(config)
            for repo in config["repositories"]:
                if repo["id"] == "a": repo["path"] = str(self.repo)
            return initialize(ledger, config)
        def seed_fixture(*args, **kwargs): return {**seed(*args, **kwargs), "baseSHA": self.base}
        def preflight(fixture):
            q = fixture.fx.fx.q
            fixture.ledger.preflight(fixture.token, q["id"], {"seedHash": q["seedHash"], "packetDigest": q["packetDigest"],
                "baseSHA": self.base, "projectId": "project-a", "checks": {k: True for k in PREFLIGHT_CHECKS}, "evidence": ["fixture"]})
        for mock in (patch.object(Ledger, "initialize", initialize_fixture), patch.object(test_core, "seed", seed_fixture),
                     patch.object(test_dispatch_admission, "KEY", self.key), patch.object(test_ownership_settlement, "KEY", self.key),
                     patch.object(test_dispatch_admission.DispatchAdmissionTest, "preflight", preflight)):
            mock.start(); self.addCleanup(mock.stop)
        self.fx = test_result_review.ResultReviewTest(); self.fx.setUp(); self.addCleanup(self.fx.tearDown)
        self.ledger, self.token, self.store, self.wid = self.fx.ledger, self.fx.token, self.fx.store, self.fx.wid
        self.api = source.SourceObserver(self.fx.fx.bridge)
        self.intent = self.fx.intent
        artifact = self.fx.artifact
        self.fx.artifact = lambda subject, raw=b"Independent fixture proof.", commit=None: artifact(subject, raw, commit or self.result)

    def request(self, **fields):
        return {"id": "source-1", "expectedRevision": self.ledger.snapshot()["meta"]["revision"],
            "settlementHash": self.fx.worker()["ownershipSettlementHash"], "commit": self.result, **fields}

    def observe(self, request=None): return self.api.observe(self.token, self.wid, request or self.request())

    def review_request(self, receipt, outcome="accepted", **changes):
        request = self.fx.evidence(commit=self.result)
        result = request["result"]; result["pr"]["headSHA"] = result["ci"]["headSHA"] = self.result
        for check in result["ci"]["checks"]: check["headSHA"] = self.result
        result["evidence"]["source"] = {"status": "verified", "artifactId": receipt["artifactId"], "observedAt": time.time()}
        result.update(changes); result["observedAt"] = time.time()
        return self.fx.request(result, outcome)

    def test_retains_exact_bytes_without_acceptance_or_shared_changes(self):
        before = self.store.snapshot(); worker = self.fx.worker(); state = self.ledger.snapshot()
        receipt = self.observe(); report = self.ledger.document(receipt["observationHash"])
        self.assertEqual(report["kind"], source.KIND); self.assertEqual(report["intentHash"], digest(self.intent))
        self.assertEqual(report["changedPaths"], ["src/example.py"]); self.assertTrue(receipt["sourceWithinScope"])
        self.assertFalse(receipt["packetAccepted"]); self.assertFalse(receipt["nativeCallMade"])
        self.assertEqual(self.fx.worker(), worker); self.assertEqual(self.store.snapshot(), before)
        after = self.ledger.snapshot()
        self.assertEqual(after["queue"], state["queue"])
        for k in ("paused", "pilotPassed", "heartbeat", "runner", "runAuthority"):
            self.assertEqual(after["meta"][k], state["meta"][k])
        with self.ledger.tx() as db:
            info, raw = source.artifact_in(db, receipt["artifactId"], self.intent, "source", self.result)
        self.assertEqual(raw, canonical(report).encode()); self.assertEqual(info["provenance"], source.PROVENANCE)

    def test_replay_after_pause_expiry_and_fence_never_reads_git_or_refreshes(self):
        request = self.request(); first = self.observe(request)
        self.fx.fx.fx.fx.fx.fx.command("pause")
        (self.ledger.root / "admission-fence.json").touch(mode=0o600)
        before = self.fx.logical()
        with patch.object(source, "inspect_source", side_effect=AssertionError("historical read")), \
             patch.object(self.store, "clock", return_value=time.time()+10000):
            self.assertEqual(self.observe(request), first)
        self.assertEqual(before, self.fx.logical())
        with self.assertRaisesRegex(Refusal, "different content"): self.observe({**request, "commit": "f"*40})

    def test_bad_requests_wrong_controller_and_stale_revision_refuse_without_io(self):
        for fields in ({"expectedRevision": 0}, {"path": "/arbitrary"}, {"settlementHash": "f"*64}, {"commit": "HEAD"}):
            before = self.fx.logical()
            with patch.object(source, "inspect_source", side_effect=AssertionError("invalid request")):
                with self.assertRaises(Refusal): self.observe(self.request(**fields))
            self.assertEqual(before, self.fx.logical())
        with self.assertRaises(Refusal): self.api.observe("wrong", self.wid, self.request())
        with self.assertRaises(Refusal): self.api.observe(self.token, "foreign", self.request())

    def test_pause_before_io_and_during_io_refuses_without_source_proof(self):
        original = source.inspect_source
        def paused(*args, **kwargs):
            result = original(*args, **kwargs); self.fx.fx.fx.fx.fx.fx.command("pause"); return result
        with patch.object(source, "inspect_source", side_effect=paused):
            with self.assertRaisesRegex(Refusal, "paused"): self.observe()
        before = self.fx.logical()
        with patch.object(source, "inspect_source", side_effect=AssertionError("paused")):
            with self.assertRaisesRegex(Refusal, "paused"): self.observe()
        self.assertEqual(before, self.fx.logical())
        with self.ledger.tx() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots WHERE kind=?", (source.KIND,)).fetchone()[0], 0)

    def test_event_failure_rolls_back_proof_and_receipt(self):
        before = self.fx.logical(); shared = self.store.snapshot()
        with patch.object(self.api.ledger, "event", side_effect=RuntimeError("fixture retention interruption")):
            with self.assertRaises(RuntimeError): self.observe()
        self.assertEqual(before, self.fx.logical()); self.assertEqual(shared, self.store.snapshot())
        self.assertTrue(self.observe()["sourceWithinScope"])

    def test_source_proof_can_support_separate_review_but_never_ci(self):
        receipt = self.observe(); request = self.review_request(receipt)
        result = self.fx.review(request)
        self.assertTrue(result["packetAccepted"])
        self.assertEqual(self.fx.worker()["evidence"]["runtime"]["status"], "unverified")

    def test_collected_paths_cannot_be_replaced_by_caller_inventory(self):
        receipt = self.observe()
        request = self.review_request(receipt, "changes_required", changedPaths=["other.py"])
        with self.assertRaisesRegex(Refusal, "collected source evidence"): self.fx.review(request)

    def test_missing_collector_journal_cannot_fall_back_to_generic_proof(self):
        receipt = self.observe(); request = self.review_request(receipt)
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (receipt["observationHash"],))
        with self.assertRaises(Refusal): self.fx.review(request)

    def test_removed_provenance_label_cannot_fall_back_to_generic_proof(self):
        receipt = self.observe(); request = self.review_request(receipt)
        with self.ledger.tx() as db:
            data = json.loads(db.execute("SELECT data FROM artifact_versions WHERE id=?", (receipt["artifactId"],)).fetchone()[0])
            del data["provenance"]
            db.execute("UPDATE artifact_versions SET data=? WHERE id=?", (canonical(data), receipt["artifactId"]))
        with self.assertRaisesRegex(Refusal, "provenance"): self.fx.review(request)

    def test_any_collector_marker_requires_complete_provenance(self):
        with self.ledger.tx() as db:
            for metadata in ({"sourceObservationHash": "a"*64}, {"key": "source-observation:fixture"},
                             {"provenance": source.PROVENANCE}):
                with self.subTest(metadata=metadata), self.assertRaisesRegex(Refusal, "provenance"):
                    source.validate_source_proof(db, metadata, b"ordinary assertion", self.intent, {}, {})
            self.assertIsNone(source.validate_source_proof(db, {"key": "caller-fixture"}, b"ordinary assertion", self.intent, {}, {}))

    def test_out_of_scope_is_retained_but_cannot_verify_source(self):
        self.result = self.change("outside.py", "outside\n")
        receipt = self.observe(); self.assertFalse(receipt["sourceWithinScope"])
        request = self.review_request(receipt, "changes_required", changedPaths=["outside.py", "src/example.py"])
        with self.assertRaisesRegex(Refusal, "out-of-scope"): self.fx.review(request)
        request["result"]["evidence"]["source"]["status"] = "failed"
        request = self.fx.request(request["result"], "changes_required")
        self.assertFalse(self.fx.review(request)["packetAccepted"])

    def test_fresh_review_cannot_refresh_old_measurement(self):
        receipt = self.observe(); request = self.review_request(receipt)
        original = self.store.fresh; seen = []
        def fresh(at, policy):
            seen.append(at)
            if at == receipt["observedAt"]: raise Refusal("Stale collected measurement")
            return original(at, policy)
        with patch.object(self.store, "fresh", side_effect=fresh):
            with self.assertRaisesRegex(Refusal, "Stale collected"): self.fx.review(request)
        self.assertIn(receipt["observedAt"], seen)

    def test_missing_request_receipt_refuses_review_and_replay(self):
        original = self.request(); receipt = self.observe(original); request = self.review_request(receipt)
        report = self.ledger.document(receipt["observationHash"])
        with self.ledger.tx() as db: db.execute("DELETE FROM snapshots WHERE id=?", (report["requestKey"],))
        with self.assertRaisesRegex(Refusal, "receipt changed or missing"): self.fx.review(request)
        # A lost request cannot silently refresh the stale revision.
        with self.assertRaises(Refusal): self.observe(original)

    def test_corrupted_receipt_does_not_replay_or_verify(self):
        original = self.request(); receipt = self.observe(original); request = self.review_request(receipt)
        report = self.ledger.document(receipt["observationHash"])
        with self.ledger.tx() as db:
            db.execute("UPDATE snapshots SET data=? WHERE id=?", (canonical({**receipt, "packetAccepted": True}), report["requestKey"]))
        with self.assertRaisesRegex(Refusal, "receipt changed or missing"): self.observe(original)
        with self.assertRaisesRegex(Refusal, "receipt changed or missing"): self.fx.review(request)

    def test_source_proof_is_not_ci_and_does_not_supply_required_checks(self):
        receipt = self.observe(); request = self.review_request(receipt)
        request["result"]["evidence"]["ci"] = copy.deepcopy(request["result"]["evidence"]["source"])
        with self.assertRaisesRegex(Refusal, "subject binding"): self.fx.review(self.fx.request(request["result"]))
        request = self.review_request(receipt)
        request["result"]["ci"]["requiredChecks"] = []
        with self.assertRaisesRegex(Refusal, "empty checks"): self.fx.review(self.fx.request(request["result"]))

    def test_expiry_and_revocation_refuse_before_filesystem_io(self):
        with patch.object(source, "inspect_source", side_effect=AssertionError("expired")), \
             patch("orchestrator.run_authority.time.time", return_value=time.time()+7200):
            with self.assertRaisesRegex(Refusal, "expired"): self.observe()
        run_fx = self.fx.fx.fx.fx.fx
        runs.revoke_task(self.ledger, run_fx.request(queueId=self.intent["queueId"],
            approvalHash=self.intent["approvalHash"], reason="Withdrawn fixture"), actor="dashboard_owner")
        with patch.object(source, "inspect_source", side_effect=AssertionError("revoked")):
            with self.assertRaisesRegex(Refusal, "approval"): self.observe()

    def test_harness_refuses_before_local_filesystem_inspection(self):
        initialize, seed = Ledger.initialize, test_core.seed
        def initialize_harness(ledger, config):
            config = copy.deepcopy(config)
            for repo in config["repositories"]:
                if repo["id"] == "a": repo["policyProfile"] = "harness"
            return initialize(ledger, config)
        def seed_harness(*args, **kwargs): return seed(*args, **(kwargs | {"profile": "harness"}))
        fx = test_ownership_settlement.OwnershipSettlementTest()
        with patch.object(Ledger, "initialize", initialize_harness), patch.object(test_core, "seed", seed_harness): fx.setUp()
        self.addCleanup(fx.tearDown); fx.settle()
        request = self.request(expectedRevision=fx.ledger.snapshot()["meta"]["revision"],
                               settlementHash=fx.worker()["ownershipSettlementHash"])
        with patch.object(source, "inspect_source", side_effect=AssertionError("no Harness inspection")):
            with self.assertRaisesRegex(Refusal, "Harness result acceptance needs its trusted adapter"):
                source.SourceObserver(fx.bridge).observe(fx.token, fx.wid, request)

    def test_remote_only_identity_needs_separate_local_binding(self):
        fx = test_ownership_settlement.OwnershipSettlementTest()
        remote = "repo-remote:"+"d"*64
        with patch.object(test_dispatch_admission, "KEY", remote), patch.object(test_ownership_settlement, "KEY", remote):
            fx.setUp(); self.addCleanup(fx.tearDown); fx.settle()
        request = self.request(expectedRevision=fx.ledger.snapshot()["meta"]["revision"],
                               settlementHash=fx.worker()["ownershipSettlementHash"])
        with patch.object(source, "inspect_source", side_effect=AssertionError("no local identity")):
            with self.assertRaisesRegex(Refusal, "pinned local"):
                source.SourceObserver(fx.bridge).observe(fx.token, fx.wid, request)

    def test_concurrent_same_request_retains_one_receipt(self):
        request = self.request(); barrier = threading.Barrier(2); inspect = source.inspect_source
        def simultaneous(*args, **kwargs):
            result = inspect(*args, **kwargs); barrier.wait(timeout=10); return result
        before = self.ledger.snapshot()["meta"]["revision"]
        with patch.object(source, "inspect_source", side_effect=simultaneous), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.observe, request) for _ in range(2)]
            receipts = [f.result() for f in futures]
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(before+1, self.ledger.snapshot()["meta"]["revision"])

    def test_source_read_error_leaves_no_artifacts_and_retry_can_succeed(self):
        before = self.fx.logical()
        with patch.object(source, "git_read", side_effect=Refusal("fixture missing local object")):
            with self.assertRaises(Refusal): self.observe()
        self.assertEqual(before, self.fx.logical()); self.assertTrue(self.observe()["sourceWithinScope"])

    def test_accepted_result_allows_historical_replay_not_new_collection(self):
        original = self.request(); receipt = self.observe(original)
        self.fx.review(self.review_request(receipt))
        with patch.object(source, "inspect_source", side_effect=AssertionError("accepted")):
            self.assertEqual(self.observe(original), receipt)
            with self.assertRaises(Refusal): self.observe(self.request(id="new"))

    def test_subprocess_interruption_before_and_after_commit(self):
        request = self.request(); before = self.fx.logical(); shared = self.store.snapshot()
        script = """
import json, os, sys
from orchestrator.admission import AdmissionStore
from orchestrator.dispatch_admission import DispatchAdmission
from orchestrator.source_observation import SourceObserver
from orchestrator.workspaces import Registry
registry = Registry(sys.argv[1])
api = SourceObserver(DispatchAdmission(registry, 'a', AdmissionStore(registry.root)))
if sys.argv[5] == 'before': api.ledger.event = lambda *args, **kwargs: os._exit(23)
api.observe(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]))
os._exit(24)
"""
        argv = [sys.executable, "-c", script, str(self.store.root), self.token, self.wid, canonical(request)]
        child = subprocess.run([*argv, "before"], capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 23, child.stderr.decode()); self.assertEqual(before, self.fx.logical())
        child = subprocess.run([*argv, "after"], capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 24, child.stderr.decode()); before = self.fx.logical()
        with patch.object(source, "inspect_source", side_effect=AssertionError("already committed")):
            self.assertTrue(self.observe(request)["sourceWithinScope"])
        self.assertEqual(before, self.fx.logical()); self.assertEqual(shared, self.store.snapshot())


if __name__ == "__main__": unittest.main()
